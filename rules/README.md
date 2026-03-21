Pluggable rule modules (one class per DfX rule)


This layer has more internal complexity than Layers 1 and 2 — three distinct subsystems that interact rather than run in parallel columns. I'll show the overall structure first, then zoom into the DfX rule module internals.

see rule_engine_layer3_overview.svg

The key structural shift in this layer is that the three subsystems aren't parallel — they form a directed cycle. The dependency graph tells the rule modules what order to run checks in, the rule modules produce violation data that becomes constraint inputs for the tolerance solver, and the solver's feasibility verdict feeds back into the aggregator alongside the raw check results. That loop is the heart of the layer.
Here's a closer look at how the DfX rule module internals should be structured:

see rule_engine_layer3_module_anatomy.svg

The module anatomy diagram shows the key implementation pattern: a DfxCheck abstract base class with a uniform run(shape, params) → CheckResult signature. Every concrete check — wall thickness, draft angles, hole ratios — subclasses this and owns its own kernel calls (trimesh, OCCT, CGAL). The rule registry maps string names to classes so the dependency graph's topological sort can schedule checks by name without hard-wiring the execution order.
## Implementation

The rule engine is structured as:

- `base.py`: `DfxCheck` abstract base class and `CheckResult` dataclass
- `checks.py`: Concrete check implementations (WallThicknessCheck, DraftAngleCheck, etc.)
- `registry.py`: `RuleRegistry` for name → class mapping
- `param_store.py`: `ParamStore` for process parameters and thresholds
- `dependency_graph.py`: `DependencyGraph` (networkx) and `CheckScheduler`
- `tolerance_solver.py`: `ToleranceSolver` (scipy.optimize) for constraint solving
- `rule_engine.py`: `RuleEngine` orchestrator and `AnalysisReport`

### Key Architectural Decisions

**Execution Scheduling**: The networkx DAG is the execution scheduler, not just documentation. Each node is a check or feature. Edges encode dependencies — a check can't run until its dependencies pass. `nx.topological_sort()` gives check execution order, and cascading failures are handled naturally (failed dependencies suppress dependent checks).

**Constraint Integration**: scipy.optimize receives violation data as constraint bounds. When wall thickness check returns min=1.8mm vs threshold=2.0mm, margin=-0.2mm becomes a constraint in tolerance stack. This means the tolerance solver shares data with DfX checks — they run over the same geometric measurements.

**Parameter Management**: The param store is single source of truth for thresholds. Manufacturing process (injection moulding vs CNC vs casting) determines what min_wall, min_draft_angle, etc. mean. You can swap process profiles without touching check code.

### Usage

```python
from rules import RuleEngine

# Create engine with standard checks
engine = RuleEngine()

# Select manufacturing process
engine.set_process('injection_moulding')

# Run analysis
report = engine.analyze(geometry_data)

# Display results
print(engine.print_report(report))
```

### Custom Checks

```python
from rules import DfxCheck, CheckResult, Severity

class CustomCheck(DfxCheck):
    def run(self, geometry_data, params):
        # Implement your check logic
        return CheckResult(
            check_name=self.name,
            severity=Severity.PASS,
            message="Check passed"
        )

engine.register_custom_check('custom_check', CustomCheck)
```