"""Hole-diameter gatherer for NormalizedShape output.

Scans every solid in a :class:`~post_process.shape_normalizer.NormalizedShape`
for cylindrical faces whose angular sweep covers at least
``(100 - full_circle_tol_pct)`` % of 360°.  These are holes, bores, and
shafts where the material wraps fully around the cylinder axis — the cylinder
**completely defines** the feature in all 360°.

Cylinders whose sweep falls below the threshold (partial arcs, fillets, …) are
excluded and counted separately.

The two inputs are both produced by :mod:`post_process.shape_normalizer`:

.. code-block:: python

    from load_cad.step_reader import read_step_single
    from post_process.shape_normalizer import normalize_shape, extract_solids
    from post_process.dimensions.dimension_gather_diameterHole import gather_hole_diameters

    compound   = read_step_single("part.step")
    normalized = normalize_shape(compound)
    solids     = extract_solids(compound)
    result     = gather_hole_diameters(normalized, solids)

Every :class:`HoleDiameterFeature` carries ``(solid_id, face_id)`` that map
directly back into the ``NormalizedShape``::

    solid_data = normalized.solids[feature.solid_id]
    face_data  = solid_data.faces[feature.face_id]
    neighbours = solid_data.adjacency[feature.face_id]
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
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
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class HoleDiameterFeature:
    """One cylindrical face that fully defines a hole, bore, or shaft.

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
    diameter_mm:
        Hole diameter in mm (2 × ``radius_mm``).
    radius_mm:
        Cylinder radius in mm.
    angle_deg:
        Angular sweep of this face in degrees (≥ threshold, typically ≈360°).
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
    diameter_mm: float
    radius_mm: float
    angle_deg: float
    axis_direction: Tuple[float, float, float]
    axis_location: Tuple[float, float, float]
    center: Tuple[float, float, float]
    area: float
    adjacent_face_ids: List[int] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "solid_id":          self.solid_id,
            "face_id":           self.face_id,
            "diameter_mm":       self.diameter_mm,
            "radius_mm":         self.radius_mm,
            "angle_deg":         self.angle_deg,
            "axis_direction":    self.axis_direction,
            "axis_location":     self.axis_location,
            "center":            self.center,
            "area":              self.area,
            "adjacent_face_ids": self.adjacent_face_ids,
        }


@dataclass
class SolidHoleResult:
    """Hole-diameter analysis for one solid.

    Attributes
    ----------
    solid_id:
        Index into ``NormalizedShape.solids``.
    holes:
        Cylindrical faces whose angular sweep meets the full-circle threshold.
    excluded_count:
        Number of cylindrical faces that were partial (sweep too small) and
        therefore excluded.
    """

    solid_id: int
    holes: List[HoleDiameterFeature] = field(default_factory=list)
    excluded_count: int = 0

    def as_dict(self) -> dict:
        return {
            "solid_id":       self.solid_id,
            "holes":          [h.as_dict() for h in self.holes],
            "excluded_count": self.excluded_count,
        }


@dataclass
class HoleDiameterGatherResult:
    """Full hole-diameter analysis for all solids in a :class:`~post_process.shape_normalizer.NormalizedShape`.

    Attributes
    ----------
    solids:
        One :class:`SolidHoleResult` per solid, in the same order as
        ``NormalizedShape.solids``.
    full_circle_tol_pct:
        Percentage of 360° that may be missing and still be accepted as a
        complete hole.  Default 5 % → threshold = 342°.
    """

    solids: List[SolidHoleResult]
    full_circle_tol_pct: float = 5.0

    @property
    def total_holes(self) -> int:
        return sum(len(s.holes) for s in self.solids)

    @property
    def total_excluded(self) -> int:
        return sum(s.excluded_count for s in self.solids)

    @property
    def all_holes(self) -> List[HoleDiameterFeature]:
        """All hole candidates across every solid."""
        return [h for s in self.solids for h in s.holes]

    def as_dict(self) -> dict:
        return {
            "full_circle_tol_pct": self.full_circle_tol_pct,
            "total_holes":         self.total_holes,
            "total_excluded":      self.total_excluded,
            "solids":              [s.as_dict() for s in self.solids],
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def gather_hole_diameters(
    normalized: "NormalizedShape",
    solids: "List[TopoDS_Solid]",
    full_circle_tol_pct: float = 5.0,
) -> HoleDiameterGatherResult:
    """Gather all cylindrical faces that fully define a hole in a :class:`~post_process.shape_normalizer.NormalizedShape`.

    A cylinder is included when its angular sweep covers at least
    ``(100 - full_circle_tol_pct)`` % of 360°, meaning the CAD part
    material wraps around the cylinder axis over the full circumference
    within the given tolerance.

    Parameters
    ----------
    normalized:
        Output of :func:`~post_process.shape_normalizer.normalize_shape`.
    solids:
        Raw OCC solids from
        :func:`~post_process.shape_normalizer.extract_solids`.
        Must be in the **same order** as ``normalized.solids`` (both are
        produced from the same compound in depth-first order).
    full_circle_tol_pct:
        Percentage tolerance below 360° that is still accepted as a full
        circle.  Default 5 % → cylinders with sweep ≥ 342° are included.

    Returns
    -------
    HoleDiameterGatherResult

    Raises
    ------
    ValueError
        If ``normalized`` and ``solids`` have different lengths.
    """
    if not _OCC_AVAILABLE:
        raise ImportError(
            "pythonocc-core is required for gather_hole_diameters().  "
            "Install it with: conda install -c conda-forge pythonocc-core"
        )

    if len(normalized.solids) != len(solids):
        raise ValueError(
            f"normalized has {len(normalized.solids)} solid(s) but "
            f"solids list has {len(solids)}.  Both must come from the "
            f"same compound."
        )

    solid_results = [
        _gather_solid_holes(sd, occ_s, full_circle_tol_pct)
        for sd, occ_s in zip(normalized.solids, solids)
    ]

    return HoleDiameterGatherResult(
        solids=solid_results,
        full_circle_tol_pct=full_circle_tol_pct,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_full_circle(angle_deg: float, full_circle_tol_pct: float) -> bool:
    """Return True if *angle_deg* covers enough of 360° to be a complete hole.

    This pure function contains no OCC dependency and is independently
    testable.

    Parameters
    ----------
    angle_deg:
        Angular sweep in degrees, in (0°, 360°].
    full_circle_tol_pct:
        Percentage of 360° that may be missing and still be accepted.
        ``0.0`` → only exact 360° passes; ``5.0`` → ≥ 342° passes.
    """
    threshold = 360.0 * (1.0 - full_circle_tol_pct / 100.0)
    return angle_deg >= threshold


def _gather_solid_holes(
    solid_data: "SolidData",
    occ_solid: "TopoDS_Solid",
    full_circle_tol_pct: float,
) -> SolidHoleResult:
    """Analyse one solid for cylindrical faces that fully define holes.

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

    result = SolidHoleResult(solid_id=solid_data.solid_id)

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

        if _is_full_circle(angle_deg, full_circle_tol_pct):
            feature = HoleDiameterFeature(
                solid_id=solid_data.solid_id,
                face_id=face_data.face_id,
                diameter_mm=2.0 * radius_mm,
                radius_mm=radius_mm,
                angle_deg=angle_deg,
                axis_direction=(d.X(), d.Y(), d.Z()),
                axis_location=(loc.X(), loc.Y(), loc.Z()),
                center=face_data.center,
                area=face_data.area,
                adjacent_face_ids=list(solid_data.adjacency.get(face_data.face_id, [])),
            )
            result.holes.append(feature)
        else:
            result.excluded_count += 1

    return result


__all__ = [
    "HoleDiameterFeature",
    "SolidHoleResult",
    "HoleDiameterGatherResult",
    "gather_hole_diameters",
    "_is_full_circle",  # exported for testing
]
