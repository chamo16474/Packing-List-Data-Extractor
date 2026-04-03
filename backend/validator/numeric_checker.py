"""
validator/numeric_checker.py — Cross-check numeric totals for data integrity.

Checks:
  • If per-roll weights are available in tables, sum them and compare
    to the stated net_weight total. Tolerance: ±2%.
  • Returns a list of warning strings (not hard errors — human review only).
"""

from __future__ import annotations

import logging

from extractor.pdf_parser import ParsedDocument

logger = logging.getLogger(__name__)

_TOLERANCE = 0.02  # 2% tolerance


def check_weight_totals(
    stated_net_weight: float | None,
    doc: ParsedDocument,
    net_weight_synonyms: list[str] | None = None,
) -> list[str]:
    """
    Attempt to sum per-roll net weights found in tables and compare to stated total.
    Returns a list of warning strings (empty if no discrepancy or if check cannot run).

    Args:
        stated_net_weight:    The net_weight value from the canonical record.
        doc:                  The parsed document (with table data).
        net_weight_synonyms:  Column header aliases to look for (default: built-in list).
    """
    warnings: list[str] = []

    if stated_net_weight is None or stated_net_weight <= 0:
        return warnings

    if net_weight_synonyms is None:
        net_weight_synonyms = [
            "n wt.(kgs)", "net weight", "nett weight", "nw (kg)",
            "net wt", "net wt (kg)", "n.wt.(kgs)", "net wt.(kgs)",
        ]

    row_weights: list[float] = []

    for page in doc.pages:
        for table in page.tables:
            if not table or len(table) < 2:
                continue

            # Find weight column index
            headers = [str(h).strip().lower() if h else "" for h in table[0]]
            weight_col_idx: int | None = None
            for idx, header in enumerate(headers):
                if any(alias in header for alias in net_weight_synonyms):
                    weight_col_idx = idx
                    break

            if weight_col_idx is None:
                continue

            for row in table[1:]:
                if weight_col_idx >= len(row):
                    continue
                cell = row[weight_col_idx]
                if not cell:
                    continue
                try:
                    clean = str(cell).replace(",", "").strip()
                    val = float(clean)
                    if val > 0:
                        row_weights.append(val)
                except (ValueError, TypeError):
                    pass

    if not row_weights:
        logger.debug("Numeric check: no per-roll weights found in tables.")
        return warnings

    summed = sum(row_weights)
    diff_pct = abs(summed - stated_net_weight) / stated_net_weight if stated_net_weight else 0

    logger.info(
        "Numeric check: sum_of_rows=%.2f  stated=%.2f  diff=%.2f%%",
        summed, stated_net_weight, diff_pct * 100
    )

    if diff_pct > _TOLERANCE:
        warnings.append(
            f"Weight mismatch: sum of row weights ({summed:.2f} KG) differs "
            f"from stated net_weight ({stated_net_weight:.2f} KG) by "
            f"{diff_pct * 100:.1f}% (tolerance ±2%)."
        )

    return warnings
