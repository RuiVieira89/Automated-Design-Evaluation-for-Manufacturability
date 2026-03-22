"""
Tests for Layer 6 — Orchestration: Celery Tasks

Tests the asynchronous execution plane including task execution,
progress tracking, and error handling.
"""

import pytest
import tempfile
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import json

# Import Celery tasks
import sys
sys.path.insert(0, '/home/rui/dev/Automated-Design-Evaluation-for-Manufacturability/synchronous_request_plane_FastAPI')

from celery_tasks import analyse_part, fan_out, aggregate, cleanup_job

@pytest.fixture
def sample_stl_file():
    """Create a temporary sample STL file for testing."""
    with tempfile.NamedTemporaryFile(suffix='.stl', delete=False) as f:
        # Create a minimal valid STL file
        stl_content = b"""solid test_cube
  facet normal 0 0 1
    outer loop
      vertex 0 0 0
      vertex 1 0 0
      vertex 0.5 1 0
    endloop
  endfacet
  facet normal 0 0 -1
    outer loop
      vertex 0 0 1
      vertex 0.5 1 1
      vertex 1 0 1
    endloop
  endfacet
endsolid test_cube"""
        f.write(stl_content)
        return f.name

class TestCeleryTasks:
    """Test cases for Celery task execution."""

    @patch('celery_tasks.input_layer.load_geometry')
    @patch('celery_tasks.RuleEngine')
    @patch('celery_tasks.MLInferenceEngine')
    @patch('celery_tasks.AnnotationEngine')
    def test_analyse_part_success(self, mock_annotation, mock_ml, mock_rules, mock_load_geom, sample_stl_file):
        """Test successful part analysis."""
        # Mock geometry loading
        mock_mesh = Mock()
        mock_load_geom.return_value = mock_mesh

        # Mock rule engine
        mock_rule_engine = Mock()
        mock_rule_results = [Mock(__dict__={'check_name': 'test', 'severity': 'PASS'})]
        mock_rule_engine.analyze_geometry.return_value = mock_rule_results
        mock_rules.return_value = mock_rule_engine

        # Mock ML engine
        mock_ml_engine = Mock()
        mock_ml_assessment = Mock(__dict__={'process_recommendations': []})
        mock_ml_engine.assess_manufacturability.return_value = mock_ml_assessment
        mock_ml.return_value = mock_ml_engine

        # Mock annotation engine
        mock_annotation_engine = Mock()
        mock_plotter = Mock()
        mock_annotation_engine.create_annotated_scene.return_value = mock_plotter
        mock_annotation_engine.export_scene.return_value = "/tmp/test.png"
        mock_annotation.return_value = mock_annotation_engine

        # Execute task
        result = analyse_part(
            job_id="test_job",
            file_path=sample_stl_file,
            process_type="single"
        )

        # Verify result structure
        assert result["job_id"] == "test_job"
        assert result["status"] == "completed"
        assert "rule_results" in result
        assert "ml_assessment" in result
        assert "visualizations" in result

        # Verify mocks were called
        mock_load_geom.assert_called_once_with(sample_stl_file)
        mock_rule_engine.analyze_geometry.assert_called_once_with(mock_mesh)
        mock_ml_engine.assess_manufacturability.assert_called_once()
        mock_annotation_engine.create_annotated_scene.assert_called_once()

    @patch('celery_tasks.load_geometry')
    def test_analyse_part_geometry_load_failure(self, mock_load_geom):
        """Test analysis failure when geometry loading fails."""
        mock_load_geom.return_value = None

        with pytest.raises(ValueError, match="Failed to load geometry"):
            analyse_part(
                job_id="test_job",
                file_path="/nonexistent/file.stl"
            )

    @patch('celery_tasks.load_geometry')
    @patch('celery_tasks.RuleEngine')
    def test_analyse_part_rule_engine_failure(self, mock_rules, mock_load_geom):
        """Test analysis failure in rule engine."""
        mock_mesh = Mock()
        mock_load_geom.return_value = mock_mesh

        mock_rule_engine = Mock()
        mock_rule_engine.analyze_geometry.side_effect = Exception("Rule engine error")
        mock_rules.return_value = mock_rule_engine

        with pytest.raises(Exception, match="Rule engine error"):
            analyse_part(
                job_id="test_job",
                file_path="/test/file.stl"
            )

    def test_fan_out_task_creation(self):
        """Test fan_out task creates correct chord structure."""
        component_files = ["/tmp/comp1.stl", "/tmp/comp2.stl", "/tmp/comp3.stl"]

        # Mock chord and subtasks
        with patch('celery_tasks.chord') as mock_chord, \
             patch('celery_tasks.analyse_part') as mock_analyse:

            mock_subtask = Mock()
            mock_analyse.s.return_value = mock_subtask

            mock_chord_result = Mock()
            mock_chord_result.id = "chord_task_id"
            mock_chord.return_value = mock_chord_result

            # Execute fan_out
            result = fan_out(
                job_id="test_assembly",
                component_files=component_files
            )

            # Verify chord was created with correct number of subtasks
            assert mock_chord.called
            assert result == "chord_task_id"

    def test_aggregate_success(self):
        """Test successful result aggregation."""
        component_results = [
            {
                "rule_results": [{"check_name": "check1", "severity": "PASS"}],
                "ml_assessment": {"confidence": 0.8},
                "visualizations": ["/tmp/viz1.png"]
            },
            {
                "rule_results": [{"check_name": "check2", "severity": "WARN"}],
                "ml_assessment": {"confidence": 0.7},
                "visualizations": ["/tmp/viz2.png"]
            }
        ]

        result = aggregate(
            job_id="test_assembly",
            component_results=component_results
        )

        # Verify aggregation
        assert result["job_id"] == "test_assembly"
        assert result["component_count"] == 2
        assert len(result["rule_results"]) == 2
        assert len(result["visualizations"]) == 2
        assert result["status"] == "completed"

    def test_aggregate_empty_results(self):
        """Test aggregation with empty component results."""
        result = aggregate(
            job_id="test_assembly",
            component_results=[]
        )

        assert result["component_count"] == 0
        assert result["rule_results"] == []
        assert result["visualizations"] == []

    @patch('celery_tasks.Path')
    def test_cleanup_job_success(self, mock_path):
        """Test successful job cleanup."""
        # Mock file existence and removal
        mock_file_path = Mock()
        mock_file_path.exists.return_value = True
        mock_file_path.unlink.return_value = None

        mock_dir_path = Mock()
        mock_dir_path.exists.return_value = True

        mock_path.return_value = mock_file_path
        mock_path.glob.return_value = [mock_file_path]

        with patch('celery_tasks.shutil.rmtree') as mock_rmtree:
            cleanup_job(job_id="test_job")

            # Verify cleanup was attempted
            mock_rmtree.assert_called()

class TestProgressTracking:
    """Test progress tracking functionality."""

    @patch('celery_tasks.load_geometry')
    @patch('celery_tasks.RuleEngine')
    @patch('celery_tasks.MLInferenceEngine')
    @patch('celery_tasks.AnnotationEngine')
    def test_progress_updates(self, mock_annotation, mock_ml, mock_rules, mock_load_geom, sample_stl_file):
        """Test that progress is updated throughout analysis."""
        # Setup mocks
        mock_mesh = Mock()
        mock_load_geom.return_value = mock_mesh

        mock_rule_engine = Mock()
        mock_rule_results = []
        mock_rule_engine.analyze_geometry.return_value = mock_rule_results
        mock_rules.return_value = mock_rule_engine

        mock_ml_engine = Mock()
        mock_ml_assessment = Mock(__dict__={})
        mock_ml_engine.assess_manufacturability.return_value = mock_ml_assessment
        mock_ml.return_value = mock_ml_engine

        mock_annotation_engine = Mock()
        mock_plotter = Mock()
        mock_annotation_engine.create_annotated_scene.return_value = mock_plotter
        mock_annotation_engine.export_scene.return_value = "/tmp/test.png"
        mock_annotation.return_value = mock_annotation_engine

        # Create task instance to test progress
        task_instance = analyse_part._get_current_object()
        progress_calls = []

        # Mock progress recorder
        mock_progress_recorder = Mock()
        mock_progress_recorder.set_progress = lambda c, t, d: progress_calls.append((c, t, d))
        task_instance.progress_recorder = mock_progress_recorder

        # Execute task
        with patch.object(task_instance, 'update_progress', side_effect=lambda c, t, d: progress_calls.append((c, t, d))):
            result = analyse_part(
                job_id="test_job",
                file_path=sample_stl_file
            )

        # Verify progress was tracked (should have 5 steps)
        assert len(progress_calls) >= 4  # At least loading, rules, ML, visualization

class TestErrorHandling:
    """Test error handling in tasks."""

    @patch('celery_tasks.load_geometry')
    def test_task_timeout_simulation(self, mock_load_geom):
        """Test behavior under timeout conditions."""
        # Simulate a long-running operation that might timeout
        mock_load_geom.return_value = Mock()

        with patch('celery_tasks.RuleEngine') as mock_rules:
            mock_rule_engine = Mock()
            mock_rule_engine.analyze_geometry.side_effect = Exception("Timeout")
            mock_rules.return_value = mock_rule_engine

            with pytest.raises(Exception, match="Timeout"):
                analyse_part(
                    job_id="test_job",
                    file_path="/test/file.stl"
                )

if __name__ == "__main__":
    pytest.main([__file__])