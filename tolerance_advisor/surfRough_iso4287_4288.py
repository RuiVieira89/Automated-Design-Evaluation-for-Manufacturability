"""Surface roughness tolerance advisor — ISO 4287 / ISO 4288.

ISO 4287 defines surface texture parameters (Ra, Rz, RSm, Rmr, …).
ISO 4288 defines how to select cut-off wavelengths and acceptance rules.

This module provides drawing-level tolerance advice: which parameter to
specify, what value to target based on process capability, and which
acceptance rule to invoke.  Measurement procedures are out of scope.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .helpers import choose_process_entry


# ---------------------------------------------------------------------------
# Parameter-to-function mapping (ISO 4287 parameter rationale)
# ---------------------------------------------------------------------------

_FUNCTION_PARAMETER_MAP: Dict[str, Dict[str, str]] = {
    "general": {
        "primary": "Ra",
        "secondary": "Rz",
        "rationale": (
            "Ra is the universal statistical roughness index. "
            "Add Rz to bound peak heights — two surfaces can share identical Ra "
            "while having very different peak heights."
        ),
    },
    "sealing": {
        "primary": "Rz",
        "secondary": "Ra",
        "rationale": (
            "Rz (peak-to-valley height) governs leak paths at sealing interfaces. "
            "Ra alone understates the hazard from isolated peaks."
        ),
    },
    "coating": {
        "primary": "Rz",
        "secondary": "Ra",
        "rationale": (
            "Coating adhesion depends on anchor profile depth (Rz). "
            "Ra underestimates the texture amplitude relevant to adhesion."
        ),
    },
    "sliding": {
        "primary": "Ra",
        "secondary": "Rmr",
        "rationale": (
            "Ra controls bulk roughness for sliding contacts; "
            "Rmr (bearing ratio / Abbott-Firestone) characterises the load-carrying plateau."
        ),
    },
    "friction": {
        "primary": "RSm",
        "secondary": "Ra",
        "rationale": (
            "RSm (mean spacing of profile elements) drives asperity density and "
            "lubricant film retention alongside Ra."
        ),
    },
    "lubrication": {
        "primary": "RSm",
        "secondary": "Rmr",
        "rationale": (
            "Lubricant retention depends on asperity spacing (RSm) and "
            "plateau geometry (Rmr / Abbott-Firestone)."
        ),
    },
    "bearing": {
        "primary": "Rmr",
        "secondary": "Rz",
        "rationale": (
            "Bearing and piston liner surfaces: Rmr (plateau bearing ratio) "
            "is the primary functional parameter. Rz bounds the peak height."
        ),
    },
    "contact_stress": {
        "primary": "Rz",
        "secondary": "Rq",
        "rationale": (
            "Peak heights (Rz) drive contact pressure concentrations. "
            "Rq (RMS roughness) is used in statistical contact stress models."
        ),
    },
}

# ---------------------------------------------------------------------------
# ISO 4288 cut-off wavelength table
# Rows: (Ra_min_um, Ra_max_um, lambda_c_mm)
# Used to advise which lc applies to the specified Ra value so the supplier
# measures consistently.
# ---------------------------------------------------------------------------

_LC_TABLE: List[Tuple[float, float, float]] = [
    (0.006, 0.02,  0.08),
    (0.02,  0.1,   0.25),
    (0.1,   2.0,   0.8),
    (2.0,   10.0,  2.5),
    (10.0,  80.0,  8.0),
]

# ---------------------------------------------------------------------------
# Process-specific surface-texture notes
# ---------------------------------------------------------------------------

_PROCESS_NOTES: Dict[str, str] = {
    "CNC_turning": (
        "Turned surfaces have a directional lay (along the feed direction). "
        "Specify lay direction on the drawing per ISO 1302 if it matters functionally."
    ),
    "cylindrical_grinding": (
        "Ground surfaces suit tight Ra specs. "
        "Rz/Ra ratio is typically 4-6 for ground surfaces."
    ),
    "sand_casting": (
        "Cast surfaces have high Rz relative to Ra. "
        "Specify Rz as the primary parameter; Ra alone understates peak height."
    ),
    "injection_moulding": (
        "Surface texture mirrors the mould finish. "
        "Specify the required texture on the mould, not the part, unless post-machining is planned."
    ),
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SurfaceRoughnessRecommendation:
    """Tolerance recommendation returned by recommend_surface_roughness()."""

    process: str
    function: str
    primary_parameter: str
    secondary_parameter: str
    ra_range_um: Tuple[float, float]
    rz_approx_um: float
    lambda_c_mm: float
    acceptance_rule: str
    notes: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict:
        return {
            "process": self.process,
            "function": self.function,
            "primary_parameter": self.primary_parameter,
            "secondary_parameter": self.secondary_parameter,
            "ra_range_um": self.ra_range_um,
            "rz_approx_um": self.rz_approx_um,
            "lambda_c_mm": self.lambda_c_mm,
            "acceptance_rule": self.acceptance_rule,
            "notes": self.notes,
        }

    def drawing_callout(self) -> str:
        """Return a representative ISO 1302-style drawing callout."""
        ra_val = self.ra_range_um[1]  # upper end of achievable range as the limit
        rz_val = self.rz_approx_um
        suffix = " max" if "max rule" in self.acceptance_rule else ""
        return f"Ra {ra_val:.4g}{suffix} / Rz {rz_val:.4g}"


@dataclass
class StandardRecommendation:
    """Advice on which roughness standard to use."""

    recommended_standard: str   # "ISO_4287_4288" or "ISO_25178"
    rationale: str
    notes: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def recommend_surface_roughness(
    process: str,
    function: str = "general",
    acceptance_rule: str = "16pct",
    process_db: Optional[Dict] = None,
) -> SurfaceRoughnessRecommendation:
    """Return a surface roughness tolerance recommendation for a drawing.

    Parameters
    ----------
    process:
        Manufacturing process key matching an entry in process_capabilities.yaml
        (e.g. ``'CNC_turning'``, ``'cylindrical_grinding'``).
    function:
        Surface functional purpose — one of:
        ``'general'``, ``'sealing'``, ``'coating'``, ``'sliding'``,
        ``'friction'``, ``'lubrication'``, ``'bearing'``, ``'contact_stress'``.
        Defaults to ``'general'``.
    acceptance_rule:
        ``'16pct'`` (ISO 4288 default; up to 16% of individual sampling-length
        measurements may exceed the stated limit) or ``'max'`` (every
        measurement must be below the limit; stricter, for safety-critical or
        sealing surfaces).
    process_db:
        Optional process capability dict.  Loaded from the bundled YAML if
        omitted.
    """
    entry = choose_process_entry(process, process_db)

    ra_values = entry.get("surface_roughness_ra_um")
    if ra_values is None:
        ra_values = [1.6, 3.2]
    if isinstance(ra_values, (int, float)):
        ra_values = [float(ra_values)]
    ra_range: Tuple[float, float] = (float(min(ra_values)), float(max(ra_values)))

    func_key = function.lower() if function.lower() in _FUNCTION_PARAMETER_MAP else "general"
    param_info = _FUNCTION_PARAMETER_MAP[func_key]

    ra_mid = (ra_range[0] + ra_range[1]) / 2.0
    lambda_c = _select_lambda_c(ra_mid)
    rz_approx = ra_range[1] * 4.0

    if acceptance_rule == "max":
        rule_label = "max rule (every measurement must be below the limit)"
    else:
        rule_label = "16% rule (ISO 4288 default — <=16% of measurements may exceed the limit)"

    notes: List[str] = [param_info["rationale"]]
    if process in _PROCESS_NOTES:
        notes.append(_PROCESS_NOTES[process])
    if acceptance_rule == "max":
        notes.append(
            "Max rule is significantly stricter than the default 16% rule. "
            "Reserve it for safety-critical or sealing surfaces and mark it "
            "explicitly on the drawing (ISO 1302)."
        )

    return SurfaceRoughnessRecommendation(
        process=process,
        function=func_key,
        primary_parameter=param_info["primary"],
        secondary_parameter=param_info["secondary"],
        ra_range_um=ra_range,
        rz_approx_um=rz_approx,
        lambda_c_mm=lambda_c,
        acceptance_rule=rule_label,
        notes=notes,
    )


def recommend_parameter(function: str) -> Dict[str, str]:
    """Return recommended ISO 4287 parameter(s) for a surface function.

    Parameters
    ----------
    function:
        One of the keys returned by :func:`list_surface_functions`.

    Returns
    -------
    Dict with ``'primary'``, ``'secondary'``, and ``'rationale'`` keys.

    Raises
    ------
    ValueError
        If *function* is not recognised.
    """
    key = function.lower()
    if key not in _FUNCTION_PARAMETER_MAP:
        raise ValueError(
            f"Unknown surface function '{function}'. "
            f"Choose from: {list(_FUNCTION_PARAMETER_MAP.keys())}"
        )
    return dict(_FUNCTION_PARAMETER_MAP[key])


def recommend_standard(function: str, surface_type: str = "machined") -> StandardRecommendation:
    """Advise whether ISO 4287/4288 (profile) or ISO 25178 (areal) is more appropriate.

    Parameters
    ----------
    function:
        Surface functional purpose (same keywords as :func:`recommend_surface_roughness`).
    surface_type:
        ``'machined'``, ``'additive'``, ``'isotropic'``, or ``'optical'``.
    """
    surface_key = surface_type.lower()
    func_key = function.lower()

    surface_areal: Dict[str, str] = {
        "additive": (
            "Additive-manufactured surfaces have irregular, isotropic texture. "
            "ISO 25178 (Sa, Sz, Str) provides a complete 3D characterisation."
        ),
        "isotropic": (
            "Isotropic surfaces cannot be adequately characterised by a single 2D trace. "
            "Use ISO 25178 areal parameters."
        ),
        "optical": (
            "Optical components are covered by ISO 10110, not ISO 4287/4288."
        ),
    }

    func_areal: Dict[str, str] = {
        "friction": (
            "Tribological function (friction, wear) depends on 3D texture. "
            "ISO 25178 (Sdr, Str, Vvv) is preferred for design-to-function work."
        ),
        "lubrication": (
            "Lubricant retention depends on 3D void volume (Vvv) and texture isotropy (Str). "
            "Migrate to ISO 25178 for tribological optimisation."
        ),
    }

    if surface_key in surface_areal:
        return StandardRecommendation(
            recommended_standard="ISO_25178",
            rationale=surface_areal[surface_key],
            notes=[
                "ISO 4287/4288 may still be used for contractual drawing callouts "
                "where the supplier's lab cannot perform areal measurement."
            ],
        )

    if func_key in func_areal:
        return StandardRecommendation(
            recommended_standard="ISO_25178",
            rationale=func_areal[func_key],
            notes=[
                "ISO 4287/4288 remains the universal contractual standard.",
                "Use ISO 25178 in development; ISO 4287/4288 for supplier drawing callouts.",
            ],
        )

    return StandardRecommendation(
        recommended_standard="ISO_4287_4288",
        rationale=(
            "Profile method (ISO 4287/4288) is appropriate for machined surfaces "
            "with a defined lay direction and height-based functional requirements."
        ),
        notes=[
            "Specify Ra + Rz dual constraint per ISO 1302.",
            "Explicitly state the acceptance rule (16% or max) on the drawing "
            "for safety-critical or sealing surfaces.",
        ],
    )


def list_surface_functions() -> List[str]:
    """Return all recognised surface function keywords."""
    return list(_FUNCTION_PARAMETER_MAP.keys())


def ra_to_rz(ra_um: float) -> float:
    """Approximate Ra to Rz conversion (engineering heuristic: Rz approx 4 x Ra)."""
    return ra_um * 4.0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _select_lambda_c(ra_um: float) -> float:
    """Return the ISO 4288 cut-off wavelength (mm) for a given Ra value (um)."""
    for ra_min, ra_max, lc in _LC_TABLE:
        if ra_min <= ra_um <= ra_max:
            return lc
    return _LC_TABLE[0][2] if ra_um < _LC_TABLE[0][0] else _LC_TABLE[-1][2]
