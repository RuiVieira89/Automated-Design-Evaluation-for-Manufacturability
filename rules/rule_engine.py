"""
Rule Engine orchestrator - the main entry point for DfX analysis.

Coordinates DfX checks, dependency scheduling, and result aggregation.
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import networkx as nx

from .base import DfxCheck, CheckResult, Severity
from .registry import RuleRegistry
from .param_store import ParamStore
from .dependency_graph import DependencyGraph, CheckScheduler
from .tolerance_solver import ToleranceSolver
from .checks import (
    WallThicknessCheck,
    DraftAngleCheck,
    HoleRatioCheck,
    UndercutDetectionCheck,
    ToolAccessConeCheck
)


@dataclass
class AnalysisReport:
    """Result of complete DfX analysis."""
    check_results: List[CheckResult]
    overall_status: Severity
    feasible: bool
    critical_margins: Dict[str, float]
    constraint_summary: str
    messages: List[str]


class RuleEngine:
    """
    Main DfX rule engine.

    Orchestrates check execution, dependency scheduling, tolerance solving,
    and result aggregation.
    """

    def __init__(self):
        """Initialize rule engine with standard checks."""
        self.registry = RuleRegistry()
        self.param_store = ParamStore()
        self.dependency_graph = DependencyGraph()
        self.tolerance_solver = ToleranceSolver()

        # Register standard checks
        self._register_standard_checks()

        # Set up default dependency graph
        self._setup_default_dependencies()

    def _register_standard_checks(self) -> None:
        """Register all standard DfX checks."""
        self.registry.register('wall_thickness', WallThicknessCheck)
        self.registry.register('draft_angle', DraftAngleCheck)
        self.registry.register('hole_ratio', HoleRatioCheck)
        self.registry.register('undercut_detection', UndercutDetectionCheck)
        self.registry.register('tool_access', ToolAccessConeCheck)

    def _setup_default_dependencies(self) -> None:
        """Set up default dependency graph."""
        # Add check nodes
        for check_name in self.registry.list_checks():
            self.dependency_graph.add_node(check_name, node_type='check')

        # Wall thickness has no dependencies
        # Draft angle depends on wall thickness (both affect mold complexity)
        self.dependency_graph.add_edge(
            'wall_thickness', 'draft_angle',
            reason='Both affect moldability'
        )

        # Undercut depends on draft angle
        self.dependency_graph.add_edge(
            'draft_angle', 'undercut_detection',
            reason='Undercuts interact with draft'
        )

        # Hole ratio independent but related
        # Tool access depends on all geometry
        for check in ['wall_thickness', 'draft_angle', 'hole_ratio']:
            self.dependency_graph.add_edge(
                check, 'tool_access',
                reason='Tool access depends on geometry'
            )

    def register_custom_check(self, name: str, check_class: type) -> None:
        """
        Register a custom check.

        Args:
            name: Unique check identifier
            check_class: Must inherit from DfxCheck
        """
        self.registry.register(name, check_class)
        self.dependency_graph.add_node(name, node_type='check')

    def set_process(self, process_name: str) -> None:
        """
        Select manufacturing process.

        Args:
            process_name: Process identifier in ParamStore
        """
        self.param_store.select_process(process_name)

    def analyze(self, geometry_data: Dict[str, Any],
                checks_to_run: Optional[List[str]] = None) -> AnalysisReport:
        """
        Run complete DfX analysis.

        Args:
            geometry_data: Geometry results from Layer 2
                          (contains brep_results and mesh_results)
            checks_to_run: List of check names to run. If None, runs all.

        Returns:
            AnalysisReport with all results and metrics
        """
        messages = []
        check_results: List[CheckResult] = []

        # Determine which checks to run
        if checks_to_run is None:
            checks_to_run = self.registry.list_checks()

        # Get execution order from dependency graph
        try:
            execution_order = self.dependency_graph.get_execution_order()
            checks_to_run = [c for c in execution_order if c in checks_to_run]
        except ValueError as e:
            messages.append(f"Dependency cycle detected: {e}")

        # Get parameters for current process
        params = self.param_store.to_dict()

        # Run checks in order
        scheduler = CheckScheduler(self.dependency_graph)
        critical_margins = {}

        for check_name in checks_to_run:
            if not scheduler.should_run(check_name):
                messages.append(f"Skipping {check_name} (unmet dependency)")
                continue

            try:
                # Instantiate and run check
                check = self.registry.instantiate(check_name)
                result = check.run(geometry_data, params)
                check_results.append(result)

                # Track critical margins
                if result.margin is not None:
                    critical_margins[check_name] = result.margin

                # Add to tolerance solver
                if result.margin is not None:
                    self.tolerance_solver.add_check_result(
                        check_name,
                        result.margin,
                        result.measured_value or 0,
                        result.threshold or 0
                    )

                # Mark as failed for cascading logic
                if result.severity == Severity.FAIL:
                    scheduler.mark_failed(check_name)
                    messages.append(f"{check_name}: FAILED")

            except Exception as e:
                messages.append(f"Error running {check_name}: {e}")
                scheduler.mark_failed(check_name)

        # Check overall feasibility
        feasibility = self.tolerance_solver.check_feasibility()

        # Determine overall status
        fail_count = sum(1 for r in check_results if r.severity == Severity.FAIL)
        warn_count = sum(1 for r in check_results if r.severity == Severity.WARN)

        if fail_count > 0:
            overall_status = Severity.FAIL
        elif warn_count > 0:
            overall_status = Severity.WARN
        else:
            overall_status = Severity.PASS

        return AnalysisReport(
            check_results=check_results,
            overall_status=overall_status,
            feasible=feasibility['feasible'],
            critical_margins=critical_margins,
            constraint_summary=self.tolerance_solver.get_constraint_summary(),
            messages=messages
        )

    def get_dependency_info(self) -> str:
        """Get information about check dependencies."""
        return self.dependency_graph.visualize_description()

    def print_report(self, report: AnalysisReport) -> str:
        """
        Format analysis report for display.

        Args:
            report: AnalysisReport from analyze()

        Returns:
            Formatted string
        """
        lines = [
            "=" * 60,
            "DfX ANALYSIS REPORT",
            "=" * 60,
            "",
            f"Overall Status: {report.overall_status.value.upper()}",
            f"Feasible: {'YES' if report.feasible else 'NO'}",
            "",
            "Check Results:",
            "-" * 60
        ]

        for result in report.check_results:
            status_icon = "✓" if result.severity == Severity.PASS else \
                         "⚠" if result.severity == Severity.WARN else "✗"
            margin_str = f" (margin: {result.margin:+.2f})" if result.margin is not None else ""
            lines.append(
                f"{status_icon} {result.check_name}: {result.severity.value.upper()}"
                f"{margin_str}"
            )
            if result.message:
                lines.append(f"    {result.message}")

        lines.extend([
            "",
            report.constraint_summary,
            ""
        ])

        if report.messages:
            lines.extend([
                "Notes:",
                "-" * 60
            ])
            for msg in report.messages:
                lines.append(f"  • {msg}")

        lines.append("=" * 60)
        return "\n".join(lines)