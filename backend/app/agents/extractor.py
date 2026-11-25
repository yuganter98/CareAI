"""
Text extraction from uploaded reports.

Extraction is page-aware: `extract_report_pages()` returns one entry per page so
chunks can record the page they came from and answers can cite "page 3". The
older `process_report_file()` still returns a single joined string for callers
that only need the full text.
"""

import os
import logging
from typing import List, TypedDict

import fitz  # PyMuPDF
import pytesseract
from PIL import Image

logger = logging.getLogger(__name__)

# NOTE: If Tesseract is not in your SYSTEM PATH on Windows, you will need to uncomment
# and set the path explicitly like below:
# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'


class Page(TypedDict):
    """One page of extracted text. `page` is 1-based, as printed on the document."""
    page: int
    text: str


def extract_pages_from_pdf(file_path: str) -> List[Page]:
    """Extracts text from a multi-page PDF, one entry per page."""
    pages: List[Page] = []
    try:
        with fitz.open(file_path) as pdf_doc:
            for index, page in enumerate(pdf_doc, start=1):
                pages.append({"page": index, "text": page.get_text()})
    except Exception as e:
        logger.error(f"Failed to read PDF {file_path}: {e}")
        return []
    return pages


def extract_pages_from_image(file_path: str) -> List[Page]:
    """Extracts text from an image file using Tesseract OCR. An image is one page."""
    try:
        img = Image.open(file_path)
        return [{"page": 1, "text": pytesseract.image_to_string(img)}]
    except Exception as e:
        logger.error(f"Failed to extract text from Image {file_path}: {e}")
        return []


def extract_text_from_pdf(file_path: str) -> str:
    """Full text of a PDF, pages joined. Kept for callers that don't need pages."""
    return "\n".join(p["text"] for p in extract_pages_from_pdf(file_path))


def extract_text_from_image(file_path: str) -> str:
    """Full text of an image. Kept for callers that don't need pages."""
    pages = extract_pages_from_image(file_path)
    return pages[0]["text"] if pages else ""


def clean_extracted_text(text: str) -> str:
    """Basic cleaning to remove excessive whitespace and garbage characters."""
    # Split by lines, strip whitespace, drop empty lines, and recombine
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    return "\n".join(lines).strip()


def join_pages(pages: List[Page]) -> str:
    """Join page texts into one string, in page order."""
    return "\n".join(p["text"] for p in pages)


def extract_report_pages(file_path: str, file_type: str) -> List[Page]:
    """
    Main extraction entrypoint.

    Reads the file from disk, picks the parser by type, cleans each page and
    drops pages that hold no text. Page numbers stay as printed on the document,
    so a blank page 2 does not renumber page 3.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found at: {file_path}")

    file_type = (file_type or "").lower()

    # Simple routing based on file type
    if "pdf" in file_type or file_path.endswith(".pdf"):
        pages = extract_pages_from_pdf(file_path)
    elif "image" in file_type or file_path.endswith((".png", ".jpg", ".jpeg")):
        pages = extract_pages_from_image(file_path)
    else:
        raise ValueError(f"Unsupported file type for extraction: {file_type}")

    cleaned = [
        {"page": p["page"], "text": clean_extracted_text(p["text"])}
        for p in pages
    ]
    cleaned = [p for p in cleaned if p["text"]]

    if not cleaned:
        raise ValueError(
            "Could not extract any text from the document. The file might be empty, "
            "corrupted, or handwritten text is unrecognizable."
        )

    return cleaned


def process_report_file(file_path: str, file_type: str) -> str:
    """The whole document as one cleaned string."""
    return join_pages(extract_report_pages(file_path, file_type))
