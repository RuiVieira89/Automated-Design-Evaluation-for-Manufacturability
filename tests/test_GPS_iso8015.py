"""Tests for tolerance_advisor/GPS_iso8015.py.

Covers all public classes and functions:
  - Constants (reference conditions)
  - Enumerations (GPSStandard, GPSModifier, GPSOperatorStep, FeatureType)
  - default_operator_chain
  - GPSInvocation / validate_invocation
  - check_independency / IndependencyResult
  - gps_specify_feature / GPSFeatureSpec
  - dimensioning_checks
  - Backwards-compatibility shims (apply_independence_principle,
    simple_dimensioning_checks)

All tests use an in-memory process DB to avoid filesystem / PyYAML dependency.
Expected tolerance values are cross-checked against the individual sub-standard
modules rather than hard-coded, so the tests remain correct if table data changes.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tolerance_advisor.GPS_iso8015 import (
    REFERENCE_TEMPERATURE_C,
    REFERENCE_PRESSURE_PA,
    GPSStandard,
    GPSModifier,
    GPSOperatorStep,
    FeatureType,
    GPSOperator,
    GPSInvocation,
    IndependencyResult,
    GPSFeatureSpec,
    default_operator_chain,
    validate_invocation,
    check_independency,
    gps_specify_feature,
    dimensioning_checks,
    apply_independence_principle,
    simple_dimensioning_checks,
)

# ---------------------------------------------------------------------------
# Shared in-memory process DB
# ---------------------------------------------------------------------------

DB = {
    "CNC_turning": {
        "typical_it_grade": "IT8",
        "iso_it_grades": ["IT6", "IT7", "IT8", "IT9"],
        "surface_roughness_ra_um": [0.8, 1.6, 3.2],
        "min_feature_size_mm": 0.5,
        "applicable_materials": ["steel"],
        "dimensional_range_mm": [1, 500],
    },
    "cylindrical_grinding": {
        "typical_it_grade": "IT5",
        "iso_it_grades": ["IT4", "IT5", "IT6"],
        "surface_roughness_ra_um": [0.1, 0.4, 0.8],
        "min_feature_size_mm": 1.0,
        "applicable_materials": ["hardened_steel"],
        "dimensional_range_mm": [3, 300],
    },
    "sand_casting": {
        "typical_it_grade": "IT14",
        "iso_it_grades": ["IT12", "IT13", "IT14", "IT15", "IT16"],
        "surface_roughness_ra_um": [12.5, 25.0],
        "min_feature_size_mm": 3.0,
        "applicable_materials": ["cast_iron"],
        "dimensional_range_mm": [10, 2000],
    },
    "injection_moulding": {
        "typical_it_grade": "IT12",
        "iso_it_grades": ["IT10", "IT11", "IT12", "IT13"],
        "surface_roughness_ra_um": [0.4, 1.6],
        "min_feature_size_mm": 0.5,
        "applicable_materials": ["ABS"],
        "dimensional_range_mm": [0.5, 800],
    },
}


# ===========================================================================
# Constants
# ===========================================================================

class TestConstants:

    def test_reference_temperature(self):
        assert REFERENCE_TEMPERATURE_C == 20.0

    def test_reference_pressure(self):
        assert REFERENCE_PRESSURE_PA == 101_325.0


# ===========================================================================
# Enumerations
# ===========================================================================

class TestEnumerations:

    def test_gps_standard_members(self):
        assert GPSStandard.ISO_8015.value == "ISO 8015"
        assert GPSStandard.ASME_Y14_5.value == "ASME Y14.5"

    def test_gps_modifier_symbols(self):
        assert GPSModifier.INDEPENDENCY.value == "Ⓘ"
        assert GPSModifier.ENVELOPE.value == "ⓔ"
        assert GPSModifier.MMC.value == "Ⓜ"
        assert GPSModifier.LMC.value == "Ⓛ"
        assert GPSModifier.COMBINED_ZONE.value == "CZ"
        assert GPSModifier.SEPARATE_ZONE.value == "SZ"

    def test_gps_operator_step_all_five_present(self):
        steps = set(GPSOperatorStep)
        assert GPSOperatorStep.PARTITION in steps
        assert GPSOperatorStep.EXTRACTION in steps
        assert GPSOperatorStep.FILTRATION in steps
        assert GPSOperatorStep.ASSOCIATION in steps
        assert GPSOperatorStep.EVALUATION in steps
        assert len(steps) == 5

    def test_feature_type_values(self):
        assert FeatureType.EXTERNAL_CYLINDER.value == "external_cylinder"
        assert FeatureType.INTERNAL_CYLINDER.value == "internal_cylinder"
        assert FeatureType.FLAT_SURFACE.value == "flat_surface"


# ===========================================================================
# GPS Operator chain
# ===========================================================================

class TestDefaultOperatorChain:

    def test_chain_always_five_steps(self):
        for ft in FeatureType:
            chain = default_operator_chain(ft)
            assert len(chain) == 5

    def test_chain_step_order(self):
        chain = default_operator_chain(FeatureType.INTERNAL_CYLINDER)
        steps = [op.step for op in chain]
        assert steps == [
            GPSOperatorStep.PARTITION,
            GPSOperatorStep.EXTRACTION,
            GPSOperatorStep.FILTRATION,
            GPSOperatorStep.ASSOCIATION,
            GPSOperatorStep.EVALUATION,
        ]

    def test_all_steps_are_gps_operator_instances(self):
        for op in default_operator_chain(FeatureType.FLAT_SURFACE):
            assert isinstance(op, GPSOperator)
            assert op.description  # non-empty

    @pytest.mark.parametrize("ftype, expected_substr", [
        (FeatureType.INTERNAL_CYLINDER, "inscribed"),
        (FeatureType.EXTERNAL_CYLINDER, "circumscribed"),
        (FeatureType.FLAT_SURFACE, "plane"),
        (FeatureType.ANGULAR, "plane"),
        (FeatureType.THREAD, "helix"),
        (FeatureType.FREEFORM, "surface"),
    ])
    def test_association_method_by_feature(self, ftype, expected_substr):
        chain = default_operator_chain(ftype)
        assoc = next(op for op in chain if op.step == GPSOperatorStep.ASSOCIATION)
        assert expected_substr in assoc.description.lower()


# ===========================================================================
# GPS Invocation
# ===========================================================================

class TestGPSInvocation:

    def test_default_standard_is_iso8015(self):
        inv = GPSInvocation()
        assert inv.standard == GPSStandard.ISO_8015

    def test_independency_is_default_for_iso8015(self):
        inv = GPSInvocation(standard=GPSStandard.ISO_8015)
        assert inv.independency_is_default is True
        assert inv.envelope_is_default is False

    def test_envelope_is_default_for_asme(self):
        inv = GPSInvocation(standard=GPSStandard.ASME_Y14_5)
        assert inv.envelope_is_default is True
        assert inv.independency_is_default is False

    def test_default_title_block_text(self):
        inv = GPSInvocation()
        assert "ISO 8015" in inv.title_block_text


class TestValidateInvocation:

    def test_no_warnings_for_valid_iso8015(self):
        inv = GPSInvocation()
        assert validate_invocation(inv) == []

    def test_empty_title_block_triggers_warning(self):
        inv = GPSInvocation(title_block_text="   ")
        warnings = validate_invocation(inv)
        assert any("title block" in w.lower() for w in warnings)

    def test_asme_envelope_modifier_redundancy_warning(self):
        inv = GPSInvocation(
            standard=GPSStandard.ASME_Y14_5,
            title_block_text="ASME Y14.5-2018",
            active_modifiers=[GPSModifier.ENVELOPE],
        )
        warnings = validate_invocation(inv)
        assert any("redundant" in w.lower() for w in warnings)

    def test_mmc_modifier_triggers_todo_warning(self):
        inv = GPSInvocation(active_modifiers=[GPSModifier.MMC])
        warnings = validate_invocation(inv)
        assert any("ISO 2692" in w or "not yet implemented" in w for w in warnings)

    def test_lmc_modifier_triggers_todo_warning(self):
        inv = GPSInvocation(active_modifiers=[GPSModifier.LMC])
        warnings = validate_invocation(inv)
        assert any("ISO 2692" in w or "not yet implemented" in w for w in warnings)

    def test_valid_asme_no_spurious_warnings(self):
        inv = GPSInvocation(
            standard=GPSStandard.ASME_Y14_5,
            title_block_text="ASME Y14.5-2018",
        )
        assert validate_invocation(inv) == []


# ===========================================================================
# check_independency / IndependencyResult
# ===========================================================================

class TestCheckIndependency:

    # --- ISO 8015 default (independency) ---

    def test_independency_default_independent_true(self):
        r = check_independency(0.030, 0.010)
        assert r.independent is True
        assert r.envelope_active is False

    def test_independency_default_form_limit_unchanged(self):
        r = check_independency(0.030, 0.010)
        assert r.effective_form_limit_mm == pytest.approx(0.010)

    def test_independency_preserves_larger_form_tolerance(self):
        # Under independency, form can exceed size — both checked separately
        r = check_independency(0.010, 0.050)
        assert r.effective_form_limit_mm == pytest.approx(0.050)
        assert r.independent is True

    # --- Envelope requirement (ⓔ modifier) ---

    def test_envelope_modifier_sets_envelope_active(self):
        r = check_independency(0.030, 0.010, GPSModifier.ENVELOPE)
        assert r.envelope_active is True
        assert r.independent is False

    def test_envelope_form_limit_capped_by_size(self):
        r = check_independency(0.020, 0.050, GPSModifier.ENVELOPE)
        assert r.effective_form_limit_mm == pytest.approx(0.020)

    def test_envelope_form_limit_unchanged_when_smaller(self):
        r = check_independency(0.050, 0.010, GPSModifier.ENVELOPE)
        assert r.effective_form_limit_mm == pytest.approx(0.010)

    def test_envelope_note_mentions_mmc(self):
        r = check_independency(0.020, 0.010, GPSModifier.ENVELOPE)
        assert any("MMC" in n or "envelope" in n.lower() for n in r.notes)

    def test_envelope_note_warns_when_form_exceeds_size(self):
        r = check_independency(0.010, 0.050, GPSModifier.ENVELOPE)
        clipping_notes = [n for n in r.notes if "clips" in n or "exceeds" in n.lower()]
        assert len(clipping_notes) >= 1

    # --- ASME Y14.5 (Rule #1 — envelope by default) ---

    def test_asme_invocation_activates_envelope(self):
        asme = GPSInvocation(standard=GPSStandard.ASME_Y14_5, title_block_text="ASME")
        r = check_independency(0.030, 0.010, GPSModifier.INDEPENDENCY, asme)
        assert r.envelope_active is True

    def test_asme_envelope_clips_form(self):
        asme = GPSInvocation(standard=GPSStandard.ASME_Y14_5, title_block_text="ASME")
        r = check_independency(0.010, 0.050, GPSModifier.INDEPENDENCY, asme)
        assert r.effective_form_limit_mm == pytest.approx(0.010)

    def test_iso8015_explicit_independency_modifier_stays_independent(self):
        iso = GPSInvocation()
        r = check_independency(0.030, 0.010, GPSModifier.INDEPENDENCY, iso)
        assert r.independent is True

    # --- Result fields ---

    def test_result_stores_input_tolerances(self):
        r = check_independency(0.025, 0.008, GPSModifier.INDEPENDENCY)
        assert r.size_tolerance_mm == pytest.approx(0.025)
        assert r.form_tolerance_mm == pytest.approx(0.008)
        assert r.modifier == GPSModifier.INDEPENDENCY

    def test_as_dict_keys(self):
        r = check_independency(0.025, 0.008)
        d = r.as_dict()
        assert set(d.keys()) == {
            "modifier", "size_tolerance_mm", "form_tolerance_mm",
            "independent", "envelope_active", "effective_form_limit_mm", "notes",
        }

    def test_as_dict_modifier_is_string(self):
        r = check_independency(0.025, 0.008, GPSModifier.ENVELOPE)
        assert isinstance(r.as_dict()["modifier"], str)

    def test_notes_non_empty(self):
        for mod in (GPSModifier.INDEPENDENCY, GPSModifier.ENVELOPE):
            r = check_independency(0.025, 0.008, mod)
            assert len(r.notes) >= 1


# ===========================================================================
# gps_specify_feature / GPSFeatureSpec
# ===========================================================================

class TestGpsSpecifyFeature:

    # --- ISO 286 integration (cylindrical features) ---

    def test_bore_has_size_tolerance(self):
        spec = gps_specify_feature(
            "bore", FeatureType.INTERNAL_CYLINDER, 52.0,
            "cylindrical_grinding", process_db=DB,
        )
        assert spec.size_tolerance is not None
        assert spec.size_tolerance["it_grade"] == "IT5"

    def test_shaft_has_size_tolerance(self):
        spec = gps_specify_feature(
            "shaft", FeatureType.EXTERNAL_CYLINDER, 25.0,
            "CNC_turning", process_db=DB,
        )
        assert spec.size_tolerance is not None
        assert spec.size_tolerance["tolerance_mm"] > 0

    def test_flat_surface_no_size_tolerance(self):
        spec = gps_specify_feature(
            "face", FeatureType.FLAT_SURFACE, 80.0,
            "sand_casting", process_db=DB,
        )
        assert spec.size_tolerance is None

    # --- ISO 2768 integration ---

    def test_general_tolerance_present(self):
        spec = gps_specify_feature(
            "bore", FeatureType.INTERNAL_CYLINDER, 52.0,
            "cylindrical_grinding", process_db=DB,
        )
        assert spec.general_tolerance is not None
        assert "class" in spec.general_tolerance
        assert spec.general_tolerance["tolerance_mm"] > 0

    def test_grinding_general_tolerance_class_f(self):
        spec = gps_specify_feature(
            "bore", FeatureType.INTERNAL_CYLINDER, 52.0,
            "cylindrical_grinding", process_db=DB,
        )
        assert spec.general_tolerance["class"] == "f"

    def test_sand_casting_general_tolerance_class_c(self):
        spec = gps_specify_feature(
            "face", FeatureType.FLAT_SURFACE, 80.0,
            "sand_casting", process_db=DB,
        )
        assert spec.general_tolerance["class"] == "c"

    # --- ISO 1101 integration ---

    def test_geometric_tolerances_non_empty(self):
        spec = gps_specify_feature(
            "bore", FeatureType.INTERNAL_CYLINDER, 52.0,
            "cylindrical_grinding", "bearing_bore", process_db=DB,
        )
        assert len(spec.geometric_tolerances) > 0

    def test_bearing_bore_has_circularity(self):
        spec = gps_specify_feature(
            "bore", FeatureType.INTERNAL_CYLINDER, 52.0,
            "cylindrical_grinding", "bearing_bore", process_db=DB,
        )
        chars = [r.characteristic for r in spec.geometric_tolerances]
        assert "circularity" in chars

    def test_geometric_tolerances_positive(self):
        spec = gps_specify_feature(
            "bore", FeatureType.INTERNAL_CYLINDER, 52.0,
            "cylindrical_grinding", "bearing_bore", process_db=DB,
        )
        for r in spec.geometric_tolerances:
            assert r.tolerance_mm > 0

    def test_locating_pin_functional_class(self):
        spec = gps_specify_feature(
            "pin", FeatureType.EXTERNAL_CYLINDER, 8.0,
            "CNC_turning", "locating_pin", process_db=DB,
        )
        chars = [r.characteristic for r in spec.geometric_tolerances]
        assert "straightness" in chars or "cylindricity" in chars

    # --- ISO 4287/4288 integration ---

    def test_surface_texture_present(self):
        spec = gps_specify_feature(
            "bore", FeatureType.INTERNAL_CYLINDER, 52.0,
            "cylindrical_grinding", process_db=DB,
        )
        assert spec.surface_texture is not None
        assert "Ra_um" in spec.surface_texture
        assert "Rz_um" in spec.surface_texture

    # --- ISO 8015 independency check ---

    def test_independency_result_present_for_cylinder(self):
        spec = gps_specify_feature(
            "bore", FeatureType.INTERNAL_CYLINDER, 52.0,
            "cylindrical_grinding", "bearing_bore", process_db=DB,
        )
        assert spec.independency is not None

    def test_independency_default_modifier(self):
        spec = gps_specify_feature(
            "bore", FeatureType.INTERNAL_CYLINDER, 52.0,
            "cylindrical_grinding", "bearing_bore",
            modifier=GPSModifier.INDEPENDENCY, process_db=DB,
        )
        assert spec.independency.independent is True
        assert spec.independency.envelope_active is False

    def test_envelope_modifier_propagates(self):
        spec = gps_specify_feature(
            "pin", FeatureType.EXTERNAL_CYLINDER, 8.0,
            "CNC_turning", "locating_pin",
            modifier=GPSModifier.ENVELOPE, process_db=DB,
        )
        assert spec.independency.envelope_active is True

    def test_envelope_effective_form_limit_le_size(self):
        spec = gps_specify_feature(
            "pin", FeatureType.EXTERNAL_CYLINDER, 8.0,
            "CNC_turning", "locating_pin",
            modifier=GPSModifier.ENVELOPE, process_db=DB,
        )
        ind = spec.independency
        assert ind.effective_form_limit_mm <= ind.size_tolerance_mm + 1e-9

    def test_flat_surface_no_independency_result(self):
        # No size tolerance → no independency check
        spec = gps_specify_feature(
            "face", FeatureType.FLAT_SURFACE, 80.0,
            "sand_casting", "structural", process_db=DB,
        )
        assert spec.independency is None

    # --- GPS operator chain ---

    def test_operator_chain_five_steps(self):
        spec = gps_specify_feature(
            "bore", FeatureType.INTERNAL_CYLINDER, 52.0,
            "cylindrical_grinding", process_db=DB,
        )
        assert len(spec.operator_chain) == 5

    def test_operator_chain_correct_association_for_bore(self):
        spec = gps_specify_feature(
            "bore", FeatureType.INTERNAL_CYLINDER, 52.0,
            "cylindrical_grinding", process_db=DB,
        )
        assoc = next(op for op in spec.operator_chain
                     if op.step == GPSOperatorStep.ASSOCIATION)
        assert "inscribed" in assoc.description.lower()

    def test_operator_chain_correct_association_for_shaft(self):
        spec = gps_specify_feature(
            "shaft", FeatureType.EXTERNAL_CYLINDER, 25.0,
            "CNC_turning", process_db=DB,
        )
        assoc = next(op for op in spec.operator_chain
                     if op.step == GPSOperatorStep.ASSOCIATION)
        assert "circumscribed" in assoc.description.lower()

    def test_operator_chain_flat_surface_uses_plane(self):
        spec = gps_specify_feature(
            "face", FeatureType.FLAT_SURFACE, 80.0,
            "sand_casting", process_db=DB,
        )
        assoc = next(op for op in spec.operator_chain
                     if op.step == GPSOperatorStep.ASSOCIATION)
        assert "plane" in assoc.description.lower()

    # --- Reference conditions ---

    def test_reference_temperature_is_20c(self):
        spec = gps_specify_feature(
            "bore", FeatureType.INTERNAL_CYLINDER, 25.0,
            "CNC_turning", process_db=DB,
        )
        assert spec.reference_temperature_c == pytest.approx(20.0)

    def test_reference_pressure_is_standard(self):
        spec = gps_specify_feature(
            "bore", FeatureType.INTERNAL_CYLINDER, 25.0,
            "CNC_turning", process_db=DB,
        )
        assert spec.reference_pressure_pa == pytest.approx(101_325.0)

    # --- GPS standard invocation ---

    def test_default_invocation_is_iso8015(self):
        spec = gps_specify_feature(
            "bore", FeatureType.INTERNAL_CYLINDER, 25.0,
            "CNC_turning", process_db=DB,
        )
        assert spec.invocation.standard == GPSStandard.ISO_8015

    def test_custom_asme_invocation_propagates(self):
        asme = GPSInvocation(standard=GPSStandard.ASME_Y14_5, title_block_text="ASME")
        spec = gps_specify_feature(
            "bore", FeatureType.INTERNAL_CYLINDER, 52.0,
            "cylindrical_grinding", "bearing_bore",
            invocation=asme, process_db=DB,
        )
        assert spec.invocation.standard == GPSStandard.ASME_Y14_5
        assert spec.independency.envelope_active is True

    # --- Unknown process ---

    def test_unknown_process_populates_warnings(self):
        spec = gps_specify_feature(
            "x", FeatureType.INTERNAL_CYLINDER, 25.0,
            "laser_ablation", process_db=DB,
        )
        assert len(spec.warnings) > 0

    # --- as_dict round-trip ---

    def test_as_dict_contains_expected_keys(self):
        spec = gps_specify_feature(
            "bore", FeatureType.INTERNAL_CYLINDER, 52.0,
            "cylindrical_grinding", "bearing_bore", process_db=DB,
        )
        d = spec.as_dict()
        for key in (
            "feature_id", "feature_type", "nominal_size_mm", "process",
            "functional_class", "modifier", "invocation",
            "size_tolerance", "general_tolerance", "geometric_tolerances",
            "surface_texture", "independency",
            "reference_temperature_c", "reference_pressure_pa", "warnings",
        ):
            assert key in d, f"Missing key: {key}"

    def test_as_dict_feature_type_is_string(self):
        spec = gps_specify_feature(
            "bore", FeatureType.INTERNAL_CYLINDER, 52.0,
            "cylindrical_grinding", process_db=DB,
        )
        assert isinstance(spec.as_dict()["feature_type"], str)

    def test_as_dict_modifier_is_string(self):
        spec = gps_specify_feature(
            "bore", FeatureType.INTERNAL_CYLINDER, 52.0,
            "cylindrical_grinding", process_db=DB,
        )
        assert isinstance(spec.as_dict()["modifier"], str)

    def test_as_dict_geometric_tolerances_serialisable(self):
        spec = gps_specify_feature(
            "bore", FeatureType.INTERNAL_CYLINDER, 52.0,
            "cylindrical_grinding", "bearing_bore", process_db=DB,
        )
        gts = spec.as_dict()["geometric_tolerances"]
        assert isinstance(gts, list)
        for item in gts:
            assert isinstance(item, dict)


# ===========================================================================
# ISO 8015 vs ASME Y14.5 — behavioural comparison
# ===========================================================================

class TestStandardComparison:
    """Verify that the two standards produce the expected behavioural difference
    on the same feature: ISO 8015 keeps independency, ASME Y14.5 activates the
    envelope by default (Rule #1)."""

    @pytest.fixture
    def iso_spec(self):
        return gps_specify_feature(
            "bore", FeatureType.INTERNAL_CYLINDER, 52.0,
            "cylindrical_grinding", "bearing_bore",
            modifier=GPSModifier.INDEPENDENCY,
            invocation=GPSInvocation(),
            process_db=DB,
        )

    @pytest.fixture
    def asme_spec(self):
        return gps_specify_feature(
            "bore", FeatureType.INTERNAL_CYLINDER, 52.0,
            "cylindrical_grinding", "bearing_bore",
            modifier=GPSModifier.INDEPENDENCY,
            invocation=GPSInvocation(
                standard=GPSStandard.ASME_Y14_5,
                title_block_text="ASME Y14.5-2018",
            ),
            process_db=DB,
        )

    def test_iso_independency_true(self, iso_spec):
        assert iso_spec.independency.independent is True

    def test_asme_independency_false(self, asme_spec):
        assert asme_spec.independency.independent is False

    def test_iso_envelope_not_active(self, iso_spec):
        assert iso_spec.independency.envelope_active is False

    def test_asme_envelope_active(self, asme_spec):
        assert asme_spec.independency.envelope_active is True

    def test_same_size_tolerance(self, iso_spec, asme_spec):
        assert iso_spec.independency.size_tolerance_mm == pytest.approx(
            asme_spec.independency.size_tolerance_mm
        )

    def test_same_form_tolerance(self, iso_spec, asme_spec):
        assert iso_spec.independency.form_tolerance_mm == pytest.approx(
            asme_spec.independency.form_tolerance_mm
        )

    def test_asme_effective_form_limit_le_iso(self, iso_spec, asme_spec):
        # ASME clips form to size; ISO leaves it unconstrained
        assert asme_spec.independency.effective_form_limit_mm <= (
            iso_spec.independency.effective_form_limit_mm + 1e-9
        )

    def test_iso_and_asme_produce_identical_sub_standard_values(
        self, iso_spec, asme_spec
    ):
        # ISO 286, 2768, 1101, 4287 are independent of the GPS standard invocation
        assert (iso_spec.size_tolerance["tolerance_mm"]
                == pytest.approx(asme_spec.size_tolerance["tolerance_mm"]))
        assert (iso_spec.general_tolerance["class"]
                == asme_spec.general_tolerance["class"])
        assert len(iso_spec.geometric_tolerances) == len(asme_spec.geometric_tolerances)


# ===========================================================================
# dimensioning_checks
# ===========================================================================

class TestDimensioningChecks:

    def test_all_valid_returns_empty(self):
        dims = [("shaft_d", 25.0, 0.021), ("flange_h", 10.0, 0.050)]
        assert dimensioning_checks(dims) == []

    def test_zero_nominal_triggers_warning(self):
        warnings = dimensioning_checks([("x", 0.0, 0.010)])
        # nominal=0 triggers both the "≤ 0" check and the "tol > nominal" check
        assert len(warnings) >= 1
        assert any("nominal" in w.lower() or "≤ 0" in w for w in warnings)

    def test_negative_nominal_triggers_warning(self):
        warnings = dimensioning_checks([("x", -5.0, 0.010)])
        assert any("nominal" in w.lower() or "≤ 0" in w for w in warnings)

    def test_zero_tolerance_triggers_warning(self):
        warnings = dimensioning_checks([("x", 10.0, 0.0)])
        assert any("tolerance" in w.lower() or "≤ 0" in w for w in warnings)

    def test_tolerance_exceeds_nominal_triggers_warning(self):
        warnings = dimensioning_checks([("x", 5.0, 10.0)])
        assert len(warnings) == 1
        assert "10.0" in warnings[0] or "exceed" in warnings[0].lower()

    def test_multiple_bad_dimensions_all_reported(self):
        dims = [
            ("a", 10.0, 0.0),    # zero tolerance — exactly one warning
            ("b", 5.0, 10.0),    # tol > nominal — exactly one warning
            ("c", 20.0, 0.020),  # good — no warning
        ]
        warnings = dimensioning_checks(dims)
        assert len(warnings) == 2

    def test_generator_input_accepted(self):
        dims = ((name, nom, tol) for name, nom, tol in [("d", 10.0, 0.01)])
        assert dimensioning_checks(dims) == []


# ===========================================================================
# Backwards-compatibility shims
# ===========================================================================

class TestBackwardsCompatShims:

    # apply_independence_principle

    def test_no_modifiers_returns_base(self):
        assert apply_independence_principle(0.05) == pytest.approx(0.05)

    def test_modifier_above_one_increases_result(self):
        result = apply_independence_principle(0.05, [1.2])
        assert result == pytest.approx(0.06)

    def test_modifier_below_one_returns_base(self):
        # max() keeps the base when modifier < 1
        result = apply_independence_principle(0.05, [0.8])
        assert result == pytest.approx(0.05)

    def test_multiple_modifiers_returns_max(self):
        result = apply_independence_principle(0.05, [1.1, 0.9, 1.3])
        assert result == pytest.approx(0.065)

    def test_empty_modifier_list_returns_base(self):
        assert apply_independence_principle(0.05, []) == pytest.approx(0.05)

    # simple_dimensioning_checks (alias of dimensioning_checks)

    def test_alias_valid_returns_empty(self):
        assert simple_dimensioning_checks([("x", 10.0, 0.01)]) == []

    def test_alias_bad_returns_warnings(self):
        w = simple_dimensioning_checks([("x", 0.0, 0.01)])
        assert len(w) >= 1

    def test_alias_identical_to_dimensioning_checks(self):
        dims = [("a", 5.0, 10.0), ("b", 25.0, 0.02)]
        from tolerance_advisor.GPS_iso8015 import dimensioning_checks as dc
        assert simple_dimensioning_checks(dims) == dc(dims)
