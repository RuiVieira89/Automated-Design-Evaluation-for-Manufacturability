"""Example: normalize a STEP file into a structured NormalizedShape.

Usage::

    python examples/normalize_shape.py data/simple_rib.step
    python examples/normalize_shape.py data/escavator_arm-Assembly.step --context
    python examples/normalize_shape.py data/simple_rib.step --verbose
    python examples/normalize_shape.py data/simple_rib.step --visualize
    python examples/normalize_shape.py data/escavator_arm-Assembly.step --visualize --screenshot out.png
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalize a STEP file into a structured NormalizedShape"
    )
    parser.add_argument("path", help="Path to the STEP file")
    parser.add_argument(
        "--context",
        action="store_true",
        help="Record the assembly hierarchy for each solid",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-face details (type, area, centre, normal)",
    )
    parser.add_argument(
        "--visualize",
        action="store_true",
        help="Open an interactive 3-D window with per-face colour coding and labels",
    )
    parser.add_argument(
        "--no-labels",
        dest="labels",
        action="store_false",
        default=True,
        help="Suppress text labels in the 3-D view",
    )
    parser.add_argument(
        "--screenshot",
        default=None,
        metavar="PATH",
        help="Save a screenshot of the 3-D view to this file (implies --visualize)",
    )
    parser.add_argument("--deflection", type=float, default=0.1)
    parser.add_argument("--angle", type=float, default=0.5)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    do_visualize = args.visualize or args.screenshot is not None

    print(f"Loading:     {args.path}")
    compound = read_step_single(args.path)

    print("Normalizing shape ...")
    result = normalize_shape(compound, keep_context=args.context)

    print(f"\nExtracted {len(result.solids)} solid(s)\n")

    # ------------------------------------------------------------------ #
    # Assembly context                                                     #
    # ------------------------------------------------------------------ #
    if args.context and result.assembly_context:
        print("Assembly context (solid -> hierarchy path):")
        for node in result.assembly_context:
            if node.path:
                path_str = " > ".join(str(i) for i in node.path)
            else:
                path_str = "(direct child of root)"
            print(f"  Solid {node.solid_id:3d}  path: {path_str}")
        print()

    # ------------------------------------------------------------------ #
    # Per-solid summary                                                    #
    # ------------------------------------------------------------------ #
    for solid_data in result.solids:
        face_count = len(solid_data.faces)
        print(f"Solid {solid_data.solid_id}  ({face_count} face(s))")

        # Surface-type histogram
        type_counts: dict = {}
        for fd in solid_data.faces:
            type_counts[fd.surface_type] = type_counts.get(fd.surface_type, 0) + 1
        for surf_type, count in sorted(type_counts.items()):
            print(f"  {surf_type:<10s}: {count} face(s)")

        # Adjacency degree statistics
        degrees = [len(nb) for nb in solid_data.adjacency.values()]
        if degrees:
            avg_deg = sum(degrees) / len(degrees)
            print(f"  Adjacency  : avg degree {avg_deg:.1f}, "
                  f"min {min(degrees)}, max {max(degrees)}")

        # Per-face detail (opt-in)
        if args.verbose:
            print("  Face details:")
            for fd in solid_data.faces:
                cx, cy, cz = fd.center
                nb_ids = solid_data.adjacency[fd.face_id]
                line = (
                    f"    Face {fd.face_id:3d}  type={fd.surface_type:<10s}"
                    f"  area={fd.area:12.4f}"
                    f"  centre=({cx:8.3f}, {cy:8.3f}, {cz:8.3f})"
                    f"  neighbours={nb_ids}"
                )
                print(line)
                if fd.normal:
                    nx, ny, nz = fd.normal
                    print(f"            normal=({nx:.4f}, {ny:.4f}, {nz:.4f})")

        print()

    # ------------------------------------------------------------------ #
    # 3-D labelled visualization                                          #
    # ------------------------------------------------------------------ #
    if do_visualize:
        try:
            from visualization.viewer import HAVE_PYVISTA, plot_normalized_shape
        except ImportError:
            print("ERROR: visualization module not found.")
            return

        if not HAVE_PYVISTA:
            print("ERROR: pyvista is not installed – cannot visualize.")
            return

        solid_shapes = extract_solids(compound)

        off_screen = args.screenshot is not None
        print("Opening 3-D labelled viewer …")
        plot_normalized_shape(
            result,
            solid_shapes,
            deflection=args.deflection,
            angle=args.angle,
            show_labels=args.labels,
            off_screen=off_screen,
            screenshot_path=args.screenshot,
        )
        if args.screenshot:
            print(f"Screenshot saved to: {args.screenshot}")


if __name__ == "__main__":
    main()
