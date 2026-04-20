"""ISO 286 — Tolerance grades and fit advisor.

Combines ISO 286-1 (fundamental tolerances, IT grades) and ISO 286-2
(preferred fits, limits and deviations) in a single module.

IT grades
---------
  fundamental_tolerance(nominal_mm, it_grade)   → tolerance in mm
  propose_tolerance(nominal_mm, process, db)    → dict with grade + tolerance

Fit advisor
-----------
  fit_category and clearance_type are inputs supplied by upstream modules.

  list_fit_options()                              → valid input catalogue
  select_fit(fit_category, clearance_type)        → (hole_code, shaft_code)
  hole_deviations(nominal_mm, hole_code)          → (EI_mm, ES_mm)
  shaft_deviations(nominal_mm, shaft_code)        → (ei_mm, es_mm)
  evaluate_fit(nominal_mm, fit_category,
               clearance_type)                    → FitResult

References
----------
  ISO 286-1:2010  — Basis of tolerances, deviations and fits.
  ISO 286-2:2010  — Tables of standard tolerance grades and limit deviations.
  FreeCAD TechDraw TaskHoleShaftFit.py — tabulated IT6-IT11 and deviation values.
  Machinery's Handbook — supplementary deviation values for d, p, u.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Tuple

# ===========================================================================
# Size ranges
# ===========================================================================

# 13-range system used for IT01–IT5 and IT12–IT18 (formula-based, starts at 1 mm)
SIZE_RANGES: List[Tuple[float, float]] = [
    (1, 3), (3, 6), (6, 10), (10, 18), (18, 30),
    (30, 50), (50, 80), (80, 120), (120, 180),
    (180, 250), (250, 315), (315, 400), (400, 500),
]

# 25-range system per ISO 286-1 Table 3 used for IT6–IT11 and all deviation tables.
# Matches FreeCAD TechDraw implementation and the standard's fine sub-ranges.
FIT_SIZE_RANGES: List[Tuple[float, float]] = [
    (0, 3),   (3, 6),   (6, 10),  (10, 14),  (14, 18),
    (18, 24), (24, 30), (30, 40), (40, 50),  (50, 65),
    (65, 80), (80, 100),(100,120),(120, 140),(140, 160),
    (160,180),(180,200),(200,225),(225, 250),(250, 280),
    (280,315),(315,355),(355,400),(400, 450),(450, 500),
]


def _fit_range_index(nominal_mm: float) -> int:
    """Return index into FIT_SIZE_RANGES for a given nominal size."""
    for i, (lo, hi) in enumerate(FIT_SIZE_RANGES):
        if lo <= nominal_mm <= hi:
            return i
    raise ValueError(
        f"Nominal {nominal_mm} mm is outside the supported range "
        f"(0–500 mm)"
    )


# ===========================================================================
# IT grade tolerance (ISO 286-1)
# ===========================================================================

# IT01, IT0, IT1 — linear formula T(µm) = a + b·D  (ISO 286-1:2010 Table 2)
IT_FORMULA_GRADES: Dict[str, Tuple[float, float]] = {
    "IT01": (0.3, 0.008),
    "IT0":  (0.5, 0.012),
    "IT1":  (0.8, 0.020),
}

# IT2–IT5, IT12–IT18 — T(µm) = k·i  (ISO 286-1:2010 Table 2)
# IT2–IT4 are approximate values extrapolated from the R5 series anchored at IT5 = 7i.
IT_MULTIPLIERS: Dict[str, float] = {
    "IT2":  1.6,
    "IT3":  2.5,
    "IT4":  4.0,
    "IT5":  7,
    "IT12": 160,
    "IT13": 250,
    "IT14": 400,
    "IT15": 640,
    "IT16": 1000,
    "IT17": 1600,
    "IT18": 2500,
}

# IT6–IT11 — exact tabulated values (µm) over 25 FIT_SIZE_RANGES.
# Source: ISO 286-1:2010 Table 1; FreeCAD TechDraw TaskHoleShaftFit.py.
_IT_TABLE: Dict[str, List[int]] = {
    "IT6":  [ 6,  8,  9, 11, 11, 13, 13, 16, 16, 19, 19, 22, 22, 25, 25, 25, 29, 29, 29, 32, 32, 36, 36, 40, 40],
    "IT7":  [10, 12, 15, 18, 18, 21, 21, 25, 25, 30, 30, 35, 35, 40, 40, 40, 46, 46, 46, 52, 52, 57, 57, 63, 63],
    "IT8":  [14, 18, 22, 27, 27, 33, 33, 39, 39, 46, 46, 54, 54, 63, 63, 63, 72, 72, 72, 81, 81, 89, 89, 97, 97],
    "IT9":  [25, 30, 36, 43, 43, 52, 52, 62, 62, 74, 74, 87, 87,100,100,100,115,115,115,130,130,140,140,155,155],
    "IT10": [40, 48, 58, 70, 70, 84, 84,100,100,120,120,140,140,160,160,160,185,185,185,210,210,230,230,250,250],
    "IT11": [60, 75, 90,110,110,130,130,160,160,190,190,220,220,250,250,250,290,290,290,320,320,360,360,400,400],
}


def geometric_mean(d_min: float, d_max: float) -> float:
    return math.sqrt(d_min * d_max)


def standard_tolerance_factor(D: float) -> float:
    """Standard tolerance unit i (µm) for geometric mean diameter D (mm).

    ISO 286-1 formula: i = 0.45·D^(1/3) + 0.001·D
    """
    return 0.45 * (D ** (1.0 / 3.0)) + 0.001 * D


def fundamental_tolerance(nominal_mm: float, it_grade: str) -> float:
    """Return the fundamental tolerance in mm for a nominal size and IT grade.

    - IT6–IT11: exact tabulated values over 25 ISO sub-ranges.
    - IT01, IT0, IT1: linear formula T(µm) = a + b·D.
    - IT2–IT5, IT12–IT18: T(µm) = k·i (formula).
    """
    if it_grade in _IT_TABLE:
        idx = _fit_range_index(nominal_mm)
        return round(_IT_TABLE[it_grade][idx] / 1000.0, 6)

    # Formula path for grades outside the tabulated set
    for d_min, d_max in SIZE_RANGES:
        if d_min <= nominal_mm <= d_max:
            D = geometric_mean(d_min, d_max)
            break
    else:
        raise ValueError(f"Nominal {nominal_mm} mm is outside supported range (1–500 mm)")

    formula = IT_FORMULA_GRADES.get(it_grade)
    if formula is not None:
        a, b = formula
        return round((a + b * D) / 1000.0, 6)

    multiplier = IT_MULTIPLIERS.get(it_grade)
    if multiplier is None:
        raise ValueError(f"Unsupported IT grade: {it_grade!r}")

    return round((standard_tolerance_factor(D) * multiplier) / 1000.0, 6)


def propose_tolerance(nominal_mm: float, process: str, process_db: Dict) -> Dict:
    """Propose a tolerance for a nominal dimension and manufacturing process.

    Returns a dict with keys: nominal_mm, process, it_grade, tolerance_mm,
    achievable_grades, typical_ra_um.
    """
    proc = process_db.get(process)
    if not proc:
        raise ValueError(f"Unknown process: {process}")

    typical_grade = proc.get("typical_it_grade")
    if not typical_grade:
        raise ValueError(f"Process {process} missing typical_it_grade in DB")

    return {
        "nominal_mm":        nominal_mm,
        "process":           process,
        "it_grade":          typical_grade,
        "tolerance_mm":      fundamental_tolerance(nominal_mm, typical_grade),
        "achievable_grades": proc.get("iso_it_grades", []),
        "typical_ra_um":     proc.get("surface_roughness_ra_um", []),
    }


# ===========================================================================
# Fit catalog — ISO 286-2 preferred fits, hole-basis system
# ===========================================================================

FIT_CATALOG: Dict[str, Dict[str, Tuple[str, str]]] = {
    "clearance": {
        "loose":         ("H11", "c11"),
        "free_running":  ("H9",  "d9"),
        "close_running": ("H8",  "f7"),
        "sliding":       ("H7",  "g6"),
        "close_sliding": ("H7",  "h6"),
    },
    "transition": {
        "accurate_location":  ("H7", "k6"),
        "positive_location":  ("H7", "n6"),
    },
    "interference": {
        "light":        ("H7", "p6"),
        "medium_light": ("H7", "r6"),
        "medium":       ("H7", "s6"),
        "heavy":        ("H7", "u6"),
    },
}

_FIT_DESCRIPTIONS: Dict[str, str] = {
    "H11/c11": "Very loose clearance — very wide tolerances, dirty environments or wide temperature variation",
    "H9/d9":   "Free running — widely toleranced rotating/sliding parts, low positional accuracy required",
    "H8/f7":   "Close running — general running fits, grease- or oil-lubricated bearings",
    "H7/g6":   "Sliding — accurate location with slow movement or sliding, minimal play",
    "H7/h6":   "Close sliding — precise location, no intentional play, easy assembly",
    "H7/k6":   "Transition (accurate location) — accurate location, slight interference or clearance possible",
    "H7/n6":   "Transition (positive location) — more positive location, light press required",
    "H7/p6":   "Light interference — press fit, permanent but still disassemblable",
    "H7/r6":   "Medium-light interference — press fit with reliable retention",
    "H7/s6":   "Medium interference — drive fit, reliable force/torque transmission",
    "H7/u6":   "Heavy interference — permanent joint for high torque or shock loading",
}

# ===========================================================================
# Deviation tables — indexed over FIT_SIZE_RANGES (25 entries)
#
# Convention: all tables store the UPPER deviation (es for shafts, ES for holes)
# in micrometres.  For a given tolerance code the other limit is:
#   ei  = es  − IT   (shaft)
#   EI  = ES  − IT   (hole)
# Exception: H holes (ES_fundamental = 0) are handled as the special case
#   EI = 0, ES = +IT  — the standard "hole-basis zero" convention.
#
# Sources: ISO 286-1:2010 Table 3; FreeCAD TechDraw TaskHoleShaftFit.py;
#          Machinery's Handbook (d, p, u).
# ===========================================================================

# ---------------------------------------------------------------------------
# Shaft upper deviations es (µm)  — clearance shafts: negative; interference: positive
# ---------------------------------------------------------------------------
_SHAFT_TABLE: Dict[str, List[float]] = {
    # --- clearance shafts (a–h): es is the fundamental deviation, negative ---
    "c": [-60,-70,-80,-95,-95,-110,-110,-120,-130,-140,-150,-170,-180,-200,-210,
          -230,-240,-260,-280,-300,-330,-360,-400,-440,-480],
    "d": [-20,-30,-40,-50,-50,-65,-65,-80,-80,-100,-100,-120,-120,-145,-145,
          -145,-170,-170,-170,-190,-190,-210,-210,-230,-230],
    "e": [-14,-20,-25,-32,-32,-40,-40,-50,-50,-60,-60,-72,-72,-85,-85,
          -85,-100,-100,-100,-110,-110,-125,-125,-135,-135],
    "f": [ -6,-10,-13,-16,-16,-20,-20,-25,-25,-30,-30,-36,-36,-43,-43,
           -43,-50,-50,-50,-56,-56,-62,-62,-68,-68],
    "g": [ -2, -4, -5, -6, -6, -7, -7, -9, -9,-10,-10,-12,-12,-14,-14,
           -14,-15,-15,-15,-17,-17,-18,-18,-20,-20],
    "h": [0] * 25,
    # --- transition / interference shafts (k–u): es is positive ---
    # Values represent es for the grade used in preferred fits (IT6 for k,n,r,s,p,u).
    # Source: FreeCAD rField, kField, nField, sField; ISO 286-1 Table 3 for p, u.
    "k": [ 6,  9, 10, 12, 12, 15, 15, 18, 18, 21, 21, 25, 25, 28, 28,
           28, 33, 33, 33, 36, 36, 40, 40, 45, 45],
    "n": [10, 16, 19, 23, 23, 28, 28, 33, 33, 39, 39, 45, 45, 52, 52,
          60, 60, 66, 66, 73, 73, 80, 80, 80, 80],
    "p": [12, 20, 24, 29, 29, 35, 35, 42, 42, 51, 51, 59, 59, 68, 68,
          68, 79, 79, 79, 88, 88, 98, 98,108,108],
    "r": [16, 23, 28, 34, 34, 41, 41, 50, 50, 60, 62, 73, 76, 88, 90,
          93,106,109,113,126,130,144,150,166,172],
    "s": [20, 27, 32, 39, 39, 48, 48, 59, 59, 72, 78, 93,101,117,125,
         133,151,159,169,190,202,226,244,272,292],
    "u": [24, 31, 37, 44, 44, 54, 54, 76, 76,106,106,146,146,191,191,
         191,239,239,239,290,290,351,351,425,425],
}

# ---------------------------------------------------------------------------
# Hole upper deviations ES (µm) — clearance holes: positive; interference: negative
# H is special-cased: ES_fundamental = 0 → hole_deviations() returns EI=0, ES=+IT.
# ---------------------------------------------------------------------------
_HOLE_TABLE: Dict[str, List[float]] = {
    # clearance holes (D–G): ES positive
    "D": [60, 78, 98,120,120,149,149,180,180,220,220,260,260,305,305,
         305,355,355,355,400,400,440,440,480,480],
    "E": [39, 50, 61, 75, 75, 92, 92,112,112,134,134,159,159,185,185,
         185,215,215,215,240,240,265,265,290,290],
    "F": [20, 28, 35, 43, 43, 53, 53, 64, 64, 76, 76, 90, 90,106,106,
         106,122,122,122,137,137,151,151,165,165],
    "G": [12, 16, 20, 24, 24, 28, 28, 34, 34, 40, 40, 47, 47, 54, 54,
          54, 61, 61, 61, 69, 69, 75, 75, 83, 83],
    # H: ES_fundamental = 0; special-cased in hole_deviations()
    "H": [0] * 25,
    # transition holes (K, N): ES near zero or slightly negative
    "K": [ 0,  3,  5,  6,  6,  6,  6,  7,  7,  9,  9, 10, 10, 12, 12,
           12, 13, 13, 13, 16, 16, 17, 17, 18, 18],
    "N": [-4, -4, -4, -5, -5, -7, -7, -8, -8, -9, -9,-10,-10,-12,-12,
          -12,-14,-14,-14,-14,-14,-16,-16,-17,-17],
    # interference holes (R, S): ES negative
    "R": [-10,-11,-13,-16,-16,-20,-20,-25,-25,-30,-32,-38,-41,-48,-50,
          -53,-60,-63,-67,-74,-78,-87,-93,-103,-109],
    "S": [-14,-15,-17,-21,-21,-27,-27,-34,-34,-42,-48,-58,-66,-77,-85,
          -93,-105,-113,-123,-138,-150,-169,-187,-209,-229],
}


def _parse_code(code: str) -> Tuple[str, str]:
    """Split a tolerance code like 'H7' or 'k6' into (letter(s), 'ITn')."""
    for i in range(1, len(code)):
        if code[i].isdigit():
            return code[:i], "IT" + code[i:]
    raise ValueError(f"Cannot parse tolerance code: {code!r}")


# ===========================================================================
# Public fit API
# ===========================================================================

def list_fit_options() -> Dict[str, List[str]]:
    """Return valid fit_category → [clearance_type, …] mapping."""
    return {cat: list(types) for cat, types in FIT_CATALOG.items()}


def select_fit(fit_category: str, clearance_type: str) -> Tuple[str, str]:
    """Return (hole_code, shaft_code) for the requested fit.

    Args:
        fit_category:   "clearance", "transition", or "interference".
        clearance_type: Subcategory — see list_fit_options() for valid values.
    """
    cat = FIT_CATALOG.get(fit_category)
    if cat is None:
        raise ValueError(
            f"Unknown fit_category {fit_category!r}. Valid: {list(FIT_CATALOG)}"
        )
    pair = cat.get(clearance_type)
    if pair is None:
        raise ValueError(
            f"Unknown clearance_type {clearance_type!r} for category "
            f"{fit_category!r}. Valid: {list(cat)}"
        )
    return pair


def hole_deviations(nominal_mm: float, hole_code: str) -> Tuple[float, float]:
    """Return (EI_mm, ES_mm) for a hole tolerance code.

    Supports all letters in _HOLE_TABLE: D, E, F, G, H, K, N, R, S.
    For H: EI = 0, ES = +IT (hole-basis convention).
    For all others: ES = table value, EI = ES − IT.
    """
    letter, it_grade = _parse_code(hole_code)
    upper_letter = letter.upper()

    if upper_letter not in _HOLE_TABLE:
        raise ValueError(
            f"Unsupported hole deviation letter {letter!r}. "
            f"Supported: {sorted(_HOLE_TABLE)}"
        )

    it_tol = fundamental_tolerance(nominal_mm, it_grade)
    idx = _fit_range_index(nominal_mm)

    if upper_letter == "H":
        return 0.0, round(it_tol, 6)

    ES_mm = _HOLE_TABLE[upper_letter][idx] / 1000.0
    EI_mm = round(ES_mm - it_tol, 6)
    return EI_mm, round(ES_mm, 6)


def shaft_deviations(nominal_mm: float, shaft_code: str) -> Tuple[float, float]:
    """Return (ei_mm, es_mm) for a shaft tolerance code.

    Supports all letters in _SHAFT_TABLE: c, d, e, f, g, h, k, n, p, r, s, u.
    Negative values are below the nominal line (clearance shafts a–h).
    Positive values are above the nominal line (interference shafts k–zc).
    """
    letter, it_grade = _parse_code(shaft_code)

    if letter not in _SHAFT_TABLE:
        raise ValueError(
            f"Unsupported shaft deviation letter {letter!r}. "
            f"Supported: {sorted(_SHAFT_TABLE)}"
        )

    it_tol = fundamental_tolerance(nominal_mm, it_grade)
    idx = _fit_range_index(nominal_mm)
    es_mm = _SHAFT_TABLE[letter][idx] / 1000.0
    return round(es_mm - it_tol, 6), round(es_mm, 6)


@dataclass
class FitResult:
    """Complete dimensional analysis of a standard ISO 286 fit."""

    fit_designation: str    # e.g. "H7/k6"
    nominal_mm: float
    fit_category: str
    clearance_type: str
    description: str

    hole_code: str
    hole_EI_mm: float       # lower deviation of hole (mm)
    hole_ES_mm: float       # upper deviation of hole (mm)
    hole_min_mm: float      # absolute minimum hole size
    hole_max_mm: float      # absolute maximum hole size

    shaft_code: str
    shaft_ei_mm: float      # lower deviation of shaft (mm)
    shaft_es_mm: float      # upper deviation of shaft (mm)
    shaft_min_mm: float     # absolute minimum shaft size
    shaft_max_mm: float     # absolute maximum shaft size

    # Positive = clearance, negative = interference
    max_clearance_mm: float     # ES_hole − ei_shaft
    min_clearance_mm: float     # EI_hole − es_shaft

    def is_always_clearance(self) -> bool:
        return self.min_clearance_mm > 0.0

    def is_always_interference(self) -> bool:
        return self.max_clearance_mm < 0.0

    def is_transition(self) -> bool:
        return not self.is_always_clearance() and not self.is_always_interference()


def evaluate_fit(
    nominal_mm: float,
    fit_category: str,
    clearance_type: str,
) -> FitResult:
    """Compute all limits and clearance/interference bounds for a standard fit.

    Args:
        nominal_mm:     Nominal shaft/bore diameter in mm.
        fit_category:   "clearance", "transition", or "interference".
        clearance_type: Subcategory — see list_fit_options() for valid values.

    Returns:
        FitResult with hole/shaft absolute limits and assembly fit bounds.
    """
    hole_code, shaft_code = select_fit(fit_category, clearance_type)
    EI, ES = hole_deviations(nominal_mm, hole_code)
    ei, es = shaft_deviations(nominal_mm, shaft_code)

    designation = f"{hole_code}/{shaft_code}"
    return FitResult(
        fit_designation=designation,
        nominal_mm=nominal_mm,
        fit_category=fit_category,
        clearance_type=clearance_type,
        description=_FIT_DESCRIPTIONS.get(
            designation, f"{fit_category} — {clearance_type}"
        ),
        hole_code=hole_code,
        hole_EI_mm=EI,
        hole_ES_mm=ES,
        hole_min_mm=round(nominal_mm + EI, 6),
        hole_max_mm=round(nominal_mm + ES, 6),
        shaft_code=shaft_code,
        shaft_ei_mm=ei,
        shaft_es_mm=es,
        shaft_min_mm=round(nominal_mm + ei, 6),
        shaft_max_mm=round(nominal_mm + es, 6),
        max_clearance_mm=round(ES - ei, 6),
        min_clearance_mm=round(EI - es, 6),
    )
