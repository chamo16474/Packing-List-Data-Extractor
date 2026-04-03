"""
models.py — All Pydantic models for the Packing List Extraction Backend.
Schema is FIXED — never modify the 9 canonical fields.
"""

from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Canonical 9-field schema (+ metadata)
# ---------------------------------------------------------------------------

class PackingLineItem(BaseModel):
    """Represents a single extracted roll or piece on the packing list."""
    lot: str | None = None
    po_number: str | None = None          # Per-roll PO (AML docs have multiple POs)
    piece_number: str | None = None
    meters: float | None = None
    net_weight: float | None = None
    color: str | None = None
    quality: str | None = None
    # Additional fields requested for Book2.xlsx format
    length_yds: float | None = None
    points_per_roll: int | float | None = None
    points_per_100m2: float | None = None
    weight_gross_kgs: float | None = None

    model_config = {"extra": "ignore"}

class RawPageText(BaseModel):
    page: int
    text: str

class PackingListRecord(BaseModel):
    """The single canonical output record per processed packing list."""

    # ── 9 canonical fields ─────────────────────────────────────────────────
    lot: str | None = None             # Lot / batch number
    pieces: int | None = None          # Number of rolls / pieces
    meters: float | None = None        # Total quantity in metres
    po_number: str | None = None       # Purchase order number
    net_weight: float | None = None    # Net weight in KG
    order_number: str | None = None    # Internal order / delivery note number
    invoice_number: str | None = None  # Invoice or D/A number
    delivered_date: str | None = None  # Delivery date ISO format YYYY-MM-DD
    quality: str | None = None         # Fabric quality / article description
    color: str | None = None           # Shade / colour name or code

    # ── Metadata (not shown to user) ────────────────────────────────────────
    supplier_name: str = Field(default="unknown")
    source_file: str = Field(default="")
    extraction_confidence: dict[str, float] = Field(default_factory=dict)
    weight_granularity: str = Field(default="document_level")         # "per_roll" | "document_level"
    mapping_source: str = Field(default="regex")                      # "template" | "ai" | "regex"
    flagged_fields: list[str] = Field(default_factory=list)
    doc_type: str = Field(default="unknown")                          # "roll_level" | "lot_level" | "hybrid" | "unknown"
    line_items: list[PackingLineItem] = Field(default_factory=list)
    raw_candidates: dict[str, list[Any]] = Field(default_factory=dict)  # used for /mapping/candidates
    raw_text: list[RawPageText] = Field(default_factory=list)          # list of {page, text} 

    model_config = {"extra": "ignore"}

    @model_validator(mode="after")
    def build_flagged_fields(self) -> "PackingListRecord":
        from config import CONFIDENCE_THRESHOLD
        self.flagged_fields = [
            field
            for field, conf in self.extraction_confidence.items()
            if conf < CONFIDENCE_THRESHOLD
        ]
        return self


# ---------------------------------------------------------------------------
# Request / Response models for API endpoints
# ---------------------------------------------------------------------------

class ExtractedField(BaseModel):
    value: Any | None = None
    confidence: float = 0.0
    mapping_source: str = "regex"
    source_page: int | None = None
    source_text: str | None = None


class UploadResponse(BaseModel):
    job_id: str
    status: str = "done"
    fields: dict[str, ExtractedField] = Field(default_factory=dict)
    flagged_fields: list[str] = Field(default_factory=list)
    raw_text: list[RawPageText] = Field(default_factory=list)
    line_items: list[Any] = Field(default_factory=list)  # per-roll data


class MappingAction(str, Enum):
    confirm = "confirm"
    reassign = "reassign"
    not_present = "not_present"


class MappingConfirmRequest(BaseModel):
    job_id: str
    field_name: str
    confirmed_value: Any | None
    action: MappingAction


class MappingConfirmResponse(BaseModel):
    job_id: str
    field_name: str
    updated_value: Any | None
    flagged_fields: list[str]
    validation_errors: list[str] = Field(default_factory=list)


class CandidatesResponse(BaseModel):
    job_id: str
    field_name: str
    candidates: list[Any]


class SupplierListResponse(BaseModel):
    suppliers: list[str]


class ErrorResponse(BaseModel):
    detail: str
    field: str | None = None
