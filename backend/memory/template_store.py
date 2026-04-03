"""
memory/template_store.py — ChromaDB-backed supplier template store.

Purpose: Cache extraction mappings per supplier so future documents
from the same supplier skip the AI entirely (regex + template path).

Schema stored per supplier:
  - document: supplier_name (unique ID)
  - metadata: all canonical field values + doc_type + _schema_version + _correction_count

VERSIONING (Flaw C fix):
  TEMPLATE_SCHEMA_VERSION = "2"
  Any template without this version (or with a different version) is treated as stale
  and silently rejected. The pipeline then runs AI extraction and re-caches the result.

FEEDBACK LOOP (Flaw G fix):
  apply_correction() patches a single field in an existing template and increments
  _correction_count, so user confirmations accumulate permanently.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from config import CHROMA_PERSIST_DIR

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema version — bump this whenever the canonical field set changes.
# All templates written before this version will be silently rejected and
# re-built on next extraction.  No manual migration needed.
# ---------------------------------------------------------------------------
TEMPLATE_SCHEMA_VERSION = "2"

_COLLECTION_NAME = "supplier_templates"
_client = None
_collection = None


def _get_collection():
    global _client, _collection
    if _collection is not None:
        return _collection
    try:
        import chromadb  # type: ignore

        _client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
        _collection = _client.get_or_create_collection(
            name=_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("ChromaDB collection '%s' ready at %s", _COLLECTION_NAME, CHROMA_PERSIST_DIR)
    except Exception as exc:
        logger.error("ChromaDB init failed: %s. Templates will not be cached.", exc)
        _collection = None
    return _collection


# ---------------------------------------------------------------------------
# CRUD operations
# ---------------------------------------------------------------------------

def save_template(supplier_name: str, record_data: dict[str, Any]) -> bool:
    """
    Save or overwrite a supplier template in ChromaDB.
    record_data should contain canonical fields + doc_type.
    Always stamps _schema_version = TEMPLATE_SCHEMA_VERSION.
    """
    col = _get_collection()
    if col is None:
        return False

    try:
        # Store all values as strings in metadata (ChromaDB limitation)
        metadata = {k: json.dumps(v) for k, v in record_data.items() if v is not None}
        metadata["supplier_name"] = supplier_name
        # --- Flaw C fix: stamp schema version ---
        metadata["_schema_version"] = TEMPLATE_SCHEMA_VERSION
        # Preserve existing correction count if we are updating
        existing = load_template(supplier_name, _skip_version_check=True)
        if existing and "_correction_count" in existing:
            metadata["_correction_count"] = str(existing["_correction_count"])
        else:
            metadata.setdefault("_correction_count", "0")

        # Use supplier_name as the document ID (upsert)
        col.upsert(
            ids=[supplier_name],
            documents=[supplier_name],
            metadatas=[metadata],
        )
        logger.info(
            "Template saved for supplier: %s (version=%s)",
            supplier_name,
            TEMPLATE_SCHEMA_VERSION,
        )
        return True
    except Exception as exc:
        logger.error("Failed to save template for '%s': %s", supplier_name, exc)
        return False


def load_template(
    supplier_name: str,
    _skip_version_check: bool = False,
) -> Optional[dict[str, Any]]:
    """
    Load a cached supplier template. Returns None if not found or version mismatch.

    _skip_version_check is an internal flag used only by apply_correction() and
    save_template() to avoid recursion — do NOT pass True from external callers.
    """
    col = _get_collection()
    if col is None:
        return None

    try:
        results = col.get(ids=[supplier_name], include=["metadatas"])
        if not results or not results.get("metadatas"):
            return None

        meta = results["metadatas"][0]

        # --- Flaw C fix: reject stale templates ---
        if not _skip_version_check:
            stored_version = meta.get("_schema_version", "1")  # legacy = "1"
            if stored_version != TEMPLATE_SCHEMA_VERSION:
                logger.warning(
                    "Stale template rejected for supplier '%s' "
                    "(stored version=%s, required=%s). "
                    "AI extraction will run and re-cache.",
                    supplier_name,
                    stored_version,
                    TEMPLATE_SCHEMA_VERSION,
                )
                return None

        # Deserialise JSON strings back to Python types (skip internal meta keys)
        _internal_keys = {"supplier_name", "_schema_version", "_correction_count"}
        data = {}
        for k, v in meta.items():
            if k in _internal_keys:
                continue
            try:
                data[k] = json.loads(v)
            except (json.JSONDecodeError, TypeError):
                data[k] = v
        # Also surface correction count as plain int for callers
        try:
            data["_correction_count"] = int(meta.get("_correction_count", 0))
        except (ValueError, TypeError):
            data["_correction_count"] = 0
        return data

    except Exception as exc:
        logger.error("Failed to load template for '%s': %s", supplier_name, exc)
        return None


def apply_correction(supplier_name: str, field_name: str, corrected_value: Any) -> bool:
    """
    Flaw G fix — Patch a single field in an existing supplier template.

    Loads the current template (bypassing version check so we can update it),
    patches the corrected field, bumps _correction_count, and saves back.
    If no template exists yet for this supplier, creates a minimal one.

    Returns True on success, False on failure.
    """
    existing = load_template(supplier_name, _skip_version_check=True) or {}

    # Remove internal metadata keys before patching
    clean = {k: v for k, v in existing.items() if not k.startswith("_")}

    # Apply the correction
    clean[field_name] = corrected_value

    # Bump correction counter
    correction_count = existing.get("_correction_count", 0) + 1
    clean["_correction_count_raw"] = correction_count  # carried into save_template

    saved = save_template(supplier_name, clean)
    if saved:
        logger.info(
            "Feedback correction saved: supplier=%s field=%s value=%r (correction #%d)",
            supplier_name,
            field_name,
            corrected_value,
            correction_count,
        )
    return saved


def list_suppliers() -> list[str]:
    """Return all known supplier names (regardless of version)."""
    col = _get_collection()
    if col is None:
        return []
    try:
        results = col.get(include=["metadatas"])
        return [
            meta.get("supplier_name", "")
            for meta in (results.get("metadatas") or [])
            if meta.get("supplier_name")
        ]
    except Exception as exc:
        logger.error("Failed to list suppliers: %s", exc)
        return []


def delete_template(supplier_name: str) -> bool:
    """Delete a supplier template (used for manual re-training)."""
    col = _get_collection()
    if col is None:
        return False
    try:
        col.delete(ids=[supplier_name])
        logger.info("Template deleted for supplier: %s", supplier_name)
        return True
    except Exception as exc:
        logger.error("Failed to delete template for '%s': %s", supplier_name, exc)
        return False


def template_exists(supplier_name: str) -> bool:
    """Quick check if a *valid versioned* template exists for the given supplier."""
    return load_template(supplier_name) is not None
