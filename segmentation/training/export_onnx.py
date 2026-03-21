# segmentation/training/export_onnx.py
"""
Export trained PyTorch models to ONNX format for inference.
"""

import torch
import torch.onnx
import numpy as np
from typing import Any, Dict
import logging
import os

logger = logging.getLogger(__name__)


def export_gnn_to_onnx(model: torch.nn.Module, output_path: str = 'gnn_model.onnx',
                      input_sample: torch.Tensor = None) -> None:
    """
    Export GNN model to ONNX format.

    Args:
        model: Trained PyTorch Geometric GNN model
        output_path: Path to save ONNX model
        input_sample: Sample input for tracing (optional)
    """
    model.eval()

    # Create dummy input if not provided
    if input_sample is None:
        # Dummy graph: 32 nodes, 6 features each, random edges
        num_nodes = 32
        num_edges = 64
        x = torch.randn(num_nodes, 6)  # node features
        edge_index = torch.randint(0, num_nodes, (2, num_edges))
        batch = torch.zeros(num_nodes, dtype=torch.long)  # single graph

        input_sample = (x, edge_index, batch)

    # Export to ONNX
    torch.onnx.export(
        model,
        input_sample,
        output_path,
        export_params=True,
        opset_version=11,
        do_constant_folding=True,
        input_names=['x', 'edge_index', 'batch'],
        output_names=['output'],
        dynamic_axes={
            'x': {0: 'num_nodes'},
            'edge_index': {1: 'num_edges'},
            'batch': {0: 'num_nodes'},
            'output': {0: 'batch_size'}
        }
    )

    logger.info(f"GNN model exported to {output_path}")


def export_pointnet_to_onnx(model: torch.nn.Module, output_path: str = 'pointnet_model.onnx',
                           input_sample: torch.Tensor = None) -> None:
    """
    Export PointNet++ model to ONNX format.

    Args:
        model: Trained PointNet++ model
        output_path: Path to save ONNX model
        input_sample: Sample input for tracing (optional)
    """
    model.eval()

    # Create dummy input if not provided
    if input_sample is None:
        # Dummy point cloud: batch_size=1, 1024 points, 6 features (xyz + normals)
        input_sample = torch.randn(1, 1024, 6)

    # Export to ONNX
    torch.onnx.export(
        model,
        input_sample,
        output_path,
        export_params=True,
        opset_version=11,
        do_constant_folding=True,
        input_names=['input'],
        output_names=['output'],
        dynamic_axes={
            'input': {0: 'batch_size', 1: 'num_points'},
            'output': {0: 'batch_size'}
        }
    )

    logger.info(f"PointNet++ model exported to {output_path}")


def validate_onnx_model(onnx_path: str, pytorch_model: torch.nn.Module,
                       input_sample: torch.Tensor, model_type: str = 'gnn') -> bool:
    """
    Validate that ONNX model produces same outputs as PyTorch model.

    Args:
        onnx_path: Path to ONNX model
        pytorch_model: Original PyTorch model
        input_sample: Sample input tensor
        model_type: 'gnn' or 'pointnet'

    Returns:
        True if outputs match within tolerance
    """
    try:
        import onnxruntime as ort
    except ImportError:
        logger.warning("ONNX Runtime not available for validation")
        return False

    # Load ONNX model
    ort_session = ort.InferenceSession(onnx_path)

    # Get PyTorch output
    pytorch_model.eval()
    with torch.no_grad():
        if model_type == 'gnn':
            x, edge_index, batch = input_sample
            pytorch_out = pytorch_model(x, edge_index, batch)
        else:  # pointnet
            pytorch_out = pytorch_model(input_sample)

    # Get ONNX output
    if model_type == 'gnn':
        x, edge_index, batch = input_sample
        ort_inputs = {
            'x': x.numpy(),
            'edge_index': edge_index.numpy(),
            'batch': batch.numpy()
        }
    else:
        ort_inputs = {'input': input_sample.numpy()}

    onnx_out = ort_session.run(None, ort_inputs)[0]

    # Compare outputs
    pytorch_out_np = pytorch_out.numpy()
    diff = np.abs(pytorch_out_np - onnx_out).max()

    logger.info(f"Max difference between PyTorch and ONNX outputs: {diff}")

    # Check if within tolerance
    tolerance = 1e-5
    if diff < tolerance:
        logger.info("ONNX validation passed!")
        return True
    else:
        logger.warning(f"ONNX validation failed! Difference {diff} > {tolerance}")
        return False


def export_models(gnn_model: torch.nn.Module = None, pointnet_model: torch.nn.Module = None,
                 output_dir: str = 'models/') -> Dict[str, str]:
    """
    Export both models to ONNX format.

    Args:
        gnn_model: Trained GNN model
        pointnet_model: Trained PointNet++ model
        output_dir: Directory to save models

    Returns:
        Dictionary with paths to exported models
    """
    os.makedirs(output_dir, exist_ok=True)

    exported_models = {}

    if gnn_model is not None:
        gnn_path = os.path.join(output_dir, 'gnn_model.onnx')
        export_gnn_to_onnx(gnn_model, gnn_path)
        exported_models['gnn'] = gnn_path

    if pointnet_model is not None:
        pointnet_path = os.path.join(output_dir, 'pointnet_model.onnx')
        export_pointnet_to_onnx(pointnet_model, pointnet_path)
        exported_models['pointnet'] = pointnet_path

    return exported_models