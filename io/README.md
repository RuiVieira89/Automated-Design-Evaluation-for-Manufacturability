Format parsers (STEP)

Supported input formats:
STEP (.step, .stp) — via pythonocc-core

Output contracts
B-Rep path: OCC.TopoDS.Shape object. Passed to Layer 2.

Install
- Python dependency: pythonocc-core (OpenCASCADE bindings)
- System dependency: OpenCASCADE runtime libs (platform-specific)

Usage (basic)
```
from io.step_reader import read_step

shapes = read_step("data/simple_rib.step")
print(len(shapes))
```

Usage (tessellation)
```
from io.step_reader import read_step_single, tessellate_shape

shape = read_step_single("data/simple_rib.step")
vertices, faces = tessellate_shape(shape, deflection=0.1, angle=0.5)
print(len(vertices), len(faces))
```

Notes
- This repository uses an `io` package that shares its name with Python's stdlib `io` module.
	When running scripts, ensure the project root is on `PYTHONPATH` so local imports resolve.