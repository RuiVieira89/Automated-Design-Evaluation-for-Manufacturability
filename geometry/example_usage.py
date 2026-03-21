"""
Example usage of the Geometry Kernel.

This script demonstrates how to use the geometry kernel to process
both B-Rep and mesh geometry with separate analysis tracks.
"""

import numpy as np
import sys
import os

# Add project root to path
project_root = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, project_root)

from geometry import GeometryKernel, GeometryInputs

def create_sample_mesh():
    """Create a simple cube mesh for demonstration."""
    # Cube vertices
    vertices = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],  # bottom
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]   # top
    ])

    # Cube faces
    faces = np.array([
        [0, 1, 2], [0, 2, 3],  # bottom
        [4, 5, 6], [4, 6, 7],  # top
        [0, 1, 5], [0, 5, 4],  # front
        [1, 2, 6], [1, 6, 5],  # right
        [2, 3, 7], [2, 7, 6],  # back
        [3, 0, 4], [3, 4, 7]   # left
    ])

    return vertices, faces

def main():
    print("Geometry Kernel Example")
    print("=" * 40)

    # Create geometry kernel
    kernel = GeometryKernel()
    print("✓ Geometry kernel initialized")

    # Create sample mesh input
    vertices, faces = create_sample_mesh()
    print(f"✓ Created sample mesh: {len(vertices)} vertices, {len(faces)} faces")

    # Prepare inputs (mesh-only for this example)
    inputs = GeometryInputs(
        brep_shape=None,  # No B-Rep input
        mesh_vertices=vertices,
        mesh_faces=faces
    )

    # Process geometry
    print("\nProcessing geometry...")
    results = kernel.process_geometry(inputs)

    # Display results
    print("\nB-Rep Results (empty, no B-Rep input):")
    print(f"  Topology: {results.brep_results.topology_info}")
    print(f"  Curvature: {results.brep_results.curvature_data}")

    print("\nMesh Results:")
    print(f"  Thickness analysis: {results.mesh_results.thickness_analysis}")
    print(f"  Accessibility: {results.mesh_results.accessibility_checks}")
    print(f"  Features: {results.mesh_results.feature_analysis}")

    print("\n✓ Geometry processing complete!")

if __name__ == "__main__":
    main()