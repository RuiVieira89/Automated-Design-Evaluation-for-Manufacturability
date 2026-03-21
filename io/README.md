Format parsers (STEP, STL, OBJ) — one adapter per format

The three libraries sit in parallel columns, each owning a distinct input family, and all click through if you want to drill into any node.

see cad_io_layer1_structure.svg

A few structural decisions worth calling out:
Each library is sovereign over its format. pythonocc-core handles anything OpenCASCADE speaks (STEP, IGES, native B-Rep). ifcOpenShell owns the IFC/BIM path and is the only one that preserves semantic metadata (room names, material properties, element hierarchy). meshio handles every discretised/tessellated format and is format-agnostic by design.
The dashed cross-library arrow matters. pythonocc-core can tessellate a B-Rep into a mesh, at which point meshio takes over for normalisation and re-export. This is your escape hatch when downstream code expects points + cells arrays rather than topological B-Rep objects. ifcOpenShell similarly tessellates internally before handing off.
The unified handoff is the contract. Layer 2 (processing/analysis) shouldn't care which library produced the geometry — it should receive either a B-Rep object (for exact geometry operations like Boolean ops, offsets, drafting analysis) or a numpy-backed mesh (for FEM, rendering, ML). Deciding which representation Layer 2 expects is the main architectural choice this layer forces you to make early.