"""Practical helper for ISO 2768 (general tolerances) - pragmatic implementation.

This module implements a useful approximation for ISO 2768 general
tolerances for linear dimensions. It is intentionally lightweight and
designed to be used as a guidance helper inside the repo's tooling.

DO NOT treat this as a replacement for a standards subscription — it is an
engineering convenience.
"""
from __future__ import annotations

from typing import Dict

from .helpers import find_size_range, choose_process_entry

# Representative multipliers for tolerance classes (pragmatic).
# Values are factors applied to nominal size (result in mm).
CLASS_FACTORS = {
    "f": 0.0005,  # fine
    "m": 0.0010,  # medium
    "c": 0.0020,  # coarse
    "v": 0.0050,  # very coarse
}


def fundamental_tol_iso2768(nominal_mm: float, tol_class: str = "m") -> float:
    """Return a pragmatic ISO 2768 general tolerance in mm.

    tol_class: one of 'f','m','c','v'. If unknown, 'm' is used.
    """
    tol_class = tol_class.lower()
    if tol_class not in CLASS_FACTORS:
        tol_class = "m"
    idx = find_size_range(nominal_mm)
    factor = CLASS_FACTORS[tol_class]
    # Size-range modifier to slightly increase tolerances for large sizes
    range_mod = 1.0 + 0.5 * idx
    return nominal_mm * factor * range_mod


def propose_general_tolerance(nominal_mm: float, process: str, process_db: Dict[str, Dict] | None = None) -> Dict[str, float]:
    """Propose a general tolerance (ISO 2768 style) based on process.

    Returns a dict with chosen tol_class and computed tolerance_mm.
    """
    entry = choose_process_entry(process, process_db)
    # pick a suggested class based on typical IT-like grade in process db
    it_raw = entry.get("typical_it_grade", "IT8")
    # typical_it_grade may be stored as "IT8" (str) or 8 (int)
    if isinstance(it_raw, str):
        it = int(it_raw.upper().lstrip("IT") or 8)
    else:
        it = int(it_raw)
    # heuristic: lower IT -> finer ISO2768 class
    if it <= 6:
        cls = "f"
    elif it <= 8:
        cls = "m"
    elif it <= 11:
        cls = "c"
    else:
        cls = "v"
    tol_mm = fundamental_tol_iso2768(nominal_mm, cls)
    return {"class": cls, "tolerance_mm": tol_mm}
