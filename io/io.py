"""
Layer 1: Geometry Input Layer

Handles loading and initial processing of various geometry formats:
- STEP/IGES (B-Rep): pythonocc-core
- IFC/BIM: ifcOpenShell
- STL/OBJ/VTK (Mesh): meshio

Provides unified handoff to Layer 2 with either B-Rep objects or normalized meshes.
"""

import numpy as np
from typing import Optional, Union, Dict, Any
from abc import ABC, abstractmethod

# Library imports
try:
    from OCC.Core.TopoDS import TopoDS_Shape
    from OCC.Core.STEPControl import STEPControl_Reader
    from OCC.Core.IGESControl import IGESControl_Reader
    from OCC.Core.BRepMesh import BRepMesh_IncrementalMesh
    from OCC.Core.BRep import BRep_Tool
    from OCC.Core.TopExp import TopExp_Explorer
    from OCC.Core.TopAbs import TopAbs_FACE
    OCC_AVAILABLE = True
    ShapeType = TopoDS_Shape
except ImportError:
    OCC_AVAILABLE = False
    print("Warning: pythonocc-core not available")
    ShapeType = Any

try:
    import ifcopenshell
    import ifcopenshell.geom
    IFC_AVAILABLE = True
except ImportError:
    IFC_AVAILABLE = False
    print("Warning: ifcopenshell not available")

try:
    import meshio
    MESHIO_AVAILABLE = True
except ImportError:
    MESHIO_AVAILABLE = False
    print("Warning: meshio not available")


class Geometry:
    """
    Unified geometry representation for handoff to Layer 2.

    Can represent either:
    - B-Rep topology (exact geometry)
    - Tessellated mesh (discrete geometry)
    """

    def __init__(self,
                 is_brep: bool = False,
                 shape: Optional[ShapeType] = None,
                 points: Optional[np.ndarray] = None,
                 cells: Optional[np.ndarray] = None,
                 metadata: Optional[Dict[str, Any]] = None):
        self.is_brep = is_brep
        self.shape = shape  # OCC TopoDS_Shape for B-Rep
        self.points = points  # Nx3 numpy array for mesh vertices
        self.cells = cells  # Mx3 or Mx4 numpy array for mesh faces/cells
        self.metadata = metadata or {}  # IFC metadata, material properties, etc.

    def tessellate(self, deflection: float = 0.1) -> 'Geometry':
        """
        Convert B-Rep to tessellated mesh if not already meshed.
        """
        if not self.is_brep:
            return self  # Already a mesh

        if not OCC_AVAILABLE:
            raise ImportError("pythonocc-core required for tessellation")

        # Tessellate the B-Rep
        mesher = BRepMesh_IncrementalMesh(self.shape, deflection)
        mesher.Perform()

        # Extract mesh data
        points = []
        faces = []

        explorer = TopExp_Explorer(self.shape, TopAbs_FACE)
        while explorer.More():
            face = explorer.Current()
            triangulation = BRep_Tool.Triangulation(face, None)
            if triangulation:
                # Get vertices
                nodes = triangulation.Nodes()
                for i in range(1, triangulation.NbNodes() + 1):
                    p = nodes.Value(i)
                    points.append([p.X(), p.Y(), p.Z()])

                # Get triangles
                triangles = triangulation.Triangles()
                for i in range(1, triangulation.NbTriangles() + 1):
                    t = triangles.Value(i)
                    faces.append([t.Get(1)-1, t.Get(2)-1, t.Get(3)-1])  # 0-based indexing

            explorer.Next()

        return Geometry(
            is_brep=False,
            points=np.array(points),
            cells=np.array(faces),
            metadata=self.metadata
        )


class GeometryLoader(ABC):
    """
    Abstract base class for geometry loaders.
    """

    @abstractmethod
    def can_load(self, filepath: str) -> bool:
        """Check if this loader can handle the given file."""
        pass

    @abstractmethod
    def load(self, filepath: str) -> Geometry:
        """Load geometry from file."""
        pass


class OCCLoader(GeometryLoader):
    """
    Loader for STEP/IGES files using pythonocc-core.
    Handles B-Rep geometry.
    """

    def can_load(self, filepath: str) -> bool:
        if not OCC_AVAILABLE:
            return False
        ext = filepath.lower().split('.')[-1]
        return ext in ['step', 'stp', 'iges', 'igs']

    def load(self, filepath: str) -> Geometry:
        if not OCC_AVAILABLE:
            raise ImportError("pythonocc-core required for STEP/IGES loading")

        ext = filepath.lower().split('.')[-1]

        if ext in ['step', 'stp']:
            reader = STEPControl_Reader()
            reader.ReadFile(filepath)
            reader.TransferRoots()
            shape = reader.OneShape()
        elif ext in ['iges', 'igs']:
            reader = IGESControl_Reader()
            reader.ReadFile(filepath)
            reader.TransferRoots()
            shape = reader.OneShape()
        else:
            raise ValueError(f"Unsupported format: {ext}")

        return Geometry(is_brep=True, shape=shape)


class IFCLoader(GeometryLoader):
    """
    Loader for IFC files using ifcOpenShell.
    Handles BIM models with semantic metadata.
    """

    def can_load(self, filepath: str) -> bool:
        if not IFC_AVAILABLE:
            return False
        ext = filepath.lower().split('.')[-1]
        return ext == 'ifc'

    def load(self, filepath: str) -> Geometry:
        if not IFC_AVAILABLE:
            raise ImportError("ifcopenshell required for IFC loading")

        # Load IFC model
        model = ifcopenshell.open(filepath)

        # For now, we'll tessellate all geometry into a single mesh
        # In a full implementation, you might want to handle individual elements
        settings = ifcopenshell.geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)

        # Collect all geometric elements
        elements = model.by_type("IfcProduct")  # Or more specific types

        all_points = []
        all_faces = []
        metadata = {"ifc_model": model, "elements": []}

        for element in elements:
            try:
                geom = ifcopenshell.geom.create_shape(settings, element)
                if geom:
                    # Extract mesh from IFC geometry
                    verts = geom.geometry.verts
                    faces = geom.geometry.faces

                    # Convert to numpy arrays
                    points = np.array(verts).reshape(-1, 3)
                    faces = np.array(faces).reshape(-1, 3)

                    # Offset indices for combined mesh
                    offset = len(all_points)
                    all_points.extend(points)
                    all_faces.extend(faces + offset)

                    # Store element metadata
                    metadata["elements"].append({
                        "id": element.id(),
                        "type": element.is_a(),
                        "name": getattr(element, 'Name', None),
                        "geometry": geom
                    })

            except Exception as e:
                print(f"Warning: Failed to process element {element.id()}: {e}")

        return Geometry(
            is_brep=False,  # IFC loader produces tessellated meshes
            points=np.array(all_points),
            cells=np.array(all_faces),
            metadata=metadata
        )


class MeshLoader(GeometryLoader):
    """
    Loader for mesh files using meshio.
    Handles STL, OBJ, VTK, and other mesh formats.
    """

    def can_load(self, filepath: str) -> bool:
        if not MESHIO_AVAILABLE:
            return False
        ext = filepath.lower().split('.')[-1]
        supported = ['stl', 'obj', 'vtk', 'ply', 'off', 'vtu', 'vtp']  # Common mesh formats
        return ext in supported

    def load(self, filepath: str) -> Geometry:
        if not MESHIO_AVAILABLE:
            raise ImportError("meshio required for mesh loading")

        mesh = meshio.read(filepath)

        # Normalize to triangles if needed
        if mesh.cells:
            # Use the first cell type, or prefer triangles
            cell_type = None
            cells = None

            for cell_block in mesh.cells:
                if cell_block.type == "triangle":
                    cells = cell_block.data
                    cell_type = "triangle"
                    break
                elif cell_block.type == "quad":
                    # Convert quads to triangles
                    cells = []
                    for quad in cell_block.data:
                        cells.extend([[quad[0], quad[1], quad[2]], [quad[0], quad[2], quad[3]]])
                    cells = np.array(cells)
                    cell_type = "triangle"
                    break

            if cells is None:
                # Use first available
                cells = mesh.cells[0].data
                cell_type = mesh.cells[0].type

            return Geometry(
                is_brep=False,
                points=mesh.points,
                cells=cells,
                metadata={"cell_type": cell_type, "meshio_mesh": mesh}
            )
        else:
            raise ValueError("No cells found in mesh file")


class GeometryInputLayer:
    """
    Main interface for Layer 1 geometry input.
    Automatically selects appropriate loader based on file type.
    """

    def __init__(self):
        self.loaders = [
            OCCLoader(),
            IFCLoader(),
            MeshLoader()
        ]

    def load_geometry(self, filepath: str) -> Geometry:
        """
        Load geometry from file using appropriate loader.
        """
        for loader in self.loaders:
            if loader.can_load(filepath):
                return loader.load(filepath)

        raise ValueError(f"No suitable loader found for {filepath}")

    def load_and_tessellate(self, filepath: str, deflection: float = 0.1) -> Geometry:
        """
        Load geometry and ensure it's tessellated (mesh representation).
        Useful when Layer 2 expects mesh data.
        """
        geom = self.load_geometry(filepath)
        return geom.tessellate(deflection)


# Convenience functions
def load_step_iges(filepath: str) -> Geometry:
    """Load STEP or IGES file."""
    return OCCLoader().load(filepath)

def load_ifc(filepath: str) -> Geometry:
    """Load IFC file."""
    return IFCLoader().load(filepath)

def load_mesh(filepath: str) -> Geometry:
    """Load mesh file (STL, OBJ, etc.)."""
    return MeshLoader().load(filepath)

# Global instance for easy access
input_layer = GeometryInputLayer()