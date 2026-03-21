# segmentation/__init__.py
"""
Layer 4: ML / Context-Aware Reasoning

This layer implements machine learning models for manufacturability analysis,
providing process-aware classification beyond rule-based checks.
"""

try:
    from .inference import MLInferenceEngine
    INFERENCE_AVAILABLE = True
except ImportError as e:
    INFERENCE_AVAILABLE = False
    print(f"Warning: ML inference not available: {e}")

try:
    from .training import train_gnn_model, train_pointnet_model
    TRAINING_AVAILABLE = True
except ImportError as e:
    TRAINING_AVAILABLE = False
    print(f"Warning: ML training not available: {e}")

from .model_registry import ModelRegistry
from .data_prep import prepare_ml_inputs, BRepGraphBuilder, PointCloudBuilder

__all__ = [
    'ModelRegistry',
    'prepare_ml_inputs',
    'BRepGraphBuilder',
    'PointCloudBuilder'
]

if INFERENCE_AVAILABLE:
    __all__.append('MLInferenceEngine')

if TRAINING_AVAILABLE:
    __all__.extend(['train_gnn_model', 'train_pointnet_model'])