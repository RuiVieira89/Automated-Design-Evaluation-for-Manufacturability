"""Tests for tolerance_advisor/linTol_iso2768.py.

All expected values are taken directly from the published ISO 2768 tables:
  ISO 2768-1:1989 Table 1  (linear)
  ISO 2768-1:1989 Table 3  (angular)
  ISO 2768-2:1989 Tables 1-3 (geometric)

Tests use an in-memory process DB to avoid filesystem / PyYAML dependency.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tolerance_advisor.linTol_iso2768 import (
    linear_tol_iso2768,
    fundamental_tol_iso2768,
    angular_tol_iso2768,
    geometric_tol_iso2768,
    propose_general_tolerance,
    recommend_title_block,
    TitleBlockRecommendation,
    list_linear_classes,
    list_geo_classes,
    list_geo_characteristics,
)

# ---------------------------------------------------------------------------
# Minimal in-memory process DB (mirrors process_capabilities.yaml)
# ---------------------------------------------------------------------------

SAMPLE_DB = {
    "CNC_turning": {"typical_it_grade": "IT8"},
    "cylindrical_grinding": {"typical_it_grade": "IT5"},
    "sand_casting": {"typical_it_grade": "IT14"},
    "injection_moulding": {"typical_it_grade": "IT12"},
    "custom_fine": {"typical_it_grade": "IT6"},
    "custom_very_coarse": {"typical_it_grade": "IT15"},
}


# ===========================================================================
# ISO 2768-1  Part 1 — Linear tolerances
# ===========================================================================

class TestLinearTol:

    # --- Known table values (ISO 2768-1:1989 Table 1) ---

    @pytest.mark.parametrize("nominal, cls, expected", [
        # 0.5–3 mm
        (2.0,    "f", 0.05),
        (2.0,    "m", 0.10),
        (2.0,    "c", 0.20),
        # 3–6 mm
        (5.0,    "f", 0.05),
        (5.0,    "m", 0.10),
        (5.0,    "c", 0.30),
        (5.0,    "v", 0.50),
        # 6–30 mm
        (18.0,   "f", 0.10),
        (18.0,   "m", 0.20),
        (18.0,   "c", 0.50),
        (18.0,   "v", 1.00),
        # 30–120 mm  (boundary: exactly 30 belongs to this row)
        (30.0,   "m", 0.20),   # ≤30 → 6-30 row
        (30.1,   "m", 0.30),   # >30 → 30-120 row
        (50.0,   "f", 0.15),
        (50.0,   "m", 0.30),
        (50.0,   "c", 0.80),
        (50.0,   "v", 1.50),
        # 120–400 mm
        (200.0,  "f", 0.20),
        (200.0,  "m", 0.50),
        (200.0,  "c", 1.20),
        (200.0,  "v", 2.50),
        # 400–1000 mm
        (600.0,  "f", 0.30),
        (600.0,  "m", 0.80),
        (600.0,  "c", 2.00),
        (600.0,  "v", 4.00),
        # 1000–2000 mm
        (1500.0, "f", 0.50),
        (1500.0, "m", 1.20),
        (1500.0, "c", 3.00),
        (1500.0, "v", 8.00),
        # 2000–4000 mm (f not defined)
        (3000.0, "m", 2.00),
        (3000.0, "c", 4.00),
        (3000.0, "v", 12.00),
    ])
    def test_table_values(self, nominal, cls, expected):
        assert linear_tol_iso2768(nominal, cls) == pytest.approx(expected)

    def test_v_not_defined_below_3mm(self):
        with pytest.raises(ValueError, match="not defined"):
            linear_tol_iso2768(2.0, "v")

    def test_f_not_defined_above_2000mm(self):
        with pytest.raises(ValueError, match="not defined"):
            linear_tol_iso2768(2500.0, "f")

    def test_unknown_class_falls_back_to_m(self):
        assert linear_tol_iso2768(50.0, "x") == linear_tol_iso2768(50.0, "m")

    def test_case_insensitive_class(self):
        assert linear_tol_iso2768(50.0, "F") == linear_tol_iso2768(50.0, "f")
        assert linear_tol_iso2768(50.0, "M") == linear_tol_iso2768(50.0, "m")

    def test_boundary_inclusive_upper(self):
        # 120.0 belongs to the 30–120 row, not the 120–400 row
        assert linear_tol_iso2768(120.0, "m") == pytest.approx(0.30)
        assert linear_tol_iso2768(120.1, "m") == pytest.approx(0.50)

    # --- Backwards-compatibility alias ---

    def test_fundamental_tol_alias(self):
        assert fundamental_tol_iso2768(50.0, "m") == linear_tol_iso2768(50.0, "m")
        assert fundamental_tol_iso2768 is not None

    # --- Catalogue ---

    def test_list_linear_classes(self):
        assert list_linear_classes() == ["f", "m", "c", "v"]

    def test_ordering_tighter_to_looser(self):
        tols = [linear_tol_iso2768(50.0, cls) for cls in list_linear_classes()]
        assert tols == sorted(tols)


# ===========================================================================
# ISO 2768-1  Part 1 — Angular tolerances
# ===========================================================================

class TestAngularTol:

    @pytest.mark.parametrize("side, cls, expected_deg", [
        # ≤10 mm
        (8.0,   "f", 1.000),
        (8.0,   "m", 1.000),   # f == m
        (8.0,   "c", 1.500),
        (8.0,   "v", 3.000),
        # >10–50 mm
        (25.0,  "f", 0.500),
        (25.0,  "m", 0.500),
        (25.0,  "c", 1.000),
        (25.0,  "v", 2.000),
        # >50–120 mm
        (80.0,  "f", 0.333),
        (80.0,  "c", 0.500),
        (80.0,  "v", 1.000),
        # >120–400 mm
        (200.0, "m", 0.167),
        (200.0, "c", 0.250),
        (200.0, "v", 0.500),
        # >400 mm
        (600.0, "f", 0.083),
        (600.0, "c", 0.167),
        (600.0, "v", 0.333),
    ])
    def test_table_values(self, side, cls, expected_deg):
        res = angular_tol_iso2768(side, cls)
        assert res["tolerance_deg"] == pytest.approx(expected_deg, abs=0.001)
        assert res["class"] == cls

    def test_f_equals_m_for_angular(self):
        for side in [5.0, 25.0, 80.0, 200.0, 600.0]:
            f_res = angular_tol_iso2768(side, "f")
            m_res = angular_tol_iso2768(side, "m")
            assert f_res["tolerance_deg"] == pytest.approx(m_res["tolerance_deg"])

    def test_dms_format_whole_degree(self):
        res = angular_tol_iso2768(8.0, "f")
        assert res["tolerance_dms"] == "±1°"

    def test_dms_format_with_minutes(self):
        res = angular_tol_iso2768(25.0, "f")  # 0.5° = 0°30'
        assert res["tolerance_dms"] == "±0°30'"

    def test_result_keys(self):
        res = angular_tol_iso2768(50.0, "m")
        assert set(res.keys()) == {"class", "tolerance_deg", "tolerance_dms"}

    def test_unknown_class_falls_back_to_m(self):
        res = angular_tol_iso2768(50.0, "z")
        assert res["class"] == "m"


# ===========================================================================
# ISO 2768-2  Part 2 — Geometric tolerances
# ===========================================================================

class TestGeometricTol:

    # --- Straightness / Flatness (ISO 2768-2:1989 Table 1) ---

    @pytest.mark.parametrize("size, gcls, char, expected", [
        ( 8.0, "H", "straightness",   0.02),
        ( 8.0, "K", "straightness",   0.05),
        ( 8.0, "L", "straightness",   0.10),
        (20.0, "H", "flatness",       0.05),
        (20.0, "K", "flatness",       0.10),
        (20.0, "L", "flatness",       0.20),
        (60.0, "H", "straightness",   0.10),
        (60.0, "K", "straightness",   0.20),
        (60.0, "L", "straightness",   0.40),
        (200.0,"H", "flatness",       0.20),
        (200.0,"K", "flatness",       0.40),
        (200.0,"L", "flatness",       0.80),
        (600.0,"H", "straightness",   0.30),
        (600.0,"K", "straightness",   0.60),
        (600.0,"L", "straightness",   1.20),
        (2000.0,"H","flatness",       0.40),
        (2000.0,"K","flatness",       0.80),
        (2000.0,"L","flatness",       1.60),
    ])
    def test_straight_flat(self, size, gcls, char, expected):
        assert geometric_tol_iso2768(size, gcls, char) == pytest.approx(expected)

    # --- Perpendicularity / Symmetry (ISO 2768-2:1989 Table 2) ---

    @pytest.mark.parametrize("size, gcls, char, expected", [
        ( 50.0, "H", "perpendicularity", 0.20),
        ( 50.0, "K", "perpendicularity", 0.40),
        ( 50.0, "L", "perpendicularity", 0.60),
        (200.0, "H", "symmetry",         0.30),
        (200.0, "K", "symmetry",         0.60),
        (200.0, "L", "symmetry",         1.00),
        (600.0, "H", "perpendicularity", 0.40),
        (600.0, "K", "perpendicularity", 0.80),
        (600.0, "L", "perpendicularity", 1.50),
        (2000.0,"H", "symmetry",         0.50),
        (2000.0,"K", "symmetry",         1.00),
        (2000.0,"L", "symmetry",         2.00),
    ])
    def test_perp_sym(self, size, gcls, char, expected):
        assert geometric_tol_iso2768(size, gcls, char) == pytest.approx(expected)

    # --- Circular run-out (ISO 2768-2:1989 Table 3) — size-independent ---

    @pytest.mark.parametrize("gcls, expected", [
        ("H", 0.10), ("K", 0.20), ("L", 0.50),
    ])
    def test_runout(self, gcls, expected):
        for size in [5.0, 100.0, 1000.0]:
            assert geometric_tol_iso2768(size, gcls, "circular_runout") == pytest.approx(expected)

    def test_unknown_geo_class_raises(self):
        with pytest.raises(ValueError, match="Unknown ISO 2768-2 class"):
            geometric_tol_iso2768(50.0, "X", "flatness")

    def test_unknown_characteristic_raises(self):
        with pytest.raises(ValueError, match="not in ISO 2768-2 scope"):
            geometric_tol_iso2768(50.0, "K", "cylindricity")

    def test_list_geo_classes(self):
        assert list_geo_classes() == ["H", "K", "L"]

    def test_list_geo_characteristics(self):
        chars = list_geo_characteristics()
        assert "straightness" in chars
        assert "flatness" in chars
        assert "perpendicularity" in chars
        assert "symmetry" in chars
        assert "circular_runout" in chars

    def test_geo_class_case_insensitive(self):
        assert geometric_tol_iso2768(50.0, "k", "flatness") == geometric_tol_iso2768(50.0, "K", "flatness")


# ===========================================================================
# Process-driven API
# ===========================================================================

class TestProposeGeneralTolerance:

    def test_cnc_turning_class_m(self):
        res = propose_general_tolerance(50.0, "CNC_turning", SAMPLE_DB)
        assert res["class"] == "m"
        assert res["tolerance_mm"] == pytest.approx(0.30)

    def test_grinding_class_f(self):
        res = propose_general_tolerance(50.0, "cylindrical_grinding", SAMPLE_DB)
        assert res["class"] == "f"
        assert res["tolerance_mm"] == pytest.approx(0.15)

    def test_sand_casting_class_c(self):
        res = propose_general_tolerance(50.0, "sand_casting", SAMPLE_DB)
        assert res["class"] == "c"

    def test_injection_moulding_class_c(self):
        res = propose_general_tolerance(50.0, "injection_moulding", SAMPLE_DB)
        assert res["class"] == "c"

    def test_unknown_process_raises(self):
        with pytest.raises(ValueError, match="Unknown process"):
            propose_general_tolerance(50.0, "laser_ablation", SAMPLE_DB)

    def test_tolerance_mm_is_positive(self):
        res = propose_general_tolerance(25.0, "CNC_turning", SAMPLE_DB)
        assert res["tolerance_mm"] > 0

    def test_result_keys(self):
        res = propose_general_tolerance(50.0, "CNC_turning", SAMPLE_DB)
        assert "class" in res
        assert "tolerance_mm" in res


class TestRecommendTitleBlock:

    def test_cnc_turning_title_block(self):
        tb = recommend_title_block("CNC_turning", SAMPLE_DB)
        assert tb.title_block == "ISO 2768-mK"
        assert tb.linear_class == "m"
        assert tb.geo_class == "K"

    def test_grinding_title_block(self):
        tb = recommend_title_block("cylindrical_grinding", SAMPLE_DB)
        assert tb.title_block == "ISO 2768-fH"
        assert tb.linear_class == "f"
        assert tb.geo_class == "H"

    def test_sand_casting_title_block(self):
        tb = recommend_title_block("sand_casting", SAMPLE_DB)
        assert tb.title_block == "ISO 2768-cL"
        assert tb.linear_class == "c"

    def test_injection_moulding_title_block(self):
        tb = recommend_title_block("injection_moulding", SAMPLE_DB)
        assert tb.title_block == "ISO 2768-cK"

    def test_returns_title_block_recommendation(self):
        tb = recommend_title_block("CNC_turning", SAMPLE_DB)
        assert isinstance(tb, TitleBlockRecommendation)

    def test_notes_always_include_scope_warning(self):
        tb = recommend_title_block("CNC_turning", SAMPLE_DB)
        scope_notes = [n for n in tb.notes if "non-critical" in n]
        assert len(scope_notes) >= 1

    def test_coarse_class_triggers_stack_up_note(self):
        tb = recommend_title_block("sand_casting", SAMPLE_DB)
        coarse_notes = [n for n in tb.notes if "stack-up" in n or "coarse" in n]
        assert len(coarse_notes) >= 1

    def test_fine_class_no_stack_up_note(self):
        tb = recommend_title_block("cylindrical_grinding", SAMPLE_DB)
        coarse_notes = [n for n in tb.notes if "stack-up" in n]
        assert len(coarse_notes) == 0

    def test_as_dict_keys(self):
        tb = recommend_title_block("CNC_turning", SAMPLE_DB)
        d = tb.as_dict()
        assert set(d.keys()) == {"linear_class", "geo_class", "title_block", "process", "notes"}

    def test_process_and_class_consistency(self):
        for proc in SAMPLE_DB:
            gen = propose_general_tolerance(50.0, proc, SAMPLE_DB)
            tb = recommend_title_block(proc, SAMPLE_DB)
            assert gen["class"] == tb.linear_class, (
                f"propose_general_tolerance and recommend_title_block disagree "
                f"on linear class for process '{proc}'"
            )

    def test_unknown_process_raises(self):
        with pytest.raises(ValueError, match="Unknown process"):
            recommend_title_block("waterjet_cutting", SAMPLE_DB)

    def test_it_grade_fallback_fine(self):
        tb = recommend_title_block("custom_fine", SAMPLE_DB)
        assert tb.linear_class == "f"
        assert tb.geo_class == "H"

    def test_it_grade_fallback_very_coarse(self):
        tb = recommend_title_block("custom_very_coarse", SAMPLE_DB)
        assert tb.linear_class == "v"
