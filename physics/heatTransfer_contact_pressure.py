"""Thermal contact conductance between two rough solid surfaces under pressure.

The total interface conductance has two parallel heat paths:

    h_total = h_spot + h_gap

where *h_spot* is heat flow through solid-to-solid asperity contacts and
*h_gap* is heat flow through the interstitial medium (gas or thermal paste)
filling the voids between asperities.

When thermal paste is specified *h_gap* uses the paste conductivity instead of
the gas conductivity.  An optional explicit bond-line thickness overrides the
computed mean gap when the paste layer is thicker than the surface roughness.

All inputs and outputs share the same consistent unit system — no conversion is
applied internally.  Typical choices:

    SI  : lengths [m], conductivity [W/(m·K)], pressure [Pa],  hardness [Pa]
    mm  : lengths [mm], conductivity [W/(mm·K)], pressure [N/mm²=MPa], hardness [MPa]

References
----------
[1] Cooper, M.G., Mikic, B.B. & Yovanovich, M.M. (1969).
    Thermal contact conductance.
    International Journal of Heat and Mass Transfer, 12(3), 279–300.
    — Cooper-Mikic-Yovanovich (CMY) correlation for asperity spot conductance:
      h_s = 1.25 · k_s · (m_s/σ_s) · (P/H_c)^0.95

[2] Yovanovich, M.M. (2005).
    Four decades of research on thermal contact, gap, and joint resistance in
    microelectronics.
    IEEE Transactions on Components and Packaging Technologies, 28(2), 182–206.
    — Comprehensive review of CMY, gap and joint conductance models.
    — Gas rarefaction parameter M formulation (§ IV-B).

[3] Antonetti, V.W. & Yovanovich, M.M. (1985).
    Enhancement of thermal contact conductance by metallic coatings: theory and
    experiment.
    Journal of Heat Transfer, 107(3), 513–519.
    — Empirical mean plane separation: Y/σ_s = exp(−0.8314·(P/H_c)^0.547)

[4] Madhusudana, C.V. (1996).
    Thermal Contact Conductance.
    Springer, New York.
    — Gap conductance model: h_g = k_f / (Y + M)
    — Parallel-path model: h_total = h_spot + h_gap  (Ch. 2–3)

[5] Song, S. & Yovanovich, M.M. (1988).
    Relative contact pressure: dependence on surface roughness and Vickers
    microhardness.
    Journal of Thermophysics and Heat Transfer, 2(1), 43–47.
    — Dimensionless pressure P/H_c as the controlling parameter.

[6] Incropera, F.P., DeWitt, D.P., Bergman, T.L. & Lavine, A.S. (2007).
    Fundamentals of Heat and Mass Transfer, 6th ed.  Wiley, Hoboken.
    — Contact conductance overview and representative material data (Table 3.2).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


# ---------------------------------------------------------------------------
# Material / surface descriptor
# ---------------------------------------------------------------------------

@dataclass
class ContactSurface:
    """Thermal and mechanical surface properties for one contacting body.

    Parameters
    ----------
    thermal_conductivity : float
        k  [W/(length·K)] — bulk thermal conductivity of the material.
    roughness_rms : float
        σ  [length] — RMS (Ra-equivalent) surface roughness of the contact face.
    asperity_slope_rms : float
        m  [–] — RMS slope of the surface profile asperities (dimensionless).
        Typical ranges:  ground/milled ≈ 0.10–0.20,  lapped ≈ 0.02–0.08.
        Can be estimated as  m ≈ 0.076 · σ^0.52  (σ in μm, Antonetti 1983).
    microhardness : float
        H_c  [force/length²] — Vickers microhardness of this surface.
        The *softer* of the two surfaces controls plastic deformation.
        Use the same pressure units as the contact pressure input.
    """
    thermal_conductivity: float
    roughness_rms:        float
    asperity_slope_rms:   float
    microhardness:        float


# ---------------------------------------------------------------------------
# Results container
# ---------------------------------------------------------------------------

@dataclass
class ContactResults:
    """Outputs from a ``ContactConductance`` evaluation.

    All conductance values share the units W/(length²·K) consistent with the
    input unit system.

    Scalar or array quantities (shape matches the *pressure* input)
    ---------------------------------------------------------------
    pressure : float | ndarray
        Applied nominal contact pressure.
    h_spot : float | ndarray
        Asperity contact-spot conductance  h_s  (CMY model)  [Ref. 1].
    h_gap : float | ndarray
        Interstitial gap conductance  h_g  through gas or thermal paste  [Ref. 4].
    h_total : float | ndarray
        Total interface conductance  h_total = h_spot + h_gap.
    R_total : float | ndarray
        Total interface thermal resistance  R = 1 / h_total  [length²·K/W].
    mean_gap : float | ndarray
        Mean plane separation  Y  between the two surfaces  [length]  [Ref. 3].

    Metadata
    --------
    with_paste : bool
        True if a thermal paste was used for the gap conductance.
    k_harmonic : float
        Harmonic mean conductivity  k_s = 2·k_a·k_b / (k_a + k_b).
    sigma_combined : float
        Combined RMS roughness  σ_s = √(σ_a² + σ_b²).
    slope_combined : float
        Combined RMS slope  m_s = √(m_a² + m_b²).
    hardness_effective : float
        Microhardness of the softer surface used in the model.
    """
    pressure:          float | np.ndarray
    h_spot:            float | np.ndarray
    h_gap:             float | np.ndarray
    h_total:           float | np.ndarray
    R_total:           float | np.ndarray
    mean_gap:          float | np.ndarray
    with_paste:        bool
    k_harmonic:        float
    sigma_combined:    float
    slope_combined:    float
    hardness_effective: float


# ---------------------------------------------------------------------------
# Main callable
# ---------------------------------------------------------------------------

class ContactConductance:
    """Thermal contact conductance model for two rough surfaces under pressure.

    Implements the Cooper-Mikic-Yovanovich (CMY) spot conductance correlation
    combined with a gap conductance model.  Supports both bare-surface (gas gap)
    and thermal-paste configurations.

    Parameters
    ----------
    surface_a, surface_b : ContactSurface
        Thermal and mechanical properties of each contacting surface.
    gap_fluid_conductivity : float
        k_f  — thermal conductivity of the interstitial gas (default: air at
        ~300 K ≈ 0.026 W/(m·K)).  Ignored when *paste_conductivity* is set.
    gas_parameter : float
        M  [length] — gas rarefaction parameter that accounts for the
        temperature jump at the gas–solid interface (Knudsen effect).
        For air at 1 atm and 300 K, M ≈ 4×10⁻⁷ m = 0.4 μm  [Ref. 2].
        Set to 0 to ignore rarefaction (appropriate for liquids or rough surfaces
        where Y ≫ M).
    paste_conductivity : float | None
        k_paste  — thermal conductivity of the thermal paste or TIM.
        When provided, paste replaces the interstitial gas in the gap model.
        Set to None (default) for a bare metal-to-metal contact with gas gap.
    paste_thickness : float | None
        t_paste  [length] — explicit bond-line thickness of the paste layer.
        When None, the computed mean plane separation Y is used as the paste
        thickness (paste fills only the interfacial gap).
        When > 0, the paste is modelled as a slab of uniform thickness t_paste
        (use this when the paste layer is thicker than the surface roughness,
        e.g. a controlled dispense application).
    n_pressure_points : int
        Number of pressure points for the field output when calling with a
        pressure range.  Default 200.
    """

    def __init__(
        self,
        surface_a: ContactSurface,
        surface_b: ContactSurface,
        gap_fluid_conductivity: float = 0.026,
        gas_parameter: float = 4e-7,
        paste_conductivity: float | None = None,
        paste_thickness: float | None = None,
        n_pressure_points: int = 200,
    ) -> None:
        self.surface_a = surface_a
        self.surface_b = surface_b
        self.k_fluid   = gap_fluid_conductivity
        self.M         = gas_parameter
        self.k_paste   = paste_conductivity
        self.t_paste   = paste_thickness
        self.n_pts     = n_pressure_points

        # Combined surface parameters (computed once)
        a, b = surface_a, surface_b
        self._k_s   = 2.0 * a.thermal_conductivity * b.thermal_conductivity \
                      / (a.thermal_conductivity + b.thermal_conductivity)
        self._sigma = np.sqrt(a.roughness_rms**2 + b.roughness_rms**2)
        self._m     = np.sqrt(a.asperity_slope_rms**2 + b.asperity_slope_rms**2)
        self._H_c   = min(a.microhardness, b.microhardness)  # softer surface governs

    # ------------------------------------------------------------------
    def __call__(self, pressure: float | np.ndarray) -> ContactResults:
        """Compute contact conductance at the given pressure(s).

        Parameters
        ----------
        pressure : float or ndarray
            Nominal contact pressure (scalar or 1-D array).  Must be > 0 and
            should satisfy P/H_c < 1 (elastic-plastic asperity regime).

        Returns
        -------
        ContactResults
            Scalar fields when *pressure* is a float; array fields when an
            array is passed.
        """
        p = np.asarray(pressure, dtype=float)
        scalar = p.ndim == 0
        p = np.atleast_1d(p)

        h_spot, h_gap, mean_gap = self._evaluate(p)
        h_total = h_spot + h_gap
        R_total = np.where(h_total > 0, 1.0 / h_total, np.inf)

        if scalar:
            h_spot   = float(h_spot[0])
            h_gap    = float(h_gap[0])
            h_total  = float(h_total[0])
            R_total  = float(R_total[0])
            mean_gap = float(mean_gap[0])
            p_out    = float(p[0])
        else:
            p_out = p

        return ContactResults(
            pressure=p_out,
            h_spot=h_spot,
            h_gap=h_gap,
            h_total=h_total,
            R_total=R_total,
            mean_gap=mean_gap,
            with_paste=self.k_paste is not None,
            k_harmonic=self._k_s,
            sigma_combined=self._sigma,
            slope_combined=self._m,
            hardness_effective=self._H_c,
        )

    # ------------------------------------------------------------------
    def pressure_sweep(
        self,
        p_min: float,
        p_max: float,
    ) -> ContactResults:
        """Evaluate over a logarithmically spaced pressure range.

        Convenience method for generating a conductance-vs-pressure curve.

        Parameters
        ----------
        p_min, p_max : float
            Pressure bounds (same units as the single-pressure call).
        """
        pressures = np.logspace(np.log10(p_min), np.log10(p_max), self.n_pts)
        return self(pressures)

    # ------------------------------------------------------------------
    # Internal physics
    # ------------------------------------------------------------------

    def _evaluate(
        self, p: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Return (h_spot, h_gap, mean_gap) for a pressure array."""
        h_spot   = self._cmy_spot_conductance(p)
        mean_gap = self._mean_plane_separation(p)
        h_gap    = self._gap_conductance(mean_gap)
        return h_spot, h_gap, mean_gap

    def _cmy_spot_conductance(self, p: np.ndarray) -> np.ndarray:
        """Cooper-Mikic-Yovanovich asperity contact conductance [Ref. 1].

        Correlation:
            h_s = 1.25 · k_s · (m_s / σ_s) · (P / H_c)^0.95

        where
            k_s = 2·k_a·k_b / (k_a + k_b)   harmonic mean conductivity
            σ_s = √(σ_a² + σ_b²)             combined RMS roughness
            m_s = √(m_a² + m_b²)             combined RMS slope
            H_c = microhardness of softer surface

        Valid for elastic-plastic asperity deformation, P/H_c ∈ (10⁻⁵, 0.5).
        """
        p_norm = p / self._H_c                   # dimensionless contact pressure
        return 1.25 * self._k_s * (self._m / self._sigma) * p_norm ** 0.95

    def _mean_plane_separation(self, p: np.ndarray) -> np.ndarray:
        """Mean gap between the two mean surface planes under load [Ref. 3].

        Empirical fit from Antonetti & Yovanovich (1985):
            Y / σ_s = exp(−0.8314 · (P / H_c)^0.547)

        At zero pressure Y = σ_s (gap equals combined roughness amplitude).
        At P = H_c the gap reduces to ≈ 0.44 · σ_s.
        Monotonically decreasing with pressure; always positive.
        """
        p_norm = np.clip(p / self._H_c, 1e-10, None)
        return self._sigma * np.exp(-0.8314 * p_norm ** 0.547)

    def _gap_conductance(self, Y: np.ndarray) -> np.ndarray:
        """Heat transfer through the interstitial gap medium [Ref. 4].

        Without paste (gas gap):
            h_g = k_f / (Y + M)
            where M is the gas rarefaction parameter [Ref. 2].

        With paste (paste fills the gap):
            h_g = k_paste / (t_paste or Y)
            The optional *paste_thickness* overrides Y when the paste layer
            is thicker than the interfacial gap (controlled dispense).
        """
        if self.k_paste is not None:
            thickness = self.t_paste if self.t_paste is not None else Y
            thickness = np.broadcast_to(np.asarray(thickness, dtype=float), Y.shape).copy()
            thickness = np.maximum(thickness, 1e-30)   # guard against zero
            return self.k_paste / thickness
        else:
            return self.k_fluid / (Y + self.M)


# ---------------------------------------------------------------------------
# Script entry-point — example: aluminium–aluminium interface, with and
# without thermal paste, over a range of contact pressures
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import matplotlib
    matplotlib.use("TkAgg")
    import matplotlib.pyplot as plt

    # --- Surface definitions ---
    # Ground aluminium surface (typical heat-sink mounting face)
    aluminium = ContactSurface(
        thermal_conductivity=200.0,     # W/(m·K)
        roughness_rms=1.6e-6,           # σ = 1.6 μm  (Ra ≈ 1.2 μm → σ ≈ 1.6 μm)
        asperity_slope_rms=0.12,        # typical ground surface
        microhardness=1.0e9,            # ~ 100 HV → 1 GPa
    )

    # Stainless steel surface (slightly rougher, harder)
    steel = ContactSurface(
        thermal_conductivity=15.0,      # W/(m·K)
        roughness_rms=3.2e-6,           # σ = 3.2 μm
        asperity_slope_rms=0.15,
        microhardness=2.0e9,            # ~ 200 HV → 2 GPa
    )

    # --- Models ---
    al_al_bare  = ContactConductance(aluminium, aluminium)
    al_al_paste = ContactConductance(
        aluminium, aluminium,
        paste_conductivity=4.0,         # W/(m·K)  — typical silver-filled paste
    )
    al_ss_bare  = ContactConductance(aluminium, steel)
    al_ss_paste = ContactConductance(
        aluminium, steel,
        paste_conductivity=4.0,
    )

    # Pressure sweep: 0.1 MPa to 100 MPa
    p_min, p_max = 1e5, 1e8

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    for ax, model_bare, model_paste, label in [
        (axes[0], al_al_bare,  al_al_paste,  "Al – Al"),
        (axes[1], al_ss_bare,  al_ss_paste,  "Al – Steel"),
    ]:
        rb = model_bare.pressure_sweep(p_min, p_max)
        rp = model_paste.pressure_sweep(p_min, p_max)
        p_MPa = rb.pressure * 1e-6

        ax.loglog(p_MPa, rb.h_spot,  "b--",  lw=1.2, label="spot (bare)")
        ax.loglog(p_MPa, rb.h_gap,   "g--",  lw=1.2, label="gap / air (bare)")
        ax.loglog(p_MPa, rb.h_total, "b-",   lw=2.0, label="total (bare)")
        ax.loglog(p_MPa, rp.h_total, "r-",   lw=2.0, label="total (paste 4 W/m·K)")

        ax.set_xlabel("Contact pressure  [MPa]")
        ax.set_ylabel("h  [W/(m²·K)]")
        ax.set_title(f"Contact conductance — {label}")
        ax.legend(fontsize=8)
        ax.grid(True, which="both", ls=":")

    plt.tight_layout()
    plt.show()
