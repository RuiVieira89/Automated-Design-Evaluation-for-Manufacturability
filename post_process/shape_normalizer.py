"""Shape normalization layer for TopoDS topology.

Converts a TopoDS_Compound (e.g., loaded from a STEP file) into a structured
NormalizedShape containing SolidData objects with per-face attributes and a
face-adjacency graph built from shared edges.

Hierarchy traversed::

    TopoDS_Compound
      -> TopoDS_CompSolid  (optional)
      -> TopoDS_Solid
          -> TopoDS_Shell
              -> TopoDS_Face
                  -> TopoDS_Wire
                      -> TopoDS_Edge

Shapes at the SHELL / WIRE / EDGE / VERTEX level that have no solid parent
(wireframe-only or construction-only geometry) are silently ignored.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from OCC.Core.BRepAdaptor import BRepAdaptor_Surface
from OCC.Core.BRepBndLib import brepbndlib
from OCC.Core.BRepGProp import brepgprop
from OCC.Core.Bnd import Bnd_Box
from OCC.Core.GeomAbs import (
    GeomAbs_BSplineSurface,
    GeomAbs_BezierSurface,
    GeomAbs_Cone,
    GeomAbs_Cylinder,
    GeomAbs_OtherSurface,
    GeomAbs_Plane,
    GeomAbs_Sphere,
    GeomAbs_Torus,
)
from OCC.Core.GProp import GProp_GProps
from OCC.Core.TopAbs import (
    TopAbs_COMPOUND,
    TopAbs_COMPSOLID,
    TopAbs_EDGE,
    TopAbs_FACE,
    TopAbs_SOLID,
)
from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopTools import TopTools_IndexedMapOfShape
from OCC.Core.TopoDS import TopoDS_Iterator, TopoDS_Shape, TopoDS_Solid, topods

LOGGER = logging.getLogger(__name__)

_SURFACE_TYPE_NAMES: Dict[int, str] = {
    GeomAbs_Plane: "Plane",
    GeomAbs_Cylinder: "Cylinder",
    GeomAbs_Cone: "Cone",
    GeomAbs_Sphere: "Sphere",
    GeomAbs_Torus: "Torus",
    GeomAbs_BezierSurface: "Bezier",
    GeomAbs_BSplineSurface: "BSpline",
    GeomAbs_OtherSurface: "Other",
}


@dataclass
class FaceData:
    """Attributes computed for a single topological face.

    Attributes
    ----------
    face_id:
        Zero-based index of the face within its parent solid.
    surface_type:
        String name of the underlying geometry type (e.g. ``"Plane"``,
        ``"Cylinder"``).
    area:
        Surface area of the face.
    center:
        Centre of mass of the face as ``(x, y, z)``.
    normal:
        Unit normal direction for planar faces; ``None`` for non-planar
        surfaces.
    bounding_box:
        Axis-aligned bounding box as
        ``(xmin, ymin, zmin, xmax, ymax, zmax)``.
    """

    face_id: int
    surface_type: str
    area: float
    center: Tuple[float, float, float]
    normal: Optional[Tuple[float, float, float]]
    bounding_box: Tuple[float, float, float, float, float, float]


@dataclass
class SolidData:
    """Normalized representation of a single solid.

    Attributes
    ----------
    solid_id:
        Zero-based index of the solid within the parent :class:`NormalizedShape`.
    faces:
        Ordered list of :class:`FaceData` for each face of the solid.
    adjacency:
        Mapping from ``face_id`` to a list of neighbouring ``face_id`` values
        that share at least one edge with that face.
    """

    solid_id: int
    faces: List[FaceData] = field(default_factory=list)
    adjacency: Dict[int, List[int]] = field(default_factory=dict)


@dataclass
class AssemblyNode:
    """Assembly hierarchy context for a single solid.

    Attributes
    ----------
    path:
        Sequence of child indices from the root compound down to the immediate
        parent of this solid.  An empty tuple means the solid is a direct
        child of the root.
    solid_id:
        Index into :attr:`NormalizedShape.solids`.
    """

    path: Tuple[int, ...]
    solid_id: int


@dataclass
class NormalizedShape:
    """Result of normalizing a ``TopoDS_Compound``.

    Attributes
    ----------
    solids:
        One :class:`SolidData` per extracted ``TopoDS_Solid``, in depth-first
        traversal order.
    assembly_context:
        Present only when :func:`normalize_shape` is called with
        ``keep_context=True``.  One :class:`AssemblyNode` per solid recording
        its location in the assembly tree.
    """

    solids: List[SolidData]
    assembly_context: Optional[List[AssemblyNode]] = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def normalize_shape(
    compound: TopoDS_Shape,
    keep_context: bool = False,
) -> NormalizedShape:
    """Normalize a ``TopoDS_Shape`` into a structured :class:`NormalizedShape`.

    Traverses the topology tree, extracts every ``TopoDS_Solid``, computes
    per-face geometric attributes, and builds a face-adjacency graph via
    shared edges.  Shapes at the SHELL, WIRE, EDGE, or VERTEX level that have
    no solid parent are silently ignored (wireframe / construction-only
    geometry).

    Parameters
    ----------
    compound:
        Root shape to normalize (usually a ``TopoDS_Compound`` loaded from a
        STEP file).  A bare ``TopoDS_Solid`` is also accepted.
    keep_context:
        When ``True``, populate :attr:`NormalizedShape.assembly_context` so
        each solid carries its path in the assembly hierarchy.

    Returns
    -------
    NormalizedShape
        Structured representation of all solids found in *compound*.
    """
    solid_shapes: List[TopoDS_Solid] = []
    context: Optional[List[AssemblyNode]] = [] if keep_context else None

    _collect_solids(compound, solid_shapes, context, path=())

    solids: List[SolidData] = [
        _process_solid(solid, idx) for idx, solid in enumerate(solid_shapes)
    ]
    return NormalizedShape(solids=solids, assembly_context=context)


def extract_solids(compound: TopoDS_Shape) -> List[TopoDS_Solid]:
    """Return the list of ``TopoDS_Solid`` objects extracted from *compound*.

    The order matches the ``solid_id`` assigned by :func:`normalize_shape`.
    This is useful when you need both the normalized metadata *and* the raw
    OCC solid objects for further processing (e.g., per-face tessellation for
    visualization).

    Parameters
    ----------
    compound:
        Root shape (same value passed to :func:`normalize_shape`).

    Returns
    -------
    List[TopoDS_Solid]
        Solids in depth-first traversal order.
    """
    solid_shapes: List[TopoDS_Solid] = []
    _collect_solids(compound, solid_shapes, context=None, path=())
    return solid_shapes


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _collect_solids(
    shape: TopoDS_Shape,
    out: List[TopoDS_Solid],
    context: Optional[List[AssemblyNode]],
    path: Tuple[int, ...],
) -> None:
    """Recursively extract ``TopoDS_Solid`` objects from *shape*.

    Silently skips SHELL, WIRE, EDGE, and VERTEX shapes that have no solid
    ancestor (wireframe / construction-only geometry).
    """
    shape_type = shape.ShapeType()

    if shape_type == TopAbs_SOLID:
        solid_idx = len(out)
        out.append(topods.Solid(shape))
        if context is not None:
            context.append(AssemblyNode(path=path, solid_id=solid_idx))
        return

    if shape_type not in (TopAbs_COMPOUND, TopAbs_COMPSOLID):
        # Ignore wireframe-only / construction-only topology
        return

    it = TopoDS_Iterator(shape)
    child_idx = 0
    while it.More():
        _collect_solids(it.Value(), out, context, path + (child_idx,))
        child_idx += 1
        it.Next()


def _process_solid(solid: TopoDS_Solid, solid_id: int) -> SolidData:
    """Build a :class:`SolidData` for a single solid.

    Enumerates all faces, computes their attributes, then builds the
    face-adjacency graph by discovering which pairs of faces share an edge.
    """
    # Build indexed maps so we can assign stable IDs and look up shapes.
    face_map = TopTools_IndexedMapOfShape()
    exp = TopExp_Explorer(solid, TopAbs_FACE)
    while exp.More():
        face_map.Add(exp.Current())
        exp.Next()

    edge_map = TopTools_IndexedMapOfShape()
    exp = TopExp_Explorer(solid, TopAbs_EDGE)
    while exp.More():
        edge_map.Add(exp.Current())
        exp.Next()

    # Compute face attributes; simultaneously record which edges each face owns.
    faces: List[FaceData] = []
    edge_to_face_ids: Dict[int, List[int]] = {}

    for fi in range(1, face_map.Size() + 1):
        face = topods.Face(face_map.FindKey(fi))
        face_id = fi - 1  # convert to 0-based
        faces.append(_compute_face_attributes(face, face_id))

        edge_exp = TopExp_Explorer(face, TopAbs_EDGE)
        seen_edges: set = set()
        while edge_exp.More():
            edge_key = edge_map.FindIndex(edge_exp.Current())
            if edge_key > 0 and edge_key not in seen_edges:
                seen_edges.add(edge_key)
                edge_to_face_ids.setdefault(edge_key, []).append(face_id)
            edge_exp.Next()

    # Build adjacency from edges shared between two or more faces.
    adjacency: Dict[int, List[int]] = {i: [] for i in range(len(faces))}
    for sharing in edge_to_face_ids.values():
        for i in range(len(sharing)):
            for j in range(i + 1, len(sharing)):
                a, b = sharing[i], sharing[j]
                if b not in adjacency[a]:
                    adjacency[a].append(b)
                if a not in adjacency[b]:
                    adjacency[b].append(a)

    return SolidData(solid_id=solid_id, faces=faces, adjacency=adjacency)


def _compute_face_attributes(face, face_id: int) -> FaceData:
    """Extract geometric attributes from a single ``TopoDS_Face``."""
    adaptor = BRepAdaptor_Surface(face)
    surface_type = _SURFACE_TYPE_NAMES.get(adaptor.GetType(), "Other")

    props = GProp_GProps()
    brepgprop.SurfaceProperties(face, props)
    area = props.Mass()
    cog = props.CentreOfMass()
    center = (cog.X(), cog.Y(), cog.Z())

    normal: Optional[Tuple[float, float, float]] = None
    if adaptor.GetType() == GeomAbs_Plane:
        ax = adaptor.Plane().Axis().Direction()
        normal = (ax.X(), ax.Y(), ax.Z())

    bbox = Bnd_Box()
    brepbndlib.Add(face, bbox)
    if not bbox.IsVoid():
        xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
    else:
        xmin = ymin = zmin = xmax = ymax = zmax = 0.0

    return FaceData(
        face_id=face_id,
        surface_type=surface_type,
        area=area,
        center=center,
        normal=normal,
        bounding_box=(xmin, ymin, zmin, xmax, ymax, zmax),
    )


__all__ = [
    "normalize_shape",
    "extract_solids",
    "NormalizedShape",
    "SolidData",
    "FaceData",
    "AssemblyNode",
]
