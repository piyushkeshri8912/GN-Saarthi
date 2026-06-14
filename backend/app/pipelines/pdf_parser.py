import fitz  # PyMuPDF
import pdfplumber
import io
import logging
from typing import List, Tuple
from app.config import settings
from app.services.ocr_service import OCRService

logger = logging.getLogger(__name__)

# Configuration constants
MIN_TEXT_THRESHOLD = 40
OCR_IMAGE_DPI = 150

# Singleton instance to avoid re-instantiating the service per page
_ocr_service_instance = None

def get_ocr_service() -> OCRService:
    global _ocr_service_instance
    if _ocr_service_instance is None:
        _ocr_service_instance = OCRService()
    return _ocr_service_instance

def extract_text_via_ocr(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    """
    Wrapper that routes OCR requests through the OCRService abstraction layer.
    """
    ocr_service = get_ocr_service()
    return ocr_service.perform_ocr(image_bytes, filename="pdf_page.jpeg", mime_type=mime_type)

def extract_text_from_image(image_bytes: bytes, filename: str) -> List[Tuple[int, str]]:
    """
    Extracts text from an image file using Gemini OCR.
    Returns a single page tuple: [(1, ocr_text)]
    """
    logger.info(f"Performing OCR on image: {filename}")
    ext = filename.lower().split(".")[-1]
    mime_map = {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "webp": "image/webp",
        "tiff": "image/tiff",
        "tif": "image/tiff",
    }
    mime_type = mime_map.get(ext, "image/jpeg")
    try:
        text = extract_text_via_ocr(image_bytes, mime_type=mime_type)
        return [(1, text)]
    except Exception as e:
        logger.error(f"Failed to perform OCR on image {filename}: {e}")
        raise ValueError(f"Failed to perform OCR on image: {e}")

def extract_text_from_pdf(pdf_bytes: bytes) -> List[Tuple[int, str]]:
    """
    Extracts text page-by-page from PDF bytes.
    Uses PyMuPDF (fitz) as the primary engine.
    If a page returns no text, falls back to pdfplumber for that page.
    If text is still empty or near-empty (< 40 characters), triggers page-level OCR fallback.
    
    Returns a list of tuples: (page_number_1_indexed, text_content)
    """
    pages_data = []
    
    try:
        # Open PDF with PyMuPDF
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page_idx in range(len(doc)):
            page_num = page_idx + 1
            page = doc[page_idx]
            text = page.get_text().strip()
            
            # Fallback to pdfplumber if text is empty
            if not text:
                logger.info(f"Page {page_num} returned empty text with PyMuPDF. Trying pdfplumber fallback.")
                try:
                    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                        if page_idx < len(pdf.pages):
                            plumber_text = pdf.pages[page_idx].extract_text()
                            if plumber_text:
                                text = plumber_text.strip()
                except Exception as pe:
                    logger.warning(f"pdfplumber fallback failed on page {page_num}: {pe}")
            
            # Check for structural layouts (timetables, schedules) that tend to get flattened and corrupted by raw text extraction
            has_structural_layout = any(
                kw in text.lower()
                for kw in ["schedule", "timetable", "timings", "calendar", "bus", "time-table", "seater", "route", "capacity", "class timings", "exam timings"]
            )
            
            trigger_ocr = (len(text) < MIN_TEXT_THRESHOLD) or (has_structural_layout and len(text) < 4000)
            if trigger_ocr:
                reason = "empty or near-empty text" if len(text) < MIN_TEXT_THRESHOLD else "structural schedule/table detected"
                logger.info(f"Page {page_num} triggers Gemini OCR fallback (reason: {reason}).")
                try:
                    pix = page.get_pixmap(dpi=OCR_IMAGE_DPI)
                    img_bytes = pix.tobytes("jpeg")
                    ocr_text = extract_text_via_ocr(img_bytes, mime_type="image/jpeg")
                    if ocr_text:
                        text = ocr_text
                        logger.info(f"Successfully extracted {len(text)} chars using OCR fallback on page {page_num}.")
                except Exception as oe:
                    logger.warning(f"OCR fallback failed on page {page_num} (skipping OCR for this page): {oe}")
            
            pages_data.append((page_num, text))
            
    except Exception as e:
        logger.error(f"PyMuPDF failed to parse PDF: {e}. Trying full pdfplumber fallback with page-level OCR fallback.")
        # Full fallback to pdfplumber
        try:
            pages_data = []
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for idx, page in enumerate(pdf.pages):
                    page_num = idx + 1
                    text = page.extract_text()
                    text = text.strip() if text else ""
                    
                    has_structural_layout = any(
                        kw in text.lower()
                        for kw in ["schedule", "timetable", "timings", "calendar", "bus", "time-table", "seater", "route", "capacity", "class timings", "exam timings"]
                    )
                    
                    trigger_ocr = (len(text) < MIN_TEXT_THRESHOLD) or (has_structural_layout and len(text) < 4000)
                    if trigger_ocr:
                        reason = "empty or near-empty text" if len(text) < MIN_TEXT_THRESHOLD else "structural schedule/table detected"
                        logger.info(f"Page {page_num} text triggers page-level OCR in full fallback (reason: {reason}).")
                        try:
                            doc_temp = fitz.open(stream=pdf_bytes, filetype="pdf")
                            page_temp = doc_temp[idx]
                            pix = page_temp.get_pixmap(dpi=OCR_IMAGE_DPI)
                            img_bytes = pix.tobytes("jpeg")
                            ocr_text = extract_text_via_ocr(img_bytes, mime_type="image/jpeg")
                            if ocr_text:
                                text = ocr_text
                        except Exception as oe:
                            logger.warning(f"Page-level OCR in fallback failed on page {page_num}: {oe}")
                            
                    pages_data.append((page_num, text))
        except Exception as pe:
            logger.error(f"Full pdfplumber fallback also failed: {pe}")
            raise ValueError(f"Failed to parse PDF document: {pe}")
            
    return pages_data
