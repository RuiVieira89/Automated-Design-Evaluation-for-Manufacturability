"""Minimal dimension set for 2D drawing — example.

Loads a STEP file, runs shape normalisation and dimension inference, then
derives the minimal set of drawing dimensions for a specified manufacturing
process.  Shows how the dimension count and tolerance values change between
process classes (coarse / medium / fine).

Default target: data/FlandersMake_part_NOK-Merger.step

Usage::

    python examples/dimension_minimal_example.py
    python examples/dimension_minimal_example.py data/simple_rib.step --process CNC_milling
    python examples/dimension_minimal_example.py data/simple_rib.step --compare
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from load_cad.step_reader import read_step_single
from post_process.shape_normalizer import normalize_shape
from post_process.shape_dimension import infer_dimensions
from post_process.dimension_minimal import (
    DimensionEntry,
    MinimalDimensionSet,
    minimal_dimensions,
)
from tolerance_advisor.helpers import load_process_capabilities

DB = load_process_capabilities()

_WIDTH = 72
_PRIORITY_SYMBOL = {"critical": "(!)", "important": "   ", "informational": "   "}
_KIND_ORDER = [
    "length", "width", "height",
    "diameter", "depth",
    "position_x", "position_y", "position_z",
    "wall_thickness", "span",
]


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _header(title: str) -> None:
    print()
    print("=" * _WIDTH)
    print(f"  {title}")
    print("=" * _WIDTH)


def _section(title: str) -> None:
    print(f"\n  --- {title} ---")


def _kind_label(kind: str) -> str:
    return {
        "length": "Length", "width": "Width", "height": "Height",
        "diameter": "Diameter", "depth": "Depth",
        "position_x": "Pos X", "position_y": "Pos Y", "position_z": "Pos Z",
        "wall_thickness": "Wall", "span": "Span",
    }.get(kind, kind)


def _print_minimal_set(mds: MinimalDimensionSet) -> None:
    _header(
        f"Solid {mds.solid_id}  ·  process={mds.process}"
        f"  ·  {mds.it_grade}  ({mds.process_class})"
    )

    print(f"\n  Dimensions  : {mds.count()}  total")
    print(f"  General tol : {mds.general_tolerance_note}")

    # Group by kind in display order
    by_kind: dict = {}
    for d in mds.dimensions:
        by_kind.setdefault(d.kind, []).append(d)

    for kind in _KIND_ORDER:
        entries = by_kind.get(kind, [])
        if not entries:
            continue
        _section(_kind_label(kind))
        print(f"  {'annotation':<28} {'priority':<14} description")
        print("  " + "-" * 68)
        for d in entries:
            sym = _PRIORITY_SYMBOL.get(d.priority, "   ")
            print(f"  {sym} {d.drawing_annotation():<25} {d.priority:<14} {d.description}")

    if mds.warnings:
        _section("Warnings")
        for w in mds.warnings:
            print(f"  (!) {w}")


def _compare_processes(step_path: str, processes: list[str]) -> None:
    """Side-by-side summary across process classes."""
    compound = read_step_single(step_path)
    normalized = normalize_shape(compound)
    dims = infer_dimensions(normalized)

    print(f"\nFile: {step_path}")
    print(f"Solids: {len(dims.solids)}\n")

    header = f"  {'Process':<30} {'Class':<8} {'IT':<6} {'Dims':>5}  {'Critical':>8}"
    print(header)
    print("  " + "-" * 62)

    for proc in processes:
        if proc not in DB:
            print(f"  {proc:<30} (not in process_capabilities.yaml)")
            continue
        result = minimal_dimensions(dims, proc, DB)
        for mds in result:
            n_crit = len(mds.critical())
            print(
                f"  {proc:<30} {mds.process_class:<8} {mds.it_grade:<6} "
                f"{mds.count():>5}  {n_crit:>8}"
            )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    default = ROOT / "data" / "FlandersMake_part_NOK-Merger.step"
    parser = argparse.ArgumentParser(
        description="Minimal drawing dimensions from a STEP file"
    )
    parser.add_argument("path", nargs="?", default=str(default),
                        help="Path to STEP file")
    parser.add_argument("--process", default="CNC_milling",
                        help="Manufacturing process (default: CNC_milling)")
    parser.add_argument(
        "--compare", action="store_true",
        help="Compare dimension counts across a range of process classes",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.compare:
        compare_procs = [
            "cylindrical_grinding",
            "CNC_turning",
            "CNC_milling",
            "drilling",
            "die_casting",
            "injection_moulding",
            "sand_casting",
            "FDM_3d_printing",
        ]
        _compare_processes(args.path, compare_procs)
        return

    print(f"Loading:     {args.path}")
    compound = read_step_single(args.path)
    print("Normalizing ...")
    normalized = normalize_shape(compound)
    print("Inferring dimensions ...")
    dims = infer_dimensions(normalized)
    print(f"Computing minimal set for process: {args.process}")
    results = minimal_dimensions(dims, args.process, DB)

    for mds in results:
        _print_minimal_set(mds)

    print()
    total = sum(m.count() for m in results)
    total_crit = sum(len(m.critical()) for m in results)
    print(f"  Total dimensions : {total}")
    print(f"  Critical         : {total_crit}")
    print()


if __name__ == "__main__":
    main()
