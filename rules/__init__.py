"""
Rule Engine - Layer 3

DfX rule evaluation with dependency scheduling and tolerance solving.
"""

from .base import DfxCheck, CheckResult, Severity
from .registry import RuleRegistry
from .param_store import ParamStore, ProcessParams
from .dependency_graph import DependencyGraph, CheckScheduler
from .tolerance_solver import ToleranceSolver
from .checks import (
    WallThicknessCheck,
    DraftAngleCheck,
    HoleRatioCheck,
    UndercutDetectionCheck,
    ToolAccessConeCheck
)
from .rule_engine import RuleEngine, AnalysisReport

__all__ = [
    'DfxCheck',
    'CheckResult',
    'Severity',
    'RuleRegistry',
    'ParamStore',
    'ProcessParams',
    'DependencyGraph',
    'CheckScheduler',
    'ToleranceSolver',
    'WallThicknessCheck',
    'DraftAngleCheck',
    'HoleRatioCheck',
    'UndercutDetectionCheck',
    'ToolAccessConeCheck',
    'RuleEngine',
    'AnalysisReport'
]