"""Empirical convection correlations for forced flow in a rectangular channel.

All inputs and outputs share the same consistent unit system — no conversion is
applied internally.  For the heat-sink context (mm, W, K) pass lengths in mm,
conductivity in W/(mm·K), viscosity in N·s/mm², etc.

References
----------
[1] Shah, R.K. & London, A.L. (1978).
    Laminar Flow Forced Convection in Ducts.
    Academic Press, New York.
    — Polynomial fits for fully-developed Nu (Table 43, H1 and T conditions).
    — Graetz-problem local Nu correlations (Eqs. 68–70).

[2] Gnielinski, V. (1976).
    New equations for heat and mass transfer in turbulent pipe and channel flow.
    International Chemical Engineering, 16(2), 359–368.
    — Main turbulent Nusselt correlation; valid 0.5 ≤ Pr ≤ 2000,
      3000 ≤ Re ≤ 5×10⁶.

[3] Petukhov, B.S. (1970).
    Heat transfer and friction in turbulent pipe flow with variable physical
    properties.  Advances in Heat Transfer, 6, 503–564.
    — Friction-factor formula used inside the Gnielinski correlation.

[4] Incropera, F.P., DeWitt, D.P., Bergman, T.L. & Lavine, A.S. (2007).
    Fundamentals of Heat and Mass Transfer, 6th ed.  Wiley, Hoboken.
    — Flow-regime boundaries, entry-length estimates (§§ 8.1–8.5).
    — Transitional-regime blending approach (§ 8.7).

[5] Hausen, H. (1943).
    Darstellung des Wärmeüberganges in Rohren durch verallgemeinerte
    Potenzbeziehungen.  VDI Zeitung Beiheft Verfahrenstechnik, 4, 91–98.
    — Combined-entry-length mean Nu for laminar flow.

[6] Dittus, F.W. & Boelter, L.M.K. (1930).
    Heat transfer in automobile radiators of the tubular type.
    University of California Publications in Engineering, 2(13), 443–461.
    — Classic turbulent correlation (used for cross-checking only).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


# ---------------------------------------------------------------------------
# Results container
# ---------------------------------------------------------------------------

@dataclass
class ConvectionResults:
    """Outputs from a ``RectangularChannelConvection`` evaluation.

    Scalar quantities
    -----------------
    h_avg : float
        Length-averaged heat-transfer coefficient  h̄ = (1/L) ∫₀ᴸ h(x) dx.
    Nu_avg : float
        Length-averaged Nusselt number  Nu̅ = h̄ · Dh / k.
    Re : float
        Reynolds number based on hydraulic diameter.
    Pr : float
        Prandtl number.
    Dh : float
        Hydraulic diameter  Dh = 4·A / P = 2·H·W / (H + W).
    flow_regime : str
        ``'laminar'``, ``'transitional'``, or ``'turbulent'``.

    Field quantities (along channel length)
    ----------------------------------------
    x_field : ndarray, shape (n,)
        Positions from channel inlet.
    h_field : ndarray, shape (n,)
        Local heat-transfer coefficient at each position.
    Nu_field : ndarray, shape (n,)
        Local Nusselt number at each position.
    """
    h_avg:       float
    Nu_avg:      float
    Re:          float
    Pr:          float
    Dh:          float
    flow_regime: str
    x_field:     np.ndarray = field(repr=False)
    h_field:     np.ndarray = field(repr=False)
    Nu_field:    np.ndarray = field(repr=False)


# ---------------------------------------------------------------------------
# Main callable
# ---------------------------------------------------------------------------

class RectangularChannelConvection:
    """Empirical h-coefficient model for forced convection in a rectangular duct.

    The channel is assumed to have a uniform cross-section and a single inlet
    where both the hydrodynamic and thermal boundary layers start developing.

    Parameters
    ----------
    channel_height : float
        Internal channel height  H  [length].
    channel_width : float
        Internal channel width   W  [length].
    channel_length : float
        Channel length           L  [length].
    velocity : float
        Mean (bulk) fluid velocity  U  [length / time].
    density : float
        Fluid density  ρ  [mass / length³].
    dynamic_viscosity : float
        Dynamic viscosity  μ  [mass / (length · time)].
    thermal_conductivity : float
        Fluid thermal conductivity  k  [power / (length · K)].
    specific_heat : float
        Fluid specific heat at constant pressure  cₚ  [energy / (mass · K)].
    n_points : int
        Number of equally-spaced sample points along the channel for the field
        output.  Default 200.
    bc_type : ``'H'`` | ``'T'``
        Thermal boundary condition used for the fully-developed laminar Nusselt
        number.
        ``'H'`` — uniform axial heat flux, uniform peripheral temperature (H1
        condition).  [Ref. 1, Table 43]
        ``'T'`` — uniform wall temperature.  [Ref. 1, Table 43]
        For the entry-region (Graetz) solution the T-condition form is used in
        both cases because it is the more conservative (lower Nu) bound and
        the closed-form expressions are better established.  [Ref. 1, Eqs. 68–70]
    """

    # Flow-regime boundaries [Ref. 4, §8.1]
    RE_LAM_MAX  = 2_300
    RE_TURB_MIN = 10_000

    def __init__(
        self,
        channel_height: float,
        channel_width: float,
        channel_length: float,
        velocity: float,
        density: float,
        dynamic_viscosity: float,
        thermal_conductivity: float,
        specific_heat: float,
        n_points: int = 200,
        bc_type: str = "H",
    ) -> None:
        if bc_type not in ("H", "T"):
            raise ValueError("bc_type must be 'H' (uniform heat flux) or 'T' (uniform wall temp)")

        self.H   = float(channel_height)
        self.W   = float(channel_width)
        self.L   = float(channel_length)
        self.U   = float(velocity)
        self.rho = float(density)
        self.mu  = float(dynamic_viscosity)
        self.k   = float(thermal_conductivity)
        self.cp  = float(specific_heat)
        self.n_points = int(n_points)
        self.bc_type  = bc_type

    # ------------------------------------------------------------------
    def __call__(self) -> ConvectionResults:
        """Compute average and field heat-transfer coefficients."""
        Dh  = 2.0 * self.H * self.W / (self.H + self.W)   # hydraulic diameter
        Re  = self.rho * self.U * Dh / self.mu
        Pr  = self.mu * self.cp / self.k

        if Re < self.RE_LAM_MAX:
            regime = "laminar"
        elif Re >= self.RE_TURB_MIN:
            regime = "turbulent"
        else:
            regime = "transitional"

        # Evaluate local Nu at n_points along x; avoid x=0 (Gz → ∞)
        x = np.linspace(self.L / self.n_points, self.L, self.n_points)

        Nu_lam_field  = self._nu_laminar_field(x, Re, Pr, Dh)
        Nu_turb_field = self._nu_turbulent_field(x, Re, Pr, Dh)

        if regime == "laminar":
            Nu_field = Nu_lam_field
        elif regime == "turbulent":
            Nu_field = Nu_turb_field
        else:
            # Linear blend in Re between the two limiting solutions [Ref. 4, §8.7]
            w = (Re - self.RE_LAM_MAX) / (self.RE_TURB_MIN - self.RE_LAM_MAX)
            Nu_field = (1.0 - w) * Nu_lam_field + w * Nu_turb_field

        h_field  = Nu_field * self.k / Dh
        h_avg    = float(np.mean(h_field))
        Nu_avg   = h_avg * Dh / self.k

        return ConvectionResults(
            h_avg=h_avg,
            Nu_avg=Nu_avg,
            Re=Re,
            Pr=Pr,
            Dh=Dh,
            flow_regime=regime,
            x_field=x,
            h_field=h_field,
            Nu_field=Nu_field,
        )

    # ------------------------------------------------------------------
    # Laminar
    # ------------------------------------------------------------------

    def _nu_fd_laminar(self) -> float:
        """Fully-developed Nusselt number for laminar flow in a rectangular duct.

        Uses the polynomial fits from Shah & London (1978), Table 43, as a
        function of the aspect ratio  α* = min(H, W) / max(H, W) ∈ [0, 1].

        H1 condition (uniform heat flux) [Ref. 1, Eq. 52]:
            Nu_H = 8.235 · (1 − 2.0421α* + 3.0853α*² − 2.4765α*³
                               + 1.0578α*⁴ − 0.1861α*⁵)
            Limits: 8.235 (parallel plates, α*=0) → 3.608 (square, α*=1)

        T condition (uniform wall temperature) [Ref. 1, Eq. 53]:
            Nu_T = 7.541 · (1 − 2.610α* + 4.970α*² − 5.119α*³
                               + 2.702α*⁴ − 0.548α*⁵)
            Limits: 7.541 (parallel plates) → 2.976 (square)
        """
        ar = min(self.H, self.W) / max(self.H, self.W)  # α* ∈ [0, 1]

        if self.bc_type == "H":
            # Shah & London (1978) Eq. 52  [Ref. 1]
            Nu = 8.235 * (1.0
                          - 2.0421 * ar
                          + 3.0853 * ar**2
                          - 2.4765 * ar**3
                          + 1.0578 * ar**4
                          - 0.1861 * ar**5)
        else:
            # Shah & London (1978) Eq. 53  [Ref. 1]
            Nu = 7.541 * (1.0
                          - 2.610  * ar
                          + 4.970  * ar**2
                          - 5.119  * ar**3
                          + 2.702  * ar**4
                          - 0.548  * ar**5)
        return Nu

    def _nu_laminar_local(self, Gz_x: np.ndarray) -> np.ndarray:
        """Local Nusselt for thermally developing, hydrodynamically developed
        laminar flow (Graetz problem, T-condition).

            Gz_x = (Dh / x) · Re · Pr          (local Graetz number)

        Thermally developing region [Ref. 1, Eq. 68]:
            Nu_x = 1.077 · Gz_x^(1/3) − 0.70

        This is the local (not mean) asymptotic solution valid for Gz_x ≥ 33.3.
        Outside this range (large x, small Gz_x) the flow is fully developed and
        Nu_x is clipped to Nu_fd, giving a smooth monotonically decreasing profile.

        Note: the formula  3.657 + 6.874·(1000/Gz)^0.488·exp(−57.2/Gz)  from
        Shah & London (1978) Eq. 70 is the *mean* Nu averaged from 0 to x, not
        the local Nu.  Using it here as a second branch would introduce a
        discontinuity of ~7 at Gz_x = 33.3 and is therefore excluded.
        """
        Nu_fd  = self._nu_fd_laminar()
        Nu_loc = 1.077 * Gz_x ** (1.0 / 3.0) - 0.70
        return np.maximum(Nu_loc, Nu_fd)

    def _nu_laminar_field(
        self, x: np.ndarray, Re: float, Pr: float, Dh: float
    ) -> np.ndarray:
        """Local laminar Nu along the channel length."""
        Gz_x = (Dh / x) * Re * Pr
        return self._nu_laminar_local(Gz_x)

    # ------------------------------------------------------------------
    # Turbulent
    # ------------------------------------------------------------------

    def _nu_turbulent_fd(self, Re: float, Pr: float) -> float:
        """Fully-developed turbulent Nusselt using Gnielinski (1976) [Ref. 2].

        Friction factor from Petukhov (1970) [Ref. 3]:
            f = (0.790 · ln Re − 1.64)^(−2)

        Gnielinski correlation:
            Nu = (f/8)(Re − 1000)Pr
                 ─────────────────────────────────────
                 1 + 12.7 · (f/8)^0.5 · (Pr^(2/3) − 1)

        Validity: 0.5 ≤ Pr ≤ 2000,  3000 ≤ Re ≤ 5×10⁶.
        """
        f  = (0.790 * np.log(Re) - 1.64) ** (-2)   # Petukhov [Ref. 3]
        Nu = ((f / 8.0) * (Re - 1000.0) * Pr
              / (1.0 + 12.7 * (f / 8.0) ** 0.5 * (Pr ** (2.0 / 3.0) - 1.0)))
        return float(Nu)

    def _nu_turbulent_field(
        self, x: np.ndarray, Re: float, Pr: float, Dh: float
    ) -> np.ndarray:
        """Local turbulent Nu with entry-region correction.

        The fully-developed value (Gnielinski) is enhanced near the inlet using
        the entry correction proposed by Nusselt and cited in Incropera et al.
        (2007), §8.5  [Ref. 4]:

            Nu(x) = Nu_fd · [1 + (Dh / x)^0.7]

        This decays to Nu_fd as x → ∞ and provides a smooth, physically correct
        increase towards the inlet.  The exponent 0.7 is a widely used empirical
        value for moderate Prandtl numbers (Pr ≈ 0.7–7).
        """
        Nu_fd   = self._nu_turbulent_fd(Re, Pr)
        Nu_field = Nu_fd * (1.0 + (Dh / x) ** 0.7)
        return Nu_field


# ---------------------------------------------------------------------------
# Script entry-point — quick sanity check with air in a heat-sink channel
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import matplotlib
    matplotlib.use("TkAgg")
    import matplotlib.pyplot as plt

    # Air at ~60 °C, SI units (m, W, kg, s, K)
    air = dict(
        density=1.060,           # kg/m³
        dynamic_viscosity=1.96e-5,  # Pa·s
        thermal_conductivity=0.0281, # W/(m·K)
        specific_heat=1007.0,    # J/(kg·K)
    )

    channel = RectangularChannelConvection(
        channel_height=5e-3,     # 5 mm
        channel_width=3e-3,      # 3 mm
        channel_length=50e-3,    # 50 mm
        velocity=2.0,            # m/s
        bc_type="H",
        **air,
    )
    r = channel()

    print(f"Re           = {r.Re:.1f}  ({r.flow_regime})")
    print(f"Pr           = {r.Pr:.3f}")
    print(f"Dh           = {r.Dh*1e3:.2f} mm")
    print(f"Nu_avg       = {r.Nu_avg:.2f}")
    print(f"h_avg        = {r.h_avg:.1f} W/(m²·K)")

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(r.x_field * 1e3, r.h_field, lw=2)
    ax.axhline(r.h_avg, ls="--", color="gray", label=f"h̄ = {r.h_avg:.1f} W/(m²·K)")
    ax.set_xlabel("x  [mm]")
    ax.set_ylabel("h(x)  [W/(m²·K)]")
    ax.set_title(f"Local heat-transfer coefficient — Re={r.Re:.0f} ({r.flow_regime})")
    ax.legend()
    plt.tight_layout()
    plt.show()
