# segmentation/inference/process_classifier.py
"""
Process classification and manufacturability reasoning.
"""

import numpy as np
from typing import Dict, List, Any, Tuple, Optional
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ManufacturingProcess(Enum):
    """Manufacturing process types."""
    THREE_AXIS_MILL = "3-axis_mill"
    FIVE_AXIS_MILL = "5-axis_mill"
    TURNING = "turning"
    CASTING = "casting"
    INJECTION_MOLDING = "injection_molding"
    SHEET_METAL = "sheet_metal"
    ADDITIVE = "additive"
    EDM = "edm"


class ProcessCapability:
    """Capability assessment for a manufacturing process."""

    def __init__(self, process: ManufacturingProcess, confidence: float,
                 limitations: List[str] = None, requirements: List[str] = None):
        self.process = process
        self.confidence = confidence  # 0-1
        self.limitations = limitations or []
        self.requirements = requirements or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            'process': self.process.value,
            'confidence': self.confidence,
            'limitations': self.limitations,
            'requirements': self.requirements
        }


class ProcessClassifier:
    """Classifies manufacturing processes based on ML predictions and geometry."""

    def __init__(self):
        # Process capability mappings
        self.process_rules = self._load_process_rules()

    def classify(self, ml_predictions: Dict[str, Any],
                geometry_features: Dict[str, Any]) -> List[ProcessCapability]:
        """
        Classify suitable manufacturing processes.

        Args:
            ml_predictions: ML model outputs (gnn and pointnet results)
            geometry_features: Geometric features from Layer 3

        Returns:
            List of ProcessCapability objects
        """
        capabilities = []

        # Get predictions from both models
        gnn_probs = np.array(ml_predictions.get('gnn_probabilities', np.zeros(5)))
        pointnet_probs = np.array(ml_predictions.get('pointnet_probabilities', np.zeros(5)))

        # Align lengths if necessary
        max_len = max(len(gnn_probs), len(pointnet_probs))
        if len(gnn_probs) < max_len:
            gnn_probs = np.pad(gnn_probs, (0, max_len - len(gnn_probs)), 'constant')
        if len(pointnet_probs) < max_len:
            pointnet_probs = np.pad(pointnet_probs, (0, max_len - len(pointnet_probs)), 'constant')

        # Combine predictions (simple average for now)
        combined_probs = (gnn_probs + pointnet_probs) / 2

        # Map to processes based on highest probability class
        predicted_class = np.argmax(combined_probs)
        confidence = combined_probs[predicted_class]

        # Get process capabilities based on predicted class and geometry
        process_capabilities = self._get_process_capabilities(
            predicted_class, confidence, geometry_features
        )

        return process_capabilities

    def _get_process_capabilities(self, predicted_class: int, confidence: float,
                                geometry_features: Dict[str, Any]) -> List[ProcessCapability]:
        """Determine process capabilities based on prediction and geometry."""
        capabilities = []

        # Extract key geometry features
        has_deep_holes = geometry_features.get('deep_holes', False)
        has_complex_curves = geometry_features.get('complex_curves', False)
        has_undercuts = geometry_features.get('undercuts', False)
        wall_thickness = geometry_features.get('min_wall_thickness', 1.0)
        draft_angles = geometry_features.get('draft_angles', [])

        # Class-based process mapping (simplified)
        if predicted_class == 0:  # Simple prismatic
            capabilities.extend([
                ProcessCapability(ManufacturingProcess.THREE_AXIS_MILL, confidence * 0.9),
                ProcessCapability(ManufacturingProcess.CASTING, confidence * 0.7),
                ProcessCapability(ManufacturingProcess.SHEET_METAL, confidence * 0.6)
            ])

        elif predicted_class == 1:  # Complex geometry
            capabilities.extend([
                ProcessCapability(ManufacturingProcess.FIVE_AXIS_MILL, confidence * 0.8),
                ProcessCapability(ManufacturingProcess.ADDITIVE, confidence * 0.7),
                ProcessCapability(ManufacturingProcess.CASTING, confidence * 0.5,
                               limitations=["May require cores for complex shapes"])
            ])

        elif predicted_class == 2:  # Rotational
            capabilities.extend([
                ProcessCapability(ManufacturingProcess.TURNING, confidence * 0.9),
                ProcessCapability(ManufacturingProcess.CASTING, confidence * 0.6)
            ])

        elif predicted_class == 3:  # Thin-walled
            capabilities.extend([
                ProcessCapability(ManufacturingProcess.INJECTION_MOLDING, confidence * 0.8),
                ProcessCapability(ManufacturingProcess.SHEET_METAL, confidence * 0.7),
                ProcessCapability(ManufacturingProcess.CASTING, confidence * 0.5,
                               limitations=["May require special casting techniques"])
            ])

        elif predicted_class == 4:  # High precision
            capabilities.extend([
                ProcessCapability(ManufacturingProcess.FIVE_AXIS_MILL, confidence * 0.9),
                ProcessCapability(ManufacturingProcess.EDM, confidence * 0.8),
                ProcessCapability(ManufacturingProcess.ADDITIVE, confidence * 0.6)
            ])

        # Apply geometry-based adjustments
        capabilities = self._apply_geometry_adjustments(capabilities, geometry_features)

        # Sort by confidence
        capabilities.sort(key=lambda x: x.confidence, reverse=True)

        return capabilities

    def _apply_geometry_adjustments(self, capabilities: List[ProcessCapability],
                                  geometry_features: Dict[str, Any]) -> List[ProcessCapability]:
        """Adjust capabilities based on specific geometry features."""
        adjusted = []

        for cap in capabilities:
            new_cap = ProcessCapability(
                cap.process,
                cap.confidence,
                cap.limitations.copy(),
                cap.requirements.copy()
            )

            # Deep holes penalty for 3-axis milling
            if cap.process == ManufacturingProcess.THREE_AXIS_MILL:
                if geometry_features.get('deep_holes', False):
                    new_cap.confidence *= 0.7
                    new_cap.limitations.append("Deep holes may require additional operations")

            # Undercuts penalty for milling
            if cap.process in [ManufacturingProcess.THREE_AXIS_MILL, ManufacturingProcess.FIVE_AXIS_MILL]:
                if geometry_features.get('undercuts', False):
                    new_cap.confidence *= 0.8
                    new_cap.limitations.append("Undercuts may require electrode EDM")

            # Thin walls penalty for casting
            if cap.process == ManufacturingProcess.CASTING:
                min_thickness = geometry_features.get('min_wall_thickness', 1.0)
                if min_thickness < 2.0:
                    new_cap.confidence *= 0.6
                    new_cap.limitations.append("Thin walls may cause casting defects")

            # Draft angle requirements for molding
            if cap.process == ManufacturingProcess.INJECTION_MOLDING:
                draft_angles = geometry_features.get('draft_angles', [])
                poor_draft = any(angle < 1.0 for angle in draft_angles)  # degrees
                if poor_draft:
                    new_cap.confidence *= 0.7
                    new_cap.requirements.append("May require texture or draft angle optimization")

            adjusted.append(new_cap)

        return adjusted

    def _load_process_rules(self) -> Dict[str, Any]:
        """Load process capability rules (placeholder for now)."""
        return {
            'tolerance_requirements': {
                ManufacturingProcess.THREE_AXIS_MILL: {'typical': 0.1, 'min': 0.05},
                ManufacturingProcess.FIVE_AXIS_MILL: {'typical': 0.05, 'min': 0.01},
                ManufacturingProcess.CASTING: {'typical': 0.5, 'min': 0.2},
                ManufacturingProcess.INJECTION_MOLDING: {'typical': 0.1, 'min': 0.05},
            },
            'material_compatibility': {
                # Material-process compatibility matrix would go here
            }
        }


class ManufacturabilityAssessment:
    """Complete manufacturability assessment combining ML and rules."""

    def __init__(self, ml_predictions: Dict[str, Any],
                 process_capabilities: List[ProcessCapability],
                 rule_results: List[Any],  # From Layer 3
                 confidence_threshold: float = 0.65):
        self.ml_predictions = ml_predictions
        self.process_capabilities = process_capabilities
        self.rule_results = rule_results
        self.confidence_threshold = confidence_threshold

    def get_recommendations(self) -> Dict[str, Any]:
        """Get manufacturing recommendations with fallback logic."""
        # Check if ML confidence is high enough
        ml_confidence = self._calculate_ml_confidence()

        if ml_confidence >= self.confidence_threshold:
            # Use ML-based recommendations
            return self._ml_based_recommendations()
        else:
            # Fall back to rule-based assessment
            logger.info(f"ML confidence {ml_confidence:.3f} below threshold {self.confidence_threshold}, "
                       "falling back to rule-based assessment")
            return self._rule_based_recommendations()

    def _calculate_ml_confidence(self) -> float:
        """Calculate overall ML confidence score."""
        gnn_conf = self.ml_predictions.get('gnn_confidence', 0.0)
        pointnet_conf = self.ml_predictions.get('pointnet_confidence', 0.0)
        return (gnn_conf + pointnet_conf) / 2

    def _ml_based_recommendations(self) -> Dict[str, Any]:
        """Generate recommendations based on ML predictions."""
        top_process = self.process_capabilities[0] if self.process_capabilities else None

        return {
            'method': 'ml_based',
            'recommended_process': top_process.process.value if top_process else None,
            'confidence': top_process.confidence if top_process else 0.0,
            'alternative_processes': [
                cap.to_dict() for cap in self.process_capabilities[1:3]  # Top 3
            ],
            'limitations': top_process.limitations if top_process else [],
            'requirements': top_process.requirements if top_process else []
        }

    def _rule_based_recommendations(self) -> Dict[str, Any]:
        """Generate recommendations based on Layer 3 rules."""
        # Analyze rule results to determine suitable processes
        # This is a simplified fallback - in practice would analyze violations

        has_critical_violations = any(
            result.severity == 'FAIL' for result in self.rule_results
        )

        if has_critical_violations:
            recommended = ManufacturingProcess.ADDITIVE
            confidence = 0.8  # Additive can handle complex geometries
        else:
            recommended = ManufacturingProcess.THREE_AXIS_MILL
            confidence = 0.7

        return {
            'method': 'rule_fallback',
            'recommended_process': recommended.value,
            'confidence': confidence,
            'reason': 'ML confidence below threshold, using rule-based assessment',
            'limitations': [],
            'requirements': []
        }