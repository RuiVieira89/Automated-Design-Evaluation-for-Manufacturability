"""
Test the geometry kernel implementation.
"""

import numpy as np
import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

def test_geometry_kernel_import():
    """Test that the geometry kernel can be imported."""
    try:
        from geometry import GeometryKernel, GeometryInputs
        print("✓ Geometry kernel imported successfully")
        return True
    except ImportError as e:
        print(f"✗ Import failed: {e}")
        return False

def test_mesh_kernel():
    """Test mesh kernel with a simple cube mesh."""
    try:
        from geometry import MeshKernel

        # Create a simple cube mesh
        vertices = np.array([
            [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],  # bottom
            [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]   # top
        ])
        faces = np.array([
            [0, 1, 2], [0, 2, 3],  # bottom
            [4, 5, 6], [4, 6, 7],  # top
            [0, 1, 5], [0, 5, 4],  # front
            [1, 2, 6], [1, 6, 5],  # right
            [2, 3, 7], [2, 7, 6],  # back
            [3, 0, 4], [3, 4, 7]   # left
        ])

        kernel = MeshKernel()

        # Test thickness analysis
        thickness = kernel.analyze_thickness(vertices, faces)
        print(f"✓ Thickness analysis: {thickness}")

        # Test accessibility
        accessibility = kernel.check_accessibility(vertices, faces)
        print(f"✓ Accessibility check: {accessibility}")

        return True
    except Exception as e:
        print(f"✗ Mesh kernel test failed: {e}")
        return False

def test_brep_kernel():
    """Test B-Rep kernel (requires pythonocc-core)."""
    try:
        from geometry import BRepKernel
        kernel = BRepKernel()
        print("✓ B-Rep kernel initialized")
        return True
    except Exception as e:
        print(f"✗ B-Rep kernel test failed: {e}")
        return False

def test_tessellation():
    """Test tessellation engine."""
    try:
        from geometry import TessellationEngine
        engine = TessellationEngine()
        print("✓ Tessellation engine initialized")
        return True
    except Exception as e:
        print(f"✗ Tessellation test failed: {e}")
        return False

if __name__ == "__main__":
    print("Testing Geometry Kernel Implementation")
    print("=" * 40)

    tests = [
        test_geometry_kernel_import,
        test_mesh_kernel,
        test_brep_kernel,
        test_tessellation
    ]

    passed = 0
    for test in tests:
        if test():
            passed += 1
        print()

    print(f"Results: {passed}/{len(tests)} tests passed")