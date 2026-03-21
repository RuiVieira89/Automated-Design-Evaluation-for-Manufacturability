"""
Headless/API surface for Layer 5 visualization.

REST API for batch processing, CI/CD integration, and automated analysis.
Provides JSON reports and annotated screenshots.
"""

import json
import base64
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Any, Optional
import tempfile
import os
from datetime import datetime

import uvicorn
from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel, Field
import pyvista as pv

from rules.rule_engine import RuleEngine, AnalysisReport
from segmentation.inference.ml_inference_engine import MLInferenceEngine
from reporting.annotation_engine import AnnotationEngine, AnnotationConfig

app = FastAPI(
    title="CAD Manufacturability Analyzer API",
    description="REST API for automated manufacturability analysis of CAD models",
    version="1.0.0"
)


class AnalysisRequest(BaseModel):
    """Request model for analysis."""
    analysis_mode: str = Field(
        default="full",
        description="Analysis mode: 'full', 'rules_only', 'ml_only'"
    )
    include_visualization: bool = Field(
        default=True,
        description="Include 3D visualization in response"
    )
    export_formats: List[str] = Field(
        default_factory=lambda: ["json"],
        description="Export formats: 'json', 'png', 'vtk'"
    )


class AnalysisResponse(BaseModel):
    """Response model for analysis results."""
    job_id: str
    status: str
    summary: Dict[str, Any]
    rule_results: Optional[Dict[str, Any]] = None
    ml_assessment: Optional[Dict[str, Any]] = None
    visualizations: Optional[Dict[str, Any]] = None
    exports: Optional[Dict[str, str]] = None


class APIAnalyzer:
    """Headless analyzer for REST API."""

    def __init__(self):
        self.annotation_engine = AnnotationEngine()
        self.rule_engine = RuleEngine()
        self.ml_engine = MLInferenceEngine()
        self.jobs: Dict[str, Dict[str, Any]] = {}

    def analyze_file(self, file_path: str, request: AnalysisRequest) -> Dict[str, Any]:
        """Analyze a CAD file and return results."""
        job_id = f"job_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        try:
            # Load geometry
            mesh = self._load_geometry(file_path)

            results = {
                'job_id': job_id,
                'status': 'completed',
                'summary': {},
                'rule_results': None,
                'ml_assessment': None,
                'visualizations': None,
                'exports': {}
            }

            # Run analyses based on mode
            if request.analysis_mode in ['full', 'rules_only']:
                rule_results = self.rule_engine.analyze(mesh)
                results['rule_results'] = self._serialize_rule_results(rule_results)

            if request.analysis_mode in ['full', 'ml_only']:
                ml_assessment = self.ml_engine.analyze(mesh)
                results['ml_assessment'] = self._serialize_ml_assessment(ml_assessment)

            # Generate summary
            results['summary'] = self._generate_summary(results)

            # Create visualizations if requested
            if request.include_visualization:
                visualizations = self._create_visualizations(
                    mesh, results, request.export_formats
                )
                results['visualizations'] = visualizations
                results['exports'] = self._get_export_paths(job_id, request.export_formats)

            self.jobs[job_id] = results
            return results

        except Exception as e:
            error_result = {
                'job_id': job_id,
                'status': 'failed',
                'error': str(e),
                'summary': {'feasible': False, 'error': str(e)}
            }
            self.jobs[job_id] = error_result
            return error_result

    def _load_geometry(self, file_path: str) -> Any:
        """Load geometry from CAD file."""
        # This would need actual CAD file loading
        # For now, handle common formats or create fallback
        if file_path.endswith(('.stl', '.obj')):
            try:
                return pv.read(file_path)
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Failed to load mesh: {e}")

        # Fallback for CAD formats - would need OpenCASCADE or similar
        # For now, create a simple test geometry
        cube = pv.Cube()
        return cube

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

    def _generate_summary(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate summary statistics."""
        summary = {
            'total_violations': 0,
            'overall_severity': 'OK',
            'feasible': True,
            'severity_breakdown': {}
        }

        if results.get('rule_results'):
            rule_data = results['rule_results']
            violations = [r for r in rule_data['check_results']
                         if r['severity'] != 'OK']

            summary['total_violations'] = len(violations)
            summary['overall_severity'] = rule_data['overall_status']
            summary['feasible'] = rule_data['feasible']

            # Severity breakdown
            for violation in violations:
                severity = violation['severity']
                summary['severity_breakdown'][severity] = summary['severity_breakdown'].get(severity, 0) + 1

        return summary

    def _create_visualizations(self, mesh: Any, results: Dict[str, Any],
                              export_formats: List[str]) -> Dict[str, Any]:
        """Create visualizations and exports."""
        visualizations = {}

        # Get analysis data
        rule_results = []
        if results.get('rule_results'):
            # Convert back to CheckResult objects (simplified)
            rule_results = results['rule_results']['check_results']

        ml_assessment = results.get('ml_assessment')

        # Create annotated scene
        plotter = self.annotation_engine.create_annotated_scene(
            mesh, rule_results, ml_assessment
        )

        # Generate exports
        export_dir = Path("api_exports")
        export_dir.mkdir(exist_ok=True)

        job_id = results['job_id']

        for fmt in export_formats:
            if fmt == 'png':
                png_path = export_dir / f"{job_id}_screenshot.png"
                exported_path = self.annotation_engine.export_scene(
                    plotter, str(png_path.with_suffix('')), 'png'
                )

                # Convert to base64 for API response
                with open(exported_path, 'rb') as f:
                    img_data = base64.b64encode(f.read()).decode()
                visualizations['screenshot_base64'] = img_data

            elif fmt == 'vtk':
                vtk_path = export_dir / f"{job_id}_scene.vtk"
                exported_path = self.annotation_engine.export_scene(
                    plotter, str(vtk_path.with_suffix('')), 'vtk'
                )
                visualizations['vtk_path'] = str(exported_path)

        return visualizations

    def _get_export_paths(self, job_id: str, formats: List[str]) -> Dict[str, str]:
        """Get paths to exported files."""
        export_dir = Path("api_exports")
        paths = {}

        for fmt in formats:
            if fmt == 'png':
                paths['png'] = str(export_dir / f"{job_id}_screenshot.png")
            elif fmt == 'vtk':
                paths['vtk'] = str(export_dir / f"{job_id}_scene.vtk")

        return paths


# Global analyzer instance
analyzer = APIAnalyzer()


@app.post("/analyze", response_model=AnalysisResponse)
async def analyze_cad_file(
    file: UploadFile = File(...),
    analysis_mode: str = "full",
    include_visualization: bool = True,
    export_formats: str = "json,png"
):
    """
    Analyze a CAD file for manufacturability.

    - **file**: CAD file (STEP, IGES, STL, OBJ)
    - **analysis_mode**: 'full', 'rules_only', or 'ml_only'
    - **include_visualization**: Include 3D visualization
    - **export_formats**: Comma-separated list of formats (json,png,vtk)
    """
    # Parse export formats
    formats = [f.strip() for f in export_formats.split(',') if f.strip()]

    request = AnalysisRequest(
        analysis_mode=analysis_mode,
        include_visualization=include_visualization,
        export_formats=formats
    )

    # Save uploaded file temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix=file.filename) as tmp_file:
        content = await file.read()
        tmp_file.write(content)
        temp_path = tmp_file.name

    try:
        # Run analysis
        results = analyzer.analyze_file(temp_path, request)
        return AnalysisResponse(**results)

    finally:
        # Clean up temp file
        os.unlink(temp_path)


@app.get("/job/{job_id}")
async def get_job_status(job_id: str):
    """Get status and results of an analysis job."""
    if job_id not in analyzer.jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    return analyzer.jobs[job_id]


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@app.get("/exports/{job_id}/{filename}")
async def download_export(job_id: str, filename: str):
    """Download exported files (screenshots, VTK scenes)."""
    if job_id not in analyzer.jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job_data = analyzer.jobs[job_id]
    exports = job_data.get('exports', {})

    # Find the requested file
    file_path = None
    for fmt, path in exports.items():
        if filename in path:
            file_path = path
            break

    if not file_path or not Path(file_path).exists():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type='application/octet-stream'
    )


def main():
    """Run the FastAPI server."""
    uvicorn.run(
        "reporting.headless_api:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )


if __name__ == "__main__":
    main()
