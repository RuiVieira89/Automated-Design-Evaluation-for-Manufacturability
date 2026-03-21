"""
Example usage of Layer 5 — Visualization & Feedback

This script demonstrates how to use the reporting layer to visualize
manufacturability analysis results from Layers 3 and 4.
"""

import numpy as np
import pyvista as pv
from pathlib import Path

from rules.rule_engine import RuleEngine
from segmentation.inference.ml_inference_engine import MLInferenceEngine
from reporting.annotation_engine import AnnotationEngine, AnnotationConfig, ColorScheme


def create_sample_geometry() -> pv.PolyData:
    """Create a sample geometry for demonstration."""
    # Create a simple part with some features that might have manufacturability issues
    # This would normally come from CAD file loading

    # Create a base cube
    cube = pv.Cube(x_length=10, y_length=10, z_length=5)

    # Add some features that might cause issues
    # Thin wall section
    thin_wall = pv.Cube(center=[0, 0, 3], x_length=8, y_length=0.5, z_length=2)

    # Combine geometries
    part = cube + thin_wall

    return part


def run_analysis_demo():
    """Demonstrate the full analysis and visualization pipeline."""
    print("🔧 CAD Manufacturability Analyzer - Layer 5 Demo")
    print("=" * 50)

    # Create sample geometry
    print("📐 Creating sample geometry...")
    mesh = create_sample_geometry()
    print(f"   Mesh: {mesh.n_points} points, {mesh.n_faces} faces")

    # Initialize analyzers
    print("🔍 Initializing analyzers...")
    rule_engine = RuleEngine()
    ml_engine = MLInferenceEngine()
    annotation_engine = AnnotationEngine()

    # Run Layer 3: Rule-based analysis
    print("📏 Running rule-based analysis (Layer 3)...")
    rule_results = rule_engine.analyze(mesh)
    print(f"   Found {len(rule_results.check_results)} check results")
    print(f"   Overall status: {rule_results.overall_status.value}")
    print(f"   Feasible: {rule_results.feasible}")

    # Run Layer 4: ML-based analysis
    print("🤖 Running ML-based analysis (Layer 4)...")
    ml_assessment = ml_engine.analyze(mesh)
    recommendations = ml_assessment.get_recommendations()
    print(f"   Recommended process: {recommendations.get('recommended_process', 'Unknown')}")
    print(f"   Confidence: {recommendations.get('confidence', 0.0):.2f}")

    # Create Layer 5: Visualization
    print("🎨 Creating 3D visualization (Layer 5)...")

    # Configure annotation
    config = AnnotationConfig(
        color_scheme=ColorScheme.SEVERITY_GRADIENT,
        show_measurements=True,
        show_labels=True,
        show_arrows=True
    )

    # Create annotated scene
    plotter = annotation_engine.create_annotated_scene(
        mesh,
        rule_results.check_results,
        ml_assessment
    )

    # Export visualizations
    print("💾 Exporting visualizations...")
    export_dir = Path("demo_exports")
    export_dir.mkdir(exist_ok=True)

    # Screenshot
    screenshot_path = annotation_engine.export_scene(
        plotter, str(export_dir / "demo_screenshot"), 'png'
    )
    print(f"   Screenshot saved: {screenshot_path}")

    # VTK scene
    vtk_path = annotation_engine.export_scene(
        plotter, str(export_dir / "demo_scene"), 'vtk'
    )
    print(f"   VTK scene saved: {vtk_path}")

    # Show interactive plot if running interactively
    try:
        import matplotlib
        matplotlib.use('TkAgg')  # Use Tkinter backend
        print("🖼️  Displaying interactive 3D view...")
        plotter.show()
    except ImportError:
        print("⚠️  Matplotlib not available for interactive display")
    except Exception as e:
        print(f"⚠️  Could not display interactive view: {e}")

    print("\n✅ Analysis complete!")
    print(f"📁 Results saved to: {export_dir.absolute()}")

    return {
        'mesh': mesh,
        'rule_results': rule_results,
        'ml_assessment': ml_assessment,
        'plotter': plotter,
        'exports': {
            'screenshot': screenshot_path,
            'vtk': vtk_path
        }
    }


def web_ui_demo():
    """Demonstrate the web UI surface."""
    print("\n🌐 Web UI Demo")
    print("-" * 20)
    print("To run the web UI:")
    print("  streamlit run reporting/web_ui.py")
    print("Then open http://localhost:8501 in your browser")


def api_demo():
    """Demonstrate the headless API surface."""
    print("\n🔌 API Demo")
    print("-" * 20)
    print("To run the REST API:")
    print("  python reporting/headless_api.py")
    print("Then visit http://localhost:8000/docs for API documentation")
    print("\nExample API call:")
    print("  curl -X POST 'http://localhost:8000/analyze' \\")
    print("       -F 'file=@sample_part.step' \\")
    print("       -F 'analysis_mode=full' \\")
    print("       -F 'include_visualization=true'")


def freecad_demo():
    """Demonstrate the FreeCAD plugin surface."""
    print("\n🔧 FreeCAD Plugin Demo")
    print("-" * 20)
    print("To use the FreeCAD plugin:")
    print("1. Copy reporting/freecad_plugin.py to FreeCAD's Mod directory")
    print("2. Restart FreeCAD")
    print("3. Select 'Manufacturability' workbench")
    print("4. Use the toolbar buttons to analyze parts")


if __name__ == "__main__":
    # Run the main demo
    results = run_analysis_demo()

    # Show other surface demos
    web_ui_demo()
    api_demo()
    freecad_demo()

    print("\n🎉 All demos completed!")
