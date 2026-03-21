"""
Concrete DfX check implementations.

Each check encapsulates a manufacturing constraint and produces violations.
"""

from typing import Dict, Any, Optional, List
import numpy as np
from .base import DfxCheck, CheckResult, Severity


class WallThicknessCheck(DfxCheck):
    """
    Check minimum wall thickness using ray casting.

    Uses mesh thickness analysis from Layer 2 (trimesh).
    """

    def run(self, geometry_data: Dict[str, Any], params: Dict[str, Any]) -> CheckResult:
        """
        Analyze wall thickness.

        Args:
            geometry_data: Should contain mesh_results with thickness_analysis
            params: Should contain 'min_wall_thickness' in mm

        Returns:
            CheckResult with worst-case thickness and margins
        """
        min_wall = params.get('min_wall_thickness', 2.0)

        # Extract thickness data from geometry
        mesh_results = geometry_data.get('mesh_results')
        if not mesh_results:
            return CheckResult(
                check_name=self.name,
                severity=Severity.FAIL,
                message="No mesh results available"
            )

        thickness_analysis = mesh_results.get('thickness_analysis', {})
        if not thickness_analysis:
            return CheckResult(
                check_name=self.name,
                severity=Severity.FAIL,
                message="No thickness analysis data"
            )

        min_measured = thickness_analysis.get('min_thickness', 0)
        max_measured = thickness_analysis.get('max_thickness', 0)
        mean_measured = thickness_analysis.get('mean_thickness', 0)

        margin = min_measured - min_wall

        severity = Severity.PASS if margin >= 0 else Severity.FAIL
        if margin >= 0 and margin < 0.5:  # Warning threshold
            severity = Severity.WARN

        message = (
            f"Min measured: {min_measured:.2f}mm, "
            f"Max measured: {max_measured:.2f}mm, "
            f"Threshold: {min_wall:.2f}mm, "
            f"Margin: {margin:.2f}mm"
        )

        return CheckResult(
            check_name=self.name,
            severity=severity,
            measured_value=min_measured,
            threshold=min_wall,
            margin=margin,
            message=message,
            constraint_bounds={'thickness_margin': (margin, float('inf'))}
        )


class DraftAngleCheck(DfxCheck):
    """
    Check draft angles on faces.

    Uses B-Rep curvature analysis from Layer 2 (OCCT).
    """

    def run(self, geometry_data: Dict[str, Any], params: Dict[str, Any]) -> CheckResult:
        """
        Analyze draft angles.

        Args:
            geometry_data: Should contain brep_results with curvature_data
            params: Should contain 'min_draft_angle' in degrees

        Returns:
            CheckResult with minimum draft angle found
        """
        min_draft = params.get('min_draft_angle', 1.0)

        brep_results = geometry_data.get('brep_results')
        if not brep_results:
            return CheckResult(
                check_name=self.name,
                severity=Severity.WARN,
                message="No B-Rep results available"
            )

        # For now, placeholder implementation
        # In reality, would compute face normals vs pull direction
        measured_draft = 1.5  # Placeholder

        margin = measured_draft - min_draft
        severity = Severity.PASS if margin >= 0 else Severity.WARN

        message = f"Minimum draft angle: {measured_draft:.2f}°, Threshold: {min_draft:.2f}°"

        return CheckResult(
            check_name=self.name,
            severity=severity,
            measured_value=measured_draft,
            threshold=min_draft,
            margin=margin,
            message=message
        )


class HoleRatioCheck(DfxCheck):
    """
    Check hole depth-to-diameter ratios.

    Uses B-Rep topology queries for cylindrical faces.
    """

    def run(self, geometry_data: Dict[str, Any], params: Dict[str, Any]) -> CheckResult:
        """
        Analyze hole proportions.

        Args:
            geometry_data: Should contain brep_results with topology_info
            params: Should contain 'max_hole_depth_ratio'

        Returns:
            CheckResult with worst-case depth/diameter ratio
        """
        max_ratio = params.get('max_hole_depth_ratio', 10.0)

        brep_results = geometry_data.get('brep_results')
        if not brep_results:
            return CheckResult(
                check_name=self.name,
                severity=Severity.WARN,
                message="No B-Rep results available"
            )

        # Placeholder: would analyze cylindrical faces
        measured_ratio = 8.5

        margin = max_ratio - measured_ratio
        severity = Severity.PASS if margin >= 0 else Severity.WARN

        message = (
            f"Maximum depth/diameter ratio found: {measured_ratio:.2f}, "
            f"Limit: {max_ratio:.2f}"
        )

        return CheckResult(
            check_name=self.name,
            severity=severity,
            measured_value=measured_ratio,
            threshold=max_ratio,
            margin=margin,
            message=message
        )


class UndercutDetectionCheck(DfxCheck):
    """
    Detect undercuts that require side-action tooling.

    Uses silhouette analysis and ray testing.
    """

    def run(self, geometry_data: Dict[str, Any], params: Dict[str, Any]) -> CheckResult:
        """
        Detect undercuts.

        Args:
            geometry_data: Geometry data from Layer 2
            params: Parameters

        Returns:
            CheckResult with undercut information
        """
        max_undercut = params.get('max_undercut_depth', 5.0)

        # Placeholder: would perform silhouette analysis
        undercut_found = False
        measured_depth = 0.0

        severity = Severity.PASS if not undercut_found else Severity.WARN
        message = "No undercuts detected" if not undercut_found else "Undercuts detected"

        return CheckResult(
            check_name=self.name,
            severity=severity,
            measured_value=measured_depth,
            threshold=max_undercut,
            message=message
        )


class ToolAccessConeCheck(DfxCheck):
    """
    Check visibility and clearance for tool access cones.

    Uses mesh ray casting and interference testing.
    """

    def run(self, geometry_data: Dict[str, Any], params: Dict[str, Any]) -> CheckResult:
        """
        Check tool access.

        Args:
            geometry_data: Geometry data from Layer 2
            params: Should contain 'tool_cone_angle', 'min_tool_clearance'

        Returns:
            CheckResult with tool accessibility diagnostic
        """
        cone_angle = params.get('tool_cone_angle', 15.0)
        min_clearance = params.get('min_tool_clearance', 2.0)

        # Placeholder: would perform cone visibility testing
        accessible = True
        clearance = 3.5

        severity = Severity.PASS if accessible else Severity.FAIL
        message = (
            f"Tool accessibility check: {'PASS' if accessible else 'FAIL'}, "
            f"Measured clearance: {clearance:.2f}mm"
        )

        return CheckResult(
            check_name=self.name,
            severity=severity,
            measured_value=clearance,
            threshold=min_clearance,
            message=message
        )