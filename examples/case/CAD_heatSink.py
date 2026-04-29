"""Parametric CAD generation of a simple fin-array (rib) using pythonocc-core.

Geometry
--------
A base plate with FinNumber rectangular fins extruded upward:

         |<--- ChannelLength --->|
         ___   ___   ___   ___      ↑
        |   | |   | |   | |   |    FinHeight
     ___|   |_|   |_|   |_|   |___
    |_____________________________| ↑ BaseHeight

    |←FinThick→| |←FinSpacing→|

Usage
-----
As a library::

    from examples.case.simple_rib import generate_fin_array
    step_path = generate_fin_array(fin_number=8, output_step="rib_8fins.step")

As a script::

    conda run -n auto_eval_manuf python examples/case/simple_rib.py
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# repo root on sys.path
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from OCC.Core.BRepAlgoAPI import BRepAlgoAPI_Fuse
from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCC.Core.IFSelect import IFSelect_RetDone
from OCC.Core.STEPControl import STEPControl_AsIs, STEPControl_Writer
from OCC.Core.gp import gp_Pnt

# ---------------------------------------------------------------------------
# Default destination folder
# ---------------------------------------------------------------------------
_DEFAULT_DEST = ROOT / "data" / "CAD_generated"


def generate_fin_array(
    fin_height: float = 20.0,
    fin_thickness: float = 2.0,
    fin_spacing: float = 5.0,
    base_height: float = 5.0,
    fin_number: int = 6,
    channel_length: float = 50.0,
    output_step: str = "simple_rib.step",
    output_fcstd: Optional[str] = None,
    dest_folder: Optional[Path | str] = None,
) -> Path:
    """Generate a parametric fin-array (rib) and write it to STEP.

    Parameters
    ----------
    fin_height:
        Height of each fin above the base plate  [mm].
    fin_thickness:
        Thickness of one fin  [mm].
    fin_spacing:
        Clear distance between adjacent fins (channel width)  [mm].
    base_height:
        Thickness of the base plate  [mm].
    fin_number:
        Number of fins.
    channel_length:
        Length of the heat sink in the flow direction  [mm].
    output_step:
        File name (not path) of the exported STEP file.
    output_fcstd:
        File name of an optional FreeCAD .FCStd file.
        Pass ``None`` (default) to skip FreeCAD export.
        Requires FreeCAD to be installed and importable.
    dest_folder:
        Destination directory.  Defaults to ``<repo_root>/data/CAD_generated``.
        Created automatically if it does not exist.

    Returns
    -------
    Path
        Absolute path of the written STEP file.
    """
    dest = Path(dest_folder) if dest_folder is not None else _DEFAULT_DEST
    dest.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Geometry
    # Coordinate system:
    #   x  — channel / extrusion direction (length = channel_length)
    #   y  — fin-spacing direction (width = total_width)
    #   z  — height direction
    # ------------------------------------------------------------------
    total_width = fin_number * fin_thickness + (fin_number - 1) * fin_spacing

    # Base plate: origin at (0, 0, 0)
    base = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, 0.0, 0.0),
        channel_length,
        total_width,
        base_height,
    ).Shape()

    # Fins: stacked along y, sitting on top of the base (z = base_height)
    compound = base
    for i in range(fin_number):
        y0 = i * (fin_thickness + fin_spacing)
        fin = BRepPrimAPI_MakeBox(
            gp_Pnt(0.0, y0, base_height),
            channel_length,
            fin_thickness,
            fin_height,
        ).Shape()
        fuse = BRepAlgoAPI_Fuse(compound, fin)
        fuse.Build()
        compound = fuse.Shape()

    # ------------------------------------------------------------------
    # STEP export
    # ------------------------------------------------------------------
    step_path = dest / output_step
    writer = STEPControl_Writer()
    writer.Transfer(compound, STEPControl_AsIs)
    status = writer.Write(str(step_path))
    if status != IFSelect_RetDone:
        raise RuntimeError(f"STEP write failed for {step_path}")
    print(f"STEP written → {step_path}")

    # ------------------------------------------------------------------
    # FreeCAD .FCStd export (optional)
    # ------------------------------------------------------------------
    if output_fcstd is not None:
        fcstd_path = dest / output_fcstd
        _write_fcstd(step_path, fcstd_path)

    return step_path


def _write_fcstd(step_path: Path, fcstd_path: Path) -> None:
    """Import *step_path* into a FreeCAD document and save as .FCStd."""
    try:
        import FreeCAD  # type: ignore[import]
        import Import   # type: ignore[import]  (FreeCAD STEP import module)
    except ImportError:
        warnings.warn(
            "FreeCAD is not installed — skipping .FCStd export. "
            "Install FreeCAD (https://www.freecad.org) and ensure its "
            "Python modules are on sys.path.",
            stacklevel=3,
        )
        return

    doc_name = fcstd_path.stem
    doc = FreeCAD.newDocument(doc_name)
    Import.insert(str(step_path), doc.Name)
    doc.saveAs(str(fcstd_path))
    FreeCAD.closeDocument(doc.Name)
    print(f"FCStd written → {fcstd_path}")


# ---------------------------------------------------------------------------
# Script entry-point — uses default parameter values
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    generate_fin_array(
        fin_height=20.0,
        fin_thickness=2.0,
        fin_spacing=5.0,
        base_height=5.0,
        fin_number=6,
        channel_length=50.0,
        output_step="simple_rib.step",
        output_fcstd=None,          # set to e.g. "simple_rib.FCStd" to enable
        dest_folder=None,           # defaults to data/CAD_generated/
    )
