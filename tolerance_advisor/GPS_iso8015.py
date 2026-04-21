"""GPS_iso8015 — Master GPS standard implementation (ISO 8015).

ISO 8015 is the **foundational standard** for the ISO Geometrical Product
Specifications (GPS) system.  It does not define tolerance values; instead it
establishes the default interpretation rules that govern every other GPS
standard on a technical drawing.

Core principles encoded here:

  1. Principle of Independency — each GPS tolerance is fulfilled separately
     unless an explicit modifier (e.g. Envelope ⓔ) overrides the default.
  2. GPS Operators — the five-step chain (partition → extraction →
     filtration → association → evaluation) linking design intent to
     physical measurement.
  3. Duality Principle — specification operator and verification operator
     must correspond.
  4. Default Reference Conditions — 20 °C, 101 325 Pa.

GPS hierarchy implemented / planned:

  GPS_iso8015  ← This module — fundamental rules (ISO 8015)
      │
      ├── fit_iso286.py        ← ISO 286   — dimensional fits          ✓ IMPLEMENTED
      ├── linTol_iso2768.py    ← ISO 2768  — general tolerances        ✓ IMPLEMENTED
      ├── geoTol_iso1101.py    ← ISO 1101  — geometric tolerances      ✓ IMPLEMENTED
      ├── iso4287_4288.py      ← ISO 4287/4288 — surface roughness     ✓ IMPLEMENTED
      ├── [iso14405.py]        ← ISO 14405 — dimensional size specs    TODO
      ├── [iso2692.py]         ← ISO 2692  — MMC/LMC modifiers         TODO
      ├── [iso5459.py]         ← ISO 5459  — datum systems             TODO
      └── [iso1302.py]         ← ISO 1302  — surface texture indication TODO

Backwards-compatible shims for the original ``apply_independence_principle``
and ``simple_dimensioning_checks`` are retained at the bottom of this module.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, Iterable, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Reference conditions (ISO 8015 §5)
# ---------------------------------------------------------------------------

REFERENCE_TEMPERATURE_C: float = 20.0
REFERENCE_PRESSURE_PA: float = 101_325.0


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class GPSStandard(Enum):
    """Drawing standard in force — governs default interpretation rules."""
    ISO_8015 = "ISO 8015"
    ASME_Y14_5 = "ASME Y14.5"


class GPSModifier(Enum):
    """Feature-level modifiers that override default GPS interpretation rules."""
    INDEPENDENCY = "Ⓘ"    # default under ISO 8015 — explicit annotation rarely needed
    ENVELOPE = "ⓔ"         # size and form coupled at MMC (overrides independency)
    MMC = "Ⓜ"              # maximum material condition — requires ISO 2692  TODO
    LMC = "Ⓛ"              # least material condition   — requires ISO 2692  TODO
    COMBINED_ZONE = "CZ"   # pattern tolerance shares one zone
    SEPARATE_ZONE = "SZ"   # pattern tolerance uses separate zones per feature


class GPSOperatorStep(Enum):
    """The five GPS operator steps per ISO 8015 §4.3."""
    PARTITION = auto()     # identify the feature (surface, edge, axis …)
    EXTRACTION = auto()    # sample points from the physical surface
    FILTRATION = auto()    # apply spatial filter (noise removal, UPR range)
    ASSOCIATION = auto()   # fit reference geometry (best-fit cylinder, plane …)
    EVALUATION = auto()    # compare fitted geometry against tolerance zone


class FeatureType(Enum):
    """Broad feature classification used by the GPS orchestrator."""
    EXTERNAL_CYLINDER = "external_cylinder"  # shaft, pin, boss
    INTERNAL_CYLINDER = "internal_cylinder"  # bore, hole
    FLAT_SURFACE = "flat_surface"
    ANGULAR = "angular"
    THREAD = "thread"
    FREEFORM = "freeform"


# ---------------------------------------------------------------------------
# GPS Operator descriptor
# ---------------------------------------------------------------------------

@dataclass
class GPSOperator:
    """One step in the GPS operator chain."""
    step: GPSOperatorStep
    description: str
    parameters: Dict = field(default_factory=dict)


def default_operator_chain(feature_type: FeatureType) -> List[GPSOperator]:
    """Return the standard GPS operator chain for a given feature type.

    The five-step sequence is invariant per ISO 8015; the association method
    and filtration parameters vary by feature geometry.
    """
    assoc_method = {
        FeatureType.EXTERNAL_CYLINDER: "minimum circumscribed cylinder",
        FeatureType.INTERNAL_CYLINDER: "maximum inscribed cylinder",
        FeatureType.FLAT_SURFACE: "least-squares plane",
        FeatureType.ANGULAR: "least-squares plane pair",
        FeatureType.THREAD: "thread axis via best-fit helix",
        FeatureType.FREEFORM: "least-squares reference surface",
    }.get(feature_type, "least-squares reference geometry")

    return [
        GPSOperator(
            step=GPSOperatorStep.PARTITION,
            description="Identify the nominal feature and its boundaries on the workpiece.",
        ),
        GPSOperator(
            step=GPSOperatorStep.EXTRACTION,
            description="Sample discrete points from the real surface (CMM probe or optical scan).",
            parameters={"method": "CMM or optical scan", "density": "as required by tolerance magnitude"},
        ),
        GPSOperator(
            step=GPSOperatorStep.FILTRATION,
            description="Apply spatial filter to separate form from roughness/waviness components.",
            parameters={"filter_type": "Gaussian (ISO 16610-21)", "UPR": "application-specific"},
        ),
        GPSOperator(
            step=GPSOperatorStep.ASSOCIATION,
            description=f"Fit reference geometry: {assoc_method}.",
            parameters={"method": assoc_method},
        ),
        GPSOperator(
            step=GPSOperatorStep.EVALUATION,
            description="Compute deviation from nominal and compare against tolerance zone.",
        ),
    ]


# ---------------------------------------------------------------------------
# GPS Invocation (drawing title block)
# ---------------------------------------------------------------------------

@dataclass
class GPSInvocation:
    """Records which GPS standard governs a drawing and any global modifiers."""
    standard: GPSStandard = GPSStandard.ISO_8015
    title_block_text: str = "Tolerancing according to ISO 8015"
    active_modifiers: List[GPSModifier] = field(default_factory=list)

    @property
    def independency_is_default(self) -> bool:
        return self.standard == GPSStandard.ISO_8015

    @property
    def envelope_is_default(self) -> bool:
        return self.standard == GPSStandard.ASME_Y14_5


def validate_invocation(invocation: GPSInvocation) -> List[str]:
    """Return warnings about a GPS invocation.

    Checks for missing title-block text and mixed-standard conflicts.
    """
    warnings: List[str] = []
    if not invocation.title_block_text.strip():
        warnings.append(
            "Drawing title block does not declare a tolerancing standard. "
            "Add 'Tolerancing according to ISO 8015' or equivalent."
        )
    if (invocation.standard == GPSStandard.ASME_Y14_5
            and GPSModifier.ENVELOPE in invocation.active_modifiers):
        warnings.append(
            "ASME Y14.5 applies the envelope principle (Rule #1) by default; "
            "the ⓔ modifier is redundant but harmless."
        )
    if GPSModifier.MMC in invocation.active_modifiers:
        warnings.append(
            "MMC modifier (Ⓜ) requires ISO 2692 — not yet implemented in this "
            "package.  Treat as a design-intent marker only."
        )
    if GPSModifier.LMC in invocation.active_modifiers:
        warnings.append(
            "LMC modifier (Ⓛ) requires ISO 2692 — not yet implemented in this "
            "package.  Treat as a design-intent marker only."
        )
    return warnings


# ---------------------------------------------------------------------------
# Independency principle (ISO 8015 §6.1)
# ---------------------------------------------------------------------------

@dataclass
class IndependencyResult:
    """Result of an independency / envelope check between size and form tolerance."""
    modifier: GPSModifier
    size_tolerance_mm: float
    form_tolerance_mm: float
    independent: bool               # True → each tolerance fulfilled separately
    envelope_active: bool           # True → form bounded by size at MMC
    effective_form_limit_mm: float
    notes: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict:
        return {
            "modifier": self.modifier.value,
            "size_tolerance_mm": self.size_tolerance_mm,
            "form_tolerance_mm": self.form_tolerance_mm,
            "independent": self.independent,
            "envelope_active": self.envelope_active,
            "effective_form_limit_mm": self.effective_form_limit_mm,
            "notes": self.notes,
        }


def check_independency(
    size_tolerance_mm: float,
    form_tolerance_mm: float,
    modifier: GPSModifier = GPSModifier.INDEPENDENCY,
    invocation: Optional[GPSInvocation] = None,
) -> IndependencyResult:
    """Evaluate the independency principle for a size / form tolerance pair.

    Under ISO 8015 (independency default)
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    Size and form are checked **independently**.  A feature can satisfy its
    size tolerance while violating its form tolerance and vice versa — both
    must be met, but they do not constrain each other.

    Under the Envelope requirement (ⓔ modifier)
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    The feature must lie within a geometrically perfect envelope at its
    Maximum Material Condition (MMC) size.  The effective form limit is
    therefore capped at the size tolerance — the feature cannot have more
    form error than the size tolerance allows at MMC.

    Under ASME Y14.5 (Rule #1)
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~
    Equivalent to the envelope requirement — size and form are coupled by
    default.  Use ``GPSInvocation(standard=GPSStandard.ASME_Y14_5)`` to
    activate this behaviour globally.
    """
    std = invocation.standard if invocation else GPSStandard.ISO_8015
    envelope_active = (
        modifier == GPSModifier.ENVELOPE
        or std == GPSStandard.ASME_Y14_5
    )

    notes: List[str] = []

    if envelope_active:
        effective_form_limit = min(form_tolerance_mm, size_tolerance_mm)
        notes.append(
            "Envelope requirement (ⓔ) active: the feature must lie within a "
            "perfect-form envelope at MMC size.  Form error is capped at the "
            f"size tolerance ({size_tolerance_mm} mm)."
        )
        if form_tolerance_mm > size_tolerance_mm:
            notes.append(
                f"Specified form tolerance ({form_tolerance_mm} mm) exceeds size "
                f"tolerance ({size_tolerance_mm} mm) — envelope clips effective "
                f"form limit to {size_tolerance_mm} mm."
            )
    else:
        effective_form_limit = form_tolerance_mm
        notes.append(
            "Independency principle applies (ISO 8015 default): size and form "
            "tolerances are fulfilled separately.  Add ⓔ modifier to couple "
            "them for mating fits."
        )
        if std == GPSStandard.ASME_Y14_5:
            notes.append(
                "WARNING: drawing declares ASME Y14.5 but INDEPENDENCY modifier "
                "was passed explicitly.  ASME Rule #1 (envelope) is the Y14.5 "
                "default — verify modifier intent."
            )

    return IndependencyResult(
        modifier=modifier,
        size_tolerance_mm=size_tolerance_mm,
        form_tolerance_mm=form_tolerance_mm,
        independent=not envelope_active,
        envelope_active=envelope_active,
        effective_form_limit_mm=effective_form_limit,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# GPS Feature specification (master orchestrator)
# ---------------------------------------------------------------------------

@dataclass
class GPSFeatureSpec:
    """Complete GPS specification for a single feature.

    Aggregates outputs from all implemented GPS sub-standards and records
    the operator chain and modifier governing conformance assessment.
    """
    feature_id: str
    feature_type: FeatureType
    nominal_size_mm: float
    process: str
    functional_class: str
    modifier: GPSModifier
    invocation: GPSInvocation

    # Sub-standard outputs (None when standard not applicable or not yet implemented)
    size_tolerance: Optional[Dict] = None        # ISO 286
    general_tolerance: Optional[Dict] = None     # ISO 2768
    geometric_tolerances: List = field(default_factory=list)  # ISO 1101
    surface_texture: Optional[Dict] = None       # ISO 4287/4288
    independency: Optional[IndependencyResult] = None

    # GPS operator chain
    operator_chain: List[GPSOperator] = field(default_factory=list)

    # Reference conditions (ISO 8015 §5)
    reference_temperature_c: float = REFERENCE_TEMPERATURE_C
    reference_pressure_pa: float = REFERENCE_PRESSURE_PA

    # Accumulated warnings from all sub-standards
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict:
        return {
            "feature_id": self.feature_id,
            "feature_type": self.feature_type.value,
            "nominal_size_mm": self.nominal_size_mm,
            "process": self.process,
            "functional_class": self.functional_class,
            "modifier": self.modifier.value,
            "invocation": {
                "standard": self.invocation.standard.value,
                "title_block_text": self.invocation.title_block_text,
            },
            "size_tolerance": self.size_tolerance,
            "general_tolerance": self.general_tolerance,
            "geometric_tolerances": [
                r.as_dict() if hasattr(r, "as_dict") else r
                for r in self.geometric_tolerances
            ],
            "surface_texture": self.surface_texture,
            "independency": self.independency.as_dict() if self.independency else None,
            "reference_temperature_c": self.reference_temperature_c,
            "reference_pressure_pa": self.reference_pressure_pa,
            "warnings": self.warnings,
        }


def gps_specify_feature(
    feature_id: str,
    feature_type: FeatureType,
    nominal_size_mm: float,
    process: str,
    functional_class: str = "general",
    modifier: GPSModifier = GPSModifier.INDEPENDENCY,
    invocation: Optional[GPSInvocation] = None,
    process_db: Optional[Dict] = None,
) -> GPSFeatureSpec:
    """Build a complete GPS specification for a feature by orchestrating all
    implemented GPS sub-standards under the ISO 8015 framework.

    Parameters
    ----------
    feature_id:
        Label identifying the feature on the drawing (e.g. ``"bore_A"``).
    feature_type:
        Feature geometry classification (``FeatureType`` enum).
    nominal_size_mm:
        Nominal size in mm — diameter for cylinders, span for planar features.
    process:
        Manufacturing process key matching the bundled process capabilities DB.
    functional_class:
        Functional context for ISO 1101 recommendation (e.g. ``"bearing_bore"``,
        ``"sealing_surface"``).
    modifier:
        GPS modifier governing independency / envelope behaviour for this feature.
    invocation:
        GPS drawing invocation.  Defaults to ISO 8015 with independency as the
        default rule.
    process_db:
        Optional override for the process capabilities database.

    Returns
    -------
    GPSFeatureSpec
        Fully populated specification aggregating outputs from every implemented
        sub-standard and the GPS operator chain.
    """
    if invocation is None:
        invocation = GPSInvocation()

    # Pre-load DB once so all sub-standard calls receive a concrete dict.
    # fit_iso286.propose_tolerance requires a non-None process_db.
    if process_db is None:
        from .helpers import load_process_capabilities
        try:
            process_db = load_process_capabilities()
        except Exception as exc:
            process_db = {}

    warnings: List[str] = list(validate_invocation(invocation))

    spec = GPSFeatureSpec(
        feature_id=feature_id,
        feature_type=feature_type,
        nominal_size_mm=nominal_size_mm,
        process=process,
        functional_class=functional_class,
        modifier=modifier,
        invocation=invocation,
        operator_chain=default_operator_chain(feature_type),
        warnings=warnings,
    )

    # --- ISO 286 — dimensional fit (cylindrical features only) ---
    if feature_type in {FeatureType.EXTERNAL_CYLINDER, FeatureType.INTERNAL_CYLINDER}:
        try:
            from .fit_iso286 import propose_tolerance
            spec.size_tolerance = propose_tolerance(nominal_size_mm, process, process_db)
        except Exception as exc:
            spec.warnings.append(f"ISO 286 (size tolerance): {exc}")

    # --- ISO 2768 — general tolerance and title-block class ---
    try:
        from .linTol_iso2768 import propose_general_tolerance, recommend_title_block
        spec.general_tolerance = propose_general_tolerance(
            nominal_size_mm, process, process_db
        )
        tb = recommend_title_block(process, process_db)
        # Only include the scope notes (index 0 and 1); suppress the coarse-
        # class stack-up note from polluting the GPS spec warnings.
        spec.warnings.extend(tb.notes[:2])
    except Exception as exc:
        spec.warnings.append(f"ISO 2768 (general tolerance): {exc}")

    # --- ISO 1101 — geometric tolerances ---
    try:
        from .geoTol_iso1101 import recommend_for_function
        spec.geometric_tolerances = recommend_for_function(
            functional_class=functional_class,
            feature_size_mm=nominal_size_mm,
            process=process,
            process_db=process_db,
        )
    except Exception as exc:
        spec.warnings.append(f"ISO 1101 (geometric tolerances): {exc}")

    # --- ISO 4287/4288 — surface roughness values ---
    try:
        from .iso4287_4288 import propose_surface_roughness
        spec.surface_texture = propose_surface_roughness(
            process, nominal_size_mm, process_db
        )
    except Exception as exc:
        spec.warnings.append(f"ISO 4287/4288 (surface roughness): {exc}")

    # --- ISO 8015 — independency / envelope principle check ---
    if spec.size_tolerance and spec.geometric_tolerances:
        size_tol_mm = spec.size_tolerance.get("tolerance_mm", 0.0)
        form_tols = [
            r.tolerance_mm
            for r in spec.geometric_tolerances
            if hasattr(r, "category") and r.category == "form"
        ]
        if form_tols:
            spec.independency = check_independency(
                size_tolerance_mm=size_tol_mm,
                form_tolerance_mm=min(form_tols),
                modifier=modifier,
                invocation=invocation,
            )

    # --- TODO: ISO 14405 — dimensional size specifications ---
    # ISO 14405 governs how linear sizes (diameters, widths, etc.) are
    # specified and measured, including two-point, least-squares, and
    # circumscribed/inscribed size operators.  Complements ISO 8015 and
    # overrides ISO 286 for non-fit-system size specifications.
    # Implement when iso14405.py is added to the package.

    # --- TODO: ISO 2692 — maximum / least material requirements ---
    # ISO 2692 defines the MMC (Ⓜ) and LMC (Ⓛ) modifiers that allow
    # geometric tolerance to grow as features depart from their critical size.
    # Required to fully implement GPSModifier.MMC and GPSModifier.LMC above.
    # Implement when iso2692.py is added to the package.

    # --- TODO: ISO 5459 — datum systems ---
    # ISO 5459 defines how datums are physically established from real
    # surfaces (primary, secondary, tertiary) and how datum reference frames
    # are constructed.  This governs fixturing for machining and CMM inspection.
    # Implement when iso5459.py is added to the package.

    # --- TODO: ISO 1302 — surface texture indication on drawings ---
    # ISO 1302 defines the graphical symbols used to annotate surface texture
    # requirements on drawings and in MBD/PMI.  Values come from ISO 4287/4288
    # (already implemented above); ISO 1302 adds the annotation layer.
    # Implement when iso1302.py is added to the package.

    return spec


# ---------------------------------------------------------------------------
# Dimensioning sanity checks (ISO 8015 §7 — general dimensioning rules)
# ---------------------------------------------------------------------------

def dimensioning_checks(
    dimensions: Iterable[Tuple[str, float, float]],
) -> List[str]:
    """Check a set of dimensions against ISO 8015 general rules.

    Parameters
    ----------
    dimensions:
        Iterable of ``(name, nominal_mm, tolerance_mm)`` tuples.

    Returns
    -------
    List[str]
        Human-readable warnings; empty list if all checks pass.
    """
    warnings: List[str] = []
    for name, nominal, tol in dimensions:
        if nominal <= 0:
            warnings.append(
                f"'{name}': nominal ≤ 0 ({nominal} mm) — "
                "ISO 8015 requires a positive nominal value."
            )
        if tol <= 0:
            warnings.append(
                f"'{name}': tolerance ≤ 0 ({tol} mm) — "
                "a zero or negative tolerance is physically meaningless."
            )
        elif tol > nominal:
            warnings.append(
                f"'{name}': tolerance ({tol} mm) exceeds nominal ({nominal} mm) — "
                "verify intent; this is unusual for machined features."
            )
    return warnings


# ---------------------------------------------------------------------------
# Backwards-compatibility shims (original iso8015.py public API)
# ---------------------------------------------------------------------------

def apply_independence_principle(
    base_tolerance_mm: float,
    modifiers: Optional[Iterable[float]] = None,
) -> float:
    """Combine a base tolerance with multiplicative modifiers.

    Retained for backwards compatibility with the original iso8015.py API.
    For correct ISO 8015 independency modelling use ``check_independency``.
    """
    if modifiers is None:
        return base_tolerance_mm
    values = [base_tolerance_mm]
    for m in modifiers:
        values.append(base_tolerance_mm * float(m))
    return max(values)


def simple_dimensioning_checks(
    dimensions: Iterable[Tuple[str, float, float]],
) -> List[str]:
    """Alias of ``dimensioning_checks`` retained for backwards compatibility."""
    return dimensioning_checks(dimensions)
