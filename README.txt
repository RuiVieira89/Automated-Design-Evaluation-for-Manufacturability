Project goals/layers


Layer 1 — CAD I/O

pythonocc-core (Python bindings for OpenCASCADE) — reads STEP, IGES, and B-Rep natively
ifcOpenShell — for BIM/IFC inputs common in industrial workflows
meshio — universal mesh format converter (STL, OBJ, VTK, etc.)

Layer 2 — Geometry Kernel

OpenCASCADE Technology (OCCT) — the industry-grade B-Rep kernel; handles topology queries, face classification, edge analysis, curvature computation
CGAL — best-in-class for computational geometry algorithms (convex hulls, Minkowski sums, mesh repair, exact arithmetic)
trimesh / Open3D — lighter-weight mesh analysis with good Python APIs; useful for wall thickness, ray casting, and accessibility checks
libigl — excellent for differential geometry on meshes (useful for sharp-feature detection)

Layer 3 — Rule Engine

Python rule modules that call into OCC/CGAL for each DfX check (min wall thickness, draft angles, undercuts, hole depth/diameter ratios, tool access cones)
networkx for modelling feature dependency graphs across an assembly
scipy.optimize for tolerance-stack constraint solving

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