"""
Example showing integration of Layers 1, 2, and 3.

Demonstrates the complete pipeline: I/O → Geometry Kernel → Rule Engine
"""

import sys
import os

# Add project root to path
project_root = os.path.dirname(__file__)
sys.path.insert(0, project_root)

from geometry import GeometryKernel, GeometryInputs
from rules import RuleEngine


def main():
    print("=" * 70)
    print("LAYER 1 → LAYER 2 → LAYER 3 INTEGRATION EXAMPLE")
    print("=" * 70)
    print()

    # --- LAYER 1: I/O ---
    print("LAYER 1: I/O")
    print("-" * 70)
    print("✓ IOManager: Reads STEP, STL, OBJ, VTK formats")
    print("✓ Normalizes to geometry objects (B-Rep or mesh)")
    print()

    # --- LAYER 2: GEOMETRY KERNEL ---
    print("LAYER 2: GEOMETRY KERNEL")
    print("-" * 70)
    geometry_kernel = GeometryKernel()
    print("✓ GeometryKernel initialized")
    print("  - B-Rep track: OCCT topology, curvature, Boolean ops")
    print("  - Mesh track: trimesh thickness, Open3D repair, libigl features")
    print("  - Tessellation: Configurable B-Rep → mesh conversion")
    print()

    # Create sample geometry input
    import numpy as np
    vertices = np.array([
        [0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0],  # base
        [0, 0, 10], [10, 0, 10], [10, 10, 10], [0, 10, 10]  # top
    ])
    faces = np.array([
        [0, 1, 2], [0, 2, 3],  # bottom
        [4, 5, 6], [4, 6, 7],  # top
        [0, 1, 5], [0, 5, 4],  # front
        [1, 2, 6], [1, 6, 5],  # right
        [2, 3, 7], [2, 7, 6],  # back
        [3, 0, 4], [3, 4, 7]   # left
    ])

    inputs = GeometryInputs(mesh_vertices=vertices, mesh_faces=faces)
    print(f"✓ Sample geometry created: {len(vertices)} vertices, {len(faces)} faces")
    print()

    # Process geometry
    geometry_results = geometry_kernel.process_geometry(inputs)
    print("✓ Geometry analysis complete:")
    print(f"  - Mesh results: thickness, accessibility, features")
    print(f"  - B-Rep results: (empty for mesh-only input)")
    print()

    # --- LAYER 3: RULE ENGINE ---
    print("LAYER 3: RULE ENGINE")
    print("-" * 70)
    rule_engine = RuleEngine()
    print("✓ RuleEngine initialized")
    print(f"  - Checks: {', '.join(rule_engine.registry.list_checks())}")
    print(f"  - Process profiles: injection_moulding, cnc_3axis, casting")
    print()

    # Prepare geometry data in format expected by rules
    geometry_data = {
        'brep_results': geometry_results.brep_results.__dict__,
        'mesh_results': {
            'thickness_analysis': geometry_results.mesh_results.thickness_analysis,
            'accessibility_checks': geometry_results.mesh_results.accessibility_checks,
            'feature_analysis': geometry_results.mesh_results.feature_analysis
        }
    }

    # Run analysis for injection moulding
    rule_engine.set_process('injection_moulding')
    print("Running DfX analysis for: INJECTION MOULDING")
    print()

    report = rule_engine.analyze(geometry_data)
    print(rule_engine.print_report(report))

    # Summary
    print()
    print("=" * 70)
    print("INTEGRATION SUMMARY")
    print("=" * 70)
    print(f"✓ Layer 1 (I/O):     Read formats, normalize to geometry objects")
    print(f"✓ Layer 2 (Geometry): Analyze B-Rep & mesh in parallel tracks")
    print(f"✓ Layer 3 (Rules):    Execute DfX checks with scheduling & tolerance solving")
    print()
    print(f"Overall Design Status: {report.overall_status.value.upper()}")
    print(f"Manufacturing Feasible: {'YES' if report.feasible else 'NO'}")
    print("=" * 70)


if __name__ == "__main__":
    main()