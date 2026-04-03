"""
extractor/chunker.py — Smart document chunker for large PDFs.

FLAW B FIX — Column-Signature Detection replaces keyword heuristic:
  Instead of scanning all text for roll/lot keywords (which fires false positives
  on any document that mentions those words anywhere), we now scan only the
  HEADER ROW of the largest detected table on each page and build a column
  signature — a set of normalised canonical column names found.

  Signature sets (matched via synonym_dict.yaml):
    Roll-level:  {roll_no, length_mts, weight_gross_kgs, weight_nett_kgs}
    Lot-level:   {lot, pieces, meters, net_weight}

  Scoring:
    roll_score ≥ 3  → "roll_level"
    lot_score  ≥ 3  → "lot_level"
    BOTH ≥ 2        → "hybrid"   ← NEW: AI gets all pages, not just key pages
    else            → "unknown"  (fallback — previous behaviour)

  The "hybrid" type signals build_ai_context() to send the full document to AI
  regardless of page count, and the conflict resolver to weight AI even higher
  on table fields.

Page selection strategy (unchanged for non-hybrid docs):
  PDFs ≤ 15 pages → send all text to AI.
  PDFs > 15 pages → send header page + first item page + last summary page.
    The remaining item pages are parsed using regex/table extraction only.
  "hybrid" docs   → always send all pages (the layout complexity needs full context).
"""

from __future__ import annotations

import logging

from extractor.pdf_parser import ParsedDocument, PageResult

from config import MAX_DOCUMENT_CHARS

logger = logging.getLogger(__name__)

_LARGE_DOC_THRESHOLD = 15  # pages

# ---------------------------------------------------------------------------
# Column signature definitions for layout detection (Flaw B fix)
# ---------------------------------------------------------------------------

# Canonical field names that unambiguously signal roll-level data
_ROLL_SIGNATURE: frozenset[str] = frozenset({
    "roll_no", "length_mts", "weight_gross_kgs", "weight_nett_kgs",
})

# Canonical field names that unambiguously signal lot/summary-level data
_LOT_SIGNATURE: frozenset[str] = frozenset({
    "lot", "pieces", "meters", "net_weight",
})

# Synonyms per signature field — mirrors the most critical entries in synonym_dict.yaml
# so classification works even if yaml loading fails.
_ROLL_ALIASES: dict[str, list[str]] = {
    "roll_no": [
        "roll no", "roll number", "roll#", "roll #", "piece no", "pce no",
        "piece number", "fabric no", "ref no", "serial no", "sr. no",
        "item no", "bolt no", "bale no",
    ],
    "length_mts": [
        "length(mts)", "length (mts)", "length(m)", "length (m)",
        "meters", "mtr", "qty(mtr)", "qty mtr", "mtrs", "running meters",
        "rm", "qty (meter)", "quantity (m)", "length in meters",
    ],
    "weight_gross_kgs": [
        "gross wt", "gross weight", "g.wt", "g wt", "gross", "gw",
        "weight (gross kgs)", "weight gross", "gross kgs", "gr wt.(kgs)",
        "gross weight (kg)", "gwt",
    ],
    "weight_nett_kgs": [
        "net wt", "nett wt", "net weight", "n.wt", "n wt", "nett", "nw",
        "weight (nett kgs)", "weight nett", "net kgs", "nett kgs",
        "n wt.(kgs)", "net weight (kg)", "nwt",
    ],
}

_LOT_ALIASES: dict[str, list[str]] = {
    "lot": [
        "lot no", "lot number", "lot#", "lot #", "batch no", "batch",
        "dye lot", "dyeing lot", "dye batch", "shade lot",
        "fbn", "fabric batch no",
    ],
    "pieces": [
        "pieces", "pcs", "rolls", "total rolls", "no. of rolls",
        "no of pieces", "qty (pcs)", "quantity",
    ],
    "meters": [
        "total meters", "total mtr", "grand total meters",
        "sum meters", "meters", "mtr", "qty(mtr)",
    ],
    "net_weight": [
        "net weight", "nett weight", "total net weight",
        "net wt", "nett wt", "n.wt.(kgs)", "nw (kg)",
    ],
}


def _header_to_canonical(header: str, aliases: dict[str, list[str]]) -> str | None:
    """
    Match a single table header cell to a canonical field name.
    Returns the canonical name or None if no match found.
    Matching is case-insensitive substring check.
    """
    h = header.strip().lower().replace("  ", " ")
    for canonical, syns in aliases.items():
        for syn in syns:
            if syn == h or syn in h or h in syn:
                return canonical
    return None


def _score_table_headers(
    table: list[list[str | None]],
) -> tuple[int, int]:
    """
    Examine the first 3 rows of a table (looking for the header row).
    Returns (roll_score, lot_score) — counts of signature columns matched.
    """
    roll_score = 0
    lot_score  = 0
    matched_roll: set[str] = set()
    matched_lot:  set[str] = set()

    for row in table[:3]:
        for cell in row:
            if not cell:
                continue
            canon_roll = _header_to_canonical(str(cell), _ROLL_ALIASES)
            if canon_roll and canon_roll not in matched_roll:
                matched_roll.add(canon_roll)
                roll_score += 1

            canon_lot = _header_to_canonical(str(cell), _LOT_ALIASES)
            if canon_lot and canon_lot not in matched_lot:
                matched_lot.add(canon_lot)
                lot_score += 1

    return roll_score, lot_score


def classify_doc_type(doc: ParsedDocument) -> str:
    """
    Classify the document structure using column-signature detection.

    Returns: "roll_level" | "lot_level" | "hybrid" | "unknown"

    Hybrid = document contains BOTH roll-level columns (e.g. per-roll weight)
    AND lot-level summary columns (e.g. total meters, total pieces) — common in
    Penfabric (per-carton weight only) and multi-section Sapphire documents.
    """
    total_roll_score = 0
    total_lot_score  = 0

    for page in doc.pages:
        for table in (page.tables or []):
            if not table or len(table) < 2:
                continue
            r, l = _score_table_headers(table)
            total_roll_score += r
            total_lot_score  += l

    # Determine doc type from aggregated scores across all pages
    if total_roll_score >= 3 and total_lot_score >= 2:
        doc_type = "hybrid"
    elif total_roll_score >= total_lot_score and total_roll_score >= 3:
        doc_type = "roll_level"
    elif total_lot_score > total_roll_score and total_lot_score >= 3:
        doc_type = "lot_level"
    else:
        # Column detection inconclusive — fall back to fast keyword heuristic
        doc_type = _keyword_fallback(doc)

    logger.info(
        "Document classified as: %s (roll_score=%d, lot_score=%d)",
        doc_type, total_roll_score, total_lot_score,
    )
    return doc_type


def _keyword_fallback(doc: ParsedDocument) -> str:
    """
    Original keyword-counting heuristic used as a last resort when
    column-signature detection is inconclusive (no tables found or very low scores).
    """
    roll_signals = {"roll no", "n wt.(kgs)", "gr wt.(kgs)", "gross wt"}
    lot_signals  = {"lot", "piece", "metres", "tone", "lot no"}

    full_lower = doc.full_text.lower()
    roll_score = sum(1 for s in roll_signals if s in full_lower)
    lot_score  = sum(1 for s in lot_signals  if s in full_lower)

    if roll_score > lot_score:
        return "roll_level"
    elif lot_score > roll_score:
        return "lot_level"
    return "unknown"


# ---------------------------------------------------------------------------
# Page selection
# ---------------------------------------------------------------------------

def select_key_pages(doc: ParsedDocument) -> list[PageResult]:
    """
    For large documents, return only the most information-dense pages.
    Hybrid documents always get ALL pages (layout complexity demands full context).
    """
    # Classify first so we know if this is hybrid
    doc_type = classify_doc_type(doc)

    # Hybrid or small docs → always send all pages
    if doc_type == "hybrid" or doc.total_pages <= _LARGE_DOC_THRESHOLD:
        if doc_type == "hybrid":
            logger.info("Hybrid layout detected — sending all %d pages to AI.", doc.total_pages)
        return doc.pages

    key_pages: list[PageResult] = []

    # All header pages
    key_pages.extend(doc.header_pages)

    # First item table page
    item_pages = doc.item_pages
    if item_pages:
        key_pages.append(item_pages[0])

    # Last summary page (or last page)
    summary_pages = doc.summary_pages
    if summary_pages:
        key_pages.append(summary_pages[-1])
    elif doc.pages:
        last = doc.pages[-1]
        if last not in key_pages:
            key_pages.append(last)

    logger.info(
        "Large doc (%d pages, type=%s): selected %d key pages for AI.",
        doc.total_pages, doc_type, len(key_pages),
    )
    return key_pages


# ---------------------------------------------------------------------------
# Table serialisation
# ---------------------------------------------------------------------------

def _serialize_table(table: list[list[str | None]]) -> str:
    if not table:
        return ""
    lines = []
    max_cols = max((len(r) for r in table if r), default=0)
    for i, row in enumerate(table):
        padded_row = [(str(c).replace("\n", " ").strip() if c is not None else "") for c in row]
        padded_row.extend([""] * (max_cols - len(padded_row)))
        lines.append("| " + " | ".join(padded_row) + " |")
        if i == 0:
            lines.append("|" + "|".join(["---"] * max_cols) + "|")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# AI context builder
# ---------------------------------------------------------------------------

def build_ai_context(doc: ParsedDocument) -> str:
    """
    Produce the text block to send to AI.
    Enforces MAX_DOCUMENT_CHARS limit.
    """
    pages = select_key_pages(doc)
    parts: list[str] = []

    for page in pages:
        if page.raw_text:
            page_content = f"--- Page {page.page_number} ({page.page_type}) ---\n"
            page_content += page.raw_text + "\n"
            if page.tables:
                page_content += "\n--- Extracted Structured Tables ---\n"
                for i, tbl in enumerate(page.tables):
                    page_content += f"\nTable {i+1}:\n" + _serialize_table(tbl) + "\n"
            parts.append(page_content)

    combined = "\n\n".join(parts)

    if len(combined) > MAX_DOCUMENT_CHARS:
        logger.info(
            "Trimming AI context from %d to %d chars.",
            len(combined), MAX_DOCUMENT_CHARS,
        )
        combined = combined[:MAX_DOCUMENT_CHARS]

    return combined
