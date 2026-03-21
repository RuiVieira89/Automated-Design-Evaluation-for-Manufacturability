"""
Test the rule engine implementation.
"""

import sys
import os
from typing import Dict, Any

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

def test_rule_engine_import():
    """Test that rule engine can be imported."""
    try:
        from rules import RuleEngine, CheckResult, Severity
        print("✓ Rule engine imported successfully")
        return True
    except ImportError as e:
        print(f"✗ Import failed: {e}")
        return False

def test_param_store():
    """Test parameter store."""
    try:
        from rules import ParamStore

        store = ParamStore()
        assert store.current_process == 'injection_moulding'

        # Get parameters
        params = store.get_params()
        assert params.min_wall_thickness == 2.0

        # Switch process
        store.select_process('cnc_3axis')
        params = store.get_params()
        assert params.min_wall_thickness == 1.0

        # Set parameter
        store.set_param('min_wall_thickness', 1.5)
        assert store.get_param('min_wall_thickness') == 1.5

        print("✓ Parameter store works correctly")
        return True
    except Exception as e:
        print(f"✗ Parameter store test failed: {e}")
        return False

def test_rule_registry():
    """Test rule registry."""
    try:
        from rules import RuleRegistry, WallThicknessCheck

        registry = RuleRegistry()
        registry.register('test_check', WallThicknessCheck)

        assert registry.is_registered('test_check')
        assert 'test_check' in registry.list_checks()

        # Instantiate
        check = registry.instantiate('test_check')
        assert check.name == 'test_check'

        print("✓ Rule registry works correctly")
        return True
    except Exception as e:
        print(f"✗ Rule registry test failed: {e}")
        return False

def test_dependency_graph():
    """Test dependency graph and scheduling."""
    try:
        from rules import DependencyGraph, CheckScheduler

        graph = DependencyGraph()
        graph.add_node('check_a', node_type='check')
        graph.add_node('check_b', node_type='check')
        graph.add_node('check_c', node_type='check')

        # a → b → c
        graph.add_edge('check_a', 'check_b', reason='dependency')
        graph.add_edge('check_b', 'check_c', reason='dependency')

        order = graph.get_execution_order()
        assert order == ['check_a', 'check_b', 'check_c']

        # Test cascading failures
        scheduler = CheckScheduler(graph)
        assert scheduler.should_run('check_a')
        
        scheduler.mark_failed('check_a')
        assert not scheduler.should_run('check_b')
        assert not scheduler.should_run('check_c')

        print("✓ Dependency graph and scheduling work correctly")
        return True
    except Exception as e:
        print(f"✗ Dependency graph test failed: {e}")
        return False

def test_checks():
    """Test concrete check implementations."""
    try:
        from rules import WallThicknessCheck, Severity

        # Create dummy geometry data
        geometry_data = {
            'mesh_results': {
                'thickness_analysis': {
                    'min_thickness': 2.5,
                    'max_thickness': 3.0,
                    'mean_thickness': 2.7
                }
            }
        }

        params = {'min_wall_thickness': 2.0}

        # Run check
        check = WallThicknessCheck('wall_thickness')
        result = check.run(geometry_data, params)

        assert result.severity == Severity.PASS
        assert result.measured_value == 2.5
        assert result.margin == 0.5

        print("✓ Concrete checks work correctly")
        return True
    except Exception as e:
        print(f"✗ Checks test failed: {e}")
        return False

def test_tolerance_solver():
    """Test tolerance solver."""
    try:
        from rules import ToleranceSolver

        solver = ToleranceSolver()
        
        # Add some constraint results
        solver.add_check_result('wall_thickness', 0.5, 2.5, 2.0)
        solver.add_check_result('draft_angle', 0.3, 1.5, 1.2)
        solver.add_check_result('hole_ratio', -0.2, 10.2, 10.0)

        # Check feasibility
        feasibility = solver.check_feasibility()
        assert not feasibility['feasible']  # One check has negative margin
        assert feasibility['worst_case_margin'] == -0.2

        print("✓ Tolerance solver works correctly")
        return True
    except Exception as e:
        print(f"✗ Tolerance solver test failed: {e}")
        return False

def test_rule_engine_integration():
    """Test complete rule engine integration."""
    try:
        from rules import RuleEngine

        engine = RuleEngine()
        
        # Check that standard checks are registered
        checks = engine.registry.list_checks()
        assert 'wall_thickness' in checks
        assert 'draft_angle' in checks

        # Create minimal geometry data
        geometry_data = {
            'brep_results': {},
            'mesh_results': {
                'thickness_analysis': {
                    'min_thickness': 2.5,
                    'max_thickness': 3.0,
                    'mean_thickness': 2.7
                }
            }
        }

        # Run analysis
        report = engine.analyze(geometry_data, checks_to_run=['wall_thickness'])
        
        assert len(report.check_results) > 0
        assert report.overall_status is not None

        # Print report
        report_text = engine.print_report(report)
        assert 'wall_thickness' in report_text

        print("✓ Rule engine integration works correctly")
        return True
    except Exception as e:
        print(f"✗ Rule engine integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("Testing Rule Engine Implementation")
    print("=" * 40)

    tests = [
        test_rule_engine_import,
        test_param_store,
        test_rule_registry,
        test_dependency_graph,
        test_checks,
        test_tolerance_solver,
        test_rule_engine_integration
    ]

    passed = 0
    for test in tests:
        if test():
            passed += 1
        print()

    print(f"Results: {passed}/{len(tests)} tests passed")