"""
FreeCAD plugin surface for Layer 5 visualization.

In-process Python plugin that integrates with FreeCAD's workbench system
and 3D viewport for real-time manufacturability feedback.
"""

import FreeCAD
import FreeCADGui
from PySide import QtCore, QtGui
import pyvista as pv
import numpy as np
from typing import Dict, List, Any, Optional
import tempfile
import os

from rules.rule_engine import RuleEngine, AnalysisReport
from segmentation.inference.ml_inference_engine import MLInferenceEngine
from .annotation_engine import AnnotationEngine, AnnotationConfig

try:
    from pivy import coin
    COIN_AVAILABLE = True
except ImportError:
    COIN_AVAILABLE = False


class ManufacturabilityWorkbench(FreeCADGui.Workbench):
    """FreeCAD workbench for manufacturability analysis."""

    MenuText = "Manufacturability"
    ToolTip = "Analyze parts for manufacturing feasibility"
    Icon = ""  # Would need icon file

    def Initialize(self):
        """Initialize the workbench."""
        # Add commands to toolbar
        self.appendToolbar("Manufacturability", [
            "Manufacturability_Analyze",
            "Manufacturability_ShowViolations",
            "Manufacturability_ProcessRecommendation"
        ])

        # Add menu
        self.appendMenu("Manufacturability", [
            "Manufacturability_Analyze",
            "Manufacturability_ShowViolations",
            "Manufacturability_ProcessRecommendation",
            "Separator",
            "Manufacturability_Settings"
        ])

    def GetClassName(self):
        return "Gui::PythonWorkbench"


class AnalyzeCommand:
    """Command to run manufacturability analysis."""

    def GetResources(self):
        return {
            'Pixmap': '',  # Icon path
            'MenuText': 'Analyze Manufacturability',
            'ToolTip': 'Run manufacturability analysis on selected object'
        }

    def Activated(self):
        """Run when command is activated."""
        analyzer = FreeCADAnalyzer()
        analyzer.run_analysis()

    def IsActive(self):
        """Check if command should be active."""
        return FreeCADGui.ActiveDocument is not None


class ShowViolationsCommand:
    """Command to show/hide violation visualization."""

    def GetResources(self):
        return {
            'Pixmap': '',
            'MenuText': 'Show Violations',
            'ToolTip': 'Toggle violation visualization overlay'
        }

    def Activated(self):
        analyzer = FreeCADAnalyzer()
        analyzer.toggle_violations()

    def IsActive(self):
        return FreeCADGui.ActiveDocument is not None


class ProcessRecommendationCommand:
    """Command to show process recommendations."""

    def GetResources(self):
        return {
            'Pixmap': '',
            'MenuText': 'Process Recommendations',
            'ToolTip': 'Show manufacturing process recommendations'
        }

    def Activated(self):
        analyzer = FreeCADAnalyzer()
        analyzer.show_recommendations()

    def IsActive(self):
        return FreeCADGui.ActiveDocument is not None


class FreeCADAnalyzer:
    """FreeCAD-specific analyzer integration."""

    def __init__(self):
        self.annotation_engine = AnnotationEngine()
        self.rule_engine = RuleEngine()
        self.ml_engine = MLInferenceEngine()
        self.current_results = None
        self.overlay_visible = False

    def run_analysis(self):
        """Run manufacturability analysis on selected object."""
        try:
            # Get selected object
            selection = FreeCADGui.Selection.getSelection()
            if not selection:
                FreeCAD.Console.PrintError("No object selected for analysis\n")
                return

            obj = selection[0]

            # Convert FreeCAD object to PyVista mesh
            mesh = self._freecad_to_pyvista(obj)

            # Run analysis
            FreeCAD.Console.PrintMessage("Running manufacturability analysis...\n")

            # Rule analysis
            rule_results = self.rule_engine.analyze(mesh)
            FreeCAD.Console.PrintMessage(f"Rule analysis complete: {len(rule_results.check_results)} checks\n")

            # ML analysis
            ml_assessment = self.ml_engine.analyze(mesh, rule_results)
            recommendations = ml_assessment.get_recommendations()
            FreeCAD.Console.PrintMessage(f"ML analysis complete: {recommendations.get('recommended_process', 'Unknown')}\n")

            # Store results
            self.current_results = {
                'rule_results': rule_results,
                'ml_assessment': ml_assessment,
                'mesh': mesh
            }

            # Show results panel
            self._show_results_panel()

            # Update overlay
            self._update_overlay()

        except Exception as e:
            FreeCAD.Console.PrintError(f"Analysis failed: {str(e)}\n")

    def toggle_violations(self):
        """Toggle violation visualization overlay."""
        if not self.current_results:
            FreeCAD.Console.PrintError("No analysis results available. Run analysis first.\n")
            return

        self.overlay_visible = not self.overlay_visible
        self._update_overlay()

    def show_recommendations(self):
        """Show process recommendations dialog."""
        if not self.current_results:
            FreeCAD.Console.PrintError("No analysis results available. Run analysis first.\n")
            return

        recommendations = self.current_results['ml_assessment'].get_recommendations()

        # Create dialog
        dialog = QtGui.QDialog(FreeCADGui.getMainWindow())
        dialog.setWindowTitle("Manufacturing Process Recommendations")

        layout = QtGui.QVBoxLayout()

        # Recommended process
        process_label = QtGui.QLabel(f"Recommended Process: {recommendations.get('recommended_process', 'Unknown')}")
        layout.addWidget(process_label)

        # Confidence
        confidence = recommendations.get('confidence', 0.0)
        confidence_label = QtGui.QLabel(f"Confidence: {confidence:.2f}")
        layout.addWidget(confidence_label)

        # Alternatives
        alternatives = recommendations.get('alternative_processes', [])
        if alternatives:
            alt_label = QtGui.QLabel("Alternatives:")
            layout.addWidget(alt_label)

            for alt in alternatives[:3]:
                alt_text = f"{alt['process']}: {alt['confidence']:.2f}"
                layout.addWidget(QtGui.QLabel(alt_text))

        # Close button
        close_button = QtGui.QPushButton("Close")
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button)

        dialog.setLayout(layout)
        dialog.exec_()

    def _freecad_to_pyvista(self, obj) -> Any:
        """Convert FreeCAD object to PyVista mesh."""
        try:
            # Get mesh from FreeCAD object
            if hasattr(obj, 'Mesh'):
                mesh = obj.Mesh
            elif hasattr(obj, 'Shape'):
                # Convert shape to mesh
                import Mesh
                mesh = Mesh.Mesh(obj.Shape.tessellate(0.1))  # 0.1mm tolerance
            else:
                raise ValueError("Object has no mesh or shape")

            # Convert to PyVista
            vertices = np.array([[v.x, v.y, v.z] for v in mesh.Points])
            faces = []

            for f in mesh.Facets:
                if len(f.PointIndices) == 3:
                    faces.extend([3] + f.PointIndices)
                elif len(f.PointIndices) == 4:
                    # Triangulate quad
                    faces.extend([3] + f.PointIndices[:3])
                    faces.extend([3] + [f.PointIndices[0], f.PointIndices[2], f.PointIndices[3]])

            return pv.PolyData(vertices, faces)

        except Exception as e:
            FreeCAD.Console.PrintWarning(f"Mesh conversion failed, using fallback: {e}\n")
            # Fallback: simple cube
            return pv.Cube()

    def _update_overlay(self):
        """Update the 3D overlay in FreeCAD viewport."""
        if not COIN_AVAILABLE:
            FreeCAD.Console.PrintWarning("Coin3D not available - overlay disabled\n")
            return

        try:
            # Get FreeCAD's scene graph
            sg = FreeCADGui.ActiveDocument.ActiveView.getSceneGraph()

            # Remove existing overlay
            self._remove_overlay(sg)

            if self.overlay_visible and self.current_results:
                # Create new overlay
                overlay_node = self._create_overlay_node()
                if overlay_node:
                    sg.addChild(overlay_node)

        except Exception as e:
            FreeCAD.Console.PrintError(f"Overlay update failed: {e}\n")

    def _create_overlay_node(self):
        """Create Coin3D scene graph node for overlay."""
        if not self.current_results:
            return None

        try:
            # Create annotated scene
            mesh = self.current_results['mesh']
            rule_results = self.current_results['rule_results'].check_results
            ml_assessment = self.current_results['ml_assessment']

            plotter = self.annotation_engine.create_annotated_scene(
                mesh, rule_results, ml_assessment
            )

            # Convert PyVista scene to Coin3D (simplified)
            # This would need proper PyVista -> Coin3D conversion
            # For now, just create a placeholder
            root = coin.SoSeparator()

            # Add coordinate system
            coords = coin.SoCoordinate3()
            coords.point.setValues(0, 8, [[-1, -1, -1], [1, -1, -1], [-1, 1, -1], [1, 1, -1],
                                         [-1, -1, 1], [1, -1, 1], [-1, 1, 1], [1, 1, 1]])
            root.addChild(coords)

            return root

        except Exception as e:
            FreeCAD.Console.PrintError(f"Overlay creation failed: {e}\n")
            return None

    def _remove_overlay(self, scene_graph):
        """Remove existing overlay from scene graph."""
        # Find and remove overlay nodes
        # This is a simplified implementation
        pass

    def _show_results_panel(self):
        """Show results in FreeCAD's report view."""
        if not self.current_results:
            return

        rule_results = self.current_results['rule_results']
        ml_assessment = self.current_results['ml_assessment']

        # Clear report view
        FreeCADGui.getMainWindow().findChild(QtGui.QTextEdit, "Report view").clear()

        # Add results
        FreeCAD.Console.PrintMessage("=== MANUFACTURABILITY ANALYSIS RESULTS ===\n\n")

        # Rule results summary
        violations = [r for r in rule_results.check_results if r.severity.value != 'OK']
        FreeCAD.Console.PrintMessage(f"Rule Analysis: {len(violations)} violations found\n")
        FreeCAD.Console.PrintMessage(f"Overall Status: {rule_results.overall_status.value}\n")
        FreeCAD.Console.PrintMessage(f"Feasible: {'Yes' if rule_results.feasible else 'No'}\n\n")

        # ML results
        recommendations = ml_assessment.get_recommendations()
        FreeCAD.Console.PrintMessage(f"Recommended Process: {recommendations.get('recommended_process', 'Unknown')}\n")
        confidence = recommendations.get('confidence', 0.0)
        FreeCAD.Console.PrintMessage(f"Confidence: {confidence:.2f}\n\n")

        # Detailed violations
        if violations:
            FreeCAD.Console.PrintMessage("DETAILED VIOLATIONS:\n")
            for violation in violations:
                FreeCAD.Console.PrintMessage(f"- {violation.check_name}: {violation.message}\n")


# Register workbench and commands
FreeCADGui.addWorkbench(ManufacturabilityWorkbench())

# Register commands
FreeCADGui.addCommand('Manufacturability_Analyze', AnalyzeCommand())
FreeCADGui.addCommand('Manufacturability_ShowViolations', ShowViolationsCommand())
FreeCADGui.addCommand('Manufacturability_ProcessRecommendation', ProcessRecommendationCommand())


def initialize_plugin():
    """Initialize the FreeCAD plugin."""
    FreeCAD.Console.PrintMessage("Manufacturability Analysis plugin loaded\n")


# Initialize when module is imported
initialize_plugin()
