"""ISO 2768 general tolerances advisor — example.

Demonstrates linTol_iso2768 across all three functional areas of the standard:

  Part 1 linear  — table-based tolerance bands for all four classes (f/m/c/v)
  Part 1 angular — angular tolerance bands for all four classes
  Part 2 geom    — ISO 2768-2 form and position classes (H/K/L)
  Process-driven — title-block recommendation from process capability

⚠ ISO 2768 covers only non-critical, unannotated features.
  Critical features (bearing bores, sealing surfaces, precision fits,
  safety interfaces) require explicit ISO 286 / ISO 1101 tolerances.

Run from the repository root:
    python examples/linTol_iso2768_example.py
    python examples/linTol_iso2768_example.py --process sand_casting --nominal 250
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tolerance_advisor.helpers import load_process_capabilities
from tolerance_advisor.linTol_iso2768 import (
    linear_tol_iso2768,
    angular_tol_iso2768,
    geometric_tol_iso2768,
    propose_general_tolerance,
    recommend_title_block,
    list_linear_classes,
    list_geo_classes,
    list_geo_characteristics,
)

DB = load_process_capabilities()

CLASS_NAMES = {"f": "fine", "m": "medium", "c": "coarse", "v": "very coarse"}


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _header(title: str) -> None:
    width = 68
    print()
    print("=" * width)
    print(f"  {title}")
    print("=" * width)


def _row(label: str, value: str) -> None:
    print(f"  {label:<38} {value}")


# ---------------------------------------------------------------------------
# Part 1 — Linear tolerances
# ---------------------------------------------------------------------------

def demo_linear() -> None:
    _header("ISO 2768-1  Part 1 — Linear tolerances  (±mm)")

    nominals = [2.0, 5.0, 18.0, 50.0, 200.0, 600.0, 1500.0, 3000.0]

    # Header row
    print()
    print(f"  {'Nominal (mm)':<14}", end="")
    for cls in list_linear_classes():
        print(f"  {cls} ({CLASS_NAMES[cls][:6]:<6})", end="")
    print()
    print("  " + "-" * 64)

    for nom in nominals:
        print(f"  {nom:<14.1f}", end="")
        for cls in list_linear_classes():
            try:
                t = linear_tol_iso2768(nom, cls)
                print(f"  ±{t:<14.3f}", end="")
            except ValueError:
                print(f"  {'n/a':<15}", end="")
        print()

    print()
    print("  n/a = class not defined for that size range per ISO 2768-1:1989 Table 1")


# ---------------------------------------------------------------------------
# Part 1 — Angular tolerances
# ---------------------------------------------------------------------------

def demo_angular() -> None:
    _header("ISO 2768-1  Part 1 — Angular tolerances")

    shorter_sides = [5.0, 25.0, 80.0, 250.0, 600.0]

    print()
    print(f"  {'Shorter side (mm)':<20}", end="")
    for cls in list_linear_classes():
        print(f"  {cls} ({CLASS_NAMES[cls][:6]:<6})", end="")
    print()
    print("  " + "-" * 72)

    for side in shorter_sides:
        print(f"  {side:<20.1f}", end="")
        for cls in list_linear_classes():
            res = angular_tol_iso2768(side, cls)
            print(f"  {res['tolerance_dms']:<15}", end="")
        print()

    print()
    print("  Note: classes f and m are identical for angular dimensions (ISO 2768-1).")


# ---------------------------------------------------------------------------
# Part 2 — Geometric tolerances
# ---------------------------------------------------------------------------

def demo_geometric() -> None:
    _header("ISO 2768-2  Part 2 — Geometric tolerances  (mm)")

    sizes = [8.0, 20.0, 60.0, 200.0, 600.0, 2000.0]
    characteristics = list_geo_characteristics()

    for char in characteristics:
        print()
        print(f"  Characteristic: {char}")
        print(f"  {'Size (mm)':<14}", end="")
        for gcls in list_geo_classes():
            print(f"  class {gcls:<10}", end="")
        print()
        print("  " + "-" * 50)
        for sz in sizes:
            if char == "circular_runout":
                # size-independent; only print once
                if sz != sizes[0]:
                    continue
                print(f"  {'(any)':<14}", end="")
            else:
                print(f"  {sz:<14.1f}", end="")
            for gcls in list_geo_classes():
                t = geometric_tol_iso2768(sz, gcls, char)
                print(f"  {t:<16.3f}", end="")
            print()


# ---------------------------------------------------------------------------
# Process-driven recommendations
# ---------------------------------------------------------------------------

def demo_process_recommendations() -> None:
    _header("Process-driven ISO 2768 title-block recommendations")

    processes = list(DB.keys())
    print()
    for proc in processes:
        tb = recommend_title_block(proc, DB)
        gen = propose_general_tolerance(50.0, proc, DB)
        print(f"  Process : {proc}")
        print(f"    Title block    : {tb.title_block}")
        print(f"    Linear class   : {tb.linear_class}  ({CLASS_NAMES.get(tb.linear_class, '')})")
        print(f"    Geo class      : {tb.geo_class}")
        print(f"    Linear tol @50mm: ±{gen['tolerance_mm']} mm")
        for note in tb.notes:
            print(f"    ⚑  {note}")
        print()


# ---------------------------------------------------------------------------
# Custom scenario (CLI)
# ---------------------------------------------------------------------------

def demo_custom(process: str, nominal: float) -> None:
    _header(f"Custom  nominal={nominal} mm  ·  process={process}")
    print()

    tb = recommend_title_block(process, DB)
    _row("Title block", tb.title_block)
    _row("Linear class", f"{tb.linear_class}  ({CLASS_NAMES.get(tb.linear_class, '')})")

    lin = propose_general_tolerance(nominal, process, DB)
    _row(f"Linear tolerance ±mm @{nominal} mm", f"±{lin['tolerance_mm']} mm")

    ang = angular_tol_iso2768(nominal, tb.linear_class)
    _row(f"Angular tolerance (shorter side {nominal} mm)", ang["tolerance_dms"])

    for char in list_geo_characteristics():
        t = geometric_tol_iso2768(nominal, tb.geo_class, char)
        _row(f"Geo {char} @{nominal} mm [{tb.geo_class}]", f"{t} mm")

    print()
    for note in tb.notes:
        print(f"  ⚑  {note}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ISO 2768 general tolerances example"
    )
    parser.add_argument("--process", default=None,
                        help="Process for custom scenario (e.g. sand_casting)")
    parser.add_argument("--nominal", type=float, default=50.0,
                        help="Nominal size in mm for custom scenario (default: 50.0)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    demo_linear()
    demo_angular()
    demo_geometric()
    demo_process_recommendations()

    if args.process:
        demo_custom(args.process, args.nominal)

    print()


if __name__ == "__main__":
    main()
