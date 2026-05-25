"""ISO 2768 general tolerances advisor — Part 1 (linear/angular) and Part 2 (geometric).

╔══════════════════════════════════════════════════════════════════════════════╗
║  DESIGN WARNING — SCOPE OF ISO 2768                                          ║
║                                                                              ║
║  ISO 2768 is a background default for NON-CRITICAL, unannotated features.    ║
║  It carries NO functional justification and MUST NOT be the sole tolerance   ║
║  specification for:                                                          ║
║    • bearing bores, sealing surfaces, or precision fits                      ║
║    • safety-critical or load-bearing interfaces                              ║
║    • features controlling assembly location or clearance                     ║
║                                                                              ║
║  These features require explicit tolerances (ISO 286, ISO 1101) backed       ║
║  by functional analysis. Using ISO 2768 alone on critical features is a      ║
║  known source of field failures and supplier non-conformance.                ║
╚══════════════════════════════════════════════════════════════════════════════╝

ISO 2768 eliminates the need to annotate every drawing feature individually by
providing a single title-block entry (e.g. "ISO 2768-mK") that governs all
unannotated dimensions.  Two parts:

  Part 1 (ISO 2768-1) — linear and angular dimensions: classes f, m, c, v
  Part 2 (ISO 2768-2) — geometric form and position:   classes H, K, L

Returned values follow the standard's published tables, not heuristic scaling.
This module is engineering guidance; it is not a substitute for a standards
subscription or for functional tolerance analysis on critical features.

Related standards in the GPS chain:
  ISO 286   — dimensional fits for shafts and bores (use for critical fits)
  ISO 1101  — full geometric tolerancing with datum control (use for critical geometry)
  ISO 4287  — surface roughness (not covered by ISO 2768)
  ISO 13920 — welding tolerances (ISO 2768 does not cover welds)
  ISO 965   — thread tolerances (ISO 2768 does not cover threads)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .helpers import choose_process_entry


# ---------------------------------------------------------------------------
# ISO 2768-1 — Linear tolerance table (±mm)
# Rows: (lower_bound_exclusive, upper_bound_inclusive)  — upper is inclusive
# None means the class is not applicable for that range.
# Source: ISO 2768-1:1989 Table 1.
# ---------------------------------------------------------------------------

# Each entry: (upper_mm_inclusive, f, m, c, v)
# lower bound is previous upper (or 0.5 for the first row).
_LINEAR_TABLE: List[Tuple[float, Optional[float], Optional[float], Optional[float], Optional[float]]] = [
    #  upper   f       m       c       v
    (    3.0,  0.05,   0.10,   0.20,   None),
    (    6.0,  0.05,   0.10,   0.30,   0.50),
    (   30.0,  0.10,   0.20,   0.50,   1.00),
    (  120.0,  0.15,   0.30,   0.80,   1.50),
    (  400.0,  0.20,   0.50,   1.20,   2.50),
    ( 1000.0,  0.30,   0.80,   2.00,   4.00),
    ( 2000.0,  0.50,   1.20,   3.00,   8.00),
    ( 4000.0,  None,   2.00,   4.00,  12.00),
]

_LINEAR_CLASS_INDEX = {"f": 1, "m": 2, "c": 3, "v": 4}


# ---------------------------------------------------------------------------
# ISO 2768-1 — Angular tolerance table (±decimal degrees)
# Rows keyed by shorter-side length (mm): (upper_mm, f, m, c, v)
# f and m are identical for angular dimensions per the standard.
# Source: ISO 2768-1:1989 Table 3.
# ---------------------------------------------------------------------------

_ANGULAR_TABLE: List[Tuple[float, float, float, float, float]] = [
    #  upper    f        m        c        v
    (   10.0,   1.000,   1.000,   1.500,   3.000),
    (   50.0,   0.500,   0.500,   1.000,   2.000),
    (  120.0,   0.333,   0.333,   0.500,   1.000),
    (  400.0,   0.167,   0.167,   0.250,   0.500),
    (float("inf"), 0.083, 0.083,  0.167,   0.333),
]


def _deg_to_dms(deg: float) -> str:
    """Format decimal degrees as '±D°MM\'' string for display."""
    d = int(deg)
    m = round((deg - d) * 60)
    if m == 0:
        return f"±{d}°"
    return f"±{d}°{m:02d}'"


# ---------------------------------------------------------------------------
# ISO 2768-2 — Geometric tolerance tables (mm)
# Source: ISO 2768-2:1989 Tables 1, 2, 3.
# ---------------------------------------------------------------------------

# Straightness and Flatness — (upper_mm, H, K, L)
_STRAIGHT_FLAT_TABLE: List[Tuple[float, float, float, float]] = [
    (   10.0,  0.02,  0.05,  0.10),
    (   30.0,  0.05,  0.10,  0.20),
    (  100.0,  0.10,  0.20,  0.40),
    (  300.0,  0.20,  0.40,  0.80),
    ( 1000.0,  0.30,  0.60,  1.20),
    ( 3000.0,  0.40,  0.80,  1.60),
]

# Perpendicularity and Symmetry — (upper_mm, H, K, L)
_PERP_SYM_TABLE: List[Tuple[float, float, float, float]] = [
    (  100.0,  0.20,  0.40,  0.60),
    (  300.0,  0.30,  0.60,  1.00),
    ( 1000.0,  0.40,  0.80,  1.50),
    ( 3000.0,  0.50,  1.00,  2.00),
]

# Circular run-out — fixed per class (size-independent per ISO 2768-2 Table 3)
_RUNOUT: Dict[str, float] = {"H": 0.10, "K": 0.20, "L": 0.50}

_GEO_CLASS_INDEX = {"H": 1, "K": 2, "L": 3}

_GEO_CHARACTERISTICS = frozenset({
    "straightness", "flatness",
    "perpendicularity", "symmetry",
    "circular_runout",
})


# ---------------------------------------------------------------------------
# Process → class mapping
# ---------------------------------------------------------------------------

_PROCESS_LINEAR_CLASS: Dict[str, str] = {
    "cylindrical_grinding": "f",
    "CNC_turning": "m",
    "injection_moulding": "c",
    "sand_casting": "c",
}

_PROCESS_GEO_CLASS: Dict[str, str] = {
    "cylindrical_grinding": "H",
    "CNC_turning": "K",
    "injection_moulding": "K",
    "sand_casting": "L",
}


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class TitleBlockRecommendation:
    linear_class: str
    geo_class: str
    title_block: str
    process: str
    notes: List[str]

    def as_dict(self) -> Dict:
        return {
            "linear_class": self.linear_class,
            "geo_class": self.geo_class,
            "title_block": self.title_block,
            "process": self.process,
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# Internal lookup helpers
# ---------------------------------------------------------------------------

def _lookup_linear(nominal_mm: float, col: int) -> Optional[float]:
    for row in _LINEAR_TABLE:
        if nominal_mm <= row[0]:
            return row[col]
    return _LINEAR_TABLE[-1][col]


def _lookup_table3(
    table: List[Tuple[float, float, float, float]],
    size_mm: float,
    col: int,
) -> float:
    for row in table:
        if size_mm <= row[0]:
            return row[col]
    return table[-1][col]


def _it_grade_from_entry(entry: Dict) -> int:
    it_raw = entry.get("typical_it_grade", "IT8")
    if isinstance(it_raw, str):
        return int(it_raw.upper().lstrip("IT") or 8)
    return int(it_raw)


# ---------------------------------------------------------------------------
# Public API — Part 1 (linear)
# ---------------------------------------------------------------------------

def linear_tol_iso2768(nominal_mm: float, tol_class: str = "m") -> float:
    """Return the ISO 2768-1 linear tolerance (±mm) from the standard's table.

    Parameters
    ----------
    nominal_mm:
        Nominal dimension in mm.  Must be in [0.5, 4000].
    tol_class:
        One of ``'f'`` (fine), ``'m'`` (medium), ``'c'`` (coarse),
        ``'v'`` (very coarse).  Falls back to ``'m'`` if unrecognised.

    Returns
    -------
    float
        Half-tolerance in mm (the ± value). Raises ``ValueError`` if the
        class is not applicable for the given size range (e.g. ``'v'`` below
        3 mm or ``'f'`` above 2000 mm).
    """
    cls = tol_class.lower()
    if cls not in _LINEAR_CLASS_INDEX:
        cls = "m"
    col = _LINEAR_CLASS_INDEX[cls]
    value = _lookup_linear(nominal_mm, col)
    if value is None:
        raise ValueError(
            f"ISO 2768-1 class '{tol_class}' is not defined for nominal {nominal_mm} mm. "
            "Check the standard's applicability range."
        )
    return value


# Backwards-compatibility alias
fundamental_tol_iso2768 = linear_tol_iso2768


def angular_tol_iso2768(shorter_side_mm: float, tol_class: str = "m") -> Dict:
    """Return the ISO 2768-1 angular tolerance for a given shorter-side length.

    Parameters
    ----------
    shorter_side_mm:
        Length of the shorter side of the angle in mm.
    tol_class:
        One of ``'f'``, ``'m'``, ``'c'``, ``'v'``.

    Returns
    -------
    dict with keys:
        ``'tolerance_deg'`` — half-tolerance in decimal degrees (the ± value)
        ``'tolerance_dms'`` — formatted string, e.g. ``'±0°30\\'``
        ``'class'``         — resolved class letter
    """
    cls = tol_class.lower()
    if cls not in _LINEAR_CLASS_INDEX:
        cls = "m"
    col = _LINEAR_CLASS_INDEX[cls]  # f=1, m=2, c=3, v=4
    for row in _ANGULAR_TABLE:
        if shorter_side_mm <= row[0]:
            tol_deg = row[col]
            return {
                "class": cls,
                "tolerance_deg": tol_deg,
                "tolerance_dms": _deg_to_dms(tol_deg),
            }
    # unreachable — last row uses inf
    raise ValueError(f"Cannot resolve angular tolerance for {shorter_side_mm} mm")


# ---------------------------------------------------------------------------
# Public API — Part 2 (geometric)
# ---------------------------------------------------------------------------

def geometric_tol_iso2768(
    size_mm: float,
    geo_class: str = "K",
    characteristic: str = "straightness",
) -> float:
    """Return the ISO 2768-2 geometric tolerance (mm) from the standard's table.

    Parameters
    ----------
    size_mm:
        Controlling dimension in mm (feature length for straightness/flatness;
        feature height/length for perpendicularity and symmetry).
    geo_class:
        One of ``'H'``, ``'K'``, ``'L'``.
    characteristic:
        One of ``'straightness'``, ``'flatness'``, ``'perpendicularity'``,
        ``'symmetry'``, ``'circular_runout'``.

    Returns
    -------
    float
        Geometric tolerance in mm.
    """
    gcls = geo_class.upper()
    if gcls not in _GEO_CLASS_INDEX:
        raise ValueError(f"Unknown ISO 2768-2 class '{geo_class}'. Use 'H', 'K', or 'L'.")
    char = characteristic.lower()
    if char not in _GEO_CHARACTERISTICS:
        raise ValueError(
            f"Characteristic '{characteristic}' not in ISO 2768-2 scope. "
            f"Supported: {sorted(_GEO_CHARACTERISTICS)}"
        )
    col = _GEO_CLASS_INDEX[gcls]
    if char == "circular_runout":
        return _RUNOUT[gcls]
    if char in {"straightness", "flatness"}:
        return _lookup_table3(_STRAIGHT_FLAT_TABLE, size_mm, col)
    return _lookup_table3(_PERP_SYM_TABLE, size_mm, col)


# ---------------------------------------------------------------------------
# Public API — process-driven recommendation
# ---------------------------------------------------------------------------

def _linear_class_for_process(process: str, it: int) -> str:
    """Resolve ISO 2768-1 linear class from explicit process map, falling back to IT grade."""
    if process in _PROCESS_LINEAR_CLASS:
        return _PROCESS_LINEAR_CLASS[process]
    if it <= 6:
        return "f"
    if it <= 9:
        return "m"
    if it <= 12:
        return "c"
    return "v"


def propose_general_tolerance(
    nominal_mm: float,
    process: str,
    process_db: Optional[Dict] = None,
) -> Dict:
    """Propose an ISO 2768-1 tolerance class and value based on process capability.

    Returns a dict with ``'class'`` and ``'tolerance_mm'`` for backwards
    compatibility with callers of the original module.

    For a paired geometric class recommendation use ``recommend_title_block``.
    """
    entry = choose_process_entry(process, process_db)
    it = _it_grade_from_entry(entry)
    cls = _linear_class_for_process(process, it)
    tol_mm = linear_tol_iso2768(nominal_mm, cls)
    return {"class": cls, "tolerance_mm": tol_mm}


def recommend_title_block(
    process: str,
    process_db: Optional[Dict] = None,
) -> TitleBlockRecommendation:
    """Recommend a complete ISO 2768 title-block specification for a process.

    Returns a ``TitleBlockRecommendation`` with the suggested linear class,
    geometric class, the formatted title-block string (e.g. ``'ISO 2768-mK'``),
    and contextual notes.

    This recommendation covers only unannotated, non-critical features.
    Critical features must always carry individual tolerances.
    """
    entry = choose_process_entry(process, process_db)
    it = _it_grade_from_entry(entry)

    lin_cls = _linear_class_for_process(process, it)
    geo_cls = _PROCESS_GEO_CLASS.get(process)
    if geo_cls is None:
        if it <= 6:
            geo_cls = "H"
        elif it <= 9:
            geo_cls = "K"
        else:
            geo_cls = "L"

    title_block = f"ISO 2768-{lin_cls}{geo_cls}"

    notes: List[str] = [
        "This specification governs unannotated, non-critical features only.",
        "Bearing bores, sealing surfaces, precision fits, and safety-critical "
        "interfaces require explicit individual tolerances (ISO 286 / ISO 1101).",
    ]
    if lin_cls in {"c", "v"}:
        notes.append(
            f"Class '{lin_cls}' indicates a coarse process — verify that "
            "assembly stack-up is acceptable before releasing the drawing."
        )

    return TitleBlockRecommendation(
        linear_class=lin_cls,
        geo_class=geo_cls,
        title_block=title_block,
        process=process,
        notes=notes,
    )


def list_linear_classes() -> List[str]:
    """Return supported ISO 2768-1 linear class letters."""
    return ["f", "m", "c", "v"]


def list_geo_classes() -> List[str]:
    """Return supported ISO 2768-2 geometric class letters."""
    return ["H", "K", "L"]


def list_geo_characteristics() -> List[str]:
    """Return ISO 2768-2 characteristic names supported by this module."""
    return sorted(_GEO_CHARACTERISTICS)
