"""Combined CAD + FEA model for the fin-array heat sink, with optimization example.

The geometry is generated in memory by CAD_heatSink and passed directly to
FEA_HeatSink — no intermediate STEP file is written unless explicitly requested.

Usage
-----
As a library::

    from examples.case.heat_sink_example.HeatSink_Optimize import HeatSinkModel

    model   = HeatSinkModel(fin_number=8, h_conv_fins=1e-4)
    results = model()               # run CAD + FEA in-memory
    results = model(plot=True)      # same + interactive 3D plot
    model.save_step()               # optionally write STEP to disk

As a script (runs the built-in scipy optimisation example)::

    conda run -n auto_eval_manuf python examples/case/heat_sink_example/HeatSink_Optimize.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from examples.case.heat_sink_example.CAD_heatSink import (
    build_heat_sink_step_text,
    generate_heat_sink,
)
from examples.case.heat_sink_example.FEA_HeatSink import HeatSinkFEA, HeatSinkResults


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

    FEA parameters
    --------------
    mech_load_pressure : float   Surface pressure on fin tops [N/mm²].
    h_conv_fins : float          Convection coeff on fin surfaces [W/(mm²·K)].
    h_conv_base : float          Convection coeff on base [W/(mm²·K)].
    T_ambient : float            Ambient temperature [K].
    T_base_hot : float           Hot-side base temperature [K].
    mesh_size : float            Target element edge length [mm].
    coord_tol : float            Surface node selection tolerance [mm].
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
        h_conv_fins: float = 5.0e-5,
        h_conv_base: float = 1.0e-4,
        T_ambient: float = 300.0,
        T_base_hot: float = 350.0,
        mesh_size: float = 3.0,
        coord_tol: float = 0.5,
    ) -> None:
        self.fin_height = fin_height
        self.fin_thickness = fin_thickness
        self.fin_spacing = fin_spacing
        self.base_height = base_height
        self.fin_number = fin_number
        self.channel_length = channel_length

        self.mech_load_pressure = mech_load_pressure
        self.h_conv_fins = h_conv_fins
        self.h_conv_base = h_conv_base
        self.T_ambient = T_ambient
        self.T_base_hot = T_base_hot
        self.mesh_size = mesh_size
        self.coord_tol = coord_tol

    def __call__(self, plot: bool = False) -> HeatSinkResults:
        """Generate geometry in-memory and run FEA.

        Parameters
        ----------
        plot : bool
            Open an interactive 3D plot after solving.
        """
        print("Generating CAD geometry …")
        step_text = build_heat_sink_step_text(
            fin_height=self.fin_height,
            fin_thickness=self.fin_thickness,
            fin_spacing=self.fin_spacing,
            base_height=self.base_height,
            fin_number=self.fin_number,
            channel_length=self.channel_length,
        )

        fea = HeatSinkFEA(
            mech_load_pressure=self.mech_load_pressure,
            h_conv_fins=self.h_conv_fins,
            h_conv_base=self.h_conv_base,
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
    ) -> Path:
        """Write the current geometry to a STEP file and return its path."""
        return generate_heat_sink(
            fin_height=self.fin_height,
            fin_thickness=self.fin_thickness,
            fin_spacing=self.fin_spacing,
            base_height=self.base_height,
            fin_number=self.fin_number,
            channel_length=self.channel_length,
            output_step=output_step,
            dest_folder=dest_folder,
        )


# ---------------------------------------------------------------------------
# Optimisation example
# ---------------------------------------------------------------------------

def _objective(x: list[float], fixed: dict) -> float:
    """Scalar objective for scipy: minimise max temperature.

    Design variables (x)
    --------------------
    x[0] : fin_height    [mm]   bounds (10, 40)
    x[1] : fin_spacing   [mm]   bounds (2, 10)
    x[2] : fin_number    int    bounds (4, 12)  — rounded inside
    """
    fin_height  = float(x[0])
    fin_spacing = float(x[1])
    fin_number  = max(2, int(round(x[2])))

    model = HeatSinkModel(
        fin_height=fin_height,
        fin_spacing=fin_spacing,
        fin_number=fin_number,
        **fixed,
    )
    try:
        results = model()
        val = results.max_temperature
    except Exception as exc:
        print(f"  [warn] evaluation failed ({exc}); returning large penalty")
        val = 1e6

    print(
        f"  fin_height={fin_height:.1f}  fin_spacing={fin_spacing:.1f}"
        f"  fin_number={fin_number}  → T_max={val:.2f} K"
    )
    return val


def run_optimisation() -> None:
    """Minimise maximum temperature using scipy Nelder-Mead."""
    from scipy.optimize import minimize

    fixed = dict(
        fin_thickness=2.0,
        base_height=5.0,
        channel_length=50.0,
        mech_load_pressure=-1.0,
        h_conv_fins=5.0e-5,
        h_conv_base=1.0e-4,
        T_ambient=300.0,
        T_base_hot=350.0,
        mesh_size=4.0,      # coarser mesh for faster optimisation iterations
    )

    x0     = [20.0, 5.0, 6.0]
    bounds = [(10.0, 40.0), (2.0, 10.0), (4.0, 12.0)]

    print("=" * 60)
    print("Optimisation: minimise max temperature")
    print("  variables : fin_height, fin_spacing, fin_number")
    print("=" * 60)

    result = minimize(
        _objective,
        x0,
        args=(fixed,),
        method="Nelder-Mead",
        bounds=bounds,
        options={"maxiter": 30, "xatol": 1.0, "fatol": 0.5, "disp": True},
    )

    print("\nOptimisation result:")
    print(f"  fin_height  = {result.x[0]:.2f} mm")
    print(f"  fin_spacing = {result.x[1]:.2f} mm")
    print(f"  fin_number  = {int(round(result.x[2]))}")
    print(f"  T_max       = {result.fun:.2f} K")

    print("\nRe-running optimal design with full mesh + plot …")
    best = HeatSinkModel(
        fin_height=result.x[0],
        fin_spacing=result.x[1],
        fin_number=int(round(result.x[2])),
        **{k: v for k, v in fixed.items() if k != "mesh_size"},
    )
    best(plot=True)


if __name__ == "__main__":
    run_optimisation()
