"""
Tessellation Engine - B-Rep to Mesh conversion

Handles the conversion from exact B-Rep geometry to discretized mesh
with configurable chord and angular tolerances.
"""

from typing import Tuple, Optional, Dict, Any
import numpy as np

try:
    from OCC.Core.TopoDS import TopoDS_Shape
    from OCC.Core.BRepMesh import BRepMesh_IncrementalMesh
    from OCC.Core.StlAPI import StlAPI_Writer
    from OCC.Core.BRep import BRep_Tool
    from OCC.Core.TopExp import TopExp_Explorer
    from OCC.Core.TopAbs import TopAbs_FACE
    from OCC.Core.TopLoc import TopLoc_Location
    from OCC.Core.Poly import Poly_Triangulation
    import tempfile
    import os
    OCC_AVAILABLE = True
    ShapeType = TopoDS_Shape
except ImportError:
    OCC_AVAILABLE = False
    ShapeType = Any

try:
    import trimesh
    TRIMESH_AVAILABLE = True
except ImportError:
    TRIMESH_AVAILABLE = False


class TessellationEngine:
    """
    Converts B-Rep shapes to triangle meshes with configurable tolerances.
    """

    def __init__(self):
        if not OCC_AVAILABLE:
            raise ImportError("pythonocc-core not available")
        if not TRIMESH_AVAILABLE:
            raise ImportError("trimesh not available")

    def tessellate_brep(self, shape: ShapeType,
                       chord_tolerance: float = 0.1,
                       angular_tolerance: float = 0.1) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """
        Tessellate B-Rep shape into triangle mesh.

        Args:
            shape: OCCT TopoDS_Shape to tessellate
            chord_tolerance: Maximum chordal deviation (mm)
            angular_tolerance: Maximum angular deviation (radians)

        Returns:
            Tuple of (vertices, faces) as numpy arrays
        """
        if not OCC_AVAILABLE or not isinstance(shape, TopoDS_Shape):
            return None, None

        # Create incremental mesh
        mesh = BRepMesh_IncrementalMesh(shape, chord_tolerance, False, angular_tolerance, True)

        # Extract triangulation data
        vertices = []
        faces = []
        vertex_offset = 0

        # Iterate through faces
        face_explorer = TopExp_Explorer(shape, TopAbs_FACE)
        while face_explorer.More():
            face = face_explorer.Current()

            # Get triangulation for this face
            location = TopLoc_Location()
            triangulation = BRep_Tool.Triangulation(face, location)

            if triangulation is not None:
                # Get vertices for this face
                face_vertices = []
                for i in range(1, triangulation.NbNodes() + 1):
                    pnt = triangulation.Node(i)
                    pnt.Transform(location.Transformation())
                    face_vertices.append([pnt.X(), pnt.Y(), pnt.Z()])

                # Get triangles for this face
                for i in range(1, triangulation.NbTriangles() + 1):
                    triangle = triangulation.Triangle(i)
                    v1, v2, v3 = triangle.Get()
                    # Adjust for 0-based indexing and global vertex offset
                    faces.append([v1 - 1 + vertex_offset, v2 - 1 + vertex_offset, v3 - 1 + vertex_offset])

                vertices.extend(face_vertices)
                vertex_offset += len(face_vertices)

            face_explorer.Next()

        if not vertices or not faces:
            return None, None

        return np.array(vertices), np.array(faces)

    def tessellate_to_stl(self, shape: ShapeType,
                         filename: str,
                         chord_tolerance: float = 0.1,
                         angular_tolerance: float = 0.1) -> bool:
        """
        Tessellate B-Rep and save as STL file.

        Args:
            shape: OCCT TopoDS_Shape
            filename: Output STL filename
            chord_tolerance: Maximum chordal deviation
            angular_tolerance: Maximum angular deviation

        Returns:
            True if successful
        """
        if not OCC_AVAILABLE or not isinstance(shape, TopoDS_Shape):
            return False

        # Create mesh
        mesh = BRepMesh_IncrementalMesh(shape, chord_tolerance, False, angular_tolerance, True)

        # Write to STL
        writer = StlAPI_Writer()
        writer.SetASCIIMode(False)  # Binary STL

        try:
            success = writer.Write(shape, filename)
            return success
        except:
            return False

    def load_stl_as_mesh(self, filename: str) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """
        Load STL file as mesh arrays using trimesh.

        Args:
            filename: STL filename

        Returns:
            Tuple of (vertices, faces)
        """
        try:
            mesh = trimesh.load(filename)
            return mesh.vertices, mesh.faces
        except:
            return None, None

    def tessellate_with_quality_control(self, shape: ShapeType,
                                      target_edge_length: float = 1.0,
                                      min_angle: float = 20.0) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """
        Tessellate with quality control parameters.

        Args:
            shape: OCCT TopoDS_Shape
            target_edge_length: Target edge length for triangles
            min_angle: Minimum triangle angle in degrees

        Returns:
            Tuple of (vertices, faces)
        """
        # Simplified - use chord tolerance based on target edge length
        chord_tolerance = target_edge_length * 0.1
        angular_tolerance = np.radians(min_angle * 0.1)

        return self.tessellate_brep(shape, chord_tolerance, angular_tolerance)