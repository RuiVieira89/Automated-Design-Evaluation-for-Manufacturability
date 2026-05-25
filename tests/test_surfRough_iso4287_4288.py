"""Tests for tolerance_advisor/surfRough_iso4287_4288.py.

Covers:
  - recommend_surface_roughness: process capability, function selection,
    acceptance rules, return type, drawing callout
  - recommend_parameter: known function mappings, unknown function raises
  - recommend_standard: profile vs areal selection logic
  - list_surface_functions: catalogue completeness
  - ra_to_rz: conversion heuristic
  - _select_lambda_c: ISO 4288 table boundaries
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tolerance_advisor.surfRough_iso4287_4288 import (
    recommend_surface_roughness,
    recommend_parameter,
    recommend_standard,
    list_surface_functions,
    ra_to_rz,
    SurfaceRoughnessRecommendation,
    StandardRecommendation,
    _select_lambda_c,
)

# ---------------------------------------------------------------------------
# Minimal in-memory process DB
# ---------------------------------------------------------------------------

SAMPLE_DB = {
    "CNC_turning":          {"surface_roughness_ra_um": [0.8, 1.6, 3.2]},
    "cylindrical_grinding": {"surface_roughness_ra_um": [0.1, 0.4, 0.8]},
    "sand_casting":         {"surface_roughness_ra_um": [12.5, 25.0]},
    "injection_moulding":   {"surface_roughness_ra_um": [0.4, 1.6]},
    "no_roughness_entry":   {"typical_it_grade": "IT10"},
}


# ===========================================================================
# recommend_surface_roughness
# ===========================================================================

class TestRecommendSurfaceRoughness:

    def test_returns_correct_type(self):
        rec = recommend_surface_roughness("CNC_turning", process_db=SAMPLE_DB)
        assert isinstance(rec, SurfaceRoughnessRecommendation)

    def test_process_stored(self):
        rec = recommend_surface_roughness("sand_casting", process_db=SAMPLE_DB)
        assert rec.process == "sand_casting"

    def test_function_default_is_general(self):
        rec = recommend_surface_roughness("CNC_turning", process_db=SAMPLE_DB)
        assert rec.function == "general"

    # --- Ra range from process DB ---

    def test_cnc_turning_ra_range(self):
        rec = recommend_surface_roughness("CNC_turning", process_db=SAMPLE_DB)
        assert rec.ra_range_um == (0.8, 3.2)

    def test_grinding_ra_range(self):
        rec = recommend_surface_roughness("cylindrical_grinding", process_db=SAMPLE_DB)
        assert rec.ra_range_um == (0.1, 0.8)

    def test_sand_casting_ra_range(self):
        rec = recommend_surface_roughness("sand_casting", process_db=SAMPLE_DB)
        assert rec.ra_range_um == (12.5, 25.0)

    def test_missing_roughness_entry_uses_fallback(self):
        rec = recommend_surface_roughness("no_roughness_entry", process_db=SAMPLE_DB)
        assert rec.ra_range_um[0] > 0
        assert rec.ra_range_um[1] > 0

    # --- Rz approximation ---

    def test_rz_approx_is_four_times_ra_max(self):
        rec = recommend_surface_roughness("CNC_turning", process_db=SAMPLE_DB)
        assert rec.rz_approx_um == pytest.approx(rec.ra_range_um[1] * 4.0)

    # --- Function drives parameter selection ---

    @pytest.mark.parametrize("function, primary, secondary", [
        ("general",       "Ra",  "Rz"),
        ("sealing",       "Rz",  "Ra"),
        ("coating",       "Rz",  "Ra"),
        ("sliding",       "Ra",  "Rmr"),
        ("friction",      "RSm", "Ra"),
        ("lubrication",   "RSm", "Rmr"),
        ("bearing",       "Rmr", "Rz"),
        ("contact_stress","Rz",  "Rq"),
    ])
    def test_function_parameter_mapping(self, function, primary, secondary):
        rec = recommend_surface_roughness("CNC_turning", function=function, process_db=SAMPLE_DB)
        assert rec.primary_parameter == primary
        assert rec.secondary_parameter == secondary

    def test_unknown_function_falls_back_to_general(self):
        rec = recommend_surface_roughness("CNC_turning", function="welding", process_db=SAMPLE_DB)
        assert rec.function == "general"
        assert rec.primary_parameter == "Ra"

    def test_function_case_insensitive(self):
        rec_lower = recommend_surface_roughness("CNC_turning", function="sealing", process_db=SAMPLE_DB)
        rec_upper = recommend_surface_roughness("CNC_turning", function="SEALING", process_db=SAMPLE_DB)
        assert rec_lower.primary_parameter == rec_upper.primary_parameter

    # --- Acceptance rules ---

    def test_default_acceptance_rule_is_16pct(self):
        rec = recommend_surface_roughness("CNC_turning", process_db=SAMPLE_DB)
        assert "16%" in rec.acceptance_rule

    def test_max_rule_label(self):
        rec = recommend_surface_roughness("CNC_turning", acceptance_rule="max", process_db=SAMPLE_DB)
        assert "max rule" in rec.acceptance_rule

    def test_max_rule_adds_note(self):
        rec = recommend_surface_roughness("CNC_turning", acceptance_rule="max", process_db=SAMPLE_DB)
        assert any("max rule" in n.lower() or "stricter" in n.lower() for n in rec.notes)

    def test_notes_always_non_empty(self):
        rec = recommend_surface_roughness("CNC_turning", process_db=SAMPLE_DB)
        assert len(rec.notes) >= 1

    # --- Lambda c ---

    def test_cnc_turning_lambda_c(self):
        # Ra mid ~2.0 µm => lambda_c = 0.8 mm or 2.5 mm boundary
        rec = recommend_surface_roughness("CNC_turning", process_db=SAMPLE_DB)
        assert rec.lambda_c_mm in (0.8, 2.5)

    def test_grinding_lambda_c(self):
        # Ra mid ~0.45 µm => lambda_c = 0.8 mm
        rec = recommend_surface_roughness("cylindrical_grinding", process_db=SAMPLE_DB)
        assert rec.lambda_c_mm == pytest.approx(0.8)

    def test_casting_lambda_c(self):
        # Ra mid ~18.75 µm => lambda_c = 8.0 mm
        rec = recommend_surface_roughness("sand_casting", process_db=SAMPLE_DB)
        assert rec.lambda_c_mm == pytest.approx(8.0)

    # --- Unknown process ---

    def test_unknown_process_raises(self):
        with pytest.raises(ValueError, match="Unknown process"):
            recommend_surface_roughness("laser_ablation", process_db=SAMPLE_DB)

    # --- as_dict ---

    def test_as_dict_has_expected_keys(self):
        rec = recommend_surface_roughness("CNC_turning", process_db=SAMPLE_DB)
        d = rec.as_dict()
        assert set(d.keys()) == {
            "process", "function", "primary_parameter", "secondary_parameter",
            "ra_range_um", "rz_approx_um", "lambda_c_mm", "acceptance_rule", "notes",
        }

    # --- drawing_callout ---

    def test_drawing_callout_contains_ra_and_rz(self):
        rec = recommend_surface_roughness("CNC_turning", process_db=SAMPLE_DB)
        callout = rec.drawing_callout()
        assert "Ra" in callout
        assert "Rz" in callout

    def test_drawing_callout_max_rule_suffix(self):
        rec = recommend_surface_roughness("CNC_turning", acceptance_rule="max", process_db=SAMPLE_DB)
        callout = rec.drawing_callout()
        assert "max" in callout

    def test_drawing_callout_16pct_no_max_suffix(self):
        rec = recommend_surface_roughness("CNC_turning", acceptance_rule="16pct", process_db=SAMPLE_DB)
        callout = rec.drawing_callout()
        assert "max" not in callout


# ===========================================================================
# recommend_parameter
# ===========================================================================

class TestRecommendParameter:

    @pytest.mark.parametrize("function, primary", [
        ("general",       "Ra"),
        ("sealing",       "Rz"),
        ("bearing",       "Rmr"),
        ("friction",      "RSm"),
        ("contact_stress","Rz"),
    ])
    def test_known_functions(self, function, primary):
        p = recommend_parameter(function)
        assert p["primary"] == primary

    def test_returns_dict_with_required_keys(self):
        p = recommend_parameter("general")
        assert "primary" in p
        assert "secondary" in p
        assert "rationale" in p

    def test_unknown_function_raises(self):
        with pytest.raises(ValueError, match="Unknown surface function"):
            recommend_parameter("plasma_etching")

    def test_returns_copy_not_reference(self):
        p1 = recommend_parameter("general")
        p2 = recommend_parameter("general")
        p1["primary"] = "MUTATED"
        assert p2["primary"] == "Ra"


# ===========================================================================
# recommend_standard
# ===========================================================================

class TestRecommendStandard:

    def test_returns_correct_type(self):
        std = recommend_standard("general")
        assert isinstance(std, StandardRecommendation)

    def test_machined_general_recommends_profile(self):
        std = recommend_standard("general", surface_type="machined")
        assert std.recommended_standard == "ISO_4287_4288"

    def test_additive_recommends_areal(self):
        std = recommend_standard("general", surface_type="additive")
        assert std.recommended_standard == "ISO_25178"

    def test_isotropic_recommends_areal(self):
        std = recommend_standard("general", surface_type="isotropic")
        assert std.recommended_standard == "ISO_25178"

    def test_optical_recommends_areal(self):
        std = recommend_standard("general", surface_type="optical")
        assert std.recommended_standard == "ISO_25178"

    def test_friction_function_recommends_areal(self):
        std = recommend_standard("friction", surface_type="machined")
        assert std.recommended_standard == "ISO_25178"

    def test_lubrication_function_recommends_areal(self):
        std = recommend_standard("lubrication", surface_type="machined")
        assert std.recommended_standard == "ISO_25178"

    def test_sealing_machined_recommends_profile(self):
        std = recommend_standard("sealing", surface_type="machined")
        assert std.recommended_standard == "ISO_4287_4288"

    def test_surface_type_takes_precedence_over_function(self):
        # additive surface type always triggers ISO_25178 regardless of function
        std = recommend_standard("general", surface_type="additive")
        assert std.recommended_standard == "ISO_25178"

    def test_notes_always_non_empty(self):
        std = recommend_standard("general")
        assert len(std.notes) >= 1

    def test_rationale_non_empty(self):
        for fn in ["general", "sealing", "friction"]:
            std = recommend_standard(fn)
            assert len(std.rationale) > 0


# ===========================================================================
# list_surface_functions
# ===========================================================================

class TestListSurfaceFunctions:

    def test_returns_list(self):
        assert isinstance(list_surface_functions(), list)

    def test_expected_functions_present(self):
        fns = list_surface_functions()
        for expected in ["general", "sealing", "coating", "sliding",
                         "friction", "lubrication", "bearing", "contact_stress"]:
            assert expected in fns

    def test_no_duplicates(self):
        fns = list_surface_functions()
        assert len(fns) == len(set(fns))


# ===========================================================================
# ra_to_rz
# ===========================================================================

class TestRaToRz:

    @pytest.mark.parametrize("ra, expected_rz", [
        (0.1,  0.4),
        (0.8,  3.2),
        (1.6,  6.4),
        (3.2,  12.8),
        (12.5, 50.0),
        (25.0, 100.0),
    ])
    def test_known_values(self, ra, expected_rz):
        assert ra_to_rz(ra) == pytest.approx(expected_rz)

    def test_proportional(self):
        assert ra_to_rz(2.0) == pytest.approx(ra_to_rz(1.0) * 2.0)


# ===========================================================================
# _select_lambda_c (ISO 4288 table)
# ===========================================================================

class TestSelectLambdaC:

    @pytest.mark.parametrize("ra, expected_lc", [
        (0.006,  0.08),   # lower boundary of table
        (0.01,   0.08),
        (0.02,   0.08),   # boundary belongs to first row
        (0.05,   0.25),
        (0.1,    0.25),  # Ra=0.1 is the upper bound of the 0.02-0.1 row (lc=0.25)
        (1.0,    0.8),
        (2.0,    0.8),    # boundary belongs to third row
        (5.0,    2.5),
        (10.0,   2.5),   # boundary belongs to fourth row
        (40.0,   8.0),
        (80.0,   8.0),
    ])
    def test_table_values(self, ra, expected_lc):
        assert _select_lambda_c(ra) == pytest.approx(expected_lc)

    def test_below_table_clamps_to_lowest(self):
        assert _select_lambda_c(0.001) == pytest.approx(0.08)

    def test_above_table_clamps_to_highest(self):
        assert _select_lambda_c(200.0) == pytest.approx(8.0)
