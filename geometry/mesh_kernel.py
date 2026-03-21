"""
Mesh Kernel - Mesh-based geometry operations

Handles thickness analysis, accessibility checks, and feature extraction
using trimesh, Open3D, and libigl.
"""

from typing import Dict, Any, Tuple, Optional, List
import numpy as np

try:
    import trimesh
    TRIMESH_AVAILABLE = True
except ImportError:
    TRIMESH_AVAILABLE = False

try:
    import open3d as o3d
    OPEN3D_AVAILABLE = True
except ImportError:
    OPEN3D_AVAILABLE = False

try:
    import compas_libigl as igl
    LIBIGL_AVAILABLE = True
except ImportError:
    LIBIGL_AVAILABLE = False


class MeshKernel:
    """
    Mesh geometry operations using trimesh, Open3D, and libigl.
    """

    def __init__(self):
        if not TRIMESH_AVAILABLE:
            raise ImportError("trimesh not available. Install with: pip install trimesh")
        if not OPEN3D_AVAILABLE:
            raise ImportError("open3d not available. Install with: conda install open3d")
        if not LIBIGL_AVAILABLE:
            print("Warning: compas_libigl not available. Some features will be limited.")

    def analyze_thickness(self, vertices: np.ndarray, faces: np.ndarray) -> Dict[str, Any]:
        """
        Analyze wall thickness using ray casting.

        Args:
            vertices: V array (N, 3)
            faces: F array (M, 3)

        Returns:
            Dictionary with thickness statistics
        """
        if not TRIMESH_AVAILABLE:
            return {}

        # Create trimesh object
        mesh = trimesh.Trimesh(vertices=vertices, faces=faces)

        # Sample points on surface
        samples, face_indices = trimesh.sample.sample_surface(mesh, count=1000)

        thicknesses = []
        for point, face_idx in zip(samples, face_indices):
            # Cast ray inward (simplified - assumes outward normals)
            face_normal = mesh.face_normals[face_idx]
            ray_origin = point + 0.001 * face_normal  # Offset slightly
            ray_direction = -face_normal  # Cast inward

            # Find intersection
            locations, index_ray, index_tri = mesh.ray.intersects_location(
                ray_origins=[ray_origin],
                ray_directions=[ray_direction]
            )

            if len(locations) > 0:
                # Calculate distance to intersection
                distance = np.linalg.norm(locations[0] - ray_origin)
                thicknesses.append(distance)

        if thicknesses:
            return {
                'min_thickness': float(np.min(thicknesses)),
                'max_thickness': float(np.max(thicknesses)),
                'mean_thickness': float(np.mean(thicknesses)),
                'std_thickness': float(np.std(thicknesses)),
                'thickness_histogram': np.histogram(thicknesses, bins=20)
            }
        else:
            return {'error': 'No thickness measurements possible'}

    def check_accessibility(self, vertices: np.ndarray, faces: np.ndarray) -> Dict[str, Any]:
        """
        Check accessibility and clearance.

        Args:
            vertices: V array (N, 3)
            faces: F array (M, 3)

        Returns:
            Dictionary with accessibility metrics
        """
        if not TRIMESH_AVAILABLE:
            return {}

        mesh = trimesh.Trimesh(vertices=vertices, faces=faces)

        # Check watertightness
        is_watertight = mesh.is_watertight

        # Check for holes
        holes = len(mesh.fill_holes()) if not is_watertight else 0

        # Volume calculation
        try:
            volume = mesh.volume
        except:
            volume = 0.0

        # Surface area
        surface_area = mesh.area

        return {
            'is_watertight': is_watertight,
            'hole_count': holes,
            'volume': float(volume),
            'surface_area': float(surface_area)
        }

    def analyze_features(self, vertices: np.ndarray, faces: np.ndarray) -> Dict[str, Any]:
        """
        Analyze sharp features and curvature using libigl.

        Args:
            vertices: V array (N, 3)
            faces: F array (M, 3)

        Returns:
            Dictionary with feature analysis results
        """
        if not LIBIGL_AVAILABLE:
            return {'error': 'compas_libigl not available'}

        # Convert to compas mesh format if needed
        # For now, return placeholder
        return {
            'sharp_features_detected': 0,
            'feature_edges': [],
            'dihedral_angles': []
        }

    def repair_mesh(self, vertices: np.ndarray, faces: np.ndarray) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        """
        Repair mesh using Open3D or trimesh.

        Args:
            vertices: V array (N, 3)
            faces: F array (M, 3)

        Returns:
            Repaired mesh as (V, F) tuple, or None if no repair needed
        """
        if not OPEN3D_AVAILABLE:
            return None

        # Create Open3D mesh
        o3d_mesh = o3d.geometry.TriangleMesh()
        o3d_mesh.vertices = o3d.utility.Vector3dVector(vertices)
        o3d_mesh.triangles = o3d.utility.Vector3iVector(faces)

        # Check if mesh needs repair
        o3d_mesh.compute_vertex_normals()

        # Basic repair: remove degenerate triangles, etc.
        o3d_mesh.remove_degenerate_triangles()
        o3d_mesh.remove_duplicated_triangles()
        o3d_mesh.remove_duplicated_vertices()
        o3d_mesh.remove_non_manifold_edges()

        # Get repaired arrays
        repaired_vertices = np.asarray(o3d_mesh.vertices)
        repaired_faces = np.asarray(o3d_mesh.triangles)

        return repaired_vertices, repaired_faces

    def compute_curvature_tensors(self, vertices: np.ndarray, faces: np.ndarray) -> Dict[str, Any]:
        """
        Compute curvature tensors using libigl.

        Args:
            vertices: V array (N, 3)
            faces: F array (M, 3)

        Returns:
            Dictionary with curvature data
        """
        if not LIBIGL_AVAILABLE:
            return {'error': 'compas_libigl not available'}

        # Placeholder for libigl curvature computation
        return {
            'mean_curvature': np.zeros(len(vertices)),
            'gaussian_curvature': np.zeros(len(vertices))
        }

    def parameterize_mesh(self, vertices: np.ndarray, faces: np.ndarray) -> Dict[str, Any]:
        """
        Compute UV parameterization.

        Args:
            vertices: V array (N, 3)
            faces: F array (M, 3)

        Returns:
            Dictionary with UV coordinates
        """
        if not LIBIGL_AVAILABLE:
            return {'error': 'compas_libigl not available'}

        # Placeholder for parameterization
        return {
            'uv_coordinates': np.zeros((len(vertices), 2))
        }