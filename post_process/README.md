# post_process — Shape Normalisation Layer

Converts a `TopoDS_Shape` (typically a `TopoDS_Compound` loaded from a STEP file) into a structured `NormalizedShape` containing per-solid face data and a face-adjacency graph.

## Topology hierarchy traversed

```
TopoDS_Compound
  └─ TopoDS_CompSolid  (optional)
      └─ TopoDS_Solid
          └─ TopoDS_Shell
              └─ TopoDS_Face
                  └─ TopoDS_Wire
                      └─ TopoDS_Edge
```

Shapes at the SHELL / WIRE / EDGE / VERTEX level that have no solid parent (wireframe-only or construction-only geometry) are silently ignored.

## Dependencies

- `pythonocc-core` — `conda install -c conda-forge pythonocc-core`

## Data model

### `FaceData`

Attributes computed for a single face:

| Field | Type | Description |
|---|---|---|
| `face_id` | `int` | Zero-based index within the parent solid |
| `surface_type` | `str` | `"Plane"`, `"Cylinder"`, `"Cone"`, `"Sphere"`, `"Torus"`, `"Bezier"`, `"BSpline"`, or `"Other"` |
| `area` | `float` | Surface area |
| `center` | `(x, y, z)` | Centre of mass |
| `normal` | `(nx, ny, nz)` \| `None` | Unit normal (planar faces only) |
| `bounding_box` | `(xmin, ymin, zmin, xmax, ymax, zmax)` | Axis-aligned bounding box |

### `SolidData`

| Field | Type | Description |
|---|---|---|
| `solid_id` | `int` | Zero-based index within the `NormalizedShape` |
| `faces` | `List[FaceData]` | Ordered face list |
| `adjacency` | `Dict[int, List[int]]` | Face → list of face IDs sharing an edge |

### `AssemblyNode`

| Field | Type | Description |
|---|---|---|
| `solid_id` | `int` | Index into `NormalizedShape.solids` |
| `path` | `Tuple[int, ...]` | Child-index path from root compound to the solid |

### `NormalizedShape`

| Field | Type | Description |
|---|---|---|
| `solids` | `List[SolidData]` | All extracted solids in depth-first order |
| `assembly_context` | `List[AssemblyNode]` \| `None` | Present only when `keep_context=True` |

## Public API

### `normalize_shape(compound, keep_context=False) -> NormalizedShape`

Main entry point. Accepts any `TopoDS_Shape` (compound, solid, etc.).

```python
from load_cad.step_reader import read_step_single
from post_process.shape_normalizer import normalize_shape

compound = read_step_single("data/simple_rib.step")
result = normalize_shape(compound)

for solid in result.solids:
    print(f"Solid {solid.solid_id}: {len(solid.faces)} faces")
    for face in solid.faces:
        print(f"  Face {face.face_id}: {face.surface_type}, area={face.area:.3f}")
```

With assembly context:

```python
result = normalize_shape(compound, keep_context=True)
for node in result.assembly_context:
    print(f"Solid {node.solid_id} at path {node.path}")
```

### `extract_solids(compound) -> List[TopoDS_Solid]`

Returns the raw `TopoDS_Solid` objects in the same order as `normalize_shape`. Useful when you need both normalised metadata **and** the OCC solids (e.g. for per-face tessellation in the visualisation layer).

```python
from post_process.shape_normalizer import extract_solids

solids = extract_solids(compound)
```

## CLI example

```bash
# Default summary
python examples/normalize_shape.py data/simple_rib.step

# Per-face detail
python examples/normalize_shape.py data/simple_rib.step --verbose

# Assembly hierarchy
python examples/normalize_shape.py data/escavator_arm-Assembly.step --context

# Verbose + assembly
python examples/normalize_shape.py data/escavator_arm-Assembly.step --context --verbose
```
