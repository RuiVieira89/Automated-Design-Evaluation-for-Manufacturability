"""Tests for post_process.dimensions.dimension_gather_radiusFillet.

Pure-Python unit tests (no OCC) cover _classify_angle() and data structures.
Integration tests load a real STEP file and are skipped without OCC.
"""

from __future__ import annotations

import json
import math
import sys
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from post_process.dimensions.dimension_gather_radiusFillet import (
    CylinderFeature,
    CylinderKind,
    FilletGatherResult,
    SolidFilletResult,
    _classify_angle,
    gather_fillets,
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
_SIMPLE_RIB = DATA_DIR / "simple_rib.step"


# ---------------------------------------------------------------------------
# Helpers to build synthetic data structures without OCC
# ---------------------------------------------------------------------------

def _make_feature(
    solid_id: int = 0,
    face_id: int = 0,
    kind: CylinderKind = CylinderKind.FILLET,
    radius_mm: float = 2.0,
    angle_deg: float = 90.0,
) -> CylinderFeature:
    return CylinderFeature(
        solid_id=solid_id,
        face_id=face_id,
        kind=kind,
        radius_mm=radius_mm,
        angle_deg=angle_deg,
        axis_direction=(0.0, 0.0, 1.0),
        axis_location=(0.0, 0.0, 0.0),
        center=(1.0, 2.0, 3.0),
        area=12.566,
        adjacent_face_ids=[1, 2],
    )


def _make_solid_result(
    solid_id: int = 0,
    n_fillets: int = 2,
    n_partials: int = 1,
    excluded_count: int = 3,
) -> SolidFilletResult:
    sr = SolidFilletResult(solid_id=solid_id, excluded_count=excluded_count)
    for i in range(n_fillets):
        sr.fillets.append(_make_feature(solid_id=solid_id, face_id=i, kind=CylinderKind.FILLET))
    for i in range(n_partials):
        sr.partials.append(
            _make_feature(
                solid_id=solid_id,
                face_id=n_fillets + i,
                kind=CylinderKind.PARTIAL,
                angle_deg=45.0,
            )
        )
    return sr


# ---------------------------------------------------------------------------
# _classify_angle — pure Python, no OCC
# ---------------------------------------------------------------------------

class TestClassifyAngle(unittest.TestCase):
    """Unit tests for the stateless angle classifier."""

    # ── Full circles (EXCLUDED) ──────────────────────────────────────────────

    def test_exact_360_is_excluded(self) -> None:
        self.assertEqual(_classify_angle(360.0, 5.0, 2.0), CylinderKind.EXCLUDED)

    def test_358_5_is_excluded_within_default_tol(self) -> None:
        # 360 - 2 = 358; 358.5 is still inside the exclusion band
        self.assertEqual(_classify_angle(358.5, 5.0, 2.0), CylinderKind.EXCLUDED)

    def test_358_is_excluded_at_boundary(self) -> None:
        self.assertEqual(_classify_angle(358.0, 5.0, 2.0), CylinderKind.EXCLUDED)

    def test_357_9_is_partial_just_below_full_tol(self) -> None:
        self.assertEqual(_classify_angle(357.9, 5.0, 2.0), CylinderKind.PARTIAL)

    def test_custom_full_tol_zero_only_360_excluded(self) -> None:
        self.assertEqual(_classify_angle(359.9, 5.0, 0.0), CylinderKind.PARTIAL)
        self.assertEqual(_classify_angle(360.0, 5.0, 0.0), CylinderKind.EXCLUDED)

    def test_custom_full_tol_5_deg(self) -> None:
        self.assertEqual(_classify_angle(355.5, 5.0, 5.0), CylinderKind.EXCLUDED)
        self.assertEqual(_classify_angle(354.9, 5.0, 5.0), CylinderKind.PARTIAL)

    # ── Fillets (~90°) ───────────────────────────────────────────────────────

    def test_exact_90_is_fillet(self) -> None:
        self.assertEqual(_classify_angle(90.0, 5.0, 2.0), CylinderKind.FILLET)

    def test_upper_boundary_fillet_default_tol(self) -> None:
        # 5% of 90° = 4.5°; upper bound = 94.5°
        self.assertEqual(_classify_angle(94.5, 5.0, 2.0), CylinderKind.FILLET)

    def test_lower_boundary_fillet_default_tol(self) -> None:
        # lower bound = 85.5°
        self.assertEqual(_classify_angle(85.5, 5.0, 2.0), CylinderKind.FILLET)

    def test_just_above_upper_boundary_is_partial(self) -> None:
        self.assertEqual(_classify_angle(94.6, 5.0, 2.0), CylinderKind.PARTIAL)

    def test_just_below_lower_boundary_is_partial(self) -> None:
        self.assertEqual(_classify_angle(85.4, 5.0, 2.0), CylinderKind.PARTIAL)

    def test_custom_fillet_tol_10pct(self) -> None:
        # 10% of 90° = 9°; band = [81°, 99°]
        self.assertEqual(_classify_angle(81.0, 10.0, 2.0), CylinderKind.FILLET)
        self.assertEqual(_classify_angle(99.0, 10.0, 2.0), CylinderKind.FILLET)
        self.assertEqual(_classify_angle(80.9, 10.0, 2.0), CylinderKind.PARTIAL)

    def test_custom_fillet_tol_0pct_only_exact_90(self) -> None:
        self.assertEqual(_classify_angle(90.0, 0.0, 2.0), CylinderKind.FILLET)
        self.assertEqual(_classify_angle(90.1, 0.0, 2.0), CylinderKind.PARTIAL)
        self.assertEqual(_classify_angle(89.9, 0.0, 2.0), CylinderKind.PARTIAL)

    # ── Partial cylinders ────────────────────────────────────────────────────

    def test_45_is_partial(self) -> None:
        self.assertEqual(_classify_angle(45.0, 5.0, 2.0), CylinderKind.PARTIAL)

    def test_180_is_partial(self) -> None:
        self.assertEqual(_classify_angle(180.0, 5.0, 2.0), CylinderKind.PARTIAL)

    def test_270_is_partial(self) -> None:
        self.assertEqual(_classify_angle(270.0, 5.0, 2.0), CylinderKind.PARTIAL)

    def test_1_is_partial(self) -> None:
        self.assertEqual(_classify_angle(1.0, 5.0, 2.0), CylinderKind.PARTIAL)

    def test_120_is_partial(self) -> None:
        self.assertEqual(_classify_angle(120.0, 5.0, 2.0), CylinderKind.PARTIAL)

    # ── Return type ──────────────────────────────────────────────────────────

    def test_returns_cylinder_kind_instance(self) -> None:
        for angle in (45.0, 90.0, 360.0):
            with self.subTest(angle=angle):
                result = _classify_angle(angle, 5.0, 2.0)
                self.assertIsInstance(result, CylinderKind)


# ---------------------------------------------------------------------------
# CylinderKind enum
# ---------------------------------------------------------------------------

class TestCylinderKind(unittest.TestCase):

    def test_values_are_strings(self) -> None:
        for member in CylinderKind:
            self.assertIsInstance(member.value, str)

    def test_str_subclass(self) -> None:
        # CylinderKind inherits from str
        self.assertIsInstance(CylinderKind.FILLET, str)

    def test_expected_members(self) -> None:
        values = {m.value for m in CylinderKind}
        self.assertIn("excluded", values)
        self.assertIn("fillet", values)
        self.assertIn("partial", values)


# ---------------------------------------------------------------------------
# CylinderFeature data class
# ---------------------------------------------------------------------------

class TestCylinderFeature(unittest.TestCase):

    def setUp(self) -> None:
        self.f = _make_feature(solid_id=1, face_id=5, radius_mm=3.14, angle_deg=90.0)

    def test_fields_stored_correctly(self) -> None:
        self.assertEqual(self.f.solid_id, 1)
        self.assertEqual(self.f.face_id, 5)
        self.assertAlmostEqual(self.f.radius_mm, 3.14)
        self.assertAlmostEqual(self.f.angle_deg, 90.0)
        self.assertEqual(self.f.kind, CylinderKind.FILLET)

    def test_as_dict_has_required_keys(self) -> None:
        d = self.f.as_dict()
        required = {
            "solid_id", "face_id", "kind", "radius_mm", "angle_deg",
            "axis_direction", "axis_location", "center", "area",
            "adjacent_face_ids",
        }
        self.assertEqual(set(d.keys()), required)

    def test_as_dict_kind_is_string(self) -> None:
        d = self.f.as_dict()
        self.assertIsInstance(d["kind"], str)
        self.assertEqual(d["kind"], "fillet")

    def test_as_dict_numeric_fields(self) -> None:
        d = self.f.as_dict()
        self.assertAlmostEqual(d["radius_mm"], 3.14)
        self.assertAlmostEqual(d["angle_deg"], 90.0)

    def test_as_dict_is_json_serializable(self) -> None:
        d = self.f.as_dict()
        dumped = json.dumps(d)
        self.assertIsInstance(dumped, str)

    def test_adjacent_face_ids_default_list(self) -> None:
        f = CylinderFeature(
            solid_id=0, face_id=0, kind=CylinderKind.PARTIAL,
            radius_mm=1.0, angle_deg=45.0,
            axis_direction=(1.0, 0.0, 0.0),
            axis_location=(0.0, 0.0, 0.0),
            center=(0.0, 0.0, 0.0),
            area=1.0,
        )
        self.assertIsInstance(f.adjacent_face_ids, list)
        self.assertEqual(f.adjacent_face_ids, [])

    def test_partial_feature_as_dict_kind_value(self) -> None:
        f = _make_feature(kind=CylinderKind.PARTIAL, angle_deg=45.0)
        self.assertEqual(f.as_dict()["kind"], "partial")

    def test_excluded_feature_as_dict_kind_value(self) -> None:
        f = _make_feature(kind=CylinderKind.EXCLUDED, angle_deg=360.0)
        self.assertEqual(f.as_dict()["kind"], "excluded")


# ---------------------------------------------------------------------------
# SolidFilletResult
# ---------------------------------------------------------------------------

class TestSolidFilletResult(unittest.TestCase):

    def setUp(self) -> None:
        self.sr = _make_solid_result(solid_id=2, n_fillets=3, n_partials=2, excluded_count=5)

    def test_solid_id_stored(self) -> None:
        self.assertEqual(self.sr.solid_id, 2)

    def test_fillet_list_length(self) -> None:
        self.assertEqual(len(self.sr.fillets), 3)

    def test_partial_list_length(self) -> None:
        self.assertEqual(len(self.sr.partials), 2)

    def test_excluded_count(self) -> None:
        self.assertEqual(self.sr.excluded_count, 5)

    def test_all_candidates_combines_fillets_and_partials(self) -> None:
        candidates = self.sr.all_candidates
        self.assertEqual(len(candidates), 5)  # 3 fillets + 2 partials

    def test_all_candidates_contains_fillets_first(self) -> None:
        candidates = self.sr.all_candidates
        for c in candidates[:3]:
            self.assertEqual(c.kind, CylinderKind.FILLET)
        for c in candidates[3:]:
            self.assertEqual(c.kind, CylinderKind.PARTIAL)

    def test_empty_solid_result(self) -> None:
        sr = SolidFilletResult(solid_id=0)
        self.assertEqual(len(sr.fillets), 0)
        self.assertEqual(len(sr.partials), 0)
        self.assertEqual(sr.excluded_count, 0)
        self.assertEqual(sr.all_candidates, [])

    def test_as_dict_keys(self) -> None:
        d = self.sr.as_dict()
        self.assertIn("solid_id", d)
        self.assertIn("fillets", d)
        self.assertIn("partials", d)
        self.assertIn("excluded_count", d)

    def test_as_dict_solid_id_value(self) -> None:
        self.assertEqual(self.sr.as_dict()["solid_id"], 2)

    def test_as_dict_fillets_is_list_of_dicts(self) -> None:
        d = self.sr.as_dict()
        self.assertIsInstance(d["fillets"], list)
        for item in d["fillets"]:
            self.assertIsInstance(item, dict)

    def test_as_dict_is_json_serializable(self) -> None:
        dumped = json.dumps(self.sr.as_dict())
        self.assertIsInstance(dumped, str)


# ---------------------------------------------------------------------------
# FilletGatherResult
# ---------------------------------------------------------------------------

class TestFilletGatherResult(unittest.TestCase):

    def _make_result(self) -> FilletGatherResult:
        sr0 = _make_solid_result(solid_id=0, n_fillets=2, n_partials=1, excluded_count=3)
        sr1 = _make_solid_result(solid_id=1, n_fillets=1, n_partials=2, excluded_count=0)
        return FilletGatherResult(
            solids=[sr0, sr1],
            fillet_angle_tol_pct=5.0,
            full_circle_tol_deg=2.0,
        )

    def test_total_fillets(self) -> None:
        r = self._make_result()
        self.assertEqual(r.total_fillets, 3)

    def test_total_partials(self) -> None:
        r = self._make_result()
        self.assertEqual(r.total_partials, 3)

    def test_total_excluded(self) -> None:
        r = self._make_result()
        self.assertEqual(r.total_excluded, 3)

    def test_all_fillets_length(self) -> None:
        r = self._make_result()
        self.assertEqual(len(r.all_fillets), 3)

    def test_all_fillets_kind(self) -> None:
        r = self._make_result()
        for f in r.all_fillets:
            self.assertEqual(f.kind, CylinderKind.FILLET)

    def test_all_partials_length(self) -> None:
        r = self._make_result()
        self.assertEqual(len(r.all_partials), 3)

    def test_all_partials_kind(self) -> None:
        r = self._make_result()
        for p in r.all_partials:
            self.assertEqual(p.kind, CylinderKind.PARTIAL)

    def test_tolerance_parameters_stored(self) -> None:
        r = self._make_result()
        self.assertAlmostEqual(r.fillet_angle_tol_pct, 5.0)
        self.assertAlmostEqual(r.full_circle_tol_deg, 2.0)

    def test_empty_result(self) -> None:
        r = FilletGatherResult(solids=[], fillet_angle_tol_pct=5.0, full_circle_tol_deg=2.0)
        self.assertEqual(r.total_fillets, 0)
        self.assertEqual(r.total_partials, 0)
        self.assertEqual(r.total_excluded, 0)
        self.assertEqual(r.all_fillets, [])
        self.assertEqual(r.all_partials, [])

    def test_as_dict_has_required_keys(self) -> None:
        r = self._make_result()
        d = r.as_dict()
        required = {
            "fillet_angle_tol_pct", "full_circle_tol_deg",
            "total_fillets", "total_partials", "total_excluded", "solids",
        }
        self.assertEqual(set(d.keys()), required)

    def test_as_dict_aggregate_counts(self) -> None:
        r = self._make_result()
        d = r.as_dict()
        self.assertEqual(d["total_fillets"], 3)
        self.assertEqual(d["total_partials"], 3)
        self.assertEqual(d["total_excluded"], 3)

    def test_as_dict_solids_list_length(self) -> None:
        r = self._make_result()
        self.assertEqual(len(r.as_dict()["solids"]), 2)

    def test_as_dict_is_json_serializable(self) -> None:
        r = self._make_result()
        dumped = json.dumps(r.as_dict())
        self.assertIsInstance(dumped, str)


# ---------------------------------------------------------------------------
# Integration tests (OCC required)
# ---------------------------------------------------------------------------

@unittest.skipUnless(HAVE_OCC, f"pythonocc-core not available: {OCC_IMPORT_ERROR}")
class TestGatherFilletsIntegration(unittest.TestCase):
    """Integration tests that load real STEP files."""

    @classmethod
    def setUpClass(cls) -> None:
        compound = read_step_single(str(_FLANDERSMAKE))
        cls.normalized = normalize_shape(compound)
        cls.solids = extract_solids(compound)
        cls.result = gather_fillets(cls.normalized, cls.solids)

    # ── Return type and shape ────────────────────────────────────────────────

    def test_returns_fillet_gather_result(self) -> None:
        self.assertIsInstance(self.result, FilletGatherResult)

    def test_solid_count_matches_normalized(self) -> None:
        self.assertEqual(len(self.result.solids), len(self.normalized.solids))

    def test_solid_results_are_solid_fillet_result(self) -> None:
        for sr in self.result.solids:
            with self.subTest(solid_id=sr.solid_id):
                self.assertIsInstance(sr, SolidFilletResult)

    def test_solid_ids_match_normalized_order(self) -> None:
        for idx, sr in enumerate(self.result.solids):
            with self.subTest(idx=idx):
                self.assertEqual(sr.solid_id, idx)

    # ── CylinderFeature invariants ───────────────────────────────────────────

    def test_all_features_have_positive_radius(self) -> None:
        for sr in self.result.solids:
            for f in sr.fillets + sr.partials:
                with self.subTest(solid_id=f.solid_id, face_id=f.face_id):
                    self.assertGreater(f.radius_mm, 0.0)

    def test_all_features_have_valid_angle(self) -> None:
        for sr in self.result.solids:
            for f in sr.fillets + sr.partials:
                with self.subTest(solid_id=f.solid_id, face_id=f.face_id):
                    self.assertGreater(f.angle_deg, 0.0)
                    self.assertLessEqual(f.angle_deg, 360.0)

    def test_fillet_features_have_angle_near_90(self) -> None:
        tol = self.result.fillet_angle_tol_pct
        band = 90.0 * (tol / 100.0)
        for f in self.result.all_fillets:
            with self.subTest(solid_id=f.solid_id, face_id=f.face_id):
                self.assertAlmostEqual(f.angle_deg, 90.0, delta=band + 0.01)

    def test_excluded_features_not_in_fillets_or_partials(self) -> None:
        for sr in self.result.solids:
            for f in sr.fillets:
                self.assertNotEqual(f.kind, CylinderKind.EXCLUDED)
            for p in sr.partials:
                self.assertNotEqual(p.kind, CylinderKind.EXCLUDED)

    def test_fillet_kind_is_fillet(self) -> None:
        for f in self.result.all_fillets:
            self.assertEqual(f.kind, CylinderKind.FILLET)

    def test_partial_kind_is_partial(self) -> None:
        for p in self.result.all_partials:
            self.assertEqual(p.kind, CylinderKind.PARTIAL)

    def test_all_features_have_valid_kind(self) -> None:
        valid_kinds = set(CylinderKind)
        for sr in self.result.solids:
            for f in sr.fillets + sr.partials:
                with self.subTest(solid_id=f.solid_id, face_id=f.face_id):
                    self.assertIn(f.kind, valid_kinds)

    # ── Back-reference validity ──────────────────────────────────────────────

    def test_solid_id_is_valid_index_into_normalized(self) -> None:
        n_solids = len(self.normalized.solids)
        for sr in self.result.solids:
            for f in sr.fillets + sr.partials:
                with self.subTest(solid_id=f.solid_id, face_id=f.face_id):
                    self.assertGreaterEqual(f.solid_id, 0)
                    self.assertLess(f.solid_id, n_solids)

    def test_face_id_is_valid_index_into_solid(self) -> None:
        for sr in self.result.solids:
            solid_data = self.normalized.solids[sr.solid_id]
            n_faces = len(solid_data.faces)
            for f in sr.fillets + sr.partials:
                with self.subTest(solid_id=f.solid_id, face_id=f.face_id):
                    self.assertGreaterEqual(f.face_id, 0)
                    self.assertLess(f.face_id, n_faces)

    def test_adjacent_face_ids_are_valid_indices(self) -> None:
        for sr in self.result.solids:
            solid_data = self.normalized.solids[sr.solid_id]
            n_faces = len(solid_data.faces)
            for f in sr.fillets + sr.partials:
                for adj_id in f.adjacent_face_ids:
                    with self.subTest(solid_id=f.solid_id, face_id=f.face_id, adj=adj_id):
                        self.assertGreaterEqual(adj_id, 0)
                        self.assertLess(adj_id, n_faces)

    def test_center_is_3_tuple_of_floats(self) -> None:
        for f in self.result.all_fillets + self.result.all_partials:
            self.assertEqual(len(f.center), 3)
            for v in f.center:
                self.assertIsInstance(v, float)

    def test_axis_direction_is_unit_vector(self) -> None:
        for f in self.result.all_fillets + self.result.all_partials:
            dx, dy, dz = f.axis_direction
            length = math.sqrt(dx**2 + dy**2 + dz**2)
            with self.subTest(solid_id=f.solid_id, face_id=f.face_id):
                self.assertAlmostEqual(length, 1.0, places=5)

    def test_area_is_positive(self) -> None:
        for f in self.result.all_fillets + self.result.all_partials:
            with self.subTest(solid_id=f.solid_id, face_id=f.face_id):
                self.assertGreater(f.area, 0.0)

    # ── Aggregate counts are consistent ─────────────────────────────────────

    def test_total_fillets_equals_sum_of_per_solid(self) -> None:
        expected = sum(len(sr.fillets) for sr in self.result.solids)
        self.assertEqual(self.result.total_fillets, expected)

    def test_total_partials_equals_sum_of_per_solid(self) -> None:
        expected = sum(len(sr.partials) for sr in self.result.solids)
        self.assertEqual(self.result.total_partials, expected)

    def test_total_excluded_equals_sum_of_per_solid(self) -> None:
        expected = sum(sr.excluded_count for sr in self.result.solids)
        self.assertEqual(self.result.total_excluded, expected)

    # ── Error handling ───────────────────────────────────────────────────────

    def test_length_mismatch_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            gather_fillets(self.normalized, self.solids[:-1])

    # ── Serialization ────────────────────────────────────────────────────────

    def test_as_dict_is_json_serializable(self) -> None:
        dumped = json.dumps(self.result.as_dict())
        self.assertIsInstance(dumped, str)

    # ── Custom tolerance parameters ──────────────────────────────────────────

    def test_fillet_tol_pct_stored_in_result(self) -> None:
        result = gather_fillets(
            self.normalized, self.solids,
            fillet_angle_tol_pct=10.0,
            full_circle_tol_deg=3.0,
        )
        self.assertAlmostEqual(result.fillet_angle_tol_pct, 10.0)
        self.assertAlmostEqual(result.full_circle_tol_deg, 3.0)

    def test_wider_fillet_tol_finds_at_least_as_many_fillets(self) -> None:
        tight = gather_fillets(self.normalized, self.solids, fillet_angle_tol_pct=1.0)
        wide = gather_fillets(self.normalized, self.solids, fillet_angle_tol_pct=20.0)
        self.assertGreaterEqual(wide.total_fillets, tight.total_fillets)


@unittest.skipUnless(HAVE_OCC, f"pythonocc-core not available: {OCC_IMPORT_ERROR}")
class TestGatherFilletsSimpleRib(unittest.TestCase):
    """Integration tests on simple_rib.step (single solid, known geometry)."""

    @classmethod
    def setUpClass(cls) -> None:
        compound = read_step_single(str(_SIMPLE_RIB))
        cls.normalized = normalize_shape(compound)
        cls.solids = extract_solids(compound)
        cls.result = gather_fillets(cls.normalized, cls.solids)

    def test_at_least_one_solid_analysed(self) -> None:
        self.assertGreater(len(self.result.solids), 0)

    def test_no_negative_excluded_count(self) -> None:
        for sr in self.result.solids:
            self.assertGreaterEqual(sr.excluded_count, 0)

    def test_solid_result_solid_ids_sequential(self) -> None:
        for idx, sr in enumerate(self.result.solids):
            self.assertEqual(sr.solid_id, idx)

    def test_all_face_ids_are_non_negative(self) -> None:
        for sr in self.result.solids:
            for f in sr.fillets + sr.partials:
                self.assertGreaterEqual(f.face_id, 0)


if __name__ == "__main__":
    unittest.main()
