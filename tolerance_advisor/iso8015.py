"""Small helpers inspired by ISO 8015 (fundamental rules for dimensioning and tolerancing).

ISO 8015 contains general rules (principle of independence, etc.). This
module encodes a few pragmatic checks and helpers used by the project's
automation: a simple independence principle applier and some checks for
dimensioning sanity.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Tuple


def apply_independence_principle(base_tolerance_mm: float, modifiers: Iterable[float] | None = None) -> float:
    """Combine a base tolerance with multiplicative modifiers using the
    independence principle: modifiers do not automatically tighten a base
    tolerance unless explicitly stated. We therefore return the maximum of
    the base and any modifier-derived values.

    This is a pragmatic interpretation to help automation choose conservative
    values.
    """
    if modifiers is None:
        return base_tolerance_mm
    values = [base_tolerance_mm]
    for m in modifiers:
        values.append(base_tolerance_mm * float(m))
    return max(values)


def simple_dimensioning_checks(dimensions: Iterable[Tuple[str, float, float]]) -> List[str]:
    """Run a few quick sanity checks over a set of dimensions.

    dimensions: iterable of tuples (name, nominal_mm, tolerance_mm)
    Returns a list of human-readable warnings (empty if all good).
    """
    warnings: List[str] = []
    for name, nominal, tol in dimensions:
        if nominal <= 0:
            warnings.append(f"Dimension '{name}' nominal <= 0: {nominal}")
        if tol <= 0:
            warnings.append(f"Dimension '{name}' tolerance <= 0: {tol}")
        if tol > nominal:
            warnings.append(f"Dimension '{name}' tolerance > nominal: {tol} > {nominal}")
    return warnings
