import os
import logging
import fitz  # PyMuPDF
import pytesseract
from PIL import Image

logger = logging.getLogger(__name__)

# NOTE: If Tesseract is not in your SYSTEM PATH on Windows, you will need to uncomment 
# and set the path explicitly like below:
# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

def extract_text_from_pdf(file_path: str) -> str:
    """Extracts text from a multi-page PDF document."""
    text_content = []
    try:
        with fitz.open(file_path) as pdf_doc:
            for page in pdf_doc:
                text_content.append(page.get_text())
        return "\n".join(text_content)
    except Exception as e:
        logger.error(f"Failed to read PDF {file_path}: {e}")
        return ""

def extract_text_from_image(file_path: str) -> str:
    """Extracts text from an image file using Tesseract OCR."""
    try:
        img = Image.open(file_path)
        text = pytesseract.image_to_string(img)
        return text
    except Exception as e:
        logger.error(f"Failed to extract text from Image {file_path}: {e}")
        return ""

def clean_extracted_text(text: str) -> str:
    """Basic cleaning to remove excessive whitespace and garbage characters."""
    # Split by lines, strip whitespace, drop empty lines, and recombine
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    return "\n".join(lines).strip()

def process_report_file(file_path: str, file_type: str) -> str:
    """
    Main orchestration function.
    Reads the file from disk, figures out the parser, and extracts text.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found at: {file_path}")
        
    extracted_text = ""
    file_type = file_type.lower()
    
    # Simple routing based on file type
    if "pdf" in file_type or file_path.endswith(".pdf"):
        extracted_text = extract_text_from_pdf(file_path)
    elif "image" in file_type or file_path.endswith((".png", ".jpg", ".jpeg")):
        extracted_text = extract_text_from_image(file_path)
    else:
        raise ValueError(f"Unsupported file type for extraction: {file_type}")
            
    if not extracted_text.strip():
        raise ValueError("Could not extract any text from the document. The file might be empty, corrupted, or handwritten text is unrecognizable.")
        
    return clean_extracted_text(extracted_text)
