"""
Tolerance solver using scipy.optimize.

Converts violation data from DfX checks into constraint bounds
and solves for worst-case tolerance stack-up.
"""

from typing import Dict, Any, List, Tuple, Optional
import numpy as np
from scipy.optimize import minimize, LinearConstraint


class ToleranceSolver:
    """
    Solves tolerance stack-up and constraint feasibility.

    Uses violation data from checks as constraint inputs to optimization.
    """

    def __init__(self):
        """Initialize solver."""
        self.constraints: Dict[str, Tuple[float, float]] = {}
        self.check_results: List[Dict[str, Any]] = []

    def add_constraint(self, name: str, lower_bound: float, upper_bound: float) -> None:
        """
        Add a constraint bound.

        Args:
            name: Constraint identifier
            lower_bound: Minimum allowable value
            upper_bound: Maximum allowable value
        """
        self.constraints[name] = (lower_bound, upper_bound)

    def add_check_result(self, check_name: str, margin: float,
                        measured: float, threshold: float) -> None:
        """
        Add a check result as constraint data.

        Args:
            check_name: Name of the check
            margin: measured - threshold (the feasibility gap)
            measured: Actual measured value
            threshold: Required threshold
        """
        self.check_results.append({
            'check': check_name,
            'margin': margin,
            'measured': measured,
            'threshold': threshold
        })

    def solve_worst_case(self, nominal_dims: np.ndarray, tolerances: np.ndarray
                        ) -> Dict[str, Any]:
        """
        Solve worst-case tolerance stack.

        Args:
            nominal_dims: Nominal dimensions array
            tolerances: Tolerance (half-width) for each dimension

        Returns:
            Dictionary with solution details and feasibility verdict
        """
        def worst_case_gap(x):
            """Objective: maximize minimum margin (minimize negative)."""
            # x = dimension adjustments
            # For each constraint, compute new margin
            margins = []
            for result in self.check_results:
                # Simplified: margin changes with dimension adjustments
                scaled_margin = result['margin'] - np.linalg.norm(x) * 0.1
                margins.append(scaled_margin)

            if margins:
                return -min(margins)  # Minimize negative = maximize minimum
            return 0

        # Bounds for adjustments (can't exceed nominal ± tolerances)
        bounds = [(-t, t) for t in tolerances]

        # Initial guess: nominal
        x0 = np.zeros_like(nominal_dims)

        # Solve
        result = minimize(worst_case_gap, x0, method='L-BFGS-B', bounds=bounds)

        # Check feasibility
        worst_margin = -result.fun
        feasible = worst_margin >= 0

        return {
            'feasible': feasible,
            'worst_case_margin': float(worst_margin),
            'adjusted_dimensions': result.x.tolist(),
            'optimization_success': result.success,
            'message': result.message
        }

    def check_feasibility(self) -> Dict[str, Any]:
        """
        Check if all constraints are simultaneously feasible.

        Returns:
            Dictionary with feasibility analysis
        """
        if not self.check_results:
            return {
                'feasible': True,
                'message': 'No constraints to check'
            }

        margins = [r['margin'] for r in self.check_results]
        worst_margin = min(margins) if margins else 0

        # A design is feasible if worst-case margin >= 0
        feasible = worst_margin >= 0

        return {
            'feasible': feasible,
            'worst_case_margin': float(worst_margin),
            'constraint_count': len(self.check_results),
            'critical_check': next(
                (r['check'] for r in self.check_results if r['margin'] == worst_margin),
                None
            ),
            'details': self.check_results
        }

    def get_constraint_summary(self) -> str:
        """Get text summary of constraints."""
        lines = ["Constraint Summary:"]
        lines.append(f"  Total constraints: {len(self.check_results)}")
        lines.append("")

        for result in self.check_results:
            margin = result['margin']
            status = "✓ PASS" if margin >= 0 else "✗ FAIL"
            lines.append(
                f"  {result['check']}: {status} "
                f"(margin: {margin:+.2f}mm)"
            )

        return "\n".join(lines)