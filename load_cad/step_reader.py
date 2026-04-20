"""STEP file reader utilities using pythonocc-core."""

from __future__ import annotations

import logging
import os
from typing import List, Tuple

from OCC.Core.BRep import BRep_Builder, BRep_Tool
from OCC.Core.BRepMesh import BRepMesh_IncrementalMesh
from OCC.Core.IFSelect import IFSelect_RetDone
from OCC.Core.STEPControl import STEPControl_Reader
from OCC.Core.TopoDS import TopoDS_Compound, TopoDS_Shape, topods
from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopAbs import TopAbs_FACE
from OCC.Core.TopLoc import TopLoc_Location

LOGGER = logging.getLogger(__name__)


class StepReadError(RuntimeError):
    """Raised when STEP files cannot be read or transferred."""


def read_step(path: str) -> List[TopoDS_Shape]:
    """Read a STEP file and return a list of top-level shapes.

    Each element corresponds to a top-level transfer from the STEP file.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(path)

    reader = STEPControl_Reader()
    status = reader.ReadFile(path)
    if status != IFSelect_RetDone:
        raise StepReadError(f"Failed to read STEP file: {path}")

    # Transfer all roots into TopoDS shapes.
    transferred = reader.TransferRoots()
    if transferred == 0:
        raise StepReadError(f"No roots transferred from STEP file: {path}")

    shapes: List[TopoDS_Shape] = []
    for index in range(1, reader.NbShapes() + 1):
        shape = reader.Shape(index)
        if shape.IsNull():
            LOGGER.warning("Null shape encountered at index %s in %s", index, path)
            continue
        shapes.append(shape)

    if not shapes:
        raise StepReadError(f"No shapes extracted from STEP file: {path}")

    return shapes


def read_step_single(path: str) -> TopoDS_Shape:
    """Read a STEP file and return a single TopoDS_Shape.

    If the STEP file contains multiple top-level shapes, they are combined
    into a compound.
    """
    shapes = read_step(path)
    if len(shapes) == 1:
        return shapes[0]

    compound = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(compound)
    for shape in shapes:
        builder.Add(compound, shape)
    return compound


def tessellate_shape(
    shape: TopoDS_Shape,
    deflection: float = 0.1,
    angle: float = 0.5,
) -> Tuple[List[Tuple[float, float, float]], List[Tuple[int, int, int]]]:
    """Tessellate a shape into vertices and triangle indices.

    Returns a pair of lists: vertices (x, y, z) and faces (i, j, k) with
    0-based indices.
    """
    if shape.IsNull():
        raise ValueError("Cannot tessellate a null shape")

    mesher = BRepMesh_IncrementalMesh(shape, deflection, False, angle, True)
    mesher.Perform()

    vertices: List[Tuple[float, float, float]] = []
    faces: List[Tuple[int, int, int]] = []

    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        face = topods.Face(explorer.Current())
        location = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation(face, location)
        if triangulation is None:
            explorer.Next()
            continue

        transformation = location.Transformation()

        offset = len(vertices)
        if hasattr(triangulation, "Nodes"):
            nodes = triangulation.Nodes()
            for idx in range(1, nodes.Length() + 1):
                point = nodes.Value(idx)
                point = point.Transformed(transformation)
                vertices.append((point.X(), point.Y(), point.Z()))
        else:
            node_count = triangulation.NbNodes()
            for idx in range(1, node_count + 1):
                point = triangulation.Node(idx)
                point = point.Transformed(transformation)
                vertices.append((point.X(), point.Y(), point.Z()))

        if hasattr(triangulation, "Triangles"):
            triangles = triangulation.Triangles()
            for idx in range(1, triangles.Length() + 1):
                triangle = triangles.Value(idx)
                n1, n2, n3 = triangle.Get()
                faces.append((offset + n1 - 1, offset + n2 - 1, offset + n3 - 1))
        else:
            tri_count = triangulation.NbTriangles()
            for idx in range(1, tri_count + 1):
                triangle = triangulation.Triangle(idx)
                n1, n2, n3 = triangle.Get()
                faces.append((offset + n1 - 1, offset + n2 - 1, offset + n3 - 1))

        explorer.Next()

    if not vertices or not faces:
        LOGGER.warning("No tessellation produced for the provided shape")

    return vertices, faces


__all__ = [
    "read_step",
    "read_step_single",
    "tessellate_shape",
    "StepReadError",
]
