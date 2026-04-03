"""
extractor/regex_rules.py — Fast regex extraction for known structured fields.
Runs BEFORE any Gemini call. Returns value + page number + confidence per field.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Patterns — ordered from most-specific to most-generic per field
# ---------------------------------------------------------------------------

REGEX_RULES: dict[str, list[str]] = {
    "po_number": [
        r"(?:PO|Contract\s*No|Your\s*Order|PO\s*No|Customer\s*PO|Client\s*PO)[:\s#]+([A-Z0-9\-\/]{3,30})",
        r"(?:Customer\s*PO\s*No|Buyer\s*PO)[:\s#]+([A-Z0-9\-]+)",
    ],
    "invoice_number": [
        r"(?:Invoice\s*No|D\/A\s*No|Packing\s*List\s*No|Commercial\s*Invoice\s*No)[:\s]+([A-Z0-9\.\-\/]{3,30})",
        r"(?:Inv\.?\s*No|PL\s*No)[:\s]+([A-Z0-9\.\-\/]{3,30})",
        r"(?:Invoice\s*Ref|Document\s*No)[:\s]+([A-Z0-9\-\/]{3,20})",
    ],
    "delivered_date": [
        r"(\d{2}[-\/]\w{3,}[-\/]\d{2,4})",      # 01-Jan-2024 or 01/January/24
        r"(\d{2}[\/\.]\d{2}[\/\.]\d{4})",        # 01/02/2024 or 01.02.2024
        r"(\d{4}-\d{2}-\d{2})",                   # ISO 2024-01-02
        r"Date[:\s]+(\d{2}[-\/]\w{3,}[-\/]\d{2,4})",  # "Date: 28-NOV-25"
    ],
    "net_weight": [
        r"Net\s*Weight[:\s]+([,\d\.]+)",
        r"Nett\s*Weight[:\s]+([,\d\.]+)",
        r"NW\s*\(KG\)[:\s]+([,\d\.]+)",
        r"N\s*Wt\.\s*\(KGS?\)[:\s]+([,\d\.]+)",
        r"Total\s*Net\s*(?:Weight|Wt\.?)[:\s]+([,\d\.]+)",
        r"N\s*Wt\.\s*\(Kgs?\)[:\s]+([,\d\.]+)",
    ],
    "order_number": [
        r"(?:Order\s*No|Order\s*Number)[:\s#]+([A-Z0-9\/\-]{3,20})",
        r"(?:Delivery\s*N[oº]|Delivery\s*No|Delivery\s*Note\s*No|DN\s*No)[:\s#]+([A-Z0-9\/\-]{3,20})",
        r"(?:S\.?O\.?\s*No|Sales\s*Order\s*No)[:\s#]+([A-Z0-9\-]+)",
        r"(?:Shipment\s*No|Dispatch\s*Order)[:\s#]+([A-Z0-9\-]+)",
    ],
    # --- Enhanced patterns for better LOT extraction ---
    "lot": [
        r"(?:Lot\s*No\.?|Batch\s*No\.?|LOT\s*NO\.?|Lot\s*Number)[:\s]+([A-Z0-9\-\/\.]+)",
        r"(?:^|\s)(?:Lot|Batch)\s*[:\s]+([A-Z0-9\-\/\.]{2,20})",
        r"Lot\s+([A-Z][A-Z0-9\-\.]*)",  # "Lot A0", "Lot A123"
        r"Batch\s+([A-Z][A-Z0-9\-\.]*)",  # "Batch X123"
        r"BATCH\/LOT[:\s]+([A-Z0-9\-\/\.]+)",
        r"Lot\/Batch[:\s]+([A-Z0-9\-\/\.]+)",
    ],
    "quality": [
        r"(?:Quality|Article|Fabric\s*(?:Code|Description|Quality))[:\s]+([^\n\r]{3,80})",
        r"(?:Construction|Composition|Your\s*product)[:\s]+([^\n\r]{3,80})",
        r"(?:Material|Style|Fabric)[:\s]+([^\n\r]{3,80})",
        r"(?:Description|Item\s*Description)[:\s]+([^\n\r]{3,80})",
    ],
    "color": [
        r"(?:Colour|Color|Shade)[:\s]+([^\n\r\|]{3,50})",
        r"Shade\s*(?:Name|Code|No\.?)[:\s]+([^\n\r\|]{3,40})",
        r"Color\s*\/\s*Shade[:\s]+([^\n\r]{3,40})",
    ],
    "pieces": [
        r"Total\s*(?:No\.?\s*of\s*)?(?:Rolls?|Pieces?|Pcs?|QTY)[:\s]+(\d+)",
        r"(?:Grand\s*Total|Total)[:\s\|]+(\d+)\s*(?:Rolls?|Pcs?|Pieces?)",
        r"No\.\s*of\s*(?:Rolls?|Pieces?|Pcs?)[:\s]+(\d+)",
        r"Quantity\s*\(?(?:Rolls?|Pcs?)?\)?[:\s]+(\d+)",
    ],
    "meters": [
        r"Total\s*(?:Metres?|Meters?|MTR|Mtrs?)[:\s]+([,\d\.]+)",
        r"(?:Grand\s*Total|Total)[:\s\|]+([,\d\.]+)\s*(?:Metres?|Meters?|MTR|Mtrs?|M\b)",
        r"Qty\s*\(?(?:MTR|Mtrs?|Meters?)?\)?[:\s]+([,\d\.]+)",
        r"Length\s*\(?(?:M|Mtr)?\)?[:\s]+([,\d\.]+)",
    ],
}

SUPPLIER_REGEX_RULES: dict[str, dict[str, list[str]]] = {
    "techs": {
        "quality": [r"(?:Article)[:\s]+([\w\-\s]+)"],
        "color": [r"(?:Color|Colour)[:\s]+([\w\-\s]+)"],
        "lot": [r"(?:Lot\s*No)[:\s]+([\w\-]+)"],
    },
    "guston": {
        "po_number": [r"(?:Client\s*PO)[:\s]+([\w\-]+)"],
        "quality": [r"(?:Style)[:\s]+([\w\-\s]+)"],
    }
}


# ---------------------------------------------------------------------------
# Date normalisation  (crude but reliable for common formats)
# ---------------------------------------------------------------------------

_MONTH_MAP = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "may": "05", "jun": "06", "jul": "07", "aug": "08",
    "sep": "09", "oct": "10", "nov": "11", "dec": "12",
}


def _normalise_date(raw: str) -> str:
    """Try to convert a matched date string to YYYY-MM-DD.  Returns raw string unchanged if parsing fails."""
    raw = raw.strip()

    # Already ISO
    if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
        return raw

    # DD/MM/YYYY or DD.MM.YYYY
    m = re.match(r"^(\d{2})[\/\.](\d{2})[\/\.](\d{4})$", raw)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"

    # DD-Mon-YYYY  (e.g. 15-Jan-2024)
    m = re.match(r"^(\d{2})[-\/]([A-Za-z]{3,})[-\/](\d{2,4})$", raw)
    if m:
        d, mon_raw, y = m.group(1), m.group(2).lower()[:3], m.group(3)
        year = f"20{y}" if len(y) == 2 else y
        month = _MONTH_MAP.get(mon_raw, "00")
        return f"{year}-{month}-{d}"

    return raw


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class RegexMatch:
    value: str
    page_number: int
    confidence: float       # 0.90 for regex hits (high but not perfect)
    raw_match: str          # original regex capture before normalisation


# ---------------------------------------------------------------------------
# Core extraction function
# ---------------------------------------------------------------------------

def _extract_field(field: str, patterns: list[str], text: str, page_number: int) -> Optional[RegexMatch]:
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if m:
            raw = m.group(1).strip().rstrip(",").strip()
            value = _normalise_date(raw) if field == "delivered_date" else raw
            if value:
                return RegexMatch(
                    value=value,
                    page_number=page_number,
                    confidence=0.90,
                    raw_match=raw,
                )
    return None


def run_regex_extraction(pages_text: list[tuple[int, str]], supplier_name: str = "unknown") -> dict[str, RegexMatch]:
    """
    Run all regex patterns against each page's text.
    Returns a dict of field_name → best RegexMatch (first non-empty match wins).
    pages_text: list of (page_number, raw_text) tuples.
    """
    results: dict[str, RegexMatch] = {}

    supplier_rules = SUPPLIER_REGEX_RULES.get(supplier_name.lower(), {})
    
    # Merge rules: supplier-specific rules get priority (placed first in the list)
    merged_rules: dict[str, list[str]] = {}
    all_fields = set(REGEX_RULES.keys()).union(set(supplier_rules.keys()))
    
    for field in all_fields:
        merged_rules[field] = supplier_rules.get(field, []) + REGEX_RULES.get(field, [])

    for field_name, patterns in merged_rules.items():
        for page_number, text in pages_text:
            match = _extract_field(field_name, patterns, text, page_number)
            if match:
                logger.debug("Regex hit: field=%s value=%r page=%d", field_name, match.value, page_number)
                results[field_name] = match
                break   # First page that matches wins — usually the header page

    found = set(results.keys())
    missing = set(REGEX_RULES.keys()) - found
    logger.info("Regex extraction: found=%s  missing=%s", sorted(found), sorted(missing))
    return results


def all_regex_fields_found(results: dict[str, RegexMatch]) -> bool:
    """True if all 10 canonical fields were found with confidence >= 0.85.
    Used to decide whether to skip the Gemini call. Returns False if any field is missing.
    """
    required = set(REGEX_RULES.keys())
    return required.issubset(results.keys())
