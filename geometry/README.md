Thickness computation, MAT, ray casting — pure functions

see geometry/geometry_kernel_layer2.svg

The key structural decision in this layer is that two parallel tracks emerge and need to stay separate until Layer 3 explicitly merges them.
The B-Rep track (left) stays in OCCT the whole time. OCCT is both the kernel that underpins pythonocc-core in Layer 1 and the engine you query here — so there's no serialisation cost. You're running topology walkers, surface analysers, and Boolean operations directly on the same in-memory solid. CGAL plugs in alongside it when you need algorithms OCCT doesn't do well, like robust mesh repair with exact arithmetic guarantees — but CGAL receives a tessellated copy of the B-Rep, not the original.
The mesh track (right) is where trimesh, Open3D, and libigl live. These three share data almost for free: all of them speak numpy (V, F) arrays, so passing a mesh from trimesh into libigl is a single array hand-off, no conversion. The practical split is by task — trimesh for physical checks (thickness, ray casting, watertightness), Open3D when you have point clouds or need ICP/voxelisation, libigl when you need differential operators (Laplacian, geodesics, sharp-feature dihedral angles) or parameterisation.
The dashed cross-track arrows represent the one crossing you'll do frequently: tessellating a B-Rep from OCCT to hand off to the mesh side. This is lossy (you lose exact surface parametrisation), so the decision of when to cross — and at what chord tolerance — matters. Keeping the tessellation step explicit and configurable is worth architecting in early.
The two output buses feed Layer 3 separately, which is intentional: feature extraction and manufacturability analysis will likely query both — exact face counts and draft angles from the B-Rep side, wall thickness histograms and sharp-feature maps from the mesh side.

## Implementation

The geometry kernel is implemented as a Python package with the following modules:

- `geometry_kernel.py`: Main orchestrator for the two parallel tracks
- `brep_kernel.py`: B-Rep operations using pythonocc-core (OCCT)
- `mesh_kernel.py`: Mesh operations using trimesh, Open3D, and compas_libigl
- `tessellation.py`: B-Rep to mesh conversion with configurable tolerances

### Usage

```python
from geometry import GeometryKernel, GeometryInputs

# Create kernel
kernel = GeometryKernel()

# Prepare inputs (from Layer 1)
inputs = GeometryInputs(
    brep_shape=occ_shape,  # From pythonocc-core
    mesh_vertices=V,       # Or provide mesh directly
    mesh_faces=F
)

# Process geometry
results = kernel.process_geometry(inputs)

# Access separate results
brep_data = results.brep_results.topology_info
mesh_data = results.mesh_results.thickness_analysis
```

### Dependencies

- pythonocc-core: B-Rep operations
- trimesh: Mesh analysis and ray casting
- open3d: Mesh repair and point cloud operations
- compas_libigl: Differential geometry on meshes
- numpy: Array operations