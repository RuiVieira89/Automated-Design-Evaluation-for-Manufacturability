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
from load_cad.step_reader import read_step

shapes = read_step("data/simple_rib.step")
print(len(shapes))
```

Usage (tessellation)
```
from load_cad.step_reader import read_step_single, tessellate_shape

shape = read_step_single("data/simple_rib.step")
vertices, faces = tessellate_shape(shape, deflection=0.1, angle=0.5)
print(len(vertices), len(faces))
```

Notes
- The module is now named `load_cad` to avoid clashing with Python's stdlib `io` module.