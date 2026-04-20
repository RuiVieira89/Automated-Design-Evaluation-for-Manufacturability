import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from tolerance_advisor.fit_iso286 import (
    fundamental_tolerance,
    propose_tolerance,
    evaluate_fit,
    select_fit,
    hole_deviations,
    shaft_deviations,
    list_fit_options,
    FitResult,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_DB = {
    "CNC_turning": {
        "typical_it_grade": "IT8",
        "iso_it_grades": ["IT6", "IT7", "IT8", "IT9"],
        "surface_roughness_ra_um": [0.8, 1.6, 3.2],
    },
    "sand_casting": {
        "typical_it_grade": "IT14",
        "iso_it_grades": ["IT12", "IT13", "IT14", "IT15"],
        "surface_roughness_ra_um": [12.5, 25.0],
    },
}

# ---------------------------------------------------------------------------
# fundamental_tolerance — IT6-IT11 use tabulated values (25 sub-ranges)
# ---------------------------------------------------------------------------

def test_fundamental_tolerance_it7_25mm():
    # 25 mm → FIT_SIZE_RANGES index 6 (24-30); IT7[6] = 21 µm
    assert fundamental_tolerance(25.0, "IT7") == pytest.approx(0.021, abs=1e-6)

def test_fundamental_tolerance_it6_25mm():
    # IT6[6] = 13 µm
    assert fundamental_tolerance(25.0, "IT6") == pytest.approx(0.013, abs=1e-6)

def test_fundamental_tolerance_it8_25mm():
    # IT8[6] = 33 µm
    assert fundamental_tolerance(25.0, "IT8") == pytest.approx(0.033, abs=1e-6)

def test_fundamental_tolerance_it9_25mm():
    # IT9[6] = 52 µm
    assert fundamental_tolerance(25.0, "IT9") == pytest.approx(0.052, abs=1e-6)

def test_fundamental_tolerance_it11_25mm():
    # IT11[6] = 130 µm
    assert fundamental_tolerance(25.0, "IT11") == pytest.approx(0.130, abs=1e-6)

def test_fundamental_tolerance_tabulated_subrange():
    # 35 mm is in FIT_SIZE_RANGES index 7 (30-40); IT7[7] = 25 µm
    assert fundamental_tolerance(35.0, "IT7") == pytest.approx(0.025, abs=1e-6)
    # 45 mm is in index 8 (40-50); IT7[8] = 25 µm
    assert fundamental_tolerance(45.0, "IT7") == pytest.approx(0.025, abs=1e-6)
    # 55 mm is in index 9 (50-65); IT7[9] = 30 µm
    assert fundamental_tolerance(55.0, "IT7") == pytest.approx(0.030, abs=1e-6)
    # 70 mm is in index 10 (65-80); IT7[10] = 30 µm
    assert fundamental_tolerance(70.0, "IT7") == pytest.approx(0.030, abs=1e-6)

def test_fundamental_tolerance_monotonic_for_25mm():
    grades = ["IT01", "IT0"] + [f"IT{n}" for n in range(1, 19)]
    values = [fundamental_tolerance(25.0, g) for g in grades]
    for a, b in zip(values, values[1:]):
        assert a < b, "IT grades must produce strictly increasing tolerances"

def test_fundamental_tolerance_all_grades_positive():
    grades = ["IT01", "IT0"] + [f"IT{n}" for n in range(1, 19)]
    for g in grades:
        assert fundamental_tolerance(10.0, g) > 0

def test_fundamental_tolerance_fine_grades_formula():
    tol = fundamental_tolerance(25.0, "IT01")
    assert tol < 0.001

def test_fundamental_tolerance_out_of_range():
    with pytest.raises(ValueError, match="outside"):
        fundamental_tolerance(600.0, "IT7")

def test_fundamental_tolerance_bad_grade():
    with pytest.raises(ValueError, match="Unsupported"):
        fundamental_tolerance(25.0, "IT99")

# ---------------------------------------------------------------------------
# propose_tolerance
# ---------------------------------------------------------------------------

def test_propose_tolerance_returns_expected_keys():
    res = propose_tolerance(25.0, "CNC_turning", SAMPLE_DB)
    assert res["nominal_mm"] == 25.0
    assert res["process"] == "CNC_turning"
    assert res["it_grade"] == "IT8"
    assert 0.0 < res["tolerance_mm"] < 0.1
    assert isinstance(res["achievable_grades"], list)

def test_propose_tolerance_unknown_process():
    with pytest.raises(ValueError, match="Unknown process"):
        propose_tolerance(25.0, "laser_sintering", SAMPLE_DB)

# ---------------------------------------------------------------------------
# select_fit
# ---------------------------------------------------------------------------

def test_select_fit_clearance_sliding():
    hole, shaft = select_fit("clearance", "sliding")
    assert hole == "H7" and shaft == "g6"

def test_select_fit_interference_medium():
    hole, shaft = select_fit("interference", "medium")
    assert hole == "H7" and shaft == "s6"

def test_select_fit_interference_medium_light():
    hole, shaft = select_fit("interference", "medium_light")
    assert hole == "H7" and shaft == "r6"

def test_select_fit_bad_category():
    with pytest.raises(ValueError, match="fit_category"):
        select_fit("unknown", "sliding")

def test_select_fit_bad_type():
    with pytest.raises(ValueError, match="clearance_type"):
        select_fit("clearance", "nonexistent")

# ---------------------------------------------------------------------------
# hole_deviations — H and non-H letters
# ---------------------------------------------------------------------------

def test_hole_deviations_H7_zero_lower():
    EI, ES = hole_deviations(25.0, "H7")
    assert EI == 0.0
    assert ES == pytest.approx(0.021, abs=1e-6)

def test_hole_deviations_G7_clearance():
    # G hole: ES positive (clearance), both EI and ES > 0
    EI, ES = hole_deviations(25.0, "G7")
    assert ES > 0.0 and EI > 0.0  # both above nominal

def test_hole_deviations_F8_clearance():
    EI, ES = hole_deviations(50.0, "F8")
    assert ES > EI > 0.0

def test_hole_deviations_K7_transition():
    # K hole: ES small positive or zero, EI negative → transition
    EI, ES = hole_deviations(25.0, "K7")
    assert EI < 0.0

def test_hole_deviations_N7_transition():
    EI, ES = hole_deviations(25.0, "N7")
    assert ES < 0.0 or ES == pytest.approx(0.0, abs=1e-6)

def test_hole_deviations_R7_interference():
    EI, ES = hole_deviations(25.0, "R7")
    assert ES < 0.0 and EI < ES  # both below nominal

def test_hole_deviations_S7_more_interference_than_R7():
    _, ES_R = hole_deviations(25.0, "R7")
    _, ES_S = hole_deviations(25.0, "S7")
    assert ES_S < ES_R  # S is tighter than R

def test_hole_deviations_span_equals_it_tolerance():
    EI, ES = hole_deviations(50.0, "F8")
    it_tol = fundamental_tolerance(50.0, "IT8")
    assert abs((ES - EI) - it_tol) < 1e-9

def test_hole_deviations_unsupported_letter():
    with pytest.raises(ValueError, match="Unsupported"):
        hole_deviations(25.0, "A7")

# ---------------------------------------------------------------------------
# shaft_deviations
# ---------------------------------------------------------------------------

def test_shaft_deviations_h6_zero_upper():
    ei, es = shaft_deviations(25.0, "h6")
    assert es == 0.0 and ei < 0.0

def test_shaft_deviations_clearance_both_negative():
    ei, es = shaft_deviations(25.0, "g6")
    assert ei < es < 0.0

def test_shaft_deviations_interference_both_positive():
    ei, es = shaft_deviations(25.0, "s6")
    assert 0.0 < ei < es

def test_shaft_deviations_r6_between_p6_and_s6():
    # r is between p and s in interference magnitude
    _, es_p = shaft_deviations(50.0, "p6")
    _, es_r = shaft_deviations(50.0, "r6")
    _, es_s = shaft_deviations(50.0, "s6")
    assert es_p < es_r < es_s

def test_shaft_deviations_span_equals_it_tolerance():
    ei, es = shaft_deviations(25.0, "k6")
    it_tol = fundamental_tolerance(25.0, "IT6")
    assert abs((es - ei) - it_tol) < 1e-9

def test_shaft_deviations_tabulated_c_subrange():
    # c at 35 mm (30-40, index 7): _SHAFT_TABLE['c'][7] = -120 µm
    ei, es = shaft_deviations(35.0, "c11")
    assert es == pytest.approx(-0.120, abs=1e-6)
    # c at 45 mm (40-50, index 8): -130 µm
    ei, es = shaft_deviations(45.0, "c11")
    assert es == pytest.approx(-0.130, abs=1e-6)

def test_shaft_deviations_unsupported_letter():
    with pytest.raises(ValueError, match="Unsupported"):
        shaft_deviations(25.0, "z6")

# ---------------------------------------------------------------------------
# evaluate_fit — clearance fits
# ---------------------------------------------------------------------------

def test_evaluate_fit_clearance_always_positive():
    for ctype in ("loose", "free_running", "close_running", "sliding"):
        r = evaluate_fit(25.0, "clearance", ctype)
        assert r.is_always_clearance(), f"{ctype} should always be clearance"

def test_evaluate_fit_close_sliding_zero_min_clearance():
    # H7/h6: shaft es = 0 → EI_hole(0) - es_shaft(0) = 0
    r = evaluate_fit(25.0, "clearance", "close_sliding")
    assert abs(r.min_clearance_mm) < 1e-9

def test_evaluate_fit_clearance_limits_ordering():
    r = evaluate_fit(25.0, "clearance", "sliding")
    assert r.hole_min_mm < r.hole_max_mm
    assert r.shaft_min_mm < r.shaft_max_mm
    assert r.shaft_max_mm < r.hole_min_mm

# ---------------------------------------------------------------------------
# evaluate_fit — transition fits
# ---------------------------------------------------------------------------

def test_evaluate_fit_transition_k6():
    r = evaluate_fit(25.0, "transition", "accurate_location")
    assert r.is_transition()
    assert r.max_clearance_mm > 0.0
    assert r.min_clearance_mm < 0.0

def test_evaluate_fit_transition_n6():
    r = evaluate_fit(25.0, "transition", "positive_location")
    assert r.is_transition()

# ---------------------------------------------------------------------------
# evaluate_fit — interference fits (including r6)
# ---------------------------------------------------------------------------

def test_evaluate_fit_interference_always_negative():
    for ctype in ("light", "medium_light", "medium", "heavy"):
        r = evaluate_fit(25.0, "interference", ctype)
        assert r.is_always_interference(), f"{ctype} should always be interference"

def test_evaluate_fit_interference_ordering():
    # Heavier fit → more negative min_clearance
    light        = evaluate_fit(50.0, "interference", "light")
    medium_light = evaluate_fit(50.0, "interference", "medium_light")
    medium       = evaluate_fit(50.0, "interference", "medium")
    heavy        = evaluate_fit(50.0, "interference", "heavy")
    assert medium_light.min_clearance_mm < light.min_clearance_mm
    assert medium.min_clearance_mm       < medium_light.min_clearance_mm
    assert heavy.min_clearance_mm        < medium.min_clearance_mm

# ---------------------------------------------------------------------------
# evaluate_fit — FitResult structure
# ---------------------------------------------------------------------------

def test_evaluate_fit_returns_fitresult():
    r = evaluate_fit(25.0, "clearance", "sliding")
    assert isinstance(r, FitResult)
    assert r.fit_designation == "H7/g6"
    assert r.nominal_mm == 25.0

def test_evaluate_fit_absolute_limits_consistent():
    r = evaluate_fit(40.0, "transition", "accurate_location")
    assert abs(r.hole_min_mm - (r.nominal_mm + r.hole_EI_mm)) < 1e-9
    assert abs(r.hole_max_mm - (r.nominal_mm + r.hole_ES_mm)) < 1e-9
    assert abs(r.shaft_min_mm - (r.nominal_mm + r.shaft_ei_mm)) < 1e-9
    assert abs(r.shaft_max_mm - (r.nominal_mm + r.shaft_es_mm)) < 1e-9

def test_evaluate_fit_clearance_formula():
    r = evaluate_fit(25.0, "clearance", "sliding")
    assert abs(r.max_clearance_mm - (r.hole_ES_mm - r.shaft_ei_mm)) < 1e-9
    assert abs(r.min_clearance_mm - (r.hole_EI_mm - r.shaft_es_mm)) < 1e-9

# ---------------------------------------------------------------------------
# list_fit_options
# ---------------------------------------------------------------------------

def test_list_fit_options_structure():
    opts = list_fit_options()
    assert set(opts) == {"clearance", "transition", "interference"}
    assert "sliding" in opts["clearance"]
    assert "accurate_location" in opts["transition"]
    assert "medium_light" in opts["interference"]
    assert "heavy" in opts["interference"]
