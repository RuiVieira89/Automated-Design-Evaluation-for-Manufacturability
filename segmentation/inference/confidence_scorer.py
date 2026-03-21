# segmentation/inference/confidence_scorer.py
"""
Confidence scoring and uncertainty estimation for ML predictions.
"""

import numpy as np
from typing import Dict, Any, List, Tuple
from scipy.stats import entropy
import logging

logger = logging.getLogger(__name__)


class ConfidenceScorer:
    """Calculate confidence scores for ML predictions."""

    def __init__(self, calibration_data: Dict[str, Any] = None):
        """
        Initialize confidence scorer.

        Args:
            calibration_data: Optional calibration data for temperature scaling
        """
        self.calibration_data = calibration_data or {}

    def calculate_confidence(self, probabilities: np.ndarray,
                           method: str = 'max_prob') -> float:
        """
        Calculate confidence score from prediction probabilities.

        Args:
            probabilities: Class probabilities (shape: batch_size, num_classes)
            method: Confidence calculation method

        Returns:
            Confidence score between 0 and 1
        """
        if method == 'max_prob':
            return self._max_probability_confidence(probabilities)
        elif method == 'entropy':
            return self._entropy_based_confidence(probabilities)
        elif method == 'calibrated':
            return self._calibrated_confidence(probabilities)
        else:
            raise ValueError(f"Unknown confidence method: {method}")

    def _max_probability_confidence(self, probabilities: np.ndarray) -> float:
        """Confidence based on maximum probability."""
        if probabilities.ndim == 1:
            probabilities = probabilities.reshape(1, -1)

        max_probs = np.max(probabilities, axis=1)
        return float(np.mean(max_probs))  # Average across batch

    def _entropy_based_confidence(self, probabilities: np.ndarray) -> float:
        """Confidence based on prediction entropy (lower entropy = higher confidence)."""
        if probabilities.ndim == 1:
            probabilities = probabilities.reshape(1, -1)

        # Calculate entropy for each prediction
        entropies = entropy(probabilities, axis=1)

        # Normalize entropy to confidence (0 entropy = 1 confidence)
        max_entropy = np.log(probabilities.shape[1])  # Maximum possible entropy
        normalized_entropies = entropies / max_entropy

        # Convert to confidence (1 - normalized_entropy)
        confidences = 1 - normalized_entropies

        return float(np.mean(confidences))

    def _calibrated_confidence(self, probabilities: np.ndarray) -> float:
        """Temperature-scaled confidence using calibration data."""
        # Placeholder for temperature scaling
        # In practice, this would use Platt scaling or temperature scaling
        # fitted on validation data

        if not self.calibration_data:
            # Fallback to max probability
            return self._max_probability_confidence(probabilities)

        # Apply temperature scaling
        temperature = self.calibration_data.get('temperature', 1.0)
        scaled_probs = self._temperature_scale(probabilities, temperature)

        return self._max_probability_confidence(scaled_probs)

    @staticmethod
    def _temperature_scale(probabilities: np.ndarray, temperature: float) -> np.ndarray:
        """Apply temperature scaling to logits."""
        # Convert to logits first (assuming probabilities are already softmaxed)
        logits = np.log(probabilities + 1e-7)  # Add small epsilon to avoid log(0)
        scaled_logits = logits / temperature
        return ConfidenceScorer._softmax(scaled_logits)

    @staticmethod
    def _softmax(x: np.ndarray) -> np.ndarray:
        """Softmax function."""
        exp_x = np.exp(x - np.max(x, axis=-1, keepdims=True))
        return exp_x / np.sum(exp_x, axis=-1, keepdims=True)


class UncertaintyEstimator:
    """Estimate various types of uncertainty in predictions."""

    def __init__(self):
        pass

    def estimate_uncertainty(self, probabilities: np.ndarray,
                           method: str = 'entropy') -> Dict[str, float]:
        """
        Estimate prediction uncertainty using different methods.

        Args:
            probabilities: Class probabilities
            method: Uncertainty estimation method

        Returns:
            Dictionary with uncertainty metrics
        """
        metrics = {}

        if method == 'entropy':
            metrics['predictive_entropy'] = self._predictive_entropy(probabilities)
        elif method == 'mutual_information':
            metrics.update(self._mutual_information_uncertainty(probabilities))
        elif method == 'all':
            metrics['predictive_entropy'] = self._predictive_entropy(probabilities)
            metrics.update(self._mutual_information_uncertainty(probabilities))

        return metrics

    def _predictive_entropy(self, probabilities: np.ndarray) -> float:
        """Calculate predictive entropy."""
        if probabilities.ndim == 1:
            probabilities = probabilities.reshape(1, -1)

        entropies = entropy(probabilities, axis=1)
        return float(np.mean(entropies))

    def _mutual_information_uncertainty(self, probabilities: np.ndarray) -> Dict[str, float]:
        """Calculate mutual information uncertainty (aleatoric + epistemic)."""
        # For single forward pass, we can only estimate predictive entropy
        # In practice, this would require multiple forward passes (e.g., MC dropout)

        predictive_entropy = self._predictive_entropy(probabilities)

        # Placeholder: assume all uncertainty is aleatoric for single pass
        return {
            'aleatoric_uncertainty': predictive_entropy,
            'epistemic_uncertainty': 0.0,
            'total_uncertainty': predictive_entropy
        }


class ConfidenceAggregator:
    """Aggregate confidence scores from multiple models."""

    def __init__(self):
        self.scorer = ConfidenceScorer()
        self.estimator = UncertaintyEstimator()

    def aggregate_confidence(self, model_outputs: Dict[str, Any]) -> Dict[str, float]:
        """
        Aggregate confidence from multiple ML models.

        Args:
            model_outputs: Dictionary with model predictions
                Expected keys: 'gnn_probabilities', 'pointnet_probabilities'

        Returns:
            Aggregated confidence metrics
        """
        confidences = {}

        # Calculate confidence for each model
        if 'gnn_probabilities' in model_outputs:
            gnn_probs = np.array(model_outputs['gnn_probabilities'])
            confidences['gnn'] = self.scorer.calculate_confidence(gnn_probs)

        if 'pointnet_probabilities' in model_outputs:
            pointnet_probs = np.array(model_outputs['pointnet_probabilities'])
            confidences['pointnet'] = self.scorer.calculate_confidence(pointnet_probs)

        # Aggregate across models
        if confidences:
            confidences['aggregate'] = np.mean(list(confidences.values()))
            confidences['min'] = min(confidences.values())
            confidences['max'] = max(confidences.values())
        else:
            confidences['aggregate'] = 0.0
            confidences['min'] = 0.0
            confidences['max'] = 0.0

        return confidences

    def calculate_overall_confidence(self, model_outputs: Dict[str, Any],
                                   geometry_features: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Calculate comprehensive confidence assessment.

        Args:
            model_outputs: ML model outputs
            geometry_features: Optional geometry features for confidence adjustment

        Returns:
            Comprehensive confidence assessment
        """
        # Aggregate model confidences
        model_confidences = self.aggregate_confidence(model_outputs)

        # Estimate uncertainty
        uncertainty = {}
        if 'gnn_probabilities' in model_outputs:
            uncertainty['gnn'] = self.estimator.estimate_uncertainty(
                np.array(model_outputs['gnn_probabilities'])
            )
        if 'pointnet_probabilities' in model_outputs:
            uncertainty['pointnet'] = self.estimator.estimate_uncertainty(
                np.array(model_outputs['pointnet_probabilities'])
            )

        # Adjust confidence based on geometry complexity
        adjusted_confidence = self._adjust_for_geometry_complexity(
            model_confidences['aggregate'], geometry_features
        )

        return {
            'model_confidences': model_confidences,
            'uncertainty_estimates': uncertainty,
            'adjusted_confidence': adjusted_confidence,
            'confidence_category': self._categorize_confidence(adjusted_confidence)
        }

    def _adjust_for_geometry_complexity(self, base_confidence: float,
                                      geometry_features: Dict[str, Any] = None) -> float:
        """Adjust confidence based on geometry complexity."""
        if not geometry_features:
            return base_confidence

        adjustment = 1.0

        # Penalize confidence for complex features
        if geometry_features.get('has_complex_curves', False):
            adjustment *= 0.9
        if geometry_features.get('has_undercuts', False):
            adjustment *= 0.95
        if geometry_features.get('num_features', 0) > 10:
            adjustment *= 0.9

        # Boost confidence for simple geometries
        if geometry_features.get('is_prismatic', False):
            adjustment *= 1.1

        return min(1.0, base_confidence * adjustment)

    def _categorize_confidence(self, confidence: float) -> str:
        """Categorize confidence level."""
        if confidence >= 0.8:
            return 'high'
        elif confidence >= 0.6:
            return 'medium'
        elif confidence >= 0.4:
            return 'low'
        else:
            return 'very_low'