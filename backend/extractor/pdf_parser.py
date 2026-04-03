"""
extractor/pdf_parser.py — PDF text and table extraction using pdfplumber.
Scanned pages with no extractable text are flagged for OCR fallback.
Pages processed in parallel using ThreadPoolExecutor for speed.
"""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Optional

import pdfplumber

from config import MAX_PDF_WORKERS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class PageResult:
    page_number: int
    page_type: str              # "header" | "item_table" | "summary" | "scanned"
    raw_text: str
    tables: list[list[list[str | None]]]  # list of tables, each table = list of rows
    needs_ocr: bool = False


@dataclass
class ParsedDocument:
    pages: list[PageResult] = field(default_factory=list)
    total_pages: int = 0
    has_scanned_pages: bool = False

    @property
    def full_text(self) -> str:
        return "\n\n".join(p.raw_text for p in self.pages if not p.needs_ocr)

    @property
    def header_pages(self) -> list[PageResult]:
        return [p for p in self.pages if p.page_type == "header"]

    @property
    def item_pages(self) -> list[PageResult]:
        return [p for p in self.pages if p.page_type == "item_table"]

    @property
    def summary_pages(self) -> list[PageResult]:
        return [p for p in self.pages if p.page_type == "summary"]


# ---------------------------------------------------------------------------
# Page classification heuristics
# ---------------------------------------------------------------------------

_HEADER_KEYWORDS = {"packing list", "invoice", "purchase order", "shipment", "delivery note"}
_SUMMARY_KEYWORDS = {"total", "grand total", "net weight total", "summary"}
_ITEM_KEYWORDS = {"roll no", "lot no", "piece", "metres", "mtr", "qty", "net wt", "shade"}


def _classify_page(text: str, has_tables: bool) -> str:
    lower = text.lower()

    # Summary pages tend to appear at the end and carry totals
    if any(kw in lower for kw in _SUMMARY_KEYWORDS) and "total" in lower:
        if not has_tables or len(lower) < 800:
            return "summary"

    # Header pages: short + contain PO / invoice headers
    if any(kw in lower for kw in _HEADER_KEYWORDS) and len(lower) < 1_500:
        return "header"

    # Item pages: contain roll-level or lot-level table headers
    if any(kw in lower for kw in _ITEM_KEYWORDS) and has_tables:
        return "item_table"

    # Default to item_table if tables are present
    if has_tables:
        return "item_table"

    # Short page with no tables → likely a header
    if len(lower) < 800:
        return "header"

    return "item_table"


# ---------------------------------------------------------------------------
# Single-page processor
# ---------------------------------------------------------------------------

def _process_page(page: pdfplumber.page.Page) -> PageResult:
    try:
        raw_text: str = page.extract_text() or ""
        tables_raw = page.extract_tables() or []

        # Normalise table cells: strip whitespace, coerce None to ""
        tables: list[list[list[str | None]]] = []
        for tbl in tables_raw:
            normalised = [
                [cell.strip() if isinstance(cell, str) else cell for cell in row]
                for row in tbl
                if row
            ]
            tables.append(normalised)

        needs_ocr = len(raw_text.strip()) < 20  # almost no text → scanned

        if needs_ocr:
            return PageResult(
                page_number=page.page_number,
                page_type="scanned",
                raw_text="",
                tables=[],
                needs_ocr=True,
            )

        page_type = _classify_page(raw_text, bool(tables))
        return PageResult(
            page_number=page.page_number,
            page_type=page_type,
            raw_text=raw_text,
            tables=tables,
            needs_ocr=False,
        )

    except Exception as exc:
        logger.error("Page %d processing error: %s", page.page_number, exc, exc_info=True)
        return PageResult(
            page_number=page.page_number,
            page_type="scanned",
            raw_text="",
            tables=[],
            needs_ocr=True,
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_pdf(pdf_bytes: bytes, filename: str = "upload.pdf") -> ParsedDocument:
    """
    Extract text and tables from a PDF byte stream.
    Pages are processed in parallel. Scanned pages are flagged for OCR.
    """
    result = ParsedDocument()

    try:
        import io
        pdf_stream = io.BytesIO(pdf_bytes)

        with pdfplumber.open(pdf_stream) as pdf:
            result.total_pages = len(pdf.pages)

            with ThreadPoolExecutor(max_workers=MAX_PDF_WORKERS) as executor:
                future_to_page = {
                    executor.submit(_process_page, page): page.page_number
                    for page in pdf.pages
                }
                for future in as_completed(future_to_page):
                    page_result = future.result()
                    result.pages.append(page_result)
                    if page_result.needs_ocr:
                        result.has_scanned_pages = True

            # Ensure pages are in order
            result.pages.sort(key=lambda p: p.page_number)

    except Exception as exc:
        logger.error("PDF parse failed for %s: %s", filename, exc, exc_info=True)
        # Return an empty result rather than raising — caller must handle gracefully

    return result
