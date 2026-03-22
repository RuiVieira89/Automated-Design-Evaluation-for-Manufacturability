# segmentation/inference/ml_inference_engine.py
"""
Main ML inference engine coordinating GNN, PointNet++, and rule fallback.
"""

import numpy as np
from typing import Dict, Any, List, Optional
from .onnx_session import GNNInferenceSession, PointNetInferenceSession
from .process_classifier import ProcessClassifier, ManufacturabilityAssessment
from .confidence_scorer import ConfidenceAggregator
from .rule_fallback import RuleFallbackEngine
from ..model_registry import ModelRegistry
from ..data_prep import prepare_ml_inputs
import logging

logger = logging.getLogger(__name__)


class MLInferenceEngine:
    """Main engine for ML-based manufacturability inference."""

    def __init__(self, model_registry_path: str = 'model_registry.json',
                 confidence_threshold: float = 0.65):
        """
        Initialize the ML inference engine.

        Args:
            model_registry_path: Path to model registry
            confidence_threshold: Threshold for rule fallback
        """
        self.model_registry = ModelRegistry(model_registry_path)
        self.confidence_threshold = confidence_threshold

        # Initialize components
        self.gnn_session = None
        self.pointnet_session = None
        self.process_classifier = ProcessClassifier()
        self.confidence_aggregator = ConfidenceAggregator()
        self.rule_fallback = RuleFallbackEngine(confidence_threshold)

        # Load active models
        self._load_active_models()

    def _load_active_models(self) -> None:
        """Load the active models from registry."""
        active_models = self.model_registry.get_active_models()

        if 'gnn' in active_models:
            gnn_meta = active_models['gnn']
            self.gnn_session = GNNInferenceSession(gnn_meta.path)
            logger.info(f"Loaded GNN model: {gnn_meta.path}")

        if 'pointnet' in active_models:
            pointnet_meta = active_models['pointnet']
            self.pointnet_session = PointNetInferenceSession(pointnet_meta.path)
            logger.info(f"Loaded PointNet++ model: {pointnet_meta.path}")

        if not self.gnn_session and not self.pointnet_session:
            logger.warning("No ML models loaded - will use rule fallback only")

    def analyze_manufacturability(self, layer3_results: List[Any],
                                geometry_features: Dict[str, Any] = None) -> ManufacturabilityAssessment:
        """
        Perform complete manufacturability analysis.

        Args:
            layer3_results: Results from Layer 3 rule engine
            geometry_features: Additional geometry features

        Returns:
            ManufacturabilityAssessment object
        """
        # Prepare ML inputs from Layer 3 results
        ml_inputs = prepare_ml_inputs(layer3_results)

        # Run ML inference
        ml_outputs = self._run_ml_inference(ml_inputs)

        # Calculate confidence
        confidence_assessment = self.confidence_aggregator.calculate_overall_confidence(
            ml_outputs, geometry_features
        )

        # Classify processes
        process_capabilities = self.process_classifier.classify(ml_outputs, geometry_features or {})

        # Create assessment
        assessment = ManufacturabilityAssessment(
            ml_outputs, process_capabilities, layer3_results, self.confidence_threshold
        )

        return assessment

    def analyze(self, mesh: Any, rule_results: Any = None) -> ManufacturabilityAssessment:
        """
        Analyze manufacturability of a mesh.

        Args:
            mesh: PyVista mesh or similar geometry
            rule_results: Results from rule engine analysis

        Returns:
            ManufacturabilityAssessment object
        """
        if rule_results is None:
            # If no rule results provided, we can't run ML analysis
            # This shouldn't happen in normal usage
            raise ValueError("Rule results are required for ML analysis")

        # Extract check_results from AnalysisReport
        if hasattr(rule_results, 'check_results'):
            layer3_results = rule_results.check_results
        else:
            layer3_results = rule_results

        # Extract geometry features from mesh
        geometry_features = self._extract_geometry_features(mesh)

        # Run manufacturability analysis
        return self.analyze_manufacturability(layer3_results, geometry_features)

    def _extract_geometry_features(self, mesh: Any) -> Dict[str, Any]:
        """Extract geometry features from mesh for ML analysis."""
        # This is a placeholder - in a real implementation, this would
        # use geometry_kernel to extract features
        return {}

    def _run_ml_inference(self, ml_inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Run inference on both ML models."""
        outputs = {}

        # GNN inference on B-Rep graph
        if self.gnn_session and 'gnn_input' in ml_inputs:
            try:
                graph_data = ml_inputs['gnn_input']
                logits, probs = self.gnn_session.predict(
                    graph_data.x.numpy(),
                    graph_data.edge_index.numpy(),
                    graph_data.batch.numpy() if hasattr(graph_data, 'batch') else np.zeros(graph_data.x.shape[0], dtype=np.int64)
                )
                outputs['gnn_logits'] = logits
                outputs['gnn_probabilities'] = probs
                outputs['gnn_confidence'] = np.max(probs)
            except Exception as e:
                logger.error(f"GNN inference failed: {e}")
                outputs['gnn_error'] = str(e)

        # PointNet++ inference on point cloud
        if self.pointnet_session and 'pointnet_input' in ml_inputs:
            try:
                point_cloud = ml_inputs['pointnet_input']
                logits, probs = self.pointnet_session.predict(point_cloud.numpy())
                outputs['pointnet_logits'] = logits
                outputs['pointnet_probabilities'] = probs
                outputs['pointnet_confidence'] = np.max(probs)
            except Exception as e:
                logger.error(f"PointNet++ inference failed: {e}")
                outputs['pointnet_error'] = str(e)

        return outputs

    def get_model_status(self) -> Dict[str, Any]:
        """Get status of loaded models."""
        return {
            'gnn_loaded': self.gnn_session is not None,
            'pointnet_loaded': self.pointnet_session is not None,
            'registry_path': self.model_registry.registry_path,
            'active_models': self.model_registry.get_active_models()
        }

    def reload_models(self) -> None:
        """Reload models from registry."""
        self._load_active_models()