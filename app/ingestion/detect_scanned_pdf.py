from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from pypdf import PdfReader


@dataclass
class PdfScanDetectionResult:
    file_path: str
    is_scanned: bool
    pages_checked: int
    total_pages: int
    extracted_chars: int
    avg_chars_per_checked_page: float
    reason: str


def detect_scanned_pdf(
    pdf_path: str | Path,
    max_pages_to_check: int = 5,
    min_total_chars: int = 120,
    min_avg_chars_per_page: int = 40,
) -> PdfScanDetectionResult:
    """
    Detect whether a PDF is likely scanned (image-based) or text-based.

    Logic:
    - Read up to `max_pages_to_check` pages.
    - Extract text with pypdf.
    - If very little text is found, classify as scanned.

    Parameters
    ----------
    pdf_path : str | Path
        Path to the PDF file.
    max_pages_to_check : int
        Maximum number of pages to inspect from the beginning of the document.
    min_total_chars : int
        Minimum total extracted characters required to consider the PDF text-based.
    min_avg_chars_per_page : int
        Minimum average characters per checked page required to consider it text-based.

    Returns
    -------
    PdfScanDetectionResult
    """
    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(f"File is not a PDF: {pdf_path}")

    try:
        reader = PdfReader(str(pdf_path))
        total_pages = len(reader.pages)

        if total_pages == 0:
            return PdfScanDetectionResult(
                file_path=str(pdf_path),
                is_scanned=True,
                pages_checked=0,
                total_pages=0,
                extracted_chars=0,
                avg_chars_per_checked_page=0.0,
                reason="PDF has no pages",
            )

        pages_to_check = min(total_pages, max_pages_to_check)
        extracted_text_parts: list[str] = []

        for i in range(pages_to_check):
            try:
                page_text = reader.pages[i].extract_text() or ""
            except Exception:
                page_text = ""
            extracted_text_parts.append(page_text.strip())

        extracted_text = "\n".join(part for part in extracted_text_parts if part)
        extracted_chars = len(extracted_text)
        avg_chars = extracted_chars / pages_to_check if pages_to_check else 0.0

        # Main decision rule
        if extracted_chars < min_total_chars or avg_chars < min_avg_chars_per_page:
            return PdfScanDetectionResult(
                file_path=str(pdf_path),
                is_scanned=True,
                pages_checked=pages_to_check,
                total_pages=total_pages,
                extracted_chars=extracted_chars,
                avg_chars_per_checked_page=avg_chars,
                reason=(
                    f"Very little extractable text found "
                    f"(total_chars={extracted_chars}, avg_chars_per_page={avg_chars:.1f})"
                ),
            )

        return PdfScanDetectionResult(
            file_path=str(pdf_path),
            is_scanned=False,
            pages_checked=pages_to_check,
            total_pages=total_pages,
            extracted_chars=extracted_chars,
            avg_chars_per_checked_page=avg_chars,
            reason=(
                f"Sufficient extractable text found "
                f"(total_chars={extracted_chars}, avg_chars_per_page={avg_chars:.1f})"
            ),
        )

    except Exception as e:
        # If parsing fails entirely, safest assumption is scanned / needs OCR
        return PdfScanDetectionResult(
            file_path=str(pdf_path),
            is_scanned=True,
            pages_checked=0,
            total_pages=0,
            extracted_chars=0,
            avg_chars_per_checked_page=0.0,
            reason=f"PDF parsing failed: {e}",
        )


def is_scanned_pdf(
    pdf_path: str | Path,
    max_pages_to_check: int = 5,
    min_total_chars: int = 120,
    min_avg_chars_per_page: int = 40,
) -> bool:
    """
    Convenience wrapper that returns only True/False.
    """
    result = detect_scanned_pdf(
        pdf_path=pdf_path,
        max_pages_to_check=max_pages_to_check,
        min_total_chars=min_total_chars,
        min_avg_chars_per_page=min_avg_chars_per_page,
    )
    return result.is_scanned


if __name__ == "__main__":
    # Example manual test
    sample_path = "sample.pdf"
    result = detect_scanned_pdf(sample_path)
    print(result)