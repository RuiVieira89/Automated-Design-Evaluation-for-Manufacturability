# Layer 4: ML / Context-Aware Reasoning

This layer implements machine learning models for manufacturability analysis, providing process-aware classification beyond rule-based checks.

## Architecture Overview

The layer splits into two paths:
- **Training path**: PyTorch Geometric (GNN on B-Rep graphs) and PointNet++ (point cloud classification)
- **Inference path**: ONNX Runtime with rule fallback for low-confidence predictions

## Key Components

### Data Preparation (`data_prep.py`)
- `BRepGraphBuilder`: Converts B-Rep topology to PyTorch Geometric graphs
- `PointCloudBuilder`: Samples point clouds from mesh surfaces
- `prepare_ml_inputs()`: Main function converting Layer 3 results to ML inputs

### Training (`training/`)
- `gnn_trainer.py`: PyTorch Geometric GNN training for manufacturability classification
- `pointnet_trainer.py`: PointNet++ training on point cloud features
- `export_onnx.py`: Export trained models to ONNX format

### Inference (`inference/`)
- `onnx_session.py`: ONNX Runtime wrappers for GNN and PointNet++ models
- `process_classifier.py`: Maps ML predictions to manufacturing processes
- `confidence_scorer.py`: Calculates prediction confidence and uncertainty
- `rule_fallback.py`: Rule-based recommendations when ML confidence is low
- `ml_inference_engine.py`: Main orchestrator coordinating all components

### Model Management (`model_registry.py`)
- Versioned storage of trained ONNX models
- Automatic loading of latest models
- Metadata tracking (metrics, creation dates, etc.)

## Input/Output Contract

**Inputs from Layer 3:**
- CheckResult list with violation details
- Feature vectors and geometry data
- Mesh and B-Rep representations

**Outputs:**
- Process recommendations (3-axis mill, 5-axis mill, casting, etc.)
- Confidence scores per process
- Fallback to rule-based assessment when ML confidence < threshold
- Manufacturability limitations and requirements

## Usage Example

```python
from segmentation.inference import MLInferenceEngine

# Initialize engine (loads latest models from registry)
engine = MLInferenceEngine()

# Run analysis on Layer 3 results
results = engine.analyze_manufacturability(layer3_results, geometry_features)

print(f"Recommended process: {results['recommended_process']}")
print(f"Confidence: {results['confidence']:.3f}")
```

## Training Workflow

```python
from segmentation.training import train_gnn_model, train_pointnet_model, export_models

# Train models
gnn_model = train_gnn_model(num_epochs=100)
pointnet_model = train_pointnet_model(num_epochs=100)

# Export to ONNX
export_models(gnn_model, pointnet_model, output_dir='models/')
```

## Dependencies

- PyTorch & PyTorch Geometric (training only)
- ONNX Runtime (inference)
- NetworkX, NumPy, SciPy
- Rule engine from Layer 3

## Model Registry

Models are automatically registered and versioned:

```python
from segmentation.model_registry import ModelRegistry

registry = ModelRegistry()
active = registry.get_active_models()  # Gets latest GNN and PointNet models
```