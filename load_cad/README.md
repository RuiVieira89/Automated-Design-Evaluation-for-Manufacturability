# load_cad — STEP File Reader

Loads STEP files via **pythonocc-core** (OpenCASCADE Python bindings) and produces `TopoDS_Shape` objects consumed by the `post_process` layer.

## Supported formats

| Format | Extension | Backend |
|---|---|---|
| STEP | `.step`, `.stp` | pythonocc-core (`STEPControl_Reader`) |

## Dependencies

- `pythonocc-core` — `conda install -c conda-forge pythonocc-core`

## Public API

### `read_step(path) -> List[TopoDS_Shape]`

Returns every top-level shape transferred from the STEP file.

```python
from load_cad.step_reader import read_step

shapes = read_step("data/simple_rib.step")
print(len(shapes))  # 1
```

### `read_step_single(path) -> TopoDS_Shape`

Like `read_step`, but returns a single shape. If the file has multiple roots they are merged into a `TopoDS_Compound`.

```python
from load_cad.step_reader import read_step_single

shape = read_step_single("data/escavator_arm-Assembly.step")
```

### `tessellate_shape(shape, deflection=0.1, angle=0.5) -> (vertices, faces)`

Triangulates a `TopoDS_Shape` using `BRepMesh_IncrementalMesh`. Returns:
- `vertices` — `List[Tuple[float, float, float]]` of `(x, y, z)` coordinates
- `faces` — `List[Tuple[int, int, int]]` of 0-based triangle indices

```python
from load_cad.step_reader import read_step_single, tessellate_shape

shape = read_step_single("data/simple_rib.step")
vertices, faces = tessellate_shape(shape, deflection=0.05, angle=0.3)
print(f"{len(vertices)} vertices, {len(faces)} triangles")
```

Smaller `deflection` and `angle` values produce a finer mesh at the cost of speed.

### `StepReadError`

Raised when a file cannot be read or no shapes are transferred.

## CLI example

```bash
# Load and print shape count
python examples/load_step.py data/simple_rib.step

# Load as a single compound + tessellate
python examples/load_step.py data/escavator_arm-Assembly.step --single --tessellate

# Custom mesh quality
python examples/load_step.py data/simple_rib.step --tessellate --deflection 0.05 --angle 0.3
```

## Notes

- Module name is `load_cad` to avoid shadowing the Python stdlib `io` module.
- `read_step` preserves multiple top-level shapes; `read_step_single` is
  convenient when downstream code expects exactly one shape object.
