"""ISO 1101 geometric tolerancing advisor.

Recommends geometric tolerances for the five ISO 1101 categories — Form,
Orientation, Location, Run-out, and Profile — based on manufacturing process
capability and functional context supplied by other modules.

Returned values are engineering guidance (mm), not a legal interpretation of the
standard.  Integrate with fit_iso286, iso2768, and iso4287_4288 for full GPS
chain coverage.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .helpers import choose_process_entry


# ---------------------------------------------------------------------------
# Characteristic definitions
# ---------------------------------------------------------------------------

CHARACTERISTICS: Dict[str, Dict] = {
    # --- Form (no datum required) ---
    "straightness": {
        "category": "form",
        "zone_geometry": "cylinder or two parallel planes",
        "requires_datum": False,
        "base_factor": 0.0010,
    },
    "flatness": {
        "category": "form",
        "zone_geometry": "two parallel planes",
        "requires_datum": False,
        "base_factor": 0.0015,
    },
    "circularity": {
        "category": "form",
        "zone_geometry": "annular zone in cross-section",
        "requires_datum": False,
        "base_factor": 0.0008,
    },
    "cylindricity": {
        "category": "form",
        "zone_geometry": "coaxial cylindrical shell",
        "requires_datum": False,
        "base_factor": 0.0012,
    },
    # --- Orientation (datum required) ---
    "parallelism": {
        "category": "orientation",
        "zone_geometry": "two parallel planes or cylinder",
        "requires_datum": True,
        "base_factor": 0.0020,
    },
    "perpendicularity": {
        "category": "orientation",
        "zone_geometry": "two parallel planes or cylinder",
        "requires_datum": True,
        "base_factor": 0.0025,
    },
    "angularity": {
        "category": "orientation",
        "zone_geometry": "two parallel planes",
        "requires_datum": True,
        "base_factor": 0.0030,
    },
    # --- Location (datum required) ---
    "position": {
        "category": "location",
        "zone_geometry": "cylinder, two parallel planes, or sphere",
        "requires_datum": True,
        "base_factor": 0.0050,
    },
    "concentricity": {
        "category": "location",
        "zone_geometry": "cylinder about datum axis",
        "requires_datum": True,
        "base_factor": 0.0040,
    },
    "symmetry": {
        "category": "location",
        "zone_geometry": "two parallel planes about datum plane",
        "requires_datum": True,
        "base_factor": 0.0040,
    },
    # --- Run-out (datum axis required) ---
    "circular_runout": {
        "category": "runout",
        "zone_geometry": "annular zone per cross-section during rotation",
        "requires_datum": True,
        "base_factor": 0.0030,
    },
    "total_runout": {
        "category": "runout",
        "zone_geometry": "coaxial cylindrical shell during full rotation",
        "requires_datum": True,
        "base_factor": 0.0020,
    },
    # --- Profile (datum optional) ---
    "profile_of_a_line": {
        "category": "profile",
        "zone_geometry": "two offset curves along the line",
        "requires_datum": False,
        "base_factor": 0.0040,
    },
    "profile_of_a_surface": {
        "category": "profile",
        "zone_geometry": "two offset surfaces",
        "requires_datum": False,
        "base_factor": 0.0035,
    },
}


# ---------------------------------------------------------------------------
# Functional context multipliers
# Tighter function -> smaller multiplier -> tighter tolerance recommendation.
# ---------------------------------------------------------------------------

FUNCTIONAL_MULTIPLIERS: Dict[str, float] = {
    "bearing_bore": 0.35,       # rotation quality, tight clearance
    "sealing_surface": 0.45,    # leakage prevention
    "locating_pin": 0.55,       # precise assembly location
    "sliding_fit": 0.50,        # smooth linear or rotational motion
    "rotating_shaft": 0.40,     # run-out sensitive
    "threaded_interface": 0.65,
    "assembly_locator": 0.70,
    "general": 1.00,
    "structural": 1.50,         # shape not functionally critical
    "cosmetic": 2.00,
}


# ---------------------------------------------------------------------------
# Functional context -> recommended characteristics
# ---------------------------------------------------------------------------

FUNCTIONAL_RECOMMENDATIONS: Dict[str, List[str]] = {
    "bearing_bore": ["circularity", "cylindricity", "position", "perpendicularity"],
    "sealing_surface": ["flatness", "circularity", "profile_of_a_surface"],
    "locating_pin": ["straightness", "cylindricity", "position"],
    "sliding_fit": ["straightness", "cylindricity", "parallelism"],
    "rotating_shaft": ["circular_runout", "total_runout", "concentricity", "straightness"],
    "threaded_interface": ["straightness", "position"],
    "assembly_locator": ["position", "perpendicularity", "flatness"],
    "general": ["flatness", "perpendicularity", "position"],
    "structural": ["flatness", "position"],
    "cosmetic": ["profile_of_a_surface"],
}


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class GeoTolResult:
    characteristic: str
    category: str
    tolerance_mm: float
    zone_geometry: str
    requires_datum: bool
    functional_class: str
    process: str
    it_grade: int
    notes: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict:
        return {
            "characteristic": self.characteristic,
            "category": self.category,
            "tolerance_mm": round(self.tolerance_mm, 5),
            "zone_geometry": self.zone_geometry,
            "requires_datum": self.requires_datum,
            "functional_class": self.functional_class,
            "process": self.process,
            "it_grade": self.it_grade,
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _it_grade_from_entry(entry: Dict) -> int:
    it_raw = entry.get("typical_it_grade", "IT8")
    if isinstance(it_raw, str):
        return int(it_raw.upper().lstrip("IT") or 8)
    return int(it_raw)


def _compute_tolerance(
    characteristic: str,
    feature_size_mm: float,
    it_grade: int,
    functional_class: str,
) -> float:
    """Scale base_factor by feature size, IT grade relative to IT8, and functional multiplier.

    Lower IT grade (better process) -> smaller it_modifier -> tighter recommendation.
    """
    char = CHARACTERISTICS[characteristic]
    base = char["base_factor"]
    it_modifier = it_grade / 8.0
    func_modifier = FUNCTIONAL_MULTIPLIERS.get(functional_class, 1.0)
    return feature_size_mm * base * it_modifier * func_modifier


def _build_notes(
    char_info: Dict,
    functional_class: str,
    it_grade: int,
    datum_available: bool,
) -> List[str]:
    notes: List[str] = []
    if char_info["requires_datum"] and not datum_available:
        notes.append(
            f"{char_info['category'].capitalize()} tolerance requires a datum "
            "reference frame — ensure fixturing datum is defined."
        )
    if functional_class == "bearing_bore" and char_info["category"] == "location":
        notes.append(
            "Cylindrical position tolerance zone recommended; apply MMC modifier "
            "(ISO 2692) where clearance allows."
        )
    if functional_class == "sealing_surface":
        notes.append(
            "Surface finish (Ra/Rz per ISO 4287) must be specified alongside "
            "form tolerance for sealing performance."
        )
    if functional_class == "rotating_shaft":
        notes.append(
            "Run-out tolerance subsumes concentricity for rotating features; "
            "prefer circular_runout or total_runout over concentricity."
        )
    if it_grade > 10 and functional_class in {"bearing_bore", "sealing_surface", "sliding_fit"}:
        notes.append(
            f"Process IT{it_grade} may be insufficient for '{functional_class}' — "
            "consider a finer process (grinding, honing, or precision boring)."
        )
    return notes


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def recommend_geometric_tolerance(
    characteristic: str,
    feature_size_mm: float,
    process: str,
    functional_class: str = "general",
    datum_available: bool = True,
    process_db: Optional[Dict] = None,
) -> GeoTolResult:
    """Recommend an ISO 1101 geometric tolerance for a single characteristic.

    Parameters
    ----------
    characteristic:
        ISO 1101 characteristic name (case-insensitive).  Must be one of the
        keys in ``CHARACTERISTICS`` (e.g. ``"flatness"``, ``"position"``).
    feature_size_mm:
        Nominal feature size in mm — diameter for bores/pins, length for
        planar features.
    process:
        Manufacturing process key matching an entry in the process capabilities
        database (e.g. ``"cnc_milling"``, ``"grinding"``).
    functional_class:
        Functional context driving tolerance tightening.  One of the keys in
        ``FUNCTIONAL_MULTIPLIERS`` (e.g. ``"bearing_bore"``, ``"general"``).
    datum_available:
        Whether a datum reference frame is established.  Triggers a note when
        the characteristic requires a datum.
    process_db:
        Optional override for the process capabilities database.  If ``None``
        the bundled ``process_capabilities.yaml`` is loaded.

    Returns
    -------
    GeoTolResult
        Structured result with tolerance value, zone geometry, datum
        requirement, and contextual engineering notes.
    """
    key = characteristic.lower()
    if key not in CHARACTERISTICS:
        raise ValueError(
            f"Unknown ISO 1101 characteristic: '{characteristic}'. "
            f"Supported: {sorted(CHARACTERISTICS)}"
        )
    func_key = functional_class.lower()
    if func_key not in FUNCTIONAL_MULTIPLIERS:
        raise ValueError(
            f"Unknown functional class: '{functional_class}'. "
            f"Supported: {sorted(FUNCTIONAL_MULTIPLIERS)}"
        )

    entry = choose_process_entry(process, process_db)
    it_grade = _it_grade_from_entry(entry)
    char_info = CHARACTERISTICS[key]

    tol_mm = _compute_tolerance(key, feature_size_mm, it_grade, func_key)
    notes = _build_notes(char_info, func_key, it_grade, datum_available)

    return GeoTolResult(
        characteristic=key,
        category=char_info["category"],
        tolerance_mm=tol_mm,
        zone_geometry=char_info["zone_geometry"],
        requires_datum=char_info["requires_datum"],
        functional_class=func_key,
        process=process,
        it_grade=it_grade,
        notes=notes,
    )


def recommend_for_function(
    functional_class: str,
    feature_size_mm: float,
    process: str,
    datum_available: bool = True,
    process_db: Optional[Dict] = None,
) -> List[GeoTolResult]:
    """Recommend all relevant ISO 1101 characteristics for a functional context.

    Returns a list of GeoTolResult — one per characteristic in
    ``FUNCTIONAL_RECOMMENDATIONS[functional_class]`` — sorted tightest-first
    by ``tolerance_mm``.

    This is the primary entry point for automated GD&T suggestion driven by
    functional intent rather than manual characteristic selection.
    """
    func_key = functional_class.lower()
    if func_key not in FUNCTIONAL_RECOMMENDATIONS:
        raise ValueError(
            f"Unknown functional class: '{functional_class}'. "
            f"Supported: {sorted(FUNCTIONAL_RECOMMENDATIONS)}"
        )
    results = [
        recommend_geometric_tolerance(
            characteristic=c,
            feature_size_mm=feature_size_mm,
            process=process,
            functional_class=func_key,
            datum_available=datum_available,
            process_db=process_db,
        )
        for c in FUNCTIONAL_RECOMMENDATIONS[func_key]
    ]
    return sorted(results, key=lambda r: r.tolerance_mm)


def list_characteristics(category: Optional[str] = None) -> List[str]:
    """Return supported characteristic names, optionally filtered by category.

    category: one of 'form', 'orientation', 'location', 'runout', 'profile'.
    """
    if category is None:
        return sorted(CHARACTERISTICS)
    cat = category.lower()
    return sorted(k for k, v in CHARACTERISTICS.items() if v["category"] == cat)


def list_functional_classes() -> List[str]:
    """Return all supported functional class names."""
    return sorted(FUNCTIONAL_MULTIPLIERS)


# ---------------------------------------------------------------------------
# Backwards-compatibility shim — keeps any callers of the old propose_geometric_tolerance intact
# ---------------------------------------------------------------------------

def propose_geometric_tolerance(
    symbol: str,
    feature_size_mm: float,
    process: str,
    process_db: Optional[Dict] = None,
) -> Dict:
    """Thin wrapper retained for backwards compatibility.

    Prefer ``recommend_geometric_tolerance`` for new code.
    """
    result = recommend_geometric_tolerance(
        characteristic=symbol,
        feature_size_mm=feature_size_mm,
        process=process,
        functional_class="general",
        process_db=process_db,
    )
    return {"symbol": result.characteristic, "tolerance_mm": result.tolerance_mm}
