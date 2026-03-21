import open3d as o3d
import time

# 1. Initialize the Web Visualizer BEFORE creating the geometry
# This ensures the server is ready to 'receive' the mesh
o3d.visualization.webrtc_server.enable_webrtc()

# 2. Create a high-detail mesh (using the new T-geometry for 0.19.0)
mesh = o3d.geometry.TriangleMesh.create_sphere(radius=1.0)
mesh.compute_vertex_normals()

print("--- Open3D WebRTC Server Active ---")
print("1. Refresh http://127.0.0.1:8888 in Chrome/Firefox")
print("2. You should see a 'Main Window' in the browser list")
print("3. Click it to view and rotate the sphere")
print("-----------------------------------")

# 3. Launch the visualizer in 'non-blocking' mode
# This keeps the Python process alive while the browser interacts
o3d.visualization.draw(mesh, 
                       title="Interactive CAD View", 
                       width=800, 
                       height=600, 
                       show_ui=True)

# Important: Keep the script from exiting
try:
    while True:
        # This allows the background server to process mouse movements from the browser
        time.sleep(0.1) 
except KeyboardInterrupt:
    print("Shutting down...")

    