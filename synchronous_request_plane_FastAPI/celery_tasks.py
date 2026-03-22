"""
Layer 6 — Orchestration: Asynchronous Execution Plane (Celery Tasks)

This module defines the Celery tasks for asynchronous execution of CAD manufacturability
analysis jobs. Tasks are designed to be idempotent and support progress tracking.
"""

import os
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path
import tempfile

from celery import Celery, Task
from celery_progress.backend import ProgressRecorder

# Import analysis pipeline components
from rules.rule_engine import RuleEngine, AnalysisReport, CheckResult, Severity
from segmentation.inference.ml_inference_engine import MLInferenceEngine, ManufacturabilityAssessment
from reporting.annotation_engine import AnnotationEngine, AnnotationConfig
import sys
import os
import importlib.util

# Import geometry loader
parent_dir = os.path.dirname(os.path.dirname(__file__))
io_path = os.path.join(parent_dir, 'io', 'io.py')
spec = importlib.util.spec_from_file_location("io_module", io_path)
io_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(io_module)
input_layer = io_module.input_layer

from geometry.geometry_kernel import GeometryKernel, GeometryInputs

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Celery configuration
celery_app = Celery(
    'orchestration',
    broker=os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/1'),
    backend=os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/2')
)

# Configure Celery
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour timeout
    task_soft_time_limit=3300,  # 55 minutes soft timeout
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)

class AnalysisTask(Task):
    """Base class for analysis tasks with progress tracking."""

    def __init__(self):
        self.progress_recorder = None

    def update_progress(self, current: int, total: int, description: str = ""):
        """Update task progress."""
        if self.progress_recorder:
            self.progress_recorder.set_progress(current, total, description)
        logger.info(f"Task progress: {current}/{total} - {description}")

@celery_app.task(bind=True, base=AnalysisTask)
def analyse_part(self, job_id: str, file_path: str, process_type: str = "single",
                rules_config: Optional[Dict[str, Any]] = None,
                ml_config: Optional[Dict[str, Any]] = None,
                reporting_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Analyze a single CAD part for manufacturability.

    This is the main analysis task that runs the complete L1-L5 pipeline:
    1. Load geometry (L1)
    2. Run rule checks (L3)
    3. ML assessment (L4)
    4. Generate visualizations (L5)

    Args:
        job_id: Unique job identifier
        file_path: Path to the CAD file
        process_type: Type of analysis ('single' or 'assembly')
        rules_config: Custom rules configuration
        ml_config: ML inference configuration
        reporting_config: Reporting configuration

    Returns:
        Dict containing analysis results
    """
    self.progress_recorder = ProgressRecorder(self)

    try:
        logger.info(f"Starting analysis for job {job_id}, file: {file_path}")

        # Step 1: Load geometry (L1)
        self.update_progress(1, 5, "Loading geometry")
        geometry = input_layer.load_geometry(file_path)
        
        # Create geometry inputs for Layer 2
        if geometry.is_brep:
            geom_inputs = GeometryInputs(brep_shape=geometry.shape)
        else:
            geom_inputs = GeometryInputs(
                mesh_vertices=geometry.points,
                mesh_faces=geometry.cells
            )
        
        # Step 2: Process geometry (L2)
        self.update_progress(2, 5, "Processing geometry")
        geom_kernel = GeometryKernel()
        geom_outputs = geom_kernel.process_geometry(geom_inputs)
        
        # Step 3: Run rule checks (L3)
        self.update_progress(3, 5, "Running rule checks")
        rule_engine = RuleEngine()
        rule_results = rule_engine.analyze({
            'brep_results': geom_outputs.brep_results,
            'mesh_results': geom_outputs.mesh_results
        })

        # Step 3: ML assessment (L4)
        self.update_progress(3, 5, "Running ML assessment")
        ml_engine = MLInferenceEngine()
        ml_assessment = ml_engine.analyze_manufacturability(rule_results.check_results, {
            'brep_results': geom_outputs.brep_results,
            'mesh_results': geom_outputs.mesh_results
        })

        # Step 4: Generate visualizations (L5)
        self.update_progress(4, 5, "Generating visualizations")
        reporting_cfg = reporting_config or {}
        annotation_config = AnnotationConfig(**reporting_cfg)
        annotation_engine = AnnotationEngine(annotation_config)

        # Create PyVista mesh from geometry
        import pyvista as pv
        if geometry.is_brep:
            # Tessellate if needed
            tessellated = geometry.tessellate()
            pv_mesh = pv.PolyData(tessellated.points, tessellated.cells)
        else:
            pv_mesh = pv.PolyData(geometry.points, geometry.cells)

        # Create annotated scene
        plotter = annotation_engine.create_annotated_scene(pv_mesh, rule_results.check_results, ml_assessment)

        # Export visualizations
        output_dir = Path(f"/tmp/analysis_results/{job_id}")
        output_dir.mkdir(parents=True, exist_ok=True)

        visualizations = []
        for fmt in ['png', 'vtk']:
            try:
                output_path = output_dir / f"result.{fmt}"
                annotation_engine.export_scene(plotter, str(output_path), fmt)
                visualizations.append(str(output_path))
            except Exception as e:
                logger.warning(f"Failed to export {fmt}: {e}")

        # Step 5: Compile results
        self.update_progress(5, 5, "Compiling results")

        result = {
            "job_id": job_id,
            "file_path": file_path,
            "process_type": process_type,
            "rule_results": [result.__dict__ for result in rule_results.check_results],
            "ml_assessment": ml_assessment,
            "visualizations": visualizations,
            "status": "completed",
            "timestamp": str(celery_app.now())
        }

        logger.info(f"Analysis completed for job {job_id}")
        return result

    except Exception as e:
        logger.error(f"Analysis failed for job {job_id}: {str(e)}")
        raise

@celery_app.task(bind=True)
def fan_out(self, job_id: str, component_files: List[str],
           rules_config: Optional[Dict[str, Any]] = None,
           ml_config: Optional[Dict[str, Any]] = None,
           reporting_config: Optional[Dict[str, Any]] = None):
    """
    Fan out analysis tasks for assembly components.

    This task creates a chord that runs analyse_part on each component in parallel,
    then calls aggregate to combine the results.
    """
    from celery import chord

    logger.info(f"Fanning out analysis for assembly job {job_id} with {len(component_files)} components")

    # Create subtasks for each component
    subtasks = [
        analyse_part.s(job_id, component_file, "component", rules_config, ml_config, reporting_config)
        for component_file in component_files
    ]

    # Create chord: run all subtasks in parallel, then aggregate
    chord_result = chord(subtasks)(aggregate.s(job_id))
    return chord_result.id

@celery_app.task(bind=True)
def aggregate(self, job_id: str, component_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Aggregate results from component analyses into a unified assembly report.

    This is the chord callback that runs after all component analyses complete.
    """
    logger.info(f"Aggregating results for assembly job {job_id}")

    try:
        # Combine rule results from all components
        all_rule_results = []
        all_visualizations = []

        for component_result in component_results:
            if "rule_results" in component_result:
                all_rule_results.extend(component_result["rule_results"])
            if "visualizations" in component_result:
                all_visualizations.extend(component_result["visualizations"])

        # Aggregate ML assessments (simplified - take the worst assessment)
        ml_assessments = [r.get("ml_assessment") for r in component_results if r.get("ml_assessment")]
        aggregated_ml = None
        if ml_assessments:
            # Simple aggregation: take the assessment with lowest confidence or highest risk
            aggregated_ml = ml_assessments[0]  # Placeholder logic

        # Create unified result
        result = {
            "job_id": job_id,
            "process_type": "assembly",
            "component_count": len(component_results),
            "rule_results": all_rule_results,
            "ml_assessment": aggregated_ml,
            "visualizations": all_visualizations,
            "status": "completed",
            "timestamp": str(celery_app.now())
        }

        logger.info(f"Aggregation completed for assembly job {job_id}")
        return result

    except Exception as e:
        logger.error(f"Aggregation failed for job {job_id}: {str(e)}")
        raise

@celery_app.task(bind=True)
def cleanup_job(self, job_id: str):
    """Clean up temporary files and resources for a completed job."""
    try:
        # Clean up uploaded files
        upload_dir = Path("/tmp/cad_analysis_uploads")
        for file_path in upload_dir.glob(f"{job_id}_*"):
            file_path.unlink()

        # Clean up result files (optional - might want to keep for some time)
        result_dir = Path(f"/tmp/analysis_results/{job_id}")
        if result_dir.exists():
            import shutil
            shutil.rmtree(result_dir)

        logger.info(f"Cleaned up resources for job {job_id}")

    except Exception as e:
        logger.error(f"Cleanup failed for job {job_id}: {str(e)}")

# Export the app for use in other modules
__all__ = ['celery_app', 'analyse_part', 'fan_out', 'aggregate', 'cleanup_job']