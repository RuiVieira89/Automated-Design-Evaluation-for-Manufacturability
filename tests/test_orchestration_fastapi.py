"""
Tests for Layer 6 — Orchestration: FastAPI Application

Tests the synchronous request plane functionality including job submission,
status polling, and error handling.
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient
from pathlib import Path
import tempfile
import json

# Import the FastAPI app
import sys
sys.path.insert(0, '/home/rui/dev/Automated-Design-Evaluation-for-Manufacturability/synchronous_request_plane_FastAPI')

from fastapi_app import app
from celery_tasks import analyse_part

@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)

@pytest.fixture
def sample_cad_file():
    """Create a temporary sample CAD file for testing."""
    with tempfile.NamedTemporaryFile(suffix='.stl', delete=False) as f:
        # Create a minimal STL file content (simplified)
        stl_content = b"""solid test_cube
  facet normal 0 0 1
    outer loop
      vertex 0 0 0
      vertex 1 0 0
      vertex 0.5 1 0
    endloop
  endfacet
endsolid test_cube"""
        f.write(stl_content)
        return f.name

class TestFastAPIApp:
    """Test cases for the FastAPI application."""

    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data

    @patch('fastapi_app.redis_client')
    @patch('fastapi_app.celery_app')
    def test_submit_analysis_success(self, mock_celery, mock_redis, client, sample_cad_file):
        """Test successful job submission."""
        # Mock Redis
        mock_redis.setex.return_value = None

        # Mock Celery task
        mock_task = Mock()
        mock_task.id = "test_task_id"
        mock_task.delay.return_value = mock_task
        mock_celery.send_task.return_value = mock_task

        # Mock the analyse_part task import
        with patch.object(analyse_part, 'delay', return_value=mock_task):
            # Submit analysis
            with open(sample_cad_file, 'rb') as f:
                response = client.post(
                    "/analyze",
                    files={"file": ("test.stl", f, "application/octet-stream")},
                    data={"process_type": "single"}
                )

            assert response.status_code == 200
            data = response.json()
            assert "job_id" in data
            assert data["status"] == "accepted"
            assert "poll_url" in data

    def test_submit_analysis_invalid_file(self, client):
        """Test job submission with invalid file."""
        response = client.post("/analyze")
        assert response.status_code == 422  # Validation error

    @patch('fastapi_app.redis_client')
    def test_get_job_status_not_found(self, mock_redis, client):
        """Test getting status of non-existent job."""
        mock_redis.get.return_value = None

        response = client.get("/job/nonexistent")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @patch('fastapi_app.redis_client')
    @patch('fastapi_app.celery_app')
    def test_get_job_status_success(self, mock_celery, mock_redis, client):
        """Test getting job status successfully."""
        job_data = {
            "job_id": "test_job",
            "status": "PENDING",
            "created_at": "2024-01-01T00:00:00",
            "celery_task_id": "test_task_id"
        }

        # Mock Redis returning job data
        mock_redis.get.return_value = json.dumps(job_data).encode()

        # Mock Celery task as successful
        mock_task_result = Mock()
        mock_task_result.state = "SUCCESS"
        mock_task_result.result = {"test": "result"}
        mock_celery.AsyncResult.return_value = mock_task_result

        response = client.get("/job/test_job")
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == "test_job"
        assert data["status"] == "SUCCESS"
        assert data["result"] == {"test": "result"}

    @patch('fastapi_app.redis_client')
    @patch('fastapi_app.celery_app')
    def test_cancel_job_success(self, mock_celery, mock_redis, client):
        """Test successful job cancellation."""
        job_data = {
            "job_id": "test_job",
            "status": "RUNNING",
            "celery_task_id": "test_task_id"
        }

        mock_redis.get.return_value = json.dumps(job_data).encode()
        mock_redis.setex.return_value = None
        mock_celery.control.revoke.return_value = None

        response = client.delete("/job/test_job")
        assert response.status_code == 200
        assert "cancelled" in response.json()["message"].lower()

    @patch('fastapi_app.redis_client')
    def test_cancel_job_not_found(self, mock_redis, client):
        """Test cancelling non-existent job."""
        mock_redis.get.return_value = None

        response = client.delete("/job/nonexistent")
        assert response.status_code == 404

class TestRequestValidation:
    """Test request validation and error handling."""

    def test_invalid_process_type(self, client, sample_cad_file):
        """Test submission with invalid process type."""
        with patch('fastapi_app.redis_client') as mock_redis, \
             patch('fastapi_app.celery_app') as mock_celery, \
             patch.object(analyse_part, 'delay') as mock_analyse:

            # Setup mocks
            mock_redis.setex.return_value = None
            mock_task = Mock()
            mock_task.id = "test_task_id"
            mock_analyse.return_value = mock_task

            with open(sample_cad_file, 'rb') as f:
                response = client.post(
                    "/analyze",
                    files={"file": ("test.stl", f, "application/octet-stream")},
                    data={"process_type": "invalid"}
                )

            # Should still accept but validation happens in task
            assert response.status_code == 200

    def test_large_file_handling(self, client):
        """Test handling of potentially large files."""
        # Create a mock large file
        large_content = b"x" * (10 * 1024 * 1024)  # 10MB

        with patch('fastapi_app.redis_client') as mock_redis, \
             patch('fastapi_app.celery_app') as mock_celery, \
             patch.object(analyse_part, 'delay') as mock_analyse:

            # Setup mocks
            mock_redis.setex.return_value = None
            mock_task = Mock()
            mock_task.id = "test_task_id"
            mock_analyse.return_value = mock_task

            response = client.post(
                "/analyze",
                files={"file": ("large.stl", large_content, "application/octet-stream")},
                data={"process_type": "single"}
            )

            # Should handle large files appropriately
            assert response.status_code in [200, 413]  # 200 success or 413 too large

if __name__ == "__main__":
    pytest.main([__file__])