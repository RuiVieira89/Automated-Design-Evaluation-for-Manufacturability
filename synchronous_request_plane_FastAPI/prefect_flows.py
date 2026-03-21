"""
Layer 6 — Orchestration: Prefect Flows

This module defines Prefect flows for orchestrating complex CAD analysis workflows,
particularly for assemblies and batch processing scenarios.

Prefect provides workflow orchestration on top of Celery task execution.
"""

import os
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path

from prefect import flow, task
from prefect.context import get_run_context
from prefect.states import Completed, Failed
from prefect.logging import get_run_logger
from prefect.exceptions import MissingContextError

# Import Celery tasks (will be mocked in tests)
try:
    from .celery_tasks import analyse_part, fan_out, aggregate, cleanup_job
except ImportError:
    # For testing without proper package structure
    analyse_part = None
    fan_out = None
    aggregate = None
    cleanup_job = None

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@task
def extract_components(assembly_file: str) -> List[str]:
    """
    Extract individual component files from an assembly.

    In a real implementation, this would parse the assembly file
    and extract individual component geometries.
    """
    try:
        logger = get_run_logger()
    except MissingContextError:
        logger = logging.getLogger(__name__)

    # Placeholder: simulate extracting 3 components
    # In reality, this would use FreeCAD or similar to decompose assemblies
    component_files = []
    for i in range(3):
        component_file = f"/tmp/components/{Path(assembly_file).stem}_comp_{i}.stl"
        # Simulate creating component files
        Path(component_file).parent.mkdir(parents=True, exist_ok=True)
        Path(component_file).touch()  # Placeholder
        component_files.append(component_file)

    logger.info(f"Extracted {len(component_files)} components from {assembly_file}")
    return component_files

@task
def validate_inputs(file_path: str, process_type: str) -> bool:
    """Validate input parameters before starting analysis."""
    try:
        logger = get_run_logger()
    except MissingContextError:
        # Fallback for testing without context
        logger = logging.getLogger(__name__)

    if not Path(file_path).exists():
        raise ValueError(f"Input file does not exist: {file_path}")

    if process_type not in ["single", "assembly"]:
        raise ValueError(f"Invalid process type: {process_type}")

    logger.info(f"Input validation passed for {file_path}")
    return True

@task
def store_results(job_id: str, results: Dict[str, Any], output_dir: Optional[str] = None):
    """Store analysis results to persistent storage."""
    try:
        logger = get_run_logger()
    except MissingContextError:
        logger = logging.getLogger(__name__)

    output_path = Path(output_dir or f"/tmp/analysis_results/{job_id}/results.json")

    try:
        import json
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2, default=str)

        logger.info(f"Results stored to {output_path}")
        return str(output_path)

    except Exception as e:
        logger.error(f"Failed to store results: {e}")
        raise

@flow(name="single-part-analysis")
def single_part_analysis_flow(
    job_id: str,
    file_path: str,
    rules_config: Optional[Dict[str, Any]] = None,
    ml_config: Optional[Dict[str, Any]] = None,
    reporting_config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Prefect flow for analyzing a single CAD part.

    This flow orchestrates the complete analysis pipeline for a single component.
    """
    try:
        logger = get_run_logger()
    except MissingContextError:
        logger = logging.getLogger(__name__)

    logger.info(f"Starting single part analysis flow for job {job_id}")

    # Validate inputs
    validate_inputs(file_path, "single")

    # Run analysis (this will be a Celery task)
    # Note: In Prefect 2.x, we can use task runners to execute Celery tasks
    result = analyse_part.delay(
        job_id=job_id,
        file_path=file_path,
        process_type="single",
        rules_config=rules_config,
        ml_config=ml_config,
        reporting_config=reporting_config
    )

    # Wait for result (simplified - in production use proper async handling)
    analysis_result = result.get(timeout=3600)

    # Store results
    stored_path = store_results(job_id, analysis_result)

    # Cleanup
    cleanup_job.delay(job_id)

    logger.info(f"Single part analysis flow completed for job {job_id}")
    return {
        "job_id": job_id,
        "status": "completed",
        "result_path": stored_path,
        "analysis_result": analysis_result
    }

@flow(name="assembly-analysis")
def assembly_analysis_flow(
    job_id: str,
    assembly_file: str,
    rules_config: Optional[Dict[str, Any]] = None,
    ml_config: Optional[Dict[str, Any]] = None,
    reporting_config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Prefect flow for analyzing a CAD assembly.

    This flow decomposes the assembly, analyzes components in parallel,
    then aggregates the results.
    """
    try:
        logger = get_run_logger()
    except MissingContextError:
        logger = logging.getLogger(__name__)

    logger.info(f"Starting assembly analysis flow for job {job_id}")

    # Validate inputs
    validate_inputs(assembly_file, "assembly")

    # Extract components from assembly
    component_files = extract_components(assembly_file)

    # Fan out analysis to components (parallel execution via Celery chord)
    fan_out_result = fan_out.delay(
        job_id=job_id,
        component_files=component_files,
        rules_config=rules_config,
        ml_config=ml_config,
        reporting_config=reporting_config
    )

    # Wait for aggregation to complete
    final_result = fan_out_result.get(timeout=3600)

    # Store results
    stored_path = store_results(job_id, final_result)

    # Cleanup
    cleanup_job.delay(job_id)

    logger.info(f"Assembly analysis flow completed for job {job_id}")
    return {
        "job_id": job_id,
        "status": "completed",
        "component_count": len(component_files),
        "result_path": stored_path,
        "analysis_result": final_result
    }

@flow(name="batch-analysis")
def batch_analysis_flow(
    job_ids: List[str],
    file_paths: List[str],
    process_types: List[str],
    rules_config: Optional[Dict[str, Any]] = None,
    ml_config: Optional[Dict[str, Any]] = None,
    reporting_config: Optional[Dict[str, Any]] = None,
    max_concurrent: int = 5
) -> Dict[str, Any]:
    """
    Prefect flow for batch analysis of multiple CAD files.

    This flow processes multiple files with controlled concurrency.
    """
    try:
        logger = get_run_logger()
    except MissingContextError:
        logger = logging.getLogger(__name__)

    logger.info(f"Starting batch analysis flow for {len(job_ids)} jobs")

    if not (len(job_ids) == len(file_paths) == len(process_types)):
        raise ValueError("job_ids, file_paths, and process_types must have same length")

    # Create subtasks for each analysis
    analysis_tasks = []
    for job_id, file_path, process_type in zip(job_ids, file_paths, process_types):
        if process_type == "single":
            task = single_part_analysis_flow(
                job_id=job_id,
                file_path=file_path,
                rules_config=rules_config,
                ml_config=ml_config,
                reporting_config=reporting_config
            )
        elif process_type == "assembly":
            task = assembly_analysis_flow(
                job_id=job_id,
                assembly_file=file_path,
                rules_config=rules_config,
                ml_config=ml_config,
                reporting_config=reporting_config
            )
        else:
            raise ValueError(f"Unsupported process type: {process_type}")

        analysis_tasks.append(task)

    # Execute with concurrency control
    # Note: Prefect handles concurrency through its task runner configuration
    results = analysis_tasks  # In practice, these would be executed concurrently

    batch_result = {
        "batch_id": f"batch_{os.urandom(8).hex()}",
        "total_jobs": len(job_ids),
        "completed_jobs": len([r for r in results if r.get("status") == "completed"]),
        "failed_jobs": len([r for r in results if r.get("status") == "failed"]),
        "results": results
    }

    logger.info(f"Batch analysis flow completed: {batch_result['completed_jobs']}/{batch_result['total_jobs']} successful")
    return batch_result

@flow(name="scheduled-assembly-analysis")
def scheduled_assembly_analysis_flow(
    assembly_file: str,
    schedule_config: Dict[str, Any],
    rules_config: Optional[Dict[str, Any]] = None,
    ml_config: Optional[Dict[str, Any]] = None,
    reporting_config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Prefect flow for scheduled analysis of assemblies.

    This demonstrates how Prefect can handle scheduled/cron-based workflows.
    """
    try:
        logger = get_run_logger()
    except MissingContextError:
        logger = logging.getLogger(__name__)

    # Generate job ID based on file and timestamp
    import time
    job_id = f"scheduled_{Path(assembly_file).stem}_{int(time.time())}"

    logger.info(f"Starting scheduled analysis for {assembly_file}")

    # Run assembly analysis
    result = assembly_analysis_flow(
        job_id=job_id,
        assembly_file=assembly_file,
        rules_config=rules_config,
        ml_config=ml_config,
        reporting_config=reporting_config
    )

    # Additional scheduled workflow logic could go here
    # (e.g., notifications, archiving, integration with external systems)

    logger.info(f"Scheduled analysis completed for {assembly_file}")
    return result

# Export flows for use in deployment scripts
__all__ = [
    'single_part_analysis_flow',
    'assembly_analysis_flow',
    'batch_analysis_flow',
    'scheduled_assembly_analysis_flow'
]