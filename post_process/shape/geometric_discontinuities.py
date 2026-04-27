"""Geometric discontinuity gatherer for NormalizedShape output.

Scans every solid in a :class:`~post_process.shape_normalizer.NormalizedShape`
for adjacent face pairs that meet at a **sharp edge** — a geometric
discontinuity — by measuring the angle between their outward-pointing surface
normals at each shared edge.

The angle between outward normals (``dihedral_angle_deg``) is the sharpness
metric:

* **0°** → coplanar / tangent-continuous surfaces (smooth, not flagged)
* **90°** → right-angle corner (typical machined box edge)
* **180°** → knife edge (degenerate)

Edges are flagged when ``dihedral_angle_deg ≥ angle_threshold_deg``
(default **30°**), which corresponds to faces meeting at ≤ 150° exterior
dihedral.  Fillets replace sharp edges with smooth blends, so their
boundary edges produce angles near 0° and are **not** flagged.

Each :class:`SharpEdge` also carries:

* A :class:`DiscontinuityKind` — ``CONVEX`` (ridge, injury risk) or
  ``CONCAVE`` (re-entrant notch, stress-concentration risk) — determined
  heuristically from the solid centroid.
* A :class:`DiscontinuitySeverity` — ``LOW / MEDIUM / HIGH``.
* ``(solid_id, face_id_a, face_id_b)`` that map back into the
  :class:`~post_process.shape_normalizer.NormalizedShape`.

Usage::

    from load_cad.step_reader import read_step_single
    from post_process.shape_normalizer import normalize_shape, extract_solids
    from post_process.shape.geometric_discontinuities import gather_discontinuities

    compound   = read_step_single("part.step")
    normalized = normalize_shape(compound)
    solids     = extract_solids(compound)
    result     = gather_discontinuities(normalized, solids)

    solid_data = normalized.solids[edge.solid_id]
    face_a     = solid_data.faces[edge.face_id_a]
    face_b     = solid_data.faces[edge.face_id_b]
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple

_OCC_AVAILABLE = False
try:
    from OCC.Core.BRep import BRep_Tool
    from OCC.Core.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
    from OCC.Core.BRepGProp import brepgprop
    from OCC.Core.BRepLProp import BRepLProp_SLProps
    from OCC.Core.GProp import GProp_GProps
    from OCC.Core.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_REVERSED
    from OCC.Core.TopExp import TopExp_Explorer, topexp
    from OCC.Core.TopTools import (
        TopTools_IndexedDataMapOfShapeListOfShape,
        TopTools_IndexedMapOfShape,
        TopTools_ListIteratorOfListOfShape,
    )
    from OCC.Core.TopoDS import TopoDS_Solid, topods
    from OCC.Core.gp import gp_Pnt, gp_Vec
    from post_process.shape_normalizer import NormalizedShape, SolidData
    _OCC_AVAILABLE = True
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class DiscontinuityKind(str, Enum):
    """Geometric orientation of a sharp edge."""

    CONVEX = "convex"
    """Outward ridge — material protrudes at the edge.  Risk: physical injury."""

    CONCAVE = "concave"
    """Re-entrant notch — material wraps inward.  Risk: stress concentration."""

    UNKNOWN = "unknown"
    """Orientation could not be determined reliably."""


class DiscontinuitySeverity(str, Enum):
    """Severity bucket derived from the angle between outward face normals."""

    LOW = "low"
    """30° – 44°: gentle turn; minor concern."""

    MEDIUM = "medium"
    """45° – 89°: notable sharp edge; review recommended."""

    HIGH = "high"
    """≥ 90°: right-angle corner or sharper; action recommended."""


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SharpEdge:
    """One geometric discontinuity between two adjacent faces.

    Attributes
    ----------
    solid_id:
        Index into ``NormalizedShape.solids``.
    face_id_a, face_id_b:
        Indices into ``NormalizedShape.solids[solid_id].faces`` for the two
        faces that share this sharp edge.
    dihedral_angle_deg:
        Angle between the outward surface normals at the edge midpoint, in
        degrees.  0° = coplanar/smooth; 90° = right-angle corner; 180° =
        knife edge.
    edge_midpoint:
        3-D coordinates ``(x, y, z)`` of the edge's parametric midpoint in mm.
    edge_length:
        Length of the shared edge in mm.
    kind:
        Convex / concave / unknown classification (heuristic based on the
        solid centroid).
    severity:
        Severity bucket derived from ``dihedral_angle_deg``.
    adjacent_face_ids_a:
        All faces adjacent to ``face_id_a`` within the same solid
        (from :attr:`~post_process.shape_normalizer.SolidData.adjacency`).
    adjacent_face_ids_b:
        All faces adjacent to ``face_id_b`` within the same solid.
    """

    solid_id: int
    face_id_a: int
    face_id_b: int
    dihedral_angle_deg: float
    edge_midpoint: Tuple[float, float, float]
    edge_length: float
    kind: DiscontinuityKind
    severity: DiscontinuitySeverity
    adjacent_face_ids_a: List[int] = field(default_factory=list)
    adjacent_face_ids_b: List[int] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "solid_id":            self.solid_id,
            "face_id_a":           self.face_id_a,
            "face_id_b":           self.face_id_b,
            "dihedral_angle_deg":  self.dihedral_angle_deg,
            "edge_midpoint":       self.edge_midpoint,
            "edge_length":         self.edge_length,
            "kind":                self.kind.value,
            "severity":            self.severity.value,
            "adjacent_face_ids_a": self.adjacent_face_ids_a,
            "adjacent_face_ids_b": self.adjacent_face_ids_b,
        }


@dataclass
class SolidDiscontinuityResult:
    """Discontinuity analysis for one solid.

    Attributes
    ----------
    solid_id:
        Index into ``NormalizedShape.solids``.
    sharp_edges:
        All sharp edges detected in this solid above the angle threshold.
    total_edges_checked:
        Number of manifold (shared by exactly 2 faces) edges examined.
    """

    solid_id: int
    sharp_edges: List[SharpEdge] = field(default_factory=list)
    total_edges_checked: int = 0

    @property
    def convex_edges(self) -> List[SharpEdge]:
        """Sharp edges classified as convex ridges."""
        return [e for e in self.sharp_edges if e.kind == DiscontinuityKind.CONVEX]

    @property
    def concave_edges(self) -> List[SharpEdge]:
        """Sharp edges classified as concave notches."""
        return [e for e in self.sharp_edges if e.kind == DiscontinuityKind.CONCAVE]

    @property
    def high_severity_edges(self) -> List[SharpEdge]:
        """Sharp edges with HIGH severity (≥ 90° between normals)."""
        return [e for e in self.sharp_edges if e.severity == DiscontinuitySeverity.HIGH]

    def as_dict(self) -> dict:
        return {
            "solid_id":            self.solid_id,
            "sharp_edges":         [e.as_dict() for e in self.sharp_edges],
            "total_edges_checked": self.total_edges_checked,
        }


@dataclass
class DiscontinuityGatherResult:
    """Full discontinuity analysis for all solids in a :class:`~post_process.shape_normalizer.NormalizedShape`.

    Attributes
    ----------
    solids:
        One :class:`SolidDiscontinuityResult` per solid, in the same order
        as ``NormalizedShape.solids``.
    angle_threshold_deg:
        Minimum angle between outward normals (degrees) used to flag an edge
        as a sharp discontinuity.
    """

    solids: List[SolidDiscontinuityResult]
    angle_threshold_deg: float = 30.0

    @property
    def total_sharp_edges(self) -> int:
        return sum(len(s.sharp_edges) for s in self.solids)

    @property
    def total_edges_checked(self) -> int:
        return sum(s.total_edges_checked for s in self.solids)

    @property
    def all_sharp_edges(self) -> List[SharpEdge]:
        """All sharp edges across every solid."""
        return [e for s in self.solids for e in s.sharp_edges]

    @property
    def all_convex_edges(self) -> List[SharpEdge]:
        return [e for s in self.solids for e in s.convex_edges]

    @property
    def all_concave_edges(self) -> List[SharpEdge]:
        return [e for s in self.solids for e in s.concave_edges]

    @property
    def all_high_severity(self) -> List[SharpEdge]:
        return [e for s in self.solids for e in s.high_severity_edges]

    def as_dict(self) -> dict:
        return {
            "angle_threshold_deg": self.angle_threshold_deg,
            "total_sharp_edges":   self.total_sharp_edges,
            "total_edges_checked": self.total_edges_checked,
            "solids":              [s.as_dict() for s in self.solids],
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def gather_discontinuities(
    normalized: "NormalizedShape",
    solids: "List[TopoDS_Solid]",
    angle_threshold_deg: float = 30.0,
) -> DiscontinuityGatherResult:
    """Detect sharp geometric discontinuities in a :class:`~post_process.shape_normalizer.NormalizedShape`.

    For every internal edge (shared by exactly two faces) the angle between
    the outward surface normals is measured.  Edges above
    ``angle_threshold_deg`` are flagged as :class:`SharpEdge` features.

    Parameters
    ----------
    normalized:
        Output of :func:`~post_process.shape_normalizer.normalize_shape`.
    solids:
        Raw OCC solids from
        :func:`~post_process.shape_normalizer.extract_solids`.
        Must be in the **same order** as ``normalized.solids``.
    angle_threshold_deg:
        Minimum angle between outward normals (degrees) to flag an edge.
        Default 30° corresponds to faces meeting at ≤ 150° exterior dihedral.

    Returns
    -------
    DiscontinuityGatherResult

    Raises
    ------
    ValueError
        If ``normalized`` and ``solids`` have different lengths.
    """
    if not _OCC_AVAILABLE:
        raise ImportError(
            "pythonocc-core is required for gather_discontinuities().  "
            "Install it with: conda install -c conda-forge pythonocc-core"
        )

    if len(normalized.solids) != len(solids):
        raise ValueError(
            f"normalized has {len(normalized.solids)} solid(s) but "
            f"solids list has {len(solids)}.  Both must come from the "
            f"same compound."
        )

    solid_results = []
    for sd, occ_s in zip(normalized.solids, solids):
        centroid = _solid_centroid(occ_s)
        solid_results.append(
            _gather_solid_discontinuities(sd, occ_s, angle_threshold_deg, centroid)
        )

    return DiscontinuityGatherResult(
        solids=solid_results,
        angle_threshold_deg=angle_threshold_deg,
    )


# ---------------------------------------------------------------------------
# Internal helpers — pure Python (no OCC), independently testable
# ---------------------------------------------------------------------------

def _classify_severity(dihedral_angle_deg: float) -> DiscontinuitySeverity:
    """Return the :class:`DiscontinuitySeverity` for a given normal angle.

    Parameters
    ----------
    dihedral_angle_deg:
        Angle between outward face normals at the shared edge, in degrees.

    Returns
    -------
    DiscontinuitySeverity
    """
    if dihedral_angle_deg >= 90.0:
        return DiscontinuitySeverity.HIGH
    elif dihedral_angle_deg >= 45.0:
        return DiscontinuitySeverity.MEDIUM
    else:
        return DiscontinuitySeverity.LOW


# ---------------------------------------------------------------------------
# Internal helpers — OCC
# ---------------------------------------------------------------------------

def _solid_centroid(occ_solid: "TopoDS_Solid") -> "Optional[gp_Pnt]":
    """Return the volumetric centroid of *occ_solid*, or ``None`` on failure."""
    try:
        props = GProp_GProps()
        brepgprop.VolumeProperties(occ_solid, props)
        return props.CentreOfMass()
    except Exception:
        return None


def _face_normal_at_edge(
    occ_edge,
    face,
) -> Optional[gp_Vec]:
    """Evaluate the outward surface normal of *face* at the midpoint of *occ_edge*.

    Returns ``None`` if the normal cannot be determined (degenerate geometry,
    missing pcurve, …).
    """
    try:
        pcurve, t_first, t_last = BRep_Tool.CurveOnSurface(occ_edge, face)
        if pcurve is None:
            return None
        t_mid = (t_first + t_last) * 0.5
        uv = pcurve.Value(t_mid)

        adaptor = BRepAdaptor_Surface(face)
        sln = BRepLProp_SLProps(adaptor, uv.X(), uv.Y(), 1, 1e-6)
        if not sln.IsNormalDefined():
            return None

        n_dir = sln.Normal()
        n = gp_Vec(n_dir.X(), n_dir.Y(), n_dir.Z())

        # Flip so the normal points outward from the solid material.
        if face.Orientation() == TopAbs_REVERSED:
            n.Reverse()

        mag = n.Magnitude()
        if mag < 1e-10:
            return None
        n.Multiply(1.0 / mag)  # normalize in place
        return n
    except Exception:
        return None


def _determine_kind(
    n_a: "gp_Vec",
    n_b: "gp_Vec",
    centroid: "Optional[gp_Pnt]",
    midpoint: "gp_Pnt",
) -> DiscontinuityKind:
    """Classify an edge as CONVEX, CONCAVE, or UNKNOWN.

    Uses the bisector of the two outward normals: if it points away from the
    solid centroid the edge is a **convex** ridge; if toward the centroid it
    is a **concave** notch.
    """
    if centroid is None:
        return DiscontinuityKind.UNKNOWN
    try:
        bx = n_a.X() + n_b.X()
        by = n_a.Y() + n_b.Y()
        bz = n_a.Z() + n_b.Z()
        b_mag = math.sqrt(bx * bx + by * by + bz * bz)
        if b_mag < 1e-8:
            # Normals are antiparallel — knife edge, direction ambiguous.
            return DiscontinuityKind.UNKNOWN

        # Unit bisector of the two outward normals (points into "free space").
        bx /= b_mag
        by /= b_mag
        bz /= b_mag

        # Vector from solid centroid to edge midpoint.
        dx = midpoint.X() - centroid.X()
        dy = midpoint.Y() - centroid.Y()
        dz = midpoint.Z() - centroid.Z()
        dist = math.sqrt(dx * dx + dy * dy + dz * dz)
        if dist < 1e-8:
            return DiscontinuityKind.UNKNOWN

        dot = bx * dx + by * dy + bz * dz
        # Require at least 10 % confidence (bisector not nearly ⊥ centroid dir).
        if abs(dot) < 0.1 * dist:
            return DiscontinuityKind.UNKNOWN

        return DiscontinuityKind.CONVEX if dot > 0 else DiscontinuityKind.CONCAVE
    except Exception:
        return DiscontinuityKind.UNKNOWN


def _gather_solid_discontinuities(
    solid_data: "SolidData",
    occ_solid: "TopoDS_Solid",
    angle_threshold_deg: float,
    centroid: "Optional[gp_Pnt]",
) -> SolidDiscontinuityResult:
    """Scan one solid for all sharp edges above the angle threshold.

    Rebuilds the face map in the same traversal order as
    :func:`~post_process.shape_normalizer._process_solid` so that face IDs
    match the :class:`~post_process.shape_normalizer.NormalizedShape` indices.
    """
    # Face map — same order as shape_normalizer._process_solid.
    face_map = TopTools_IndexedMapOfShape()
    exp = TopExp_Explorer(occ_solid, TopAbs_FACE)
    while exp.More():
        face_map.Add(exp.Current())
        exp.Next()

    # Edge → parent faces map.
    edge_face_map = TopTools_IndexedDataMapOfShapeListOfShape()
    topexp.MapShapesAndAncestors(occ_solid, TopAbs_EDGE, TopAbs_FACE, edge_face_map)

    result = SolidDiscontinuityResult(solid_id=solid_data.solid_id)

    for i in range(1, edge_face_map.Size() + 1):
        occ_edge = topods.Edge(edge_face_map.FindKey(i))

        # Skip degenerate edges (e.g., poles of spheres / cones).
        if BRep_Tool.Degenerated(occ_edge):
            continue

        face_list = edge_face_map.FindFromIndex(i)
        if face_list.Size() != 2:
            # Boundary or non-manifold edge — not an internal seam.
            continue

        result.total_edges_checked += 1

        # Collect the two parent faces.
        it = TopTools_ListIteratorOfListOfShape(face_list)
        parent_faces = []
        while it.More():
            parent_faces.append(it.Value())
            it.Next()
        face_a = topods.Face(parent_faces[0])
        face_b = topods.Face(parent_faces[1])

        # Resolve 0-based face IDs from the face map.
        idx_a = face_map.FindIndex(face_a)
        idx_b = face_map.FindIndex(face_b)
        if idx_a == 0 or idx_b == 0:
            continue
        face_id_a = idx_a - 1
        face_id_b = idx_b - 1

        # Edge midpoint (parametric mid).
        try:
            adaptor_c = BRepAdaptor_Curve(occ_edge)
        except Exception:
            continue
        t_mid = (adaptor_c.FirstParameter() + adaptor_c.LastParameter()) * 0.5
        pnt_mid = adaptor_c.Value(t_mid)

        # Edge length.
        edge_props = GProp_GProps()
        brepgprop.LinearProperties(occ_edge, edge_props)
        edge_length = edge_props.Mass()

        # Outward surface normals at the edge midpoint.
        n_a = _face_normal_at_edge(occ_edge, face_a)
        n_b = _face_normal_at_edge(occ_edge, face_b)
        if n_a is None or n_b is None:
            continue

        # Angle between outward normals.
        dot_nn = max(-1.0, min(1.0, n_a.Dot(n_b)))
        angle_deg = math.degrees(math.acos(dot_nn))

        if angle_deg < angle_threshold_deg:
            continue  # smooth transition — not a discontinuity

        severity = _classify_severity(angle_deg)
        kind = _determine_kind(n_a, n_b, centroid, pnt_mid)

        result.sharp_edges.append(SharpEdge(
            solid_id=solid_data.solid_id,
            face_id_a=face_id_a,
            face_id_b=face_id_b,
            dihedral_angle_deg=angle_deg,
            edge_midpoint=(pnt_mid.X(), pnt_mid.Y(), pnt_mid.Z()),
            edge_length=edge_length,
            kind=kind,
            severity=severity,
            adjacent_face_ids_a=list(solid_data.adjacency.get(face_id_a, [])),
            adjacent_face_ids_b=list(solid_data.adjacency.get(face_id_b, [])),
        ))

    return result


__all__ = [
    "DiscontinuityKind",
    "DiscontinuitySeverity",
    "SharpEdge",
    "SolidDiscontinuityResult",
    "DiscontinuityGatherResult",
    "gather_discontinuities",
    "_classify_severity",  # exported for testing
]
