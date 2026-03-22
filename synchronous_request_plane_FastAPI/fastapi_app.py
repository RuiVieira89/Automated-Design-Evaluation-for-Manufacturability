"""
Layer 6 — Orchestration: Synchronous Request Plane (FastAPI)

This module provides the synchronous request handling layer for the CAD manufacturability
analysis system. It accepts analysis requests, validates them, dispatches jobs to the
asynchronous execution plane, and provides polling endpoints for results.

Key Features:
- REST API for job submission and status polling
- Request validation using Pydantic models
- Integration with Celery for async job dispatch
- Redis backend for job state management
"""

import os
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from pathlib import Path

from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import redis
import celery
import json

from rules.rule_engine import RuleEngine, AnalysisReport
from segmentation.inference.ml_inference_engine import MLInferenceEngine
from reporting.annotation_engine import AnnotationEngine

# Configure logging
logger = logging.getLogger(__name__)


# Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")

# Initialize components
try:
    redis_client = redis.from_url(REDIS_URL)
except redis.ConnectionError:
    print(f"Warning: Could not connect to Redis at {REDIS_URL}. Some features may not work.")
    redis_client = None
celery_app = celery.Celery(
    'orchestration',
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND
)

# Pydantic models for request/response
class AnalysisRequest(BaseModel):
    """Request model for analysis jobs."""
    file_path: str = Field(..., description="Path to the CAD file to analyze")
    process_type: str = Field("single", description="Type of analysis: 'single' or 'assembly'")
    rules_config: Optional[Dict[str, Any]] = Field(None, description="Custom rules configuration")
    ml_config: Optional[Dict[str, Any]] = Field(None, description="ML inference configuration")
    reporting_config: Optional[Dict[str, Any]] = Field(None, description="Reporting configuration")

class JobStatus(BaseModel):
    """Job status response model."""
    job_id: str
    status: str  # PENDING, RUNNING, SUCCESS, FAILURE, RETRY
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    progress: Optional[float] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

class AnalysisResponse(BaseModel):
    """Response model for analysis results."""
    job_id: str
    status: str
    rule_results: List[Dict[str, Any]]
    ml_assessment: Optional[Dict[str, Any]] = None
    visualizations: Optional[List[str]] = None
    created_at: datetime

# FastAPI app
app = FastAPI(
    title="CAD Manufacturability Analyzer API",
    description="REST API for automated manufacturability analysis of CAD models",
    version="1.0.0"
)

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc)}

@app.post("/analyze", response_model=dict)
async def submit_analysis(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    process_type: str = Form("single"),
    rules_config: Optional[str] = Form(None),
    ml_config: Optional[str] = Form(None),
    reporting_config: Optional[str] = Form(None)
):
    """
    Submit a CAD file for manufacturability analysis.

    This endpoint accepts a CAD file upload and immediately returns a job_id.
    The actual analysis runs asynchronously. Use GET /job/{job_id} to check status.
    """
    # Generate unique job ID
    job_id = str(uuid.uuid4())

    # Save uploaded file temporarily
    upload_dir = Path("/tmp/cad_analysis_uploads")
    upload_dir.mkdir(exist_ok=True)
    file_path = upload_dir / f"{job_id}_{file.filename}"

    try:
        # Save file
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)

        # Parse config strings to dicts
        rules_cfg = eval(rules_config) if rules_config else None
        ml_cfg = eval(ml_config) if ml_config else None
        reporting_cfg = eval(reporting_config) if reporting_config else None

        if redis_client is None:
            raise HTTPException(status_code=503, detail="Redis service unavailable")

        try:
            # Create job record in Redis
            job_data = {
                "job_id": job_id,
                "status": "PENDING",
                "file_path": str(file_path),
                "process_type": process_type,
                "rules_config": rules_cfg,
                "ml_config": ml_cfg,
                "reporting_config": reporting_cfg,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

            redis_client.setex(f"job:{job_id}", 3600, json.dumps(job_data))  # 1 hour TTL

            # Dispatch to Celery (this will be implemented)
            from celery_tasks import analyse_part
            task = analyse_part.delay(job_id, str(file_path), process_type, rules_cfg, ml_cfg, reporting_cfg)

            # Update job with task ID
            job_data["celery_task_id"] = task.id
            redis_client.setex(f"job:{job_id}", 3600, json.dumps(job_data))
        except redis.ConnectionError:
            raise HTTPException(status_code=503, detail="Redis service unavailable")

        return JSONResponse(
            status_code=202,
            content={
                "job_id": job_id,
                "status": "accepted",
                "message": "Analysis job submitted successfully",
                "poll_url": f"/job/{job_id}"
            }
        )

    except Exception as e:
        # Clean up on error
        if file_path.exists():
            file_path.unlink()

        # Don't catch HTTPException, let it propagate
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(status_code=500, detail=f"Failed to submit job: {str(e)}")

@app.get("/job/{job_id}", response_model=JobStatus)
async def get_job_status(job_id: str):
    """Get the status of an analysis job."""
    try:
        if redis_client is None:
            raise HTTPException(status_code=503, detail="Redis service unavailable")

        job_data_str = redis_client.get(f"job:{job_id}")
        if not job_data_str:
            raise HTTPException(status_code=404, detail="Job not found")

        # Parse job data
        job_data = json.loads(job_data_str.decode())

        # Check Celery task status if we have a task ID
        if "celery_task_id" in job_data:
            task_id = job_data["celery_task_id"]
            task_result = celery_app.AsyncResult(task_id)

            print(f"DEBUG: Task {task_id} state: {task_result.state}, ready: {task_result.ready()}")
            logger.info(f"Task {task_id} state: {task_result.state}, ready: {task_result.ready()}")
            
            if task_result.state == "PENDING":
                job_data["status"] = "PENDING"
            elif task_result.state == "PROGRESS":
                job_data["status"] = "RUNNING"
                job_data["progress"] = task_result.info.get("progress", 0) if isinstance(task_result.info, dict) else 0
            elif task_result.state == "SUCCESS":
                job_data["status"] = "SUCCESS"
                # Store the result from the task
                if task_result.result:
                    job_data["result"] = task_result.result
                job_data["completed_at"] = datetime.now(timezone.utc).isoformat()
            elif task_result.state == "FAILURE":
                job_data["status"] = "FAILURE"
                job_data["error"] = str(task_result.info)
                job_data["completed_at"] = datetime.now(timezone.utc).isoformat()
            elif task_result.state == "RETRY":
                job_data["status"] = "RETRY"

            # Always save updated job data back to Redis
            redis_client.setex(f"job:{job_id}", 3600, json.dumps(job_data))

        return JobStatus(**job_data)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get job status: {str(e)}")

@app.delete("/job/{job_id}")
async def cancel_job(job_id: str):
    """Cancel a running analysis job."""
    try:
        if redis_client is None:
            raise HTTPException(status_code=503, detail="Redis service unavailable")

        job_data_str = redis_client.get(f"job:{job_id}")
        if not job_data_str:
            raise HTTPException(status_code=404, detail="Job not found")

        job_data = eval(job_data_str.decode())

        # Cancel Celery task if running
        if "celery_task_id" in job_data:
            task_id = job_data["celery_task_id"]
            celery_app.control.revoke(task_id, terminate=True)

        # Update job status
        job_data["status"] = "CANCELLED"
        job_data["completed_at"] = datetime.now(timezone.utc).isoformat()
        redis_client.setex(f"job:{job_id}", 3600, str(job_data))

        return {"message": "Job cancelled successfully"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to cancel job: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)