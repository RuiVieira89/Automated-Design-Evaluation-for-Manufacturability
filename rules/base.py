"""
Base classes and data structures for the Rule Engine.

Defines the DfxCheck abstract interface and CheckResult data structures.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, List
from enum import Enum


class Severity(Enum):
    """Check result severity level."""
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


@dataclass
class CheckResult:
    """Result of a single DfX check."""
    check_name: str
    severity: Severity
    measured_value: Optional[float] = None
    threshold: Optional[float] = None
    margin: Optional[float] = None  # measured - threshold
    message: str = ""
    violations: List[Dict[str, Any]] = field(default_factory=list)  # Per-feature violations
    constraint_bounds: Optional[Dict[str, tuple]] = None  # For tolerance solver

    @property
    def passed(self) -> bool:
        """Returns True if check passed."""
        return self.severity == Severity.PASS


class DfxCheck(ABC):
    """
    Abstract base class for all DfX checks.

    Each concrete check implements run() to analyze geometry against
    manufacturing constraints.
    """

    def __init__(self, name: str):
        """
        Initialize check.

        Args:
            name: Unique identifier for this check (used in registry)
        """
        self.name = name

    @abstractmethod
    def run(self, geometry_data: Dict[str, Any], params: Dict[str, Any]) -> CheckResult:
        """
        Run the check against geometry.

        Args:
            geometry_data: Dictionary containing B-Rep results, mesh results, etc.
                          from Layer 2 (GeometryOutputs)
            params: Manufacturing parameters for this check
                   (min_wall, min_draft_angle, etc.)

        Returns:
            CheckResult with severity, measured value, and violations
        """
        pass

    def set_threshold(self, threshold: float) -> None:
        """Set the threshold for this check."""
        self.threshold = threshold