"""Fillet-radius gatherer for NormalizedShape output.

Scans every solid in a :class:`~post_process.shape_normalizer.NormalizedShape`
for cylindrical faces and classifies each one by its **angular sweep**:

``excluded``
    Full 360° cylinders — holes, bores, shafts.  These are not fillets
    and are omitted from the returned candidates.

``fillet``
    Cylinders whose angular sweep is approximately 90°
    (within ``fillet_angle_tol_pct`` percent, default ±5 %).
    These are almost certainly concave or convex fillets between two
    planar walls.  They are highlighted explicitly.

``partial``
    All other partial cylinders (e.g., 45°, 120°, 180°).  The exact
    angle is recorded so the caller can inspect or filter further.

The two inputs are both produced by :mod:`post_process.shape_normalizer`:

.. code-block:: python

    from load_cad.step_reader import read_step_single
    from post_process.shape_normalizer import normalize_shape, extract_solids
    from post_process.dimensions.dimension_gather_radiusFillet import gather_fillets

    compound   = read_step_single("part.step")
    normalized = normalize_shape(compound)
    solids     = extract_solids(compound)
    result     = gather_fillets(normalized, solids)

Every :class:`CylinderFeature` carries ``(solid_id, face_id)`` that map
directly back into the ``NormalizedShape``::

    solid_data = normalized.solids[feature.solid_id]
    face_data  = solid_data.faces[feature.face_id]
    neighbours = solid_data.adjacency[feature.face_id]
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Tuple

_OCC_AVAILABLE = False
try:
    from OCC.Core.BRepAdaptor import BRepAdaptor_Surface
    from OCC.Core.BRepTools import breptools
    from OCC.Core.GeomAbs import GeomAbs_Cylinder
    from OCC.Core.TopAbs import TopAbs_FACE
    from OCC.Core.TopExp import TopExp_Explorer
    from OCC.Core.TopTools import TopTools_IndexedMapOfShape
    from OCC.Core.TopoDS import TopoDS_Solid, topods
    from post_process.shape_normalizer import NormalizedShape, SolidData
    _OCC_AVAILABLE = True
except ImportError:
    pass

_TWO_PI = 2.0 * math.pi

# Angular tolerance used to detect a "full circle" when the U-parameter
# range is just below 2π due to floating-point or seam representation.
_SEAM_TOL_RAD = math.radians(0.5)


# ---------------------------------------------------------------------------
# Classification enum
# ---------------------------------------------------------------------------

class CylinderKind(str, Enum):
    """Angular-sweep classification of a cylindrical face."""

    EXCLUDED = "excluded"
    """Full 360° cylinder (hole, bore, shaft) — not a fillet."""

    FILLET = "fillet"
    """≈90° cylinder — highly likely a fillet between two walls."""

    PARTIAL = "partial"
    """Partial cylinder at any other angle — angle recorded for inspection."""


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CylinderFeature:
    """One classified cylindrical face.

    Attributes
    ----------
    solid_id:
        Index into ``NormalizedShape.solids``.  Use
        ``normalized.solids[solid_id]`` to retrieve the full
        :class:`~post_process.shape_normalizer.SolidData`.
    face_id:
        Index into ``NormalizedShape.solids[solid_id].faces``.  Use
        ``normalized.solids[solid_id].faces[face_id]`` to retrieve the
        full :class:`~post_process.shape_normalizer.FaceData` (area,
        centre, bounding box …).
    kind:
        Angular-sweep classification (see :class:`CylinderKind`).
    radius_mm:
        Cylinder radius in mm.
    angle_deg:
        Angular sweep of this face in degrees.
        360° → full hole; ≈90° → fillet; other → partial cylinder.
    axis_direction:
        Unit vector along the cylinder's central axis ``(dx, dy, dz)``.
    axis_location:
        A point on the cylinder's central axis ``(x, y, z)`` in mm.
    center:
        Centre of mass of the face ``(x, y, z)`` in mm.
        Copied from :attr:`~post_process.shape_normalizer.FaceData.center`.
    area:
        Surface area of the face in mm².
        Copied from :attr:`~post_process.shape_normalizer.FaceData.area`.
    adjacent_face_ids:
        Face IDs (within the same solid) that share an edge with this
        face.  Retrieved from the solid's adjacency graph.
    """

    solid_id: int
    face_id: int
    kind: CylinderKind
    radius_mm: float
    angle_deg: float
    axis_direction: Tuple[float, float, float]
    axis_location: Tuple[float, float, float]
    center: Tuple[float, float, float]
    area: float
    adjacent_face_ids: List[int] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "solid_id":         self.solid_id,
            "face_id":          self.face_id,
            "kind":             self.kind.value,
            "radius_mm":        self.radius_mm,
            "angle_deg":        self.angle_deg,
            "axis_direction":   self.axis_direction,
            "axis_location":    self.axis_location,
            "center":           self.center,
            "area":             self.area,
            "adjacent_face_ids": self.adjacent_face_ids,
        }


@dataclass
class SolidFilletResult:
    """Fillet analysis for one solid.

    Attributes
    ----------
    solid_id:
        Index into ``NormalizedShape.solids``.
    fillets:
        Cylindrical faces classified as ``fillet`` (≈90°).
    partials:
        Cylindrical faces classified as ``partial`` (other angles).
    excluded_count:
        Number of full 360° cylindrical faces that were excluded.
    """

    solid_id: int
    fillets: List[CylinderFeature] = field(default_factory=list)
    partials: List[CylinderFeature] = field(default_factory=list)
    excluded_count: int = 0

    @property
    def all_candidates(self) -> List[CylinderFeature]:
        """All non-excluded cylindrical faces (fillets + partials)."""
        return self.fillets + self.partials

    def as_dict(self) -> dict:
        return {
            "solid_id":      self.solid_id,
            "fillets":       [f.as_dict() for f in self.fillets],
            "partials":      [p.as_dict() for p in self.partials],
            "excluded_count": self.excluded_count,
        }


@dataclass
class FilletGatherResult:
    """Full fillet analysis for all solids in a :class:`~post_process.shape_normalizer.NormalizedShape`.

    Attributes
    ----------
    solids:
        One :class:`SolidFilletResult` per solid, in the same order as
        ``NormalizedShape.solids``.
    fillet_angle_tol_pct:
        Percentage tolerance applied to the 90° fillet classification.
    full_circle_tol_deg:
        Degree tolerance applied to the 360° exclusion.
    """

    solids: List[SolidFilletResult]
    fillet_angle_tol_pct: float = 5.0
    full_circle_tol_deg: float = 2.0

    @property
    def total_fillets(self) -> int:
        return sum(len(s.fillets) for s in self.solids)

    @property
    def total_partials(self) -> int:
        return sum(len(s.partials) for s in self.solids)

    @property
    def total_excluded(self) -> int:
        return sum(s.excluded_count for s in self.solids)

    @property
    def all_fillets(self) -> List[CylinderFeature]:
        """All fillet candidates across every solid."""
        return [f for s in self.solids for f in s.fillets]

    @property
    def all_partials(self) -> List[CylinderFeature]:
        """All partial-cylinder candidates across every solid."""
        return [p for s in self.solids for p in s.partials]

    def as_dict(self) -> dict:
        return {
            "fillet_angle_tol_pct": self.fillet_angle_tol_pct,
            "full_circle_tol_deg":  self.full_circle_tol_deg,
            "total_fillets":        self.total_fillets,
            "total_partials":       self.total_partials,
            "total_excluded":       self.total_excluded,
            "solids":               [s.as_dict() for s in self.solids],
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def gather_fillets(
    normalized: NormalizedShape,
    solids: List[TopoDS_Solid],
    fillet_angle_tol_pct: float = 5.0,
    full_circle_tol_deg: float = 2.0,
) -> FilletGatherResult:
    """Classify all cylindrical faces in a :class:`~post_process.shape_normalizer.NormalizedShape`.

    Parameters
    ----------
    normalized:
        Output of :func:`~post_process.shape_normalizer.normalize_shape`.
    solids:
        Raw OCC solids from
        :func:`~post_process.shape_normalizer.extract_solids`.
        Must be in the **same order** as ``normalized.solids`` (both are
        produced from the same compound in depth-first order).
    fillet_angle_tol_pct:
        Tolerance (%) applied symmetrically around 90° for the
        ``fillet`` classification.  Default 5 % → [85.5°, 94.5°].
    full_circle_tol_deg:
        Tolerance (degrees) below 360° still classified as ``excluded``.
        Default 2° → [358°, 360°] is treated as a full circle.

    Returns
    -------
    FilletGatherResult

    Raises
    ------
    ValueError
        If ``normalized`` and ``solids`` have different lengths.
    """
    if not _OCC_AVAILABLE:
        raise ImportError(
            "pythonocc-core is required for gather_fillets().  "
            "Install it with: conda install -c conda-forge pythonocc-core"
        )

    if len(normalized.solids) != len(solids):
        raise ValueError(
            f"normalized has {len(normalized.solids)} solid(s) but "
            f"solids list has {len(solids)}.  Both must come from the "
            f"same compound."
        )

    solid_results = [
        _gather_solid_fillets(sd, occ_s, fillet_angle_tol_pct, full_circle_tol_deg)
        for sd, occ_s in zip(normalized.solids, solids)
    ]

    return FilletGatherResult(
        solids=solid_results,
        fillet_angle_tol_pct=fillet_angle_tol_pct,
        full_circle_tol_deg=full_circle_tol_deg,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _classify_angle(
    angle_deg: float,
    fillet_angle_tol_pct: float,
    full_circle_tol_deg: float,
) -> CylinderKind:
    """Classify an angular sweep (degrees) into a :class:`CylinderKind`.

    This pure function contains no OCC dependency and is independently
    testable.

    Parameters
    ----------
    angle_deg:
        Angular sweep in degrees, in (0°, 360°].
    fillet_angle_tol_pct:
        Symmetric tolerance around 90° expressed as a percentage of 90°.
    full_circle_tol_deg:
        Values in [360° − tol, 360°] are classified as ``excluded``.

    Returns
    -------
    CylinderKind
    """
    # Full circle — excluded (hole / bore / shaft)
    if angle_deg >= (360.0 - full_circle_tol_deg):
        return CylinderKind.EXCLUDED

    # Fillet — approximately 90°
    fillet_tol = 90.0 * (fillet_angle_tol_pct / 100.0)
    if abs(angle_deg - 90.0) <= fillet_tol:
        return CylinderKind.FILLET

    # Everything else
    return CylinderKind.PARTIAL


def _gather_solid_fillets(
    solid_data: SolidData,
    occ_solid: TopoDS_Solid,
    fillet_angle_tol_pct: float,
    full_circle_tol_deg: float,
) -> SolidFilletResult:
    """Analyze one solid for cylindrical faces.

    Rebuilds the face map in the same traversal order used by
    :func:`~post_process.shape_normalizer._process_solid` so that
    ``face_id`` values match the ``NormalizedShape`` indices.
    """
    # Rebuild the face map exactly as _process_solid does in shape_normalizer.
    face_map = TopTools_IndexedMapOfShape()
    exp = TopExp_Explorer(occ_solid, TopAbs_FACE)
    while exp.More():
        face_map.Add(exp.Current())
        exp.Next()

    result = SolidFilletResult(solid_id=solid_data.solid_id)

    for face_data in solid_data.faces:
        if face_data.surface_type != "Cylinder":
            continue

        # face_id is 0-based; face_map is 1-based.
        occ_face = topods.Face(face_map.FindKey(face_data.face_id + 1))

        adaptor = BRepAdaptor_Surface(occ_face)
        if adaptor.GetType() != GeomAbs_Cylinder:
            # Surface type string said Cylinder but adaptor disagrees — skip.
            continue

        # Angular sweep: U-parameter range of the face.
        # For a cylinder, U is the angle φ ∈ [0, 2π) around the axis.
        umin, umax, *_ = breptools.UVBounds(occ_face)
        angle_rad = abs(umax - umin)

        # A seam-split full cylinder may report slightly less than 2π.
        # Clamp anything within _SEAM_TOL_RAD of 2π up to exactly 2π
        # so it is correctly classified as a full circle.
        if angle_rad > _TWO_PI - _SEAM_TOL_RAD:
            angle_rad = _TWO_PI
        angle_deg = math.degrees(angle_rad)

        # Cylinder geometry.
        cyl       = adaptor.Cylinder()
        radius_mm = cyl.Radius()
        ax1       = cyl.Axis()
        d         = ax1.Direction()
        loc       = ax1.Location()

        kind = _classify_angle(angle_deg, fillet_angle_tol_pct, full_circle_tol_deg)

        feature = CylinderFeature(
            solid_id=solid_data.solid_id,
            face_id=face_data.face_id,
            kind=kind,
            radius_mm=radius_mm,
            angle_deg=angle_deg,
            axis_direction=(d.X(), d.Y(), d.Z()),
            axis_location=(loc.X(), loc.Y(), loc.Z()),
            center=face_data.center,
            area=face_data.area,
            adjacent_face_ids=list(solid_data.adjacency.get(face_data.face_id, [])),
        )

        if kind == CylinderKind.EXCLUDED:
            result.excluded_count += 1
        elif kind == CylinderKind.FILLET:
            result.fillets.append(feature)
        else:
            result.partials.append(feature)

    return result


__all__ = [
    "CylinderKind",
    "CylinderFeature",
    "SolidFilletResult",
    "FilletGatherResult",
    "gather_fillets",
    "_classify_angle",  # exported for testing
]
