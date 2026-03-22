Project goals/layers


Layer 1 — CAD I/O

pythonocc-core (Python bindings for OpenCASCADE) — reads STEP, IGES, and B-Rep natively
ifcOpenShell — for BIM/IFC inputs common in industrial workflows
meshio — universal mesh format converter (STL, OBJ, VTK, etc.)

Layer 2 — Geometry Kernel ✓ IMPLEMENTED

OpenCASCADE Technology (OCCT) — the industry-grade B-Rep kernel; handles topology queries, face classification, edge analysis, curvature computation
CGAL — best-in-class for computational geometry algorithms (convex hulls, Minkowski sums, mesh repair, exact arithmetic)
trimesh / Open3D — lighter-weight mesh analysis with good Python APIs; useful for wall thickness, ray casting, and accessibility checks
libigl — excellent for differential geometry on meshes (useful for sharp-feature detection)

Implementation: geometry/ package with separate B-Rep and mesh tracks, tessellation engine for B-Rep→mesh conversion

Layer 3 — Rule Engine ✓ IMPLEMENTED

Python rule modules that call into OCC/CGAL for each DfX check (min wall thickness, draft angles, undercuts, hole depth/diameter ratios, tool access cones)
networkx for modelling feature dependency graphs across an assembly
scipy.optimize for tolerance-stack constraint solving

Implementation: rules/ package with DfxCheck base class, concrete checks, rule registry, param store, dependency graph scheduler, and tolerance solver

Layer 4 — ML / Context-Aware Reasoning

PyTorch Geometric — graph neural networks on B-Rep or mesh feature graphs; enables process-aware classification (e.g. "this feature is machinable on a 3-axis but not 2-axis mill")
PointNet++ — point-cloud-based feature recognition
ONNX Runtime — deploy trained models without framework overhead

Layer 5 — Visualization & Feedback

PyVista / VTK — annotate the 3D mesh with colored violation regions, arrows, and measurement overlays
FreeCAD (as a plugin host) — lets you embed the tool directly into a CAD environment designers already use
Gradio or Streamlit — fast path to a web UI for review and iteration

Layer 6 — Orchestration

FastAPI — expose rule evaluation as a REST service (enables CAD plugin integration)
Prefect or Airflow — pipeline orchestration for batch evaluation across large assemblies
Celery + Redis — for async job queuing when evaluating complex geometries

Recommended starting point: pythonocc-core + trimesh for geometry, a custom rule engine in Python, PyVista for visualization, and FastAPI to wire it together. That gives you a working prototype with the fewest integration hurdles.

Project structure
├── io/            # format parsers (STEP, STL, OBJ) — one adapter per format ✓
├── geometry/      # B-Rep & mesh geometry kernel with separate analysis tracks ✓
├── rules/         # DfX rule engine with dependency scheduling & tolerance solving ✓
├── segmentation/  # feature detection (base, rib, fin)
├── reporting/     # heatmap generation, JSON/PDF export
├── config/        # process profiles (injection moulding, casting, machining)
└── tests/         # unit + integration tests with reference geometries


## How to Use This Project for Design Evaluation

This project provides automated manufacturability analysis for CAD models. 
You can evaluate single parts or assemblies for manufacturing issues using the REST API.

### Prerequisites

- Python 3.13+
- Redis server (for job queuing)
- CAD files in supported formats: STEP, IGES, STL, OBJ, IFC

### Quick Start

1. **Activate the environment:**
   ```bash
   conda activate auto_eval_manuf
   ```

2. **Start Redis server:**
   ```bash
   redis-server
   ```

3. **Start the FastAPI server:**
   ```bash
   cd synchronous_request_plane_FastAPI
   python fastapi_app.py
   ```
   The API will be available at `http://localhost:8000`

4. **Submit a CAD file for analysis:**
   ```bash
   curl -X POST "http://localhost:8000/analyze" \
     -F "file=@your_part.stl" \
     -F "process_type=single"
   ```
   Response:
   ```json
   {
     "job_id": "uuid-string",
     "status": "accepted",
     "message": "Analysis job submitted successfully",
     "poll_url": "/job/uuid-string"
   }
   ```

### API Endpoints

- `GET /health` - Check if the service is running
- `POST /analyze` - Submit a CAD file for analysis
  - Parameters: `file` (upload), `process_type` ("single" or "assembly")
  - Returns: Job ID for status polling
- `GET /job/{job_id}` - Check analysis status and results
- `DELETE /job/{job_id}` - Cancel a running analysis job

### Supported File Formats

- **STEP/IGES**: Native B-Rep geometry (recommended for precision)
- **STL/OBJ/VTK**: Mesh formats
- **IFC**: BIM/IFC files for industrial workflows

### Analysis Results

The system evaluates designs for:
- Wall thickness violations
- Draft angle issues
- Undercut detection
- Hole ratio problems
- Tool access constraints
- Material-specific recommendations

Results include:
- Violation reports with severity levels
- ML-based process recommendations
- 3D visualizations with annotated issues
- Manufacturability scores

### Testing the System

Run the test suite to verify everything is working:

```bash
# Test the FastAPI orchestration layer
python -m pytest tests/test_orchestration_fastapi.py -v

# Test the Prefect workflows
python -m pytest tests/test_orchestration_prefect.py -v

# Test individual components
python -m pytest tests/test_geometry_kernel.py -v
python -m pytest tests/test_rules_engine.py -v

# Test all
python -m pytest tests/ --ignore=tests/test_open3D.py --ignore=tests/test_pkg_install.cpp
```

### Architecture Overview

This system uses a layered architecture:

- **Layer 1 (I/O)**: Loads CAD files in various formats (STEP, STL, IFC, etc.)
- **Layer 2 (Geometry)**: Analyzes 3D geometry using B-Rep and mesh processing
- **Layer 3 (Rules)**: Applies manufacturing rules and constraints
- **Layer 4 (ML)**: Provides intelligent process recommendations
- **Layer 5 (Visualization)**: Generates annotated 3D views of issues
- **Layer 6 (Orchestration)**: Manages job queuing and API serving

### Integration Options

- **CAD Plugin**: Integrate with FreeCAD for in-CAD analysis
- **Web UI**: Use the included web interface for review
- **CI/CD**: Automate design checks in your development pipeline
- **API**: Build custom integrations using the REST API


CPP installed CGAL, igl, Eigen

Python packages installed
        "trimesh",
        "open3d",       # Installed via conda-forge
        "meshio",
        "ifcopenshell",
        "lark",         # Fixes 'no stream support'
        "scipy",
        "networkx",
        "numpy",
        "pyvista",
        "pandas",
        "matplotlib",
        "fastapi",

I'm usiong conda-forge


conda activate auto_eval_manuf

# Force the modern Intel Iris driver
conda env config vars set MESA_LOADER_DRIVER_OVERRIDE=iris

# Force X11 compatibility (XWayland) for the GUI
conda env config vars set QT_QPA_PLATFORM=xcb

# Use the system C++ library to prevent Segmentation Faults on Ubuntu 24.04
conda env config vars set LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libstdc++.so.6

# Reactivate to apply these changes
conda deactivate && conda activate auto_eval_manuf
