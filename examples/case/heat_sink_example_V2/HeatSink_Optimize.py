"""Combined CAD + FEA model for the fin-array heat sink, with optimization example.

The geometry is generated in memory by CAD_heatSink and passed directly to
FEA_HeatSink — no intermediate STEP file is written unless explicitly requested.

Usage
-----
As a library::

    from examples.case.heat_sink_example_V2.HeatSink_Optimize import HeatSinkModel

    model   = HeatSinkModel(fin_number=8, flow_velocity=1.5)
    results = model()               # run CAD + FEA in-memory
    results = model(plot=True)      # same + interactive 3D plot
    model.save_step()               # optionally write STEP to disk

As a script (runs the built-in scipy optimisation example)::

    conda run -n auto_eval_manuf python examples/case/heat_sink_example/HeatSink_Optimize.py
"""

from __future__ import annotations

import sys
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from examples.case.heat_sink_example_V2.CAD_heatSink import build_heat_sink
from examples.case.heat_sink_example_V2.FEA_HeatSink import HeatSinkFEA, HeatSinkResults
from physics.convection_rectangular_channel import RectangularChannelConvection
from physics.heatTransfer_contact_pressure import ContactConductance, ContactSurface

# Default aluminium surface in mm units (k [W/(mm·K)], σ [mm], H_c [N/mm²])
_DEFAULT_AL_SURFACE_MM = ContactSurface(
    thermal_conductivity=0.200,   # W/(mm·K)
    roughness_rms=1.6e-3,         # 1.6 μm in mm
    asperity_slope_rms=0.12,
    microhardness=1000.0,         # 1 GPa in N/mm²
)


class HeatSinkModel:
    """Combined CAD + FEA model for the fin-array heat sink.

    All CAD geometry parameters and FEA boundary-condition parameters are
    exposed as constructor arguments.  Calling the object runs the full
    pipeline and returns a ``HeatSinkResults`` dataclass.

    CAD parameters
    --------------
    fin_height : float      Height of each fin above the base plate [mm].
    fin_thickness : float   Thickness of one fin [mm].
    fin_spacing : float     Clear gap between fins (channel width) [mm].
    base_height : float     Thickness of the base plate [mm].
    fin_number : int        Number of fins.
    channel_length : float  Length in the flow direction [mm].

    FEA / thermal parameters
    ------------------------
    mech_load_pressure : float       Surface pressure on fin tops [N/mm²].
    T_ambient : float                Ambient temperature [K].
    T_base_hot : float               Hot-side base temperature [K].
    mesh_size : float                Target element edge length [mm].
    coord_tol : float                Surface node selection tolerance [mm].

    Flow / convection parameters (fin channels)
    --------------------------------------------
    flow_velocity : float
        Mean coolant velocity in the fin channels [m/s].
    fluid_density : float
        Coolant density [kg/m³].  Default: water at 20 °C.
    fluid_viscosity : float
        Dynamic viscosity [Pa·s].  Default: water at 20 °C.
    fluid_conductivity : float
        Thermal conductivity [W/(m·K)].  Default: water at 20 °C.
    fluid_specific_heat : float
        Specific heat at constant pressure [J/(kg·K)].  Default: water at 20 °C.

    The convection coefficient h(x) is computed via
    ``RectangularChannelConvection`` and varies along the channel length,
    capturing entry-region enhancement near the inlet.

    Contact conductance parameters (base interface)
    ------------------------------------------------
    base_surface_a, base_surface_b : ContactSurface
        Surface properties of the two mating faces at the heat-sink base.
        Defaults to a ground aluminium–aluminium interface in mm units.
    base_gap_fluid_conductivity : float
        Interstitial gas conductivity [W/(mm·K)].  Default: air ≈ 2.6e-5.
    base_gas_parameter : float
        Gas rarefaction parameter M [mm].  Default: air at 1 atm ≈ 4e-4 mm.
    base_paste_conductivity : float | None
        Thermal paste conductivity [W/(mm·K)].  None = bare gas gap.
    base_paste_thickness : float | None
        Explicit bond-line thickness [mm].  None = use computed mean gap.
    """

    def __init__(
        self,
        # --- CAD ---
        fin_height: float = 20.0,
        fin_thickness: float = 2.0,
        fin_spacing: float = 5.0,
        base_height: float = 5.0,
        fin_number: int = 6,
        channel_length: float = 50.0,
        # --- FEA ---
        mech_load_pressure: float = -1.0,
        T_ambient: float = 300.0,
        T_base_hot: float = 350.0,
        mesh_size: float = 3.0,
        coord_tol: float = 0.5,
        # --- Flow / convection (water at 20 °C defaults) ---
        flow_velocity: float = 1.0,            # m/s
        fluid_density: float = 998.2,          # kg/m³
        fluid_viscosity: float = 1.002e-3,     # Pa·s
        fluid_conductivity: float = 0.598,     # W/(m·K)
        fluid_specific_heat: float = 4182.0,   # J/(kg·K)
        # --- Contact conductance at base ---
        base_surface_a: ContactSurface = _DEFAULT_AL_SURFACE_MM,
        base_surface_b: ContactSurface = _DEFAULT_AL_SURFACE_MM,
        base_gap_fluid_conductivity: float = 2.6e-5,   # air [W/(mm·K)]
        base_gas_parameter: float = 4e-4,              # air at 1 atm [mm]
        base_paste_conductivity: Optional[float] = None,
        base_paste_thickness: Optional[float] = None,
    ) -> None:
        self.fin_height = fin_height
        self.fin_thickness = fin_thickness
        self.fin_spacing = fin_spacing
        self.base_height = base_height
        self.fin_number = fin_number
        self.channel_length = channel_length

        self.mech_load_pressure = mech_load_pressure
        self.T_ambient = T_ambient
        self.T_base_hot = T_base_hot
        self.mesh_size = mesh_size
        self.coord_tol = coord_tol

        self.flow_velocity = flow_velocity
        self.fluid_density = fluid_density
        self.fluid_viscosity = fluid_viscosity
        self.fluid_conductivity = fluid_conductivity
        self.fluid_specific_heat = fluid_specific_heat

        self._contact_model = ContactConductance(
            surface_a=base_surface_a,
            surface_b=base_surface_b,
            gap_fluid_conductivity=base_gap_fluid_conductivity,
            gas_parameter=base_gas_parameter,
            paste_conductivity=base_paste_conductivity,
            paste_thickness=base_paste_thickness,
        )

    def __call__(self, plot: bool = False) -> HeatSinkResults:
        """Generate geometry in-memory and run FEA.

        Parameters
        ----------
        plot : bool
            Open an interactive 3D plot after solving.
        """
        contact_pressure = abs(self.mech_load_pressure)
        h_conv_base = self._contact_model(contact_pressure).h_total
        print(
            f"Contact conductance at {contact_pressure:.3g} N/mm²: "
            f"h_conv_base = {h_conv_base:.4g} W/(mm²·K)"
        )

        # Compute h(x) profile along the fin channel [SI → mm unit conversion]
        # channel_height = fin_height, channel_width = fin_spacing (both in mm → m)
        conv = RectangularChannelConvection(
            channel_height=self.fin_height  * 1e-3,   # mm → m
            channel_width=self.fin_spacing  * 1e-3,   # mm → m
            channel_length=self.channel_length * 1e-3, # mm → m
            velocity=self.flow_velocity,
            density=self.fluid_density,
            dynamic_viscosity=self.fluid_viscosity,
            thermal_conductivity=self.fluid_conductivity,
            specific_heat=self.fluid_specific_heat,
        )()
        x_mm   = conv.x_field * 1e3          # m → mm
        h_mm2k = conv.h_field * 1e-6         # W/(m²·K) → W/(mm²·K)
        h_conv_fins = lambda x: np.interp(x, x_mm, h_mm2k)
        print(
            f"Fin convection: Re={conv.Re:.0f} ({conv.flow_regime}), "
            f"h_avg={conv.h_avg * 1e-6:.4g} W/(mm²·K)"
        )

        print("Generating CAD geometry …")
        step_text = build_heat_sink(
            fin_height=self.fin_height,
            fin_thickness=self.fin_thickness,
            fin_spacing=self.fin_spacing,
            base_height=self.base_height,
            fin_number=self.fin_number,
            channel_length=self.channel_length,
        )

        fea = HeatSinkFEA(
            mech_load_pressure=self.mech_load_pressure,
            h_conv_fins=h_conv_fins,
            h_conv_base=h_conv_base,
            T_ambient=self.T_ambient,
            T_base_hot=self.T_base_hot,
            fin_height=self.fin_height,
            base_height=self.base_height,
            mesh_size=self.mesh_size,
            coord_tol=self.coord_tol,
            step_content=step_text,
        )
        return fea(plot=plot)

    def save_step(
        self,
        output_step: str = "heat_sink.step",
        dest_folder: Optional[Path | str] = None,
    ) -> None:
        """Write the current geometry to a STEP file."""
        build_heat_sink(
            fin_height=self.fin_height,
            fin_thickness=self.fin_thickness,
            fin_spacing=self.fin_spacing,
            base_height=self.base_height,
            fin_number=self.fin_number,
            channel_length=self.channel_length,
            save=True,
            output_step=output_step,
            dest_folder=dest_folder,
        )


# ---------------------------------------------------------------------------
# Multi-objective optimisation: heat transfer vs. mechanical stress
# ---------------------------------------------------------------------------

@dataclass
class DesignPoint:
    """Single evaluated design in the (mech_load_pressure, fin_thickness) space."""
    mech_load_pressure: float   # N/mm²  (negative = compressive)
    fin_thickness:      float   # mm
    delta_T:            float   # K    = T_max − T_ambient
    max_stress:         float   # N/mm² = peak von Mises stress


def _evaluate(
    mech_load_pressure: float,
    fin_thickness: float,
    fixed: dict,
) -> DesignPoint | None:
    """Run one FEA evaluation. Returns None on failure."""
    try:
        model = HeatSinkModel(
            mech_load_pressure=mech_load_pressure,
            fin_thickness=fin_thickness,
            **fixed,
        )
        r = model()
        return DesignPoint(
            mech_load_pressure=mech_load_pressure,
            fin_thickness=fin_thickness,
            delta_T=r.delta_T,
            max_stress=r.max_stress,
        )
    except Exception as exc:
        warnings.warn(
            f"Evaluation failed (p={mech_load_pressure:.3g} N/mm², "
            f"t={fin_thickness:.2f} mm): {exc}"
        )
        return None


def _pareto_front(points: list[DesignPoint]) -> list[DesignPoint]:
    """Return the non-dominated subset, sorted by delta_T ascending."""
    front = []
    for candidate in points:
        dominated = any(
            other.delta_T    <= candidate.delta_T
            and other.max_stress <= candidate.max_stress
            and (other.delta_T < candidate.delta_T or other.max_stress < candidate.max_stress)
            for other in points
        )
        if not dominated:
            front.append(candidate)
    return sorted(front, key=lambda p: p.delta_T)


def _plot_pareto(
    all_points: list[DesignPoint],
    pareto: list[DesignPoint],
    best: DesignPoint,
) -> None:
    import matplotlib
    matplotlib.use("TkAgg")
    import matplotlib.pyplot as plt

    fig, (ax_obj, ax_des) = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle(
        "Multi-objective optimisation — heat transfer vs. mechanical stress",
        fontsize=13,
    )

    # --- objective space ---
    ax_obj.scatter(
        [p.max_stress for p in all_points],
        [p.delta_T    for p in all_points],
        c="lightgrey", edgecolors="grey", s=40, zorder=2, label="Evaluated",
    )
    ax_obj.plot(
        [p.max_stress for p in pareto],
        [p.delta_T    for p in pareto],
        "o-", color="steelblue", lw=2, ms=8, zorder=3, label="Pareto front",
    )
    ax_obj.scatter(
        [best.max_stress], [best.delta_T],
        marker="*", s=250, color="tomato", zorder=4, label="Best compromise",
    )
    ax_obj.set_xlabel("Max von Mises stress  σ  [N/mm²]")
    ax_obj.set_ylabel("Temperature rise  ΔT  [K]")
    ax_obj.set_title("Objective space")
    ax_obj.legend()
    ax_obj.grid(True, alpha=0.3)

    # --- design space ---
    sc = ax_des.scatter(
        [p.fin_thickness            for p in all_points],
        [abs(p.mech_load_pressure)  for p in all_points],
        c=[p.delta_T for p in all_points],
        cmap="coolwarm_r", s=60, edgecolors="grey", zorder=2,
    )
    ax_des.scatter(
        [p.fin_thickness           for p in pareto],
        [abs(p.mech_load_pressure) for p in pareto],
        s=100, facecolors="none", edgecolors="steelblue",
        lw=2, zorder=3, label="Pareto front",
    )
    ax_des.scatter(
        [best.fin_thickness], [abs(best.mech_load_pressure)],
        marker="*", s=250, color="tomato", zorder=4, label="Best compromise",
    )
    plt.colorbar(sc, ax=ax_des, label="ΔT  [K]")
    ax_des.set_xlabel("Fin thickness  [mm]")
    ax_des.set_ylabel("|Load pressure|  [N/mm²]")
    ax_des.set_title("Design space  (colour = ΔT)")
    ax_des.legend()
    ax_des.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.show()


def run_optimisation() -> None:
    """Multi-objective Pareto optimisation: minimise ΔT and max von Mises stress.

    Design variables
    ----------------
    mech_load_pressure ∈ [−5.0, −0.5] N/mm²   (compressive, always negative)
    fin_thickness      ∈ [  1.0,  4.0] mm

    Objectives
    ----------
    f₁ = ΔT     = T_max − T_ambient  [K]      minimise → maximise heat transfer
    f₂ = σ_max  = peak von Mises stress [N/mm²]  minimise → reduce structural risk

    Method
    ------
    Weighted-sum scalarisation  f = w·(ΔT/ΔT₀) + (1−w)·(σ/σ₀)  for seven
    evenly-spaced weights w ∈ [0, 1].  Each sub-problem is solved with
    Nelder-Mead (warm-started from the previous solution).  All evaluated
    points are pooled and Pareto-filtered at the end.  The best compromise is
    the Pareto point closest to the normalised utopia point (origin).
    """
    from scipy.optimize import minimize
    from physics.material_properties.water import water as _water

    w20 = _water(20.0, unit="C")

    # Fixed geometry / flow / thermal parameters
    fixed = dict(
        fin_height=20.0,
        fin_spacing=5.0,
        base_height=5.0,
        fin_number=6,
        channel_length=50.0,
        T_ambient=293.15,                       # 20 °C
        T_base_hot=353.15,                      # 80 °C
        mesh_size=4.0,                          # coarser for speed
        flow_velocity=0.5,                      # m/s — water coolant
        fluid_density=w20.density,
        fluid_viscosity=w20.dynamic_viscosity,
        fluid_conductivity=w20.thermal_conductivity,
        fluid_specific_heat=w20.specific_heat,
    )

    P_MIN, P_MAX = 0.5, 5.0   # |pressure| bounds [N/mm²]
    T_MIN, T_MAX = 1.0, 4.0   # fin_thickness bounds [mm]

    print("=" * 60)
    print("Multi-objective optimisation")
    print(f"  x[0] = mech_load_pressure  ∈ [−{P_MAX}, −{P_MIN}] N/mm²")
    print(f"  x[1] = fin_thickness       ∈ [ {T_MIN},  {T_MAX}] mm")
    print("  f[0] = ΔT      (minimise) — maximise heat transfer")
    print("  f[1] = σ_max   (minimise) — minimise mechanical stress")
    print("=" * 60)

    # Reference evaluation for objective normalisation
    print("\n[ref] p = −1.0 N/mm²   t = 2.0 mm …")
    ref = _evaluate(-1.0, 2.0, fixed)
    if ref is None:
        raise RuntimeError("Reference evaluation failed; cannot proceed.")
    dT_ref = ref.delta_T
    s_ref  = ref.max_stress
    print(f"      ΔT₀ = {dT_ref:.2f} K   σ₀ = {s_ref:.4f} N/mm²\n")

    all_points: list[DesignPoint] = [ref]

    # Weighted-sum Pareto sweep
    weights = np.linspace(0.0, 1.0, 7)    # weight on ΔT objective
    x0 = np.array([1.0, 2.0])             # [|p|, fin_thickness]

    for i, w_T in enumerate(weights):
        w_s = 1.0 - w_T
        print(f"[{i + 1}/{len(weights)}] w_ΔT = {w_T:.2f}   w_σ = {w_s:.2f}")

        def _obj(x, w_T=w_T, w_s=w_s):
            p_mag = float(np.clip(x[0], P_MIN, P_MAX))
            t     = float(np.clip(x[1], T_MIN, T_MAX))
            pt = _evaluate(-p_mag, t, fixed)
            if pt is None:
                return 1e6
            all_points.append(pt)
            val = w_T * pt.delta_T / dT_ref + w_s * pt.max_stress / s_ref
            print(
                f"    p = {pt.mech_load_pressure:+.2f} N/mm²  "
                f"t = {pt.fin_thickness:.2f} mm  →  "
                f"ΔT = {pt.delta_T:.2f} K   σ = {pt.max_stress:.4f} N/mm²   f = {val:.4f}"
            )
            return val

        res = minimize(
            _obj, x0, method="Nelder-Mead",
            options={"maxiter": 25, "xatol": 0.1, "fatol": 0.02, "disp": False},
        )
        x0 = res.x   # warm-start next weight from current solution

    print(f"\nTotal evaluations : {len(all_points)}")

    # Pareto filtering
    pareto = _pareto_front(all_points)
    print(f"Pareto-optimal    : {len(pareto)}\n")

    # Best compromise: shortest normalised distance from utopia point (origin)
    best = min(
        pareto,
        key=lambda p: np.hypot(p.delta_T / dT_ref, p.max_stress / s_ref),
    )

    print(f"{'p [N/mm²]':>12}  {'t [mm]':>8}  {'ΔT [K]':>9}  {'σ [N/mm²]':>12}  {'':}")
    print("-" * 55)
    for pt in pareto:
        marker = " ← best compromise" if pt is best else ""
        print(
            f"{pt.mech_load_pressure:>12.3f}  {pt.fin_thickness:>8.2f}"
            f"  {pt.delta_T:>9.2f}  {pt.max_stress:>12.4f}{marker}"
        )

    _plot_pareto(all_points, pareto, best)

    # Full-mesh re-run of best compromise design
    print("\nRe-running best compromise with full mesh …")
    model = HeatSinkModel(
        mech_load_pressure=best.mech_load_pressure,
        fin_thickness=best.fin_thickness,
        **{k: v for k, v in fixed.items() if k != "mesh_size"},
    )
    model(plot=True)


if __name__ == "__main__":
    run_optimisation()
