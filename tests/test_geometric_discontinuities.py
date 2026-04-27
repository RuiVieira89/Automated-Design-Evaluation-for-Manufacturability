"""Tests for post_process.shape.geometric_discontinuities.

Pure-Python unit tests (no OCC) cover _classify_severity() and all data
structures.  Integration tests load a real STEP file and are skipped when
pythonocc-core is not available.
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

from post_process.shape.geometric_discontinuities import (
    DiscontinuityGatherResult,
    DiscontinuityKind,
    DiscontinuitySeverity,
    SharpEdge,
    SolidDiscontinuityResult,
    _classify_severity,
    gather_discontinuities,
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
_SIMPLE_RIB   = DATA_DIR / "simple_rib.step"


# ---------------------------------------------------------------------------
# Synthetic data builders (no OCC)
# ---------------------------------------------------------------------------

def _make_edge(
    solid_id: int = 0,
    face_id_a: int = 0,
    face_id_b: int = 1,
    dihedral_angle_deg: float = 90.0,
    kind: DiscontinuityKind = DiscontinuityKind.CONVEX,
    severity: DiscontinuitySeverity = DiscontinuitySeverity.HIGH,
) -> SharpEdge:
    return SharpEdge(
        solid_id=solid_id,
        face_id_a=face_id_a,
        face_id_b=face_id_b,
        dihedral_angle_deg=dihedral_angle_deg,
        edge_midpoint=(1.0, 2.0, 3.0),
        edge_length=5.0,
        kind=kind,
        severity=severity,
        adjacent_face_ids_a=[2, 3],
        adjacent_face_ids_b=[0, 4],
    )


def _make_solid_result(
    solid_id: int = 0,
    n_convex: int = 2,
    n_concave: int = 1,
    n_unknown: int = 0,
    total_checked: int = 12,
) -> SolidDiscontinuityResult:
    sr = SolidDiscontinuityResult(solid_id=solid_id, total_edges_checked=total_checked)
    for i in range(n_convex):
        sr.sharp_edges.append(_make_edge(
            solid_id=solid_id, face_id_a=i, face_id_b=i + 10,
            kind=DiscontinuityKind.CONVEX,
            severity=DiscontinuitySeverity.HIGH,
            dihedral_angle_deg=90.0,
        ))
    for i in range(n_concave):
        sr.sharp_edges.append(_make_edge(
            solid_id=solid_id, face_id_a=20 + i, face_id_b=30 + i,
            kind=DiscontinuityKind.CONCAVE,
            severity=DiscontinuitySeverity.MEDIUM,
            dihedral_angle_deg=60.0,
        ))
    for i in range(n_unknown):
        sr.sharp_edges.append(_make_edge(
            solid_id=solid_id, face_id_a=40 + i, face_id_b=50 + i,
            kind=DiscontinuityKind.UNKNOWN,
            severity=DiscontinuitySeverity.LOW,
            dihedral_angle_deg=35.0,
        ))
    return sr


# ---------------------------------------------------------------------------
# _classify_severity — pure Python, no OCC
# ---------------------------------------------------------------------------

class TestClassifySeverity(unittest.TestCase):
    """Unit tests for the stateless severity classifier."""

    # ── LOW band (30° – 44°) ─────────────────────────────────────────────────

    def test_30_is_low(self) -> None:
        self.assertEqual(_classify_severity(30.0), DiscontinuitySeverity.LOW)

    def test_37_is_low(self) -> None:
        self.assertEqual(_classify_severity(37.0), DiscontinuitySeverity.LOW)

    def test_44_9_is_low(self) -> None:
        self.assertEqual(_classify_severity(44.9), DiscontinuitySeverity.LOW)

    # ── MEDIUM band (45° – 89°) ───────────────────────────────────────────────

    def test_45_is_medium(self) -> None:
        self.assertEqual(_classify_severity(45.0), DiscontinuitySeverity.MEDIUM)

    def test_60_is_medium(self) -> None:
        self.assertEqual(_classify_severity(60.0), DiscontinuitySeverity.MEDIUM)

    def test_89_9_is_medium(self) -> None:
        self.assertEqual(_classify_severity(89.9), DiscontinuitySeverity.MEDIUM)

    # ── HIGH band (≥ 90°) ────────────────────────────────────────────────────

    def test_90_is_high(self) -> None:
        self.assertEqual(_classify_severity(90.0), DiscontinuitySeverity.HIGH)

    def test_120_is_high(self) -> None:
        self.assertEqual(_classify_severity(120.0), DiscontinuitySeverity.HIGH)

    def test_180_is_high(self) -> None:
        self.assertEqual(_classify_severity(180.0), DiscontinuitySeverity.HIGH)

    # ── Return type ──────────────────────────────────────────────────────────

    def test_returns_discontinuity_severity(self) -> None:
        for angle in (30.0, 45.0, 90.0, 180.0):
            with self.subTest(angle=angle):
                self.assertIsInstance(_classify_severity(angle), DiscontinuitySeverity)

    # ── Monotonicity: higher angle → same or higher severity ─────────────────

    def test_medium_not_returned_for_below_45(self) -> None:
        self.assertNotEqual(_classify_severity(44.9), DiscontinuitySeverity.MEDIUM)

    def test_high_not_returned_for_below_90(self) -> None:
        self.assertNotEqual(_classify_severity(89.9), DiscontinuitySeverity.HIGH)

    def test_low_not_returned_for_90_or_above(self) -> None:
        for angle in (90.0, 100.0, 180.0):
            with self.subTest(angle=angle):
                self.assertNotEqual(_classify_severity(angle), DiscontinuitySeverity.LOW)


# ---------------------------------------------------------------------------
# DiscontinuityKind enum
# ---------------------------------------------------------------------------

class TestDiscontinuityKindEnum(unittest.TestCase):

    def test_values_are_strings(self) -> None:
        for member in DiscontinuityKind:
            self.assertIsInstance(member.value, str)

    def test_is_str_subclass(self) -> None:
        self.assertIsInstance(DiscontinuityKind.CONVEX, str)

    def test_expected_members_present(self) -> None:
        values = {m.value for m in DiscontinuityKind}
        self.assertIn("convex",  values)
        self.assertIn("concave", values)
        self.assertIn("unknown", values)

    def test_exactly_three_members(self) -> None:
        self.assertEqual(len(list(DiscontinuityKind)), 3)


# ---------------------------------------------------------------------------
# DiscontinuitySeverity enum
# ---------------------------------------------------------------------------

class TestDiscontinuitySeverityEnum(unittest.TestCase):

    def test_values_are_strings(self) -> None:
        for member in DiscontinuitySeverity:
            self.assertIsInstance(member.value, str)

    def test_is_str_subclass(self) -> None:
        self.assertIsInstance(DiscontinuitySeverity.HIGH, str)

    def test_expected_members_present(self) -> None:
        values = {m.value for m in DiscontinuitySeverity}
        self.assertIn("low",    values)
        self.assertIn("medium", values)
        self.assertIn("high",   values)

    def test_exactly_three_members(self) -> None:
        self.assertEqual(len(list(DiscontinuitySeverity)), 3)


# ---------------------------------------------------------------------------
# SharpEdge data class
# ---------------------------------------------------------------------------

class TestSharpEdge(unittest.TestCase):

    def setUp(self) -> None:
        self.e = _make_edge(
            solid_id=1, face_id_a=3, face_id_b=7,
            dihedral_angle_deg=90.0,
            kind=DiscontinuityKind.CONVEX,
            severity=DiscontinuitySeverity.HIGH,
        )

    # ── Field storage ────────────────────────────────────────────────────────

    def test_solid_id_stored(self) -> None:
        self.assertEqual(self.e.solid_id, 1)

    def test_face_ids_stored(self) -> None:
        self.assertEqual(self.e.face_id_a, 3)
        self.assertEqual(self.e.face_id_b, 7)

    def test_dihedral_angle_stored(self) -> None:
        self.assertAlmostEqual(self.e.dihedral_angle_deg, 90.0)

    def test_edge_midpoint_stored(self) -> None:
        self.assertEqual(len(self.e.edge_midpoint), 3)

    def test_edge_length_stored(self) -> None:
        self.assertAlmostEqual(self.e.edge_length, 5.0)

    def test_kind_stored(self) -> None:
        self.assertEqual(self.e.kind, DiscontinuityKind.CONVEX)

    def test_severity_stored(self) -> None:
        self.assertEqual(self.e.severity, DiscontinuitySeverity.HIGH)

    def test_adjacent_ids_stored(self) -> None:
        self.assertEqual(self.e.adjacent_face_ids_a, [2, 3])
        self.assertEqual(self.e.adjacent_face_ids_b, [0, 4])

    # ── Default empty adjacency lists ────────────────────────────────────────

    def test_default_adjacent_ids_are_empty(self) -> None:
        e = SharpEdge(
            solid_id=0, face_id_a=0, face_id_b=1,
            dihedral_angle_deg=90.0,
            edge_midpoint=(0.0, 0.0, 0.0),
            edge_length=1.0,
            kind=DiscontinuityKind.UNKNOWN,
            severity=DiscontinuitySeverity.HIGH,
        )
        self.assertEqual(e.adjacent_face_ids_a, [])
        self.assertEqual(e.adjacent_face_ids_b, [])

    # ── as_dict keys and types ────────────────────────────────────────────────

    def test_as_dict_has_required_keys(self) -> None:
        required = {
            "solid_id", "face_id_a", "face_id_b", "dihedral_angle_deg",
            "edge_midpoint", "edge_length", "kind", "severity",
            "adjacent_face_ids_a", "adjacent_face_ids_b",
        }
        self.assertEqual(set(self.e.as_dict().keys()), required)

    def test_as_dict_kind_is_string(self) -> None:
        self.assertIsInstance(self.e.as_dict()["kind"], str)
        self.assertEqual(self.e.as_dict()["kind"], "convex")

    def test_as_dict_severity_is_string(self) -> None:
        self.assertIsInstance(self.e.as_dict()["severity"], str)
        self.assertEqual(self.e.as_dict()["severity"], "high")

    def test_as_dict_dihedral_angle_value(self) -> None:
        self.assertAlmostEqual(self.e.as_dict()["dihedral_angle_deg"], 90.0)

    def test_as_dict_edge_midpoint_is_tuple(self) -> None:
        mp = self.e.as_dict()["edge_midpoint"]
        self.assertEqual(len(mp), 3)

    def test_as_dict_is_json_serializable(self) -> None:
        dumped = json.dumps(self.e.as_dict())
        self.assertIsInstance(dumped, str)

    # ── Enum values in as_dict for all kind/severity combinations ────────────

    def test_concave_kind_in_dict(self) -> None:
        e = _make_edge(kind=DiscontinuityKind.CONCAVE)
        self.assertEqual(e.as_dict()["kind"], "concave")

    def test_unknown_kind_in_dict(self) -> None:
        e = _make_edge(kind=DiscontinuityKind.UNKNOWN)
        self.assertEqual(e.as_dict()["kind"], "unknown")

    def test_medium_severity_in_dict(self) -> None:
        e = _make_edge(severity=DiscontinuitySeverity.MEDIUM)
        self.assertEqual(e.as_dict()["severity"], "medium")

    def test_low_severity_in_dict(self) -> None:
        e = _make_edge(severity=DiscontinuitySeverity.LOW)
        self.assertEqual(e.as_dict()["severity"], "low")


# ---------------------------------------------------------------------------
# SolidDiscontinuityResult
# ---------------------------------------------------------------------------

class TestSolidDiscontinuityResult(unittest.TestCase):

    def setUp(self) -> None:
        self.sr = _make_solid_result(
            solid_id=2, n_convex=3, n_concave=2, n_unknown=1, total_checked=20
        )

    # ── Basic fields ──────────────────────────────────────────────────────────

    def test_solid_id_stored(self) -> None:
        self.assertEqual(self.sr.solid_id, 2)

    def test_total_sharp_edges(self) -> None:
        self.assertEqual(len(self.sr.sharp_edges), 6)  # 3 + 2 + 1

    def test_total_edges_checked(self) -> None:
        self.assertEqual(self.sr.total_edges_checked, 20)

    # ── Filtered properties ──────────────────────────────────────────────────

    def test_convex_edges_count(self) -> None:
        self.assertEqual(len(self.sr.convex_edges), 3)

    def test_concave_edges_count(self) -> None:
        self.assertEqual(len(self.sr.concave_edges), 2)

    def test_high_severity_edges_count(self) -> None:
        # Only the 3 convex edges were built with HIGH severity
        self.assertEqual(len(self.sr.high_severity_edges), 3)

    def test_convex_edges_all_convex(self) -> None:
        for e in self.sr.convex_edges:
            self.assertEqual(e.kind, DiscontinuityKind.CONVEX)

    def test_concave_edges_all_concave(self) -> None:
        for e in self.sr.concave_edges:
            self.assertEqual(e.kind, DiscontinuityKind.CONCAVE)

    def test_high_severity_edges_all_high(self) -> None:
        for e in self.sr.high_severity_edges:
            self.assertEqual(e.severity, DiscontinuitySeverity.HIGH)

    # ── Empty result ──────────────────────────────────────────────────────────

    def test_empty_result_has_no_sharp_edges(self) -> None:
        sr = SolidDiscontinuityResult(solid_id=0)
        self.assertEqual(len(sr.sharp_edges), 0)
        self.assertEqual(sr.total_edges_checked, 0)
        self.assertEqual(sr.convex_edges, [])
        self.assertEqual(sr.concave_edges, [])
        self.assertEqual(sr.high_severity_edges, [])

    # ── as_dict ───────────────────────────────────────────────────────────────

    def test_as_dict_has_required_keys(self) -> None:
        d = self.sr.as_dict()
        self.assertIn("solid_id", d)
        self.assertIn("sharp_edges", d)
        self.assertIn("total_edges_checked", d)

    def test_as_dict_sharp_edges_is_list_of_dicts(self) -> None:
        for item in self.sr.as_dict()["sharp_edges"]:
            self.assertIsInstance(item, dict)

    def test_as_dict_total_edges_checked_value(self) -> None:
        self.assertEqual(self.sr.as_dict()["total_edges_checked"], 20)

    def test_as_dict_is_json_serializable(self) -> None:
        json.dumps(self.sr.as_dict())


# ---------------------------------------------------------------------------
# DiscontinuityGatherResult
# ---------------------------------------------------------------------------

class TestDiscontinuityGatherResult(unittest.TestCase):

    def _make_result(self) -> DiscontinuityGatherResult:
        sr0 = _make_solid_result(solid_id=0, n_convex=2, n_concave=1, total_checked=10)
        sr1 = _make_solid_result(solid_id=1, n_convex=0, n_concave=3, total_checked=8)
        return DiscontinuityGatherResult(
            solids=[sr0, sr1],
            angle_threshold_deg=30.0,
        )

    # ── Aggregate counts ──────────────────────────────────────────────────────

    def test_total_sharp_edges(self) -> None:
        r = self._make_result()
        self.assertEqual(r.total_sharp_edges, 6)  # (2+1) + (0+3)

    def test_total_edges_checked(self) -> None:
        r = self._make_result()
        self.assertEqual(r.total_edges_checked, 18)

    def test_all_sharp_edges_length(self) -> None:
        r = self._make_result()
        self.assertEqual(len(r.all_sharp_edges), 6)

    def test_all_convex_edges_count(self) -> None:
        r = self._make_result()
        self.assertEqual(len(r.all_convex_edges), 2)

    def test_all_concave_edges_count(self) -> None:
        r = self._make_result()
        self.assertEqual(len(r.all_concave_edges), 4)

    def test_all_high_severity_count(self) -> None:
        # Only convex edges were built with HIGH (2 from sr0, 0 from sr1)
        r = self._make_result()
        self.assertEqual(len(r.all_high_severity), 2)

    def test_all_convex_edges_have_convex_kind(self) -> None:
        for e in self._make_result().all_convex_edges:
            self.assertEqual(e.kind, DiscontinuityKind.CONVEX)

    def test_all_concave_edges_have_concave_kind(self) -> None:
        for e in self._make_result().all_concave_edges:
            self.assertEqual(e.kind, DiscontinuityKind.CONCAVE)

    # ── Threshold stored ──────────────────────────────────────────────────────

    def test_threshold_stored(self) -> None:
        r = self._make_result()
        self.assertAlmostEqual(r.angle_threshold_deg, 30.0)

    # ── Edge ordering across solids ───────────────────────────────────────────

    def test_all_sharp_edges_solid0_before_solid1(self) -> None:
        r = self._make_result()
        solid_ids = [e.solid_id for e in r.all_sharp_edges]
        # sr0 has 3 edges, sr1 has 3 edges → first 3 are solid 0
        self.assertEqual(solid_ids[:3], [0, 0, 0])
        self.assertEqual(solid_ids[3:], [1, 1, 1])

    # ── Empty result ──────────────────────────────────────────────────────────

    def test_empty_result(self) -> None:
        r = DiscontinuityGatherResult(solids=[], angle_threshold_deg=30.0)
        self.assertEqual(r.total_sharp_edges, 0)
        self.assertEqual(r.total_edges_checked, 0)
        self.assertEqual(r.all_sharp_edges, [])
        self.assertEqual(r.all_convex_edges, [])
        self.assertEqual(r.all_concave_edges, [])
        self.assertEqual(r.all_high_severity, [])

    # ── as_dict ───────────────────────────────────────────────────────────────

    def test_as_dict_has_required_keys(self) -> None:
        required = {
            "angle_threshold_deg", "total_sharp_edges",
            "total_edges_checked", "solids",
        }
        self.assertEqual(set(self._make_result().as_dict().keys()), required)

    def test_as_dict_aggregate_counts(self) -> None:
        d = self._make_result().as_dict()
        self.assertEqual(d["total_sharp_edges"], 6)
        self.assertEqual(d["total_edges_checked"], 18)

    def test_as_dict_solids_list_length(self) -> None:
        self.assertEqual(len(self._make_result().as_dict()["solids"]), 2)

    def test_as_dict_is_json_serializable(self) -> None:
        json.dumps(self._make_result().as_dict())


# ---------------------------------------------------------------------------
# Integration tests (OCC required)
# ---------------------------------------------------------------------------

@unittest.skipUnless(HAVE_OCC, f"pythonocc-core not available: {OCC_IMPORT_ERROR}")
class TestGatherDiscontinuitiesIntegration(unittest.TestCase):
    """Integration tests using FlandersMake_part_NOK-Merger.step."""

    @classmethod
    def setUpClass(cls) -> None:
        compound      = read_step_single(str(_FLANDERSMAKE))
        cls.normalized = normalize_shape(compound)
        cls.solids     = extract_solids(compound)
        cls.result     = gather_discontinuities(cls.normalized, cls.solids)

    # ── Return type and structure ─────────────────────────────────────────────

    def test_returns_discontinuity_gather_result(self) -> None:
        self.assertIsInstance(self.result, DiscontinuityGatherResult)

    def test_solid_count_matches_normalized(self) -> None:
        self.assertEqual(len(self.result.solids), len(self.normalized.solids))

    def test_each_solid_result_is_correct_type(self) -> None:
        for sr in self.result.solids:
            with self.subTest(solid_id=sr.solid_id):
                self.assertIsInstance(sr, SolidDiscontinuityResult)

    def test_solid_ids_are_sequential(self) -> None:
        for idx, sr in enumerate(self.result.solids):
            with self.subTest(idx=idx):
                self.assertEqual(sr.solid_id, idx)

    # ── The NOK part has sharp edges ─────────────────────────────────────────

    def test_at_least_one_sharp_edge_detected(self) -> None:
        self.assertGreater(self.result.total_sharp_edges, 0)

    def test_edges_were_checked(self) -> None:
        self.assertGreater(self.result.total_edges_checked, 0)

    def test_more_edges_checked_than_sharp_edges(self) -> None:
        # A real part has both sharp and smooth edges.
        self.assertGreater(
            self.result.total_edges_checked,
            self.result.total_sharp_edges,
        )

    # ── SharpEdge field invariants ────────────────────────────────────────────

    def test_all_dihedral_angles_above_threshold(self) -> None:
        thr = self.result.angle_threshold_deg
        for e in self.result.all_sharp_edges:
            with self.subTest(solid_id=e.solid_id, fa=e.face_id_a, fb=e.face_id_b):
                self.assertGreaterEqual(e.dihedral_angle_deg, thr - 1e-6)

    def test_all_dihedral_angles_at_most_180(self) -> None:
        for e in self.result.all_sharp_edges:
            with self.subTest(solid_id=e.solid_id, fa=e.face_id_a, fb=e.face_id_b):
                self.assertLessEqual(e.dihedral_angle_deg, 180.0 + 1e-6)

    def test_all_edge_lengths_positive(self) -> None:
        for e in self.result.all_sharp_edges:
            with self.subTest(solid_id=e.solid_id, fa=e.face_id_a, fb=e.face_id_b):
                self.assertGreater(e.edge_length, 0.0)

    def test_all_edge_midpoints_are_3_tuples(self) -> None:
        for e in self.result.all_sharp_edges:
            self.assertEqual(len(e.edge_midpoint), 3)
            for v in e.edge_midpoint:
                self.assertIsInstance(v, float)

    def test_all_kinds_are_valid(self) -> None:
        valid = set(DiscontinuityKind)
        for e in self.result.all_sharp_edges:
            with self.subTest(solid_id=e.solid_id, fa=e.face_id_a, fb=e.face_id_b):
                self.assertIn(e.kind, valid)

    def test_all_severities_are_valid(self) -> None:
        valid = set(DiscontinuitySeverity)
        for e in self.result.all_sharp_edges:
            with self.subTest(solid_id=e.solid_id, fa=e.face_id_a, fb=e.face_id_b):
                self.assertIn(e.severity, valid)

    def test_severity_consistent_with_dihedral_angle(self) -> None:
        for e in self.result.all_sharp_edges:
            expected = _classify_severity(e.dihedral_angle_deg)
            with self.subTest(solid_id=e.solid_id, fa=e.face_id_a, fb=e.face_id_b):
                self.assertEqual(e.severity, expected)

    def test_face_id_a_differs_from_face_id_b(self) -> None:
        for e in self.result.all_sharp_edges:
            with self.subTest(solid_id=e.solid_id):
                self.assertNotEqual(e.face_id_a, e.face_id_b)

    # ── Back-reference validity ───────────────────────────────────────────────

    def test_solid_id_is_valid_index_into_normalized(self) -> None:
        n = len(self.normalized.solids)
        for e in self.result.all_sharp_edges:
            with self.subTest(solid_id=e.solid_id):
                self.assertGreaterEqual(e.solid_id, 0)
                self.assertLess(e.solid_id, n)

    def test_face_id_a_is_valid_index(self) -> None:
        for sr in self.result.solids:
            n_faces = len(self.normalized.solids[sr.solid_id].faces)
            for e in sr.sharp_edges:
                with self.subTest(solid_id=e.solid_id, face_id_a=e.face_id_a):
                    self.assertGreaterEqual(e.face_id_a, 0)
                    self.assertLess(e.face_id_a, n_faces)

    def test_face_id_b_is_valid_index(self) -> None:
        for sr in self.result.solids:
            n_faces = len(self.normalized.solids[sr.solid_id].faces)
            for e in sr.sharp_edges:
                with self.subTest(solid_id=e.solid_id, face_id_b=e.face_id_b):
                    self.assertGreaterEqual(e.face_id_b, 0)
                    self.assertLess(e.face_id_b, n_faces)

    def test_adjacent_face_ids_a_are_valid_indices(self) -> None:
        for sr in self.result.solids:
            n_faces = len(self.normalized.solids[sr.solid_id].faces)
            for e in sr.sharp_edges:
                for adj in e.adjacent_face_ids_a:
                    with self.subTest(solid_id=e.solid_id, adj=adj):
                        self.assertGreaterEqual(adj, 0)
                        self.assertLess(adj, n_faces)

    def test_adjacent_face_ids_b_are_valid_indices(self) -> None:
        for sr in self.result.solids:
            n_faces = len(self.normalized.solids[sr.solid_id].faces)
            for e in sr.sharp_edges:
                for adj in e.adjacent_face_ids_b:
                    with self.subTest(solid_id=e.solid_id, adj=adj):
                        self.assertGreaterEqual(adj, 0)
                        self.assertLess(adj, n_faces)

    def test_face_a_adjacent_to_face_b_in_normalized(self) -> None:
        # face_id_a and face_id_b share an edge, so they must be neighbours
        # in the NormalizedShape adjacency graph.
        for sr in self.result.solids:
            adjacency = self.normalized.solids[sr.solid_id].adjacency
            for e in sr.sharp_edges:
                with self.subTest(solid_id=e.solid_id, fa=e.face_id_a, fb=e.face_id_b):
                    self.assertIn(e.face_id_b, adjacency.get(e.face_id_a, []))

    # ── Aggregate consistency ─────────────────────────────────────────────────

    def test_total_sharp_equals_sum_of_per_solid(self) -> None:
        expected = sum(len(sr.sharp_edges) for sr in self.result.solids)
        self.assertEqual(self.result.total_sharp_edges, expected)

    def test_total_checked_equals_sum_of_per_solid(self) -> None:
        expected = sum(sr.total_edges_checked for sr in self.result.solids)
        self.assertEqual(self.result.total_edges_checked, expected)

    def test_all_sharp_edges_length_matches_total(self) -> None:
        self.assertEqual(len(self.result.all_sharp_edges), self.result.total_sharp_edges)

    # ── Error handling ────────────────────────────────────────────────────────

    def test_length_mismatch_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            gather_discontinuities(self.normalized, self.solids[:-1])

    # ── Serialization ─────────────────────────────────────────────────────────

    def test_result_as_dict_is_json_serializable(self) -> None:
        json.dumps(self.result.as_dict())

    # ── Threshold parameter effects ───────────────────────────────────────────

    def test_threshold_stored_in_result(self) -> None:
        r = gather_discontinuities(self.normalized, self.solids, angle_threshold_deg=45.0)
        self.assertAlmostEqual(r.angle_threshold_deg, 45.0)

    def test_lower_threshold_finds_at_least_as_many_edges(self) -> None:
        tight = gather_discontinuities(self.normalized, self.solids, angle_threshold_deg=60.0)
        loose = gather_discontinuities(self.normalized, self.solids, angle_threshold_deg=30.0)
        self.assertGreaterEqual(loose.total_sharp_edges, tight.total_sharp_edges)

    def test_zero_threshold_finds_at_least_as_many_as_default(self) -> None:
        default = gather_discontinuities(self.normalized, self.solids)
        zero    = gather_discontinuities(self.normalized, self.solids, angle_threshold_deg=0.0)
        self.assertGreaterEqual(zero.total_sharp_edges, default.total_sharp_edges)


@unittest.skipUnless(HAVE_OCC, f"pythonocc-core not available: {OCC_IMPORT_ERROR}")
class TestGatherDiscontinuitiesSimpleRib(unittest.TestCase):
    """Smoke tests on simple_rib.step (single solid, simpler geometry)."""

    @classmethod
    def setUpClass(cls) -> None:
        compound       = read_step_single(str(_SIMPLE_RIB))
        cls.normalized = normalize_shape(compound)
        cls.solids     = extract_solids(compound)
        cls.result     = gather_discontinuities(cls.normalized, cls.solids)

    def test_at_least_one_solid(self) -> None:
        self.assertGreater(len(self.result.solids), 0)

    def test_solid_ids_sequential(self) -> None:
        for idx, sr in enumerate(self.result.solids):
            self.assertEqual(sr.solid_id, idx)

    def test_no_negative_edge_counts(self) -> None:
        for sr in self.result.solids:
            self.assertGreaterEqual(sr.total_edges_checked, 0)
            self.assertGreaterEqual(len(sr.sharp_edges), 0)

    def test_all_face_ids_non_negative(self) -> None:
        for e in self.result.all_sharp_edges:
            self.assertGreaterEqual(e.face_id_a, 0)
            self.assertGreaterEqual(e.face_id_b, 0)

    def test_all_severities_match_angles(self) -> None:
        for e in self.result.all_sharp_edges:
            self.assertEqual(e.severity, _classify_severity(e.dihedral_angle_deg))

    def test_result_serializable(self) -> None:
        json.dumps(self.result.as_dict())


if __name__ == "__main__":
    unittest.main()
