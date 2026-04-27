"""Tests for post_process.dimensions.dimension_gather_diameterHole.

Pure-Python unit tests (no OCC) cover _is_full_circle() and data structures.
Integration tests load a real STEP file and are skipped without OCC.
"""

from __future__ import annotations

import json
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from post_process.dimensions.dimension_gather_diameterHole import (
    HoleDiameterFeature,
    HoleDiameterGatherResult,
    SolidHoleResult,
    _is_full_circle,
    gather_hole_diameters,
)

OCC_IMPORT_ERROR = None
try:
    from load_cad.step_reader import read_step_single
    from post_process.shape_normalizer import extract_solids, normalize_shape

    HAVE_OCC = True
except Exception as exc:
    HAVE_OCC = False
    OCC_IMPORT_ERROR = exc

DATA_DIR = ROOT / "data"
_FLANDERSMAKE = DATA_DIR / "FlandersMake_part_NOK-Merger.step"


# ---------------------------------------------------------------------------
# Helpers to build synthetic data structures without OCC
# ---------------------------------------------------------------------------

def _make_feature(
    solid_id: int = 0,
    face_id: int = 0,
    diameter_mm: float = 10.0,
    angle_deg: float = 360.0,
) -> HoleDiameterFeature:
    return HoleDiameterFeature(
        solid_id=solid_id,
        face_id=face_id,
        diameter_mm=diameter_mm,
        radius_mm=diameter_mm / 2.0,
        angle_deg=angle_deg,
        axis_direction=(0.0, 0.0, 1.0),
        axis_location=(0.0, 0.0, 0.0),
        center=(5.0, 5.0, 0.0),
        area=math.pi * (diameter_mm / 2.0) * 10.0,
        adjacent_face_ids=[1, 2],
    )


def _make_solid_result(
    solid_id: int = 0,
    n_holes: int = 2,
    excluded_count: int = 1,
) -> SolidHoleResult:
    sr = SolidHoleResult(solid_id=solid_id, excluded_count=excluded_count)
    for i in range(n_holes):
        sr.holes.append(
            _make_feature(solid_id=solid_id, face_id=i, diameter_mm=float(5 + i))
        )
    return sr


# ---------------------------------------------------------------------------
# _is_full_circle — pure Python, no OCC
# ---------------------------------------------------------------------------

class TestIsFullCircle(unittest.TestCase):
    """Unit tests for the stateless full-circle classifier."""

    # ── Exact 360° ──────────────────────────────────────────────────────────

    def test_360_with_zero_tol_is_full(self) -> None:
        self.assertTrue(_is_full_circle(360.0, 0.0))

    def test_360_with_5pct_tol_is_full(self) -> None:
        self.assertTrue(_is_full_circle(360.0, 5.0))

    # ── At threshold boundary (tol=5% → threshold=342°) ─────────────────────

    def test_342_at_threshold_is_full(self) -> None:
        # 360 * (1 - 5/100) = 342.0
        self.assertTrue(_is_full_circle(342.0, 5.0))

    def test_just_below_threshold_is_not_full(self) -> None:
        self.assertFalse(_is_full_circle(341.9, 5.0))

    # ── Seam-split cylinder (just below 360°) ────────────────────────────────

    def test_359_5_with_5pct_tol_is_full(self) -> None:
        self.assertTrue(_is_full_circle(359.5, 5.0))

    def test_359_5_with_zero_tol_is_not_full(self) -> None:
        self.assertFalse(_is_full_circle(359.5, 0.0))

    # ── Custom tolerances ────────────────────────────────────────────────────

    def test_tol_10pct_threshold_is_324_degrees(self) -> None:
        # 360 * (1 - 10/100) = 324.0
        self.assertTrue(_is_full_circle(324.0, 10.0))
        self.assertFalse(_is_full_circle(323.9, 10.0))

    def test_tol_0pct_only_exact_360_passes(self) -> None:
        self.assertTrue(_is_full_circle(360.0, 0.0))
        self.assertFalse(_is_full_circle(359.9, 0.0))

    def test_tol_1pct_threshold_is_356_4(self) -> None:
        # 360 * (1 - 1/100) = 356.4
        self.assertTrue(_is_full_circle(356.4, 1.0))
        self.assertFalse(_is_full_circle(356.3, 1.0))

    # ── Partial cylinders (not full) ─────────────────────────────────────────

    def test_90_is_not_full(self) -> None:
        self.assertFalse(_is_full_circle(90.0, 5.0))

    def test_180_is_not_full(self) -> None:
        self.assertFalse(_is_full_circle(180.0, 5.0))

    def test_270_is_not_full(self) -> None:
        self.assertFalse(_is_full_circle(270.0, 5.0))

    def test_1_degree_is_not_full(self) -> None:
        self.assertFalse(_is_full_circle(1.0, 5.0))

    # ── Return type ──────────────────────────────────────────────────────────

    def test_returns_bool_for_all_cases(self) -> None:
        for angle in (90.0, 342.0, 360.0):
            with self.subTest(angle=angle):
                result = _is_full_circle(angle, 5.0)
                self.assertIsInstance(result, bool)


# ---------------------------------------------------------------------------
# HoleDiameterFeature data class
# ---------------------------------------------------------------------------

class TestHoleDiameterFeature(unittest.TestCase):

    def setUp(self) -> None:
        self.h = _make_feature(solid_id=1, face_id=3, diameter_mm=8.0, angle_deg=360.0)

    def test_fields_stored_correctly(self) -> None:
        self.assertEqual(self.h.solid_id, 1)
        self.assertEqual(self.h.face_id, 3)
        self.assertAlmostEqual(self.h.diameter_mm, 8.0)
        self.assertAlmostEqual(self.h.radius_mm, 4.0)
        self.assertAlmostEqual(self.h.angle_deg, 360.0)

    def test_diameter_is_twice_radius(self) -> None:
        self.assertAlmostEqual(self.h.diameter_mm, 2.0 * self.h.radius_mm)

    def test_as_dict_has_required_keys(self) -> None:
        d = self.h.as_dict()
        required = {
            "solid_id", "face_id", "diameter_mm", "radius_mm", "angle_deg",
            "axis_direction", "axis_location", "center", "area",
            "adjacent_face_ids",
        }
        self.assertEqual(set(d.keys()), required)

    def test_as_dict_diameter_value(self) -> None:
        self.assertAlmostEqual(self.h.as_dict()["diameter_mm"], 8.0)

    def test_as_dict_radius_value(self) -> None:
        self.assertAlmostEqual(self.h.as_dict()["radius_mm"], 4.0)

    def test_as_dict_diameter_twice_radius(self) -> None:
        d = self.h.as_dict()
        self.assertAlmostEqual(d["diameter_mm"], 2.0 * d["radius_mm"])

    def test_as_dict_is_json_serializable(self) -> None:
        dumped = json.dumps(self.h.as_dict())
        self.assertIsInstance(dumped, str)

    def test_adjacent_face_ids_default_empty(self) -> None:
        h = HoleDiameterFeature(
            solid_id=0, face_id=0,
            diameter_mm=6.0, radius_mm=3.0, angle_deg=360.0,
            axis_direction=(0.0, 0.0, 1.0),
            axis_location=(0.0, 0.0, 0.0),
            center=(0.0, 0.0, 0.0),
            area=1.0,
        )
        self.assertIsInstance(h.adjacent_face_ids, list)
        self.assertEqual(h.adjacent_face_ids, [])

    def test_various_diameters(self) -> None:
        for d in (4.0, 6.35, 10.0, 25.4):
            with self.subTest(diameter=d):
                h = _make_feature(diameter_mm=d)
                self.assertAlmostEqual(h.diameter_mm, d)
                self.assertAlmostEqual(h.radius_mm, d / 2.0)


# ---------------------------------------------------------------------------
# SolidHoleResult
# ---------------------------------------------------------------------------

class TestSolidHoleResult(unittest.TestCase):

    def setUp(self) -> None:
        self.sr = _make_solid_result(solid_id=2, n_holes=3, excluded_count=4)

    def test_solid_id_stored(self) -> None:
        self.assertEqual(self.sr.solid_id, 2)

    def test_holes_list_length(self) -> None:
        self.assertEqual(len(self.sr.holes), 3)

    def test_excluded_count(self) -> None:
        self.assertEqual(self.sr.excluded_count, 4)

    def test_empty_solid_result(self) -> None:
        sr = SolidHoleResult(solid_id=0)
        self.assertEqual(len(sr.holes), 0)
        self.assertEqual(sr.excluded_count, 0)

    def test_as_dict_keys(self) -> None:
        d = self.sr.as_dict()
        self.assertIn("solid_id", d)
        self.assertIn("holes", d)
        self.assertIn("excluded_count", d)

    def test_as_dict_solid_id_value(self) -> None:
        self.assertEqual(self.sr.as_dict()["solid_id"], 2)

    def test_as_dict_holes_is_list_of_dicts(self) -> None:
        d = self.sr.as_dict()
        self.assertIsInstance(d["holes"], list)
        for item in d["holes"]:
            self.assertIsInstance(item, dict)

    def test_as_dict_excluded_count_value(self) -> None:
        self.assertEqual(self.sr.as_dict()["excluded_count"], 4)

    def test_as_dict_is_json_serializable(self) -> None:
        dumped = json.dumps(self.sr.as_dict())
        self.assertIsInstance(dumped, str)

    def test_holes_contain_hole_diameter_features(self) -> None:
        for h in self.sr.holes:
            self.assertIsInstance(h, HoleDiameterFeature)


# ---------------------------------------------------------------------------
# HoleDiameterGatherResult
# ---------------------------------------------------------------------------

class TestHoleDiameterGatherResult(unittest.TestCase):

    def _make_result(self) -> HoleDiameterGatherResult:
        sr0 = _make_solid_result(solid_id=0, n_holes=2, excluded_count=1)
        sr1 = _make_solid_result(solid_id=1, n_holes=3, excluded_count=0)
        return HoleDiameterGatherResult(
            solids=[sr0, sr1],
            full_circle_tol_pct=5.0,
        )

    def test_total_holes(self) -> None:
        r = self._make_result()
        self.assertEqual(r.total_holes, 5)

    def test_total_excluded(self) -> None:
        r = self._make_result()
        self.assertEqual(r.total_excluded, 1)

    def test_all_holes_length(self) -> None:
        r = self._make_result()
        self.assertEqual(len(r.all_holes), 5)

    def test_all_holes_are_hole_diameter_features(self) -> None:
        r = self._make_result()
        for h in r.all_holes:
            self.assertIsInstance(h, HoleDiameterFeature)

    def test_tolerance_stored(self) -> None:
        r = self._make_result()
        self.assertAlmostEqual(r.full_circle_tol_pct, 5.0)

    def test_empty_result(self) -> None:
        r = HoleDiameterGatherResult(solids=[], full_circle_tol_pct=5.0)
        self.assertEqual(r.total_holes, 0)
        self.assertEqual(r.total_excluded, 0)
        self.assertEqual(r.all_holes, [])

    def test_as_dict_has_required_keys(self) -> None:
        r = self._make_result()
        d = r.as_dict()
        required = {
            "full_circle_tol_pct", "total_holes", "total_excluded", "solids",
        }
        self.assertEqual(set(d.keys()), required)

    def test_as_dict_aggregate_counts(self) -> None:
        r = self._make_result()
        d = r.as_dict()
        self.assertEqual(d["total_holes"], 5)
        self.assertEqual(d["total_excluded"], 1)

    def test_as_dict_solids_list_length(self) -> None:
        r = self._make_result()
        self.assertEqual(len(r.as_dict()["solids"]), 2)

    def test_as_dict_is_json_serializable(self) -> None:
        r = self._make_result()
        dumped = json.dumps(r.as_dict())
        self.assertIsInstance(dumped, str)

    def test_all_holes_order_matches_solid_order(self) -> None:
        r = self._make_result()
        solid_ids = [h.solid_id for h in r.all_holes]
        # solid 0 holes come before solid 1 holes
        self.assertEqual(solid_ids[:2], [0, 0])
        self.assertEqual(solid_ids[2:], [1, 1, 1])


# ---------------------------------------------------------------------------
# Integration tests (OCC required)
# ---------------------------------------------------------------------------

@unittest.skipUnless(HAVE_OCC, f"pythonocc-core not available: {OCC_IMPORT_ERROR}")
class TestGatherHoleDiametersIntegration(unittest.TestCase):
    """Integration tests that load a real STEP file."""

    @classmethod
    def setUpClass(cls) -> None:
        compound = read_step_single(str(_FLANDERSMAKE))
        cls.normalized = normalize_shape(compound)
        cls.solids = extract_solids(compound)
        cls.result = gather_hole_diameters(cls.normalized, cls.solids)

    # ── Return type and shape ────────────────────────────────────────────────

    def test_returns_hole_diameter_gather_result(self) -> None:
        self.assertIsInstance(self.result, HoleDiameterGatherResult)

    def test_solid_count_matches_normalized(self) -> None:
        self.assertEqual(len(self.result.solids), len(self.normalized.solids))

    def test_solid_results_are_solid_hole_result(self) -> None:
        for sr in self.result.solids:
            with self.subTest(solid_id=sr.solid_id):
                self.assertIsInstance(sr, SolidHoleResult)

    def test_solid_ids_match_normalized_order(self) -> None:
        for idx, sr in enumerate(self.result.solids):
            with self.subTest(idx=idx):
                self.assertEqual(sr.solid_id, idx)

    def test_at_least_one_hole_found(self) -> None:
        # FlandersMake NOK part has drilled holes
        self.assertGreater(self.result.total_holes, 0)

    # ── HoleDiameterFeature invariants ───────────────────────────────────────

    def test_all_holes_have_positive_diameter(self) -> None:
        for h in self.result.all_holes:
            with self.subTest(solid_id=h.solid_id, face_id=h.face_id):
                self.assertGreater(h.diameter_mm, 0.0)

    def test_all_holes_diameter_is_twice_radius(self) -> None:
        for h in self.result.all_holes:
            with self.subTest(solid_id=h.solid_id, face_id=h.face_id):
                self.assertAlmostEqual(h.diameter_mm, 2.0 * h.radius_mm, places=6)

    def test_all_holes_have_angle_above_threshold(self) -> None:
        threshold = 360.0 * (1.0 - self.result.full_circle_tol_pct / 100.0)
        for h in self.result.all_holes:
            with self.subTest(solid_id=h.solid_id, face_id=h.face_id):
                self.assertGreaterEqual(h.angle_deg, threshold - 0.01)

    def test_all_holes_have_valid_angle_range(self) -> None:
        for h in self.result.all_holes:
            with self.subTest(solid_id=h.solid_id, face_id=h.face_id):
                self.assertGreater(h.angle_deg, 0.0)
                self.assertLessEqual(h.angle_deg, 360.0)

    def test_axis_direction_is_unit_vector(self) -> None:
        for h in self.result.all_holes:
            dx, dy, dz = h.axis_direction
            length = math.sqrt(dx**2 + dy**2 + dz**2)
            with self.subTest(solid_id=h.solid_id, face_id=h.face_id):
                self.assertAlmostEqual(length, 1.0, places=5)

    def test_area_is_positive(self) -> None:
        for h in self.result.all_holes:
            with self.subTest(solid_id=h.solid_id, face_id=h.face_id):
                self.assertGreater(h.area, 0.0)

    def test_center_is_3_tuple_of_floats(self) -> None:
        for h in self.result.all_holes:
            self.assertEqual(len(h.center), 3)
            for v in h.center:
                self.assertIsInstance(v, float)

    # ── Back-reference validity ──────────────────────────────────────────────

    def test_solid_id_is_valid_index_into_normalized(self) -> None:
        n_solids = len(self.normalized.solids)
        for h in self.result.all_holes:
            with self.subTest(solid_id=h.solid_id, face_id=h.face_id):
                self.assertGreaterEqual(h.solid_id, 0)
                self.assertLess(h.solid_id, n_solids)

    def test_face_id_is_valid_index_into_solid(self) -> None:
        for sr in self.result.solids:
            solid_data = self.normalized.solids[sr.solid_id]
            n_faces = len(solid_data.faces)
            for h in sr.holes:
                with self.subTest(solid_id=h.solid_id, face_id=h.face_id):
                    self.assertGreaterEqual(h.face_id, 0)
                    self.assertLess(h.face_id, n_faces)

    def test_adjacent_face_ids_are_valid_indices(self) -> None:
        for sr in self.result.solids:
            solid_data = self.normalized.solids[sr.solid_id]
            n_faces = len(solid_data.faces)
            for h in sr.holes:
                for adj_id in h.adjacent_face_ids:
                    with self.subTest(solid_id=h.solid_id, face_id=h.face_id, adj=adj_id):
                        self.assertGreaterEqual(adj_id, 0)
                        self.assertLess(adj_id, n_faces)

    def test_referenced_face_in_normalized_is_cylinder(self) -> None:
        for h in self.result.all_holes:
            face_data = self.normalized.solids[h.solid_id].faces[h.face_id]
            with self.subTest(solid_id=h.solid_id, face_id=h.face_id):
                self.assertEqual(face_data.surface_type, "Cylinder")

    def test_center_matches_normalized_face_center(self) -> None:
        for h in self.result.all_holes:
            face_data = self.normalized.solids[h.solid_id].faces[h.face_id]
            with self.subTest(solid_id=h.solid_id, face_id=h.face_id):
                self.assertAlmostEqual(h.center[0], face_data.center[0], places=6)
                self.assertAlmostEqual(h.center[1], face_data.center[1], places=6)
                self.assertAlmostEqual(h.center[2], face_data.center[2], places=6)

    def test_area_matches_normalized_face_area(self) -> None:
        for h in self.result.all_holes:
            face_data = self.normalized.solids[h.solid_id].faces[h.face_id]
            with self.subTest(solid_id=h.solid_id, face_id=h.face_id):
                self.assertAlmostEqual(h.area, face_data.area, places=4)

    # ── Aggregate counts are consistent ─────────────────────────────────────

    def test_total_holes_equals_sum_of_per_solid(self) -> None:
        expected = sum(len(sr.holes) for sr in self.result.solids)
        self.assertEqual(self.result.total_holes, expected)

    def test_total_excluded_equals_sum_of_per_solid(self) -> None:
        expected = sum(sr.excluded_count for sr in self.result.solids)
        self.assertEqual(self.result.total_excluded, expected)

    def test_no_negative_excluded_counts(self) -> None:
        for sr in self.result.solids:
            self.assertGreaterEqual(sr.excluded_count, 0)

    # ── Error handling ───────────────────────────────────────────────────────

    def test_length_mismatch_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            gather_hole_diameters(self.normalized, self.solids[:-1])

    # ── Serialization ────────────────────────────────────────────────────────

    def test_as_dict_is_json_serializable(self) -> None:
        dumped = json.dumps(self.result.as_dict())
        self.assertIsInstance(dumped, str)

    # ── Tolerance parameter effects ──────────────────────────────────────────

    def test_tolerance_stored_in_result(self) -> None:
        result = gather_hole_diameters(
            self.normalized, self.solids,
            full_circle_tol_pct=10.0,
        )
        self.assertAlmostEqual(result.full_circle_tol_pct, 10.0)

    def test_wider_tol_finds_at_least_as_many_holes(self) -> None:
        tight = gather_hole_diameters(
            self.normalized, self.solids, full_circle_tol_pct=0.1
        )
        wide = gather_hole_diameters(
            self.normalized, self.solids, full_circle_tol_pct=10.0
        )
        self.assertGreaterEqual(wide.total_holes, tight.total_holes)

    def test_zero_tol_gives_subset_of_default_tol(self) -> None:
        zero_tol = gather_hole_diameters(
            self.normalized, self.solids, full_circle_tol_pct=0.0
        )
        default = gather_hole_diameters(
            self.normalized, self.solids, full_circle_tol_pct=5.0
        )
        self.assertLessEqual(zero_tol.total_holes, default.total_holes)


if __name__ == "__main__":
    unittest.main()
