"""
Layer 5 — Visualization & Feedback

Core annotation engine using PyVista/VTK for 3D manufacturability visualization.
Creates annotated scenes that can be rendered across different surfaces.
"""

import numpy as np
from typing import Dict, List, Any, Optional, Tuple
import logging
from dataclasses import dataclass
from enum import Enum

try:
    import pyvista as pv
except ImportError:
    pv = None
    logging.warning("pyvista is not installed; reporting annotation engine will be limited")

from rules.rule_engine import CheckResult, Severity, AnalysisReport
from segmentation.inference.process_classifier import ManufacturabilityAssessment

logger = logging.getLogger(__name__)


class ColorScheme(Enum):
    """Color schemes for violation severity."""
    RED_GREEN = "red_green"  # Red for violations, green for OK
    SEVERITY_GRADIENT = "severity_gradient"  # Gradient from green to red
    BLUE_RED = "blue_red"  # Blue for OK, red for violations


@dataclass
class AnnotationConfig:
    """Configuration for 3D annotations."""
    color_scheme: ColorScheme = ColorScheme.SEVERITY_GRADIENT
    show_measurements: bool = True
    show_labels: bool = True
    show_arrows: bool = True
    arrow_scale: float = 1.0
    label_font_size: int = 12
    opacity: float = 0.8


class AnnotationEngine:
    """
    Core annotation engine using PyVista/VTK.

    Creates annotated 3D scenes from Layer 3/4 outputs that can be rendered
    across different surfaces (FreeCAD, Web UI, Headless).
    """

    def __init__(self, config: AnnotationConfig = None):
        self.config = config or AnnotationConfig()
        self._setup_color_maps()

    def _setup_color_maps(self):
        """Setup color maps for different severity levels."""
        # Severity color mapping (PASS=OK, WARN=WARNING, FAIL=ERROR)
        self.severity_colors = {
            Severity.PASS: [0.2, 0.8, 0.2],      # Green
            Severity.WARN: [1.0, 0.8, 0.2],      # Orange
            Severity.FAIL: [1.0, 0.4, 0.4],      # Red
        }

        # Create gradient colormap for severity
        self.severity_cmap = 'plasma'  # Use plasma colormap for severity gradient

    def create_annotated_scene(self,
                              mesh: Any,
                              rule_results: List[CheckResult],
                              ml_assessment: Optional[ManufacturabilityAssessment] = None,
                              off_screen: bool = True) -> Any:
        """
        Create an annotated 3D scene from analysis results.

        Args:
            mesh: Input 3D mesh (PyVista PolyData)
            rule_results: Results from Layer 3 rule engine
            ml_assessment: Optional results from Layer 4 ML engine
            off_screen: If True, render off-screen (for export); False for interactive

        Returns:
            PyVista plotter with annotated scene
        """
        # Create plotter
        if pv is None:
            raise ImportError("pyvista is required for create_annotated_scene")

        plotter = pv.Plotter(off_screen=off_screen)

        # Apply violation coloring
        colored_mesh = self._apply_violation_coloring(mesh, rule_results)
        if colored_mesh is not None:
            plotter.add_mesh(colored_mesh, scalars='severity', cmap='RdYlGn_r',
                           clim=[0.0, 1.0], opacity=self.config.opacity,
                           show_edges=True, show_scalar_bar=True,
                           scalar_bar_args={
                               'title': 'Severity',
                               'label_font_size': 12,
                               'title_font_size': 14,
                               'n_labels': 3,
                               'fmt': '%.1f',
                           })
        else:
            # No violations — render mesh in a neutral colour
            plotter.add_mesh(mesh, color='lightblue', opacity=self.config.opacity,
                           show_edges=True)

        # Add measurement overlays
        if self.config.show_measurements:
            self._add_measurement_overlays(plotter, rule_results)

        # Build summary title
        n_fail = sum(1 for r in rule_results if r.severity == Severity.FAIL)
        n_warn = sum(1 for r in rule_results if r.severity == Severity.WARN)
        status = "FAIL" if n_fail else ("WARN" if n_warn else "PASS")
        title_text = f"Manufacturability Analysis — {status}  |  Fail: {n_fail}  Warn: {n_warn}"
        title_color = 'red' if n_fail else ('orange' if n_warn else 'green')
        plotter.add_text(title_text, position='upper_edge', font_size=11,
                        color=title_color, font='arial')

        # Add process recommendations overlay
        if ml_assessment and self.config.show_labels:
            self._add_process_overlay(plotter, ml_assessment)

        plotter.view_isometric()
        plotter.reset_camera()

        return plotter

    def _apply_violation_coloring(self, mesh: Any,
                                 rule_results: List[CheckResult]) -> Optional[Any]:
        """
        Apply per-face coloring based on violation severity.

        Returns colored mesh, or None if nothing to show.
        """
        if pv is None:
            return None

        colored_mesh = mesh.copy()
        # Default: all faces are PASS (0.0 on a 0–1 scale)
        severity_scalars = np.zeros(mesh.n_faces_strict)

        # Mark faces declared by each check result
        for result in rule_results:
            face_indices = getattr(result, 'face_indices', [])
            scalar_value = self._severity_to_scalar(result.severity)
            if face_indices:
                for idx in face_indices:
                    if 0 <= idx < len(severity_scalars):
                        # Take the maximum (worst) severity on a face
                        severity_scalars[idx] = max(severity_scalars[idx], scalar_value)
            else:
                # Check has no specific face list — colour uniformly if not PASS
                if result.severity != Severity.PASS:
                    severity_scalars[:] = np.maximum(severity_scalars, scalar_value)

        colored_mesh['severity'] = severity_scalars
        return colored_mesh

    def _severity_to_scalar(self, severity: Severity) -> float:
        """Convert severity enum to scalar value for colormap."""
        mapping = {
            Severity.PASS: 0.0,
            Severity.WARN: 0.25,
            Severity.FAIL: 1.0
        }
        return mapping.get(severity, 0.0)

    def _add_measurement_overlays(self, plotter: Any,
                                 rule_results: List[CheckResult]):
        """Add measurement arrows, labels, and dimensions."""
        for result in rule_results:
            if result.severity == Severity.PASS:
                continue

            # Add arrows for measurements (simplified)
            if hasattr(result, 'measurement_points') and self.config.show_arrows:
                points = getattr(result, 'measurement_points', [])
                if len(points) >= 2:
                    start, end = points[0], points[1]
                    arrow = pv.Arrow(start=start, direction=np.array(end)-np.array(start),
                                    scale=self.config.arrow_scale)
                    plotter.add_mesh(arrow, color='blue')

            # Add text labels
            if hasattr(result, 'position') and self.config.show_labels:
                position = getattr(result, 'position', [0, 0, 0])
                label_text = f"{result.check_name}: {result.message}"
                plotter.add_point_labels([position], [label_text],
                                       font_size=self.config.label_font_size,
                                       point_color='red', text_color='black')

    def _add_process_overlay(self, plotter: Any,
                           ml_assessment: ManufacturabilityAssessment):
        """Add process recommendation overlay."""
        recommendations = ml_assessment.get_recommendations()

        # Add text overlay with process recommendation
        process_text = f"Recommended: {recommendations.get('recommended_process', 'Unknown')}"
        confidence = recommendations.get('confidence', 0.0)
        confidence_text = f"Confidence: {confidence:.2f}"

        # Position text in top-left corner
        plotter.add_text(process_text, position='upper_left', font_size=14, color='black')
        plotter.add_text(confidence_text, position=(0.01, 0.08), font_size=12, color='black',
                        viewport=True)

    def export_scene(self, plotter: Any, output_path: str,
                    format: str = 'png') -> str:
        """
        Export annotated scene to various formats.

        Args:
            plotter: PyVista plotter with scene
            output_path: Output file path (without extension)
            format: Export format ('png', 'svg', 'vtk', 'gltf')

        Returns:
            Path to exported file
        """
        if format == 'png':
            full_path = f"{output_path}.png"
            plotter.screenshot(full_path)
        elif format == 'vtk':
            full_path = f"{output_path}.vtk"
            # Save the mesh data, not graphics
            if hasattr(plotter, 'meshes') and plotter.meshes:
                # Save the first mesh (assuming it's the main one)
                plotter.meshes[0].save(full_path)
            else:
                logger.warning("No meshes to export to VTK")
                full_path = f"{output_path}.png"  # Fallback to screenshot
                plotter.screenshot(full_path)
        elif format == 'html':
            full_path = f"{output_path}.html"
            plotter.export_html(full_path)
        elif format == 'gltf':
            full_path = f"{output_path}.gltf"
            # Note: PyVista doesn't directly support glTF export
            # Would need additional libraries or conversion
            logger.warning("glTF export not implemented - using VTK format")
            full_path = f"{output_path}.vtk"
            plotter.save_graphic(full_path)
        else:
            raise ValueError(f"Unsupported export format: {format}")

        logger.info(f"Exported scene to {full_path}")
        return full_path

    def get_scene_summary(self, plotter: Any) -> Dict[str, Any]:
        """Get summary information about the annotated scene."""
        return {
            'n_meshes': len(plotter.renderer._actors),
            'camera_position': plotter.camera_position,
            'bounds': plotter.bounds
        }
