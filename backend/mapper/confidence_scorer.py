"""
mapper/confidence_scorer.py — Per-field confidence scoring.

Sources:
  • regex_hit  → 0.90 (high — deterministic pattern match)
  • gemini_hit → as returned by Gemini response (0.0–1.0)
  • template   → 0.95 (highest — known supplier, proven mapping)
  • table_col  → 0.88 (column-header match via synonym dict)
  • default    → 0.0  (field not found by any method)
"""

from __future__ import annotations

from typing import Any


SOURCE_CONFIDENCE: dict[str, float] = {
    "template": 0.95,
    "regex":    0.90,
    "table_col": 0.88,
    "ai":       0.75,   # fallback if Gemini doesn't return per-field confidence
    "none":     0.00,
}


def score_field(
    value: Any,
    source: str,
    ai_confidence: float | None = None,
) -> float:
    """
    Return confidence score for a single field.
    
    Args:
        value:          The extracted value (None → 0.0 always)
        source:         One of "template" | "regex" | "table_col" | "ai" | "none"
        ai_confidence:  Per-field confidence returned by Gemini (0.0–1.0)
    """
    if value is None:
        return 0.0

    if source == "ai" and ai_confidence is not None:
        # Clamp to [0.0, 1.0]
        return max(0.0, min(1.0, float(ai_confidence)))

    return SOURCE_CONFIDENCE.get(source, 0.0)


def build_confidence_dict(
    field_values: dict[str, Any],
    field_sources: dict[str, str],
    ai_confidences: dict[str, float] | None = None,
) -> dict[str, float]:
    """
    Build a per-field confidence dict for all 9 canonical fields.
    
    Args:
        field_values:    {field_name: value}
        field_sources:   {field_name: source}  — source is "regex"|"ai"|"template"|"table_col"
        ai_confidences:  {field_name: float}   — from Gemini response, optional
    """
    ai_confidences = ai_confidences or {}
    result: dict[str, float] = {}

    for field, value in field_values.items():
        source = field_sources.get(field, "none")
        ai_conf = ai_confidences.get(field)
        result[field] = score_field(value, source, ai_conf)

    return result
