"""ISO 4287 / ISO 4288 surface roughness tolerance advisor — example.

Demonstrates the surface roughness advisor across the main use-cases:

  Parameter selection  — which ISO 4287 parameter to put on the drawing
  Process capability   — what Ra is achievable for each manufacturing process
  Standard selection   — ISO 4287/4288 (profile) vs ISO 25178 (areal)
  Acceptance rules     — 16% rule vs max rule
  Drawing callout      — formatted ISO 1302-style callout string

Run from the repository root:
    python examples/surfRough_iso4287_4288_example.py
    python examples/surfRough_iso4287_4288_example.py --process CNC_turning --function sealing
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tolerance_advisor.helpers import load_process_capabilities
from tolerance_advisor.surfRough_iso4287_4288 import (
    recommend_surface_roughness,
    recommend_parameter,
    recommend_standard,
    list_surface_functions,
    ra_to_rz,
)

DB = load_process_capabilities()


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _header(title: str) -> None:
    width = 72
    print()
    print("=" * width)
    print(f"  {title}")
    print("=" * width)


def _row(label: str, value: str) -> None:
    print(f"  {label:<40} {value}")


def _notes(notes: list) -> None:
    for note in notes:
        print(f"    => {note}")


# ---------------------------------------------------------------------------
# Parameter selection by surface function
# ---------------------------------------------------------------------------

def demo_parameter_selection() -> None:
    _header("ISO 4287 — Parameter selection by surface function")

    functions = list_surface_functions()
    print()
    print(f"  {'Function':<18} {'Primary':<10} {'Secondary':<12}")
    print("  " + "-" * 44)
    for fn in functions:
        p = recommend_parameter(fn)
        print(f"  {fn:<18} {p['primary']:<10} {p['secondary']:<12}")

    print()
    print("  Rationale for selected functions:")
    for fn in ["sealing", "bearing", "friction"]:
        p = recommend_parameter(fn)
        print(f"\n  [{fn}]")
        print(f"    {p['rationale']}")


# ---------------------------------------------------------------------------
# Process capability and recommended drawing callout
# ---------------------------------------------------------------------------

def demo_process_recommendations() -> None:
    _header("Process-driven surface roughness recommendations")

    processes = list(DB.keys())
    functions = ["general", "sealing", "bearing"]

    for proc in processes:
        print(f"\n  Process: {proc}")
        for fn in functions:
            rec = recommend_surface_roughness(proc, function=fn, process_db=DB)
            callout = rec.drawing_callout()
            print(
                f"    [{fn:<14}]  "
                f"Ra {rec.ra_range_um[0]:.4g}–{rec.ra_range_um[1]:.4g} µm  |  "
                f"lc={rec.lambda_c_mm} mm  |  "
                f"callout: {callout}"
            )
        print()
        # Notes for default 'general' recommendation
        rec_gen = recommend_surface_roughness(proc, process_db=DB)
        _notes(rec_gen.notes)


# ---------------------------------------------------------------------------
# Acceptance rules
# ---------------------------------------------------------------------------

def demo_acceptance_rules() -> None:
    _header("Acceptance rules — 16% rule vs max rule")

    proc = "CNC_turning"
    print()
    for rule, label in [("16pct", "16% rule (default)"), ("max", "max rule (stricter)")]:
        rec = recommend_surface_roughness(proc, function="sealing", acceptance_rule=rule, process_db=DB)
        print(f"  Rule : {label}")
        _row("  Acceptance rule", rec.acceptance_rule)
        _row("  Drawing callout", rec.drawing_callout())
        print()
        _notes(rec.notes)
        print()


# ---------------------------------------------------------------------------
# Standard selection (ISO 4287/4288 vs ISO 25178)
# ---------------------------------------------------------------------------

def demo_standard_selection() -> None:
    _header("Standard selection — ISO 4287/4288 vs ISO 25178")

    cases = [
        ("general",     "machined"),
        ("sealing",     "machined"),
        ("friction",    "machined"),
        ("lubrication", "machined"),
        ("general",     "additive"),
        ("general",     "isotropic"),
        ("general",     "optical"),
    ]

    print()
    for fn, stype in cases:
        std = recommend_standard(fn, surface_type=stype)
        print(f"  function={fn:<15}  surface_type={stype:<10}  => {std.recommended_standard}")
        print(f"    {std.rationale}")
        print()


# ---------------------------------------------------------------------------
# Ra to Rz conversion
# ---------------------------------------------------------------------------

def demo_ra_to_rz() -> None:
    _header("Ra to Rz conversion (engineering heuristic: Rz approx 4 x Ra)")

    print()
    print(f"  {'Ra (µm)':<12} {'Rz approx (µm)':<16}")
    print("  " + "-" * 28)
    for ra in [0.1, 0.4, 0.8, 1.6, 3.2, 6.3, 12.5, 25.0]:
        rz = ra_to_rz(ra)
        print(f"  {ra:<12.4g} {rz:<16.4g}")


# ---------------------------------------------------------------------------
# Custom scenario (CLI)
# ---------------------------------------------------------------------------

def demo_custom(process: str, function: str, acceptance_rule: str) -> None:
    _header(f"Custom  process={process}  function={function}  rule={acceptance_rule}")
    print()

    rec = recommend_surface_roughness(process, function=function,
                                      acceptance_rule=acceptance_rule, process_db=DB)
    _row("Process", rec.process)
    _row("Function", rec.function)
    _row("Primary parameter", rec.primary_parameter)
    _row("Secondary parameter", rec.secondary_parameter)
    _row("Ra range achievable (µm)", f"{rec.ra_range_um[0]:.4g} – {rec.ra_range_um[1]:.4g}")
    _row("Rz approx (µm)", f"{rec.rz_approx_um:.4g}")
    _row("ISO 4288 cut-off lambda_c (mm)", f"{rec.lambda_c_mm}")
    _row("Acceptance rule", rec.acceptance_rule)
    _row("Drawing callout (ISO 1302)", rec.drawing_callout())
    print()
    _notes(rec.notes)

    std = recommend_standard(function)
    print()
    _row("Recommended standard", std.recommended_standard)
    print(f"    {std.rationale}")
    _notes(std.notes)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ISO 4287/4288 surface roughness tolerance advisor example"
    )
    parser.add_argument("--process", default=None,
                        help="Process for custom scenario (e.g. CNC_turning)")
    parser.add_argument("--function", default="general",
                        help="Surface function (e.g. sealing, bearing, friction)")
    parser.add_argument("--rule", default="16pct", choices=["16pct", "max"],
                        help="Acceptance rule: 16pct (default) or max")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    demo_parameter_selection()
    demo_process_recommendations()
    demo_acceptance_rules()
    demo_standard_selection()
    demo_ra_to_rz()

    if args.process:
        demo_custom(args.process, args.function, args.rule)

    print()


if __name__ == "__main__":
    main()
