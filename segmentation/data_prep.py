# segmentation/data_prep.py
"""
Data preparation utilities for Layer 4 ML models.

Converts Layer 3 outputs (CheckResult list + feature vectors) into
formats suitable for PyTorch Geometric (B-Rep graphs) and PointNet++ (point clouds).
"""

import numpy as np
from typing import List, Dict, Any, Tuple
import networkx as nx

try:
    from torch_geometric.data import Data
    import torch
    TORCH_GEOMETRIC_AVAILABLE = True
except ImportError:
    TORCH_GEOMETRIC_AVAILABLE = False
    # Mock classes for when PyTorch Geometric is not available
    class Data:
        def __init__(self, x=None, edge_index=None, edge_attr=None, batch=None):
            self.x = x
            self.edge_index = edge_index
            self.edge_attr = edge_attr
            self.batch = batch

    class MockTensor:
        def __init__(self, data):
            self.data = np.array(data)

        @property
        def shape(self):
            return self.data.shape

        @property
        def T(self):
            return MockTensor(self.data.T)

        def t(self):
            return self.T

        def contiguous(self):
            return self

        def numpy(self):
            return self.data

        def astype(self, dtype):
            return MockTensor(self.data.astype(dtype))

        def __len__(self):
            return len(self.data)

        def __getitem__(self, key):
            return self.data[key]

        def __array__(self):
            return self.data

        def __iter__(self):
            return iter(self.data)

        def __repr__(self):
            return f"MockTensor({self.data})"

    class torch:
        Tensor = MockTensor
        @staticmethod
        def tensor(data, dtype=None):
            return MockTensor(data)

        @staticmethod
        def empty(*shape, dtype=None):
            data = np.empty(shape, dtype=dtype)
            return MockTensor(data)

        float = np.float32
        long = np.int64
        int64 = np.int64

from rules.rule_engine import CheckResult


class BRepGraphBuilder:
    """Converts B-Rep topology into PyTorch Geometric graph format."""

    def __init__(self):
        pass

    def build_graph(self, brep_data: Dict[str, Any]) -> Data:
        """
        Build PyTorch Geometric Data object from B-Rep topology.

        Args:
            brep_data: Dictionary containing faces, edges, and adjacency info

        Returns:
            PyTorch Geometric Data object with node/edge features
        """
        # Extract topology
        faces = brep_data.get('faces', [])
        edges = brep_data.get('edges', [])
        adjacency = brep_data.get('adjacency', [])

        # Create node features (face features)
        face_features = []
        for face in faces:
            # Extract geometric features: area, normal, curvature, etc.
            features = self._extract_face_features(face)
            face_features.append(features)

        # Create edge features (edge features)
        edge_features = []
        edge_index = []

        for i, edge in enumerate(edges):
            features = self._extract_edge_features(edge)
            edge_features.append(features)

            # Build adjacency: which faces share this edge
            connected_faces = adjacency.get(i, [])
            for face_idx in connected_faces:
                edge_index.append([i, face_idx])

        # Convert to tensors
        x = torch.tensor(face_features, dtype=torch.float) if face_features else torch.empty(0, 0)
        edge_attr = torch.tensor(edge_features, dtype=torch.float) if edge_features else torch.empty(0, 0)
        if edge_index:
            edge_index_tensor = torch.tensor(edge_index, dtype=torch.long)
            if hasattr(edge_index_tensor, 't'):
                edge_index = edge_index_tensor.t().contiguous()
            else:
                edge_index = edge_index_tensor.T
        else:
            edge_index = torch.empty(2, 0)

        return Data(x=x, edge_index=edge_index, edge_attr=edge_attr)

    def _extract_face_features(self, face: Dict[str, Any]) -> List[float]:
        """Extract numerical features from a face."""
        return [
            face.get('area', 0.0),
            face.get('normal_x', 0.0),
            face.get('normal_y', 0.0),
            face.get('normal_z', 0.0),
            face.get('curvature', 0.0),
            face.get('type', 0.0),  # planar=0, cylindrical=1, etc.
        ]

    def _extract_edge_features(self, edge: Dict[str, Any]) -> List[float]:
        """Extract numerical features from an edge."""
        return [
            edge.get('length', 0.0),
            edge.get('curvature', 0.0),
            edge.get('type', 0.0),  # line=0, arc=1, etc.
        ]


class PointCloudBuilder:
    """Converts mesh geometry into point cloud format for PointNet++."""

    def __init__(self, num_points: int = 1024):
        self.num_points = num_points

    def build_point_cloud(self, mesh_data: Dict[str, Any]) -> Any:
        """
        Sample point cloud from mesh surface.

        Args:
            mesh_data: Dictionary containing vertices, faces, normals

        Returns:
            Tensor of shape (num_points, 3) for point coordinates
        """
        vertices = np.array(mesh_data.get('vertices', []))
        faces = np.array(mesh_data.get('faces', []))
        normals = np.array(mesh_data.get('normals', []))

        if len(vertices) == 0:
            # Fallback to plain numpy zeros when torch is unavailable
            try:
                return torch.zeros(self.num_points, 3)
            except AttributeError:
                return np.zeros((self.num_points, 3), dtype=np.float32)

        # Sample points on mesh surface
        points = self._sample_surface_points(vertices, faces, self.num_points)

        # Add normal information if available
        if len(normals) > 0:
            # For each sampled point, find closest vertex normal
            point_normals = self._get_point_normals(points, vertices, normals)
            points = np.concatenate([points, point_normals], axis=1)

        return torch.tensor(points, dtype=torch.float)

    def _sample_surface_points(self, vertices: np.ndarray, faces: np.ndarray, num_points: int) -> np.ndarray:
        """Sample points uniformly on mesh surface."""
        # Simple uniform sampling - in practice, use area-weighted sampling
        if len(faces) == 0:
            # Fallback to vertex sampling
            indices = np.random.choice(len(vertices), num_points, replace=True)
            return vertices[indices]

        # Calculate face areas for weighted sampling
        face_areas = []
        for face in faces:
            if len(face) == 3:
                # Triangle area
                v0, v1, v2 = vertices[face]
                area = 0.5 * np.linalg.norm(np.cross(v1 - v0, v2 - v0))
                face_areas.append(area)

        face_areas = np.array(face_areas)
        total_area = face_areas.sum()

        if total_area == 0:
            # Fallback
            indices = np.random.choice(len(faces), num_points, replace=True)
            sampled_faces = faces[indices]
            points = []
            for face in sampled_faces:
                # Sample random point in triangle
                r1, r2 = np.random.rand(2)
                if r1 + r2 > 1:
                    r1, r2 = 1 - r1, 1 - r2
                v0, v1, v2 = vertices[face]
                point = v0 + r1 * (v1 - v0) + r2 * (v2 - v0)
                points.append(point)
            return np.array(points)

        # Area-weighted sampling
        face_probs = face_areas / total_area
        sampled_face_indices = np.random.choice(len(faces), num_points, p=face_probs)

        points = []
        for idx in sampled_face_indices:
            face = faces[idx]
            if len(face) == 3:
                # Sample in triangle
                r1, r2 = np.random.rand(2)
                if r1 + r2 > 1:
                    r1, r2 = 1 - r1, 1 - r2
                v0, v1, v2 = vertices[face]
                point = v0 + r1 * (v1 - v0) + r2 * (v2 - v0)
                points.append(point)
            else:
                # For non-triangles, sample centroid
                centroid = vertices[face].mean(axis=0)
                points.append(centroid)

        return np.array(points)

    def _get_point_normals(self, points: np.ndarray, vertices: np.ndarray, normals: np.ndarray) -> np.ndarray:
        """Get normals for sampled points by nearest neighbor."""
        from scipy.spatial import cKDTree
        tree = cKDTree(vertices)
        _, indices = tree.query(points, k=1)
        return normals[indices]


def prepare_ml_inputs(layer3_results: List[CheckResult]) -> Dict[str, Any]:
    """
    Prepare inputs for ML models from Layer 3 results.

    Args:
        layer3_results: List of CheckResult objects from Layer 3

    Returns:
        Dictionary containing prepared inputs for GNN and PointNet++
    """
    brep_builder = BRepGraphBuilder()
    point_builder = PointCloudBuilder()

    # Extract geometry data from results
    # This assumes CheckResult has geometry data attached
    brep_data = _extract_brep_data(layer3_results)
    mesh_data = _extract_mesh_data(layer3_results)

    # Build ML inputs
    graph_data = brep_builder.build_graph(brep_data)
    point_cloud = point_builder.build_point_cloud(mesh_data)

    return {
        'gnn_input': graph_data,
        'pointnet_input': point_cloud,
        'layer3_results': layer3_results
    }


def _extract_brep_data(results: List[CheckResult]) -> Dict[str, Any]:
    """Extract B-Rep topology from Layer 3 results."""
    # Placeholder - in practice, extract from geometry kernel outputs
    return {
        'faces': [],
        'edges': [],
        'adjacency': {}
    }


def _extract_mesh_data(results: List[CheckResult]) -> Dict[str, Any]:
    """Extract mesh data from Layer 3 results."""
    # Placeholder - in practice, extract from geometry kernel outputs
    return {
        'vertices': [],
        'faces': [],
        'normals': []
    }