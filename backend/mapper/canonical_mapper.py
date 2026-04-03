"""
mapper/canonical_mapper.py — Merges regex + AI results into the canonical schema.

Pipeline:
  1. Build candidate lists from regex hits
  2. Build candidate lists from AI hits
  3. Build candidate lists from table column scanning (synonym dict)
  4. Resolve conflicts (highest confidence wins)
  5. Set weight_granularity from doc_type
  6. Return a fully populated PackingListRecord
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yaml

from mapper.conflict_resolver import Candidate, resolve_all
from mapper.confidence_scorer import build_confidence_dict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Load synonym dictionary once at module import
# ---------------------------------------------------------------------------

_SYNONYM_PATH = Path(__file__).parent / "synonym_dict.yaml"
_SYNONYM_DICT: dict[str, list[str]] = {}


def _load_synonyms() -> dict[str, list[str]]:
    """Load synonym_dict.yaml and build a normalised lookup."""
    global _SYNONYM_DICT
    if _SYNONYM_DICT:
        return _SYNONYM_DICT
    try:
        with open(_SYNONYM_PATH, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        # Normalise alias strings to lowercase for matching
        _SYNONYM_DICT = {
            canonical: [alias.lower() for alias in aliases]
            for canonical, aliases in data.items()
        }
        logger.info("Loaded synonym dict: %d canonical fields.", len(_SYNONYM_DICT))
    except Exception as exc:
        logger.error("Failed to load synonym_dict.yaml: %s", exc)
        _SYNONYM_DICT = {}
    return _SYNONYM_DICT


# ---------------------------------------------------------------------------
# Canonical field list
# ---------------------------------------------------------------------------

CANONICAL_FIELDS = [
    "lot", "pieces", "meters", "po_number", "net_weight",
    "order_number", "invoice_number", "delivered_date", "quality", "color",
]


# ---------------------------------------------------------------------------
# Table column scanner — finds canonical field values from table rows
# ---------------------------------------------------------------------------

# All known field synonym values (flattened) — used to detect if a table "value"
# is actually just a column label being echoed in the data rows
_ALL_KNOWN_ALIASES: set[str] = set()


def _get_all_aliases() -> set[str]:
    global _ALL_KNOWN_ALIASES
    if not _ALL_KNOWN_ALIASES:
        synonyms = _load_synonyms()
        for aliases in synonyms.values():
            _ALL_KNOWN_ALIASES.update(aliases)
        # Also add canonical field names themselves
        _ALL_KNOWN_ALIASES.update(f.replace("_", " ") for f in CANONICAL_FIELDS)
    return _ALL_KNOWN_ALIASES


def _is_pure_header_text(val: str) -> bool:
    """
    Return True if val is ONLY a column header (not actual data).
    A value like "Color" or "Shade" alone is a header.
    A value like "NAVY BLUE" or "Blend" is actual data.
    """
    val_lower = val.lower().strip()
    # If it's exactly a header alias, it's likely a header
    return val_lower in _get_all_aliases()


def _find_header_row(table: list[list[str | None]], synonyms: dict[str, list[str]]) -> tuple[int, dict[int, str]]:
    """
    Find the best header row in the table and return (row_index, col_to_field mapping).
    Tries the first 3 rows as candidates.
    """
    best_row_idx = -1
    best_mapping: dict[int, str] = {}

    for row_idx in range(min(3, len(table))):
        row = table[row_idx]
        headers = [str(h).strip().lower() if h else "" for h in row]
        mapping: dict[int, str] = {}

        for col_idx, header in enumerate(headers):
            if not header:
                continue
            for canonical, aliases in synonyms.items():
                # Direct match to canonical field name (e.g., "po_number" vs "po number")
                if header == canonical.replace("_", " "):
                    mapping[col_idx] = canonical
                    break
                # Exact match against synonym aliases
                if header in aliases:
                    mapping[col_idx] = canonical
                    break
                
                # Check for significant substring matches (e.g. "Lot No" contains "lot")
                # but avoid extremely short or ambiguous matches
                match_found = False
                for alias in aliases:
                    if len(alias) > 3 and alias in header:
                        mapping[col_idx] = canonical
                        match_found = True
                        break
                    # Special cases for very common short keywords
                    if alias in ("lot", "mtr", "pcs", "po") and (
                        header.startswith(alias + " ") or 
                        header.endswith(" " + alias) or
                        header.startswith(alias + ".") or
                        header == alias
                    ):
                        mapping[col_idx] = canonical
                        match_found = True
                        break
                if match_found:
                    break

        if len(mapping) > len(best_mapping):
            best_mapping = mapping
            best_row_idx = row_idx

    return best_row_idx, best_mapping


def _scan_tables_for_fields(
    tables: list[list[list[str | None]]],
    full_text: str = "",
) -> dict[str, list[Candidate]]:
    """
    Look at each table's header row and try to match column names
    to canonical fields via the synonym dictionary.
    If a match is found, collect all non-empty, non-header values from that column.
    
    Also scans full text for patterns that are hard to extract from tables.
    """
    synonyms = _load_synonyms()
    candidates: dict[str, list[Candidate]] = {f: [] for f in CANONICAL_FIELDS}

    for table in tables:
        if not table or len(table) < 2:
            continue

        header_row_idx, col_to_field = _find_header_row(table, synonyms)

        if not col_to_field:
            continue

        # Collect data rows (everything after the header row)
        for row in table[header_row_idx + 1:]:
            for col_idx, canonical in col_to_field.items():
                if col_idx < len(row) and row[col_idx]:
                    val = str(row[col_idx]).strip()
                    # Skip empty values
                    if not val:
                        continue
                    # Skip if it's purely a header text (e.g., "Color" as a value is wrong)
                    if _is_pure_header_text(val):
                        continue
                    # Skip numeric-looking values for non-numeric fields
                    if canonical in ("lot", "order_number", "invoice_number", "po_number"):
                        # These should have some letters or special chars, not just numbers
                        if val.isdigit() and len(val) < 4:
                            continue
                    candidates[canonical].append(
                        Candidate(value=val, confidence=0.88, source="table_col")
                    )

    # ── Additional text-based extraction for hard-to-find fields ──────────
    # These patterns help when table extraction fails
    
    # LOT: Look for "Lot X" or "Lot: X" patterns in full text
    if full_text:
        lot_patterns = [
            r'Lot\s+([A-Z][A-Z0-9\-\.]*)',  # "Lot A0", "Lot A123"
            r'Lot\s*[:\.]?\s*([A-Z][A-Z0-9\-\.]+)',  # "Lot: A0", "Lot. A123"
            r'Batch\s+([A-Z][A-Z0-9\-\.]*)',  # "Batch X123"
            r'Batch\s*[:\.]?\s*([A-Z][A-Z0-9\-\.]+)',  # "Batch: X123"
        ]
        for pattern in lot_patterns:
            matches = re.findall(pattern, full_text, re.IGNORECASE)
            for match in matches:
                val = match.strip()
                # Filter out common false positives
                if val.lower() not in ('no', 'number', 'num', 'no.', 'batch', 'lot'):
                    candidates["lot"].append(
                        Candidate(value=val, confidence=0.85, source="text_pattern")
                    )
                    break  # One match is enough
        
        # PIECES: Count roll/piece mentions if not found in tables
        piece_patterns = [
            r'Roll\s+(?:No\.?\s*)?(\d+)',
            r'Piece\s+(?:No\.?\s*)?(\d+)',
        ]
        all_pieces = []
        for pattern in piece_patterns:
            matches = re.findall(pattern, full_text, re.IGNORECASE)
            all_pieces.extend(matches)
        if all_pieces and not candidates["pieces"]:
            # Use the highest piece number as total count
            try:
                max_piece = max(int(p) for p in all_pieces)
                candidates["pieces"].append(
                    Candidate(value=str(max_piece), confidence=0.80, source="text_pattern")
                )
            except ValueError:
                pass
        
        # METERS: Look for total meters patterns
        meter_patterns = [
            r'Total\s+(?:Metres?|Meters?|MTR)[:\s]+([,\d\.]+)',
            r'([,\d\.]+)\s*(?:Metres?|Meters?|MTR)\s*\(?(?:Total)?\)?',
        ]
        for pattern in meter_patterns:
            matches = re.findall(pattern, full_text, re.IGNORECASE)
            for match in matches:
                val = match.strip().replace(',', '')
                try:
                    if float(val) > 0:
                        candidates["meters"].append(
                            Candidate(value=val, confidence=0.82, source="text_pattern")
                        )
                        break
                except ValueError:
                    pass

    return candidates


def _coerce_value(field: str, raw: Any) -> Any:
    """Coerce extracted string values to the correct Python type."""
    if raw is None:
        return None
    try:
        if field == "pieces":
            # Remove commas, spaces, decimal parts — accept strings and numbers
            cleaned = re.sub(r"[,\s]", "", str(raw))
            return int(float(cleaned))
        if field in ("meters", "net_weight"):
            cleaned = re.sub(r"[,\s]", "", str(raw))
            return float(cleaned)
    except (ValueError, TypeError):
        logger.warning("Could not coerce field '%s' value %r — keeping as string.", field, raw)
    return raw


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def map_to_canonical(
    regex_results: dict,           # field_name → RegexMatch (from regex_rules)
    ai_results: dict,              # field_name → {"value": ..., "confidence": float}
    all_tables: list,              # all PageResult.tables from the document
    doc_type: str,
    supplier_name: str,
    source_file: str,
    template_data: dict | None = None,  # pre-loaded template from ChromaDB
    full_text: str = "",            # full document text for pattern matching
) -> "PackingListRecord":          # noqa: F821 — forward ref resolved at runtime
    from models import PackingListRecord, PackingLineItem

    # ── Build all_candidates per field ────────────────────────────────────
    all_candidates: dict[str, list[Candidate]] = {f: [] for f in CANONICAL_FIELDS}

    # 1. Template (highest priority)
    mapping_source = "regex"
    if template_data:
        mapping_source = "template"
        for field in CANONICAL_FIELDS:
            val = template_data.get(field)
            if val is not None:
                all_candidates[field].append(
                    Candidate(value=val, confidence=0.95, source="template")
                )

    # 2. Regex hits
    for field, match in regex_results.items():
        if field in all_candidates:
            all_candidates[field].append(
                Candidate(
                    value=match.value,
                    confidence=match.confidence,
                    source="regex",
                    page_number=match.page_number,
                )
            )
            if mapping_source == "regex":
                pass  # already correct

    # 3. AI hits
    ai_confidences: dict[str, float] = {}
    if ai_results:
        if mapping_source not in ("template",):
            mapping_source = "ai"
        for field in CANONICAL_FIELDS:
            entry = ai_results.get(field)
            if isinstance(entry, dict):
                val = entry.get("value")
                conf = float(entry.get("confidence", 0.75))
                ai_confidences[field] = conf
                if val is not None:
                    all_candidates[field].append(
                        Candidate(value=val, confidence=conf, source="ai")
                    )

    # 4. Table column scan (with full text for fallback patterns)
    table_candidates = _scan_tables_for_fields(all_tables, full_text)
    for field, cands in table_candidates.items():
        all_candidates[field].extend(cands)

    # ── Resolve conflicts ────────────────────────────────────────────────
    field_values, field_sources, field_confs = resolve_all(all_candidates)

    # ── Coerce types ────────────────────────────────────────────────────
    for field in CANONICAL_FIELDS:
        field_values[field] = _coerce_value(field, field_values.get(field))

    # ── Aggregation / Fallback Logic ────────────────────────────────────
    # Step 5: Automatically sum line items if summary is missing or 0
    line_items_data = ai_results.get("line_items", []) if isinstance(ai_results, dict) else []
    
    if line_items_data:
        # Sum meters if missing or near-zero
        if not field_values.get("meters") or float(field_values.get("meters")) < 0.01:
            total_m = sum(float(_coerce_value("meters", i.get("meters")) or 0) for i in line_items_data)
            if total_m > 0:
                field_values["meters"] = total_m
                field_confs["meters"] = 0.85
                field_sources["meters"] = "aggregated"

        # Count pieces if missing or near-zero
        if not field_values.get("pieces") or int(field_values.get("pieces")) == 0:
            total_p = len(line_items_data)
            if total_p > 0:
                field_values["pieces"] = total_p
                field_confs["pieces"] = 0.85
                field_sources["pieces"] = "aggregated"

        # Check for multiple Lots/Colors/Qualities for "Mixed" status
        unique_lots = {str(i.get("lot")) for i in line_items_data if i.get("lot")}
        if len(unique_lots) > 1 and field_values.get("lot") not in unique_lots:
            field_values["lot"] = "MIXED (" + ", ".join(sorted(unique_lots)) + ")"
            field_confs["lot"] = 0.9
            field_sources["lot"] = "aggregated"
        elif len(unique_lots) == 1 and not field_values.get("lot"):
            field_values["lot"] = list(unique_lots)[0]
            field_confs["lot"] = 0.85
            field_sources["lot"] = "fallback_from_lines"

        unique_colors = {str(i.get("color")) for i in line_items_data if i.get("color")}
        if len(unique_colors) > 1 and field_values.get("color") not in unique_colors:
            field_values["color"] = "MIXED (" + ", ".join(sorted(unique_colors)) + ")"
            field_confs["color"] = 0.9
            field_sources["color"] = "aggregated"
        elif len(unique_colors) == 1 and not field_values.get("color"):
            field_values["color"] = list(unique_colors)[0]
            field_confs["color"] = 0.85
            field_sources["color"] = "fallback_from_lines"

        unique_qualities = {str(i.get("quality")) for i in line_items_data if i.get("quality")}
        if len(unique_qualities) > 1 and field_values.get("quality") not in unique_qualities:
            field_values["quality"] = "MIXED (" + ", ".join(sorted(unique_qualities)) + ")"
            field_confs["quality"] = 0.9
            field_sources["quality"] = "aggregated"
        elif len(unique_qualities) == 1 and not field_values.get("quality"):
            field_values["quality"] = list(unique_qualities)[0]
            field_confs["quality"] = 0.85
            field_sources["quality"] = "fallback_from_lines"

    # ── Confidence dict ─────────────────────────────────────────────────
    confidence = build_confidence_dict(field_values, field_sources, ai_confidences)

    # ── weight_granularity ───────────────────────────────────────────────
    weight_granularity = "per_roll" if doc_type == "roll_level" else "document_level"

    # ── Raw candidates for /mapping/candidates endpoint ──────────────────
    raw_candidates: dict[str, list[Any]] = {}
    for field, cands in all_candidates.items():
        raw_candidates[field] = [c.value for c in cands if c.value is not None]

    # ── Map line items directly from AI if present ───────────────────
    line_items = []
    if ai_results and isinstance(ai_results.get("line_items"), list):
        for item in ai_results["line_items"]:
            try:
                line_items.append(
                    PackingLineItem(
                        lot=item.get("lot"),
                        po_number=item.get("po_number"),   # per-roll PO for multi-PO docs
                        piece_number=item.get("piece_number"),
                        meters=_coerce_value("meters", item.get("meters")),
                        net_weight=_coerce_value("net_weight", item.get("net_weight")),
                        color=item.get("color"),
                        quality=item.get("quality"),
                        length_yds=_coerce_value("meters", item.get("length_yds")),
                        points_per_roll=item.get("points_per_roll"),
                        points_per_100m2=_coerce_value("meters", item.get("points_per_100m2")),
                        weight_gross_kgs=_coerce_value("net_weight", item.get("weight_gross_kgs")),
                    )
                )
            except Exception as e:
                logger.warning("Failed to parse line item %s: %s", item, e)
    logger.info("Canonical mapper: mapped %d line items from AI results", len(line_items))

    return PackingListRecord(
        lot=field_values.get("lot"),
        pieces=field_values.get("pieces"),
        meters=field_values.get("meters"),
        po_number=field_values.get("po_number"),
        net_weight=field_values.get("net_weight"),
        order_number=field_values.get("order_number"),
        invoice_number=field_values.get("invoice_number"),
        delivered_date=field_values.get("delivered_date"),
        quality=field_values.get("quality"),
        color=field_values.get("color"),
        supplier_name=supplier_name,
        source_file=source_file,
        extraction_confidence=confidence,
        weight_granularity=weight_granularity,
        mapping_source=mapping_source,
        doc_type=doc_type,
        raw_candidates=raw_candidates,
        line_items=line_items,
    )
