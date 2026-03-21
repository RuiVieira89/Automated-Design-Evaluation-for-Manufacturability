"""
Tests for Layer 6 — Orchestration: Prefect Flows

Tests the workflow orchestration functionality including flow execution,
task dependencies, and error handling.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import tempfile

# Import Prefect flows
import sys
sys.path.insert(0, '/home/rui/dev/Automated-Design-Evaluation-for-Manufacturability/synchronous_request_plane_FastAPI')

from prefect_flows import (
    single_part_analysis_flow,
    assembly_analysis_flow,
    batch_analysis_flow,
    scheduled_assembly_analysis_flow,
    extract_components,
    validate_inputs,
    store_results
)

@pytest.fixture
def sample_cad_file():
    """Create a temporary sample CAD file."""
    with tempfile.NamedTemporaryFile(suffix='.stl', delete=False) as f:
        f.write(b"fake stl content")
        return f.name

class TestPrefectTasks:
    """Test individual Prefect tasks."""

    def test_validate_inputs_success(self, sample_cad_file):
        """Test successful input validation."""
        result = validate_inputs.fn(sample_cad_file, "single")
        assert result is True

    def test_validate_inputs_file_not_found(self):
        """Test validation failure for missing file."""
        with pytest.raises(ValueError, match="Input file does not exist"):
            validate_inputs.fn("/nonexistent/file.stl", "single")

    def test_validate_inputs_invalid_process_type(self, sample_cad_file):
        """Test validation failure for invalid process type."""
        with pytest.raises(ValueError, match="Invalid process type"):
            validate_inputs.fn(sample_cad_file, "invalid")

    @patch('prefect_flows.Path')
    def test_extract_components(self, mock_path):
        """Test component extraction from assembly."""
        # Mock Path operations
        mock_path_obj = Mock()
        mock_path_obj.stem = "test_assembly"
        mock_path.return_value = mock_path_obj

        mock_parent = Mock()
        mock_path_obj.parent = mock_parent
        mock_parent.mkdir.return_value = None

        mock_component_path = Mock()
        mock_path.return_value = mock_component_path
        mock_component_path.parent = mock_parent
        mock_component_path.touch.return_value = None

        # Mock the range/side_effect for component creation
        with patch('builtins.range', return_value=[0, 1, 2]):
            result = extract_components.fn("test_assembly.stl")

            assert len(result) == 3
            assert all("comp_" in comp for comp in result)

    @patch('prefect_flows.Path')
    def test_store_results(self, mock_path):
        """Test result storage."""
        # Create a proper mock Path object
        mock_path_obj = Mock()
        mock_path_obj.parent.mkdir.return_value = None
        # Make str() return a proper path string
        mock_path_obj.__str__ = Mock(return_value="/tmp/analysis_results/test_job/results.json")
        mock_path.return_value = mock_path_obj

        # Mock json.dump and open
        with patch('json.dump') as mock_json_dump, \
             patch('builtins.open', create=True) as mock_open:

            mock_file_handle = Mock()
            mock_open.return_value.__enter__.return_value = mock_file_handle
            mock_open.return_value.__exit__.return_value = None

            result = store_results.fn(
                job_id="test_job",
                results={"status": "completed"}
            )

            mock_json_dump.assert_called_once()
            assert "test_job" in str(result)

class TestPrefectFlows:
    """Test Prefect flow execution."""

    @patch('prefect_flows.validate_inputs')
    @patch('prefect_flows.analyse_part')
    @patch('prefect_flows.store_results')
    @patch('prefect_flows.cleanup_job')
    def test_single_part_analysis_flow(self, mock_cleanup, mock_store, mock_analyse, mock_validate, sample_cad_file):
        """Test single part analysis flow."""
        # Setup mocks
        mock_validate.return_value = True

        mock_task_result = Mock()
        mock_task_result.get.return_value = {"status": "completed", "result": "test"}
        mock_analyse.delay.return_value = mock_task_result

        mock_store.return_value = "/tmp/results/test_job.json"

        # Execute flow
        result = single_part_analysis_flow(
            job_id="test_job",
            file_path=sample_cad_file
        )

        # Verify flow completed
        assert result["job_id"] == "test_job"
        assert result["status"] == "completed"
        assert "result_path" in result

        # Verify task calls
        mock_validate.assert_called_once()
        mock_analyse.delay.assert_called_once()
        mock_store.assert_called_once()
        mock_cleanup.delay.assert_called_once()

    @patch('prefect_flows.validate_inputs')
    @patch('prefect_flows.extract_components')
    @patch('prefect_flows.fan_out')
    @patch('prefect_flows.store_results')
    @patch('prefect_flows.cleanup_job')
    def test_assembly_analysis_flow(self, mock_cleanup, mock_store, mock_fan_out, mock_extract, mock_validate, sample_cad_file):
        """Test assembly analysis flow."""
        # Setup mocks
        mock_validate.return_value = True
        mock_extract.return_value = ["/tmp/comp1.stl", "/tmp/comp2.stl"]

        mock_fan_result = Mock()
        mock_fan_result.get.return_value = {"status": "completed", "component_count": 2}
        mock_fan_out.delay.return_value = mock_fan_result

        mock_store.return_value = "/tmp/results/test_assembly.json"

        # Execute flow
        result = assembly_analysis_flow(
            job_id="test_assembly",
            assembly_file=sample_cad_file
        )

        # Verify flow completed
        assert result["job_id"] == "test_assembly"
        assert result["status"] == "completed"
        assert result["component_count"] == 2

        # Verify task calls
        mock_validate.assert_called_once()
        mock_extract.assert_called_once()
        mock_fan_out.delay.assert_called_once()
        mock_store.assert_called_once()
        mock_cleanup.delay.assert_called_once()

    def test_batch_analysis_flow_input_validation(self):
        """Test batch analysis input validation."""
        # Mismatched input lengths should fail
        with pytest.raises(ValueError, match="must have same length"):
            batch_analysis_flow(
                job_ids=["job1", "job2"],
                file_paths=["file1.stl"],
                process_types=["single", "single"]
            )

    @patch('prefect_flows.single_part_analysis_flow')
    def test_batch_analysis_flow_single_parts(self, mock_single_flow):
        """Test batch analysis with single parts."""
        mock_single_flow.return_value = {"status": "completed"}

        result = batch_analysis_flow(
            job_ids=["job1", "job2"],
            file_paths=["file1.stl", "file2.stl"],
            process_types=["single", "single"]
        )

        assert result["total_jobs"] == 2
        assert result["completed_jobs"] == 2
        assert result["failed_jobs"] == 0

    @patch('prefect_flows.assembly_analysis_flow')
    def test_batch_analysis_flow_assemblies(self, mock_assembly_flow):
        """Test batch analysis with assemblies."""
        mock_assembly_flow.return_value = {"status": "completed"}

        result = batch_analysis_flow(
            job_ids=["job1"],
            file_paths=["assembly.stl"],
            process_types=["assembly"]
        )

        assert result["total_jobs"] == 1
        assert result["completed_jobs"] == 1

    def test_batch_analysis_flow_invalid_process_type(self):
        """Test batch analysis with invalid process type."""
        with pytest.raises(ValueError, match="Unsupported process type"):
            batch_analysis_flow(
                job_ids=["job1"],
                file_paths=["file1.stl"],
                process_types=["invalid"]
            )

    @patch('prefect_flows.assembly_analysis_flow')
    @patch('time.time')
    def test_scheduled_assembly_analysis_flow(self, mock_time, mock_assembly_flow):
        """Test scheduled assembly analysis flow."""
        mock_time.return_value = 1640995200  # 2022-01-01 00:00:00
        mock_assembly_flow.return_value = {"status": "completed"}

        result = scheduled_assembly_analysis_flow(
            assembly_file="/path/to/assembly.stl",
            schedule_config={}
        )

        assert result["status"] == "completed"
        mock_assembly_flow.assert_called_once()

class TestFlowErrorHandling:
    """Test error handling in flows."""

    @patch('prefect_flows.validate_inputs')
    def test_single_part_flow_validation_failure(self, mock_validate):
        """Test flow failure on validation error."""
        mock_validate.side_effect = ValueError("Validation failed")

        with pytest.raises(ValueError, match="Validation failed"):
            single_part_analysis_flow(
                job_id="test_job",
                file_path="/invalid/file.stl"
            )

    @patch('prefect_flows.validate_inputs')
    @patch('prefect_flows.analyse_part')
    def test_single_part_flow_task_failure(self, mock_analyse, mock_validate):
        """Test flow handling of task failure."""
        mock_validate.return_value = True

        mock_task_result = Mock()
        mock_task_result.get.side_effect = Exception("Task failed")
        mock_analyse.delay.return_value = mock_task_result

        with pytest.raises(Exception, match="Task failed"):
            single_part_analysis_flow(
                job_id="test_job",
                file_path="/test/file.stl"
            )

class TestFlowConfiguration:
    """Test flow configuration and parameters."""

    def test_flow_with_custom_configs(self):
        """Test flows with custom configuration parameters."""
        custom_rules = {"wall_thickness": {"min_thickness": 2.0}}
        custom_ml = {"model_version": "v2.0"}
        custom_reporting = {"color_scheme": "blue_red"}

        with patch('prefect_flows.validate_inputs'), \
             patch('prefect_flows.analyse_part') as mock_analyse, \
             patch('prefect_flows.store_results'), \
             patch('prefect_flows.cleanup_job'):

            mock_task_result = Mock()
            mock_task_result.get.return_value = {"status": "completed"}
            mock_analyse.delay.return_value = mock_task_result

            result = single_part_analysis_flow(
                job_id="test_job",
                file_path="/test/file.stl",
                rules_config=custom_rules,
                ml_config=custom_ml,
                reporting_config=custom_reporting
            )

            # Verify custom configs were passed to the task
            call_args = mock_analyse.delay.call_args
            assert call_args[1]["rules_config"] == custom_rules
            assert call_args[1]["ml_config"] == custom_ml
            assert call_args[1]["reporting_config"] == custom_reporting

if __name__ == "__main__":
    pytest.main([__file__])