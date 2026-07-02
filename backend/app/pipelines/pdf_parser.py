import io
import logging
from typing import List, Tuple

import fitz  # PyMuPDF
import pdfplumber

from app.services.ocr_service import OCRService

logger = logging.getLogger(__name__)

MIN_TEXT_THRESHOLD = 40
OCR_IMAGE_DPI = 150


_ocr_service: OCRService | None = None

def get_ocr_service() -> OCRService:
    return OCRService()


def extract_text_via_ocr(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    return get_ocr_service().perform_ocr(
        image_bytes,
        filename="pdf_page.jpeg",
        mime_type=mime_type,
    )


def _has_structural_layout(page, text: str) -> bool:
    """Detect structural content (tables, schedules, timetables) using table API and line heuristics."""
    try:
        tables = page.find_tables()
        if getattr(tables, "tables", None):
            return True
    except Exception:
        pass

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) > 15:
        short_lines = sum(1 for line in lines if len(line) < 40)
        if short_lines / len(lines) > 0.75:
            return True

    return False


def _needs_ocr(text: str, structural: bool) -> bool:
    return len(text) < MIN_TEXT_THRESHOLD or (structural and len(text) < 1500)


def _ocr_page(page) -> str:
    pix = page.get_pixmap(dpi=OCR_IMAGE_DPI)
    img_bytes = pix.tobytes("jpeg")
    return extract_text_via_ocr(img_bytes, mime_type="image/jpeg").strip()


def _extract_page_text(page, page_num: int, plumber_page=None) -> str:
    text = (page.get_text() or "").strip()

    if not text and plumber_page is not None:
        text = (plumber_page.extract_text() or "").strip()

    structural = _has_structural_layout(page, text)
    if _needs_ocr(text, structural):
        reason = "empty or near-empty text" if len(text) < MIN_TEXT_THRESHOLD else "structural table/layout"
        logger.info("Page %d triggers OCR fallback (%s).", page_num, reason)

        try:
            ocr_text = _ocr_page(page)
            if ocr_text:
                return ocr_text
        except Exception as exc:
            logger.warning("OCR fallback failed on page %d: %s", page_num, exc)

    return text


def _extract_with_fitz(pdf_bytes: bytes) -> List[Tuple[int, str]]:
    pages_data: List[Tuple[int, str]] = []
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    plumber = None
    try:
        try:
            plumber = pdfplumber.open(io.BytesIO(pdf_bytes))
        except Exception as exc:
            logger.warning("pdfplumber init failed, continuing without it: %s", exc)

        for idx in range(len(doc)):
            page_num = idx + 1
            page = doc[idx]
            plumber_page = plumber.pages[idx] if plumber and idx < len(plumber.pages) else None
            text = _extract_page_text(page, page_num, plumber_page)
            pages_data.append((page_num, text))

        return pages_data

    finally:
        if plumber is not None:
            plumber.close()
        doc.close()


def _extract_with_pdfplumber(pdf_bytes: bytes) -> List[Tuple[int, str]]:
    pages_data: List[Tuple[int, str]] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for idx, page in enumerate(pdf.pages):
            page_num = idx + 1
            text = (page.extract_text() or "").strip()
            pages_data.append((page_num, text))
    return pages_data


def extract_text_from_pdf(pdf_bytes: bytes) -> List[Tuple[int, str]]:
    """
    Extract text page by page from a PDF.

    Primary path:
    - PyMuPDF for text
    - pdfplumber for text fallback
    - OCR for empty / weak / structural pages

    Secondary path:
    - pdfplumber-only text extraction if PyMuPDF fails
    """
    try:
        return _extract_with_fitz(pdf_bytes)
    except Exception as exc:
        logger.error("PyMuPDF failed to parse PDF: %s", exc, exc_info=True)

    try:
        return _extract_with_pdfplumber(pdf_bytes)
    except Exception as exc:
        logger.error("pdfplumber fallback also failed: %s", exc, exc_info=True)
        raise ValueError(f"Failed to parse PDF document: {exc}") from exc


def extract_text_from_image(image_bytes: bytes, filename: str) -> List[Tuple[int, str]]:
    logger.info("Performing OCR on image: %s", filename)

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
    except Exception as exc:
        logger.error("Failed to perform OCR on image %s: %s", filename, exc, exc_info=True)
        raise ValueError(f"Failed to perform OCR on image: {exc}") from exc