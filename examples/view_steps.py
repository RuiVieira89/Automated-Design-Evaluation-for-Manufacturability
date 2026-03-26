"""Example: plot STEP parts with the PyVista viewer."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from visualization.viewer import plot_cad_file

STEP_FILES = [
    "simple_rib.step",
    "escavator_arm-Assembly.step",
    "FlandersMake_part_NOK-Merger.step",
]


def main() -> None:
    data_dir = ROOT / "data"
    for filename in STEP_FILES:
        path = data_dir / filename
        print(f"Plotting {path}")
        plot_cad_file(str(path), off_screen=False)


if __name__ == "__main__":
    main()
