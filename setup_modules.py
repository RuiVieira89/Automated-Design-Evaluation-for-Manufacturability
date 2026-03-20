import subprocess
import sys

def install_modules():
    env_name = "auto_eval_manuf"
    
    # All libraries, now including open3d via conda
    packages = [
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
        "pythonocc-core"
    ]

    print(f"--- Configuring {env_name} for 3D Stack ---")

    try:
        # 1. Ensure the environment uses conda-forge strictly
        print("[1/3] Setting channel priorities...")
        subprocess.run(["conda", "config", "--env", "--add", "channels", "conda-forge"], check=True)
        subprocess.run(["conda", "config", "--env", "--set", "channel_priority", "strict"], check=True)

        # 2. Install all packages in one block (helps conda solve dependencies faster)
        print(f"[2/3] Installing packages into {env_name}...")
        subprocess.check_call([
            "conda", "install", "-y", "-n", env_name, *packages
        ])

        # 3. Final Verification
        print(f"[3/3] Verifying installation...")
        verification_cmd = "import open3d; import ifcopenshell; print('Stack loaded successfully!')"
        subprocess.run(["conda", "run", "-n", env_name, "python", "-c", verification_cmd], check=True)

        print("\n" + "="*40)
        print("Done! Everything is installed via Conda.")
        print("="*40)

    except subprocess.CalledProcessError as e:
        print(f"\nInstallation failed: {e}")

if __name__ == "__main__":

    install_modules()



    ## Tests Check if the libraries are installed and can be imported


    import trimesh
    import open3d as o3d
    import numpy as np

    import meshio
    import ifcopenshell
    import pyvista as pv
    from fastapi import FastAPI


    print(f"meshio version: {meshio.__version__}")

    # Check which formats are supported on your system
    print(f"Supported formats: {list(meshio.extension_to_filetypes.keys())[:5]}...")

    from OCC.Core.gp import gp_Pnt
    p = gp_Pnt(1.0, 2.0, 3.0)
    print(f"Point created at: {p.X()}, {p.Y()}, {p.Z()}")

    print(f"IfcOpenShell version: {ifcopenshell.version}")

    # Create a blank IFC file in memory to test
    model = ifcopenshell.file(schema="IFC4")
    print(f"Success! Created a new {model.schema} model.")



    # 1. Create a simple mesh in trimesh
    mesh = trimesh.creation.box()
    print(f"Trimesh Box Volume: {mesh.volume}")

    # 2. Convert Trimesh to Open3D format
    # We pass the vertices and faces to Open3D
    o3d_mesh = o3d.geometry.TriangleMesh()
    o3d_mesh.vertices = o3d.utility.Vector3dVector(mesh.vertices)
    o3d_mesh.triangles = o3d.utility.Vector3iVector(mesh.faces)

    # 3. Visualize in Open3D (This will open a window)
    print("Opening Open3D visualizer...")
    o3d_mesh.compute_vertex_normals()
    o3d.visualization.draw_geometries([o3d_mesh])



    # 1. Create a simple built-in mesh
    mesh = pv.Sphere()

    # 2. Add some data to it (like elevation)
    mesh["elevation"] = mesh.points[:, 2]

    # 3. Try to plot it
    # Note: This will open a native macOS window
    print("Attempting to open PyVista plotter...")
    plotter = pv.Plotter()
    plotter.add_mesh(mesh, scalars="elevation", cmap="viridis")
    plotter.show()



    app = FastAPI()

    @app.get("/")
    def read_root():
        return {"Status": "CAD API is Online", "Engine": "Trimesh/Open3D"}

    @app.get("/mesh_info")
    def get_mesh_info():
        # Create a dummy box to test 3D integration
        mesh = trimesh.creation.box(extents=[1, 1, 1])
        return {"volume": mesh.volume, "is_watertight": mesh.is_watertight}