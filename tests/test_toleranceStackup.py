"""Tests for tolerance_advisor.toleranceStackup.

Unit tests cover every public function and class without requiring
pythonocc-core or a STEP file.  Synthetic SolidDimensions / MinimalDimensionSet
stubs are built from the pure-Python dataclasses in shape_dimension.py and
dimension_minimal.py (both OCC-free).
"""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tolerance_advisor.toleranceStackup import (
    DimensionContributor,
    StackUpChain,
    StackUpResult,
    assign_iso2768_tolerance,
    assign_process_tolerance,
    compute_stack_up,
    contributors_from_mds,
    contributors_from_solid,
    print_stack_up_report,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _simple_chain(
    n: int = 3,
    nominal: float = 10.0,
    tol: float = 0.1,
    sensitivity: float = 1.0,
    spec_min: float = None,
    spec_max: float = None,
) -> StackUpChain:
    """Return a chain of *n* equal contributors."""
    return StackUpChain(
        name="test_chain",
        spec_min=spec_min,
        spec_max=spec_max,
        contributors=[
            DimensionContributor(f"dim_{i}", nominal, tol, tol, sensitivity)
            for i in range(n)
        ],
    )


def _result(n=3, nominal=10.0, tol=0.1, sensitivity=1.0,
            spec_min=None, spec_max=None) -> StackUpResult:
    return compute_stack_up(
        _simple_chain(n, nominal, tol, sensitivity, spec_min, spec_max)
    )


# ---------------------------------------------------------------------------
# TestAssignISO2768Tolerance
# ---------------------------------------------------------------------------

class TestAssignISO2768Tolerance(unittest.TestCase):

    def test_medium_class_10mm(self):
        # ISO 2768-1:1989 Table 1: 6 < dim ≤ 30, class m → ±0.20
        self.assertAlmostEqual(assign_iso2768_tolerance(10.0, "m"), 0.20)

    def test_fine_class_50mm(self):
        # 30 < dim ≤ 120, class f → ±0.15
        self.assertAlmostEqual(assign_iso2768_tolerance(50.0, "f"), 0.15)

    def test_coarse_class_3mm(self):
        # 0.5 < dim ≤ 3, class c → ±0.20
        self.assertAlmostEqual(assign_iso2768_tolerance(3.0, "c"), 0.20)

    def test_very_coarse_class_200mm(self):
        # 120 < dim ≤ 400, class v → ±2.50
        self.assertAlmostEqual(assign_iso2768_tolerance(200.0, "v"), 2.50)

    def test_all_classes_return_positive(self):
        for cls in ("f", "m", "c", "v"):
            for nom in (2.0, 10.0, 50.0, 200.0, 800.0, 1500.0):
                try:
                    t = assign_iso2768_tolerance(nom, cls)
                    self.assertGreater(t, 0.0)
                except ValueError:
                    pass  # some combinations are undefined (v at <6 mm)

    def test_fine_is_tighter_than_medium(self):
        for nom in (5.0, 25.0, 100.0, 300.0):
            tf = assign_iso2768_tolerance(nom, "f")
            tm = assign_iso2768_tolerance(nom, "m")
            self.assertLessEqual(tf, tm)

    def test_medium_is_tighter_than_coarse(self):
        for nom in (5.0, 25.0, 100.0, 300.0):
            tm = assign_iso2768_tolerance(nom, "m")
            tc = assign_iso2768_tolerance(nom, "c")
            self.assertLessEqual(tm, tc)

    def test_class_case_insensitive(self):
        self.assertAlmostEqual(
            assign_iso2768_tolerance(10.0, "M"),
            assign_iso2768_tolerance(10.0, "m"),
        )

    def test_very_coarse_undefined_for_tiny_dim_raises(self):
        with self.assertRaises(ValueError):
            assign_iso2768_tolerance(2.0, "v")

    def test_unknown_class_raises(self):
        with self.assertRaises(ValueError):
            assign_iso2768_tolerance(10.0, "x")

    def test_exceeds_2000mm_raises(self):
        with self.assertRaises(ValueError):
            assign_iso2768_tolerance(2001.0, "m")

    def test_tolerance_increases_with_nominal(self):
        # Within the same class, larger dimensions have larger tolerances.
        tols_m = [assign_iso2768_tolerance(n, "m") for n in (2.0, 5.0, 20.0, 80.0, 200.0)]
        self.assertEqual(tols_m, sorted(tols_m))


# ---------------------------------------------------------------------------
# TestAssignProcessTolerance
# ---------------------------------------------------------------------------

class TestAssignProcessTolerance(unittest.TestCase):

    def test_cnc_milling_25mm(self):
        # Built-in table: (0,25] → 0.025
        self.assertAlmostEqual(assign_process_tolerance(25.0, "CNC_milling"), 0.025)

    def test_cnc_turning_25mm(self):
        self.assertAlmostEqual(assign_process_tolerance(25.0, "CNC_turning"), 0.013)

    def test_sand_casting_is_larger_than_cnc(self):
        self.assertGreater(
            assign_process_tolerance(30.0, "sand_casting"),
            assign_process_tolerance(30.0, "CNC_milling"),
        )

    def test_unknown_process_falls_back_without_raising(self):
        # Unknown process should not raise — falls back to ISO 2768 m
        t = assign_process_tolerance(20.0, "unknown_process_XYZ")
        self.assertGreater(t, 0.0)

    def test_all_builtin_processes_return_positive(self):
        processes = [
            "CNC_milling", "CNC_turning", "cylindrical_grinding",
            "injection_molding", "injection_moulding", "sheet_metal_bending",
            "die_casting", "FDM_3D_print", "SLS_3D_print",
            "sand_casting", "investment_casting",
        ]
        for proc in processes:
            t = assign_process_tolerance(30.0, proc)
            self.assertGreater(t, 0.0, msg=f"Process {proc!r} returned non-positive tol")


# ---------------------------------------------------------------------------
# TestDimensionContributor
# ---------------------------------------------------------------------------

class TestDimensionContributor(unittest.TestCase):

    def _make(self, nominal=10.0, tol_plus=0.1, tol_minus=0.05,
              sensitivity=1.0) -> DimensionContributor:
        return DimensionContributor(
            "test", nominal, tol_plus, tol_minus, sensitivity
        )

    def test_tol_sym_is_average(self):
        c = self._make(tol_plus=0.10, tol_minus=0.06)
        self.assertAlmostEqual(c.tol_sym, 0.08)

    def test_tol_sym_symmetric(self):
        c = self._make(tol_plus=0.10, tol_minus=0.10)
        self.assertAlmostEqual(c.tol_sym, 0.10)

    def test_effective_nominal_positive(self):
        c = self._make(nominal=10.0, sensitivity=1.0)
        self.assertAlmostEqual(c.effective_nominal, 10.0)

    def test_effective_nominal_negative_sensitivity(self):
        c = self._make(nominal=10.0, sensitivity=-1.0)
        self.assertAlmostEqual(c.effective_nominal, -10.0)

    def test_effective_nominal_fractional_sensitivity(self):
        c = self._make(nominal=10.0, sensitivity=0.5)
        self.assertAlmostEqual(c.effective_nominal, 5.0)

    def test_default_sensitivity_is_one(self):
        c = DimensionContributor("t", 5.0, 0.1, 0.1)
        self.assertAlmostEqual(c.sensitivity, 1.0)

    def test_default_distribution_is_normal(self):
        c = DimensionContributor("t", 5.0, 0.1, 0.1)
        self.assertEqual(c.distribution, "normal")


# ---------------------------------------------------------------------------
# TestStackUpChain
# ---------------------------------------------------------------------------

class TestStackUpChain(unittest.TestCase):

    def test_nominal_gap_sums_effective_nominals(self):
        chain = _simple_chain(n=4, nominal=10.0, sensitivity=1.0)
        self.assertAlmostEqual(chain.nominal_gap, 40.0)

    def test_nominal_gap_with_mixed_sensitivities(self):
        chain = StackUpChain("t", contributors=[
            DimensionContributor("a", 10.0, 0.1, 0.1, sensitivity=+1.0),
            DimensionContributor("b", 10.0, 0.1, 0.1, sensitivity=-1.0),
        ])
        self.assertAlmostEqual(chain.nominal_gap, 0.0)

    def test_add_returns_chain_for_chaining(self):
        chain = StackUpChain("t")
        returned = chain.add(DimensionContributor("a", 5.0, 0.1, 0.1))
        self.assertIs(returned, chain)

    def test_add_appends_contributor(self):
        chain = StackUpChain("t")
        chain.add(DimensionContributor("a", 5.0, 0.1, 0.1))
        chain.add(DimensionContributor("b", 3.0, 0.1, 0.1))
        self.assertEqual(len(chain.contributors), 2)

    def test_empty_chain_nominal_gap_zero(self):
        self.assertAlmostEqual(StackUpChain("empty").nominal_gap, 0.0)

    def test_spec_limits_stored(self):
        chain = StackUpChain("t", spec_min=-0.5, spec_max=0.5)
        self.assertEqual(chain.spec_min, -0.5)
        self.assertEqual(chain.spec_max, 0.5)


# ---------------------------------------------------------------------------
# TestComputeStackUp — core solver
# ---------------------------------------------------------------------------

class TestComputeStackUp(unittest.TestCase):

    # ── basic invariants ──────────────────────────────────────────────────────

    def test_nominal_gap_matches_chain(self):
        chain = _simple_chain(3, nominal=10.0)
        result = compute_stack_up(chain)
        self.assertAlmostEqual(result.nominal_gap, chain.nominal_gap)

    def test_wc_range_contains_nominal(self):
        result = _result(3, nominal=10.0, tol=0.5)
        self.assertLessEqual(result.wc_min, result.nominal_gap)
        self.assertGreaterEqual(result.wc_max, result.nominal_gap)

    def test_rss_range_contains_nominal(self):
        result = _result(3, nominal=10.0, tol=0.5)
        self.assertLessEqual(result.rss_min, result.nominal_gap)
        self.assertGreaterEqual(result.rss_max, result.nominal_gap)

    def test_wc_range_wider_than_rss(self):
        # WC (linear sum) ≥ RSS (3σ) when n ≥ 10 contributors.
        # For n contributors each with tol T:
        #   WC_half  = n * T
        #   RSS_half = 3 * sqrt(n) * T
        # WC ≥ RSS ↔ n ≥ 9.  Use 20 contributors for a clear margin.
        result = _result(20, nominal=10.0, tol=0.2)
        wc_spread  = result.wc_max  - result.wc_min
        rss_spread = result.rss_max - result.rss_min
        self.assertGreaterEqual(wc_spread, rss_spread)

    def test_wc_symmetric_for_symmetric_tolerances(self):
        result = _result(3, nominal=10.0, tol=0.1)
        half_wc = (result.wc_max - result.wc_min) / 2.0
        self.assertAlmostEqual(result.wc_max,  result.nominal_gap + half_wc)
        self.assertAlmostEqual(result.wc_min,  result.nominal_gap - half_wc)

    def test_wc_tol_equals_sum_of_contributor_tols(self):
        # 3 contributors each ±0.1 → WC ± 0.3
        result = _result(3, nominal=5.0, tol=0.1)
        expected_half = 3 * 0.1
        self.assertAlmostEqual(result.wc_max - result.nominal_gap, expected_half)

    def test_rss_tol_equals_sqrt_of_sum_of_squares(self):
        # n contributors each ±tol, sensitivity=1.
        # rss_tol = sqrt(sum(tol^2)) = sqrt(n) * tol
        # rss_max - nominal = 3 * rss_tol = 3 * sqrt(n) * tol
        tol = 0.1
        n   = 4
        result = _result(n, nominal=5.0, tol=tol)
        expected_rss_half = 3.0 * math.sqrt(n * tol ** 2)
        self.assertAlmostEqual(
            result.rss_max - result.nominal_gap, expected_rss_half, places=6
        )

    # ── Monte Carlo ───────────────────────────────────────────────────────────

    def test_mc_samples_shape(self):
        result = compute_stack_up(_simple_chain(), n_mc=500)
        self.assertEqual(result.mc_samples.shape, (500,))

    def test_mc_mean_close_to_nominal(self):
        # With 100k samples and symmetric normal distributions, mean ≈ nominal.
        result = _result(3, nominal=10.0, tol=0.2)
        self.assertAlmostEqual(result.mc_mean, result.nominal_gap, delta=0.01)

    def test_mc_std_positive(self):
        result = _result(3, nominal=10.0, tol=0.2)
        self.assertGreater(result.mc_std, 0.0)

    def test_mc_std_increases_with_tol(self):
        r_tight = _result(3, nominal=10.0, tol=0.05)
        r_loose = _result(3, nominal=10.0, tol=0.50)
        self.assertLess(r_tight.mc_std, r_loose.mc_std)

    def test_mc_std_increases_with_more_contributors(self):
        r_few  = _result(n=2, nominal=5.0, tol=0.1)
        r_many = _result(n=8, nominal=5.0, tol=0.1)
        self.assertLess(r_few.mc_std, r_many.mc_std)

    def test_mc_reproducible_with_same_seed(self):
        chain = _simple_chain(4, nominal=10.0, tol=0.15)
        r1 = compute_stack_up(chain, seed=7)
        r2 = compute_stack_up(chain, seed=7)
        self.assertAlmostEqual(r1.mc_mean, r2.mc_mean)
        self.assertAlmostEqual(r1.mc_std,  r2.mc_std)

    def test_mc_different_seeds_give_different_results(self):
        chain = _simple_chain(3, nominal=10.0, tol=0.1)
        r1 = compute_stack_up(chain, seed=1)
        r2 = compute_stack_up(chain, seed=2)
        # Means will differ (though both are close to nominal)
        self.assertNotEqual(r1.mc_mean, r2.mc_mean)

    def test_uniform_distribution_wider_than_normal(self):
        # Uniform(±t) samples spread over ±t; normal clips to 3σ = t.
        # So uniform should have larger std for the same half-range.
        def _chain_with_dist(dist):
            return StackUpChain("t", contributors=[
                DimensionContributor("a", 10.0, 0.3, 0.3, distribution=dist),
                DimensionContributor("b",  5.0, 0.3, 0.3, distribution=dist),
            ])
        r_norm = compute_stack_up(_chain_with_dist("normal"))
        r_unif = compute_stack_up(_chain_with_dist("uniform"))
        self.assertGreater(r_unif.mc_std, r_norm.mc_std)

    # ── yield / spec ──────────────────────────────────────────────────────────

    def test_yield_none_when_no_spec(self):
        result = _result()
        self.assertIsNone(result.mc_yield_pct)

    def test_yield_near_100_when_spec_covers_wc_range(self):
        # 3 contributors × nominal 10.0 → gap = 30.0; WC_half = 3 × 0.1 = 0.3
        # Spec [28.0, 32.0] comfortably contains the WC range [29.7, 30.3].
        result = compute_stack_up(
            _simple_chain(3, nominal=10.0, tol=0.1,
                          spec_min=28.0, spec_max=32.0)
        )
        self.assertGreater(result.mc_yield_pct, 99.0)

    def test_yield_near_0_when_spec_far_outside(self):
        result = compute_stack_up(
            _simple_chain(3, nominal=10.0, tol=0.1,
                          spec_min=100.0, spec_max=200.0)
        )
        self.assertAlmostEqual(result.mc_yield_pct, 0.0, delta=0.1)

    def test_yield_between_0_and_100(self):
        # 3 contributors × nominal 10.0 → gap = 30.0; WC_half = 3 × 0.5 = 1.5
        # Spec [29.5, 30.5] sits inside the WC range → partial yield.
        result = compute_stack_up(
            _simple_chain(3, nominal=10.0, tol=0.5,
                          spec_min=29.5, spec_max=30.5)
        )
        self.assertGreater(result.mc_yield_pct, 0.0)
        self.assertLess(result.mc_yield_pct, 100.0)

    # ── spec pass/fail flags ──────────────────────────────────────────────────

    def test_wc_passes_spec_none_when_no_spec(self):
        self.assertIsNone(_result().wc_passes_spec)

    def test_rss_passes_spec_none_when_no_spec(self):
        self.assertIsNone(_result().rss_passes_spec)

    def test_wc_passes_when_spec_contains_wc_range(self):
        # 2 contributors × nominal 5.0 → gap = 10.0; WC_half = 2 × 0.05 = 0.10
        # Spec [9.5, 10.5] contains the WC range [9.9, 10.1].
        result = compute_stack_up(
            _simple_chain(2, nominal=5.0, tol=0.05,
                          spec_min=9.5, spec_max=10.5)
        )
        self.assertTrue(result.wc_passes_spec)

    def test_wc_fails_when_spec_inside_wc_range(self):
        # WC range is [5.0 − 0.6, 5.0 + 0.6] = [4.4, 5.6]
        # Spec [4.6, 5.4] does not contain WC range.
        result = compute_stack_up(
            _simple_chain(3, nominal=5.0, tol=0.2,
                          spec_min=4.6, spec_max=5.4)
        )
        self.assertFalse(result.wc_passes_spec)

    def test_rss_can_pass_when_wc_fails(self):
        # n=16 contributors, nominal=5.0, tol=0.1 → gap = 80.0
        # WC_half  = 16 × 0.1 = 1.6
        # RSS_half = 3 × sqrt(16 × 0.01) = 3 × 0.4 = 1.2
        # Spec [78.7, 81.3] (±1.3 around gap 80.0):
        #   WC  range [78.4, 81.6] not contained → WC fails
        #   RSS range [78.8, 81.2] contained → RSS passes
        result = compute_stack_up(
            _simple_chain(16, nominal=5.0, tol=0.1,
                          spec_min=78.7, spec_max=81.3)
        )
        self.assertFalse(result.wc_passes_spec)
        self.assertTrue(result.rss_passes_spec)

    # ── sensitivity ranking ───────────────────────────────────────────────────

    def test_sensitivity_ranking_sums_to_100(self):
        result = _result(4, nominal=5.0, tol=0.1)
        total = sum(pct for _, pct in result.sensitivity_ranking)
        self.assertAlmostEqual(total, 100.0, places=6)

    def test_sensitivity_ranking_sorted_descending(self):
        chain = StackUpChain("t", contributors=[
            DimensionContributor("large", 10.0, 0.5, 0.5),
            DimensionContributor("small", 10.0, 0.1, 0.1),
            DimensionContributor("medium", 10.0, 0.3, 0.3),
        ])
        result = compute_stack_up(chain)
        pcts = [p for _, p in result.sensitivity_ranking]
        self.assertEqual(pcts, sorted(pcts, reverse=True))

    def test_largest_tol_is_top_contributor(self):
        chain = StackUpChain("t", contributors=[
            DimensionContributor("small",  10.0, 0.05, 0.05),
            DimensionContributor("large",  10.0, 0.80, 0.80),
            DimensionContributor("medium", 10.0, 0.20, 0.20),
        ])
        result = compute_stack_up(chain)
        top_name = result.sensitivity_ranking[0][0]
        self.assertEqual(top_name, "large")

    def test_sensitivity_scales_contribution(self):
        # Two identical contributors, one with double sensitivity:
        # it should have 4× the variance (variance ∝ sens²).
        chain = StackUpChain("t", contributors=[
            DimensionContributor("s1", 5.0, 0.1, 0.1, sensitivity=1.0),
            DimensionContributor("s2", 5.0, 0.1, 0.1, sensitivity=2.0),
        ])
        result = compute_stack_up(chain)
        # s2 contributes 4/(1+4) = 80%; s1 = 20%
        ranking = {n: p for n, p in result.sensitivity_ranking}
        self.assertAlmostEqual(ranking["s2"] / ranking["s1"], 4.0, places=3)

    # ── chain_name / contributors copy ───────────────────────────────────────

    def test_chain_name_copied(self):
        chain = StackUpChain("my_gap", contributors=[
            DimensionContributor("a", 5.0, 0.1, 0.1),
        ])
        result = compute_stack_up(chain)
        self.assertEqual(result.chain_name, "my_gap")

    def test_contributors_list_is_copy(self):
        chain = _simple_chain(3)
        result = compute_stack_up(chain)
        self.assertEqual(len(result.contributors), 3)
        # Modifying the result list does not affect the chain
        result.contributors.clear()
        self.assertEqual(len(chain.contributors), 3)

    # ── edge cases ────────────────────────────────────────────────────────────

    def test_empty_chain_raises(self):
        with self.assertRaises(ValueError):
            compute_stack_up(StackUpChain("empty"))

    def test_single_contributor(self):
        chain = StackUpChain("t", contributors=[
            DimensionContributor("only", 10.0, 0.2, 0.2)
        ])
        result = compute_stack_up(chain)
        self.assertAlmostEqual(result.nominal_gap, 10.0)
        self.assertAlmostEqual(result.wc_min, 9.8)
        self.assertAlmostEqual(result.wc_max, 10.2)

    def test_zero_tolerance_contributor(self):
        chain = StackUpChain("t", contributors=[
            DimensionContributor("exact", 5.0, 0.0, 0.0),
            DimensionContributor("normal", 5.0, 0.1, 0.1),
        ])
        result = compute_stack_up(chain)
        self.assertAlmostEqual(result.nominal_gap, 10.0)
        # WC spread should equal the non-zero tol only
        self.assertAlmostEqual(result.wc_max - result.wc_min, 0.2)

    def test_asymmetric_tolerance_wc_uses_max(self):
        # tol_plus=0.30, tol_minus=0.05 → WC uses max(0.30, 0.05) = 0.30
        chain = StackUpChain("t", contributors=[
            DimensionContributor("asym", 10.0, 0.30, 0.05),
        ])
        result = compute_stack_up(chain)
        self.assertAlmostEqual(result.wc_max - result.nominal_gap, 0.30)
        self.assertAlmostEqual(result.nominal_gap - result.wc_min, 0.30)

    def test_negative_sensitivity_flips_wc_sign(self):
        chain = StackUpChain("t", contributors=[
            DimensionContributor("neg", 10.0, 0.1, 0.1, sensitivity=-1.0),
        ])
        result = compute_stack_up(chain)
        self.assertAlmostEqual(result.nominal_gap, -10.0)
        self.assertAlmostEqual(result.wc_min, -10.1)
        self.assertAlmostEqual(result.wc_max, -9.9)

    def test_mixed_sensitivities_cancel_nominal(self):
        chain = StackUpChain("t", contributors=[
            DimensionContributor("pos", 10.0, 0.1, 0.1, sensitivity=+1.0),
            DimensionContributor("neg", 10.0, 0.1, 0.1, sensitivity=-1.0),
        ])
        result = compute_stack_up(chain)
        self.assertAlmostEqual(result.nominal_gap, 0.0, places=10)


# ---------------------------------------------------------------------------
# TestContributorsFromSolid
# ---------------------------------------------------------------------------

class TestContributorsFromSolid(unittest.TestCase):
    """contributors_from_solid with synthetic SolidDimensions — no OCC needed."""

    def _box_solid(self, solid_id=0, L=100.0, W=50.0, H=30.0):
        from post_process.shape_dimension import SolidDimensions, PlaneGroup, WallThickness
        return SolidDimensions(
            solid_id=solid_id,
            bounding_box=(0.0, 0.0, 0.0, L, W, H),
            length=L, width=W, height=H,
            cylinders=[],
            plane_groups=[
                PlaneGroup(
                    normal=(1.0, 0.0, 0.0),
                    face_ids=[0, 1],
                    positions=[0.0, L],
                    total_area=W * H * 2,
                    span=L,
                ),
            ],
            wall_thicknesses=[
                WallThickness(normal=(1.0, 0.0, 0.0), thickness_mm=8.0, face_ids=(0, 1)),
            ],
        )

    def _cyl_solid(self, solid_id=0, r=10.0, h=40.0):
        from post_process.shape_dimension import (
            SolidDimensions, CylindricalFeature, PlaneGroup, WallThickness,
        )
        cyl = CylindricalFeature(
            face_id=0,
            center=(0.0, 0.0, h / 2),
            radius_est=r,
            height_est=h,
            area=2 * math.pi * r * h,
            bounding_box=(-r, -r, 0.0, r, r, h),
        )
        return SolidDimensions(
            solid_id=solid_id,
            bounding_box=(-r, -r, 0.0, r, r, h),
            length=h, width=2 * r, height=2 * r,
            cylinders=[cyl],
            plane_groups=[],
            wall_thicknesses=[],
        )

    def test_box_has_three_bbox_contributors(self):
        cs = contributors_from_solid(self._box_solid(), include_walls=False)
        kinds = {c.name.split("_")[-1] for c in cs}
        self.assertIn("length", kinds)
        self.assertIn("width", kinds)
        self.assertIn("height", kinds)

    def test_total_count_box_with_walls(self):
        # 3 bbox + 1 wall = 4
        cs = contributors_from_solid(self._box_solid(), include_walls=True)
        self.assertEqual(len(cs), 4)

    def test_wall_contributor_nominal_correct(self):
        cs = contributors_from_solid(self._box_solid(), include_walls=True)
        wall_cs = [c for c in cs if "wall" in c.name]
        self.assertEqual(len(wall_cs), 1)
        self.assertAlmostEqual(wall_cs[0].nominal, 8.0)

    def test_cylinders_included(self):
        cs = contributors_from_solid(self._cyl_solid(), include_cylinders=True,
                                     include_walls=False)
        cyl_cs = [c for c in cs if "cyl" in c.name]
        self.assertGreater(len(cyl_cs), 0)

    def test_cylinders_excluded(self):
        cs = contributors_from_solid(self._cyl_solid(), include_cylinders=False,
                                     include_walls=False)
        cyl_cs = [c for c in cs if "cyl" in c.name]
        self.assertEqual(len(cyl_cs), 0)

    def test_all_tolerances_positive(self):
        cs = contributors_from_solid(self._box_solid(), include_walls=True)
        for c in cs:
            self.assertGreater(c.tol_plus, 0.0)
            self.assertGreater(c.tol_minus, 0.0)

    def test_nominal_values_match_solid_dims(self):
        sd = self._box_solid(L=120.0, W=60.0, H=40.0)
        cs = contributors_from_solid(sd, include_walls=False)
        nominals = sorted(c.nominal for c in cs)
        self.assertAlmostEqual(nominals[-1], 120.0)
        self.assertAlmostEqual(nominals[-2], 60.0)
        self.assertAlmostEqual(nominals[-3], 40.0)

    def test_solid_id_in_contributor_name(self):
        cs = contributors_from_solid(self._box_solid(solid_id=7),
                                     include_walls=False)
        for c in cs:
            self.assertIn("7", c.name)

    def test_iso_class_override(self):
        # Force ISO 2768 fine — tolerances should match the standard table.
        cs_f = contributors_from_solid(self._box_solid(L=100.0),
                                       iso_class="f", include_walls=False)
        cs_v = contributors_from_solid(self._box_solid(L=100.0),
                                       iso_class="v", include_walls=False)
        # length = 100 mm: f → ±0.15, v → ±1.50
        len_f = next(c for c in cs_f if "length" in c.name)
        len_v = next(c for c in cs_v if "length" in c.name)
        self.assertLess(len_f.tol_sym, len_v.tol_sym)

    def test_result_can_be_used_in_chain(self):
        cs = contributors_from_solid(self._box_solid())
        chain = StackUpChain("from_solid", contributors=cs)
        result = compute_stack_up(chain)
        self.assertGreater(result.nominal_gap, 0.0)


# ---------------------------------------------------------------------------
# TestContributorsFromMds
# ---------------------------------------------------------------------------

class TestContributorsFromMds(unittest.TestCase):

    def _make_mds(self):
        from post_process.dimension_minimal import DimensionEntry, MinimalDimensionSet
        return MinimalDimensionSet(
            solid_id=0,
            process="CNC_milling",
            it_grade="IT8",
            process_class="medium",
            general_tolerance_note="ISO 2768-mK",
            dimensions=[
                DimensionEntry("length",         80.0, 0.054, "IT8", "Overall length", 0, []),
                DimensionEntry("width",          40.0, 0.039, "IT8", "Overall width",  0, []),
                DimensionEntry("height",         15.0, 0.027, "IT8", "Overall height", 0, []),
                DimensionEntry("diameter",       12.0, 0.018, "IT8", "Bore Ø",         0, [1]),
                DimensionEntry("wall_thickness",  6.0, 0.015, "IT8", "Pocket wall",    0, [2, 3]),
            ],
        )

    def test_contributor_count_matches_dimension_count(self):
        mds = self._make_mds()
        cs = contributors_from_mds(mds)
        self.assertEqual(len(cs), len(mds.dimensions))

    def test_tolerances_preserved(self):
        mds = self._make_mds()
        cs = contributors_from_mds(mds)
        for c, dim in zip(cs, mds.dimensions):
            self.assertAlmostEqual(c.tol_plus,  dim.tolerance_mm)
            self.assertAlmostEqual(c.tol_minus, dim.tolerance_mm)

    def test_nominals_preserved(self):
        mds = self._make_mds()
        cs = contributors_from_mds(mds)
        for c, dim in zip(cs, mds.dimensions):
            self.assertAlmostEqual(c.nominal, dim.nominal_mm)

    def test_default_sensitivity_one(self):
        cs = contributors_from_mds(self._make_mds())
        for c in cs:
            self.assertAlmostEqual(c.sensitivity, 1.0)

    def test_sensitivity_override(self):
        cs = contributors_from_mds(self._make_mds(), sensitivity=-1.0)
        for c in cs:
            self.assertAlmostEqual(c.sensitivity, -1.0)

    def test_contributor_names_contain_kind_and_nominal(self):
        mds = self._make_mds()
        cs  = contributors_from_mds(mds)
        for c, dim in zip(cs, mds.dimensions):
            self.assertIn(dim.kind, c.name)

    def test_can_build_chain_and_compute(self):
        chain = StackUpChain("from_mds", contributors=contributors_from_mds(self._make_mds()))
        result = compute_stack_up(chain)
        self.assertGreater(result.nominal_gap, 0.0)


# ---------------------------------------------------------------------------
# TestStackUpResult — convenience properties
# ---------------------------------------------------------------------------

class TestStackUpResult(unittest.TestCase):

    def test_wc_passes_spec_true(self):
        # 3 contributors × 10.0 → gap = 30.0; WC_half = 3 × 0.1 = 0.3
        # Spec [29.0, 31.0] contains WC range [29.7, 30.3] → pass
        result = compute_stack_up(
            _simple_chain(3, nominal=10.0, tol=0.1, spec_min=29.0, spec_max=31.0)
        )
        self.assertTrue(result.wc_passes_spec)

    def test_wc_passes_spec_false(self):
        # Spec [30.0, 31.0] does not contain WC min 29.7 → fail
        result = compute_stack_up(
            _simple_chain(3, nominal=10.0, tol=0.1, spec_min=30.0, spec_max=31.0)
        )
        self.assertFalse(result.wc_passes_spec)

    def test_rss_passes_spec_true(self):
        # 2 contributors × 5.0 → gap = 10.0; RSS_half = 3 × sqrt(2 × 0.0025) ≈ 0.212
        # Spec [9.5, 10.5] comfortably contains the RSS range → pass
        result = compute_stack_up(
            _simple_chain(2, nominal=5.0, tol=0.05, spec_min=9.5, spec_max=10.5)
        )
        self.assertTrue(result.rss_passes_spec)

    def test_both_none_without_spec(self):
        result = _result()
        self.assertIsNone(result.wc_passes_spec)
        self.assertIsNone(result.rss_passes_spec)

    def test_spec_copied_into_result(self):
        result = compute_stack_up(
            _simple_chain(2, nominal=5.0, tol=0.1, spec_min=9.0, spec_max=11.0)
        )
        self.assertEqual(result.spec_min, 9.0)
        self.assertEqual(result.spec_max, 11.0)


# ---------------------------------------------------------------------------
# TestPrintStackUpReport — smoke test (just verify it doesn't raise)
# ---------------------------------------------------------------------------

class TestPrintStackUpReport(unittest.TestCase):

    def test_runs_without_error(self):
        result = _result(3, nominal=10.0, tol=0.1, spec_min=29.5, spec_max=30.5)
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            print_stack_up_report(result)
        output = buf.getvalue()
        self.assertIn("TOLERANCE STACK-UP", output)
        self.assertIn("Worst-Case", output)
        self.assertIn("RSS", output)
        self.assertIn("MC", output)
        self.assertIn("Sensitivity", output)

    def test_output_contains_chain_name(self):
        chain = StackUpChain("my_special_gap", contributors=[
            DimensionContributor("x", 5.0, 0.1, 0.1),
        ])
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            print_stack_up_report(compute_stack_up(chain))
        self.assertIn("my_special_gap", buf.getvalue())

    def test_output_contains_yield_when_spec_given(self):
        result = compute_stack_up(
            _simple_chain(2, nominal=5.0, tol=0.1, spec_min=9.5, spec_max=10.5)
        )
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            print_stack_up_report(result)
        self.assertIn("yield", buf.getvalue().lower())

    def test_output_no_yield_without_spec(self):
        result = _result(2, nominal=5.0, tol=0.1)
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            print_stack_up_report(result)
        self.assertNotIn("yield", buf.getvalue().lower())


if __name__ == "__main__":
    unittest.main()
