"""Pragmatic helpers for ISO 1101 (geometric tolerancing guidance).

This module provides small utilities to propose nominal geometric tolerances
for common symbols (position, perpendicularity, parallelism, flatness).
The returned values are pragmatic recommendations (in mm) intended for
automated guidance, not as a legal interpretation of the standard.
"""
from __future__ import annotations

from typing import Dict

from .helpers import choose_process_entry


GEOMETRIC_BASE_FACTORS = {
    "position": 0.005,  # fraction of feature size
    "perpendicularity": 0.0025,
    "parallelism": 0.0025,
    "flatness": 0.0015,
    "concentricity": 0.004,
}


def propose_geometric_tolerance(
    symbol: str, feature_size_mm: float, process: str, process_db: Dict | None = None
) -> Dict[str, float]:
    """Propose a geometric tolerance in mm for a given symbol.

    symbol: one of keys in GEOMETRIC_BASE_FACTORS (case-insensitive). The
    algorithm scales a base factor by the feature size and adjusts using
    process capability.
    """
    sym = symbol.lower()
    base = GEOMETRIC_BASE_FACTORS.get(sym)
    if base is None:
        raise ValueError(f"Unsupported geometric symbol: {symbol}")
    entry = choose_process_entry(process, process_db)
    it_raw = entry.get("typical_it_grade", "IT8")
    # typical_it_grade may be stored as "IT8" (str) or 8 (int)
    if isinstance(it_raw, str):
        it = int(it_raw.upper().lstrip("IT") or 8)
    else:
        it = int(it_raw)
    # heuristic: better IT grades -> tighter geometric tolerances
    it_modifier = max(0.5, 12.0 / max(1.0, float(it)))
    tolerance_mm = feature_size_mm * base * it_modifier
    return {"symbol": symbol, "tolerance_mm": tolerance_mm}
