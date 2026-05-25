"""Shape dimension inference from NormalizedShape.

Derives main mechanical drawing dimensions from the structured output of
post_process.shape_normalizer.normalize_shape():

  - Per-solid bounding box and principal dimensions (length × width × height)
  - Cylindrical features: estimated radius and height from bounding box geometry
  - Planar groups: faces clustered by normal direction with span along each axis
  - Wall thickness estimates: minimum gap between consecutive parallel planar faces
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, List, Tuple

# TYPE_CHECKING guard: FaceData / SolidData / NormalizedShape are OCC-dependent.
# With `from __future__ import annotations` all hints are lazy strings, so this
# import is never executed at runtime — shape_dimension can be imported without OCC.
if TYPE_CHECKING:
    from .shape_normalizer import FaceData, NormalizedShape, SolidData


_EPSILON = 1e-6       # mm — treat distances smaller than this as zero
_ANGLE_TOL_DEG = 5.0  # degrees — normals within this angle share a group


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CylindricalFeature:
    """A cylindrical surface with inferred radius and height.

    Radius and height are estimated from the axis-aligned bounding box of the
    face.  For a full 360° cylindrical face two of the three bbox extents equal
    the diameter (2r) and the third equals the height; the heuristic identifies
    the matching pair and assigns accordingly.
    """

    face_id: int
    center: Tuple[float, float, float]
    radius_est: float
    height_est: float
    area: float
    bounding_box: Tuple[float, float, float, float, float, float] = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    @property
    def diameter_est(self) -> float:
        return self.radius_est * 2.0

    @property
    def axis(self) -> str:
        """Infer cylinder axis ('x', 'y', or 'z') from the face bounding box.

        The axis direction is the one whose bounding-box extent best matches
        the estimated height (the two perpendicular extents match 2r).
        """
        xmin, ymin, zmin, xmax, ymax, zmax = self.bounding_box
        dx, dy, dz = xmax - xmin, ymax - ymin, zmax - zmin
        h = self.height_est
        diffs = [("x", abs(dx - h)), ("y", abs(dy - h)), ("z", abs(dz - h))]
        return min(diffs, key=lambda t: t[1])[0]

    def as_dict(self) -> Dict:
        return {
            "face_id": self.face_id,
            "center": self.center,
            "radius_est_mm": self.radius_est,
            "diameter_est_mm": self.diameter_est,
            "height_est_mm": self.height_est,
            "axis": self.axis,
            "area": self.area,
        }


@dataclass
class PlaneGroup:
    """A cluster of planar faces that share a common normal direction.

    Attributes
    ----------
    normal:
        Canonical unit normal — primary-axis component is always non-negative
        so that parallel and anti-parallel faces map to the same cluster.
    face_ids:
        IDs of every face in the cluster.
    positions:
        Signed distance of each face's centre along the group normal,
        same order as face_ids.
    total_area:
        Sum of face areas in the cluster.
    span:
        Distance between the outermost parallel planes in the cluster
        (max_position − min_position).  For a solid rectangular block this
        equals the overall dimension in that direction.
    """

    normal: Tuple[float, float, float]
    face_ids: List[int]
    positions: List[float]
    total_area: float
    span: float

    def as_dict(self) -> Dict:
        return {
            "normal": self.normal,
            "face_ids": self.face_ids,
            "positions": self.positions,
            "total_area": self.total_area,
            "span_mm": self.span,
        }


@dataclass
class WallThickness:
    """Distance between two consecutive parallel planar faces.

    When a normal group contains more than two parallel planes (e.g., a channel
    cut into a block), multiple WallThickness entries are generated — one per
    consecutive pair — so the caller can pick the minimum (thinnest wall) or
    interpret all gaps.

    Attributes
    ----------
    normal:
        Canonical unit normal shared by the two bounding faces.
    thickness_mm:
        Gap between the two faces along the normal direction.
    face_ids:
        ``(lower_face_id, upper_face_id)`` — the face pair that brackets the gap.
    """

    normal: Tuple[float, float, float]
    thickness_mm: float
    face_ids: Tuple[int, int]

    def as_dict(self) -> Dict:
        return {
            "normal": self.normal,
            "thickness_mm": self.thickness_mm,
            "face_ids": self.face_ids,
        }


@dataclass
class SolidDimensions:
    """All inferred dimensions for a single solid.

    Attributes
    ----------
    solid_id:
        Index into ``NormalizedShape.solids``.
    bounding_box:
        Union of all face bounding boxes: ``(xmin, ymin, zmin, xmax, ymax, zmax)``.
    length / width / height:
        Principal dimensions sorted descending (length >= width >= height).
    cylinders:
        All detected cylindrical faces with estimated radius and height.
    plane_groups:
        Planar faces clustered by normal direction, sorted by total area descending.
    wall_thicknesses:
        Consecutive-gap estimates for each planar group, sorted by thickness ascending.
    """

    solid_id: int
    bounding_box: Tuple[float, float, float, float, float, float]
    length: float
    width: float
    height: float
    cylinders: List[CylindricalFeature] = field(default_factory=list)
    plane_groups: List[PlaneGroup] = field(default_factory=list)
    wall_thicknesses: List[WallThickness] = field(default_factory=list)

    def as_dict(self) -> Dict:
        return {
            "solid_id": self.solid_id,
            "bounding_box": self.bounding_box,
            "length_mm": self.length,
            "width_mm": self.width,
            "height_mm": self.height,
            "cylinders": [c.as_dict() for c in self.cylinders],
            "plane_groups": [pg.as_dict() for pg in self.plane_groups],
            "wall_thicknesses": [wt.as_dict() for wt in self.wall_thicknesses],
        }


@dataclass
class ShapeDimensions:
    """Inferred dimensions for all solids in a NormalizedShape."""

    solids: List[SolidDimensions]

    def as_dict(self) -> Dict:
        return {"solids": [s.as_dict() for s in self.solids]}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def infer_dimensions(shape: NormalizedShape) -> ShapeDimensions:
    """Infer drawing-relevant dimensions from a :class:`NormalizedShape`.

    Parameters
    ----------
    shape:
        Output of :func:`~post_process.shape_normalizer.normalize_shape`.

    Returns
    -------
    ShapeDimensions
    """
    return ShapeDimensions(
        solids=[infer_solid_dimensions(solid) for solid in shape.solids]
    )


def infer_solid_dimensions(solid: SolidData) -> SolidDimensions:
    """Infer dimensions for a single :class:`SolidData`.

    Parameters
    ----------
    solid:
        One entry from ``NormalizedShape.solids``.

    Returns
    -------
    SolidDimensions
    """
    faces = solid.faces
    if not faces:
        empty_bb = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        return SolidDimensions(
            solid_id=solid.solid_id,
            bounding_box=empty_bb,
            length=0.0, width=0.0, height=0.0,
        )

    bbox = _union_bbox(faces)
    dx = bbox[3] - bbox[0]
    dy = bbox[4] - bbox[1]
    dz = bbox[5] - bbox[2]
    length, width, height = tuple(sorted([dx, dy, dz], reverse=True))

    cylinders = [_estimate_cylinder(f) for f in faces if f.surface_type == "Cylinder"]
    plane_groups = _group_planes_by_normal(faces)
    wall_thicknesses = _estimate_wall_thicknesses(plane_groups)

    return SolidDimensions(
        solid_id=solid.solid_id,
        bounding_box=bbox,
        length=length,
        width=width,
        height=height,
        cylinders=cylinders,
        plane_groups=plane_groups,
        wall_thicknesses=wall_thicknesses,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _union_bbox(
    faces: List[FaceData],
) -> Tuple[float, float, float, float, float, float]:
    """Return the axis-aligned union of all face bounding boxes."""
    xmin = min(f.bounding_box[0] for f in faces)
    ymin = min(f.bounding_box[1] for f in faces)
    zmin = min(f.bounding_box[2] for f in faces)
    xmax = max(f.bounding_box[3] for f in faces)
    ymax = max(f.bounding_box[4] for f in faces)
    zmax = max(f.bounding_box[5] for f in faces)
    return (xmin, ymin, zmin, xmax, ymax, zmax)


def _estimate_cylinder(face: FaceData) -> CylindricalFeature:
    """Estimate the radius and height of a cylindrical face from its bbox.

    For a full 360° cylindrical face the bounding box has two extents equal to
    the diameter (2r) and one equal to the height.  The heuristic identifies
    the matching diameter pair by comparing the gaps between sorted extents:
    the two extents with the smaller mutual gap are the diameter pair.
    """
    xmin, ymin, zmin, xmax, ymax, zmax = face.bounding_box
    dx, dy, dz = xmax - xmin, ymax - ymin, zmax - zmin

    extents = sorted([dx, dy, dz])
    e0, e1, e2 = extents

    # The pair with the smaller mutual gap is the diameter pair.
    if abs(e1 - e0) <= abs(e2 - e1):
        r_est = (e0 + e1) / 4.0
        h_est = e2
    else:
        r_est = (e1 + e2) / 4.0
        h_est = e0

    return CylindricalFeature(
        face_id=face.face_id,
        center=face.center,
        radius_est=max(r_est, _EPSILON),
        height_est=max(h_est, _EPSILON),
        area=face.area,
        bounding_box=face.bounding_box,
    )


def _canonicalize_normal(
    n: Tuple[float, float, float],
) -> Tuple[float, float, float]:
    """Flip *n* so that its dominant-axis component is non-negative.

    This maps parallel and anti-parallel normals to the same canonical
    direction, so both faces of a wall end up in the same :class:`PlaneGroup`.
    """
    ax, ay, az = abs(n[0]), abs(n[1]), abs(n[2])
    if ax >= ay and ax >= az:
        return n if n[0] >= 0 else (-n[0], -n[1], -n[2])
    if ay >= ax and ay >= az:
        return n if n[1] >= 0 else (-n[0], -n[1], -n[2])
    return n if n[2] >= 0 else (-n[0], -n[1], -n[2])


def _angle_between_deg(
    a: Tuple[float, float, float],
    b: Tuple[float, float, float],
) -> float:
    """Angle in degrees between two unit vectors."""
    dot = sum(a[i] * b[i] for i in range(3))
    return math.degrees(math.acos(max(-1.0, min(1.0, dot))))


def _dot(
    a: Tuple[float, float, float],
    b: Tuple[float, float, float],
) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _group_planes_by_normal(
    faces: List[FaceData],
    angle_tol_deg: float = _ANGLE_TOL_DEG,
) -> List[PlaneGroup]:
    """Cluster planar faces whose canonical normals are within *angle_tol_deg*.

    Face positions along the group normal are computed using the first face's
    raw normal as the projection axis (so positions for anti-parallel faces
    are negative, preserving their sign — the span calculation uses max - min).
    Groups are returned sorted by total area descending.
    """
    plane_faces = [
        f for f in faces if f.surface_type == "Plane" and f.normal is not None
    ]

    groups: List[PlaneGroup] = []
    used = [False] * len(plane_faces)

    for i, seed in enumerate(plane_faces):
        if used[i]:
            continue

        canon_seed = _canonicalize_normal(seed.normal)
        proj_axis = seed.normal  # projection axis: same sign as seed's normal

        face_ids = [seed.face_id]
        positions = [_dot(seed.center, proj_axis)]
        total_area = seed.area
        used[i] = True

        for j, other in enumerate(plane_faces):
            if used[j]:
                continue
            canon_other = _canonicalize_normal(other.normal)
            if _angle_between_deg(canon_seed, canon_other) <= angle_tol_deg:
                face_ids.append(other.face_id)
                positions.append(_dot(other.center, proj_axis))
                total_area += other.area
                used[j] = True

        span = max(positions) - min(positions) if len(positions) > 1 else 0.0
        groups.append(PlaneGroup(
            normal=canon_seed,
            face_ids=face_ids,
            positions=positions,
            total_area=total_area,
            span=span,
        ))

    groups.sort(key=lambda g: g.total_area, reverse=True)
    return groups


def _estimate_wall_thicknesses(
    plane_groups: List[PlaneGroup],
) -> List[WallThickness]:
    """Return a wall thickness entry for each consecutive gap in every plane group.

    Within each group, faces are sorted by position along the group normal.
    Every adjacent pair contributes one :class:`WallThickness`; the caller can
    select the minimum (thinnest wall) or inspect all gaps.  Results are sorted
    by thickness ascending.
    """
    thicknesses: List[WallThickness] = []

    for group in plane_groups:
        if len(group.face_ids) < 2:
            continue

        pairs = sorted(zip(group.positions, group.face_ids))

        for (p_lo, fid_lo), (p_hi, fid_hi) in zip(pairs, pairs[1:]):
            gap = p_hi - p_lo
            if gap > _EPSILON:
                thicknesses.append(WallThickness(
                    normal=group.normal,
                    thickness_mm=gap,
                    face_ids=(fid_lo, fid_hi),
                ))

    thicknesses.sort(key=lambda wt: wt.thickness_mm)
    return thicknesses


__all__ = [
    "infer_dimensions",
    "infer_solid_dimensions",
    "ShapeDimensions",
    "SolidDimensions",
    "CylindricalFeature",
    "PlaneGroup",
    "WallThickness",
]
