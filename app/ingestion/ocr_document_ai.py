from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from google.api_core.client_options import ClientOptions
from google.cloud import documentai_v1 as documentai
from google.cloud import storage


@dataclass
class OcrResult:
    input_file: str
    output_text: str
    output_text_path: Optional[str]
    mime_type: str
    processor_name: str
    char_count: int


def guess_mime_type(file_path: str | Path) -> str:
    suffix = Path(file_path).suffix.lower()
    if suffix == ".pdf":
        return "application/pdf"
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    if suffix == ".tif" or suffix == ".tiff":
        return "image/tiff"
    raise ValueError(f"Unsupported file type: {suffix}")


def process_document_ocr(
    project_id: str,
    location: str,
    processor_id: str,
    input_file_path: str | Path,
    mime_type: Optional[str] = None,
) -> OcrResult:
    """
    Run OCR on a local file using Google Cloud Document AI.

    Parameters
    ----------
    project_id : str
        Google Cloud project ID.
    location : str
        Document AI processor region, e.g. 'us' or 'eu'.
    processor_id : str
        OCR processor ID from Document AI.
    input_file_path : str | Path
        Local path to the file.
    mime_type : Optional[str]
        Optional explicit mime type. If omitted, guessed from extension.

    Returns
    -------
    OcrResult
    """
    input_file_path = Path(input_file_path)

    if not input_file_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_file_path}")

    mime_type = mime_type or guess_mime_type(input_file_path)

    client = documentai.DocumentProcessorServiceClient(
        client_options=ClientOptions(
            api_endpoint=f"{location}-documentai.googleapis.com"
        )
    )

    processor_name = client.processor_path(project_id, location, processor_id)

    with open(input_file_path, "rb") as f:
        raw_document = documentai.RawDocument(
            content=f.read(),
            mime_type=mime_type,
        )

    request = documentai.ProcessRequest(
        name=processor_name,
        raw_document=raw_document,
    )

    result = client.process_document(request=request)
    document = result.document
    full_text = document.text or ""

    return OcrResult(
        input_file=str(input_file_path),
        output_text=full_text,
        output_text_path=None,
        mime_type=mime_type,
        processor_name=processor_name,
        char_count=len(full_text),
    )


def save_ocr_text_locally(
    ocr_result: OcrResult,
    output_txt_path: str | Path,
    encoding: str = "utf-8",
) -> OcrResult:
    """
    Save OCR text to a local .txt file.
    """
    output_txt_path = Path(output_txt_path)
    output_txt_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_txt_path, "w", encoding=encoding) as f:
        f.write(ocr_result.output_text)

    ocr_result.output_text_path = str(output_txt_path)
    return ocr_result


def upload_text_to_gcs(
    bucket_name: str,
    destination_blob_name: str,
    text: str,
    project_id: Optional[str] = None,
) -> str:
    """
    Upload OCR text to a GCS object and return the gs:// URI.
    """
    client = storage.Client(project=project_id) if project_id else storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)
    blob.upload_from_string(text, content_type="text/plain; charset=utf-8")
    return f"gs://{bucket_name}/{destination_blob_name}"


def ocr_file_to_local_txt(
    project_id: str,
    location: str,
    processor_id: str,
    input_file_path: str | Path,
    output_txt_path: str | Path,
    mime_type: Optional[str] = None,
) -> OcrResult:
    """
    Convenience wrapper:
    local file -> Document AI OCR -> local txt
    """
    result = process_document_ocr(
        project_id=project_id,
        location=location,
        processor_id=processor_id,
        input_file_path=input_file_path,
        mime_type=mime_type,
    )
    return save_ocr_text_locally(result, output_txt_path)


def ocr_file_to_gcs_txt(
    project_id: str,
    location: str,
    processor_id: str,
    input_file_path: str | Path,
    bucket_name: str,
    destination_blob_name: str,
    mime_type: Optional[str] = None,
) -> tuple[OcrResult, str]:
    """
    Convenience wrapper:
    local file -> Document AI OCR -> upload OCR text to GCS
    """
    result = process_document_ocr(
        project_id=project_id,
        location=location,
        processor_id=processor_id,
        input_file_path=input_file_path,
        mime_type=mime_type,
    )
    gcs_uri = upload_text_to_gcs(
        bucket_name=bucket_name,
        destination_blob_name=destination_blob_name,
        text=result.output_text,
        project_id=project_id,
    )
    return result, gcs_uri


if __name__ == "__main__":
    # Example usage:
    PROJECT_ID = "cloudfresh-test-2"
    LOCATION = "us"  # or "eu"
    PROCESSOR_ID = "9bd06fe7b4a6b6b3"

    INPUT_FILE = "C:\\Users\\dcernazanu\\Downloads\\cookery_for_little_girls_without_last_page.pdf"
    OUTPUT_TXT = "output/sample_scan.txt"

    result = ocr_file_to_local_txt(
        project_id=PROJECT_ID,
        location=LOCATION,
        processor_id=PROCESSOR_ID,
        input_file_path=INPUT_FILE,
        output_txt_path=OUTPUT_TXT,
    )

    print("OCR complete")
    print("Input:", result.input_file)
    print("Chars:", result.char_count)
    print("Saved to:", result.output_text_path)