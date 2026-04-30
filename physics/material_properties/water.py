"""Thermophysical properties of liquid water as a function of temperature.

Valid for saturated liquid water at atmospheric pressure (0–100 °C / 273.15–373.15 K).
Cubic-spline fits are built at import time from NIST reference data at 5 °C intervals.

Properties
----------
density             ρ   [kg/m³]
specific_heat       cp  [J/(kg·K)]
dynamic_viscosity   μ   [Pa·s]
thermal_conductivity k  [W/(m·K)]
thermal_expansion   β   [1/K]       (negative below ~4 °C)
prandtl             Pr  [-]
thermal_diffusivity α   [m²/s]
kinematic_viscosity ν   [m²/s]

References
----------
[1] NIST Chemistry WebBook, https://webbook.nist.gov
    Fluid properties for H₂O along the saturation curve at 101.325 kPa.
[2] Incropera, F.P. et al. (2007). Fundamentals of Heat and Mass Transfer,
    6th ed. Wiley. Table A.6.
[3] IAPWS (2008). Release on the IAPWS Formulation 2008 for the Viscosity
    of Ordinary Water Substance.

Usage
-----
    from physics.material_properties.water import water

    props = water(293.15)           # T in K (default)
    props = water(20.0, unit="C")   # T in °C

    print(props.density)            # 998.2  kg/m³
    print(props.prandtl)            # ~7.0
    print(props)                    # full dataclass repr
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
from scipy.interpolate import CubicSpline


# ---------------------------------------------------------------------------
# NIST reference data — saturated liquid at 101.325 kPa, 0–100 °C every 5 °C
# ---------------------------------------------------------------------------

#: Reference temperatures [°C]
_T_C_REF = np.arange(0.0, 101.0, 5.0)   # 0, 5, 10, …, 100

#: Density  ρ  [kg/m³]   — NIST [1]
_RHO_REF = np.array([
    999.840, 999.965, 999.700, 999.099, 998.204, 997.045,
    995.649, 994.034, 992.215, 990.203, 988.007, 985.636,
    983.099, 980.401, 977.549, 974.548, 971.402, 968.116,
    964.693, 961.136, 957.448,
])

#: Specific heat  cp  [J/(kg·K)]   — NIST / Incropera [1, 2]
_CP_REF = np.array([
    4218.0, 4202.0, 4192.0, 4185.0, 4182.0, 4180.0,
    4178.0, 4178.0, 4179.0, 4180.0, 4181.0, 4183.0,
    4185.0, 4187.0, 4190.0, 4193.0, 4197.0, 4201.0,
    4205.0, 4210.0, 4216.0,
])

#: Dynamic viscosity  μ  [Pa·s]   — NIST [1, 3]
_MU_REF = np.array([
    1.7921e-3, 1.5186e-3, 1.3069e-3, 1.1375e-3, 1.0020e-3, 8.900e-4,
    7.972e-4,  7.190e-4,  6.527e-4,  5.963e-4,  5.470e-4,  5.040e-4,
    4.660e-4,  4.320e-4,  4.034e-4,  3.781e-4,  3.548e-4,  3.339e-4,
    3.150e-4,  2.976e-4,  2.817e-4,
])

#: Thermal conductivity  k  [W/(m·K)]   — NIST [1]
_K_REF = np.array([
    0.5553, 0.5663, 0.5770, 0.5875, 0.5978, 0.6078,
    0.6175, 0.6269, 0.6360, 0.6448, 0.6532, 0.6612,
    0.6687, 0.6758, 0.6824, 0.6885, 0.6940, 0.6989,
    0.7032, 0.7070, 0.7103,
])

#: Isobaric thermal expansion coefficient  β  [1/K]   — NIST [1]
#  Negative below ≈ 4 °C (density maximum of water).
_BETA_REF = np.array([
    -6.81e-5,  1.50e-5,  8.81e-5,  1.51e-4,  2.06e-4,  2.57e-4,
     3.03e-4,  3.47e-4,  3.86e-4,  4.24e-4,  4.57e-4,  4.91e-4,
     5.22e-4,  5.50e-4,  5.79e-4,  6.05e-4,  6.31e-4,  6.55e-4,
     6.79e-4,  7.02e-4,  7.22e-4,
])


# ---------------------------------------------------------------------------
# Precomputed cubic splines (built once at import time)
# ---------------------------------------------------------------------------
_cs_rho  = CubicSpline(_T_C_REF, _RHO_REF,  bc_type="not-a-knot")
_cs_cp   = CubicSpline(_T_C_REF, _CP_REF,   bc_type="not-a-knot")
_cs_mu   = CubicSpline(_T_C_REF, _MU_REF,   bc_type="not-a-knot")
_cs_k    = CubicSpline(_T_C_REF, _K_REF,    bc_type="not-a-knot")
_cs_beta = CubicSpline(_T_C_REF, _BETA_REF, bc_type="not-a-knot")


# ---------------------------------------------------------------------------
# Results dataclass
# ---------------------------------------------------------------------------
@dataclass
class WaterPropertiesResult:
    """Thermophysical properties of liquid water at a given temperature."""
    T_K:                  float   # K      — temperature
    T_C:                  float   # °C     — temperature
    density:              float   # kg/m³  — ρ
    specific_heat:        float   # J/(kg·K) — cp
    dynamic_viscosity:    float   # Pa·s   — μ
    thermal_conductivity: float   # W/(m·K) — k
    thermal_expansion:    float   # 1/K    — β  (negative below ~4 °C)
    prandtl:              float   # -      — Pr = μ cp / k
    thermal_diffusivity:  float   # m²/s   — α = k / (ρ cp)
    kinematic_viscosity:  float   # m²/s   — ν = μ / ρ


# ---------------------------------------------------------------------------
# Main callable
# ---------------------------------------------------------------------------
class WaterProperties:
    """Thermophysical properties of liquid water as a function of temperature.

    Parameters (at call time)
    -------------------------
    T : float or array-like
        Temperature value(s).
    unit : ``'K'`` | ``'C'``
        Temperature unit.  Default ``'K'``.

    Returns
    -------
    WaterPropertiesResult
        Dataclass with all properties evaluated at *T*.

    Valid range
    -----------
    0–100 °C (273.15–373.15 K) at atmospheric pressure.
    Values outside this range are clipped with a warning.

    Examples
    --------
    >>> props = water(293.15)          # 20 °C in Kelvin
    >>> props = water(20.0, unit="C")  # 20 °C directly
    >>> props.density
    998.2...
    >>> props.prandtl
    7.0...
    """

    T_MIN_C: float = 0.0
    T_MAX_C: float = 100.0

    def __call__(self, T: float, unit: str = "K") -> WaterPropertiesResult:
        if unit == "K":
            T_K = float(T)
            T_C = T_K - 273.15
        elif unit == "C":
            T_C = float(T)
            T_K = T_C + 273.15
        else:
            raise ValueError("unit must be 'K' or 'C'")

        if T_C < self.T_MIN_C or T_C > self.T_MAX_C:
            warnings.warn(
                f"Temperature {T_C:.2f} °C is outside the valid range "
                f"{self.T_MIN_C}–{self.T_MAX_C} °C. Values are extrapolated.",
                stacklevel=2,
            )

        T_C_c = float(np.clip(T_C, self.T_MIN_C, self.T_MAX_C))

        rho  = float(_cs_rho(T_C_c))
        cp   = float(_cs_cp(T_C_c))
        mu   = float(_cs_mu(T_C_c))
        k    = float(_cs_k(T_C_c))
        beta = float(_cs_beta(T_C_c))

        Pr    = mu * cp / k
        alpha = k / (rho * cp)
        nu    = mu / rho

        return WaterPropertiesResult(
            T_K=T_K,
            T_C=T_C,
            density=rho,
            specific_heat=cp,
            dynamic_viscosity=mu,
            thermal_conductivity=k,
            thermal_expansion=beta,
            prandtl=Pr,
            thermal_diffusivity=alpha,
            kinematic_viscosity=nu,
        )


#: Module-level singleton — import and call directly.
water = WaterProperties()


# ---------------------------------------------------------------------------
# Script entry point — property plots over 0–100 °C
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import matplotlib
    matplotlib.use("TkAgg")
    import matplotlib.pyplot as plt

    T_C_plot = np.linspace(0, 100, 300)

    # Evaluate all properties
    props = [water(T, unit="C") for T in T_C_plot]
    rho   = np.array([p.density              for p in props])
    cp    = np.array([p.specific_heat        for p in props])
    mu    = np.array([p.dynamic_viscosity    for p in props])
    k     = np.array([p.thermal_conductivity for p in props])
    beta  = np.array([p.thermal_expansion    for p in props])
    Pr    = np.array([p.prandtl              for p in props])
    alpha = np.array([p.thermal_diffusivity  for p in props])
    nu    = np.array([p.kinematic_viscosity  for p in props])

    fig, axes = plt.subplots(2, 4, figsize=(16, 8))
    fig.suptitle("Thermophysical properties of liquid water  (0–100 °C, 1 atm)", fontsize=13)

    def _panel(ax, y, label, unit, color="steelblue"):
        ax.plot(T_C_plot, y, lw=2, color=color)
        # Overlay reference points
        ax.scatter(_T_C_REF, _cs_k(_T_C_REF) if "conductivity" in label.lower()
                   else _cs_rho(_T_C_REF) if "density" in label.lower()
                   else _cs_cp(_T_C_REF)  if "heat" in label.lower()
                   else _cs_mu(_T_C_REF)  if "viscosity" in label.lower() and "kin" not in label.lower()
                   else _cs_beta(_T_C_REF) if "expansion" in label.lower()
                   else None,
                   s=20, color="tomato", zorder=5, label="NIST ref.")
        ax.set_xlabel("T  [°C]")
        ax.set_ylabel(f"{label}  [{unit}]")
        ax.grid(True, alpha=0.3)

    axes[0, 0].plot(T_C_plot, rho,   lw=2, color="steelblue")
    axes[0, 0].scatter(_T_C_REF, _RHO_REF,  s=20, color="tomato", zorder=5, label="NIST ref.")
    axes[0, 0].set_title("Density  ρ")
    axes[0, 0].set_ylabel("ρ  [kg/m³]")

    axes[0, 1].plot(T_C_plot, cp,    lw=2, color="steelblue")
    axes[0, 1].scatter(_T_C_REF, _CP_REF,   s=20, color="tomato", zorder=5, label="NIST ref.")
    axes[0, 1].set_title("Specific heat  cp")
    axes[0, 1].set_ylabel("cp  [J/(kg·K)]")

    axes[0, 2].plot(T_C_plot, mu * 1e3, lw=2, color="steelblue")
    axes[0, 2].scatter(_T_C_REF, _MU_REF * 1e3, s=20, color="tomato", zorder=5, label="NIST ref.")
    axes[0, 2].set_title("Dynamic viscosity  μ")
    axes[0, 2].set_ylabel("μ  [mPa·s]")

    axes[0, 3].plot(T_C_plot, k,     lw=2, color="steelblue")
    axes[0, 3].scatter(_T_C_REF, _K_REF,    s=20, color="tomato", zorder=5, label="NIST ref.")
    axes[0, 3].set_title("Thermal conductivity  k")
    axes[0, 3].set_ylabel("k  [W/(m·K)]")

    axes[1, 0].plot(T_C_plot, beta * 1e4, lw=2, color="steelblue")
    axes[1, 0].scatter(_T_C_REF, _BETA_REF * 1e4, s=20, color="tomato", zorder=5, label="NIST ref.")
    axes[1, 0].axhline(0, color="k", lw=0.8, ls="--")
    axes[1, 0].set_title("Thermal expansion  β")
    axes[1, 0].set_ylabel("β  [×10⁻⁴ /K]")

    axes[1, 1].plot(T_C_plot, Pr,    lw=2, color="steelblue")
    axes[1, 1].set_title("Prandtl number  Pr")
    axes[1, 1].set_ylabel("Pr  [-]")

    axes[1, 2].plot(T_C_plot, alpha * 1e7, lw=2, color="steelblue")
    axes[1, 2].set_title("Thermal diffusivity  α")
    axes[1, 2].set_ylabel("α  [×10⁻⁷ m²/s]")

    axes[1, 3].plot(T_C_plot, nu * 1e6, lw=2, color="steelblue")
    axes[1, 3].set_title("Kinematic viscosity  ν")
    axes[1, 3].set_ylabel("ν  [×10⁻⁶ m²/s]")

    for ax in axes.flat:
        ax.set_xlabel("T  [°C]")
        ax.grid(True, alpha=0.3)
    for ax in axes[0]:
        handles, labels = ax.get_legend_handles_labels()
        if handles:
            ax.legend(fontsize=8)

    plt.tight_layout()

    # Print spot check at 20 °C
    p20 = water(20.0, unit="C")
    print("\nSpot check — water at 20 °C:")
    print(f"  ρ   = {p20.density:.2f} kg/m³        (ref: 998.2)")
    print(f"  cp  = {p20.specific_heat:.1f} J/(kg·K)   (ref: 4182)")
    print(f"  μ   = {p20.dynamic_viscosity*1e3:.4f} mPa·s      (ref: 1.002)")
    print(f"  k   = {p20.thermal_conductivity:.4f} W/(m·K)    (ref: 0.5984)")
    print(f"  β   = {p20.thermal_expansion*1e4:.4f} ×10⁻⁴/K   (ref: 2.06)")
    print(f"  Pr  = {p20.prandtl:.2f}              (ref: 7.0)")
    print(f"  α   = {p20.thermal_diffusivity*1e7:.4f} ×10⁻⁷ m²/s")
    print(f"  ν   = {p20.kinematic_viscosity*1e6:.4f} ×10⁻⁶ m²/s")

    plt.show()
