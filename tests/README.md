# tests

Unit tests for all modules. Uses the standard `unittest` framework and is discovered automatically by `pytest`.

## Running tests

```bash
# All tests
python -m pytest tests/

# With verbose output
python -m pytest tests/ -v

# A specific test file
python -m pytest tests/test_step_reader.py
python -m pytest tests/test_shape_normalizer.py

# A single test class
python -m pytest tests/test_shape_normalizer.py::TestFaceAdjacency -v
```

> **Note:** Tests require `pythonocc-core`. If it is not installed the OCC-dependent test classes are automatically skipped with an informative message.

## Test files

### `test_step_reader.py`

Covers `load_cad.step_reader`:

| Test class | What is tested |
|---|---|
| `StepReaderTests` | `read_step` loads all sample STEP files without error; shapes are non-null |
| `ViewerTests` | `plot_cad_file` handles non-STEP formats (STL, OFF) — skipped if pyvista absent |

### `test_shape_normalizer.py`

Covers `post_process.shape_normalizer`:

| Test class | What is tested |
|---|---|
| `TestNormalizedShapeStructure` | Return type, solid/face count ≥ 1, zero-based sequential IDs, assembly context length, bare `TopoDS_Solid` input |
| `TestFaceAttributes` | Area > 0, valid surface-type strings, 3-tuple centre, plane normals present / curved normals absent, bounding-box min ≤ max |
| `TestFaceAdjacency` | Key completeness, symmetry, no self-loops, valid neighbour IDs, no duplicates, full graph connectivity |

## Environment

The `auto_eval_manuf` conda environment has all required dependencies:

```bash
conda activate auto_eval_manuf
python -m pytest tests/ -v
```
