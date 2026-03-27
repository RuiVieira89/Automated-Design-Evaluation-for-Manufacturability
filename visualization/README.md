# visualization — 3-D CAD Viewer

PyVista-based visualisation helpers. Supports both plain mesh rendering and labelled, colour-coded rendering of a `NormalizedShape` from the `post_process` layer.

## Dependencies

- `pyvista` — `pip install pyvista`
- `numpy`
- `pythonocc-core` (only for `plot_normalized_shape` / `build_labeled_meshes`)

## Surface-type colour palette

| Surface type | Colour |
|---|---|
| Plane | Blue `#4C72B0` |
| Cylinder | Orange `#DD8452` |
| Cone | Green `#55A868` |
| Sphere | Red `#C44E52` |
| Torus | Purple `#8172B3` |
| Bezier | Brown `#937860` |
| BSpline | Pink `#DA8BC3` |
| Other | Grey `#8C8C8C` |

## Public API

### `shape_to_pyvista(shape, deflection=0.1, angle=0.5) -> pv.PolyData`

Tessellates a `TopoDS_Shape` and returns a PyVista `PolyData` mesh.

```python
from load_cad.step_reader import read_step_single
from visualization.viewer import shape_to_pyvista

shape = read_step_single("data/simple_rib.step")
mesh = shape_to_pyvista(shape)
mesh.plot()
```

### `load_cad_file(path, deflection=0.1, angle=0.5) -> pv.DataSet`

Loads a CAD file into a PyVista dataset. STEP files are routed through `pythonocc-core`; all other formats are delegated to PyVista's native reader.

```python
from visualization.viewer import load_cad_file

mesh = load_cad_file("data/simple_rib.step")
mesh = load_cad_file("data/cube.off")   # non-STEP formats also supported
```

### `plot_cad_file(path, *, deflection=0.1, angle=0.5, off_screen=True, screenshot_path=None) -> pv.DataSet`

One-liner: load and display any CAD file as a plain grey mesh.

```python
from visualization.viewer import plot_cad_file

plot_cad_file("data/simple_rib.step", off_screen=False)
plot_cad_file("data/simple_rib.step", screenshot_path="out.png")
```

### `build_labeled_meshes(normalized_shape, solid_shapes, deflection=0.1, angle=0.5)`

Builds per-face PyVista meshes from a `NormalizedShape` together with its raw `TopoDS_Solid` list. Returns a 3-tuple:

- `face_meshes` — `List[pv.PolyData]`, one per successfully tessellated face
- `labels` — `List[str]`, `"S{solid_id} F{face_id}\n{surface_type}"` per face
- `centers` — `List[(x, y, z)]`, face centre-of-mass coordinates

```python
from post_process.shape_normalizer import normalize_shape, extract_solids
from visualization.viewer import build_labeled_meshes

compound = read_step_single("data/simple_rib.step")
result = normalize_shape(compound)
solids = extract_solids(compound)

meshes, labels, centers = build_labeled_meshes(result, solids)
```

### `plot_normalized_shape(normalized_shape, solid_shapes, *, ...)`

Full labelled render. Each face is individually tessellated, coloured by surface type, and optionally annotated with a text label (`"S{solid_id} F{face_id}\n{type}"`). A colour-type legend is always shown.

**Parameters:**

| Parameter | Default | Description |
|---|---|---|
| `normalized_shape` | — | `NormalizedShape` from `normalize_shape()` |
| `solid_shapes` | — | `List[TopoDS_Solid]` from `extract_solids()` |
| `deflection` | `0.1` | Linear tessellation deflection |
| `angle` | `0.5` | Angular tessellation deflection |
| `show_labels` | `True` | Show `"S# F# / type"` text labels at face centres |
| `show_edges` | `True` | Render face edges as wireframe overlay |
| `off_screen` | `False` | Render without opening a window (for screenshots) |
| `screenshot_path` | `None` | Save render to this file path |
| `window_size` | `(1400, 900)` | Window dimensions in pixels |

```python
from load_cad.step_reader import read_step_single
from post_process.shape_normalizer import normalize_shape, extract_solids
from visualization.viewer import plot_normalized_shape

compound = read_step_single("data/escavator_arm-Assembly.step")
result = normalize_shape(compound)
solids = extract_solids(compound)

# Interactive window
plot_normalized_shape(result, solids)

# Off-screen screenshot, no labels
plot_normalized_shape(result, solids, show_labels=False, off_screen=True, screenshot_path="out.png")
```

## CLI example

The `examples/normalize_shape.py` script exposes the full visualisation pipeline:

```bash
# Interactive labelled view
python examples/normalize_shape.py data/simple_rib.step --visualize

# No labels
python examples/normalize_shape.py data/simple_rib.step --visualize --no-labels

# Save screenshot (off-screen)
python examples/normalize_shape.py data/escavator_arm-Assembly.step --visualize --screenshot out.png

# Plain mesh viewer (all sample STEP files)
python examples/view_steps.py
```
