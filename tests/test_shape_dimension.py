"""Tests for post_process.shape_dimension.

Unit tests build synthetic geometry with local dataclass stubs — no
pythonocc-core required.  Integration tests load a real STEP file and are
skipped when pythonocc-core is not installed.
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

# shape_dimension can be imported without OCC (TYPE_CHECKING guard).
from post_process.shape_dimension import (
    CylindricalFeature,
    PlaneGroup,
    ShapeDimensions,
    SolidDimensions,
    WallThickness,
    _angle_between_deg,
    _canonicalize_normal,
    _estimate_cylinder,
    _estimate_wall_thicknesses,
    _group_planes_by_normal,
    _union_bbox,
    infer_dimensions,
    infer_solid_dimensions,
)

# OCC-dependent imports — only used for integration tests.
OCC_IMPORT_ERROR = None
try:
    from load_cad.step_reader import read_step_single
    from post_process.shape_normalizer import normalize_shape
    HAVE_OCC = True
except Exception as exc:
    HAVE_OCC = False
    OCC_IMPORT_ERROR = exc

DATA_DIR = ROOT / "data"


# ---------------------------------------------------------------------------
# Minimal dataclass stubs matching FaceData / SolidData / NormalizedShape
# (duck-typed — shape_dimension functions only access attributes, not types)
# ---------------------------------------------------------------------------

@dataclass
class FaceData:
    face_id: int
    surface_type: str
    area: float
    center: Tuple[float, float, float]
    normal: Optional[Tuple[float, float, float]]
    bounding_box: Tuple[float, float, float, float, float, float]


@dataclass
class SolidData:
    solid_id: int
    faces: List[FaceData] = field(default_factory=list)
    adjacency: Dict[int, List[int]] = field(default_factory=dict)


@dataclass
class NormalizedShape:
    solids: List[SolidData]
    assembly_context: Optional[List] = None


# ---------------------------------------------------------------------------
# Synthetic geometry builders
# ---------------------------------------------------------------------------

def _plane_face(
    face_id: int,
    normal: Tuple[float, float, float],
    center: Tuple[float, float, float],
    area: float,
    bb: Tuple[float, float, float, float, float, float],
) -> FaceData:
    return FaceData(face_id=face_id, surface_type="Plane", area=area,
                    center=center, normal=normal, bounding_box=bb)


def _cyl_face(
    face_id: int,
    center: Tuple[float, float, float],
    area: float,
    bb: Tuple[float, float, float, float, float, float],
) -> FaceData:
    return FaceData(face_id=face_id, surface_type="Cylinder", area=area,
                    center=center, normal=None, bounding_box=bb)


def _box_solid(solid_id: int, lx: float, ly: float, lz: float) -> SolidData:
    """Rectangular box from (0,0,0) to (lx, ly, lz) with 6 planar faces."""
    cx, cy, cz = lx / 2, ly / 2, lz / 2
    faces = [
        _plane_face(0, (1, 0, 0), (lx, cy, cz), ly * lz, (lx, 0, 0, lx, ly, lz)),
        _plane_face(1, (-1, 0, 0), (0, cy, cz), ly * lz, (0, 0, 0, 0, ly, lz)),
        _plane_face(2, (0, 1, 0), (cx, ly, cz), lx * lz, (0, ly, 0, lx, ly, lz)),
        _plane_face(3, (0, -1, 0), (cx, 0, cz), lx * lz, (0, 0, 0, lx, 0, lz)),
        _plane_face(4, (0, 0, 1), (cx, cy, lz), lx * ly, (0, 0, lz, lx, ly, lz)),
        _plane_face(5, (0, 0, -1), (cx, cy, 0), lx * ly, (0, 0, 0, lx, ly, 0)),
    ]
    return SolidData(solid_id=solid_id, faces=faces,
                     adjacency={i: [] for i in range(6)})


def _cylinder_solid(solid_id: int, radius: float, height: float) -> SolidData:
    """Cylinder: one lateral face + two planar end caps along Z."""
    r, h = radius, height
    lateral = _cyl_face(0, (0, 0, h / 2), 2 * math.pi * r * h,
                         (-r, -r, 0, r, r, h))
    cap_top = _plane_face(1, (0, 0, 1), (0, 0, h), math.pi * r * r,
                           (-r, -r, h, r, r, h))
    cap_bot = _plane_face(2, (0, 0, -1), (0, 0, 0), math.pi * r * r,
                           (-r, -r, 0, r, r, 0))
    return SolidData(solid_id=solid_id, faces=[lateral, cap_top, cap_bot],
                     adjacency={0: [1, 2], 1: [0], 2: [0]})


# ===========================================================================
# _union_bbox
# ===========================================================================

class TestUnionBbox(unittest.TestCase):

    def test_single_face(self):
        f = _plane_face(0, (1, 0, 0), (5, 5, 5), 100, (0, 0, 0, 10, 10, 10))
        self.assertEqual(_union_bbox([f]), (0, 0, 0, 10, 10, 10))

    def test_two_non_overlapping_faces(self):
        f0 = _plane_face(0, (1, 0, 0), (0, 0, 0), 1, (0, 0, 0, 5, 5, 5))
        f1 = _plane_face(1, (1, 0, 0), (10, 10, 10), 1, (7, 7, 7, 12, 12, 12))
        self.assertEqual(_union_bbox([f0, f1]), (0, 0, 0, 12, 12, 12))

    def test_box_solid_bbox_extents(self):
        solid = _box_solid(0, 100, 50, 30)
        bb = _union_bbox(solid.faces)
        self.assertAlmostEqual(bb[3] - bb[0], 100)
        self.assertAlmostEqual(bb[4] - bb[1], 50)
        self.assertAlmostEqual(bb[5] - bb[2], 30)


# ===========================================================================
# _estimate_cylinder
# ===========================================================================

class TestEstimateCylinder(unittest.TestCase):

    def _make(self, r, h, axis="z") -> FaceData:
        if axis == "z":
            bb = (-r, -r, 0, r, r, h)
        elif axis == "x":
            bb = (0, -r, -r, h, r, r)
        else:
            bb = (-r, 0, -r, r, h, r)
        return _cyl_face(0, (0, 0, h / 2), 2 * math.pi * r * h, bb)

    def test_tall_cylinder_z(self):
        c = _estimate_cylinder(self._make(r=10, h=40, axis="z"))
        self.assertAlmostEqual(c.radius_est, 10.0)
        self.assertAlmostEqual(c.height_est, 40.0)

    def test_tall_cylinder_x(self):
        c = _estimate_cylinder(self._make(r=5, h=60, axis="x"))
        self.assertAlmostEqual(c.radius_est, 5.0)
        self.assertAlmostEqual(c.height_est, 60.0)

    def test_disk_cylinder(self):
        c = _estimate_cylinder(self._make(r=20, h=5, axis="z"))
        self.assertAlmostEqual(c.radius_est, 20.0)
        self.assertAlmostEqual(c.height_est, 5.0)

    def test_diameter_property(self):
        c = _estimate_cylinder(self._make(r=10, h=40))
        self.assertAlmostEqual(c.diameter_est, c.radius_est * 2.0)

    def test_face_id_and_area_preserved(self):
        face = _cyl_face(7, (1, 2, 3), 314.0, (-5, -5, 0, 5, 5, 10))
        c = _estimate_cylinder(face)
        self.assertEqual(c.face_id, 7)
        self.assertAlmostEqual(c.area, 314.0)

    def test_degenerate_zero_bbox_gives_positive_result(self):
        face = _cyl_face(0, (0, 0, 0), 0.0, (0, 0, 0, 0, 0, 0))
        c = _estimate_cylinder(face)
        self.assertGreater(c.radius_est, 0)
        self.assertGreater(c.height_est, 0)


# ===========================================================================
# _canonicalize_normal
# ===========================================================================

class TestCanonicalizeNormal(unittest.TestCase):

    def test_positive_x(self):
        self.assertEqual(_canonicalize_normal((1, 0, 0)), (1, 0, 0))

    def test_negative_x_flipped(self):
        self.assertEqual(_canonicalize_normal((-1, 0, 0)), (1, 0, 0))

    def test_positive_y(self):
        self.assertEqual(_canonicalize_normal((0, 1, 0)), (0, 1, 0))

    def test_negative_z_flipped(self):
        self.assertEqual(_canonicalize_normal((0, 0, -1)), (0, 0, 1))

    def test_antiparallel_maps_to_same(self):
        n = (0.0, 0.6, 0.8)
        c1 = _canonicalize_normal(n)
        c2 = _canonicalize_normal((-n[0], -n[1], -n[2]))
        for i in range(3):
            self.assertAlmostEqual(c1[i], c2[i])

    def test_diagonal_dominant_axis_non_negative(self):
        c = _canonicalize_normal((-0.9, 0.3, 0.1))
        self.assertGreater(c[0], 0)


# ===========================================================================
# _angle_between_deg
# ===========================================================================

class TestAngleBetweenDeg(unittest.TestCase):

    def test_same_vector_zero(self):
        self.assertAlmostEqual(_angle_between_deg((1, 0, 0), (1, 0, 0)), 0.0)

    def test_opposite_180(self):
        self.assertAlmostEqual(_angle_between_deg((1, 0, 0), (-1, 0, 0)), 180.0)

    def test_perpendicular_90(self):
        self.assertAlmostEqual(_angle_between_deg((1, 0, 0), (0, 1, 0)), 90.0)

    def test_45_degrees(self):
        s = math.sqrt(2) / 2
        self.assertAlmostEqual(_angle_between_deg((1, 0, 0), (s, s, 0)), 45.0, places=5)


# ===========================================================================
# _group_planes_by_normal
# ===========================================================================

class TestGroupPlanesByNormal(unittest.TestCase):

    def test_box_has_three_groups(self):
        groups = _group_planes_by_normal(_box_solid(0, 100, 50, 30).faces)
        self.assertEqual(len(groups), 3)

    def test_cylinder_caps_form_one_group_of_two(self):
        groups = _group_planes_by_normal(_cylinder_solid(0, 10, 40).faces)
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0].face_ids), 2)

    def test_no_plane_faces_returns_empty(self):
        solid = SolidData(solid_id=0,
                          faces=[_cyl_face(0, (0,0,0), 100, (0,0,0,10,10,10))],
                          adjacency={0: []})
        self.assertEqual(_group_planes_by_normal(solid.faces), [])

    def test_sorted_by_total_area_descending(self):
        groups = _group_planes_by_normal(_box_solid(0, 100, 50, 30).faces)
        areas = [g.total_area for g in groups]
        self.assertEqual(areas, sorted(areas, reverse=True))

    def test_spans_match_box_dimensions(self):
        groups = _group_planes_by_normal(_box_solid(0, 100, 50, 30).faces)
        spans = sorted(g.span for g in groups)
        self.assertAlmostEqual(spans[0], 30.0, places=5)
        self.assertAlmostEqual(spans[1], 50.0, places=5)
        self.assertAlmostEqual(spans[2], 100.0, places=5)

    def test_each_plane_face_appears_exactly_once(self):
        faces = _box_solid(0, 100, 50, 30).faces
        groups = _group_planes_by_normal(faces)
        all_ids = [fid for g in groups for fid in g.face_ids]
        plane_ids = [f.face_id for f in faces if f.surface_type == "Plane"]
        self.assertEqual(sorted(all_ids), sorted(plane_ids))

    def test_positions_length_matches_face_ids(self):
        for g in _group_planes_by_normal(_box_solid(0, 100, 50, 30).faces):
            self.assertEqual(len(g.positions), len(g.face_ids))


# ===========================================================================
# _estimate_wall_thicknesses
# ===========================================================================

class TestEstimateWallThicknesses(unittest.TestCase):

    def test_box_produces_three_gaps(self):
        groups = _group_planes_by_normal(_box_solid(0, 100, 50, 30).faces)
        wts = _estimate_wall_thicknesses(groups)
        self.assertEqual(len(wts), 3)

    def test_box_thickness_values(self):
        groups = _group_planes_by_normal(_box_solid(0, 100, 50, 30).faces)
        values = sorted(wt.thickness_mm for wt in _estimate_wall_thicknesses(groups))
        self.assertAlmostEqual(values[0], 30.0, places=5)
        self.assertAlmostEqual(values[1], 50.0, places=5)
        self.assertAlmostEqual(values[2], 100.0, places=5)

    def test_sorted_ascending(self):
        groups = _group_planes_by_normal(_box_solid(0, 100, 50, 30).faces)
        values = [wt.thickness_mm for wt in _estimate_wall_thicknesses(groups)]
        self.assertEqual(values, sorted(values))

    def test_single_face_group_no_thickness(self):
        face = _plane_face(0, (1,0,0), (50,25,15), 100, (50,0,0,50,50,30))
        solid = SolidData(solid_id=0, faces=[face], adjacency={0: []})
        groups = _group_planes_by_normal(solid.faces)
        self.assertEqual(_estimate_wall_thicknesses(groups), [])

    def test_face_ids_are_tuple_of_two(self):
        groups = _group_planes_by_normal(_box_solid(0, 10, 10, 10).faces)
        for wt in _estimate_wall_thicknesses(groups):
            self.assertIsInstance(wt.face_ids, tuple)
            self.assertEqual(len(wt.face_ids), 2)

    def test_cylinder_caps_thickness_equals_height(self):
        h = 40.0
        groups = _group_planes_by_normal(_cylinder_solid(0, 10, h).faces)
        wts = _estimate_wall_thicknesses(groups)
        self.assertEqual(len(wts), 1)
        self.assertAlmostEqual(wts[0].thickness_mm, h, places=5)


# ===========================================================================
# infer_solid_dimensions
# ===========================================================================

class TestInferSolidDimensions(unittest.TestCase):

    def test_returns_solid_dimensions(self):
        self.assertIsInstance(infer_solid_dimensions(_box_solid(0, 10, 5, 2)),
                              SolidDimensions)

    def test_solid_id_preserved(self):
        self.assertEqual(infer_solid_dimensions(_box_solid(3, 10, 10, 10)).solid_id, 3)

    def test_principal_dims_sorted_descending(self):
        sd = infer_solid_dimensions(_box_solid(0, 100, 50, 30))
        self.assertAlmostEqual(sd.length, 100.0, places=5)
        self.assertAlmostEqual(sd.width,  50.0,  places=5)
        self.assertAlmostEqual(sd.height, 30.0,  places=5)
        self.assertGreaterEqual(sd.length, sd.width)
        self.assertGreaterEqual(sd.width, sd.height)

    def test_bounding_box_extents(self):
        sd = infer_solid_dimensions(_box_solid(0, 100, 50, 30))
        bb = sd.bounding_box
        self.assertAlmostEqual(bb[3] - bb[0], 100.0, places=5)
        self.assertAlmostEqual(bb[4] - bb[1], 50.0,  places=5)
        self.assertAlmostEqual(bb[5] - bb[2], 30.0,  places=5)

    def test_cylinder_detected_with_correct_radius_and_height(self):
        sd = infer_solid_dimensions(_cylinder_solid(0, radius=10, height=40))
        self.assertEqual(len(sd.cylinders), 1)
        self.assertAlmostEqual(sd.cylinders[0].radius_est, 10.0, places=5)
        self.assertAlmostEqual(sd.cylinders[0].height_est, 40.0, places=5)

    def test_no_cylinders_for_box(self):
        sd = infer_solid_dimensions(_box_solid(0, 100, 50, 30))
        self.assertEqual(len(sd.cylinders), 0)

    def test_box_has_three_plane_groups(self):
        sd = infer_solid_dimensions(_box_solid(0, 100, 50, 30))
        self.assertEqual(len(sd.plane_groups), 3)

    def test_box_has_three_wall_thickness_entries(self):
        sd = infer_solid_dimensions(_box_solid(0, 100, 50, 30))
        self.assertEqual(len(sd.wall_thicknesses), 3)

    def test_empty_solid_returns_zeros(self):
        sd = infer_solid_dimensions(SolidData(solid_id=0))
        self.assertEqual(sd.length, 0.0)
        self.assertEqual(sd.width,  0.0)
        self.assertEqual(sd.height, 0.0)

    def test_as_dict_has_expected_keys(self):
        d = infer_solid_dimensions(_box_solid(0, 10, 10, 10)).as_dict()
        self.assertEqual(set(d.keys()), {
            "solid_id", "bounding_box",
            "length_mm", "width_mm", "height_mm",
            "cylinders", "plane_groups", "wall_thicknesses",
        })


# ===========================================================================
# infer_dimensions (assembly level)
# ===========================================================================

class TestInferDimensions(unittest.TestCase):

    def _shape(self, *solids) -> NormalizedShape:
        return NormalizedShape(solids=list(solids))

    def test_returns_shape_dimensions(self):
        self.assertIsInstance(infer_dimensions(self._shape(_box_solid(0, 10, 5, 2))),
                              ShapeDimensions)

    def test_solid_count_preserved(self):
        result = infer_dimensions(self._shape(
            _box_solid(0, 10, 5, 2),
            _cylinder_solid(1, 5, 20),
        ))
        self.assertEqual(len(result.solids), 2)

    def test_solid_ids_preserved(self):
        result = infer_dimensions(self._shape(_box_solid(7, 10, 5, 2)))
        self.assertEqual(result.solids[0].solid_id, 7)

    def test_as_dict_structure(self):
        d = infer_dimensions(self._shape(_box_solid(0, 10, 5, 2))).as_dict()
        self.assertIn("solids", d)
        self.assertEqual(len(d["solids"]), 1)

    def test_empty_shape(self):
        result = infer_dimensions(NormalizedShape(solids=[]))
        self.assertEqual(result.solids, [])

    def test_as_dict_json_serializable(self):
        d = infer_dimensions(self._shape(
            _box_solid(0, 100, 50, 30),
            _cylinder_solid(1, 10, 40),
        )).as_dict()
        json.dumps(d)  # must not raise


# ===========================================================================
# Integration tests (require pythonocc-core)
# ===========================================================================

@unittest.skipUnless(HAVE_OCC, f"pythonocc-core not available: {OCC_IMPORT_ERROR}")
class TestIntegrationFlandersMake(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        compound = read_step_single(str(DATA_DIR / "FlandersMake_part_NOK-Merger.step"))
        cls.dims = infer_dimensions(normalize_shape(compound))

    def test_at_least_one_solid(self):
        self.assertGreater(len(self.dims.solids), 0)

    def test_all_principal_dimensions_positive(self):
        for sd in self.dims.solids:
            self.assertGreater(sd.length, 0)
            self.assertGreater(sd.width,  0)
            self.assertGreater(sd.height, 0)

    def test_dimensions_sorted_descending(self):
        for sd in self.dims.solids:
            self.assertGreaterEqual(sd.length, sd.width)
            self.assertGreaterEqual(sd.width,  sd.height)

    def test_bounding_box_consistent_with_dimensions(self):
        for sd in self.dims.solids:
            bb = sd.bounding_box
            extents = sorted([bb[3]-bb[0], bb[4]-bb[1], bb[5]-bb[2]], reverse=True)
            self.assertAlmostEqual(extents[0], sd.length, places=5)
            self.assertAlmostEqual(extents[1], sd.width,  places=5)
            self.assertAlmostEqual(extents[2], sd.height, places=5)

    def test_cylinders_have_positive_dimensions(self):
        for sd in self.dims.solids:
            for cyl in sd.cylinders:
                self.assertGreater(cyl.radius_est, 0)
                self.assertGreater(cyl.height_est, 0)

    def test_plane_groups_present(self):
        self.assertTrue(any(len(sd.plane_groups) > 0 for sd in self.dims.solids))

    def test_wall_thicknesses_positive_and_sorted(self):
        for sd in self.dims.solids:
            values = [wt.thickness_mm for wt in sd.wall_thicknesses]
            self.assertEqual(values, sorted(values))
            for v in values:
                self.assertGreater(v, 0)

    def test_as_dict_json_serializable(self):
        json.dumps(self.dims.as_dict())


if __name__ == "__main__":
    unittest.main()
