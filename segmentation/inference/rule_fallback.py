# segmentation/inference/rule_fallback.py
"""
Rule-based fallback when ML confidence is insufficient.
"""

from typing import Dict, Any, List, Optional, Tuple
from rules.rule_engine import CheckResult, AnalysisReport
from .process_classifier import ManufacturingProcess, ProcessCapability
import logging

logger = logging.getLogger(__name__)


class RuleFallbackEngine:
    """Provides rule-based manufacturing recommendations when ML fails."""

    def __init__(self, confidence_threshold: float = 0.65):
        self.confidence_threshold = confidence_threshold

    def should_fallback(self, ml_confidence: float) -> bool:
        """Determine if we should fall back to rules."""
        return ml_confidence < self.confidence_threshold

    def generate_fallback_recommendation(self, rule_results: List[CheckResult],
                                       geometry_features: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate manufacturing recommendation based on rule violations.

        Args:
            rule_results: Results from Layer 3 rule engine
            geometry_features: Geometric features

        Returns:
            Recommendation dictionary
        """
        # Analyze violations
        violations = self._analyze_violations(rule_results)

        # Determine suitable processes based on violations
        suitable_processes = self._determine_suitable_processes(violations, geometry_features)

        # Rank processes by suitability
        ranked_processes = self._rank_processes(suitable_processes, violations)

        # Generate detailed recommendation
        recommendation = self._create_recommendation(ranked_processes, violations)

        return recommendation

    def _analyze_violations(self, rule_results: List[CheckResult]) -> Dict[str, Any]:
        """Analyze rule violations to understand manufacturability issues."""
        violations = {
            'critical': [],
            'warnings': [],
            'passes': [],
            'by_check_type': {}
        }

        for result in rule_results:
            severity = result.severity.value if hasattr(result.severity, 'value') else str(result.severity).lower()
            if severity == 'fail':
                violations['critical'].append(result)
            elif severity == 'warn':
                violations['warnings'].append(result)
            else:
                violations['passes'].append(result)

            # Group by check type
            check_type = result.check_name
            if check_type not in violations['by_check_type']:
                violations['by_check_type'][check_type] = []
            violations['by_check_type'][check_type].append(result)

        # Calculate violation statistics
        violations['stats'] = {
            'total_checks': len(rule_results),
            'critical_count': len(violations['critical']),
            'warning_count': len(violations['warnings']),
            'pass_count': len(violations['passes']),
            'critical_rate': len(violations['critical']) / len(rule_results) if rule_results else 0
        }

        return violations

    def _determine_suitable_processes(self, violations: Dict[str, Any],
                                    geometry_features: Dict[str, Any]) -> List[ManufacturingProcess]:
        """Determine which processes are suitable based on violations and geometry."""
        suitable = []

        critical_rate = violations['stats']['critical_rate']
        has_critical_violations = violations['stats']['critical_count'] > 0

        # Extract key geometry features
        has_deep_features = geometry_features.get('has_deep_holes', False) or \
                           geometry_features.get('has_deep_pockets', False)
        has_complex_curves = geometry_features.get('has_complex_curves', False)
        has_undercuts = geometry_features.get('has_undercuts', False)
        is_thin_walled = geometry_features.get('is_thin_walled', False)
        is_prismatic = geometry_features.get('is_prismatic', True)

        # Decision tree for process selection
        if has_critical_violations:
            # Critical violations require more flexible processes
            if has_complex_curves or has_undercuts:
                suitable.extend([ManufacturingProcess.ADDITIVE, ManufacturingProcess.FIVE_AXIS_MILL])
            elif is_thin_walled:
                suitable.extend([ManufacturingProcess.INJECTION_MOLDING, ManufacturingProcess.CASTING])
            else:
                suitable.extend([ManufacturingProcess.FIVE_AXIS_MILL, ManufacturingProcess.ADDITIVE])
        else:
            # No critical violations - more options available
            if is_prismatic and not has_deep_features:
                suitable.extend([ManufacturingProcess.THREE_AXIS_MILL, ManufacturingProcess.CASTING])
            elif has_complex_curves:
                suitable.extend([ManufacturingProcess.FIVE_AXIS_MILL, ManufacturingProcess.ADDITIVE])
            elif is_thin_walled:
                suitable.extend([ManufacturingProcess.INJECTION_MOLDING, ManufacturingProcess.SHEET_METAL])
            else:
                suitable.extend([ManufacturingProcess.THREE_AXIS_MILL, ManufacturingProcess.FIVE_AXIS_MILL])

        # Always include some basic processes as fallback
        if not suitable:
            suitable = [ManufacturingProcess.THREE_AXIS_MILL, ManufacturingProcess.CASTING]

        return list(set(suitable))  # Remove duplicates

    def _rank_processes(self, processes: List[ManufacturingProcess],
                       violations: Dict[str, Any]) -> List[Tuple[ManufacturingProcess, float]]:
        """Rank processes by suitability score."""
        ranked = []

        for process in processes:
            score = self._calculate_process_score(process, violations)
            ranked.append((process, score))

        # Sort by score (higher is better)
        ranked.sort(key=lambda x: x[1], reverse=True)

        return ranked

    def _calculate_process_score(self, process: ManufacturingProcess,
                               violations: Dict[str, Any]) -> float:
        """Calculate suitability score for a process."""
        base_score = 1.0

        # Adjust based on violation types
        critical_checks = [v.check_name for v in violations['critical']]

        if process == ManufacturingProcess.THREE_AXIS_MILL:
            # Penalize for 5-axis specific features
            if any('undercut' in check.lower() for check in critical_checks):
                base_score *= 0.5
            if any('complex' in check.lower() for check in critical_checks):
                base_score *= 0.7

        elif process == ManufacturingProcess.FIVE_AXIS_MILL:
            # Good for complex geometries
            if any('undercut' in check.lower() for check in critical_checks):
                base_score *= 1.2
            if any('complex' in check.lower() for check in critical_checks):
                base_score *= 1.1

        elif process == ManufacturingProcess.ADDITIVE:
            # Very flexible, good for complex geometries
            base_score *= 1.3  # Boost additive for complex cases
            if violations['stats']['critical_count'] > 2:
                base_score *= 1.2  # Even better when many violations

        elif process == ManufacturingProcess.CASTING:
            # Good for simple shapes, penalize for thin walls
            if any('wall' in check.lower() for check in critical_checks):
                base_score *= 0.6

        elif process == ManufacturingProcess.INJECTION_MOLDING:
            # Good for thin walls, requires draft
            if any('draft' in check.lower() for check in critical_checks):
                base_score *= 0.7

        return base_score

    def _create_recommendation(self, ranked_processes: List[Tuple[ManufacturingProcess, float]],
                             violations: Dict[str, Any]) -> Dict[str, Any]:
        """Create detailed recommendation from ranked processes."""
        if not ranked_processes:
            return {
                'method': 'rule_fallback',
                'recommended_process': None,
                'confidence': 0.0,
                'reason': 'No suitable processes identified'
            }

        top_process, top_score = ranked_processes[0]

        # Normalize score to confidence
        max_possible_score = 2.0  # Assuming max score is around 2.0
        confidence = min(1.0, top_score / max_possible_score)

        # Get limitations and requirements
        limitations, requirements = self._get_process_details(top_process, violations)

        return {
            'method': 'rule_fallback',
            'recommended_process': top_process.value,
            'confidence': confidence,
            'score': top_score,
            'alternative_processes': [
                {'process': p.value, 'score': s} for p, s in ranked_processes[1:3]
            ],
            'limitations': limitations,
            'requirements': requirements,
            'violation_summary': {
                'critical_count': violations['stats']['critical_count'],
                'warning_count': violations['stats']['warning_count'],
                'total_checks': violations['stats']['total_checks']
            }
        }

    def _get_process_details(self, process: ManufacturingProcess,
                           violations: Dict[str, Any]) -> Tuple[List[str], List[str]]:
        """Get limitations and requirements for a process."""
        limitations = []
        requirements = []

        critical_checks = [v.check_name for v in violations['critical']]

        if process == ManufacturingProcess.THREE_AXIS_MILL:
            if any('undercut' in check.lower() for check in critical_checks):
                limitations.append("Cannot access undercut features")
                requirements.append("May require electrode EDM for undercuts")
            if any('deep' in check.lower() for check in critical_checks):
                requirements.append("May require special tooling for deep features")

        elif process == ManufacturingProcess.ADDITIVE:
            requirements.append("Supports complex geometries without tooling limitations")
            limitations.append("May have surface finish and accuracy limitations")
            if any('tolerance' in check.lower() for check in critical_checks):
                limitations.append("Post-processing may be required for tight tolerances")

        elif process == ManufacturingProcess.CASTING:
            requirements.append("Requires pattern and core design")
            limitations.append("May have draft angle requirements")
            if any('wall' in check.lower() for check in critical_checks):
                limitations.append("Thin walls may cause casting defects")

        return limitations, requirements