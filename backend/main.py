"""
main.py — FastAPI application for the Packing List Extraction & Summarization backend.

Endpoints:
  POST   /upload                         — Upload PDF, run full extraction pipeline
  GET    /result/{job_id}                — Get full result from session store
  POST   /mapping/confirm                — Confirm / reassign / mark not-present a field
  GET    /mapping/candidates/{job_id}/{field_name} — Top candidates for a field
  POST   /output/excel/{job_id}          — Download the .xlsx file
  GET    /suppliers                      — List all known supplier templates
  DELETE /suppliers/{supplier_name}      — Remove a supplier template

All state is held in memory (session_store.py). No database. No auth.
"""

from __future__ import annotations

import logging
import traceback
import uuid
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

import config  # noqa: F401 — triggers logging setup at import time
from models import (
    CandidatesResponse,
    MappingAction,
    MappingConfirmRequest,
    MappingConfirmResponse,
    PackingListRecord,
    RawPageText,
    SupplierListResponse,
    UploadResponse,
)
from session_store import store
import memory.template_store as template_store

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App & middleware
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Packing List Extraction API",
    description="Extracts and summarises packing list PDFs into a canonical 9-field schema.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # Frontend originates from any origin during dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Extraction pipeline
# ---------------------------------------------------------------------------

def run_pipeline(pdf_bytes: bytes, filename: str, supplier_name: str) -> PackingListRecord:
    """
    Full synchronous extraction pipeline:
    parse → OCR fallback → classify → regex → template cache check →
    Gemini (if needed) → canonical map → validate
    """
    from extractor.pdf_parser import parse_pdf
    from extractor.ocr_fallback import apply_ocr_to_document
    from extractor.regex_rules import run_regex_extraction, all_regex_fields_found
    from extractor.chunker import build_ai_context, classify_doc_type
    from mapper.canonical_mapper import map_to_canonical
    from validator.schema_validator import validate
    from validator.numeric_checker import check_weight_totals

    # ── Step 1: Parse PDF ────────────────────────────────────────────────
    logger.info("Pipeline START | file=%s | supplier=%s", filename, supplier_name)
    doc = parse_pdf(pdf_bytes, filename)

    if not doc.pages:
        logger.error("PDF parsing produced zero pages for %s", filename)
        # Return a zeroed record so the API never crashes
        return PackingListRecord(
            supplier_name=supplier_name,
            source_file=filename,
            extraction_confidence={},
            flagged_fields=list(
                ["lot", "pieces", "meters", "po_number", "net_weight",
                 "order_number", "invoice_number", "delivered_date", "quality", "color"]
            ),
        )

    # ── Step 1b: OCR fallback for scanned pages ──────────────────────────
    if doc.has_scanned_pages:
        apply_ocr_to_document(pdf_bytes, doc.pages)

    # ── Step 2: Document classification ─────────────────────────────────
    doc_type = classify_doc_type(doc)

    # ── Step 3: Regex fast-pass ──────────────────────────────────────────
    pages_text = [(p.page_number, p.raw_text) for p in doc.pages if p.raw_text]
    regex_results = run_regex_extraction(pages_text, supplier_name)

    # ── Step 4: Template cache check ────────────────────────────────────
    template_data: dict | None = None
    if supplier_name and supplier_name.lower() != "unknown":
        template_data = template_store.load_template(supplier_name)
        if template_data:
            logger.info("Template cache HIT for supplier: %s — skipping Gemini.", supplier_name)

    # We trigger AI if we need table-level data (line_items) which regex doesn't handle.
    ai_results: dict[str, Any] = {}

    logger.info("Triggering AI extraction to fetch granular line items.")
    
    # Try OpenRouter (PRIMARY AI provider)
    from extractor.openrouter_agent import call_openrouter
    ai_results = call_openrouter(doc.full_text, doc_type, supplier_name)
    
    if not ai_results:
        logger.warning("OpenRouter extraction failed or returned no results - using regex only")

    # ── Step 6: Collect all tables ───────────────────────────────────────
    all_tables = []
    for page in doc.pages:
        all_tables.extend(page.tables)

    # ── Step 7: Canonical mapping ────────────────────────────────────────
    record = map_to_canonical(
        regex_results=regex_results,
        ai_results=ai_results,  # AI results from OpenRouter
        all_tables=all_tables,
        doc_type=doc_type,
        supplier_name=supplier_name,
        source_file=filename,
        template_data=template_data,
        full_text=doc.full_text,  # Pass full text for pattern matching
    )

    # ── Step 8: Numeric validation ───────────────────────────────────────
    weight_warnings = check_weight_totals(record.net_weight, doc)
    if weight_warnings:
        for w in weight_warnings:
            logger.warning("Numeric check: %s", w)
        # Downgrade net_weight confidence if weight mismatch
        if "net_weight" not in record.flagged_fields:
            record.flagged_fields.append("net_weight")

    # ── Step 9: Schema validation ────────────────────────────────────────
    from validator.schema_validator import validate
    validation_errors = validate(record)
    if validation_errors:
        for err in validation_errors:
            logger.warning("Validation error: %s", err)

    # ── Step 10: Capture raw text for FE preview ─────────────────────────
    raw_text_list = []
    for page in doc.pages:
        raw_text_list.append(RawPageText(page=page.page_number, text=page.raw_text or ""))
    record.raw_text = raw_text_list

    logger.info(
        "Pipeline DONE | supplier=%s | mapping_source=%s | flagged=%s",
        supplier_name,
        record.mapping_source,
        record.flagged_fields,
    )
    return record


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

def _record_to_upload_response(job_id: str, record: PackingListRecord) -> UploadResponse:
    """Transform internal PackingListRecord to the nested format expected by the FE."""
    from mapper.canonical_mapper import CANONICAL_FIELDS
    from models import ExtractedField

    fields_map: dict[str, ExtractedField] = {}
    for field_name in CANONICAL_FIELDS:
        val = getattr(record, field_name)
        conf = record.extraction_confidence.get(field_name, 0.0) * 100 # FE expects 0-100
        fields_map[field_name] = ExtractedField(
            value=val,
            confidence=conf,
            mapping_source=record.mapping_source,
            # source_page/source_text can be added here if session_store tracked them
        )

    return UploadResponse(
        job_id=job_id,
        status="done",
        fields=fields_map,
        flagged_fields=record.flagged_fields,
        raw_text=record.raw_text,
        line_items=[item.model_dump() for item in record.line_items],
    )


def _run_pipeline_background(job_id: str, pdf_bytes: bytes, filename: str, supplier_name: str):
    """Run the extraction pipeline in a background thread with comprehensive error handling."""
    from logger_stream import set_current_job_id, stream_handler
    set_current_job_id(job_id)
    
    try:
        logger.info("Starting background pipeline for job %s | file: %s", job_id, filename)
        record = run_pipeline(pdf_bytes, filename, supplier_name)
        
        # Validate that we got a usable record
        if record is None:
            logger.error("Pipeline returned None for job %s", job_id)
            record = PackingListRecord(
                supplier_name=supplier_name,
                source_file=filename,
                extraction_confidence={},
                flagged_fields=["lot", "pieces", "meters", "po_number", "net_weight", 
                               "order_number", "invoice_number", "delivered_date", "quality", "color"],
                doc_type="unknown",
                mapping_source="error"
            )
        
        # Log extraction summary
        logger.info(
            "Pipeline completed for job %s | supplier=%s | mapping_source=%s | flagged=%d fields",
            job_id,
            supplier_name,
            record.mapping_source,
            len(record.flagged_fields)
        )
        
    except Exception as exc:
        logger.error("Pipeline CRASH for job %s (%s): %s", job_id, filename, traceback.format_exc())
        # Return a zeroed record so the UI can still function
        record = PackingListRecord(
            supplier_name=supplier_name,
            source_file=filename,
            extraction_confidence={f: 0.0 for f in ["lot", "pieces", "meters", "po_number", 
                                                     "net_weight", "order_number", 
                                                     "invoice_number", "delivered_date", 
                                                     "quality", "color"]},
            flagged_fields=["lot", "pieces", "meters", "po_number", "net_weight", 
                           "order_number", "invoice_number", "delivered_date", "quality", "color"],
            doc_type="unknown",
            mapping_source="error",
            line_items=[]
        )
    finally:
        # Always store the result (even if it's an error record)
        store.set(job_id, record)
        stream_handler.end_job(job_id)
        logger.info("Job %s finished - result stored in session", job_id)


@app.post("/upload", response_model=UploadResponse, summary="Upload PDF and extract packing list")
def upload_pdf(
    file: UploadFile = File(..., description="Packing list PDF"),
    supplier_name: str = Form(default="unknown", description="Supplier name (optional)"),
) -> UploadResponse:
    """
    Upload a packing list PDF. Starts background extraction pipeline.
    Returns a `job_id` and status='processing'.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    pdf_bytes = file.file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    job_id = str(uuid.uuid4())
    from logger_stream import stream_handler
    stream_handler.add_job(job_id)

    import threading
    t = threading.Thread(
        target=_run_pipeline_background, 
        args=(job_id, pdf_bytes, file.filename, supplier_name.strip() or "unknown")
    )
    t.start()

    return UploadResponse(
        job_id=job_id,
        status="processing",
        fields={},
        flagged_fields=[],
        raw_text=[]
    )


from fastapi.responses import StreamingResponse
import queue

@app.get("/stream/{job_id}", summary="Stream logs for a job")
def stream_logs(job_id: str):
    from logger_stream import stream_handler
    
    if job_id not in stream_handler.queues:
        raise HTTPException(status_code=404, detail="Job not found")
        
    def event_generator():
        q = stream_handler.queues[job_id]
        while True:
            try:
                msg = q.get(timeout=30)
                if msg == "DONE":
                    yield f"data: DONE\n\n"
                    break
                else:
                    safe_msg = msg.replace('\n', '  ')
                    yield f"data: {safe_msg}\n\n"
            except queue.Empty:
                yield ": keepalive\n\n"
                
    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/result/{job_id}", response_model=UploadResponse, summary="Get extraction result")
def get_result(job_id: str) -> UploadResponse:
    """Return the full result in the nested FE format for a given job_id."""
    record = store.get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return _record_to_upload_response(job_id, record)


@app.post("/mapping/confirm", response_model=MappingConfirmResponse, summary="Confirm or reassign a field")
def confirm_mapping(body: MappingConfirmRequest) -> MappingConfirmResponse:
    """
    Confirm a field, reassign it to a new value, or mark it not present.

    FLAW G FIX — Feedback loop:
      Any confirm or reassign action immediately patches the supplier template
      via apply_correction(), so the correction benefits ALL future documents
      from that supplier — regardless of whether the full template threshold
      (3+ fields) has been reached.

      The full-template save still runs at 3+ confirmed fields as before.
    """
    record = store.get(body.job_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Job '{body.job_id}' not found.")

    # Determine new value
    if body.action == MappingAction.not_present:
        new_value: Any = None
    else:
        new_value = body.confirmed_value

    # Validate field name
    from mapper.canonical_mapper import CANONICAL_FIELDS
    if body.field_name not in CANONICAL_FIELDS:
        raise HTTPException(
            status_code=400,
            detail=f"'{body.field_name}' is not a valid canonical field.",
        )

    # Update in session store
    updated_record = store.update_field(body.job_id, body.field_name, new_value)
    if updated_record is None:
        raise HTTPException(status_code=500, detail="Failed to update record.")

    # Re-validate
    from validator.schema_validator import validate
    validation_errors = validate(updated_record)

    supplier = updated_record.supplier_name
    is_known_supplier = supplier and supplier.lower() != "unknown"

    # ── Flaw G: Immediate per-field correction patch ────────────────────────
    # Applies to both `confirm` and `reassign` actions (not `not_present`).
    # This ensures every user correction is persisted in the template store
    # immediately, even for suppliers where the 3-field threshold hasn't been
    # reached yet.
    if body.action in (MappingAction.confirm, MappingAction.reassign) \
            and new_value is not None \
            and is_known_supplier:
        patched = template_store.apply_correction(supplier, body.field_name, new_value)
        if patched:
            logger.info(
                "Feedback correction saved: supplier=%s field=%s value=%r",
                supplier, body.field_name, new_value,
            )
        else:
            logger.warning(
                "Feedback correction could not be saved for supplier=%s field=%s",
                supplier, body.field_name,
            )

    # ── Full-template save at 3+ confirmed fields (unchanged behaviour) ─────
    if body.action == MappingAction.confirm and is_known_supplier:
        confirmed_count = sum(
            1 for f in CANONICAL_FIELDS
            if getattr(updated_record, f, None) is not None
        )
        if confirmed_count >= 3:
            _save_template_from_record(updated_record)
            logger.info(
                "Full template saved for supplier '%s' (%d/%d fields confirmed)",
                supplier, confirmed_count, len(CANONICAL_FIELDS),
            )

    return MappingConfirmResponse(
        job_id=body.job_id,
        field_name=body.field_name,
        updated_value=new_value,
        flagged_fields=updated_record.flagged_fields,
        validation_errors=validation_errors,
    )


def _save_template_from_record(record: PackingListRecord) -> None:
    """Extract canonical fields from a confirmed record and save as supplier template."""
    from mapper.canonical_mapper import CANONICAL_FIELDS
    template_data = {
        f: getattr(record, f)
        for f in CANONICAL_FIELDS
        if getattr(record, f) is not None
    }
    template_data["doc_type"] = record.doc_type
    template_store.save_template(record.supplier_name, template_data)


@app.get(
    "/mapping/candidates/{job_id}/{field_name}",
    response_model=CandidatesResponse,
    summary="Get top candidate values for a field",
)
def get_candidates(job_id: str, field_name: str) -> CandidatesResponse:
    """
    Return up to 5 candidate values found for a field during extraction.
    Used by the frontend REASSIGN dropdown.
    """
    record = store.get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    candidates = record.raw_candidates.get(field_name, [])
    # Deduplicate, preserve order, return up to 5
    seen: set = set()
    unique: list[Any] = []
    for v in candidates:
        key = str(v)
        if key not in seen:
            seen.add(key)
            unique.append(v)
        if len(unique) >= 5:
            break

    return CandidatesResponse(job_id=job_id, field_name=field_name, candidates=unique)


@app.get(
    "/mapping/all_candidates/{job_id}",
    summary="Get ALL raw candidate values from the extraction (for drag-drop panel)",
)
def get_all_candidates(job_id: str) -> dict:
    """
    Return every raw key→value pair found during extraction, flattened into a list.
    Powers the 'ALL MAPPED FIELDS' right-panel in the frontend.
    Each item: { field: str, value: Any, label: str }
    Unidentified items (not in canonical fields) are also included.
    """
    from mapper.canonical_mapper import CANONICAL_FIELDS

    record = store.get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    items: list[dict] = []
    seen_values: set = set()

    for field_name, candidates in record.raw_candidates.items():
        is_canonical = field_name in CANONICAL_FIELDS
        for val in candidates:
            key = f"{field_name}:{val}"
            if key not in seen_values:
                seen_values.add(key)
                items.append({
                    "field": field_name,
                    "value": str(val) if val is not None else "",
                    "is_canonical": is_canonical,
                    "label": field_name.replace("_", " ").title(),
                })

    # Also add the currently confirmed field values so users can re-drag them
    for field_name in CANONICAL_FIELDS:
        val = getattr(record, field_name)
        if val is not None:
            key = f"confirmed:{field_name}:{val}"
            if key not in seen_values:
                seen_values.add(key)
                items.append({
                    "field": field_name,
                    "value": str(val),
                    "is_canonical": True,
                    "label": field_name.replace("_", " ").title(),
                    "is_confirmed": True,
                })

    return {"job_id": job_id, "items": items, "total": len(items)}


@app.post("/output/excel/{job_id}", summary="Download the Excel (.xlsx) file")
def download_excel(job_id: str) -> Response:
    """
    Generate and return the .xlsx file for a completed job.
    THIS IS THE ONLY OUTPUT FORMAT.
    """
    record = store.get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    try:
        from output.excel_writer import generate_excel
        xlsx_bytes = generate_excel(record, job_id)
    except Exception as exc:
        logger.error("Excel generation error for job %s: %s", job_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Excel generation failed: {exc}")

    filename = f"packing_list_{record.supplier_name}_{job_id[:8]}.xlsx"
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/suppliers", response_model=SupplierListResponse, summary="List all known suppliers")
def list_suppliers() -> SupplierListResponse:
    """Return all supplier names that have a cached template in ChromaDB."""
    suppliers = template_store.list_suppliers()
    return SupplierListResponse(suppliers=suppliers)


@app.delete("/suppliers/{supplier_name}", summary="Delete a supplier template")
def delete_supplier(supplier_name: str) -> dict[str, str]:
    """Remove a supplier's cached template (use when you need to re-train the mapping)."""
    deleted = template_store.delete_template(supplier_name)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Supplier template '{supplier_name}' not found.",
        )
    return {"detail": f"Template for '{supplier_name}' deleted successfully."}


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health", include_in_schema=False)
def health() -> dict[str, str]:
    return {"status": "ok", "version": "1.0.0"}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
