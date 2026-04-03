"""
validator/schema_validator.py — Pydantic-based validation + business rules.

Runs 4 parallel checks:
  1. Pydantic schema validation (type coercion already done in canonical_mapper)
  2. Delivered date must be a valid ISO date
  3. Business rules: meters > 0, pieces > 0
  4. Completeness: all 9 fields must have a value OR explicitly None
"""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from models import PackingListRecord

logger = logging.getLogger(__name__)

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

CANONICAL_FIELDS = [
    "lot", "pieces", "meters", "po_number", "net_weight",
    "order_number", "invoice_number", "delivered_date", "quality", "color",
]


# ---------------------------------------------------------------------------
# Individual check functions
# ---------------------------------------------------------------------------

def _check_pydantic(record: PackingListRecord) -> list[str]:
    """Re-validate the model. Pydantic v2 validates on construction, but we can re-run."""
    errors: list[str] = []
    try:
        record.model_validate(record.model_dump())
    except Exception as exc:
        errors.append(f"Schema validation error: {exc}")
    return errors


def _check_date(record: PackingListRecord) -> list[str]:
    errors: list[str] = []
    date_val = record.delivered_date
    if date_val is not None:
        if not _ISO_DATE_RE.match(str(date_val)):
            errors.append(
                f"delivered_date '{date_val}' is not a valid ISO date (YYYY-MM-DD)."
            )
        else:
            # Validate calendar correctness
            year, month, day = map(int, date_val.split("-"))
            if not (1 <= month <= 12 and 1 <= day <= 31):
                errors.append(f"delivered_date '{date_val}' has invalid month or day.")
    return errors


def _check_business_rules(record: PackingListRecord) -> list[str]:
    """
    Validate business rules: meters > 0, pieces > 0, net_weight >= 0.
    Includes type guards to handle string/float conversion safely.
    """
    errors: list[str] = []
    
    # Safe type coercion with guards for meters
    meters: float | None = None
    if record.meters is not None:
        try:
            if isinstance(record.meters, (int, float)) and not isinstance(record.meters, bool):
                meters = float(record.meters)
            elif isinstance(record.meters, str):
                # Remove commas and whitespace, handle decimal strings
                cleaned = record.meters.replace(',', '').strip()
                if cleaned.replace('.', '', 1).replace('-', '', 1).isdigit():
                    meters = float(cleaned)
        except (ValueError, TypeError, AttributeError):
            meters = None
    
    # Safe type coercion with guards for pieces
    pieces: int | None = None
    if record.pieces is not None:
        try:
            if isinstance(record.pieces, int) and not isinstance(record.pieces, bool):
                pieces = record.pieces
            elif isinstance(record.pieces, (float, str)):
                cleaned = str(record.pieces).replace(',', '').strip()
                if cleaned.isdigit():
                    pieces = int(float(cleaned))
        except (ValueError, TypeError, AttributeError):
            pieces = None
    
    # Safe type coercion with guards for net_weight
    net_weight: float | None = None
    if record.net_weight is not None:
        try:
            if isinstance(record.net_weight, (int, float)) and not isinstance(record.net_weight, bool):
                net_weight = float(record.net_weight)
            elif isinstance(record.net_weight, str):
                cleaned = record.net_weight.replace(',', '').strip()
                if cleaned.replace('.', '', 1).replace('-', '', 1).isdigit():
                    net_weight = float(cleaned)
        except (ValueError, TypeError, AttributeError):
            net_weight = None

    # Apply validation rules
    if meters is not None and meters <= 0:
        errors.append(f"meters must be > 0, got {record.meters}.")
    if pieces is not None and pieces <= 0:
        errors.append(f"pieces must be > 0, got {record.pieces}.")
    if net_weight is not None and net_weight < 0:
        errors.append(f"net_weight cannot be negative, got {record.net_weight}.")
    return errors


def _check_completeness(record: PackingListRecord) -> list[str]:
    """All 9 canonical fields must exist as attributes — None is acceptable."""
    errors: list[str] = []
    record_dict = record.model_dump()
    for field in CANONICAL_FIELDS:
        if field not in record_dict:
            errors.append(f"Field '{field}' is missing from the record entirely.")
    return errors


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate(record: PackingListRecord) -> list[str]:
    """
    Run all 4 checks in parallel and collect all validation errors.
    Returns a list of error messages (empty = valid).
    """
    checks = [
        _check_pydantic,
        _check_date,
        _check_business_rules,
        _check_completeness,
    ]

    all_errors: list[str] = []

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(check, record): check.__name__ for check in checks}
        for future in as_completed(futures):
            check_name = futures[future]
            try:
                errors = future.result()
                if errors:
                    logger.warning("Validation check '%s' found %d error(s).", check_name, len(errors))
                all_errors.extend(errors)
            except Exception as exc:
                logger.error("Validation check '%s' raised: %s", check_name, exc, exc_info=True)

    return all_errors
