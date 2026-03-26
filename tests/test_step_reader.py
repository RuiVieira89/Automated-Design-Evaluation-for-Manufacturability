"""Tests for STEP reader utilities."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from io.step_reader import read_step

    HAVE_OCC = True
except Exception:
    HAVE_OCC = False

DATA_DIR = ROOT / "data"


@unittest.skipUnless(HAVE_OCC, "pythonocc-core not installed")
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


if __name__ == "__main__":
    unittest.main()
