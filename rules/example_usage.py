"""
Example usage of the Rule Engine.

Demonstrates DfX analysis with different manufacturing processes.
"""

import sys
import os

# Add project root to path
project_root = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, project_root)

from rules import RuleEngine


def create_sample_geometry_data():
    """Create sample geometry data from Layer 2."""
    return {
        'brep_results': {
            'topology_info': {
                'face_count': 12,
                'edge_count': 30,
                'vertex_count': 8
            },
            'curvature_data': {}
        },
        'mesh_results': {
            'thickness_analysis': {
                'min_thickness': 1.8,  # mm
                'max_thickness': 4.2,
                'mean_thickness': 2.8,
                'thickness_histogram': ([], [])
            },
            'accessibility_checks': {
                'is_watertight': True,
                'volume': 125.5,
                'surface_area': 250.0
            },
            'feature_analysis': {}
        }
    }


def main():
    print("Rule Engine Example")
    print("=" * 60)

    # Create engine
    engine = RuleEngine()
    print("✓ Rule engine initialized")
    print(f"✓ Registered checks: {', '.join(engine.registry.list_checks())}")
    print()

    # Show dependency information
    print("Dependency Graph:")
    print("-" * 60)
    print(engine.get_dependency_info())
    print()

    # Create sample geometry
    geometry_data = create_sample_geometry_data()
    print("Sample Geometry Data:")
    print(f"  Min wall thickness: {geometry_data['mesh_results']['thickness_analysis']['min_thickness']}mm")
    print()

    # Analyze with different processes
    processes = ['injection_moulding', 'cnc_3axis', 'casting']

    for process in processes:
        print("=" * 60)
        print(f"Analysis for: {process.upper()}")
        print("=" * 60)

        engine.set_process(process)
        report = engine.analyze(geometry_data)

        print(engine.print_report(report))
        print()


if __name__ == "__main__":
    main()