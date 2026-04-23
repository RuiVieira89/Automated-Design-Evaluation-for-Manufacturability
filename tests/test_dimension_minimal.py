"""Tests for post_process.dimension_minimal.

Unit tests use synthetic geometry (pure Python, no pythonocc-core).
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

from post_process.dimension_minimal import (
    DimensionEntry,
    MinimalDimensionSet,
    _classify,
    _general_tol_note,
    _it_int,
    _tol,
    minimal_dimensions,
    minimal_solid_dimensions,
)
from post_process.shape_dimension import (
    CylindricalFeature,
    PlaneGroup,
    SolidDimensions,
    ShapeDimensions,
    WallThickness,
    _group_planes_by_normal,
    _estimate_wall_thicknesses,
    infer_solid_dimensions,
)

OCC_IMPORT_ERROR = None
try:
    from load_cad.step_reader import read_step_single
    from post_process.shape_normalizer import normalize_shape
    from post_process.shape_dimension import infer_dimensions as _infer_dims_occ
    HAVE_OCC = True
except Exception as exc:
    HAVE_OCC = False
    OCC_IMPORT_ERROR = exc

DATA_DIR = ROOT / "data"


# ---------------------------------------------------------------------------
# Synthetic geometry stubs
# ---------------------------------------------------------------------------

@dataclass
class FaceData:
    face_id: int; surface_type: str; area: float
    center: Tuple[float,float,float]; normal: Optional[Tuple[float,float,float]]
    bounding_box: Tuple[float,float,float,float,float,float]


@dataclass
class SolidData:
    solid_id: int
    faces: List = field(default_factory=list)
    adjacency: Dict = field(default_factory=dict)


@dataclass
class NormalizedShape:
    solids: List; assembly_context: Optional[List] = None


def _pf(fid, n, c, a, bb):
    return FaceData(face_id=fid, surface_type="Plane", area=a, center=c, normal=n, bounding_box=bb)


def _cf(fid, c, a, bb):
    return FaceData(face_id=fid, surface_type="Cylinder", area=a, center=c, normal=None, bounding_box=bb)


def _box_solid(sid, lx, ly, lz):
    cx, cy, cz = lx/2, ly/2, lz/2
    faces = [
        _pf(0,(1,0,0),(lx,cy,cz),ly*lz,(lx,0,0,lx,ly,lz)),
        _pf(1,(-1,0,0),(0,cy,cz),ly*lz,(0,0,0,0,ly,lz)),
        _pf(2,(0,1,0),(cx,ly,cz),lx*lz,(0,ly,0,lx,ly,lz)),
        _pf(3,(0,-1,0),(cx,0,cz),lx*lz,(0,0,0,lx,0,lz)),
        _pf(4,(0,0,1),(cx,cy,lz),lx*ly,(0,0,lz,lx,ly,lz)),
        _pf(5,(0,0,-1),(cx,cy,0),lx*ly,(0,0,0,lx,ly,0)),
    ]
    return SolidData(solid_id=sid, faces=faces, adjacency={i:[] for i in range(6)})


def _box_with_hole(sid, lx, ly, lz, r, h):
    """Box with one cylindrical bore (Z-axis)."""
    cx, cy, cz = lx/2, ly/2, lz/2
    faces = [
        _pf(0,(1,0,0),(lx,cy,cz),ly*lz,(lx,0,0,lx,ly,lz)),
        _pf(1,(-1,0,0),(0,cy,cz),ly*lz,(0,0,0,0,ly,lz)),
        _pf(2,(0,1,0),(cx,ly,cz),lx*lz,(0,ly,0,lx,ly,lz)),
        _pf(3,(0,-1,0),(cx,0,cz),lx*lz,(0,0,0,lx,0,lz)),
        _pf(4,(0,0,1),(cx,cy,lz),lx*ly,(0,0,lz,lx,ly,lz)),
        _pf(5,(0,0,-1),(cx,cy,0),lx*ly,(0,0,0,lx,ly,0)),
        _cf(6,(cx,cy,cz),2*math.pi*r*h,(cx-r,cy-r,(lz-h)/2,cx+r,cy+r,(lz+h)/2)),
    ]
    return SolidData(solid_id=sid, faces=faces, adjacency={i:[] for i in range(7)})


def _solid_dims(sid, lx, ly, lz, r=None, h=None):
    if r is not None:
        raw = _box_with_hole(sid, lx, ly, lz, r, h)
    else:
        raw = _box_solid(sid, lx, ly, lz)
    return infer_solid_dimensions(raw)


# ---------------------------------------------------------------------------
# Minimal process databases
# ---------------------------------------------------------------------------

FINE_DB = {
    "grinding": {
        "typical_it_grade": "IT5",
        "min_feature_size_mm": 1.0,
        "dimensional_range_mm": [3, 300],
    }
}

MEDIUM_DB = {
    "milling": {
        "typical_it_grade": "IT9",
        "min_feature_size_mm": 0.5,
        "dimensional_range_mm": [1, 2000],
    }
}

COARSE_DB = {
    "casting": {
        "typical_it_grade": "IT14",
        "min_feature_size_mm": 3.0,
        "dimensional_range_mm": [10, 2000],
    }
}


# ===========================================================================
# _it_int / _classify / _tol / _general_tol_note
# ===========================================================================

class TestHelpers(unittest.TestCase):

    def test_it_int_parsing(self):
        self.assertEqual(_it_int("IT5"), 5)
        self.assertEqual(_it_int("IT14"), 14)
        self.assertEqual(_it_int("IT8"), 8)

    def test_classify_fine(self):
        for it in range(1, 8):
            self.assertEqual(_classify(it), "fine")

    def test_classify_medium(self):
        for it in range(8, 12):
            self.assertEqual(_classify(it), "medium")

    def test_classify_coarse(self):
        for it in range(12, 17):
            self.assertEqual(_classify(it), "coarse")

    def test_tol_positive(self):
        for it in ["IT5", "IT8", "IT9", "IT14"]:
            self.assertGreater(_tol(50.0, it), 0)

    def test_tol_finer_is_tighter(self):
        self.assertLess(_tol(50.0, "IT5"), _tol(50.0, "IT9"))
        self.assertLess(_tol(50.0, "IT9"), _tol(50.0, "IT14"))

    def test_tol_larger_nominal_gives_larger_tolerance(self):
        self.assertLess(_tol(10.0, "IT9"), _tol(100.0, "IT9"))

    def test_tol_clamps_small_nominal(self):
        # Should not raise for sub-1mm values
        val = _tol(0.1, "IT9")
        self.assertGreater(val, 0)

    def test_general_tol_note_fine(self):
        self.assertIn("2768-fH", _general_tol_note(6))

    def test_general_tol_note_medium(self):
        self.assertIn("2768-mK", _general_tol_note(8))

    def test_general_tol_note_coarse(self):
        note = _general_tol_note(14)
        self.assertIn("2768", note)


# ===========================================================================
# DimensionEntry
# ===========================================================================

class TestDimensionEntry(unittest.TestCase):

    def _entry(self, kind="length", nominal=50.0, tol=0.046,
               it="IT8", priority="important"):
        return DimensionEntry(
            kind=kind, nominal_mm=nominal, tolerance_mm=tol,
            it_grade=it, description="test", solid_id=0,
            face_ids=[], priority=priority,
        )

    def test_drawing_annotation_plain(self):
        e = self._entry(kind="length", nominal=100.0, tol=0.087)
        ann = e.drawing_annotation()
        self.assertIn("100", ann)
        self.assertIn("±", ann)

    def test_drawing_annotation_diameter_prefix(self):
        e = self._entry(kind="diameter", nominal=20.0, tol=0.033)
        self.assertTrue(e.drawing_annotation().startswith("Ø"))

    def test_as_dict_keys(self):
        d = self._entry().as_dict()
        self.assertEqual(set(d.keys()), {
            "kind", "nominal_mm", "tolerance_mm", "it_grade",
            "annotation", "description", "solid_id", "face_ids", "priority",
        })


# ===========================================================================
# minimal_solid_dimensions — overall dimensions
# ===========================================================================

class TestOverallDimensions(unittest.TestCase):

    def _run(self, lx, ly, lz, proc, db):
        sd = _solid_dims(0, lx, ly, lz)
        return minimal_solid_dimensions(sd, proc, db)

    def test_always_three_overall_dims(self):
        for db, proc in [(FINE_DB,"grinding"), (MEDIUM_DB,"milling"), (COARSE_DB,"casting")]:
            mds = self._run(100, 50, 30, proc, db)
            kinds = [d.kind for d in mds.dimensions]
            for k in ("length", "width", "height"):
                self.assertIn(k, kinds, f"{k} missing for {proc}")

    def test_overall_values_match_solid_dims(self):
        sd = _solid_dims(0, 100, 50, 30)
        mds = minimal_solid_dimensions(sd, "milling", MEDIUM_DB)
        lengths = [d.nominal_mm for d in mds.dimensions if d.kind == "length"]
        widths  = [d.nominal_mm for d in mds.dimensions if d.kind == "width"]
        heights = [d.nominal_mm for d in mds.dimensions if d.kind == "height"]
        self.assertAlmostEqual(lengths[0], 100.0, places=4)
        self.assertAlmostEqual(widths[0],  50.0,  places=4)
        self.assertAlmostEqual(heights[0], 30.0,  places=4)

    def test_overall_tolerances_use_it_grade(self):
        sd = _solid_dims(0, 50, 50, 50)
        mds_fine   = minimal_solid_dimensions(sd, "grinding", FINE_DB)
        mds_coarse = minimal_solid_dimensions(sd, "casting",  COARSE_DB)
        fine_tol   = next(d.tolerance_mm for d in mds_fine.dimensions   if d.kind == "length")
        coarse_tol = next(d.tolerance_mm for d in mds_coarse.dimensions if d.kind == "length")
        self.assertLess(fine_tol, coarse_tol)

    def test_part_exceeding_range_gives_critical_priority(self):
        sd = _solid_dims(0, 500, 50, 30)  # 500 mm > COARSE_DB max of 2000 ... use a tight range
        tiny_db = {"proc": {"typical_it_grade": "IT14", "min_feature_size_mm": 3.0,
                             "dimensional_range_mm": [10, 100]}}
        mds = minimal_solid_dimensions(sd, "proc", tiny_db)
        crit = [d for d in mds.dimensions if d.priority == "critical" and d.kind == "length"]
        self.assertEqual(len(crit), 1)
        self.assertTrue(any("exceed" in w.lower() or "range" in w.lower() for w in mds.warnings))


# ===========================================================================
# minimal_solid_dimensions — cylindrical features
# ===========================================================================

class TestCylindricalDimensions(unittest.TestCase):

    def test_blind_cylinder_produces_diameter_and_depth(self):
        # h=20 in a box of height 30 → blind hole → depth must be annotated
        sd = _solid_dims(0, 100, 50, 30, r=8, h=20)
        mds = minimal_solid_dimensions(sd, "milling", MEDIUM_DB)
        kinds = [d.kind for d in mds.dimensions]
        self.assertIn("diameter", kinds)
        self.assertIn("depth", kinds)

    def test_through_hole_omits_depth(self):
        # h=30 matches the box height 30 → through-hole → depth derivable, must NOT appear
        sd = _solid_dims(0, 100, 50, 30, r=8, h=30)
        mds = minimal_solid_dimensions(sd, "milling", MEDIUM_DB)
        self.assertEqual([d for d in mds.dimensions if d.kind == "depth"], [])

    def test_no_cylinder_no_diameter_entry(self):
        sd = _solid_dims(0, 100, 50, 30)
        mds = minimal_solid_dimensions(sd, "milling", MEDIUM_DB)
        self.assertEqual([d for d in mds.dimensions if d.kind == "diameter"], [])

    def test_cylinder_below_threshold_gives_critical_and_warning(self):
        # diameter = 2r = 4mm < coarse threshold = 2 × 3mm = 6mm
        sd = _solid_dims(0, 100, 50, 30, r=2, h=10)
        mds = minimal_solid_dimensions(sd, "casting", COARSE_DB)
        crit = [d for d in mds.dimensions if d.kind == "diameter" and d.priority == "critical"]
        self.assertTrue(len(crit) >= 1)
        self.assertTrue(any("minimum" in w.lower() or "feature" in w.lower()
                            for w in mds.warnings))

    def test_medium_includes_position_dims(self):
        sd = _solid_dims(0, 100, 50, 30, r=8, h=20)
        mds = minimal_solid_dimensions(sd, "milling", MEDIUM_DB)
        pos_kinds = {d.kind for d in mds.dimensions}
        self.assertTrue(pos_kinds & {"position_x", "position_y", "position_z"})

    def test_coarse_has_no_position_dims(self):
        # coarse: large enough hole (r=10 > 2×min_feat=6)
        sd = _solid_dims(0, 100, 50, 30, r=10, h=20)
        mds = minimal_solid_dimensions(sd, "casting", COARSE_DB)
        pos = [d for d in mds.dimensions if d.kind.startswith("position_")]
        self.assertEqual(pos, [])

    def test_duplicate_diameters_deduplicated(self):
        # Two cylinders with nearly identical diameters on the same solid
        from post_process.shape_dimension import _estimate_cylinder
        raw = _box_with_hole(0, 200, 100, 50, r=10, h=30)
        # Add second cylinder very close in diameter
        extra = _cf(7, (150,50,25), 2*math.pi*10.05*30,
                     (150-10.05, 50-10.05, 10, 150+10.05, 50+10.05, 40))
        raw.faces.append(extra)
        sd = infer_solid_dimensions(raw)
        mds = minimal_solid_dimensions(sd, "milling", MEDIUM_DB)
        diameters = [d for d in mds.dimensions if d.kind == "diameter"]
        # Both ~Ø20 → should be grouped into one diameter spec
        self.assertEqual(len(diameters), 1)


# ===========================================================================
# minimal_solid_dimensions — wall thickness
# ===========================================================================

class TestWallThickness(unittest.TestCase):

    def test_simple_box_has_no_wall_thickness_entries(self):
        # ISO 129: outer walls = overall dims → already captured, must not be duplicated.
        for db, proc in [(FINE_DB,"grinding"), (MEDIUM_DB,"milling"), (COARSE_DB,"casting")]:
            sd = _solid_dims(0, 100, 50, 30)
            mds = minimal_solid_dimensions(sd, proc, db)
            walls = [d for d in mds.dimensions if d.kind == "wall_thickness"]
            self.assertEqual(walls, [],
                             f"Simple box must have 0 wall_thickness entries for {proc}")

    def test_stepped_solid_adds_step_not_outer(self):
        # A solid with a step (3 parallel planes in one direction) should add the
        # step dimension but NOT the outer wall (which equals the overall dim).
        # We simulate a step by adding an extra plane group with 3 faces in Z.
        from post_process.shape_dimension import PlaneGroup, WallThickness
        import math
        # Build a box with a step: Z planes at 0, 20, 50
        raw = _box_solid(0, 100, 60, 50)
        # Inject an intermediate plane face at z=20 (normal -Z → canonical +Z)
        step_face = _pf(10, (0, 0, -1), (50, 30, 20), 100*60, (0, 0, 20, 100, 60, 20))
        raw.faces.append(step_face)
        sd = infer_solid_dimensions(raw)
        mds = minimal_solid_dimensions(sd, "grinding", FINE_DB)
        walls = [d for d in mds.dimensions if d.kind == "wall_thickness"]
        # Open-chain rule: 2 gaps (20, 30) → add 1 (the smaller=20), skip 30 (derivable)
        self.assertEqual(len(walls), 1)
        self.assertAlmostEqual(walls[0].nominal_mm, 20.0, places=3)

    def test_wall_below_min_feature_raises_warning(self):
        # A solid whose height is below min_feature_size triggers a warning.
        # The overall height dim carries critical priority (below dim_min=1 for MEDIUM_DB).
        sd = _solid_dims(0, 100, 50, 0.2)  # 0.2mm < min_feat=0.5mm and < dim_min=1
        mds = minimal_solid_dimensions(sd, "milling", MEDIUM_DB)
        # Warning must be issued (wording includes "wall" or "below" or "feature")
        self.assertTrue(any("0.2" in w or "feature" in w.lower() or "wall" in w.lower()
                            for w in mds.warnings))
        # Overall height dimension must be critical
        crit_overall = [d for d in mds.dimensions
                        if d.kind == "height" and d.priority == "critical"]
        self.assertGreater(len(crit_overall), 0)

    def test_coarse_thin_overall_dim_is_critical(self):
        # Height 4mm < dim_min=10 for COARSE_DB → overall height is critical.
        sd = _solid_dims(0, 100, 50, 4)
        mds = minimal_solid_dimensions(sd, "casting", COARSE_DB)
        crit = [d for d in mds.dimensions if d.priority == "critical"]
        self.assertGreater(len(crit), 0)
        # No wall_thickness entries for a simple box (outer wall = overall dim)
        walls = [d for d in mds.dimensions if d.kind == "wall_thickness"]
        self.assertEqual(walls, [])


# ===========================================================================
# minimal_solid_dimensions — process class behaviour
# ===========================================================================

class TestProcessClassBehaviour(unittest.TestCase):

    def test_fine_more_dims_than_coarse(self):
        sd = _solid_dims(0, 100, 50, 30, r=10, h=20)
        fine   = minimal_solid_dimensions(sd, "grinding", FINE_DB)
        coarse = minimal_solid_dimensions(sd, "casting",  COARSE_DB)
        self.assertGreater(fine.count(), coarse.count())

    def test_it_grade_stored(self):
        sd = _solid_dims(0, 50, 50, 50)
        mds = minimal_solid_dimensions(sd, "grinding", FINE_DB)
        self.assertEqual(mds.it_grade, "IT5")

    def test_process_class_stored(self):
        self.assertEqual(
            minimal_solid_dimensions(_solid_dims(0,50,50,50),"grinding",FINE_DB).process_class,
            "fine"
        )
        self.assertEqual(
            minimal_solid_dimensions(_solid_dims(0,50,50,50),"milling",MEDIUM_DB).process_class,
            "medium"
        )
        self.assertEqual(
            minimal_solid_dimensions(_solid_dims(0,50,50,50),"casting",COARSE_DB).process_class,
            "coarse"
        )

    def test_general_tolerance_note_set(self):
        mds = minimal_solid_dimensions(_solid_dims(0,50,50,50), "milling", MEDIUM_DB)
        self.assertIn("ISO 2768", mds.general_tolerance_note)

    def test_as_dict_json_serializable(self):
        mds = minimal_solid_dimensions(_solid_dims(0,100,50,30,r=8,h=20), "milling", MEDIUM_DB)
        json.dumps(mds.as_dict())

    def test_by_kind_filter(self):
        mds = minimal_solid_dimensions(_solid_dims(0,100,50,30), "milling", MEDIUM_DB)
        lengths = mds.by_kind("length")
        self.assertEqual(len(lengths), 1)
        self.assertEqual(lengths[0].kind, "length")

    def test_critical_filter(self):
        tiny_db = {"proc": {"typical_it_grade":"IT9","min_feature_size_mm":0.5,
                             "dimensional_range_mm":[1,50]}}
        sd = _solid_dims(0, 100, 50, 30)  # 100mm > 50mm max → critical
        mds = minimal_solid_dimensions(sd, "proc", tiny_db)
        self.assertGreater(len(mds.critical()), 0)


# ===========================================================================
# minimal_dimensions (assembly level)
# ===========================================================================

class TestMinimalDimensions(unittest.TestCase):

    def _shape(self, *solids):
        return ShapeDimensions(solids=list(solids))

    def test_one_result_per_solid(self):
        shape = self._shape(
            _solid_dims(0, 100, 50, 30),
            _solid_dims(1, 60, 40, 20),
        )
        results = minimal_dimensions(shape, "milling", MEDIUM_DB)
        self.assertEqual(len(results), 2)

    def test_solid_ids_preserved(self):
        shape = self._shape(_solid_dims(7, 50, 50, 50))
        results = minimal_dimensions(shape, "milling", MEDIUM_DB)
        self.assertEqual(results[0].solid_id, 7)

    def test_empty_shape(self):
        shape = ShapeDimensions(solids=[])
        self.assertEqual(minimal_dimensions(shape, "milling", MEDIUM_DB), [])

    def test_unknown_process_raises(self):
        shape = self._shape(_solid_dims(0, 50, 50, 50))
        with self.assertRaises(ValueError):
            minimal_dimensions(shape, "laser_holography", MEDIUM_DB)


# ===========================================================================
# Integration (requires pythonocc-core)
# ===========================================================================

@unittest.skipUnless(HAVE_OCC, f"pythonocc-core not available: {OCC_IMPORT_ERROR}")
class TestIntegrationFlandersMake(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from tolerance_advisor.helpers import load_process_capabilities
        compound = read_step_single(str(DATA_DIR / "FlandersMake_part_NOK-Merger.step"))
        normalized = normalize_shape(compound)
        cls.shape_dims = _infer_dims_occ(normalized)
        cls.db = load_process_capabilities()

    def _run(self, process):
        return minimal_dimensions(self.shape_dims, process, self.db)

    def test_cnc_milling_has_overall_dims(self):
        results = self._run("CNC_milling")
        for mds in results:
            self.assertGreater(len(mds.by_kind("length")), 0)

    def test_finer_process_more_dims_than_coarser(self):
        fine   = sum(m.count() for m in self._run("cylindrical_grinding"))
        coarse = sum(m.count() for m in self._run("sand_casting"))
        self.assertGreaterEqual(fine, coarse)

    def test_all_dims_have_positive_nominal(self):
        for mds in self._run("CNC_milling"):
            for d in mds.dimensions:
                self.assertGreater(d.nominal_mm, 0, f"zero nominal for {d.kind}")

    def test_all_dims_have_positive_tolerance(self):
        for mds in self._run("CNC_milling"):
            for d in mds.dimensions:
                self.assertGreater(d.tolerance_mm, 0)

    def test_as_dict_json_serializable(self):
        results = self._run("CNC_milling")
        for mds in results:
            json.dumps(mds.as_dict())

    def test_process_class_coarse_fewer_than_medium(self):
        medium_count = sum(m.count() for m in self._run("CNC_milling"))
        coarse_count = sum(m.count() for m in self._run("sand_casting"))
        self.assertGreaterEqual(medium_count, coarse_count)


if __name__ == "__main__":
    unittest.main()
