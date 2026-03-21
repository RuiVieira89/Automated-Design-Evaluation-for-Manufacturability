# segmentation/example_usage.py
"""
Example usage of Layer 4 ML-based manufacturability analysis.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rules.rule_engine import RuleEngine, AnalysisReport
from .inference import MLInferenceEngine
from .training import train_gnn_model, train_pointnet_model, export_models
from .model_registry import ModelRegistry
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def example_training_workflow():
    """Example of training ML models and exporting to ONNX."""
    print("=== Layer 4 Training Example ===")

    # Train models (this will use dummy data)
    print("Training GNN model...")
    gnn_model = train_gnn_model(num_epochs=5)  # Reduced epochs for demo

    print("Training PointNet++ model...")
    pointnet_model = train_pointnet_model(num_epochs=5)  # Reduced epochs for demo

    # Export to ONNX
    print("Exporting models to ONNX...")
    exported_paths = export_models(gnn_model, pointnet_model, output_dir='models/')

    # Register models
    registry = ModelRegistry()
    for model_type, path in exported_paths.items():
        registry.register_model(
            name='manufacturability',
            model_type=model_type,
            model_path=path,
            metrics={'accuracy': 0.85, 'f1_score': 0.82}  # Dummy metrics
        )

    print(f"Models registered: {list(exported_paths.keys())}")
    return exported_paths


def example_inference_workflow():
    """Example of running inference with trained models."""
    print("\n=== Layer 4 Inference Example ===")

    # Initialize inference engine
    engine = MLInferenceEngine()

    # Check model status
    status = engine.get_model_status()
    print(f"Model status: GNN loaded={status['gnn_loaded']}, PointNet loaded={status['pointnet_loaded']}")

    if not status['gnn_loaded'] and not status['pointnet_loaded']:
        print("No models loaded - running training first...")
        example_training_workflow()
        engine.reload_models()

    # Create mock Layer 3 results (in practice, this would come from actual rule engine)
    mock_layer3_results = create_mock_layer3_results()

    # Extract geometry features
    geometry_features = {
        'has_deep_holes': False,
        'has_undercuts': True,
        'has_complex_curves': False,
        'is_thin_walled': False,
        'is_prismatic': True,
        'min_wall_thickness': 3.0,
        'num_features': 5
    }

    # Run analysis
    print("Running manufacturability analysis...")
    results = engine.analyze_manufacturability(mock_layer3_results, geometry_features)

    # Print results
    print("\n=== Analysis Results ===")
    print(f"Method: {results['method']}")
    print(f"Recommended Process: {results['recommended_process']}")
    print(f"Confidence: {results['confidence']:.3f}")

    if 'alternative_processes' in results and results['alternative_processes']:
        print("Alternative Processes:")
        for alt in results['alternative_processes'][:2]:
            print(f"  - {alt.get('process', alt)} (score: {alt.get('score', 'N/A')})")

    if 'limitations' in results and results['limitations']:
        print("Limitations:")
        for lim in results['limitations']:
            print(f"  - {lim}")

    if 'requirements' in results and results['requirements']:
        print("Requirements:")
        for req in results['requirements']:
            print(f"  - {req}")

    # Show confidence assessment
    conf = results.get('confidence_assessment', {})
    print(f"\nConfidence Assessment: {conf.get('confidence_category', 'unknown')}")
    model_confs = conf.get('model_confidences', {})
    if 'aggregate' in model_confs:
        print(f"Aggregate Confidence: {model_confs['aggregate']:.3f}")

    return results


def create_mock_layer3_results():
    """Create mock Layer 3 results for demonstration."""
    from rules.base import CheckResult, Severity

    # Mock some check results
    results = [
        CheckResult(
            check_name="WallThicknessCheck",
            severity=Severity.PASS,
            message="Wall thickness is adequate",
            value=3.5,
            threshold=2.0,
            details={"location": "main_body"}
        ),
        CheckResult(
            check_name="DraftAngleCheck",
            severity=Severity.WARN,
            message="Draft angle could be improved",
            value=2.0,
            threshold=3.0,
            details={"location": "side_wall"}
        ),
        CheckResult(
            check_name="UndercutDetectionCheck",
            severity=Severity.FAIL,
            message="Undercut detected",
            value=1,
            threshold=0,
            details={"location": "bottom_feature"}
        )
    ]

    return results


def main():
    """Main example function."""
    try:
        # Run inference example
        results = example_inference_workflow()

        print("\n=== Example completed successfully ===")

    except Exception as e:
        logger.error(f"Example failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()