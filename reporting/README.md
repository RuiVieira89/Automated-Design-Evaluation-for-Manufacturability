Heatmap generation, JSON/PDF export


This layer is structurally unlike the previous four — it fans outward into three independent deployment surfaces rather than converging into a single output. I'll show the overall structure first, then the annotation pipeline that feeds all three surfaces.

see viz_layer5_overview.svg

The key structural insight is that the annotation engine sits above the three surfaces as a shared service — not inside any one of them. Here's why that matters, and how the surfaces differ in what they need from it:
The annotation engine is surface-agnostic. PyVista produces a PolyData mesh with scalar arrays attached (one float per face, encoding violation severity), plus a list of arrow glyphs and text labels at specific 3D coordinates. That scene description is the same regardless of whether it gets rendered interactively in FreeCAD, embedded in a Streamlit iframe, or rendered offscreen to a PNG for a JSON report. The three surfaces are just different renderers for the same annotated scene object.
The three surfaces have different latency and interaction contracts. The FreeCAD plugin is in-process and synchronous — it runs when the designer clicks "analyse" and blocks the viewport until done, so the pipeline needs to be fast (< 3s for typical parts). The web UI is request/response and can show a progress bar, so slower batch analysis is tolerable. The headless/API surface is fully async — it's called from CI/CD on every geometry commit, produces a JSON artefact and annotated screenshots, and never interacts with a human in the loop.
The feedback loop is the long-term value of this layer. Each surface should let a designer mark a result as a false positive or override the process classification. Those overrides are the most valuable training signal available — they're expert judgements on real parts. Routing them back to the Layer 4 model store (as labelled examples with the original feature vectors) closes the loop between deployment and retraining. Without this, the ML layer stays static and the system never improves on your specific part corpus.
A few more structural notes worth locking in:
FreeCAD's 3D overlay is the tricky integration point. FreeCAD's viewport is Coin3D/OpenInventor, not a raw OpenGL surface — you can't just paste a PyVista render on top of it. The clean approach is to export the annotated scene as a SoSeparator node tree (Coin3D's scene graph format) and insert it as a child of FreeCAD's root scene node. This gives you native depth-correct overlay without a separate window.
Gradio vs Streamlit comes down to one question: do you need the file-upload-and-run interaction to be a single self-contained function call? If yes, Gradio's Interface model is a better fit — you define inputs (file upload) and outputs (viewer + table) and Gradio handles the plumbing. Streamlit gives you more layout control but requires more boilerplate for the async pipeline call pattern.
The headless surface is your integration test harness too. If the REST endpoint can accept a STEP file and return a structured JSON report, you can run it against a golden set of known parts in CI and catch regressions in check logic or model confidence before they reach designers.

## Usage

This layer provides three deployment surfaces for manufacturability analysis visualization:

### 1. Web UI (Streamlit)

The interactive web interface allows users to upload CAD files and view 3D manufacturability analysis results.

**Requirements:**
- Python 3.13+
- Streamlit
- PyVista
- stpyvista

**Installation:**
```bash
pip install streamlit pyvista stpyvista
```

**Running the Web UI:**
```bash
cd /path/to/Automated-Design-Evaluation-for-Manufacturability
streamlit run reporting/web_ui.py
```

**Features:**
- File upload for CAD models (STEP, STL, OBJ formats)
- Interactive 3D visualization with PyVista
- Real-time analysis results display
- Export options for annotated scenes
- Configurable visualization settings

### 2. Headless API (FastAPI)

The REST API provides programmatic access to manufacturability analysis for CI/CD pipelines and automated workflows.

**Requirements:**
- Python 3.13+
- FastAPI
- Uvicorn
- PyVista
- python-multipart

**Installation:**
```bash
pip install fastapi uvicorn pyvista python-multipart
```

**Running the API Server:**
```bash
cd /path/to/Automated-Design-Evaluation-for-Manufacturability
PYTHONPATH=/path/to/Automated-Design-Evaluation-for-Manufacturability python reporting/headless_api.py
```

**API Endpoints:**
- `POST /analyze` - Analyze a CAD file and return results
- `GET /health` - Health check endpoint

**Example API Usage:**
```python
import requests

# Analyze a CAD file
with open('part.step', 'rb') as f:
    response = requests.post('http://localhost:8000/analyze',
                           files={'file': f})
    results = response.json()
```

### 3. Annotation Engine

The core PyVista-based annotation engine creates 3D visualizations from analysis results.

**Requirements:**
- Python 3.13+
- PyVista

**Basic Usage:**
```python
from reporting.annotation_engine import AnnotationEngine, AnnotationConfig
from rules.rule_engine import CheckResult, Severity

# Create engine with default config
engine = AnnotationEngine()

# Create sample analysis results
results = [
    CheckResult(
        check_name="Wall Thickness",
        severity=Severity.FAIL,
        message="Wall too thin"
    )
]

# Load your mesh (PyVista PolyData)
import pyvista as pv
mesh = pv.read('part.stl')

# Create annotated scene
plotter = engine.create_annotated_scene(mesh, results)

# Export to different formats
engine.export_scene(plotter, 'output', 'png')  # Screenshot
engine.export_scene(plotter, 'output', 'vtk')  # Mesh with annotations
```

**Configuration Options:**
```python
config = AnnotationConfig(
    color_scheme='severity_gradient',
    show_measurements=True,
    show_labels=True,
    opacity=0.8
)
engine = AnnotationEngine(config)
```

### 4. FreeCAD Plugin

Integration with FreeCAD for in-process analysis within the CAD environment.

**Installation:**
- Copy `freecad_plugin.py` to your FreeCAD macros directory
- Ensure PyVista and other dependencies are available in FreeCAD's Python environment

**Usage:**
- Load the plugin in FreeCAD
- Access the "Manufacturability Analyzer" workbench
- Import CAD models and run analysis directly in FreeCAD

## Testing

Run the comprehensive test suite:

```bash
cd /path/to/Automated-Design-Evaluation-for-Manufacturability
python -m pytest tests/test_reporting_reporting.py -v
```

Tests include:
- Annotation engine functionality
- Export format validation
- Configuration options
- Full pipeline integration
- PyVista dependency handling