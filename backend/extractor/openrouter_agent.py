"""
extractor/openrouter_agent.py — AI extraction using OpenRouter API.

FLAW D FIX:
  The system prompt is now loaded directly from PACKING_LIST_SKILL.md.
  This file is the authoritative, maintained extraction specification and
  should not be duplicated here.  The skill file is sent as the `system`
  role message; the document text is sent as the `user` role message.

  The skill file returns a `rolls[]` array with 10 fields per roll.
  _normalize_skill_response() translates that into the legacy internal
  format so the rest of the pipeline (canonical_mapper, models) is unchanged.

MODEL UPGRADE:
  Primary:  google/gemini-2.0-flash  (full Flash, not the weakest Lite)
  Fallback: google/gemini-2.5-pro    (if primary returns empty/invalid JSON)

  Both are available on OpenRouter.  The fallback is only invoked when the
  primary model fails to return parseable JSON — this covers Flaw I (single-model).
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections import deque
from pathlib import Path
from typing import Any, Optional

import requests

from config import (
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    OPENROUTER_MAX_TOKENS,
    OPENROUTER_TEMPERATURE,
    OPENROUTER_TIMEOUT_SECONDS,
    OPENROUTER_REQUESTS_PER_MINUTE,
    OPENROUTER_REQUESTS_PER_DAY,
)

logger = logging.getLogger("openrouter_agent")

# ---------------------------------------------------------------------------
# Model configuration — primary + fallback (fixes Flaw H and Flaw I)
# ---------------------------------------------------------------------------

_PRIMARY_MODEL  = "google/gemini-2.0-flash-001"
_FALLBACK_MODEL = "meta-llama/llama-3.3-70b-instruct"

# ---------------------------------------------------------------------------
# Skill file loader — Flaw D fix
# ---------------------------------------------------------------------------

_SKILL_CACHE: Optional[str] = None


def _load_skill() -> str:
    """
    Load PACKING_LIST_SKILL.md from the project root.
    Cached after first read.  Returns a fallback minimal prompt if file
    is missing so the system degrades gracefully.
    """
    global _SKILL_CACHE
    if _SKILL_CACHE is not None:
        return _SKILL_CACHE

    # Walk up from this file's location to find the project root
    # Layout: backend/extractor/openrouter_agent.py → project root is ../..
    candidates = [
        Path(__file__).parent.parent.parent / "PACKING_LIST_SKILL.md",
        Path(__file__).parent.parent / "PACKING_LIST_SKILL.md",
        Path(os.getcwd()) / "PACKING_LIST_SKILL.md",
    ]
    for path in candidates:
        if path.is_file():
            try:
                _SKILL_CACHE = path.read_text(encoding="utf-8")
                logger.info("Loaded PACKING_LIST_SKILL.md from %s (%d chars)", path, len(_SKILL_CACHE))
                return _SKILL_CACHE
            except Exception as exc:
                logger.error("Failed to read skill file at %s: %s", path, exc)

    # Graceful fallback — minimal instructions if skill file is missing
    logger.warning(
        "PACKING_LIST_SKILL.md not found in any expected location. "
        "Using minimal fallback prompt.  Extraction quality will be reduced."
    )
    _SKILL_CACHE = (
        "You are a textile packing list data extractor. "
        "Extract roll-level data and return ONLY valid JSON with a 'rolls' array. "
        "Each roll must have: lot_no, po_number, shade, roll_no, length_mts, "
        "length_yds, weight_gross_kgs, weight_nett_kgs. "
        "Also include supplier_code, exporter_name, packing_list_no, "
        "packing_list_date, net_weight_kg, total_length_mtr, product_description. "
        "Return ONLY JSON. No explanation."
    )
    return _SKILL_CACHE


# ---------------------------------------------------------------------------
# Rate Limiter
# ---------------------------------------------------------------------------

class RateLimiter:
    """Rate limiter for OpenRouter API calls."""

    def __init__(self, requests_per_minute: int, requests_per_day: int):
        self.rpm_limit = requests_per_minute
        self.rpd_limit = requests_per_day
        self.requests_minute: deque = deque()
        self.requests_day: deque = deque()

    def can_proceed(self) -> tuple[bool, str]:
        now = time.time()
        while self.requests_minute and self.requests_minute[0] < now - 60:
            self.requests_minute.popleft()
        while self.requests_day and self.requests_day[0] < now - 86400:
            self.requests_day.popleft()
        if len(self.requests_day) >= self.rpd_limit:
            oldest = self.requests_day[0] if self.requests_day else now
            return False, f"Daily limit reached. Try again in {int(oldest + 86400 - now) + 1}s."
        if len(self.requests_minute) >= self.rpm_limit:
            oldest = self.requests_minute[0] if self.requests_minute else now
            return False, f"Minute limit reached. Try again in {int(oldest + 60 - now) + 1}s."
        return True, "OK"

    def record_request(self):
        now = time.time()
        self.requests_minute.append(now)
        self.requests_day.append(now)

    def get_status(self) -> dict:
        return {
            "requests_last_minute": len(self.requests_minute),
            "requests_last_day":    len(self.requests_day),
            "rpm_limit":            self.rpm_limit,
            "rpd_limit":            self.rpd_limit,
        }


_rate_limiter = RateLimiter(OPENROUTER_REQUESTS_PER_MINUTE, OPENROUTER_REQUESTS_PER_DAY)


# ---------------------------------------------------------------------------
# JSON parsing
# ---------------------------------------------------------------------------

def _parse_json_response(text: str) -> Optional[dict[str, Any]]:
    """Parse JSON response, stripping any markdown code fences."""
    text = text.strip()

    # Strip markdown code fences (```json ... ``` or ``` ... ```)
    if text.startswith("```"):
        lines = text.splitlines()
        start = 1
        end = len(lines)
        if lines[-1].strip() in ("```", "```json"):
            end = -1
        text = "\n".join(lines[start:end]).strip()

    def _deserialize_clean(raw: str) -> Optional[dict[str, Any]]:
        try:
            data = json.loads(raw)
            if isinstance(data, list) and data:
                for item in data:
                    if isinstance(item, dict):
                        return item
                return None
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None

    # Try clean parsing first
    parsed = _deserialize_clean(text)
    if parsed is not None:
        return parsed

    logger.warning("JSON parsing initially failed. Output may be truncated — attempting JSON repair")
    # Find the last complete roll object and close the JSON properly
    last_brace = text.rfind("}")
    if last_brace != -1:
        repaired_text = text[: last_brace + 1]
        open_brackets = repaired_text.count("[") - repaired_text.count("]")
        open_braces   = repaired_text.count("{") - repaired_text.count("}")
        repaired_text += "]" * max(0, open_brackets) + "}" * max(0, open_braces)
        logger.warning("Repaired JSON: closed %d brackets, %d braces", open_brackets, open_braces)
        
        parsed_repaired = _deserialize_clean(repaired_text)
        if parsed_repaired is not None:
            return parsed_repaired

    logger.error("JSON parsing absolutely failed after repair | first 500 chars: %s", text[:500])
    return None


# ---------------------------------------------------------------------------
# Skill-response normalisation — Flaw D bridge layer
# ---------------------------------------------------------------------------

def _normalize_skill_response(parsed: dict[str, Any]) -> dict[str, Any]:
    """
    The PACKING_LIST_SKILL.md prompt returns a richer schema:
      {
        supplier_code, exporter_name, packing_list_no, packing_list_date,
        net_weight_kg, total_length_mtr, product_description,
        rolls: [ {lot_no, po_number, shade, roll_no, length_mts, ...} ]
      }

    This function maps that into the legacy internal format that
    canonical_mapper.py, models.py and the rest of the pipeline expect:
      {
        lot: {value, confidence},  pieces: ...,  meters: ...,
        po_number: ..., net_weight: ..., invoice_number: ...,
        delivered_date: ..., quality: ..., color: ...,
        line_items: [ {piece_number, meters, net_weight, lot, color, quality} ]
      }

    We also preserve the richer `rolls` array as `_rolls_raw` so callers
    that want the full detail can access it without losing data.
    """
    out: dict[str, Any] = {}

    def _wrap(value: Any, conf: float = 0.9) -> dict:
        return {"value": value, "confidence": conf}

    rolls = parsed.get("rolls", [])

    # ── Header fields ──────────────────────────────────────────────────────
    out["invoice_number"] = _wrap(parsed.get("packing_list_no"))
    out["delivered_date"] = _wrap(parsed.get("packing_list_date"))
    out["net_weight"]     = _wrap(parsed.get("net_weight_kg"))
    out["meters"]         = _wrap(parsed.get("total_length_mtr"))
    out["quality"]        = _wrap(parsed.get("product_description"))
    out["order_number"]   = _wrap(None, 0.0)   # not in skill schema

    # ── PO number: prefer section-level from rolls, fall back to None ──────
    po_values = list({r.get("po_number") for r in rolls if r.get("po_number")})
    if len(po_values) == 1:
        out["po_number"] = _wrap(po_values[0])
    elif len(po_values) > 1:
        out["po_number"] = _wrap(po_values[0], 0.7)  # ambiguous — low confidence
    else:
        out["po_number"] = _wrap(None, 0.0)

    # ── Count and aggregate from rolls ────────────────────────────────────
    out["pieces"] = _wrap(len(rolls) if rolls else None, 0.95)

    # Lot: if all rolls share the same lot, surface it; otherwise "MIXED"
    lot_values = list({r.get("lot_no") for r in rolls if r.get("lot_no")})
    if len(lot_values) == 1:
        out["lot"] = _wrap(lot_values[0])
    elif len(lot_values) > 1:
        out["lot"] = _wrap("MIXED (" + ", ".join(sorted(lot_values)) + ")", 0.9)
    else:
        out["lot"] = _wrap(None, 0.0)

    # Color / shade: aggregate from rolls
    shade_values = list({r.get("shade") for r in rolls if r.get("shade")})
    if len(shade_values) == 1:
        out["color"] = _wrap(shade_values[0])
    elif len(shade_values) > 1:
        out["color"] = _wrap("MIXED (" + ", ".join(sorted(shade_values)) + ")", 0.9)
    else:
        out["color"] = _wrap(None, 0.0)

    # ── Roll → line_items translation ─────────────────────────────────────
    line_items = []
    for roll in rolls:
        line_items.append({
            "lot":          roll.get("lot_no"),
            "po_number":    roll.get("po_number"),          # per-roll PO (AML multi-PO docs)
            "piece_number": roll.get("roll_no"),
            "meters":       roll.get("length_mts"),
            "net_weight":   roll.get("weight_nett_kgs"),
            "color":        roll.get("shade"),
            "quality":      None,   # not per-roll in skill schema
            "length_yds":   roll.get("length_yds"),
            "points_per_roll": roll.get("points_per_roll"),
            "points_per_100m2": roll.get("points_per_100m2"),
            "weight_gross_kgs": roll.get("weight_gross_kgs"),
        })
    out["line_items"] = line_items

    # ── Preserve raw rolls for any caller wanting the full detail ──────────
    out["_rolls_raw"] = rolls
    out["_supplier_code"] = parsed.get("supplier_code")
    out["_exporter_name"] = parsed.get("exporter_name")
    out["_extraction_notes"] = parsed.get("extraction_notes", [])

    return out


# ---------------------------------------------------------------------------
# Core API call — single model
# ---------------------------------------------------------------------------

def _call_model(
    model: str,
    system_prompt: str,
    user_message: str,
) -> Optional[dict[str, Any]]:
    """
    Make one OpenRouter chat completion call.
    Returns parsed dict on success, None on any failure.
    """
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "X-Title": "Packing List Extractor",
    }
    payload = {
        "model": model,
        "temperature": OPENROUTER_TEMPERATURE,
        "max_tokens": OPENROUTER_MAX_TOKENS,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_message},
        ],
    }

    start = time.monotonic()
    try:
        response = requests.post(
            f"{OPENROUTER_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=OPENROUTER_TIMEOUT_SECONDS,
        )
    except requests.exceptions.Timeout:
        logger.error("OpenRouter timeout after %ds (model=%s)", OPENROUTER_TIMEOUT_SECONDS, model)
        return None
    except requests.exceptions.RequestException as exc:
        logger.error("OpenRouter request error (model=%s): %s", model, exc)
        return None

    elapsed = time.monotonic() - start

    if response.status_code != 200:
        logger.error(
            "OpenRouter HTTP %d (model=%s): %s",
            response.status_code, model, response.text[:300],
        )
        return None

    response_data = response.json()
    choices = response_data.get("choices") or []
    if not choices:
        logger.error("OpenRouter returned empty choices (model=%s)", model)
        return None

    raw_text = choices[0]["message"]["content"]
    logger.info("OpenRouter response in %.2fs (model=%s, chars=%d)", elapsed, model, len(raw_text))
    logger.debug("Raw response: %s", raw_text[:800])

    return _parse_json_response(raw_text)


# ---------------------------------------------------------------------------
# Text chunker — splits large documents so each chunk fits in 8192 output tokens
# ---------------------------------------------------------------------------

# gemini-2.0-flash can output 8192 tokens ≈ ~55 rolls per call
# Each roll JSON block ≈ ~140 output tokens
# To completely eliminate LLM laziness (skipping rows), we limit to ~10-12 rolls per chunk.
_CHARS_PER_CHUNK = 3_000    # Extremely safe input chunk size, forces AI to process micro-sections
_HEADER_SNIPPET_LEN = 1000  # Number of characters to copy from page 1 into all chunks so it knows the columns

def _split_into_chunks(text: str) -> list[str]:
    """
    Split document text into chunks.
    Crucial fix: We extract the "document header" (first 1500 chars) and PREPEND it
    to chunks 2..N. This guarantees the AI knows which column is meters vs weight!
    """
    if len(text) <= _CHARS_PER_CHUNK:
        return [text]

    # Grab the top of the document (which usually defines the column layout)
    header_context = text[:_HEADER_SNIPPET_LEN]
    
    chunks: list[str] = []
    lines = text.splitlines(keepends=True)
    current: list[str] = []
    current_len = 0

    # Natural split markers
    split_markers = [
        lambda ln: ln.strip().startswith("PO #"),
        lambda ln: ln.strip().startswith("Page "),
        lambda ln: ln.strip() == "",
    ]

    for line in lines:
        is_split_point = any(fn(line) for fn in split_markers)
        # Forced hard split if a table has no natural gaps for > 10k chars
        force_split = current_len + len(line) > int(_CHARS_PER_CHUNK * 1.5)

        if current_len + len(line) > _CHARS_PER_CHUNK and current and (is_split_point or force_split):
            chunk_str = "".join(current)
            if len(chunks) > 0:
                # Prepend the header context to subsequent chunks
                chunk_str = f"--- [DOCUMENT HEADER FOR CONTEXT] ---\n{header_context}\n--- [CONTINUED ROWS] ---\n{chunk_str}"
            chunks.append(chunk_str)
            current = []
            current_len = 0

        current.append(line)
        current_len += len(line)

    if current:
        chunk_str = "".join(current)
        if len(chunks) > 0:
            chunk_str = f"--- [DOCUMENT HEADER FOR CONTEXT] ---\n{header_context}\n--- [CONTINUED ROWS] ---\n{chunk_str}"
        chunks.append(chunk_str)

    logger.info("Document split into %d chunks (%d total chars). Header preserved.", len(chunks), len(text))
    return chunks


def _call_single_chunk(
    system_prompt: str,
    supplier_name: str,
    doc_type: str,
    chunk_text: str,
    chunk_index: int,
    is_first_chunk: bool,
) -> Optional[dict[str, Any]]:
    """Call AI for one chunk. Returns parsed dict or None."""
    if is_first_chunk:
        instruction = (
            "Extract ALL data from this packing list: "
            "header fields (exporter, packing_list_no, date, net_weight_kg, "
            "total_length_mtr, product_description) AND every roll row.\n"
            "CRITICAL: Extract EVERY SINGLE ROW in the text. Do NOT skip any rows. Do not use '...'.\n"
            "Return the full JSON object as defined in the skill."
        )
    else:
        instruction = (
            "This is a CONTINUATION of the same packing list document. "
            "A [DOCUMENT HEADER FOR CONTEXT] block is included so you know what the columns mean, "
            "but your job is to extract ONLY the rolls listed under [CONTINUED ROWS].\n"
            "CRITICAL: Extract EVERY SINGLE ROW in the [CONTINUED ROWS]. Do NOT skip any rows. Do not use '...'.\n"
            "Return a JSON object with ONLY a 'rolls' array — no document-level header fields needed. "
            "Example: {\"rolls\": [{...}, {...}]}"
        )

    user_message = (
        f"Supplier hint: {supplier_name}\n"
        f"Document layout type: {doc_type}\n"
        f"Chunk {chunk_index + 1} instructions: {instruction}\n\n"
        "Return ONLY the JSON. No explanation.\n\n"
        f"DOCUMENT TEXT:\n{chunk_text}"
    )

    # Try primary model first, then fallback
    for model in (_PRIMARY_MODEL, _FALLBACK_MODEL):
        parsed = _call_model(model, system_prompt, user_message)
        if parsed is not None:
            logger.info("Chunk %d extracted with model=%s, rolls=%d",
                        chunk_index + 1, model, len(parsed.get("rolls", [])))
            return parsed
        logger.warning("Chunk %d failed on model=%s, trying next...", chunk_index + 1, model)

    logger.error("Chunk %d: both models failed.", chunk_index + 1)
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def call_openrouter(pdf_text: str, doc_type: str, supplier_name: str) -> dict[str, Any]:
    """
    Extract packing list data using the PACKING_LIST_SKILL.md as system prompt.

    Strategy:
      1. Load skill file as system prompt
      2. Split document into chunks (max ~40 rolls each) to stay within 8192 output token limit
      3. First chunk extracts header + rolls; subsequent chunks extract rolls only
      4. Merge all rolls from all chunks into a single result
      5. Normalise to legacy internal format

    Returns extracted fields dict (legacy format) or {} on all failures.
    """
    if not OPENROUTER_API_KEY or OPENROUTER_API_KEY == "your-openrouter-api-key-here":
        logger.warning("OPENROUTER_API_KEY not configured.")
        return {}

    allowed, reason = _rate_limiter.can_proceed()
    if not allowed:
        logger.warning("OpenRouter rate limited: %s", reason)
        return {}

    system_prompt = _load_skill()
    chunks = _split_into_chunks(pdf_text)

    logger.info(
        "OpenRouter | supplier=%s | doc_type=%s | text_len=%d | chunks=%d | %s",
        supplier_name, doc_type, len(pdf_text), len(chunks), _rate_limiter.get_status(),
    )

    # ── Process each chunk ────────────────────────────────────────────────
    header_parsed: Optional[dict[str, Any]] = None
    all_rolls: list[dict[str, Any]] = []

    for idx, chunk in enumerate(chunks):
        is_first = (idx == 0)

        parsed = _call_single_chunk(
            system_prompt=system_prompt,
            supplier_name=supplier_name,
            doc_type=doc_type,
            chunk_text=chunk,
            chunk_index=idx,
            is_first_chunk=is_first,
        )

        if parsed is None:
            continue

        rolls = parsed.get("rolls", [])
        all_rolls.extend(rolls)

        if is_first:
            header_parsed = parsed  # keep for header fields

        _rate_limiter.record_request()

    # ── Merge: attach all rolls to the header parsed object ─────────────
    if header_parsed is None:
        logger.error("All chunks failed — returning empty result.")
        return {}

    header_parsed["rolls"] = all_rolls
    logger.info(
        "Extraction complete: %d total rolls across %d chunk(s)",
        len(all_rolls), len(chunks),
    )

    # ── Normalise to legacy internal format ───────────────────────────────
    return _normalize_skill_response(header_parsed)


def get_available_models() -> list[str]:
    """Return list of free models available on OpenRouter."""
    if not OPENROUTER_API_KEY:
        return []
    try:
        resp = requests.get(
            f"{OPENROUTER_BASE_URL}/models",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
            timeout=30,
        )
        if resp.status_code == 200:
            models = resp.json().get("data", [])
            return [m["id"] for m in models if m.get("pricing", {}).get("prompt", "1") == "0"]
    except Exception as exc:
        logger.error("Failed to fetch OpenRouter models: %s", exc)
    return []

