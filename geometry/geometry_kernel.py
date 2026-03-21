"""
Geometry Kernel - Layer 2

This module implements the geometry kernel with two parallel tracks:
- B-Rep track: OCCT-based operations on exact geometry
- Mesh track: trimesh/Open3D/libigl operations on discretized geometry

The tracks remain separate until Layer 3 explicitly merges results.
"""

from typing import Dict, Any, Optional, Tuple, List
import numpy as np
from dataclasses import dataclass

from .brep_kernel import BRepKernel
from .mesh_kernel import MeshKernel
from .tessellation import TessellationEngine


@dataclass
class GeometryInputs:
    """Inputs from Layer 1"""
    brep_shape: Optional[Any] = None  # OCC Shape from pythonocc-core
    mesh_vertices: Optional[np.ndarray] = None  # V array
    mesh_faces: Optional[np.ndarray] = None     # F array


@dataclass
class BRepResults:
    """Results from B-Rep track"""
    topology_info: Dict[str, Any]
    curvature_data: Dict[str, Any]
    boolean_results: Dict[str, Any]


@dataclass
class MeshResults:
    """Results from mesh track"""
    thickness_analysis: Dict[str, Any]
    accessibility_checks: Dict[str, Any]
    feature_analysis: Dict[str, Any]
    repaired_mesh: Optional[Tuple[np.ndarray, np.ndarray]]  # V, F


@dataclass
class GeometryOutputs:
    """Outputs to Layer 3"""
    brep_results: BRepResults
    mesh_results: MeshResults


class GeometryKernel:
    """
    Main geometry kernel orchestrating B-Rep and mesh analysis tracks.
    """

    def __init__(self):
        self.brep_kernel = BRepKernel()
        self.mesh_kernel = MeshKernel()
        self.tessellation_engine = TessellationEngine()

    def process_geometry(self, inputs: GeometryInputs,
                        tessellation_config: Optional[Dict[str, Any]] = None) -> GeometryOutputs:
        """
        Process geometry through both tracks.

        Args:
            inputs: Geometry inputs from Layer 1
            tessellation_config: Configuration for B-Rep to mesh conversion
                               (chord tolerance, etc.)

        Returns:
            GeometryOutputs with separate B-Rep and mesh results
        """
        # Default tessellation config
        if tessellation_config is None:
            tessellation_config = {
                'chord_tolerance': 0.1,
                'angular_tolerance': 0.1
            }

        # Process B-Rep track
        brep_results = self._process_brep_track(inputs.brep_shape)

        # Process mesh track
        mesh_vertices, mesh_faces = self._prepare_mesh_inputs(
            inputs, tessellation_config
        )
        mesh_results = self._process_mesh_track(mesh_vertices, mesh_faces)

        return GeometryOutputs(
            brep_results=brep_results,
            mesh_results=mesh_results
        )

    def _process_brep_track(self, brep_shape: Optional[Any]) -> BRepResults:
        """Process B-Rep geometry through OCCT operations."""
        if brep_shape is None:
            return BRepResults(
                topology_info={},
                curvature_data={},
                boolean_results={}
            )

        # Topology queries
        topology_info = self.brep_kernel.get_topology_info(brep_shape)

        # Curvature analysis
        curvature_data = self.brep_kernel.analyze_curvature(brep_shape)

        # Boolean operations (if needed)
        boolean_results = {}  # Placeholder for boolean ops

        return BRepResults(
            topology_info=topology_info,
            curvature_data=curvature_data,
            boolean_results=boolean_results
        )

    def _prepare_mesh_inputs(self, inputs: GeometryInputs,
                           tessellation_config: Dict[str, Any]) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """Prepare mesh inputs, tessellating from B-Rep if needed."""
        # If mesh is already provided, use it
        if inputs.mesh_vertices is not None and inputs.mesh_faces is not None:
            return inputs.mesh_vertices, inputs.mesh_faces

        # Otherwise, tessellate from B-Rep
        if inputs.brep_shape is not None:
            return self.tessellation_engine.tessellate_brep(
                inputs.brep_shape, **tessellation_config
            )

        return None, None

    def _process_mesh_track(self, vertices: Optional[np.ndarray],
                          faces: Optional[np.ndarray]) -> MeshResults:
        """Process mesh geometry through trimesh/Open3D/libigl operations."""
        if vertices is None or faces is None:
            return MeshResults(
                thickness_analysis={},
                accessibility_checks={},
                feature_analysis={},
                repaired_mesh=None
            )

        # Wall thickness analysis (trimesh)
        thickness_analysis = self.mesh_kernel.analyze_thickness(vertices, faces)

        # Accessibility checks (trimesh)
        accessibility_checks = self.mesh_kernel.check_accessibility(vertices, faces)

        # Feature analysis (libigl)
        feature_analysis = self.mesh_kernel.analyze_features(vertices, faces)

        # Mesh repair (if needed)
        repaired_mesh = self.mesh_kernel.repair_mesh(vertices, faces)

        return MeshResults(
            thickness_analysis=thickness_analysis,
            accessibility_checks=accessibility_checks,
            feature_analysis=feature_analysis,
            repaired_mesh=repaired_mesh
        )