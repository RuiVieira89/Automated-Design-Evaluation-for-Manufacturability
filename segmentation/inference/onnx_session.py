# segmentation/inference/onnx_session.py
"""
ONNX Runtime session management for ML inference.
"""

import onnxruntime as ort
import numpy as np
from typing import Dict, Any, List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class ONNXInferenceSession:
    """Wrapper for ONNX Runtime inference sessions."""

    def __init__(self, model_path: str, session_options: Optional[ort.SessionOptions] = None):
        """
        Initialize ONNX session.

        Args:
            model_path: Path to ONNX model
            session_options: ONNX session options
        """
        self.model_path = model_path

        # Configure session options
        if session_options is None:
            session_options = ort.SessionOptions()
            session_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

        # Create session with appropriate provider
        providers = self._get_providers()
        self.session = ort.InferenceSession(
            model_path,
            sess_options=session_options,
            providers=providers
        )

        # Get input/output info
        self.input_names = [input.name for input in self.session.get_inputs()]
        self.output_names = [output.name for output in self.session.get_outputs()]

        logger.info(f"Loaded ONNX model: {model_path}")
        logger.info(f"Inputs: {self.input_names}")
        logger.info(f"Outputs: {self.output_names}")
        logger.info(f"Provider: {self.session.get_providers()}")

    def _get_providers(self) -> List[str]:
        """Get appropriate execution providers."""
        providers = []

        # Try CUDA first
        if 'CUDAExecutionProvider' in ort.get_available_providers():
            providers.append('CUDAExecutionProvider')
        elif 'TensorrtExecutionProvider' in ort.get_available_providers():
            providers.append('TensorrtExecutionProvider')

        # Fallback to CPU
        providers.append('CPUExecutionProvider')
        return providers

    def run(self, inputs: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
        """
        Run inference.

        Args:
            inputs: Dictionary of input tensors

        Returns:
            Dictionary of output tensors
        """
        # Run inference
        outputs = self.session.run(self.output_names, inputs)

        # Return as dictionary
        return dict(zip(self.output_names, outputs))

    def get_input_shapes(self) -> Dict[str, List[int]]:
        """Get expected input shapes."""
        shapes = {}
        for input_info in self.session.get_inputs():
            shapes[input_info.name] = input_info.shape
        return shapes

    def get_output_shapes(self) -> Dict[str, List[int]]:
        """Get output shapes."""
        shapes = {}
        for output_info in self.session.get_outputs():
            shapes[output_info.name] = output_info.shape
        return shapes


class GNNInferenceSession(ONNXInferenceSession):
    """Specialized session for GNN models."""

    def __init__(self, model_path: str):
        super().__init__(model_path)

    def predict(self, x: np.ndarray, edge_index: np.ndarray, batch: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Run GNN inference.

        Args:
            x: Node features (num_nodes, feature_dim)
            edge_index: Edge indices (2, num_edges)
            batch: Batch indices (num_nodes,)

        Returns:
            logits: Classification logits
            probabilities: Softmax probabilities
        """
        inputs = {
            'x': x.astype(np.float32),
            'edge_index': edge_index.astype(np.int64),
            'batch': batch.astype(np.int64)
        }

        outputs = self.run(inputs)
        logits = outputs['output']

        # Apply softmax for probabilities
        probabilities = self._softmax(logits)

        return logits, probabilities

    @staticmethod
    def _softmax(x: np.ndarray) -> np.ndarray:
        """Apply softmax along last axis."""
        exp_x = np.exp(x - np.max(x, axis=-1, keepdims=True))
        return exp_x / np.sum(exp_x, axis=-1, keepdims=True)


class PointNetInferenceSession(ONNXInferenceSession):
    """Specialized session for PointNet++ models."""

    def __init__(self, model_path: str):
        super().__init__(model_path)

    def predict(self, point_cloud: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Run PointNet++ inference.

        Args:
            point_cloud: Point cloud (batch_size, num_points, 6) - xyz + normals

        Returns:
            logits: Classification logits
            probabilities: Softmax probabilities
        """
        inputs = {
            'input': point_cloud.astype(np.float32)
        }

        outputs = self.run(inputs)
        logits = outputs['output']

        # Apply softmax for probabilities
        probabilities = self._softmax(logits)

        return logits, probabilities

    @staticmethod
    def _softmax(x: np.ndarray) -> np.ndarray:
        """Apply softmax along last axis."""
        exp_x = np.exp(x - np.max(x, axis=-1, keepdims=True))
        return exp_x / np.sum(exp_x, axis=-1, keepdims=True)