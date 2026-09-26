"""
extraction_service.py

Text extraction layer of the RAG ingestion pipeline. Responsible for
converting an uploaded file (PDF, DOCX, TXT, Markdown, or image) on disk
into raw extracted text plus page-level metadata, before the text is
handed off to cleaning_service.py and then chunking_service.py.

Supported formats and their extraction strategy:
    pdf          -> pdfplumber (primary), PyPDF2 (fallback)
    docx         -> python-docx
    txt / md     -> direct UTF-8 read
    png/jpg/jpeg -> pytesseract OCR (via Pillow-loaded image)

Each extractor returns a list of page-level dicts so downstream chunking
can preserve page_number metadata for citations, e.g.:
    [{"page_number": 1, "text": "..."}, {"page_number": 2, "text": "..."}]

For formats without a native concept of "pages" (TXT, MD, single images),
the entire content is returned as a single page (page_number=1).
"""

import os
from typing import List, Dict

import pdfplumber
import PyPDF2
import docx
import pytesseract
from PIL import Image

from app.utils.logger import log_to_db


class ExtractionError(Exception):
    """
    Raised when text extraction fails for a given file (corrupted PDF,
    password-protected document, unreadable image, unsupported encoding,
    etc.). Caught by document_service.py to mark the Document's
    processing_status as "failed" with a user-facing error message.
    """

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


# ---------------------------------------------------------------------------
# Public Entry Point
# ---------------------------------------------------------------------------
def extract_text(file_path: str, file_type: str) -> List[Dict]:
    """
    Dispatches to the correct extraction strategy based on file_type and
    returns a normalized, page-level list of extracted text.

    Args:
        file_path: Absolute path to the file on disk (under storage/uploads/).
        file_type: One of "pdf", "docx", "txt", "md", "png", "jpg", "jpeg"
            (matches Document.file_type).

    Returns:
        A list of dicts: [{"page_number": int, "text": str}, ...]

    Raises:
        ExtractionError: If the file cannot be read or the format is
            unsupported.
    """
    if not os.path.exists(file_path):
        raise ExtractionError(f"File not found on disk: {file_path}")

    extractors = {
        "pdf": _extract_from_pdf,
        "docx": _extract_from_docx,
        "txt": _extract_from_text_file,
        "md": _extract_from_text_file,
        "png": _extract_from_image,
        "jpg": _extract_from_image,
        "jpeg": _extract_from_image,
    }

    extractor_fn = extractors.get(file_type.lower())
    if extractor_fn is None:
        raise ExtractionError(f"Unsupported file type for extraction: {file_type}")

    try:
        pages = extractor_fn(file_path)
    except ExtractionError:
        raise
    except Exception as exc:  # noqa: BLE001 — normalize all unexpected errors into ExtractionError
        log_to_db(
            level="ERROR",
            category="rag_pipeline",
            message=f"Text extraction failed for {file_path}",
            context={"file_type": file_type, "exception": str(exc)},
        )
        raise ExtractionError(f"Failed to extract text: {exc}") from exc

    # Filter out completely empty pages (e.g. blank PDF pages) but keep
    # page_number sequencing intact for accurate citations.
    non_empty_pages = [p for p in pages if p["text"] and p["text"].strip()]

    if not non_empty_pages:
        raise ExtractionError(
            "No readable text could be extracted from this file. "
            "It may be a scanned/image-only document, corrupted, or empty."
        )

    return non_empty_pages


# ---------------------------------------------------------------------------
# PDF Extraction
# ---------------------------------------------------------------------------
def _extract_from_pdf(file_path: str) -> List[Dict]:
    """
    Extracts text from a PDF page-by-page using pdfplumber (primary
    strategy, better at preserving layout/tables). Falls back to PyPDF2
    if pdfplumber fails to open the file (e.g. certain malformed PDFs).

    Args:
        file_path: Absolute path to the PDF file.

    Returns:
        A list of {"page_number": int, "text": str} dicts, one per page.
    """
    try:
        pages = []
        with pdfplumber.open(file_path) as pdf:
            for index, page in enumerate(pdf.pages, start=1):
                page_text = page.extract_text() or ""
                pages.append({"page_number": index, "text": page_text})
        return pages
    except Exception:
        return _extract_from_pdf_fallback(file_path)


def _extract_from_pdf_fallback(file_path: str) -> List[Dict]:
    """
    Fallback PDF extraction using PyPDF2, used when pdfplumber cannot
    open/parse the file. Less accurate for complex layouts/tables but
    more tolerant of certain malformed PDF structures.

    Args:
        file_path: Absolute path to the PDF file.

    Returns:
        A list of {"page_number": int, "text": str} dicts, one per page.

    Raises:
        ExtractionError: If PyPDF2 also fails (e.g. password-protected
            or severely corrupted PDF).
    """
    try:
        pages = []
        with open(file_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)

            if reader.is_encrypted:
                raise ExtractionError(
                    "This PDF is password-protected. Please remove the password and re-upload."
                )

            for index, page in enumerate(reader.pages, start=1):
                page_text = page.extract_text() or ""
                pages.append({"page_number": index, "text": page_text})
        return pages
    except ExtractionError:
        raise
    except Exception as exc:
        raise ExtractionError(f"Unable to read this PDF file: {exc}") from exc


# ---------------------------------------------------------------------------
# DOCX Extraction
# ---------------------------------------------------------------------------
def _extract_from_docx(file_path: str) -> List[Dict]:
    """
    Extracts text from a Word document using python-docx. DOCX has no
    native page-boundary concept in the underlying XML, so all paragraph
    text is returned as a single logical page (page_number=1); precise
    page-level citation for DOCX is a known limitation noted in the
    Future Features roadmap (PDF conversion pre-pass).

    Args:
        file_path: Absolute path to the .docx file.

    Returns:
        A single-element list: [{"page_number": 1, "text": str}]
    """
    document = docx.Document(file_path)
    paragraphs = [p.text for p in document.paragraphs if p.text and p.text.strip()]

    # Also pull text out of any tables in the document, since python-docx
    # does not include table cell text in document.paragraphs.
    for table in document.tables:
        for row in table.rows:
            row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
            if row_text:
                paragraphs.append(row_text)

    full_text = "\n".join(paragraphs)
    return [{"page_number": 1, "text": full_text}]


# ---------------------------------------------------------------------------
# Plain Text / Markdown Extraction
# ---------------------------------------------------------------------------
def _extract_from_text_file(file_path: str) -> List[Dict]:
    """
    Reads a .txt or .md file directly as UTF-8 text. Falls back to
    latin-1 decoding if UTF-8 decoding fails, to tolerate files saved
    with a different encoding rather than rejecting the upload outright.

    Args:
        file_path: Absolute path to the .txt or .md file.

    Returns:
        A single-element list: [{"page_number": 1, "text": str}]
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except UnicodeDecodeError:
        with open(file_path, "r", encoding="latin-1") as f:
            content = f.read()

    return [{"page_number": 1, "text": content}]


# ---------------------------------------------------------------------------
# Image OCR Extraction
# ---------------------------------------------------------------------------
def _extract_from_image(file_path: str) -> List[Dict]:
    """
    Runs OCR on an image file (PNG/JPG/JPEG) using pytesseract, allowing
    students to upload photographed or scanned notes.

    Args:
        file_path: Absolute path to the image file.

    Returns:
        A single-element list: [{"page_number": 1, "text": str}]

    Raises:
        ExtractionError: If OCR produces no usable text (e.g. blurry
            image, or the Tesseract binary is not installed on the host).
    """
    try:
        image = Image.open(file_path)
        ocr_text = pytesseract.image_to_string(image)
    except pytesseract.TesseractNotFoundError as exc:
        raise ExtractionError(
            "OCR engine is not available on the server. Please contact support."
        ) from exc
    except Exception as exc:
        raise ExtractionError(f"Unable to process this image: {exc}") from exc

    return [{"page_number": 1, "text": ocr_text}]