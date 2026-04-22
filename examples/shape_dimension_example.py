"""Shape dimension inference — example.

Loads a STEP file, normalizes it, then infers the main drawing dimensions
for every solid:

  - Overall bounding box and principal dimensions (L × W × H)
  - Cylindrical features (estimated diameter and height)
  - Planar groups (faces clustered by normal, with span along that axis)
  - Wall thickness estimates (minimum gap between parallel planar faces)

Default target: data/FlandersMake_part_NOK-Merger.step

Usage::

    python examples/shape_dimension_example.py
    python examples/shape_dimension_example.py data/simple_rib.step
    python examples/shape_dimension_example.py data/escavator_arm-Assembly.step --verbose
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
from post_process.shape_dimension import (
    CylindricalFeature,
    PlaneGroup,
    SolidDimensions,
    WallThickness,
    infer_dimensions,
)


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

_WIDTH = 72


def _header(title: str) -> None:
    print()
    print("=" * _WIDTH)
    print(f"  {title}")
    print("=" * _WIDTH)


def _section(title: str) -> None:
    print(f"\n  --- {title} ---")


def _row(label: str, value: str) -> None:
    print(f"  {label:<38} {value}")


# ---------------------------------------------------------------------------
# Per-solid display
# ---------------------------------------------------------------------------

def _print_solid(sd: SolidDimensions, verbose: bool) -> None:
    bb = sd.bounding_box
    _header(f"Solid {sd.solid_id}")

    _section("Bounding box")
    _row("X range (mm)", f"{bb[0]:.3f}  →  {bb[3]:.3f}   (Δ {bb[3]-bb[0]:.3f})")
    _row("Y range (mm)", f"{bb[1]:.3f}  →  {bb[4]:.3f}   (Δ {bb[4]-bb[1]:.3f})")
    _row("Z range (mm)", f"{bb[2]:.3f}  →  {bb[5]:.3f}   (Δ {bb[5]-bb[2]:.3f})")

    _section("Principal dimensions")
    _row("Length (longest)  (mm)", f"{sd.length:.3f}")
    _row("Width             (mm)", f"{sd.width:.3f}")
    _row("Height (shortest) (mm)", f"{sd.height:.3f}")

    # --- Cylindrical features ---
    _section(f"Cylindrical features  ({len(sd.cylinders)} detected)")
    if sd.cylinders:
        print(f"  {'face_id':>7}  {'diameter (mm)':>14}  {'height (mm)':>12}  "
              f"{'area':>12}  {'centre'}")
        print("  " + "-" * 70)
        for cyl in sorted(sd.cylinders, key=lambda c: c.diameter_est, reverse=True):
            cx, cy, cz = cyl.center
            print(
                f"  {cyl.face_id:>7}  {cyl.diameter_est:>14.3f}  "
                f"{cyl.height_est:>12.3f}  {cyl.area:>12.3f}  "
                f"({cx:.2f}, {cy:.2f}, {cz:.2f})"
            )
    else:
        print("  (none)")

    # --- Planar groups ---
    _section(f"Planar normal groups  ({len(sd.plane_groups)} groups)")
    if sd.plane_groups:
        print(f"  {'group':>5}  {'normal (canonical)':>28}  "
              f"{'span (mm)':>10}  {'total area':>12}  {'faces'}")
        print("  " + "-" * 70)
        for gi, pg in enumerate(sd.plane_groups):
            nx, ny, nz = pg.normal
            print(
                f"  {gi:>5}  ({nx:+.3f}, {ny:+.3f}, {nz:+.3f})  "
                f"{pg.span:>10.3f}  {pg.total_area:>12.3f}  {pg.face_ids}"
            )
            if verbose:
                for fid, pos in zip(pg.face_ids, pg.positions):
                    print(f"          face {fid:3d}  position along normal: {pos:.3f} mm")
    else:
        print("  (none)")

    # --- Wall thicknesses ---
    _section(f"Wall thickness estimates  ({len(sd.wall_thicknesses)} gaps)")
    if sd.wall_thicknesses:
        print(f"  {'faces':>12}  {'thickness (mm)':>16}  {'normal'}")
        print("  " + "-" * 60)
        for wt in sd.wall_thicknesses:
            nx, ny, nz = wt.normal
            flo, fhi = wt.face_ids
            print(
                f"  {flo:>5} → {fhi:<5}  {wt.thickness_mm:>16.3f}  "
                f"({nx:+.3f}, {ny:+.3f}, {nz:+.3f})"
            )
    else:
        print("  (none)")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    default = ROOT / "data" / "FlandersMake_part_NOK-Merger.step"
    parser = argparse.ArgumentParser(
        description="Infer main drawing dimensions from a STEP file"
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=str(default),
        help="Path to STEP file (default: FlandersMake_part_NOK-Merger.step)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print per-face positions within each planar group",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    step_path = args.path

    print(f"Loading:     {step_path}")
    compound = read_step_single(step_path)

    print("Normalizing shape ...")
    normalized = normalize_shape(compound)
    print(f"Inferring dimensions for {len(normalized.solids)} solid(s) ...")
    dims = infer_dimensions(normalized)

    for sd in dims.solids:
        _print_solid(sd, verbose=args.verbose)

    # Assembly summary
    print()
    print("=" * _WIDTH)
    print("  Assembly summary")
    print("=" * _WIDTH)
    print(f"  Solids         : {len(dims.solids)}")
    total_cyl = sum(len(s.cylinders) for s in dims.solids)
    total_pg  = sum(len(s.plane_groups) for s in dims.solids)
    total_wt  = sum(len(s.wall_thicknesses) for s in dims.solids)
    print(f"  Cylinders      : {total_cyl}")
    print(f"  Planar groups  : {total_pg}")
    print(f"  Thickness gaps : {total_wt}")
    if dims.solids:
        all_min_wt = [
            min(s.wall_thicknesses, key=lambda w: w.thickness_mm)
            for s in dims.solids if s.wall_thicknesses
        ]
        if all_min_wt:
            thinnest = min(all_min_wt, key=lambda w: w.thickness_mm)
            print(f"  Thinnest wall  : {thinnest.thickness_mm:.3f} mm"
                  f"  (solid {next(i for i, s in enumerate(dims.solids) if thinnest in s.wall_thicknesses)}"
                  f", faces {thinnest.face_ids})")
    print()


if __name__ == "__main__":
    main()
