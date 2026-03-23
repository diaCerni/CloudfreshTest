import io
import os
import tempfile
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.cloud import storage

from app.ingestion.detect_scanned_pdf import detect_scanned_pdf
from app.ingestion.ocr_document_ai import ocr_file_to_gcs_txt

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

DRIVE_FOLDER_ID = "1zazAIvbvCOBxYisJLXqYNo9WetNNBb0x"
BUCKET_NAME = "cloudfresh_test_bucket"
PROJECT_ID = "cloudfresh-test-2"

RAW_PREFIX = "archive/processed"
PROCESSED_PREFIX = "processed"

DOCAI_LOCATION = "us"
DOCAI_PROCESSOR_ID = "9bd06fe7b4a6b6b3"

EXPORT_MAP = {
    "application/vnd.google-apps.document": ("application/pdf", ".pdf"),
    "application/vnd.google-apps.presentation": ("application/pdf", ".pdf"),
    "application/vnd.google-apps.spreadsheet": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xlsx",
    ),
}


def get_drive_service():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)

        with open("token.json", "w") as token:
            token.write(creds.to_json())

    return build("drive", "v3", credentials=creds)


def sanitize_name(name: str) -> str:
    return "".join(c if c.isalnum() or c in "._- " else "_" for c in name).strip()


def upload_bytes_to_gcs(bucket_name: str, blob_name: str, content: bytes, content_type: str | None = None):
    client = storage.Client(project=PROJECT_ID)
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.upload_from_string(content, content_type=content_type)


def upload_text_to_gcs(bucket_name: str, blob_name: str, text: str):
    upload_bytes_to_gcs(
        bucket_name=bucket_name,
        blob_name=blob_name,
        content=text.encode("utf-8"),
        content_type="text/plain; charset=utf-8",
    )


def list_files_in_folder(service, folder_id: str):
    query = f"'{folder_id}' in parents and trashed = false"
    results = service.files().list(
        q=query,
        fields="files(id, name, mimeType, modifiedTime)"
    ).execute()
    return results.get("files", [])


def download_or_export_file(service, file_meta):
    file_id = file_meta["id"]
    name = sanitize_name(file_meta["name"])
    mime_type = file_meta["mimeType"]

    if mime_type.startswith("application/vnd.google-apps."):
        if mime_type not in EXPORT_MAP:
            return None, None, None
        export_mime, ext = EXPORT_MAP[mime_type]
        request = service.files().export_media(fileId=file_id, mimeType=export_mime)
        filename = f"{name}{ext}"
        output_mime_type = export_mime
    else:
        request = service.files().get_media(fileId=file_id)
        filename = name
        output_mime_type = mime_type

    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)

    done = False
    while not done:
        _, done = downloader.next_chunk()

    return filename, fh.getvalue(), output_mime_type


def save_temp_file(filename: str, content: bytes) -> str:
    suffix = Path(filename).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        return tmp.name


def is_pdf_file(filename: str) -> bool:
    return Path(filename).suffix.lower() == ".pdf"


def main():
    service = get_drive_service()
    files = list_files_in_folder(service, DRIVE_FOLDER_ID)

    for f in files:
        filename, content, mime_type = download_or_export_file(service, f)
        if not filename or not content:
            print(f"Skipping unsupported file: {f['name']} ({f['mimeType']})")
            continue

        # Optional archive copy of original
        raw_blob_name = f"{RAW_PREFIX}/{filename}"
        upload_bytes_to_gcs(BUCKET_NAME, raw_blob_name, content, content_type=mime_type)
        print(f"Archived raw: gs://{BUCKET_NAME}/{raw_blob_name}")

        # Non-PDF files: upload directly to processed
        if not is_pdf_file(filename):
            processed_blob_name = f"{PROCESSED_PREFIX}/{filename}"
            upload_bytes_to_gcs(BUCKET_NAME, processed_blob_name, content, content_type=mime_type)
            print(f"Uploaded processed: gs://{BUCKET_NAME}/{processed_blob_name}")
            continue

        temp_path = save_temp_file(filename, content)

        try:
            scan_result = detect_scanned_pdf(temp_path)
            print(
                f"Scan detection for {filename}: "
                f"is_scanned={scan_result.is_scanned}, "
                f"reason={scan_result.reason}"
            )

            if scan_result.is_scanned:
                processed_blob_name = f"{PROCESSED_PREFIX}/{Path(filename).stem}.txt"

                ocr_result, gcs_uri = ocr_file_to_gcs_txt(
                    project_id=PROJECT_ID,
                    location=DOCAI_LOCATION,
                    processor_id=DOCAI_PROCESSOR_ID,
                    input_file_path=temp_path,
                    bucket_name=BUCKET_NAME,
                    destination_blob_name=processed_blob_name,
                )

                print(
                    f"OCR uploaded to processed: {gcs_uri} "
                    f"(chars={ocr_result.char_count})"
                )
            else:
                processed_blob_name = f"{PROCESSED_PREFIX}/{filename}"
                upload_bytes_to_gcs(BUCKET_NAME, processed_blob_name, content, content_type="application/pdf")
                print(f"Uploaded processed PDF: gs://{BUCKET_NAME}/{processed_blob_name}")

        except Exception as e:
            print(f"OCR pipeline failed for {filename}: {e}")

        finally:
            try:
                os.remove(temp_path)
            except Exception:
                pass


if __name__ == "__main__":
    main()