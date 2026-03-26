"""Tests for STEP reader utilities."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OCC_IMPORT_ERROR = None
try:
    from load_cad.step_reader import read_step

    HAVE_OCC = True
except Exception as exc:
    HAVE_OCC = False
    OCC_IMPORT_ERROR = exc

PYVISTA_IMPORT_ERROR = None
try:
    from visualization.viewer import HAVE_PYVISTA, plot_cad_file
except Exception as exc:
    HAVE_PYVISTA = False
    PYVISTA_IMPORT_ERROR = exc

DATA_DIR = ROOT / "data"


@unittest.skipUnless(
    HAVE_OCC,
    f"pythonocc-core not installed or failed to import: {OCC_IMPORT_ERROR}",
)
class StepReaderTests(unittest.TestCase):
    def test_read_step_files(self) -> None:
        step_files = [
            "simple_rib.step",
            "escavator_arm-Assembly.step",
            "FlandersMake_part_NOK-Merger.step",
        ]

        for filename in step_files:
            with self.subTest(filename=filename):
                path = DATA_DIR / filename
                shapes = read_step(str(path))
                self.assertTrue(shapes)
                for shape in shapes:
                    self.assertFalse(shape.IsNull())

                if HAVE_PYVISTA:
                    plot_cad_file(str(path), off_screen=True)


@unittest.skipUnless(
    HAVE_PYVISTA,
    f"pyvista not installed or failed to import: {PYVISTA_IMPORT_ERROR}",
)
class ViewerTests(unittest.TestCase):
    def test_plot_other_formats(self) -> None:
        other_files = [
            "FlandersMake_part-Merger.stl",
            "FlandersMake_part_NOK-Merger.stl",
            "cube.off",
        ]

        for filename in other_files:
            with self.subTest(filename=filename):
                path = DATA_DIR / filename
                dataset = plot_cad_file(str(path), off_screen=True)
                self.assertIsNotNone(dataset)


if __name__ == "__main__":
    unittest.main()
