"""Fillet radius gathering example.

Loads a STEP file, normalises it with shape_normalizer, then runs
gather_fillets() to classify every cylindrical face by angular sweep:

  excluded  — full 360° cylinders (holes, bores, shafts) — not printed
  fillet    — ≈90° cylinders, highlighted as likely fillets between walls
  partial   — partial cylinders at any other angle, angle annotated

Each result carries (solid_id, face_id) that map directly back into the
NormalizedShape so you can access the full FaceData (area, centre, bounding
box, adjacency neighbours).

Usage::

    python examples/dimension_radiusFillet_example.py
    python examples/dimension_radiusFillet_example.py data/simple_rib.step
    python examples/dimension_radiusFillet_example.py data/FlandersMake_part_NOK-Merger.step --verbose
    python examples/dimension_radiusFillet_example.py data/part.step --fillet-tol 3 --full-tol 1
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
from post_process.dimensions.dimension_gather_radiusFillet import (
    CylinderFeature,
    CylinderKind,
    FilletGatherResult,
    SolidFilletResult,
    gather_fillets,
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


def _print_feature(f: CylinderFeature, normalized, verbose: bool) -> None:
    """Print one CylinderFeature, optionally with full FaceData back-reference."""
    tag = ""
    if f.kind == CylinderKind.FILLET:
        tag = "  ★ FILLET"
    elif f.kind == CylinderKind.PARTIAL:
        tag = f"  △ PARTIAL ({f.angle_deg:.1f}°)"

    cx, cy, cz = f.center
    dx, dy, dz = f.axis_direction
    print(
        f"    face {f.face_id:>3d}  r={f.radius_mm:>7.3f} mm"
        f"  angle={f.angle_deg:>6.1f}°"
        f"  area={f.area:>10.3f} mm²"
        f"{tag}"
    )

    if verbose:
        # Back-reference into NormalizedShape for full FaceData
        face_data  = normalized.solids[f.solid_id].faces[f.face_id]
        neighbours = normalized.solids[f.solid_id].adjacency.get(f.face_id, [])
        lx, ly, lz = f.axis_location
        print(f"          axis dir : ({dx:+.4f}, {dy:+.4f}, {dz:+.4f})")
        print(f"          axis loc : ({lx:.3f}, {ly:.3f}, {lz:.3f}) mm")
        print(f"          centre   : ({cx:.3f}, {cy:.3f}, {cz:.3f}) mm")
        print(f"          bbox     : {face_data.bounding_box}")
        print(f"          adj faces: {neighbours}")


def _print_solid(sr: SolidFilletResult, normalized, verbose: bool) -> None:
    total_cyl = len(sr.fillets) + len(sr.partials) + sr.excluded_count
    _header(
        f"Solid {sr.solid_id}  —  {total_cyl} cylinder(s)  "
        f"[{len(sr.fillets)} fillet, "
        f"{len(sr.partials)} partial, "
        f"{sr.excluded_count} excluded]"
    )

    # ── Fillets ──────────────────────────────────────────────────────────────
    if sr.fillets:
        _subheader(f"Fillets  (≈90°)  — {len(sr.fillets)} feature(s)")
        print(f"    {'face':>4}  {'radius':>10}  {'angle':>8}  {'area':>13}")
        print("    " + "-" * 48)
        for f in sorted(sr.fillets, key=lambda x: x.radius_mm):
            _print_feature(f, normalized, verbose)
    else:
        _subheader("Fillets  (≈90°)  — none found")

    # ── Partial cylinders ─────────────────────────────────────────────────────
    if sr.partials:
        _subheader(f"Partial cylinders  — {len(sr.partials)} feature(s)")
        print(f"    {'face':>4}  {'radius':>10}  {'angle':>8}  {'area':>13}")
        print("    " + "-" * 48)
        for f in sorted(sr.partials, key=lambda x: x.angle_deg):
            _print_feature(f, normalized, verbose)
    else:
        _subheader("Partial cylinders  — none found")

    # ── Excluded ──────────────────────────────────────────────────────────────
    _subheader(f"Excluded (360° holes/bores)  — {sr.excluded_count} face(s)")


def _print_summary(result: FilletGatherResult) -> None:
    _header("Assembly Summary")
    _row("Solids analysed", str(len(result.solids)))
    _row("Fillet candidates  (≈90°)", str(result.total_fillets))
    _row("Partial cylinders  (other angle)", str(result.total_partials))
    _row("Excluded           (360° full circles)", str(result.total_excluded))
    _row("Fillet angle tolerance", f"±{result.fillet_angle_tol_pct:.1f}% of 90°  "
         f"→ [{90*(1-result.fillet_angle_tol_pct/100):.1f}°, "
         f"{90*(1+result.fillet_angle_tol_pct/100):.1f}°]")
    _row("Full-circle tolerance", f"≥ {360 - result.full_circle_tol_deg:.1f}°")

    if result.total_fillets:
        print()
        print("  Fillet radii found (all solids):")
        radii = sorted({round(f.radius_mm, 3) for f in result.all_fillets})
        for r in radii:
            count = sum(1 for f in result.all_fillets if abs(f.radius_mm - r) < 0.01)
            print(f"    r = {r:.3f} mm  ({count} face(s))")

    if result.total_partials:
        print()
        print("  Partial cylinder angles found (all solids):")
        for p in sorted(result.all_partials, key=lambda x: x.angle_deg):
            print(
                f"    solid {p.solid_id}  face {p.face_id:>3d}"
                f"  r={p.radius_mm:.3f} mm"
                f"  angle={p.angle_deg:.1f}°"
            )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    default = ROOT / "data" / "FlandersMake_part_NOK-Merger.step"
    parser = argparse.ArgumentParser(
        description="Extract and classify fillet radii from a STEP file"
    )
    parser.add_argument(
        "path", nargs="?", default=str(default),
        help="Path to STEP file (default: FlandersMake_part_NOK-Merger.step)",
    )
    parser.add_argument(
        "--fillet-tol", type=float, default=5.0, metavar="PCT",
        help="Tolerance %% around 90° for fillet classification (default: 5)",
    )
    parser.add_argument(
        "--full-tol", type=float, default=2.0, metavar="DEG",
        help="Tolerance in degrees below 360° for hole classification (default: 2)",
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

    print("Gathering fillet candidates …")
    result = gather_fillets(
        normalized, solids,
        fillet_angle_tol_pct=args.fillet_tol,
        full_circle_tol_deg=args.full_tol,
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
