# tests/test_segmentation.py
"""
Tests for Layer 4 segmentation/ML components.
"""

import pytest
import numpy as np
try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    torch = None
    TORCH_AVAILABLE = False
from unittest.mock import Mock, patch
import sys
import os

# Add segmentation to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from segmentation.data_prep import BRepGraphBuilder, PointCloudBuilder, prepare_ml_inputs
from segmentation.inference.confidence_scorer import ConfidenceScorer, ConfidenceAggregator
from segmentation.inference.rule_fallback import RuleFallbackEngine
from segmentation.inference.process_classifier import ProcessClassifier, ManufacturingProcess
from segmentation.model_registry import ModelRegistry, ModelMetadata
from rules.base import CheckResult, Severity


class TestDataPreparation:
    """Test data preparation utilities."""

    def test_brep_graph_builder(self):
        """Test B-Rep to graph conversion."""
        builder = BRepGraphBuilder()

        # Mock B-Rep data
        brep_data = {
            'faces': [
                {'area': 10.0, 'normal_x': 0.0, 'normal_y': 0.0, 'normal_z': 1.0,
                 'curvature': 0.0, 'type': 0}
            ],
            'edges': [
                {'length': 5.0, 'curvature': 0.0, 'type': 0}
            ],
            'adjacency': {0: [0]}  # Edge 0 connects to face 0
        }

        graph = builder.build_graph(brep_data)

        assert graph.x.shape[1] == 6  # 6 face features
        assert graph.edge_attr.shape[1] == 3  # 3 edge features
        assert graph.edge_index.shape[0] == 2

    def test_point_cloud_builder(self):
        """Test mesh to point cloud conversion."""
        builder = PointCloudBuilder(num_points=100)

        # Mock mesh data
        mesh_data = {
            'vertices': np.random.rand(50, 3),
            'faces': np.random.randint(0, 50, (30, 3)),
            'normals': np.random.rand(50, 3)
        }

        point_cloud = builder.build_point_cloud(mesh_data)

        assert point_cloud.shape[0] == 100  # num_points
        assert point_cloud.shape[1] == 6  # xyz + normal_xyz

    def test_prepare_ml_inputs(self):
        """Test complete ML input preparation."""
        # Mock Layer 3 results
        mock_results = [
            CheckResult("TestCheck", Severity.PASS, "OK", 1.0, 0.5, {})
        ]

        inputs = prepare_ml_inputs(mock_results)

        # Should have prepared inputs (even if empty due to mock data)
        assert 'gnn_input' in inputs
        assert 'pointnet_input' in inputs
        assert 'layer3_results' in inputs


class TestConfidenceScorer:
    """Test confidence scoring."""

    def test_max_probability_confidence(self):
        """Test max probability confidence calculation."""
        scorer = ConfidenceScorer()

        # High confidence case
        probs = np.array([[0.9, 0.05, 0.05]])
        confidence = scorer.calculate_confidence(probs, method='max_prob')
        assert confidence == pytest.approx(0.9, abs=0.01)

        # Low confidence case
        probs = np.array([[0.4, 0.35, 0.25]])
        confidence = scorer.calculate_confidence(probs, method='max_prob')
        assert confidence == pytest.approx(0.4, abs=0.01)

    def test_entropy_confidence(self):
        """Test entropy-based confidence."""
        scorer = ConfidenceScorer()

        # High confidence (low entropy)
        probs = np.array([[0.9, 0.05, 0.05]])
        confidence = scorer.calculate_confidence(probs, method='entropy')
        assert confidence > 0.6  # Should be high relative to low-confidence case

        # Low confidence (high entropy)
        probs = np.array([[0.33, 0.33, 0.34]])
        low_confidence = scorer.calculate_confidence(probs, method='entropy')
        assert low_confidence < confidence

    def test_confidence_aggregator(self):
        """Test confidence aggregation across models."""
        aggregator = ConfidenceAggregator()

        model_outputs = {
            'gnn_probabilities': [0.8, 0.1, 0.1],
            'pointnet_probabilities': [0.7, 0.2, 0.1]
        }

        confidences = aggregator.aggregate_confidence(model_outputs)

        assert 'gnn' in confidences
        assert 'pointnet' in confidences
        assert 'aggregate' in confidences
        assert confidences['aggregate'] == pytest.approx(0.75, abs=0.01)


class TestRuleFallback:
    """Test rule-based fallback."""

    def test_should_fallback(self):
        """Test fallback decision logic."""
        engine = RuleFallbackEngine(confidence_threshold=0.65)

        assert engine.should_fallback(0.5) == True
        assert engine.should_fallback(0.7) == False
        assert engine.should_fallback(0.65) == False  # At threshold

    def test_fallback_recommendation(self):
        """Test fallback recommendation generation."""
        engine = RuleFallbackEngine()

        # Mock results with violations
        rule_results = [
            CheckResult("UndercutCheck", Severity.FAIL, "Undercut detected", 1, 0, {}),
            CheckResult("WallCheck", Severity.PASS, "OK", 3.0, 2.0, {})
        ]

        geometry_features = {'has_undercuts': True, 'is_prismatic': True}

        recommendation = engine.generate_fallback_recommendation(rule_results, geometry_features)

        assert recommendation['method'] == 'rule_fallback'
        assert 'recommended_process' in recommendation
        assert 'confidence' in recommendation
        assert recommendation['violation_summary']['critical_count'] == 1


class TestProcessClassifier:
    """Test process classification."""

    def test_classify_simple_geometry(self):
        """Test classification for simple geometry."""
        classifier = ProcessClassifier()

        # Mock ML predictions favoring simple machining
        ml_predictions = {
            'gnn_probabilities': [0.8, 0.1, 0.05, 0.05],  # Class 0: simple prismatic
            'pointnet_probabilities': [0.7, 0.15, 0.1, 0.05]
        }

        geometry_features = {
            'has_deep_holes': False,
            'has_undercuts': False,
            'is_prismatic': True
        }

        capabilities = classifier.classify(ml_predictions, geometry_features)

        # Should recommend 3-axis mill for simple geometry
        process_names = [cap.process.value for cap in capabilities]
        assert '3-axis_mill' in process_names

    def test_classify_complex_geometry(self):
        """Test classification for complex geometry."""
        classifier = ProcessClassifier()

        # Mock predictions favoring complex machining
        ml_predictions = {
            'gnn_probabilities': [0.1, 0.8, 0.05, 0.05],  # Class 1: complex
            'pointnet_probabilities': [0.15, 0.7, 0.1, 0.05]
        }

        geometry_features = {
            'has_undercuts': True,
            'has_complex_curves': True
        }

        capabilities = classifier.classify(ml_predictions, geometry_features)

        # Should recommend 5-axis mill or additive for complex geometry
        process_names = [cap.process.value for cap in capabilities]
        assert any(p in ['5-axis_mill', 'additive'] for p in process_names)


class TestModelRegistry:
    """Test model registry functionality."""

    def test_register_and_retrieve(self):
        """Test model registration and retrieval."""
        registry = ModelRegistry('test_registry.json')

        # Register a model
        key = registry.register_model(
            name='test_model',
            model_type='gnn',
            model_path='/path/to/model.onnx',
            metrics={'accuracy': 0.85}
        )

        # Retrieve the model
        model = registry.get_model('test_model', 'gnn', 'latest')

        assert model is not None
        assert model.name == 'test_model'
        assert model.model_type == 'gnn'
        assert model.metrics['accuracy'] == 0.85

        # Clean up
        if os.path.exists('test_registry.json'):
            os.remove('test_registry.json')

    def test_list_models(self):
        """Test model listing."""
        registry = ModelRegistry('test_registry.json')

        # Register multiple models
        registry.register_model('model1', 'gnn', '/path1', {'acc': 0.8})
        registry.register_model('model2', 'pointnet', '/path2', {'acc': 0.9})

        # List all
        all_models = registry.list_models()
        assert len(all_models) == 2

        # List by type
        gnn_models = registry.list_models(model_type='gnn')
        assert len(gnn_models) == 1
        assert gnn_models[0].name == 'model1'

        # Clean up
        if os.path.exists('test_registry.json'):
            os.remove('test_registry.json')


# Integration test
class TestMLInferenceEngine:
    """Integration tests for ML inference engine."""

    @patch('segmentation.inference.onnx_session.GNNInferenceSession')
    @patch('segmentation.inference.onnx_session.PointNetInferenceSession')
    def test_inference_without_models(self, mock_pointnet, mock_gnn):
        """Test inference engine behavior without loaded models."""
        from segmentation.inference.ml_inference_engine import MLInferenceEngine

        # Mock registry with no models
        with patch('segmentation.model_registry.ModelRegistry.get_active_models', return_value={}):
            engine = MLInferenceEngine('dummy_registry.json')

            assert engine.gnn_session is None
            assert engine.pointnet_session is None

            # Should still work with rule fallback
            mock_results = [CheckResult("Test", Severity.PASS, "OK", 1.0, 0.5, {})]
            results = engine.analyze_manufacturability(mock_results)

            assert results['method'] == 'rule_fallback'