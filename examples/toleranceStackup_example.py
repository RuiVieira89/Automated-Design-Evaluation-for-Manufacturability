"""Tolerance stack-up example.

Demonstrates tolerance_advisor.toleranceStackup with four scenarios of
increasing realism, followed by an optional visualization.

  Scenario 1 — Manual 4-part linear chain
    Textbook-verifiable shaft + spacers + housing end-play problem.
    Shows WC, RSS, and Monte Carlo results side-by-side.

  Scenario 2 — ISO 2768 and process tolerance lookup
    How to assign tolerances from the standard or from process
    capability tables, before building a chain manually.

  Scenario 3 — Chain from SolidDimensions
    Uses contributors_from_solid() to auto-extract all dimensions of
    a synthetic part, then computes the stack-up of its bounding envelope.

  Scenario 4 — Multi-solid assembly chain
    Combines contributors from two separate solids (shaft + housing)
    with mixed sensitivities to model a real assembly gap.

Run::

    python examples/toleranceStackup_example.py
    python examples/toleranceStackup_example.py --no-plot
    python examples/toleranceStackup_example.py data/part.step --process CNC_milling

The visualization panel requires matplotlib (already a project dependency).
STEP loading in the optional 5th scenario requires pythonocc-core.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tolerance_advisor.toleranceStackup import (
    DimensionContributor,
    StackUpChain,
    StackUpResult,
    assign_iso2768_tolerance,
    assign_process_tolerance,
    compute_stack_up,
    contributors_from_mds,
    contributors_from_solid,
    print_stack_up_report,
)


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

_W = 68


def _header(title: str) -> None:
    print()
    print("=" * _W)
    print(f"  {title}")
    print("=" * _W)


def _row(label: str, value: str) -> None:
    print(f"  {label:<38} {value}")


# ---------------------------------------------------------------------------
# Scenario 1 — Manual 4-part linear chain (textbook end-play problem)
# ---------------------------------------------------------------------------

def demo_manual_chain() -> StackUpResult:
    """
    Classical 1-D stack: housing bore depth − shaft length − two spacers.

    The critical measurement is the axial end-play (gap) between the shaft
    shoulder and the housing wall.  A negative nominal gap means the chain
    as written closes the gap; signs must be consistent.

    Diagram (left → right, positive direction):

        |←── housing depth 62 mm ──────────────────────→|
        |    |←── shaft 55 mm ──→|← 4 →|← 2.8 →|      |
        |                                               gap?

    Sensitivities:
        housing_depth : –1  (opposes the gap — its increase closes the gap)
        shaft_length  : +1
        spacer_A      : +1
        spacer_B      : +1

    Nominal gap = –62 + 55 + 4 + 2.8 = –0.2 mm
    (Negative means the chain as written is 0.2 mm over-constrained;
    in reality the parts assemble because tolerances absorb this.)
    """
    _header("Scenario 1 — Manual 4-part linear chain (shaft end-play)")

    chain = StackUpChain(
        name="shaft_end_play",
        spec_min=0.05,   # minimum clearance to prevent binding
        spec_max=0.40,   # maximum clearance to prevent excessive play
        contributors=[
            DimensionContributor(
                "housing_bore_depth", 62.00, tol_plus=0.12, tol_minus=0.12,
                sensitivity=-1.0, description="CNC milling, IT9",
            ),
            DimensionContributor(
                "shaft_length", 55.00, tol_plus=0.08, tol_minus=0.08,
                sensitivity=+1.0, description="CNC turning, IT8",
            ),
            DimensionContributor(
                "spacer_A_width", 4.00, tol_plus=0.04, tol_minus=0.04,
                sensitivity=+1.0, description="CNC turning, IT8",
            ),
            DimensionContributor(
                "spacer_B_width", 2.80, tol_plus=0.04, tol_minus=0.04,
                sensitivity=+1.0, description="CNC turning, IT8",
            ),
        ],
    )

    result = compute_stack_up(chain, n_mc=200_000)
    print_stack_up_report(result)

    print("  Interpretation:")
    if result.wc_passes_spec:
        print("    WC: even the worst-case assembly stays within spec — robust design.")
    else:
        print("    WC: worst-case assembly falls outside spec.")
        print("    → Consider tightening the housing bore or shaft tolerances.")
    if result.rss_passes_spec:
        print("    RSS 3σ: statistical assembly yield is very high (>99.7%).")
    if result.mc_yield_pct is not None:
        print(f"    MC: {result.mc_yield_pct:.2f}% of simulated assemblies meet spec.")

    return result


# ---------------------------------------------------------------------------
# Scenario 2 — ISO 2768 / process tolerance lookup
# ---------------------------------------------------------------------------

def demo_tolerance_lookup() -> None:
    _header("Scenario 2 — ISO 2768 and process tolerance assignment")

    print()
    print("  ISO 2768-1 linear tolerance (±mm) by class")
    print(f"  {'Nominal (mm)':<16} {'class f':>10} {'class m':>10} "
          f"{'class c':>10} {'class v':>10}")
    print("  " + "-" * 60)
    for nom in (2.0, 10.0, 50.0, 150.0, 600.0):
        row = f"  {nom:<16.1f}"
        for cls in ("f", "m", "c", "v"):
            try:
                row += f"  ±{assign_iso2768_tolerance(nom, cls):.4f}"
            except ValueError:
                row += f"  {'—':>8}"
        print(row)

    print()
    print("  Process capability tolerance (±mm) for a 30 mm feature")
    for proc in (
        "CNC_milling", "CNC_turning", "cylindrical_grinding",
        "die_casting", "injection_moulding", "FDM_3D_print",
        "sand_casting",
    ):
        t = assign_process_tolerance(30.0, proc)
        _row(f"  {proc}", f"±{t:.4f} mm")

    print()
    print("  Building a chain with mixed tolerance sources:")
    chain = StackUpChain(
        name="mixed_tolerance_sources",
        contributors=[
            DimensionContributor(
                "precision_bore",
                nominal=52.0,
                tol_plus=assign_iso2768_tolerance(52.0, "f"),
                tol_minus=assign_iso2768_tolerance(52.0, "f"),
                sensitivity=-1.0,
                description="ISO 2768 fine",
            ),
            DimensionContributor(
                "turned_shaft",
                nominal=48.0,
                tol_plus=assign_process_tolerance(48.0, "CNC_turning"),
                tol_minus=assign_process_tolerance(48.0, "CNC_turning"),
                sensitivity=+1.0,
                description="CNC turning process",
            ),
            DimensionContributor(
                "cast_spacer",
                nominal=3.5,
                tol_plus=assign_process_tolerance(3.5, "die_casting"),
                tol_minus=assign_process_tolerance(3.5, "die_casting"),
                sensitivity=+1.0,
                description="Die casting process",
            ),
        ],
    )
    result = compute_stack_up(chain)
    print_stack_up_report(result)


# ---------------------------------------------------------------------------
# Scenario 3 — contributors_from_solid (SolidDimensions stub, no OCC)
# ---------------------------------------------------------------------------

def demo_from_solid() -> StackUpResult:
    """Extract contributors from a synthetic SolidDimensions (no OCC needed)."""
    _header("Scenario 3 — Chain from SolidDimensions (bounding-box block)")

    # Build a minimal SolidDimensions without pythonocc — uses only
    # the public dataclasses from shape_dimension.py.
    from post_process.shape_dimension import SolidDimensions, WallThickness, PlaneGroup

    sd = SolidDimensions(
        solid_id=0,
        bounding_box=(0.0, 0.0, 0.0, 120.0, 60.0, 40.0),
        length=120.0,
        width=60.0,
        height=40.0,
        cylinders=[],
        plane_groups=[
            PlaneGroup(
                normal=(1.0, 0.0, 0.0),
                face_ids=[0, 1],
                positions=[0.0, 120.0],
                total_area=60.0 * 40.0 * 2,
                span=120.0,
            ),
        ],
        wall_thicknesses=[
            WallThickness(normal=(1.0, 0.0, 0.0), thickness_mm=8.5, face_ids=(0, 1)),
        ],
    )

    contributors = contributors_from_solid(
        sd, process="CNC_milling", include_cylinders=False, include_walls=True,
    )

    print(f"\n  Extracted {len(contributors)} contributors from solid {sd.solid_id}:")
    for c in contributors:
        print(f"    {c.name:<42} nom={c.nominal:>8.3f}  ±{c.tol_sym:.4f}")

    chain = StackUpChain(
        name="block_bounding_envelope",
        contributors=contributors,
    )
    result = compute_stack_up(chain)
    print_stack_up_report(result)
    return result


# ---------------------------------------------------------------------------
# Scenario 4 — Multi-solid assembly chain (shaft + housing)
# ---------------------------------------------------------------------------

def demo_assembly_chain() -> StackUpResult:
    """Chain contributors from two separate solids into one assembly stack-up."""
    _header("Scenario 4 — Multi-solid assembly: shaft inside housing")

    from post_process.shape_dimension import SolidDimensions

    shaft = SolidDimensions(
        solid_id=0,
        bounding_box=(0.0, 0.0, 0.0, 58.0, 25.0, 25.0),
        length=58.0, width=25.0, height=25.0,
        cylinders=[], plane_groups=[], wall_thicknesses=[],
    )
    housing = SolidDimensions(
        solid_id=1,
        bounding_box=(0.0, 0.0, 0.0, 25.0, 65.0, 25.0),
        length=65.0, width=25.0, height=25.0,
        cylinders=[], plane_groups=[], wall_thicknesses=[],
    )

    shaft_cs = contributors_from_solid(
        shaft, process="CNC_turning",
        include_cylinders=False, include_walls=False,
    )
    housing_cs = contributors_from_solid(
        housing, process="CNC_milling",
        include_cylinders=False, include_walls=False,
    )

    # In the assembly: the housing length opposes the shaft length.
    # Override sensitivities: shaft → +1 (occupies space), housing → –1 (limits space).
    # Only keep the "length" contributors for the axial dimension.
    shaft_len = next(c for c in shaft_cs if "length" in c.name)
    housing_len = next(c for c in housing_cs if "length" in c.name)
    housing_len_neg = DimensionContributor(
        name=housing_len.name,
        nominal=housing_len.nominal,
        tol_plus=housing_len.tol_plus,
        tol_minus=housing_len.tol_minus,
        sensitivity=-1.0,
        description="Housing internal length (opposes shaft)",
    )

    spacer = DimensionContributor(
        "assembly_spacer", nominal=5.0,
        tol_plus=assign_process_tolerance(5.0, "CNC_turning"),
        tol_minus=assign_process_tolerance(5.0, "CNC_turning"),
        sensitivity=+1.0,
        description="Axial spacer — CNC turning",
    )

    chain = StackUpChain(
        name="shaft_in_housing_axial_gap",
        spec_min=0.0,
        spec_max=0.50,
        contributors=[housing_len_neg, shaft_len, spacer],
    )

    result = compute_stack_up(chain)
    print_stack_up_report(result)
    return result


# ---------------------------------------------------------------------------
# Scenario 5 (optional) — contributors_from_mds with a loaded MinimalDimensionSet
# ---------------------------------------------------------------------------

def demo_from_mds() -> None:
    _header("Scenario 5 — contributors_from_mds (MinimalDimensionSet stub)")

    from post_process.dimension_minimal import DimensionEntry, MinimalDimensionSet

    mds = MinimalDimensionSet(
        solid_id=0,
        process="CNC_milling",
        it_grade="IT8",
        process_class="medium",
        general_tolerance_note="ISO 2768-mK",
        dimensions=[
            DimensionEntry("length",   80.0, 0.054, "IT8", "Overall length", 0, []),
            DimensionEntry("width",    40.0, 0.039, "IT8", "Overall width",  0, []),
            DimensionEntry("height",   15.0, 0.027, "IT8", "Overall height", 0, []),
            DimensionEntry("diameter", 12.0, 0.018, "IT8", "Bore diameter",  0, [1]),
            DimensionEntry("wall_thickness", 6.0, 0.015, "IT8", "Pocket wall", 0, [2, 3]),
        ],
    )

    contributors = contributors_from_mds(mds)
    print(f"\n  {len(contributors)} contributors from MinimalDimensionSet (IT8, CNC_milling):")
    for c in contributors:
        print(f"    {c.name:<35} ±{c.tol_sym:.4f} mm  [{c.description[:40]}]")

    chain = StackUpChain(name="mds_envelope", contributors=contributors)
    result = compute_stack_up(chain)
    print_stack_up_report(result)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Tolerance stack-up example — five scenarios"
    )
    parser.add_argument(
        "step_path", nargs="?", default=None,
        help="Optional STEP file for geometry-based chain (requires pythonocc-core)",
    )
    parser.add_argument(
        "--process", default="CNC_milling",
        help="Manufacturing process for STEP-based chain (default: CNC_milling)",
    )
    parser.add_argument(
        "--no-plot", action="store_true",
        help="Skip the visualization panel",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    result1 = demo_manual_chain()
    demo_tolerance_lookup()
    result3 = demo_from_solid()
    result4 = demo_assembly_chain()
    demo_from_mds()

    # ── Optional: load chain from a real STEP file ───────────────────────────
    step_result = None
    if args.step_path:
        _header(f"Scenario 6 — From STEP file: {args.step_path}")
        try:
            from load_cad.step_reader import read_step_single
            from post_process.shape_normalizer import normalize_shape
            from post_process.shape_dimension import infer_dimensions
            from tolerance_advisor.helpers import load_process_capabilities

            print(f"  Loading {args.step_path} …")
            compound   = read_step_single(args.step_path)
            normalized = normalize_shape(compound)
            shape_dims = infer_dimensions(normalized)
            db         = load_process_capabilities()

            solid = shape_dims.solids[0]
            cs = contributors_from_solid(solid, process=args.process, db=db)
            chain = StackUpChain(
                name=f"{Path(args.step_path).stem} — {args.process}",
                contributors=cs,
            )
            step_result = compute_stack_up(chain)
            print_stack_up_report(step_result)
        except ImportError as exc:
            print(f"  pythonocc-core not available: {exc}", file=sys.stderr)
        except Exception as exc:
            print(f"  Failed to load STEP file: {exc}", file=sys.stderr)

    # ── Visualization ────────────────────────────────────────────────────────
    if not args.no_plot:
        try:
            from visualization.tolStackup_viewer import view_stack_up

            # Show the primary manual chain result.
            view_stack_up(
                result1,
                title="Tolerance Stack-Up: Shaft End-Play (Scenario 1)",
            )

            # Show the assembly chain from Scenario 4.
            view_stack_up(
                result4,
                title="Tolerance Stack-Up: Shaft-in-Housing Assembly (Scenario 4)",
            )

            # If a STEP file was loaded, show that too.
            if step_result is not None:
                view_stack_up(step_result)

        except ImportError as exc:
            print(f"\n  Visualization skipped (matplotlib unavailable): {exc}",
                  file=sys.stderr)

    print()


if __name__ == "__main__":
    main()
