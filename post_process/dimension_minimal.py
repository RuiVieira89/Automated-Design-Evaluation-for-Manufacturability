"""Minimal dimension set for 2D drawing representation.

Takes a ShapeDimensions (from shape_dimension.py) and a manufacturing process,
and returns the fewest dimensions needed to fully define the part in a 2D
engineering drawing, with tolerances derived from the process IT grade.

Process dependence (from process_capabilities.yaml)
----------------------------------------------------
Process class is inferred from the typical IT grade:

  fine   (IT ≤ 7)  : cylindrical grinding, honing, lapping, boring, reaming, EDM
  medium (IT 8–11) : CNC turning/milling, drilling, die casting, investment casting
  coarse (IT ≥ 12) : sand casting, hot forging, FDM, SLS, stamping

Rules per class
---------------
  coarse  — overall envelope only; cylinders above 2× min_feature_size;
             wall thickness only when it falls below the manufacturing risk
             threshold; no position dimensions (general tolerance covers them).
  medium  — overall + all in-range cylinders with position (X, Y from datum);
             thin-wall check at 15% of minimum principal dimension.
  fine    — all of the above plus every wall thickness, all cylinder positions,
             and up to 3 additional span dimensions.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from .shape_dimension import CylindricalFeature, ShapeDimensions, SolidDimensions

# ---------------------------------------------------------------------------
# Tolerance computation — pure Python, no OCC needed
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tolerance_advisor.fit_iso286 import fundamental_tolerance
from tolerance_advisor.helpers import choose_process_entry, load_process_capabilities


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_EPSILON = 1e-6

# Fraction of the minimum principal dimension below which a wall is flagged
_WALL_THIN_FRACTION: Dict[str, float] = {
    "fine":   0.0,    # always include every wall thickness
    "medium": 0.15,
    "coarse": 0.0,    # controlled by absolute min_feature threshold instead
}

# Maximum additional span entries per process class
_MAX_SPANS: Dict[str, int] = {"fine": 3, "medium": 2, "coarse": 1}

# ISO 2768 title-block note by IT grade
def _general_tol_note(it_grade_int: int) -> str:
    if it_grade_int <= 6:
        return "ISO 2768-fH  (non-annotated features)"
    if it_grade_int <= 8:
        return "ISO 2768-mK  (non-annotated features)"
    if it_grade_int <= 11:
        return "ISO 2768-cK  (non-annotated features)"
    if it_grade_int <= 13:
        return "ISO 2768-cL  (non-annotated features)"
    return "ISO 2768-vL  (non-annotated features)"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class DimensionEntry:
    """One dimension in the minimal drawing set.

    Attributes
    ----------
    kind:
        Category of the dimension:
        ``"length"``, ``"width"``, ``"height"``   — overall envelope
        ``"diameter"``, ``"depth"``                — cylindrical feature
        ``"position_x"``, ``"position_y"``,
        ``"position_z"``                           — cylinder centre from datum edge
        ``"wall_thickness"``                       — gap between parallel planes
        ``"span"``                                 — additional planar extent
    nominal_mm:
        Nominal value in millimetres.
    tolerance_mm:
        Half-band tolerance (±) derived from the process IT grade.
    it_grade:
        IT grade used for the tolerance, e.g. ``"IT8"``.
    description:
        Human-readable annotation.
    solid_id:
        Index of the parent solid.
    face_ids:
        Face indices that define this dimension.
    priority:
        ``"critical"`` — near or beyond process capability;
        ``"important"`` — primary drawing dimension;
        ``"informational"`` — secondary or derived.
    """

    kind: str
    nominal_mm: float
    tolerance_mm: float
    it_grade: str
    description: str
    solid_id: int
    face_ids: List[int]
    priority: str = "important"

    def drawing_annotation(self) -> str:
        """Return a concise drawing annotation string."""
        prefix = "Ø" if self.kind == "diameter" else ""
        return f"{prefix}{self.nominal_mm:.4g} ±{self.tolerance_mm:.4g}"

    def as_dict(self) -> Dict:
        return {
            "kind": self.kind,
            "nominal_mm": self.nominal_mm,
            "tolerance_mm": self.tolerance_mm,
            "it_grade": self.it_grade,
            "annotation": self.drawing_annotation(),
            "description": self.description,
            "solid_id": self.solid_id,
            "face_ids": self.face_ids,
            "priority": self.priority,
        }


@dataclass
class MinimalDimensionSet:
    """The minimal drawing dimension set for one solid.

    Attributes
    ----------
    solid_id:
        Index into ``ShapeDimensions.solids``.
    process:
        Manufacturing process key.
    it_grade:
        Typical IT grade for the process.
    process_class:
        ``"fine"``, ``"medium"``, or ``"coarse"``.
    dimensions:
        Ordered list of :class:`DimensionEntry` — overall first, then
        cylindrical features, walls, spans.
    general_tolerance_note:
        ISO 2768 title-block recommendation for non-annotated features.
    warnings:
        Process capability violations or manufacturability concerns.
    """

    solid_id: int
    process: str
    it_grade: str
    process_class: str
    dimensions: List[DimensionEntry]
    general_tolerance_note: str
    warnings: List[str] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    def critical(self) -> List[DimensionEntry]:
        return [d for d in self.dimensions if d.priority == "critical"]

    def by_kind(self, kind: str) -> List[DimensionEntry]:
        return [d for d in self.dimensions if d.kind == kind]

    def count(self) -> int:
        return len(self.dimensions)

    def as_dict(self) -> Dict:
        return {
            "solid_id": self.solid_id,
            "process": self.process,
            "it_grade": self.it_grade,
            "process_class": self.process_class,
            "dimension_count": self.count(),
            "general_tolerance_note": self.general_tolerance_note,
            "dimensions": [d.as_dict() for d in self.dimensions],
            "warnings": self.warnings,
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def minimal_dimensions(
    shape_dims: ShapeDimensions,
    process: str,
    process_db: Optional[Dict] = None,
) -> List[MinimalDimensionSet]:
    """Return the minimal drawing dimension set for every solid.

    Parameters
    ----------
    shape_dims:
        Output of :func:`~post_process.shape_dimension.infer_dimensions`.
    process:
        Manufacturing process key (must exist in *process_db*).
    process_db:
        Optional process capability dict; loaded from the bundled YAML if
        omitted.

    Returns
    -------
    List[MinimalDimensionSet]
        One entry per solid, in solid_id order.
    """
    if process_db is None:
        process_db = load_process_capabilities()
    return [
        minimal_solid_dimensions(sd, process, process_db)
        for sd in shape_dims.solids
    ]


def minimal_solid_dimensions(
    solid_dims: SolidDimensions,
    process: str,
    process_db: Optional[Dict] = None,
) -> MinimalDimensionSet:
    """Return the minimal drawing dimension set for one solid.

    Parameters
    ----------
    solid_dims:
        Output of :func:`~post_process.shape_dimension.infer_solid_dimensions`.
    process:
        Manufacturing process key.
    process_db:
        Optional process capability dict; loaded from the bundled YAML if
        omitted.
    """
    if process_db is None:
        process_db = load_process_capabilities()

    entry = choose_process_entry(process, process_db)
    it_grade = entry.get("typical_it_grade", "IT10")
    it_int = _it_int(it_grade)
    proc_class = _classify(it_int)
    min_feat = float(entry.get("min_feature_size_mm", 0.5))
    dim_range = entry.get("dimensional_range_mm", [0, 10_000])
    dim_min, dim_max = float(dim_range[0]), float(dim_range[1])

    warnings: List[str] = []
    dimensions: List[DimensionEntry] = []
    sid = solid_dims.solid_id

    # ------------------------------------------------------------------
    # 1. Overall dimensions (always included)
    # ------------------------------------------------------------------
    _add_overall(dimensions, solid_dims, it_grade, proc_class,
                 dim_min, dim_max, min_feat, warnings)

    # ------------------------------------------------------------------
    # 2. Cylindrical features
    # ------------------------------------------------------------------
    _add_cylinders(dimensions, solid_dims, it_grade, proc_class,
                   min_feat, dim_min, dim_max, warnings)

    # ------------------------------------------------------------------
    # 3. Wall thicknesses
    # ------------------------------------------------------------------
    _add_walls(dimensions, solid_dims, it_grade, proc_class,
               min_feat, warnings)

    # ------------------------------------------------------------------
    # 4. Additional spans (planar groups not covered by overall dims)
    # ------------------------------------------------------------------
    _add_spans(dimensions, solid_dims, it_grade, proc_class)

    return MinimalDimensionSet(
        solid_id=sid,
        process=process,
        it_grade=it_grade,
        process_class=proc_class,
        dimensions=dimensions,
        general_tolerance_note=_general_tol_note(it_int),
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Internal — building blocks
# ---------------------------------------------------------------------------

def _add_overall(
    out: List[DimensionEntry],
    sd: SolidDimensions,
    it_grade: str,
    proc_class: str,
    dim_min: float,
    dim_max: float,
    min_feat: float,
    warnings: List[str],
) -> None:
    for kind, nominal in (
        ("length", sd.length),
        ("width",  sd.width),
        ("height", sd.height),
    ):
        if nominal < _EPSILON:
            continue
        tol = _tol(nominal, it_grade)
        priority = _overall_priority(nominal, dim_min, dim_max, min_feat, warnings, kind)
        out.append(DimensionEntry(
            kind=kind,
            nominal_mm=nominal,
            tolerance_mm=tol,
            it_grade=it_grade,
            description=f"Overall {kind}",
            solid_id=sd.solid_id,
            face_ids=[],
            priority=priority,
        ))


def _add_cylinders(
    out: List[DimensionEntry],
    sd: SolidDimensions,
    it_grade: str,
    proc_class: str,
    min_feat: float,
    dim_min: float,
    dim_max: float,
    warnings: List[str],
) -> None:
    if not sd.cylinders:
        return

    cylinders = sorted(sd.cylinders, key=lambda c: c.area, reverse=True)

    # Diameter threshold by process class
    if proc_class == "coarse":
        diam_threshold = min_feat * 2.0
    else:
        diam_threshold = min_feat

    seen_diameters: List[float] = []

    for cyl in cylinders:
        d = cyl.diameter_est
        h = cyl.height_est

        if d < diam_threshold:
            warnings.append(
                f"Solid {sd.solid_id}: cylindrical feature Ø{d:.3g} mm is below "
                f"process minimum feature size ({diam_threshold:.3g} mm) — "
                f"review manufacturability."
            )
            priority_d = "critical"
        elif d > dim_max:
            priority_d = "critical"
        else:
            priority_d = "important" if not seen_diameters else "informational"

        # Deduplicate diameter specification — same nominal if within IT tolerance
        it_tol = _tol(max(d, 1.0), it_grade)
        duplicate = any(abs(d - prev) <= 2 * it_tol for prev in seen_diameters)

        if not duplicate:
            seen_diameters.append(d)
            out.append(DimensionEntry(
                kind="diameter",
                nominal_mm=d,
                tolerance_mm=it_tol,
                it_grade=it_grade,
                description=f"Ø{d:.4g} cylindrical feature",
                solid_id=sd.solid_id,
                face_ids=[cyl.face_id],
                priority=priority_d,
            ))

        # Depth / height dimension — always per-feature (not deduplicated)
        out.append(DimensionEntry(
            kind="depth",
            nominal_mm=h,
            tolerance_mm=_tol(max(h, 1.0), it_grade),
            it_grade=it_grade,
            description=f"Depth of Ø{d:.4g} feature",
            solid_id=sd.solid_id,
            face_ids=[cyl.face_id],
            priority="important",
        ))

        # Position dimensions — medium and fine only
        if proc_class != "coarse":
            bb = sd.bounding_box
            cx, cy, cz = cyl.center
            axis = _cylinder_axis(cyl)

            # Emit the two positional coordinates in the plane perpendicular to axis
            coords = [
                ("position_x", cx - bb[0], "X from left datum"),
                ("position_y", cy - bb[1], "Y from front datum"),
                ("position_z", cz - bb[2], "Z from base datum"),
            ]
            for kind, pos, desc in coords:
                if kind == f"position_{axis}":
                    continue  # skip the axis direction
                out.append(DimensionEntry(
                    kind=kind,
                    nominal_mm=pos,
                    tolerance_mm=_tol(max(pos, 1.0), it_grade),
                    it_grade=it_grade,
                    description=f"{desc} for Ø{d:.4g}",
                    solid_id=sd.solid_id,
                    face_ids=[cyl.face_id],
                    priority="important",
                ))


def _add_walls(
    out: List[DimensionEntry],
    sd: SolidDimensions,
    it_grade: str,
    proc_class: str,
    min_feat: float,
    warnings: List[str],
) -> None:
    if not sd.wall_thicknesses:
        return

    min_principal = min(sd.length, sd.width, sd.height)
    thin_threshold = (
        min_principal * _WALL_THIN_FRACTION[proc_class]
        if proc_class != "coarse"
        else min_feat * 1.5
    )

    for wt in sd.wall_thicknesses:
        t = wt.thickness_mm
        is_thin = t < thin_threshold or t < min_feat
        should_include = (
            proc_class == "fine"
            or is_thin
        )
        if not should_include:
            continue

        priority = "critical" if t < min_feat else ("important" if is_thin else "informational")
        if t < min_feat:
            warnings.append(
                f"Solid {sd.solid_id}: wall thickness {t:.3g} mm is below "
                f"process minimum feature size ({min_feat:.3g} mm)."
            )

        out.append(DimensionEntry(
            kind="wall_thickness",
            nominal_mm=t,
            tolerance_mm=_tol(max(t, 1.0), it_grade),
            it_grade=it_grade,
            description=f"Wall thickness between faces {wt.face_ids[0]}–{wt.face_ids[1]}",
            solid_id=sd.solid_id,
            face_ids=list(wt.face_ids),
            priority=priority,
        ))


def _add_spans(
    out: List[DimensionEntry],
    sd: SolidDimensions,
    it_grade: str,
    proc_class: str,
) -> None:
    max_spans = _MAX_SPANS[proc_class]
    overall_dims = {sd.length, sd.width, sd.height}
    added = 0

    for pg in sd.plane_groups:
        if added >= max_spans:
            break
        span = pg.span
        if span < _EPSILON:
            continue
        # Skip if the span is already captured by an overall dimension
        if any(abs(span - d) / max(d, _EPSILON) < 0.05 for d in overall_dims):
            continue

        out.append(DimensionEntry(
            kind="span",
            nominal_mm=span,
            tolerance_mm=_tol(max(span, 1.0), it_grade),
            it_grade=it_grade,
            description=f"Planar extent along normal {_fmt_normal(pg.normal)}",
            solid_id=sd.solid_id,
            face_ids=pg.face_ids,
            priority="informational",
        ))
        added += 1


# ---------------------------------------------------------------------------
# Internal — small helpers
# ---------------------------------------------------------------------------

def _it_int(it_grade: str) -> int:
    return int(it_grade.upper().replace("IT", "").strip())


def _classify(it_int: int) -> str:
    if it_int <= 7:
        return "fine"
    if it_int <= 11:
        return "medium"
    return "coarse"


def _tol(nominal_mm: float, it_grade: str) -> float:
    """IT tolerance in mm, clamped to the 1–500 mm supported range."""
    clamped = max(1.0, min(500.0, nominal_mm))
    try:
        return fundamental_tolerance(clamped, it_grade)
    except (ValueError, KeyError):
        # Fallback: 0.1% of nominal
        return round(nominal_mm * 0.001, 6)


def _overall_priority(
    nominal: float,
    dim_min: float,
    dim_max: float,
    min_feat: float,
    warnings: List[str],
    kind: str,
) -> str:
    if nominal > dim_max:
        warnings.append(
            f"Overall {kind} {nominal:.4g} mm exceeds process dimensional "
            f"range (max {dim_max:.4g} mm)."
        )
        return "critical"
    if nominal < dim_min and dim_min > 0:
        warnings.append(
            f"Overall {kind} {nominal:.4g} mm is below process dimensional "
            f"range (min {dim_min:.4g} mm)."
        )
        return "critical"
    return "important"


def _cylinder_axis(cyl: CylindricalFeature) -> str:
    """Return the cylinder axis letter via the CylindricalFeature.axis property."""
    return cyl.axis


def _fmt_normal(n: Tuple[float, float, float]) -> str:
    return f"({n[0]:+.2f}, {n[1]:+.2f}, {n[2]:+.2f})"


__all__ = [
    "minimal_dimensions",
    "minimal_solid_dimensions",
    "MinimalDimensionSet",
    "DimensionEntry",
]
