"""Tolerance stack-up analysis from shape_dimension.SolidDimensions output.

Computes 1-D tolerance chains using three methods:
  - Worst-Case (WC)  — linear sum of all tolerance magnitudes (pessimistic)
  - RSS              — Root Sum of Squares at 3σ (statistical, ~99.73%)
  - Monte Carlo      — full numerical distribution simulation

Quick start — manual chain
--------------------------
    from tolerance_advisor.toleranceStackup import (
        DimensionContributor, StackUpChain, compute_stack_up,
    )
    chain = StackUpChain(
        name="end_play",
        contributors=[
            DimensionContributor("housing_depth",  60.0, 0.10, 0.10, sensitivity=-1.0),
            DimensionContributor("shaft_length",   55.0, 0.08, 0.08),
            DimensionContributor("spacer_width",    4.5, 0.05, 0.05),
        ],
        spec_min=0.0,
        spec_max=0.5,
    )
    result = compute_stack_up(chain)
    print_stack_up_report(result)

Quick start — from shape_dimension output
------------------------------------------
    from post_process.shape_dimension import SolidDimensions
    from tolerance_advisor.helpers import load_process_capabilities
    from tolerance_advisor.toleranceStackup import contributors_from_solid, StackUpChain, compute_stack_up

    db = load_process_capabilities()
    contributors = contributors_from_solid(solid_dims, process="CNC_milling", db=db)
    chain = StackUpChain(name="overall_envelope", contributors=contributors)
    result = compute_stack_up(chain)

Quick start — from MinimalDimensionSet
---------------------------------------
    from tolerance_advisor.toleranceStackup import contributors_from_mds
    chain = StackUpChain("part_A_chain", contributors=contributors_from_mds(mds))
    result = compute_stack_up(chain)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from post_process.shape_dimension import SolidDimensions
    from post_process.dimension_minimal import MinimalDimensionSet

_EPSILON = 1e-9


# ---------------------------------------------------------------------------
# Tolerance lookup helpers
# ---------------------------------------------------------------------------

# ISO 2768-1 linear tolerance table (±mm). Source: ISO 2768-1:1989 Table 1.
# Columns: (upper_mm_inclusive, f, m, c, v) — None = class not defined.
_ISO_2768_TABLE: List[Tuple[float, Optional[float], Optional[float], Optional[float], Optional[float]]] = [
    #  upper   f      m      c      v
    (   3.0, 0.05,  0.10,  0.20,  None),
    (   6.0, 0.05,  0.10,  0.30,  0.50),
    (  30.0, 0.10,  0.20,  0.50,  1.00),
    ( 120.0, 0.15,  0.30,  0.80,  1.50),
    ( 400.0, 0.20,  0.50,  1.20,  2.50),
    (1000.0, 0.30,  0.80,  2.00,  4.00),
    (2000.0, 0.50,  1.20,  3.00,  6.00),
]
_ISO_2768_COL = {"f": 1, "m": 2, "c": 3, "v": 4}

# Built-in process ±tolerance fallback table when no YAML DB is available.
_PROCESS_TOL_TABLE: dict[str, dict[tuple[float, float], float]] = {
    "CNC_milling":          {(0, 25): 0.025, (25, 100): 0.038, (100, 500): 0.075},
    "CNC_turning":          {(0, 25): 0.013, (25, 100): 0.025, (100, 500): 0.050},
    "cylindrical_grinding": {(0, 25): 0.008, (25, 100): 0.013, (100, 500): 0.025},
    "injection_moulding":   {(0, 25): 0.10,  (25, 100): 0.15,  (100, 300): 0.25},
    "injection_molding":    {(0, 25): 0.10,  (25, 100): 0.15,  (100, 300): 0.25},
    "sheet_metal_bending":  {(0, 50): 0.25,  (50, 200): 0.40,  (200, 1000): 0.80},
    "die_casting":          {(0, 25): 0.10,  (25, 100): 0.20,  (100, 500): 0.40},
    "FDM_3D_print":         {(0, 50): 0.20,  (50, 200): 0.40,  (200, 500): 0.80},
    "SLS_3D_print":         {(0, 50): 0.15,  (50, 200): 0.30,  (200, 500): 0.60},
    "sand_casting":         {(0, 50): 0.50,  (50, 200): 0.80,  (200, 1000): 1.50},
    "investment_casting":   {(0, 25): 0.20,  (25, 100): 0.30,  (100, 500): 0.50},
}

# Fallback ISO 2768 class when a process is not in _PROCESS_TOL_TABLE.
_PROCESS_ISO_CLASS: dict[str, str] = {
    "CNC_milling":          "m",
    "CNC_turning":          "m",
    "cylindrical_grinding": "f",
    "injection_moulding":   "c",
    "injection_molding":    "c",
    "sheet_metal_bending":  "v",
    "die_casting":          "c",
    "FDM_3D_print":         "v",
    "SLS_3D_print":         "c",
    "sand_casting":         "v",
    "investment_casting":   "c",
}


def assign_iso2768_tolerance(nominal_mm: float, iso_class: str = "m") -> float:
    """Return ±tolerance (mm) per ISO 2768-1 for *nominal_mm* and *iso_class*.

    Parameters
    ----------
    nominal_mm:
        Absolute nominal dimension in mm (sign is ignored).
    iso_class:
        One of ``"f"`` (fine), ``"m"`` (medium), ``"c"`` (coarse),
        ``"v"`` (very coarse).
    """
    col = _ISO_2768_COL.get(iso_class.lower())
    if col is None:
        raise ValueError(
            f"Unknown ISO 2768 class '{iso_class}'; expected f / m / c / v."
        )
    dim = abs(nominal_mm)
    for row in _ISO_2768_TABLE:
        tol = row[col]
        if dim <= row[0]:
            if tol is None:
                raise ValueError(
                    f"ISO 2768 class '{iso_class}' is not defined for "
                    f"nominal {nominal_mm:.3f} mm."
                )
            return tol
    raise ValueError(
        f"Nominal {nominal_mm:.3f} mm exceeds ISO 2768-1 maximum (2000 mm)."
    )


def assign_process_tolerance(nominal_mm: float, process: str) -> float:
    """Return ±tolerance (mm) from the built-in process capability table.

    Falls back to ``assign_iso2768_tolerance`` with the process-mapped ISO
    class if the process key is absent or the nominal is out of range.
    """
    table = _PROCESS_TOL_TABLE.get(process)
    if table:
        dim = abs(nominal_mm)
        for (lo, hi), tol in table.items():
            if lo < dim <= hi:
                return tol
    iso_class = _PROCESS_ISO_CLASS.get(process, "m")
    try:
        return assign_iso2768_tolerance(nominal_mm, iso_class)
    except ValueError:
        # Last resort: 0.1 % of nominal
        return max(abs(nominal_mm) * 0.001, _EPSILON)


def _tol_from_db(nominal_mm: float, process: str, db: Optional[dict]) -> float:
    """Derive ±tolerance from the process YAML DB (IT grade → fundamental_tolerance).

    Mirrors the logic in :func:`post_process.dimension_minimal._tol`.
    Falls back to :func:`assign_process_tolerance` when the DB is unavailable.
    """
    if db is not None:
        try:
            from tolerance_advisor.helpers import choose_process_entry
            from tolerance_advisor.fit_iso286 import fundamental_tolerance

            entry = choose_process_entry(process, db)
            it_grade = entry.get("typical_it_grade", "IT10")
            clamped = max(1.0, min(500.0, abs(nominal_mm)))
            return fundamental_tolerance(clamped, it_grade)
        except Exception:
            pass
    return assign_process_tolerance(nominal_mm, process)


# ---------------------------------------------------------------------------
# Core data classes
# ---------------------------------------------------------------------------

@dataclass
class DimensionContributor:
    """One link in a tolerance stack-up chain.

    Parameters
    ----------
    name:
        Human-readable label (e.g. ``"housing_depth"``).
    nominal:
        Nominal value in mm.  Positive values open the gap; negative
        values close it (or use *sensitivity* = –1 for a positive nominal).
    tol_plus:
        Upper tolerance magnitude in mm (always ≥ 0).
    tol_minus:
        Lower tolerance magnitude in mm (always ≥ 0).
    sensitivity:
        Direction multiplier.  +1.0 (default) contributes positively to
        the gap; –1.0 subtracts.  Can also encode a direction cosine for
        2-D projections.
    distribution:
        Probability model for Monte Carlo sampling.
        ``"normal"`` (default, 3σ = half-range) or ``"uniform"``.
    description:
        Optional free-text note (not used in calculations).
    """

    name: str
    nominal: float
    tol_plus: float
    tol_minus: float
    sensitivity: float = 1.0
    distribution: str = "normal"
    description: str = ""

    @property
    def tol_sym(self) -> float:
        """Symmetric tolerance: average of plus and minus magnitudes."""
        return (self.tol_plus + self.tol_minus) / 2.0

    @property
    def effective_nominal(self) -> float:
        """Signed contribution to the gap = nominal × sensitivity."""
        return self.nominal * self.sensitivity


@dataclass
class StackUpChain:
    """A named 1-D tolerance stack-up chain.

    The nominal gap is the algebraic sum of all
    ``contributor.effective_nominal`` values.

    Parameters
    ----------
    name:
        Descriptive label for the gap or clearance being analysed.
    contributors:
        Ordered list of :class:`DimensionContributor` objects.
    spec_min / spec_max:
        Optional engineering specification limits (mm).  Used for
        yield calculation in Monte Carlo.
    """

    name: str
    contributors: List[DimensionContributor] = field(default_factory=list)
    spec_min: Optional[float] = None
    spec_max: Optional[float] = None

    def add(self, contributor: DimensionContributor) -> "StackUpChain":
        self.contributors.append(contributor)
        return self

    @property
    def nominal_gap(self) -> float:
        return sum(c.effective_nominal for c in self.contributors)


@dataclass
class StackUpResult:
    """Results of a full tolerance stack-up analysis.

    Attributes
    ----------
    chain_name:
        Copied from :attr:`StackUpChain.name`.
    nominal_gap:
        Algebraic sum of all ``effective_nominal`` values.
    wc_min / wc_max:
        Worst-case (linear) gap range.
    rss_min / rss_max:
        RSS statistical gap range at 3σ.
    mc_mean / mc_std:
        Monte Carlo mean and standard deviation.
    mc_yield_pct:
        Percentage of Monte Carlo samples within [spec_min, spec_max].
        ``None`` when no spec limits were provided.
    mc_samples:
        Raw Monte Carlo sample array (shape: (n_mc,)) — used for plotting.
    sensitivity_ranking:
        ``(name, variance_pct)`` pairs sorted by variance contribution
        descending.  Shows where to tighten tolerances for most effect.
    contributors:
        Copy of the input contributor list.
    spec_min / spec_max:
        Engineering spec limits (copied from chain).
    """

    chain_name: str
    nominal_gap: float
    wc_min: float
    wc_max: float
    rss_min: float
    rss_max: float
    mc_mean: float
    mc_std: float
    mc_yield_pct: Optional[float]
    mc_samples: np.ndarray
    sensitivity_ranking: List[Tuple[str, float]]
    contributors: List[DimensionContributor]
    spec_min: Optional[float] = None
    spec_max: Optional[float] = None

    @property
    def wc_passes_spec(self) -> Optional[bool]:
        """True when the worst-case range lies entirely within spec."""
        if self.spec_min is None or self.spec_max is None:
            return None
        return self.wc_min >= self.spec_min and self.wc_max <= self.spec_max

    @property
    def rss_passes_spec(self) -> Optional[bool]:
        """True when the RSS 3σ range lies entirely within spec."""
        if self.spec_min is None or self.spec_max is None:
            return None
        return self.rss_min >= self.spec_min and self.rss_max <= self.spec_max


# ---------------------------------------------------------------------------
# Contributor extraction from shape_dimension output
# ---------------------------------------------------------------------------

def contributors_from_solid(
    solid_dims: "SolidDimensions",
    process: str = "CNC_milling",
    db: Optional[dict] = None,
    iso_class: Optional[str] = None,
    include_cylinders: bool = True,
    include_walls: bool = True,
) -> List[DimensionContributor]:
    """Extract :class:`DimensionContributor` objects from a
    :class:`~post_process.shape_dimension.SolidDimensions`.

    Derives tolerances from the manufacturing process using the same
    logic as :func:`~post_process.dimension_minimal.minimal_solid_dimensions`.

    Parameters
    ----------
    solid_dims:
        Output of :func:`~post_process.shape_dimension.infer_solid_dimensions`.
    process:
        Manufacturing process key.
    db:
        Process capability dict from
        :func:`~tolerance_advisor.helpers.load_process_capabilities`.
        When *None*, the built-in :data:`_PROCESS_TOL_TABLE` is used.
    iso_class:
        Force an ISO 2768 class (``"f"``/``"m"``/``"c"``/``"v"``)
        instead of deriving from the process.
    include_cylinders:
        Include cylindrical-feature contributors (diameter + height).
    include_walls:
        Include wall-thickness contributors.

    Returns
    -------
    List[DimensionContributor]
    """
    contributors: List[DimensionContributor] = []

    def _tol(nominal: float) -> float:
        if iso_class:
            return assign_iso2768_tolerance(nominal, iso_class)
        return _tol_from_db(nominal, process, db)

    sd = solid_dims

    # ── bounding-box principal dimensions (always included) ──────────────────
    for dim_name, dim_val in [
        ("length", sd.length),
        ("width",  sd.width),
        ("height", sd.height),
    ]:
        if dim_val < _EPSILON:
            continue
        t = _tol(dim_val)
        contributors.append(DimensionContributor(
            name=f"solid{sd.solid_id}_{dim_name}",
            nominal=dim_val,
            tol_plus=t,
            tol_minus=t,
            description=f"Bounding-box {dim_name} of solid {sd.solid_id}",
        ))

    # ── cylindrical features ─────────────────────────────────────────────────
    if include_cylinders:
        seen_radii: set[float] = set()
        for cyl in sd.cylinders:
            r_key = round(cyl.radius_est, 3)
            if r_key not in seen_radii:
                seen_radii.add(r_key)
                t = _tol(cyl.diameter_est)
                contributors.append(DimensionContributor(
                    name=f"solid{sd.solid_id}_cyl{cyl.face_id}_diam",
                    nominal=cyl.diameter_est,
                    tol_plus=t,
                    tol_minus=t,
                    description=f"Cylinder Ø (face {cyl.face_id})",
                ))
            t = _tol(max(cyl.height_est, 1.0))
            contributors.append(DimensionContributor(
                name=f"solid{sd.solid_id}_cyl{cyl.face_id}_height",
                nominal=cyl.height_est,
                tol_plus=t,
                tol_minus=t,
                description=f"Cylinder height (face {cyl.face_id})",
            ))

    # ── wall thicknesses ─────────────────────────────────────────────────────
    if include_walls:
        for wt in sd.wall_thicknesses:
            t = _tol(max(wt.thickness_mm, 1.0))
            contributors.append(DimensionContributor(
                name=f"solid{sd.solid_id}_wall_{wt.face_ids[0]}_{wt.face_ids[1]}",
                nominal=wt.thickness_mm,
                tol_plus=t,
                tol_minus=t,
                description=f"Wall between faces {wt.face_ids}",
            ))

    return contributors


def contributors_from_mds(
    mds: "MinimalDimensionSet",
    sensitivity: float = 1.0,
) -> List[DimensionContributor]:
    """Convert a :class:`~post_process.dimension_minimal.MinimalDimensionSet`
    to a list of :class:`DimensionContributor` objects.

    This is the most convenient path when
    :func:`~post_process.dimension_minimal.minimal_solid_dimensions` has
    already been run, because the tolerances are already computed and
    the drawing annotation priority is preserved in the description.

    Parameters
    ----------
    mds:
        Output of :func:`~post_process.dimension_minimal.minimal_solid_dimensions`.
    sensitivity:
        Default direction coefficient applied to all contributors.
        Override per-contributor after the call if directions differ.
    """
    contributors = []
    for dim in mds.dimensions:
        contributors.append(DimensionContributor(
            name=f"{dim.kind}_{dim.nominal_mm:.4g}mm",
            nominal=dim.nominal_mm,
            tol_plus=dim.tolerance_mm,
            tol_minus=dim.tolerance_mm,
            sensitivity=sensitivity,
            description=f"[{dim.it_grade}] {dim.description} ({dim.priority})",
        ))
    return contributors


# ---------------------------------------------------------------------------
# Stack-up solver
# ---------------------------------------------------------------------------

def compute_stack_up(
    chain: StackUpChain,
    n_mc: int = 100_000,
    seed: int = 42,
) -> StackUpResult:
    """Compute WC, RSS, and Monte Carlo tolerance stack-up.

    Parameters
    ----------
    chain:
        Configured :class:`StackUpChain`.
    n_mc:
        Monte Carlo iteration count (default 100 000).
    seed:
        Random seed for reproducible results.

    Returns
    -------
    StackUpResult
    """
    cs = chain.contributors
    if not cs:
        raise ValueError("StackUpChain has no contributors — add at least one.")

    nominal = chain.nominal_gap

    # ── Worst-Case (WC) ─────────────────────────────────────────────────────
    wc_tol = sum(max(c.tol_plus, c.tol_minus) * abs(c.sensitivity) for c in cs)
    wc_min = nominal - wc_tol
    wc_max = nominal + wc_tol

    # ── RSS (Root Sum of Squares, 3σ) ────────────────────────────────────────
    rss_tol = math.sqrt(
        sum((c.tol_sym * abs(c.sensitivity)) ** 2 for c in cs)
    )
    rss_min = nominal - 3.0 * rss_tol
    rss_max = nominal + 3.0 * rss_tol

    # ── Monte Carlo ──────────────────────────────────────────────────────────
    rng = np.random.default_rng(seed)
    samples = np.zeros(n_mc)
    for c in cs:
        midpoint = c.nominal + (c.tol_plus - c.tol_minus) / 2.0
        half_range = c.tol_sym
        if c.distribution == "uniform":
            dim_s = rng.uniform(midpoint - half_range, midpoint + half_range, n_mc)
        else:  # normal: 3σ = half_range
            sigma = half_range / 3.0 if half_range > _EPSILON else _EPSILON
            dim_s = rng.normal(midpoint, sigma, n_mc)
        samples += dim_s * c.sensitivity

    mc_mean = float(np.mean(samples))
    mc_std  = float(np.std(samples))

    mc_yield: Optional[float] = None
    if chain.spec_min is not None and chain.spec_max is not None:
        in_spec = np.sum((samples >= chain.spec_min) & (samples <= chain.spec_max))
        mc_yield = float(in_spec / n_mc * 100.0)

    # ── Sensitivity ranking (% variance contribution) ────────────────────────
    variances = []
    for c in cs:
        sigma = c.tol_sym / 3.0 if c.tol_sym > _EPSILON else _EPSILON
        variances.append((c.name, (sigma * abs(c.sensitivity)) ** 2))
    total_var = sum(v for _, v in variances) or 1.0
    ranked = sorted(
        [(name, var / total_var * 100.0) for name, var in variances],
        key=lambda t: t[1],
        reverse=True,
    )

    return StackUpResult(
        chain_name=chain.name,
        nominal_gap=nominal,
        wc_min=wc_min,
        wc_max=wc_max,
        rss_min=rss_min,
        rss_max=rss_max,
        mc_mean=mc_mean,
        mc_std=mc_std,
        mc_yield_pct=mc_yield,
        mc_samples=samples,
        sensitivity_ranking=ranked,
        contributors=list(cs),
        spec_min=chain.spec_min,
        spec_max=chain.spec_max,
    )


# ---------------------------------------------------------------------------
# Text report
# ---------------------------------------------------------------------------

def print_stack_up_report(result: StackUpResult) -> None:
    """Print a concise text summary of a :class:`StackUpResult` to stdout."""
    W = 70
    print(f"\n{'═' * W}")
    print(f"  TOLERANCE STACK-UP: {result.chain_name}")
    print(f"{'═' * W}")
    print(f"  {'Contributor':<36} {'Nominal':>9}  {'±Tol':>7}  {'Sens':>5}")
    print(f"  {'-' * 62}")
    for c in result.contributors:
        print(
            f"  {c.name:<36} {c.effective_nominal:>+9.4f}"
            f"  {c.tol_sym:>7.4f}  {c.sensitivity:>+5.2f}"
        )
    print(f"  {'-' * 62}")
    print(f"  {'NOMINAL GAP':<36} {result.nominal_gap:>+9.4f}")
    print()
    wc_spread = result.wc_max - result.wc_min
    rss_spread = result.rss_max - result.rss_min
    print(f"  Worst-Case range : [{result.wc_min:+.4f}, {result.wc_max:+.4f}]  "
          f"spread = {wc_spread:.4f} mm")
    print(f"  RSS 3σ range     : [{result.rss_min:+.4f}, {result.rss_max:+.4f}]  "
          f"spread = {rss_spread:.4f} mm")
    print(f"  MC mean ± σ      : {result.mc_mean:+.4f} ± {result.mc_std:.4f} mm")

    if result.mc_yield_pct is not None:
        spec = f"[{result.spec_min:+.4f}, {result.spec_max:+.4f}]"
        print(f"  MC yield in {spec}: {result.mc_yield_pct:.2f}%")

    if result.wc_passes_spec is not None:
        flag = "✓ PASS" if result.wc_passes_spec else "✗ FAIL"
        print(f"  WC spec status   : {flag}")
    if result.rss_passes_spec is not None:
        flag = "✓ PASS" if result.rss_passes_spec else "✗ FAIL"
        print(f"  RSS spec status  : {flag}")

    print(f"\n  Sensitivity ranking (% of total variance):")
    for name, pct in result.sensitivity_ranking[:7]:
        bar = "█" * int(pct / 2)
        print(f"    {pct:5.1f}%  {bar:<25}  {name}")
    print(f"{'═' * W}\n")


__all__ = [
    "DimensionContributor",
    "StackUpChain",
    "StackUpResult",
    "assign_iso2768_tolerance",
    "assign_process_tolerance",
    "contributors_from_solid",
    "contributors_from_mds",
    "compute_stack_up",
    "print_stack_up_report",
]
