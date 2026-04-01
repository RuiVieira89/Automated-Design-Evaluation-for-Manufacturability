"""ISO 286 tolerance helpers.

Implements a minimal set of functions to compute fundamental tolerances for
standard IT grades based on the geometric mean method described in ISO 286-1.

The formulas and tables are simplified for engineering use and demonstration.
Reference:
  ISO 286-1:2010, "Geometrical product specifications (GPS) — ISO code system
  for tolerances on linear sizes — Part 1: Basis of tolerances, deviations and fits".
  (standard formula: i = 0.45 * D^(1/3) + 0.001 * D, i in µm; D = geometric mean diameter in mm)
Secondary: Machinery's Handbook (summary of ISO 286).
"""
import math
from typing import Tuple, Dict

# Multipliers for IT grades (IT5..IT16) following ISO guidance (approximate)
IT_MULTIPLIERS: Dict[str, float] = {
    "IT5": 7,
    "IT6": 10,
    "IT7": 16,
    "IT8": 25,
    "IT9": 40,
    "IT10": 64,
    "IT11": 100,
    "IT12": 160,
    "IT13": 250,
    "IT14": 400,
    "IT15": 640,
    "IT16": 1000,
}

# Representative ISO size ranges (mm)
SIZE_RANGES = [
    (1, 3), (3, 6), (6, 10), (10, 18), (18, 30),
    (30, 50), (50, 80), (80, 120), (120, 180),
    (180, 250), (250, 315), (315, 400), (400, 500),
]


def geometric_mean(d_min: float, d_max: float) -> float:
    """Return geometric mean of a size range."""
    return math.sqrt(d_min * d_max)


def standard_tolerance_factor(D: float) -> float:
    """Compute the standard tolerance unit i (in micrometres) for diameter D.

    ISO formula (approximate): i = 0.45 * D^(1/3) + 0.001 * D  (i in µm)
    """
    return 0.45 * (D ** (1.0 / 3.0)) + 0.001 * D


def fundamental_tolerance(nominal_mm: float, it_grade: str) -> float:
    """Return the tolerance in mm for a nominal size and IT grade.

    The function finds the ISO size range containing nominal_mm, computes the
    standard tolerance unit i (µm), multiplies by the IT multiplier and
    converts to mm.
    """
    # Find containing size range
    for d_min, d_max in SIZE_RANGES:
        if d_min <= nominal_mm <= d_max:
            D = geometric_mean(d_min, d_max)
            break
    else:
        raise ValueError(f"Nominal {nominal_mm}mm outside ISO 286 supported ranges")

    i_um = standard_tolerance_factor(D)  # µm
    multiplier = IT_MULTIPLIERS.get(it_grade)
    if multiplier is None:
        raise ValueError(f"Unsupported IT grade: {it_grade}")

    tol_mm = (i_um * multiplier) / 1000.0
    # Round to reasonable engineering precision
    return round(tol_mm, 6)


def propose_tolerance(nominal_mm: float, process: str, process_db: Dict) -> Dict:
    """Given a nominal dimension and manufacturing process, propose tolerance.

    Returns a dict with fields: nominal_mm, process, it_grade, tolerance_mm,
    achievable_grades, typical_ra_um.
    """
    proc = process_db.get(process)
    if not proc:
        raise ValueError(f"Unknown process: {process}")

    typical_grade = proc.get("typical_it_grade")
    if not typical_grade:
        raise ValueError(f"Process {process} missing typical_it_grade in DB")

    tol_mm = fundamental_tolerance(nominal_mm, typical_grade)

    return {
        "nominal_mm": nominal_mm,
        "process": process,
        "it_grade": typical_grade,
        "tolerance_mm": tol_mm,
        "achievable_grades": proc.get("iso_it_grades", []),
        "typical_ra_um": proc.get("surface_roughness_ra_um", []),
    }


if __name__ == "__main__":
    # Simple demo when module is executed directly
    SAMPLE_DB = {
        "CNC_turning": {
            "typical_it_grade": "IT8",
            "iso_it_grades": ["IT6", "IT7", "IT8", "IT9"],
            "surface_roughness_ra_um": [0.8, 1.6, 3.2],
        },
        "sand_casting": {
            "typical_it_grade": "IT14",
            "iso_it_grades": ["IT12", "IT13", "IT14", "IT15"],
            "surface_roughness_ra_um": [12.5, 25.0],
        },
    }

    example = propose_tolerance(25.0, "CNC_turning", SAMPLE_DB)
    print(example)
