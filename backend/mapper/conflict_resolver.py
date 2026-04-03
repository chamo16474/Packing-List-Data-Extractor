"""
mapper/conflict_resolver.py — Deduplicate and resolve conflicting values
when the same field has been found by multiple extraction methods or pages.

FLAW E FIX — Field-aware priority:
  Header fields (invoice no, PO, date, etc.): regex is authoritative — it uses
  precise patterns designed for those values. Priority: template > regex > ai > table_col.

  Table fields (lot, meters, pieces, weight, color, quality): AI is authoritative —
  regex cannot reliably parse table rows. Priority: template > ai > table_col > regex.

  This removes the previous incorrect behaviour where a regex "stray number" match
  could silently override the AI's carefully extracted table-level data.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Source priority tables — two separate tables for header vs table fields
# ---------------------------------------------------------------------------

# Fields populated from document *header* text (single, labelled values)
# Regex wins because it uses precise, supplier-specific label patterns.
_HEADER_SOURCE_PRIORITY: dict[str, int] = {
    "template":  4,
    "regex":     3,
    "ai":        2,
    "table_col": 1,
    "none":      0,
}

# Fields populated from the *data table* (multi-row roll/lot tables)
# AI wins because it understands table structure; regex cannot parse tables reliably.
_TABLE_SOURCE_PRIORITY: dict[str, int] = {
    "template":  4,
    "ai":        3,
    "table_col": 2,
    "regex":     1,   # ← regex demoted for table fields
    "none":      0,
}

# Classify every canonical field
_HEADER_FIELDS: frozenset[str] = frozenset({
    "po_number",
    "invoice_number",
    "packing_list_no",
    "packing_list_date",
    "order_number",
    "delivered_date",
    "exporter_name",
    "supplier_code",
})

_TABLE_FIELDS: frozenset[str] = frozenset({
    "lot",
    "lot_no",
    "pieces",
    "meters",
    "net_weight",
    "net_weight_kg",
    "total_length_mtr",
    "color",
    "quality",
    "shade",
    "weight_gross_kgs",
    "weight_nett_kgs",
    "length_mts",
    "length_yds",
    "points_per_roll",
    "points_per_100m2",
})


def _priority_for(field: str, source: str) -> int:
    """
    Return numeric priority for (field, source) pair.
    Table fields use _TABLE_SOURCE_PRIORITY; everything else uses _HEADER_SOURCE_PRIORITY.
    """
    if field in _TABLE_FIELDS:
        return _TABLE_SOURCE_PRIORITY.get(source, 0)
    return _HEADER_SOURCE_PRIORITY.get(source, 0)


# ---------------------------------------------------------------------------
# Candidate dataclass
# ---------------------------------------------------------------------------

@dataclass
class Candidate:
    value: Any
    confidence: float
    source: str
    page_number: int = 0


# ---------------------------------------------------------------------------
# Resolution logic
# ---------------------------------------------------------------------------

def resolve(candidates: list[Candidate], field: str = "") -> "Candidate | None":
    """
    Given multiple candidates for the same field, return the best one.

    Tie-breaking order (highest first):
      1. confidence score
      2. source priority (field-aware — table fields prefer AI, header fields prefer regex)

    Returns None if the list is empty or all values are None.
    """
    if not candidates:
        return None

    # Filter out None values
    valid = [c for c in candidates if c.value is not None]
    if not valid:
        return None

    # Sort: descending confidence, then descending field-aware source priority
    valid.sort(
        key=lambda c: (c.confidence, _priority_for(field, c.source)),
        reverse=True,
    )
    winner = valid[0]
    logger.debug(
        "Resolved field '%s': %r (conf=%.2f, src=%s, priority=%d)",
        field,
        winner.value,
        winner.confidence,
        winner.source,
        _priority_for(field, winner.source),
    )
    return winner


def resolve_all(
    all_candidates: dict[str, list[Candidate]],
) -> tuple[dict[str, Any], dict[str, str], dict[str, float]]:
    """
    Resolve conflicts for all fields.

    Returns:
        field_values  — {field_name: resolved_value}
        field_sources — {field_name: source}
        field_confs   — {field_name: confidence}
    """
    field_values: dict[str, Any] = {}
    field_sources: dict[str, str] = {}
    field_confs: dict[str, float] = {}

    for field, candidates in all_candidates.items():
        winner = resolve(candidates, field=field)  # ← pass field name for aware priority
        if winner:
            field_values[field] = winner.value
            field_sources[field] = winner.source
            field_confs[field] = winner.confidence
        else:
            field_values[field] = None
            field_sources[field] = "none"
            field_confs[field] = 0.0

    return field_values, field_sources, field_confs
