"""
Parameter store - single source of truth for manufacturing constraints.

Manages thresholds, tolerances, and process parameters that drive DfX checks.
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict


@dataclass
class ProcessParams:
    """Manufacturing process parameters."""
    # Wall thickness
    min_wall_thickness: float = 2.0  # mm

    # Draft angles
    min_draft_angle: float = 1.0  # degrees
    pull_direction: tuple = (0, 0, 1)  # default: Z-axis

    # Holes
    min_hole_diameter: float = 1.0  # mm
    max_hole_depth_ratio: float = 10.0  # depth/diameter

    # Undercuts
    max_undercut_depth: float = 5.0  # mm

    # Tool access
    tool_cone_angle: float = 15.0  # degrees
    min_tool_clearance: float = 2.0  # mm


class ParamStore:
    """
    Single source of truth for manufacturing parameters.

    Allows swapping process profiles (injection moulding, CNC, casting, etc.)
    without changing check code.
    """

    def __init__(self):
        """Initialize with default parameter sets."""
        self.processes: Dict[str, ProcessParams] = {
            'injection_moulding': ProcessParams(
                min_wall_thickness=2.0,
                min_draft_angle=1.0,
                min_hole_diameter=1.0,
                max_hole_depth_ratio=10.0,
                max_undercut_depth=2.0,
            ),
            'cnc_3axis': ProcessParams(
                min_wall_thickness=1.0,
                min_draft_angle=0.0,  # No draft needed
                min_hole_diameter=0.5,
                max_hole_depth_ratio=20.0,
                max_undercut_depth=0.0,  # No undercuts
            ),
            'casting': ProcessParams(
                min_wall_thickness=3.0,
                min_draft_angle=2.0,
                min_hole_diameter=2.0,
                max_hole_depth_ratio=5.0,
                max_undercut_depth=5.0,
            ),
        }
        self.current_process = 'injection_moulding'

    def select_process(self, process_name: str) -> None:
        """
        Select manufacturing process.

        Args:
            process_name: Key in processes dict

        Raises:
            ValueError: If process not found
        """
        if process_name not in self.processes:
            raise ValueError(f"Unknown process: {process_name}")
        self.current_process = process_name

    def get_params(self, process_name: Optional[str] = None) -> ProcessParams:
        """
        Get parameters for a process.

        Args:
            process_name: Process to query. If None, uses current process.

        Returns:
            ProcessParams for the specified process
        """
        if process_name is None:
            process_name = self.current_process
        return self.processes[process_name]

    def get_param(self, key: str, process_name: Optional[str] = None) -> Any:
        """
        Get a single parameter value.

        Args:
            key: Parameter field name (e.g., 'min_wall_thickness')
            process_name: Process to query. If None, uses current process.

        Returns:
            Parameter value

        Raises:
            AttributeError: If parameter not found
        """
        params = self.get_params(process_name)
        if not hasattr(params, key):
            raise AttributeError(f"Unknown parameter: {key}")
        return getattr(params, key)

    def set_param(self, key: str, value: Any, process_name: Optional[str] = None) -> None:
        """
        Set a single parameter value.

        Args:
            key: Parameter field name
            value: New value
            process_name: Process to update. If None, uses current process.

        Raises:
            AttributeError: If parameter not found
        """
        process_name = process_name or self.current_process
        params = self.processes[process_name]
        if not hasattr(params, key):
            raise AttributeError(f"Unknown parameter: {key}")
        setattr(params, key, value)

    def to_dict(self, process_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Convert parameters to dictionary.

        Args:
            process_name: Process to query. If None, uses current process.

        Returns:
            Dictionary of parameters
        """
        params = self.get_params(process_name)
        return asdict(params)