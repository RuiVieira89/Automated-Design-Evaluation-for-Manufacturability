

# Automated ISO Dimension & Tolerance Proposal Tool — Architecture & Strategy

## 1. Problem Framing

Engineers spend significant time manually looking up ISO tolerance tables (e.g., ISO 286 for limits/fits, ISO 2768 for general tolerances, ISO 1101 for GD&T) and matching them to manufacturing processes. 

## 2. Core Knowledge Model: Process → Tolerance Mapping

Before any ML or UI, you need a **structured knowledge base**. This is where rules and lookup tables dominate over ML.

### 2.1 Key ISO Standards to Encode

| Standard | Covers | Example Use |
|---|---|---|
| **ISO 286** (IT grades) | Fundamental tolerances for holes/shafts | IT7 for ground shafts, IT11 for rough turning |
| **ISO 2768** | General tolerances (linear, angular) | Default tolerances for non-critical dims |
| **ISO 1101** | Geometric tolerances (GD&T) | Flatness, cylindricity, position |
| **ISO 4287/4288** | Surface roughness | Ra values achievable per process |
| **ISO 8015** | Fundamental tolerancing principle | How tolerance zones are interpreted |

### 2.2 Process–Capability Data

Each manufacturing process has well-documented achievable IT grades and surface finishes. This is **deterministic, rule-based knowledge** — not an ML problem.

```yaml name=data/process_capability_example.yaml
processes:
  - name: CNC_turning
    iso_it_grades: [IT6, IT7, IT8, IT9]
    typical_it_grade: IT8
    surface_roughness_ra_um: [0.8, 1.6, 3.2]
    min_feature_size_mm: 0.5
    applicable_materials: [steel, aluminium, brass, titanium]
    dimensional_range_mm: [1, 500]

  - name: sand_casting
    iso_it_grades: [IT12, IT13, IT14, IT15, IT16]
    typical_it_grade: IT14
    surface_roughness_ra_um: [12.5, 25.0]
    min_feature_size_mm: 3.0
    applicable_materials: [cast_iron, aluminium, bronze]
    dimensional_range_mm: [10, 2000]

  - name: injection_moulding
    iso_it_grades: [IT10, IT11, IT12, IT13]
    typical_it_grade: IT12
    surface_roughness_ra_um: [0.4, 1.6]
    min_feature_size_mm: 0.5
    applicable_materials: [ABS, PA6, POM, PP]
    dimensional_range_mm: [0.5, 800]

  - name: cylindrical_grinding
    iso_it_grades: [IT4, IT5, IT6]
    typical_it_grade: IT5
    surface_roughness_ra_um: [0.1, 0.4, 0.8]
    min_feature_size_mm: 1.0
    applicable_materials: [hardened_steel, tool_steel]
    dimensional_range_mm: [3, 300]
```

> **Key point:** This mapping is the foundation. You source it from Machinery's Handbook, ISO standards, and manufacturing references. It's a **lookup/rule engine**, not ML.

---

## 3. System Architecture (All Open Source)

```
┌──────────────────────────────────────────────────────────┐
│                      USER INTERFACE                       │
│              (FreeCAD plugin  or  Web UI)                 │
│   ┌────────────────────────────────────────────────────┐  │
│   │  Feature input: Ø25 shaft, L=100, fit with bore   │  │
│   │  Process input: CNC turning + grinding             │  │
│   │  ──────────────────────────────────────────────    │  │
│   │  OUTPUT:  Ø25 h6 (+0.000 / -0.013)               │  │
│   │           General tol: ISO 2768-mK                 │  │
│   │           Ra ≤ 0.8 µm (ground surfaces)            │  │
│   │           Cylindricity ≤ 0.01 mm                   │  │
│   └────────────────────────────────────────────────────┘  │
└──────────────┬───────────────────────────┬────────────────┘
               │                           │
       ┌───────▼────────┐        ┌─────────▼──────────┐
       │  Rule Engine    │        │   ML/NLP Layer     │
       │  (core logic)   │        │   (optional)       │
       │                 │        │                    │
       │ ISO 286 tables  │        │ Feature classifier │
       │ ISO 2768 tables │        │ from STEP/CAD      │
       │ Process caps    │        │                    │
       │ Fit recommender │        │ Historical tol.    │
       └───────┬─────────┘        │ recommendation     │
               │                  └────────┬───────────┘
       ┌───────▼──────────────────────────▼────────┐
       │         KNOWLEDGE BASE (SQLite / JSON)     │
       │  ISO tables + Process data + Fit library   │
       └────────────────────────────────────────────┘
```

---

## 4. Implementation (Open Source Only)

### 4.2 Core Tolerance Engine — Example

```python name=src/iso286.py
"""
ISO 286-1: Fundamental tolerance calculation.
IT grades and fundamental deviations for shafts and holes.
"""
import math
from enum import Enum

class ITGrade(Enum):
    IT01 = "IT01"
    IT0 = "IT0"
    IT1 = "IT1"
    # ... through IT18
    IT6 = "IT6"
    IT7 = "IT7"
    IT8 = "IT8"
    IT9 = "IT9"
    IT10 = "IT10"
    IT11 = "IT11"
    IT12 = "IT12"

# ISO 286 size ranges (mm) and geometric mean
SIZE_RANGES = [
    (1, 3), (3, 6), (6, 10), (10, 18), (18, 30),
    (30, 50), (50, 80), (80, 120), (120, 180),
    (180, 250), (250, 315), (315, 400), (400, 500),
]

def geometric_mean(d_min: float, d_max: float) -> float:
    return math.sqrt(d_min * d_max)

def standard_tolerance_factor(D: float) -> float:
    """i = 0.45 * D^(1/3) + 0.001 * D  (ISO 286-1, in µm)"""
    return 0.45 * (D ** (1/3)) + 0.001 * D

# Multipliers for IT grades 5–18 (IT5=7i, IT6=10i, IT7=16i, ...)
IT_MULTIPLIERS = {
    "IT5": 7, "IT6": 10, "IT7": 16, "IT8": 25,
    "IT9": 40, "IT10": 64, "IT11": 100, "IT12": 160,
    "IT13": 250, "IT14": 400, "IT15": 640, "IT16": 1000,
}

def fundamental_tolerance(nominal_mm: float, it_grade: str) -> float:
    """Returns tolerance in mm for a given nominal size and IT grade."""
    # Find the size range
    for d_min, d_max in SIZE_RANGES:
        if d_min <= nominal_mm <= d_max:
            D = geometric_mean(d_min, d_max)
            break
    else:
        raise ValueError(f"Nominal {nominal_mm}mm outside ISO 286 range")

    i = standard_tolerance_factor(D)  # µm
    multiplier = IT_MULTIPLIERS.get(it_grade)
    if multiplier is None:
        raise ValueError(f"Unsupported grade: {it_grade}")

    return round((i * multiplier) / 1000, 4)  # convert µm → mm


def propose_tolerance(nominal_mm: float, process: str,
                      process_db: dict) -> dict:
    """
    Given a nominal dimension and process, propose ISO tolerance.
    """
    proc = process_db.get(process)
    if not proc:
        raise ValueError(f"Unknown process: {process}")

    typical_grade = proc["typical_it_grade"]
    tol_mm = fundamental_tolerance(nominal_mm, typical_grade)

    return {
        "nominal_mm": nominal_mm,
        "process": process,
        "it_grade": typical_grade,
        "tolerance_mm": tol_mm,
        "achievable_grades": proc["iso_it_grades"],
        "typical_ra_um": proc["surface_roughness_ra_um"],
    }


# --- Example usage ---
if __name__ == "__main__":
    PROCESS_DB = {
        "CNC_turning": {
            "typical_it_grade": "IT8",
            "iso_it_grades": ["IT6", "IT7", "IT8", "IT9"],
            "surface_roughness_ra_um": [0.8, 1.6, 3.2],
        },
        "sand_casting": {
            "typical_it_grade": "IT14",
            "iso_it_grades": ["IT12", "IT13", "IT14", "IT15", "IT16"],
            "surface_roughness_ra_um": [12.5, 25.0],
        },
    }

    result = propose_tolerance(25.0, "CNC_turning", PROCESS_DB)
    print(result)
    # → {'nominal_mm': 25.0, 'it_grade': 'IT8', 'tolerance_mm': 0.033, ...}
```

### 4.3 Fit Recommender (Rule-Based)

```python name=src/fit_recommender.py
"""
Recommend standard ISO fits based on functional requirement.
"""

# Common fits library (ISO 286-2 preferred fits)
FIT_LIBRARY = {
    "clearance_loose":    {"hole": "H11", "shaft": "c11", "use": "Loose running, large clearance"},
    "clearance_free":     {"hole": "H9",  "shaft": "d9",  "use": "Free running, no precision"},
    "clearance_close":    {"hole": "H8",  "shaft": "f7",  "use": "Close running, accurate location"},
    "clearance_sliding":  {"hole": "H7",  "shaft": "g6",  "use": "Sliding fit, precise location"},
    "transition_similar": {"hole": "H7",  "shaft": "h6",  "use": "Locational, snug (most common)"},
    "transition_tight":   {"hole": "H7",  "shaft": "k6",  "use": "Tight transition, light press"},
    "transition_fixed":   {"hole": "H7",  "shaft": "n6",  "use": "Light press, fixed assembly"},
    "interference_press": {"hole": "H7",  "shaft": "p6",  "use": "Press fit, permanent assembly"},
    "interference_heavy": {"hole": "H7",  "shaft": "s6",  "use": "Heavy press, shrink fit"},
}

def recommend_fit(functional_requirement: str) -> dict:
    """Simple keyword match to recommend a fit."""
    req = functional_requirement.lower()

    if any(w in req for w in ["bearing", "sliding", "rotate", "journal"]):
        return FIT_LIBRARY["clearance_sliding"]
    elif any(w in req for w in ["press", "permanent", "shrink"]):
        return FIT_LIBRARY["interference_press"]
    elif any(w in req for w in ["locational", "snug", "precise", "alignment"]):
        return FIT_LIBRARY["transition_similar"]
    elif any(w in req for w in ["loose", "thermal", "expansion"]):
        return FIT_LIBRARY["clearance_loose"]
    elif any(w in req for w in ["free running", "no precision"]):
        return FIT_LIBRARY["clearance_free"]
    else:
        # Default to most common engineering fit
        return FIT_LIBRARY["transition_similar"]
```

---
