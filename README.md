# Automated Design Evaluation for Manufacturability

A Python toolkit that loads CAD files (STEP format), normalises their topology into structured data, and visualises labelled geometry for design-for-manufacturability (DfM) analysis.

---

## Repository layout

```
load_cad/       STEP file reader — produces TopoDS_Shape objects
post_process/   Shape normalisation layer — extracts solids, faces, adjacency
visualization/  3-D viewer — colour-coded, labelled PyVista rendering
examples/       Runnable scripts demonstrating each layer
tests/          Unit tests for all modules
data/           Sample STEP / STL / OFF files
```

---

## Installation

### Prerequisites

| Dependency | Purpose | Install |
|---|---|---|
| `pythonocc-core` | OpenCASCADE Python bindings | `conda install -c conda-forge pythonocc-core` |
| `pyvista` | 3-D visualisation | `pip install pyvista` |

The recommended approach is a dedicated conda environment:

```bash
conda create -n auto_eval_manuf python=3.11
conda activate auto_eval_manuf
conda install -c conda-forge pythonocc-core
pip install pyvista
```

Or install all Python requirements at once (requires `pythonocc-core` to already be available via conda):

```bash
pip install -r requirements.txt
```

---

## Quick start

All example scripts can be run from the repository root.

### 1 — Load a STEP file

```bash
python examples/load_step.py data/simple_rib.step
python examples/load_step.py data/simple_rib.step --tessellate
python examples/load_step.py data/escavator_arm-Assembly.step --single --tessellate
```

### 2 — Visualise a CAD file (raw mesh)

```bash
python examples/view_steps.py
```

### 3 — Normalise and inspect topology

```bash
# Summary (solid count, surface-type histogram, adjacency stats)
python examples/normalize_shape.py data/simple_rib.step

# Per-face detail (area, centre, normal, neighbours)
python examples/normalize_shape.py data/simple_rib.step --verbose

# Assembly hierarchy context
python examples/normalize_shape.py data/escavator_arm-Assembly.step --context
```

### 4 — Labelled 3-D visualisation

```bash
# Interactive window
python examples/normalize_shape.py data/simple_rib.step --visualize

# Save a screenshot (off-screen, no window required)
python examples/normalize_shape.py data/simple_rib.step --visualize --screenshot out.png

# Hide labels
python examples/normalize_shape.py data/simple_rib.step --visualize --no-labels

# Assembly with context + visualization
python examples/normalize_shape.py data/escavator_arm-Assembly.step --context --visualize
```

### 5 — Run the tests

```bash
python -m pytest tests/
```

---

## Module overview

| Module | Entry point | Description |
|---|---|---|
| `load_cad` | `read_step`, `read_step_single` | Parse STEP → `TopoDS_Shape` |
| `load_cad` | `tessellate_shape` | Triangulate any `TopoDS_Shape` |
| `post_process` | `normalize_shape` | `TopoDS_Shape` → `NormalizedShape` |
| `post_process` | `extract_solids` | List of raw `TopoDS_Solid` objects |
| `visualization` | `plot_normalized_shape` | Labelled 3-D render |
| `visualization` | `plot_cad_file` | Simple mesh render of any CAD file |
| `visualization` | `build_labeled_meshes` | Per-face PyVista meshes + label data |

See each module's `README.md` for detailed API documentation.
