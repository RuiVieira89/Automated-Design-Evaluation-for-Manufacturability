"""
Tests for Layer 5 — Visualization & Feedback

Tests the annotation engine and visualization components.
"""

import pytest
import numpy as np
from pathlib import Path
import tempfile

try:
    import pyvista as pv
except ImportError:
    pv = None

from reporting.annotation_engine import AnnotationEngine, AnnotationConfig, ColorScheme
from rules.rule_engine import CheckResult, Severity


class TestAnnotationEngine:
    """Test the core annotation engine."""

    def setup_method(self):
        """Setup test fixtures."""
        self.engine = AnnotationEngine()
        if pv is not None:
            self.sample_mesh = pv.Cube()  # Simple test mesh
        else:
            self.sample_mesh = None

    def _log(self, message: str):
        print(f"[ReportingTest] {message}")

    def test_initialization(self):
        """Test annotation engine initialization."""
        self._log("test_initialization: checking config and color maps")
        assert self.engine.config is not None
        assert len(self.engine.severity_colors) == 3
        assert isinstance(self.engine.severity_cmap, str)
        self._log("test_initialization: passed")

    def test_create_annotated_scene(self):
        """Test creating an annotated scene."""
        if pv is None:
            pytest.skip("pyvista not installed; cannot create annotated scene")

        self._log("test_create_annotated_scene: starting")

        rule_results = [
            CheckResult(
                check_name="Wall Thickness",
                severity=Severity.FAIL,
                message="Wall too thin"
            )
        ]

        plotter = self.engine.create_annotated_scene(self.sample_mesh, rule_results)

        assert plotter is not None
        assert isinstance(plotter, pv.Plotter)

        self._log("test_create_annotated_scene: passed")

    def test_violation_coloring(self):
        """Test violation coloring functionality."""
        if pv is None:
            pytest.skip("pyvista not installed; skipping violation coloring check")

        rule_results = [
            CheckResult(
                check_name="Test Check",
                severity=Severity.FAIL,
                message="Test violation"
            )
        ]

        colored_mesh = self.engine._apply_violation_coloring(self.sample_mesh, rule_results)

        # Should return colored mesh when violations exist
        assert colored_mesh is not None
        assert 'severity' in colored_mesh.array_names

    def test_no_violations_coloring(self):
        """Test coloring when no violations exist."""
        if pv is None:
            pytest.skip("pyvista not installed; skipping no-violations coloring check")

        rule_results = [
            CheckResult(
                check_name="Test Check",
                severity=Severity.PASS,
                message="All good"
            )
        ]

        colored_mesh = self.engine._apply_violation_coloring(self.sample_mesh, rule_results)

        # Should return None when no violations
        assert colored_mesh is None

    def test_export_formats(self):
        """Test different export formats."""
        if pv is None:
            pytest.skip("pyvista not installed; cannot test export formats")

        plotter = self.engine.create_annotated_scene(self.sample_mesh, [])

        with tempfile.TemporaryDirectory() as tmp_dir:
            # Test PNG export
            png_path = self.engine.export_scene(plotter, f"{tmp_dir}/test", 'png')
            assert Path(png_path).exists()

            # Test VTK export
            vtk_path = self.engine.export_scene(plotter, f"{tmp_dir}/test", 'vtk')
            assert Path(vtk_path).exists()

    def test_invalid_export_format(self):
        """Test invalid export format handling."""
        if pv is None:
            pytest.skip("pyvista not installed; cannot test export formats")

        plotter = self.engine.create_annotated_scene(self.sample_mesh, [])

        with pytest.raises(ValueError):
            self.engine.export_scene(plotter, "test", 'invalid')

    def test_config_options(self):
        """Test different configuration options."""
        config = AnnotationConfig(
            color_scheme=ColorScheme.BLUE_RED,
            show_measurements=False,
            show_labels=False,
            opacity=0.5
        )

        engine = AnnotationEngine(config)
        assert engine.config.opacity == 0.5
        assert not engine.config.show_measurements


class TestAnnotationConfig:
    """Test annotation configuration."""

    def test_default_config(self):
        """Test default configuration."""
        config = AnnotationConfig()
        assert config.color_scheme == ColorScheme.SEVERITY_GRADIENT
        assert config.show_measurements
        assert config.show_labels
        assert config.opacity == 0.8

    def test_custom_config(self):
        """Test custom configuration."""
        config = AnnotationConfig(
            color_scheme=ColorScheme.RED_GREEN,
            show_arrows=False,
            label_font_size=14
        )
        assert config.color_scheme == ColorScheme.RED_GREEN
        assert not config.show_arrows
        assert config.label_font_size == 14


class TestColorSchemes:
    """Test color scheme enum."""

    def test_color_scheme_values(self):
        """Test color scheme enum values."""
        assert ColorScheme.RED_GREEN.value == "red_green"
        assert ColorScheme.SEVERITY_GRADIENT.value == "severity_gradient"
        assert ColorScheme.BLUE_RED.value == "blue_red"

    def test_all_schemes_available(self):
        """Test all color schemes are defined."""
        schemes = [ColorScheme.RED_GREEN, ColorScheme.SEVERITY_GRADIENT, ColorScheme.BLUE_RED]
        assert len(schemes) == 3


# Integration test
def test_full_pipeline():
    """Test the full annotation pipeline."""
    if pv is None:
        pytest.skip("pyvista not installed; cannot run full pipeline")

    print("[ReportingTest] test_full_pipeline: running end-to-end scenario")

    engine = AnnotationEngine()
    mesh = pv.Cube()

    rule_results = [
        CheckResult(
            check_name="Draft Angle",
            severity=Severity.WARN,
            message="Insufficient draft"
        ),
        CheckResult(
            check_name="Wall Thickness",
            severity=Severity.FAIL,
            message="Wall too thin"
        )
    ]

    plotter = engine.create_annotated_scene(mesh, rule_results)

    assert plotter is not None

    summary = engine.get_scene_summary(plotter)
    assert 'n_meshes' in summary
    assert 'camera_position' in summary

    print(f"[ReportingTest] test_full_pipeline: summary={summary}")

