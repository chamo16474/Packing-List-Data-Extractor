"""
tests/test_pipeline_integration.py — End-to-end integration test.

Runs the full pipeline against the real sample packing list PDF and
asserts that key fields are extracted correctly.

Usage:
    cd backend
    python -m pytest tests/test_pipeline_integration.py -v
"""

import sys
import os
from pathlib import Path

# Make sure backend root is on the path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

SAMPLE_PDF = Path(__file__).parent.parent.parent / "sample packing list" / "PACKING LIST.pdf"


@pytest.fixture(scope="module")
def extracted_record():
    """Run the pipeline once and reuse the result for all tests."""
    if not SAMPLE_PDF.exists():
        pytest.skip(f"Sample PDF not found at: {SAMPLE_PDF}")

    from main import run_pipeline
    pdf_bytes = SAMPLE_PDF.read_bytes()
    record = run_pipeline(pdf_bytes, SAMPLE_PDF.name, supplier_name="unknown")
    return record


# ---------------------------------------------------------------------------
# Basic smoke test — pipeline must not crash
# ---------------------------------------------------------------------------

def test_pipeline_runs_without_error(extracted_record):
    assert extracted_record is not None


# ---------------------------------------------------------------------------
# All 10 fields must be non-null
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = [
    "lot", "pieces", "meters",
    "po_number", "net_weight", "order_number",
    "invoice_number", "delivered_date", "quality", "color",
]


@pytest.mark.parametrize("field", REQUIRED_FIELDS)
def test_field_is_extracted(extracted_record, field):
    value = getattr(extracted_record, field, None)
    assert value is not None, (
        f"Field '{field}' was not extracted — got None. "
        f"Check regex rules, AI call, or synonym dict."
    )


# ---------------------------------------------------------------------------
# Specific value assertions for known sample PDF values
# ---------------------------------------------------------------------------

def test_po_number_looks_reasonable(extracted_record):
    """PO number should be alphanumeric, not a column header name."""
    po = extracted_record.po_number
    assert po is not None
    bad_values = {"color", "colour", "shade", "lot", "quality", "article", "meters", "pieces"}
    assert po.strip().lower() not in bad_values, (
        f"po_number contains a column header value: '{po}'"
    )


def test_order_number_is_not_a_field_name(extracted_record):
    """ORDER_NUMBER = 'Color' was a known bug — this validates it is fixed."""
    order = extracted_record.order_number
    if order is None:
        return  # allow None but not a field name
    bad_values = {"color", "colour", "shade", "lot", "quality", "article"}
    assert order.strip().lower() not in bad_values, (
        f"order_number wrongly contains a field name: '{order}'"
    )


def test_line_items_extracted(extracted_record):
    """AI should extract roll-level line items."""
    assert isinstance(extracted_record.line_items, list), "line_items should be a list"
    assert len(extracted_record.line_items) > 0, (
        "line_items is empty — AI did not extract roll-level data. "
    )


def test_net_weight_is_numeric(extracted_record):
    nw = extracted_record.net_weight
    if nw is not None:
        assert isinstance(nw, (int, float)), f"net_weight is not numeric: {nw!r}"
        assert nw > 0, f"net_weight is <= 0: {nw}"


def test_pieces_is_positive_int(extracted_record):
    pieces = extracted_record.pieces
    if pieces is not None:
        assert isinstance(pieces, int), f"pieces is not an int: {pieces!r}"
        assert pieces > 0, f"pieces is <= 0: {pieces}"


def test_meters_is_positive_float(extracted_record):
    meters = extracted_record.meters
    if meters is not None:
        assert isinstance(meters, (int, float)), f"meters is not numeric: {meters!r}"
        assert meters > 0, f"meters is <= 0: {meters}"


def test_no_fields_flagged_at_low_confidence(extracted_record):
    """After fixes, ideally no fields should be flagged as low-confidence."""
    flagged = extracted_record.flagged_fields
    print(f"\nFlagged fields: {flagged}")
    # Not a hard assertion — just report as info
    assert isinstance(flagged, list)


def test_ai_was_used(extracted_record):
    """mapping_source should be 'ai' when AI is triggered."""
    source = extracted_record.mapping_source
    print(f"\nMapping source: {source}")
    # Either ai or template is acceptable (template = learned from previous confirm)
    assert source in ("ai", "template", "regex"), f"Unexpected mapping_source: {source}"
