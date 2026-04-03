"""
extractor/ocr_fallback.py — OCR fallback for scanned or corrupted PDF pages.
Called only when pdfplumber returns no extractable text.

FLAW A FIX — Image pre-processing pipeline:
  Before passing any image to Tesseract, apply:
    1. Convert to greyscale
    2. Deskew (correct scan tilt up to ±10°) using OpenCV contour analysis
    3. Denoise with fastNlMeansDenoising
    4. Binarise with Otsu adaptive threshold
    5. Ensure DPI ≥ 300 (upscale if render came out smaller)

  OpenCV (cv2) is used; installed as opencv-python-headless.
  If cv2 is not available the pre-processor is a no-op — Tesseract still runs,
  just on the raw image.  No crash, no import error exposed to callers.

Strategy (in order):
  1. pymupdf (fitz) — renders page to high-DPI image, pre-processes, OCRs.
     No Poppler required.
  2. pdf2image + pytesseract — classic Tesseract pipeline (requires Poppler).
  3. Graceful skip — logs warning, returns empty string.
"""

from __future__ import annotations

import io
import logging

from extractor.pdf_parser import PageResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Image pre-processing (Flaw A fix)
# ---------------------------------------------------------------------------

def _preprocess_image(img: "PIL.Image.Image") -> "PIL.Image.Image":  # type: ignore[name-defined]
    """
    Apply greyscale → deskew → denoise → binarise pipeline.
    Returns the processed image, or the original if cv2 is unavailable.

    Steps:
      1. Greyscale                    — removes colour noise that confuses Tesseract
      2. Deskew                       — corrects scan tilt up to ±10°
      3. fastNlMeansDenoising         — removes salt-and-pepper noise
      4. Otsu binarisation            — converts grey → pure black/white
    """
    try:
        import cv2  # type: ignore
        import numpy as np

        # ── 1. Greyscale ───────────────────────────────────────────────────
        img_array = np.array(img.convert("RGB"))
        grey = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)

        # ── 2. Deskew ──────────────────────────────────────────────────────
        # Invert so text is white on black (needed for contour detection)
        inverted = cv2.bitwise_not(grey)
        # Find all non-zero (text) pixel coordinates
        coords = np.column_stack(np.where(inverted > 0))
        if len(coords) > 50:  # need enough text pixels for a reliable angle
            # minAreaRect returns the angle of the bounding box
            angle = cv2.minAreaRect(coords)[-1]
            # minAreaRect angles: -90 < angle ≤ 0
            # Text tilted right → small negative angle; tilted left → near -90
            if angle < -45:
                angle = -(90 + angle)
            else:
                angle = -angle
            # Only correct small tilts — large angles are page-turn errors
            if abs(angle) < 10:
                h, w = grey.shape
                M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
                grey = cv2.warpAffine(
                    grey, M, (w, h),
                    flags=cv2.INTER_CUBIC,
                    borderMode=cv2.BORDER_REPLICATE,
                )
                logger.debug("Deskewed page by %.2f°", angle)

        # ── 3. Denoise ─────────────────────────────────────────────────────
        # h=10: filter strength (higher = more noise removed, but blurs text)
        denoised = cv2.fastNlMeansDenoising(grey, h=10, templateWindowSize=7, searchWindowSize=21)

        # ── 4. Otsu binarisation ───────────────────────────────────────────
        _, binary = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # Convert back to PIL Image
        from PIL import Image
        processed = Image.fromarray(binary)
        logger.debug("Image pre-processing complete: greyscale → deskew → denoise → binarise")
        return processed

    except ImportError:
        logger.debug("cv2 not available — skipping image pre-processing (results may be lower quality)")
        return img
    except Exception as exc:
        logger.warning("Image pre-processing error (returning raw image): %s", exc)
        return img


def _ensure_min_dpi(img: "PIL.Image.Image", target_dpi: int = 300) -> "PIL.Image.Image":  # type: ignore[name-defined]
    """
    Upscale the image if its embedded DPI information is below target_dpi.
    Tesseract accuracy degrades significantly below 200 DPI.
    """
    try:
        info = img.info or {}
        current_dpi = info.get("dpi", (0, 0))
        current_dpi_val = current_dpi[0] if isinstance(current_dpi, tuple) else current_dpi

        if current_dpi_val and 0 < current_dpi_val < target_dpi:
            scale = target_dpi / current_dpi_val
            new_w = int(img.width * scale)
            new_h = int(img.height * scale)
            from PIL import Image
            img = img.resize((new_w, new_h), Image.LANCZOS)
            logger.debug("Upscaled image from %ddpi to %ddpi (scale=%.2f)", current_dpi_val, target_dpi, scale)
    except Exception as exc:
        logger.debug("DPI check skipped: %s", exc)
    return img


# ---------------------------------------------------------------------------
# OCR strategies
# ---------------------------------------------------------------------------

def _ocr_via_pymupdf(pdf_bytes: bytes, page_number: int) -> str:
    """
    Use pymupdf (fitz) to render the page at 300 DPI, pre-process, then OCR.
    No Poppler required.  page_number is 1-indexed.
    """
    try:
        import fitz  # type: ignore  # pip install pymupdf
        from PIL import Image

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page_idx = page_number - 1

        if page_idx < 0 or page_idx >= len(doc):
            return ""

        page = doc[page_idx]

        # First try: direct text extraction (works on many "corrupt" PDFs)
        text = page.get_text("text").strip()
        if text and len(text) > 20:
            logger.info("pymupdf direct text: page %d, chars=%d", page_number, len(text))
            return text

        # Second try: render at 300 DPI → pre-process → Tesseract
        try:
            import pytesseract  # type: ignore

            # mat = zoom matrix for 300 DPI (PDF default is 72 DPI, factor = 300/72 ≈ 4.17)
            zoom = 300 / 72
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img_bytes = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_bytes))

            # ── Flaw A: apply pre-processing ──────────────────────────────
            img = _ensure_min_dpi(img, target_dpi=300)
            img = _preprocess_image(img)

            text = pytesseract.image_to_string(img, lang="eng", config="--psm 6").strip()
            logger.info("pymupdf+tesseract OCR (pre-processed): page %d, chars=%d", page_number, len(text))
            return text

        except ImportError:
            pass  # Tesseract not available

        return text  # return whatever direct extraction got

    except ImportError:
        logger.debug("pymupdf (fitz) not installed, skipping fitz OCR path.")
        return ""
    except Exception as exc:
        logger.warning("pymupdf OCR failed for page %d: %s", page_number, exc)
        return ""


def _ocr_via_pdf2image(pdf_bytes: bytes, page_number: int) -> str:
    """
    Classic Tesseract pipeline via pdf2image. Requires Poppler on system PATH.
    """
    try:
        from pdf2image import convert_from_bytes  # type: ignore
        import pytesseract  # type: ignore

        images = convert_from_bytes(
            pdf_bytes,
            first_page=page_number,
            last_page=page_number,
            dpi=300,
        )
        if not images:
            return ""

        img = images[0]

        # ── Flaw A: apply pre-processing ──────────────────────────────────
        img = _ensure_min_dpi(img, target_dpi=300)
        img = _preprocess_image(img)

        text = pytesseract.image_to_string(img, lang="eng", config="--psm 6").strip()
        logger.info("pdf2image+tesseract OCR (pre-processed): page %d, chars=%d", page_number, len(text))
        return text

    except ImportError:
        logger.warning("pdf2image / pytesseract not installed — OCR unavailable for page %d.", page_number)
        return ""
    except Exception as exc:
        err_str = str(exc)
        if "poppler" in err_str.lower() or "pdfinfo" in err_str.lower():
            logger.warning(
                "Poppler not installed — pdf2image OCR skipped for page %d. "
                "Install from https://github.com/oschwartz10612/poppler-windows/releases",
                page_number,
            )
        else:
            logger.error("pdf2image OCR failed for page %d: %s", page_number, exc)
        return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ocr_page(pdf_bytes: bytes, page_number: int) -> str:
    """
    Run OCR on a single page with image pre-processing.
    Tries pymupdf first (pre-processed), then pdf2image+Tesseract (pre-processed).
    Returns extracted text or empty string on all failures.
    """
    # Strategy 1: pymupdf (preferred — no Poppler needed)
    text = _ocr_via_pymupdf(pdf_bytes, page_number)
    if text and len(text) > 20:
        return text

    # Strategy 2: pdf2image + Tesseract (needs Poppler)
    return _ocr_via_pdf2image(pdf_bytes, page_number)


def apply_ocr_to_document(
    pdf_bytes: bytes,
    pages: list[PageResult],
) -> list[PageResult]:
    """
    For every PageResult that has needs_ocr=True, run pre-processed OCR and
    populate raw_text. Returns the updated pages list (in-place mutation).
    """
    scanned = [p for p in pages if p.needs_ocr]
    if not scanned:
        return pages

    logger.info("Running pre-processed OCR on %d scanned page(s).", len(scanned))

    for page in scanned:
        text = ocr_page(pdf_bytes, page.page_number)
        if text:
            page.raw_text = text
            page.page_type = "item_table"
            page.needs_ocr = False
        else:
            logger.warning(
                "Page %d: no extractable text after pre-processed OCR. "
                "This page will be skipped.",
                page.page_number,
            )

    return pages
