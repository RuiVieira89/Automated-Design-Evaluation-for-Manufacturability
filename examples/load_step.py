"""Example script to load a STEP file and optionally tessellate it."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from load_cad.step_reader import read_step, read_step_single, tessellate_shape


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load a STEP file with pythonocc-core")
    parser.add_argument("path", help="Path to the STEP file")
    parser.add_argument(
        "--tessellate",
        action="store_true",
        help="Compute a triangle mesh from the loaded shape",
    )
    parser.add_argument(
        "--single",
        action="store_true",
        help="Return a single shape (compound if multiple roots)",
    )
    parser.add_argument("--deflection", type=float, default=0.1)
    parser.add_argument("--angle", type=float, default=0.5)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.single:
        shape = read_step_single(args.path)
        print("Loaded single shape")
        if args.tessellate:
            vertices, faces = tessellate_shape(
                shape, deflection=args.deflection, angle=args.angle
            )
            print(f"Mesh: {len(vertices)} vertices, {len(faces)} faces")
        return

    shapes = read_step(args.path)
    print(f"Loaded {len(shapes)} top-level shapes")
    if args.tessellate and shapes:
        vertices, faces = tessellate_shape(
            shapes[0], deflection=args.deflection, angle=args.angle
        )
        print(f"Mesh (first shape): {len(vertices)} vertices, {len(faces)} faces")


if __name__ == "__main__":
    main()
