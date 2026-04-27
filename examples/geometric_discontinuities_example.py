"""Geometric discontinuity detection example.

Loads a STEP file, normalises it with shape_normalizer, then runs
gather_discontinuities() to find every sharp edge — any junction between
two adjacent surfaces where the outward-normal angle exceeds the threshold.

  angle between normals = 0°   → coplanar / smooth blend (not flagged)
  angle between normals = 90°  → right-angle corner (HIGH severity)
  angle between normals = 180° → knife edge (HIGH severity)

Each SharpEdge carries (solid_id, face_id_a, face_id_b) that map back into
the NormalizedShape so you can retrieve full FaceData (area, centre, bbox).

Severity:
  LOW    30° – 44°   gentle geometric transition
  MEDIUM 45° – 89°   notable sharp edge
  HIGH   ≥ 90°       right-angle or sharper

Kind (heuristic):
  CONVEX   outward ridge  → risk of physical injury
  CONCAVE  re-entrant notch → risk of stress concentration
  UNKNOWN  orientation could not be determined

Usage::

    python examples/geometric_discontinuities_example.py
    python examples/geometric_discontinuities_example.py data/simple_rib.step
    python examples/geometric_discontinuities_example.py data/FlandersMake_part_NOK-Merger.step --verbose
    python examples/geometric_discontinuities_example.py data/part.step --threshold 20 --solid 0
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
from post_process.shape.geometric_discontinuities import (
    DiscontinuityGatherResult,
    DiscontinuityKind,
    DiscontinuitySeverity,
    SharpEdge,
    SolidDiscontinuityResult,
    gather_discontinuities,
)

_W = 74

_SEVERITY_TAG = {
    DiscontinuitySeverity.LOW:    "LOW   ",
    DiscontinuitySeverity.MEDIUM: "MEDIUM",
    DiscontinuitySeverity.HIGH:   "HIGH  ",
}
_KIND_TAG = {
    DiscontinuityKind.CONVEX:  "convex ",
    DiscontinuityKind.CONCAVE: "concave",
    DiscontinuityKind.UNKNOWN: "unknown",
}


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
    print(f"  {label:<38} {value}")


def _print_edge(e: SharpEdge, normalized, verbose: bool) -> None:
    sev = _SEVERITY_TAG[e.severity]
    knd = _KIND_TAG[e.kind]
    mx, my, mz = e.edge_midpoint
    print(
        f"    faces {e.face_id_a:>3d}/{e.face_id_b:<3d}"
        f"  angle={e.dihedral_angle_deg:>6.1f}°"
        f"  len={e.edge_length:>8.3f} mm"
        f"  [{sev}]  {knd}"
    )
    if verbose:
        face_a = normalized.solids[e.solid_id].faces[e.face_id_a]
        face_b = normalized.solids[e.solid_id].faces[e.face_id_b]
        print(f"          midpoint : ({mx:.3f}, {my:.3f}, {mz:.3f}) mm")
        print(f"          face_a   : type={face_a.surface_type}  area={face_a.area:.3f} mm²")
        print(f"          face_b   : type={face_b.surface_type}  area={face_b.area:.3f} mm²")
        print(f"          adj_a    : {e.adjacent_face_ids_a}")
        print(f"          adj_b    : {e.adjacent_face_ids_b}")


def _print_solid(sr: SolidDiscontinuityResult, normalized, verbose: bool) -> None:
    n_low = sum(1 for e in sr.sharp_edges if e.severity == DiscontinuitySeverity.LOW)
    n_med = sum(1 for e in sr.sharp_edges if e.severity == DiscontinuitySeverity.MEDIUM)
    n_hi  = sum(1 for e in sr.sharp_edges if e.severity == DiscontinuitySeverity.HIGH)

    _header(
        f"Solid {sr.solid_id}  —  {len(sr.sharp_edges)} sharp edge(s) "
        f"[{n_hi} HIGH / {n_med} MEDIUM / {n_low} LOW]  "
        f"({sr.total_edges_checked} edges checked)"
    )

    if not sr.sharp_edges:
        print("  No sharp edges detected above threshold.")
        return

    # ── HIGH severity ────────────────────────────────────────────────────────
    hi_edges = sr.high_severity_edges
    if hi_edges:
        _subheader(f"HIGH severity  (≥ 90°)  — {len(hi_edges)} edge(s)")
        print(f"    {'faces':>9}  {'angle':>8}  {'length':>11}  {'severity':<8}  kind")
        print("    " + "-" * 58)
        for e in sorted(hi_edges, key=lambda x: -x.dihedral_angle_deg):
            _print_edge(e, normalized, verbose)

    # ── MEDIUM severity ───────────────────────────────────────────────────────
    med_edges = [e for e in sr.sharp_edges if e.severity == DiscontinuitySeverity.MEDIUM]
    if med_edges:
        _subheader(f"MEDIUM severity  (45° – 89°)  — {len(med_edges)} edge(s)")
        print(f"    {'faces':>9}  {'angle':>8}  {'length':>11}  {'severity':<8}  kind")
        print("    " + "-" * 58)
        for e in sorted(med_edges, key=lambda x: -x.dihedral_angle_deg):
            _print_edge(e, normalized, verbose)

    # ── LOW severity ──────────────────────────────────────────────────────────
    low_edges = [e for e in sr.sharp_edges if e.severity == DiscontinuitySeverity.LOW]
    if low_edges:
        _subheader(f"LOW severity  (30° – 44°)  — {len(low_edges)} edge(s)")
        print(f"    {'faces':>9}  {'angle':>8}  {'length':>11}  {'severity':<8}  kind")
        print("    " + "-" * 58)
        for e in sorted(low_edges, key=lambda x: -x.dihedral_angle_deg):
            _print_edge(e, normalized, verbose)


def _print_summary(result: DiscontinuityGatherResult) -> None:
    _header("Assembly Summary")
    _row("Solids analysed", str(len(result.solids)))
    _row("Edges checked (internal manifold)", str(result.total_edges_checked))
    _row("Sharp edges detected", str(result.total_sharp_edges))
    _row("  — HIGH severity  (≥ 90°)", str(len(result.all_high_severity)))
    _row("  — MEDIUM severity  (45° – 89°)",
         str(sum(1 for e in result.all_sharp_edges
                 if e.severity == DiscontinuitySeverity.MEDIUM)))
    _row("  — LOW severity  (30° – 44°)",
         str(sum(1 for e in result.all_sharp_edges
                 if e.severity == DiscontinuitySeverity.LOW)))
    _row("  — CONVEX (injury risk)", str(len(result.all_convex_edges)))
    _row("  — CONCAVE (stress concentration)", str(len(result.all_concave_edges)))
    _row("  — UNKNOWN orientation", str(
        sum(1 for e in result.all_sharp_edges if e.kind == DiscontinuityKind.UNKNOWN)
    ))
    _row("Angle threshold", f"{result.angle_threshold_deg:.1f}° between outward normals")

    if result.total_sharp_edges:
        print()
        print("  Most severe edges (top 5 by angle):")
        top = sorted(result.all_sharp_edges, key=lambda x: -x.dihedral_angle_deg)[:5]
        for e in top:
            print(
                f"    solid {e.solid_id}  faces {e.face_id_a}/{e.face_id_b}"
                f"  {e.dihedral_angle_deg:.1f}°  [{e.severity.value}]"
                f"  {e.kind.value}"
            )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    default = ROOT / "data" / "FlandersMake_part_NOK-Merger.step"
    parser = argparse.ArgumentParser(
        description="Detect geometric discontinuities (sharp edges) in a STEP file"
    )
    parser.add_argument(
        "path", nargs="?", default=str(default),
        help="Path to STEP file (default: FlandersMake_part_NOK-Merger.step)",
    )
    parser.add_argument(
        "--threshold", type=float, default=30.0, metavar="DEG",
        help="Min angle between outward normals to flag as sharp (default: 30°)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Print face types, areas, adjacency for each edge",
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

    print(f"Detecting discontinuities (threshold = {args.threshold}°) …")
    result = gather_discontinuities(
        normalized, solids,
        angle_threshold_deg=args.threshold,
    )

    for sr in result.solids:
        if args.solid is not None and sr.solid_id != args.solid:
            continue
        _print_solid(sr, normalized, verbose=args.verbose)

    if args.solid is None:
        _print_summary(result)

    print()


if __name__ == "__main__":
    main()
