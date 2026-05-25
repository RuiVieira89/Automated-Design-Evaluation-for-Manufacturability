"""Hole diameter gathering example.

Loads a STEP file, normalises it with shape_normalizer, then runs
gather_hole_diameters() to find every cylindrical face that fully defines
a hole, bore, or shaft.

A cylinder is included when its angular sweep covers at least
(100 - tol)% of 360° (default 95%, i.e. ≥ 342°).  Partial cylinders
(fillets, splines, …) are excluded and counted separately.

Each result carries (solid_id, face_id) that map directly back into the
NormalizedShape so you can access the full FaceData (area, centre, bounding
box, adjacency neighbours).

Usage::

    python examples/dimension_diameterHole_example.py
    python examples/dimension_diameterHole_example.py data/simple_rib.step
    python examples/dimension_diameterHole_example.py data/FlandersMake_part_NOK-Merger.step --verbose
    python examples/dimension_diameterHole_example.py data/part.step --tol 10
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from load_cad.step_reader import read_step_single
from post_process.shape_normalizer import extract_solids, normalize_shape
from post_process.dimensions.dimension_gather_diameterHole import (
    HoleDiameterFeature,
    HoleDiameterGatherResult,
    SolidHoleResult,
    gather_hole_diameters,
)

_W = 70


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _header(text: str) -> None:
    print()
    print("=" * _W)
    print(f"  {text}")
    print("=" * _W)


def _subheader(text: str) -> None:
    print(f"\n  --- {text} ---")


def _row(label: str, value: str) -> None:
    print(f"  {label:<36} {value}")


def _print_feature(h: HoleDiameterFeature, normalized, verbose: bool) -> None:
    """Print one HoleDiameterFeature, optionally with full FaceData back-reference."""
    cx, cy, cz = h.center
    dx, dy, dz = h.axis_direction
    print(
        f"    face {h.face_id:>3d}  d={h.diameter_mm:>8.3f} mm"
        f"  r={h.radius_mm:>7.3f} mm"
        f"  angle={h.angle_deg:>6.1f}°"
        f"  area={h.area:>10.3f} mm²"
    )

    if verbose:
        # Back-reference into NormalizedShape for full FaceData
        face_data  = normalized.solids[h.solid_id].faces[h.face_id]
        neighbours = normalized.solids[h.solid_id].adjacency.get(h.face_id, [])
        lx, ly, lz = h.axis_location
        print(f"          axis dir : ({dx:+.4f}, {dy:+.4f}, {dz:+.4f})")
        print(f"          axis loc : ({lx:.3f}, {ly:.3f}, {lz:.3f}) mm")
        print(f"          centre   : ({cx:.3f}, {cy:.3f}, {cz:.3f}) mm")
        print(f"          bbox     : {face_data.bounding_box}")
        print(f"          adj faces: {neighbours}")


def _print_solid(sr: SolidHoleResult, normalized, verbose: bool) -> None:
    total_cyl = len(sr.holes) + sr.excluded_count
    _header(
        f"Solid {sr.solid_id}  —  {total_cyl} cylinder(s)  "
        f"[{len(sr.holes)} hole(s), "
        f"{sr.excluded_count} partial(s) excluded]"
    )

    if sr.holes:
        _subheader(f"Holes  — {len(sr.holes)} feature(s)")
        print(f"    {'face':>4}  {'diameter':>10}  {'radius':>9}  {'angle':>8}  {'area':>13}")
        print("    " + "-" * 56)
        for h in sorted(sr.holes, key=lambda x: x.diameter_mm):
            _print_feature(h, normalized, verbose)
    else:
        _subheader("Holes  — none found")

    _subheader(f"Partial cylinders excluded  — {sr.excluded_count} face(s)")


def _print_summary(result: HoleDiameterGatherResult) -> None:
    threshold = 360.0 * (1.0 - result.full_circle_tol_pct / 100.0)
    _header("Assembly Summary")
    _row("Solids analysed", str(len(result.solids)))
    _row("Hole features found", str(result.total_holes))
    _row("Partial cylinders excluded", str(result.total_excluded))
    _row(
        "Full-circle threshold",
        f"≥ {threshold:.1f}°  ({100 - result.full_circle_tol_pct:.0f}% of 360°)",
    )

    if result.total_holes:
        print()
        print("  Hole diameters found (all solids):")
        diameters = sorted({round(h.diameter_mm, 3) for h in result.all_holes})
        for d in diameters:
            count = sum(1 for h in result.all_holes if abs(h.diameter_mm - d) < 0.01)
            print(f"    d = {d:.3f} mm  ({count} face(s))")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    default = ROOT / "data" / "FlandersMake_part_NOK-Merger.step"
    parser = argparse.ArgumentParser(
        description="Extract hole diameters from a STEP file"
    )
    parser.add_argument(
        "path", nargs="?", default=str(default),
        help="Path to STEP file (default: FlandersMake_part_NOK-Merger.step)",
    )
    parser.add_argument(
        "--tol", type=float, default=5.0, metavar="PCT",
        help="Tolerance %% below 360° still treated as a full circle (default: 5)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Print axis direction, location, bbox, and adjacency for each feature",
    )
    parser.add_argument(
        "--solid", type=int, default=None, metavar="N",
        help="Print detail for solid N only (default: all solids)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    print(f"Loading:     {args.path}")
    compound   = read_step_single(args.path)

    print("Normalizing …")
    normalized = normalize_shape(compound)
    solids     = extract_solids(compound)
    print(f"Found {len(normalized.solids)} solid(s).")

    print("Gathering hole diameters …")
    result = gather_hole_diameters(
        normalized, solids,
        full_circle_tol_pct=args.tol,
    )

    # ── Per-solid detail ──────────────────────────────────────────────────────
    for sr in result.solids:
        if args.solid is not None and sr.solid_id != args.solid:
            continue
        _print_solid(sr, normalized, verbose=args.verbose)

    # ── Assembly summary ──────────────────────────────────────────────────────
    if args.solid is None:
        _print_summary(result)

    print()


if __name__ == "__main__":
    main()
