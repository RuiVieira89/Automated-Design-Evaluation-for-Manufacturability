"""
Web UI surface for Layer 5 visualization.

Streamlit-based interface for interactive manufacturability analysis
with 3D visualization and results display.
"""

import streamlit as st
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
import tempfile
import os
from pathlib import Path
import pyvista as pv
from stpyvista import stpyvista

from rules.rule_engine import RuleEngine, AnalysisReport
from rules.base import Severity
from segmentation.inference.ml_inference_engine import MLInferenceEngine
from reporting.annotation_engine import AnnotationEngine, AnnotationConfig, ColorScheme

# Configure PyVista for Streamlit
pv.set_plot_theme("document")
pv.global_theme.background = 'white'


class WebUI:
    """Streamlit-based web interface for manufacturability analysis."""

    def __init__(self):
        self.annotation_engine = AnnotationEngine()
        self.rule_engine = RuleEngine()
        self.ml_engine = MLInferenceEngine()

    def _serialize_rule_results(self, rule_results: AnalysisReport) -> Dict[str, Any]:
        """Convert rule results to serializable dict."""
        return {
            'overall_status': rule_results.overall_status.value,
            'feasible': rule_results.feasible,
            'check_results': [
                {
                    'check_name': r.check_name,
                    'severity': r.severity.value,
                    'message': r.message,
                    'details': getattr(r, 'details', None),
                    'face_indices': getattr(r, 'face_indices', []),
                    'measurement_points': getattr(r, 'measurement_points', [])
                }
                for r in rule_results.check_results
            ]
        }

    def _serialize_ml_assessment(self, ml_assessment) -> Dict[str, Any]:
        """Convert ML assessment to serializable dict."""
        recommendations = ml_assessment.get_recommendations()
        return {
            'recommendations': recommendations,
            'ml_predictions': ml_assessment.ml_predictions,
            'process_capabilities': [
                cap.to_dict() for cap in ml_assessment.process_capabilities
            ]
        }

    def run(self):
        """Main Streamlit application."""
        st.set_page_config(
            page_title="CAD Manufacturability Analyzer",
            page_icon="🔧",
            layout="wide"
        )

        st.title("🔧 CAD Manufacturability Analyzer")
        st.markdown("Analyze 3D CAD models for manufacturing feasibility and get visual feedback.")

        # File upload section
        self._file_upload_section()

        # Analysis results section
        if 'analysis_results' in st.session_state:
            self._display_results()

    def _file_upload_section(self):
        """File upload interface."""
        st.header("📁 Upload CAD File")

        col1, col2 = st.columns([2, 1])

        with col1:
            uploaded_file = st.file_uploader(
                "Choose a CAD file",
                type=['step', 'stp', 'iges', 'igs', 'stl', 'obj'],
                help="Supported formats: STEP, IGES, STL, OBJ"
            )

        with col2:
            analysis_mode = st.selectbox(
                "Analysis Mode",
                ["Full Analysis (Rules + ML)", "Rules Only", "ML Only"],
                help="Choose which analysis layers to run"
            )

        if uploaded_file is not None:
            # Save uploaded file temporarily
            with tempfile.NamedTemporaryFile(delete=False, suffix=uploaded_file.name) as tmp_file:
                tmp_file.write(uploaded_file.getvalue())
                temp_path = tmp_file.name

            st.success(f"File uploaded: {uploaded_file.name}")

            # Analysis button
            if st.button("🔍 Analyze Manufacturability", type="primary"):
                with st.spinner("Analyzing... This may take a few moments."):
                    try:
                        results = self._run_analysis(temp_path, analysis_mode)
                        st.session_state.analysis_results = results
                        st.session_state.temp_file = temp_path
                        st.rerun()
                    except Exception as e:
                        st.error(f"Analysis failed: {str(e)}")
                        # Clean up temp file
                        os.unlink(temp_path)

    def _run_analysis(self, file_path: str, mode: str) -> Dict[str, Any]:
        """Run manufacturability analysis."""
        results = {
            'file_path': file_path,
            'mode': mode,
            'rule_results': None,
            'ml_assessment': None,
            'annotated_scene': None,
            'summary': {}
        }

        # Load geometry (simplified - would need actual CAD loading)
        # For now, create a dummy mesh
        mesh = self._load_geometry(file_path)

        # Run rule analysis
        rule_results = None
        if mode in ["Full Analysis (Rules + ML)", "Rules Only", "ML Only"]:
            rule_results = self.rule_engine.analyze(mesh)  # Would need geometry input
            if mode in ["Full Analysis (Rules + ML)", "Rules Only"]:
                results['rule_results'] = self._serialize_rule_results(rule_results)

        # Run ML analysis
        if mode in ["Full Analysis (Rules + ML)", "ML Only"]:
            ml_assessment = self.ml_engine.analyze(mesh, rule_results)  # Would need proper input
            results['ml_assessment'] = self._serialize_ml_assessment(ml_assessment)

        # Store raw objects for visualization
        results['_raw_rule_results'] = rule_results
        results['_raw_ml_assessment'] = ml_assessment if mode in ["Full Analysis (Rules + ML)", "ML Only"] else None

        # Create annotated visualization
        if results.get('_raw_rule_results') or results.get('_raw_ml_assessment'):
            plotter = self.annotation_engine.create_annotated_scene(
                mesh,
                results['_raw_rule_results'].check_results if results.get('_raw_rule_results') else [],
                results.get('_raw_ml_assessment')
            )
            results['annotated_scene'] = plotter

        # Generate summary
        results['summary'] = self._generate_summary(results)

        return results

    def _load_geometry(self, file_path: str) -> Any:
        """Load geometry from CAD file (simplified implementation)."""
        # This would need actual CAD file loading (OpenCASCADE, etc.)
        # For now, create a simple test geometry
        if file_path.endswith(('.stl', '.obj')):
            try:
                return pv.read(file_path)
            except:
                pass

        # Fallback: create a simple test cube
        cube = pv.Cube()
        return cube

    def _display_results(self):
        """Display analysis results."""
        results = st.session_state.analysis_results

        st.header("📊 Analysis Results")

        # Summary metrics
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            severity = results['summary'].get('overall_severity', 'Unknown')
            color = {'OK': 'green', 'WARNING': 'orange', 'ERROR': 'red', 'CRITICAL': 'darkred'}.get(severity, 'gray')
            st.metric("Overall Status", severity)

        with col2:
            n_violations = results['summary'].get('total_violations', 0)
            st.metric("Violations Found", n_violations)

        with col3:
            if results.get('ml_assessment'):
                confidence = results['ml_assessment'].get_recommendations().get('confidence', 0.0)
                st.metric("ML Confidence", ".2f")
            else:
                st.metric("ML Confidence", "N/A")

        with col4:
            feasible = results['summary'].get('feasible', False)
            st.metric("Manufacturable", "Yes" if feasible else "No")

        # 3D Visualization
        if results.get('annotated_scene'):
            st.header("🎨 3D Visualization")
            st.markdown("Interactive 3D view with violation highlighting:")

            # Display PyVista plotter
            stpyvista(results['annotated_scene'])

            # Export options
            col1, col2 = st.columns(2)
            with col1:
                if st.button("📷 Export Screenshot"):
                    screenshot_path = self._export_screenshot(results['annotated_scene'])
                    st.success(f"Screenshot saved: {screenshot_path}")

            with col2:
                if st.button("📄 Export VTK Scene"):
                    vtk_path = self._export_vtk(results['annotated_scene'])
                    st.success(f"VTK file saved: {vtk_path}")

        # Detailed Results
        self._display_detailed_results(results)

        # Process Recommendations
        if results.get('ml_assessment'):
            self._display_process_recommendations(results['_raw_ml_assessment'])

    def _display_detailed_results(self, results: Dict[str, Any]):
        """Display detailed rule violation results."""
        if not results.get('rule_results'):
            return

        st.header("🔍 Detailed Violations")

        violations = [r for r in results['rule_results'].check_results
                     if r.severity != 'OK']

        if not violations:
            st.success("No violations found!")
            return

        # Group by severity
        severity_groups = {}
        for violation in violations:
            severity = violation.severity.value
            if severity not in severity_groups:
                severity_groups[severity] = []
            severity_groups[severity].append(violation)

        for severity, checks in severity_groups.items():
            with st.expander(f"{severity} ({len(checks)} issues)", expanded=True):
                for check in checks:
                    st.write(f"**{check.check_name}**: {check.message}")
                    if hasattr(check, 'details') and check.details:
                        st.write(f"Details: {check.details}")

    def _display_process_recommendations(self, ml_assessment):
        """Display ML-based process recommendations."""
        st.header("🏭 Process Recommendations")

        recommendations = ml_assessment.get_recommendations()

        col1, col2 = st.columns([1, 2])

        with col1:
            st.subheader("Recommended Process")
            process = recommendations.get('recommended_process', 'Unknown')
            confidence = recommendations.get('confidence', 0.0)

            st.write(f"**{process.replace('_', ' ').title()}**")
            st.progress(confidence)
            st.write(f"Confidence: {confidence:.1%}")

        with col2:
            st.subheader("Alternative Processes")
            alternatives = recommendations.get('alternative_processes', [])

            for alt in alternatives[:3]:  # Show top 3
                with st.container():
                    st.write(f"**{alt['process'].replace('_', ' ').title()}**")
                    st.progress(alt['confidence'])
                    if alt.get('limitations'):
                        st.write(f"Limitations: {', '.join(alt['limitations'])}")

        # Limitations and requirements
        limitations = recommendations.get('limitations', [])
        requirements = recommendations.get('requirements', [])

        if limitations or requirements:
            st.subheader("Important Notes")
            if limitations:
                st.warning("**Limitations:** " + ", ".join(limitations))
            if requirements:
                st.info("**Requirements:** " + ", ".join(requirements))

    def _generate_summary(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate summary statistics from results."""
        summary = {
            'total_violations': 0,
            'overall_severity': 'OK',
            'feasible': True,
            'severity_breakdown': {}
        }

        if results.get('_raw_rule_results'):
            rule_results = results['_raw_rule_results']
            violations = [r for r in rule_results.check_results
                         if r.severity != Severity.PASS]

            summary['total_violations'] = len(violations)

            # Determine overall severity
            severity_levels = {Severity.PASS: 0, Severity.WARN: 1, Severity.FAIL: 2}
            max_severity = max([severity_levels.get(r.severity, 0) for r in violations], default=0)
            severity_names = {0: 'OK', 1: 'WARNING', 2: 'ERROR'}
            summary['overall_severity'] = severity_names[max_severity]

            # Feasibility check
            summary['feasible'] = rule_results.feasible

            # Severity breakdown
            for violation in violations:
                severity = violation.severity.value
                summary['severity_breakdown'][severity] = summary['severity_breakdown'].get(severity, 0) + 1

        return summary

    def _export_screenshot(self, plotter: Any) -> str:
        """Export screenshot of the 3D scene."""
        output_dir = Path("exports")
        output_dir.mkdir(exist_ok=True)

        timestamp = "analysis_result"
        output_path = output_dir / f"{timestamp}_screenshot.png"

        self.annotation_engine.export_scene(plotter, str(output_path.with_suffix('')), 'png')
        return str(output_path)

    def _export_vtk(self, plotter: Any) -> str:
        """Export VTK scene file."""
        output_dir = Path("exports")
        output_dir.mkdir(exist_ok=True)

        timestamp = "analysis_result"
        output_path = output_dir / f"{timestamp}_scene.vtk"

        self.annotation_engine.export_scene(plotter, str(output_path.with_suffix('')), 'vtk')
        return str(output_path)


def main():
    """Main entry point for Streamlit app."""
    ui = WebUI()
    ui.run()


if __name__ == "__main__":
    main()
