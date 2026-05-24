"""Post-process a parametric heat sink by subtracting a cross-shaped (+) pocket.

The baseline heat sink is generated in-memory by calling :func:`build_heat_sink`
from :mod:`CAD_heatSink`.  A cross-shaped volume is then subtracted from the top
of the fin array.  The cross is:

* Composed of two rectangular arms of equal length and width that share the
  same centre.
* Rotated 45 ° about the vertical (Z) axis relative to the fin direction.
* Positioned so that its top face is flush with the top of the fins and its
  centre coincides with the centroid of the fin-array bounding box in XY.

The resulting solid is written to ``data/CAD_generated/heat_sink_cross.step``.

Coordinate system  (same as CAD_heatSink.py)
----------------------------------------------
* x — channel / extrusion direction  (length = channel_length)
* y — fin-array direction             (width  = fin_number * fin_thickness
                                               + (fin_number - 1) * fin_spacing)
* z — height                          (total  = base_height + fin_height)

Cross pocket geometry (local frame before rotation/translation)
---------------------------------------------------------------
::

       ← cross_length →
    ┌──────────────────┐    ─┐
    │      arm 2 (Y)   │     │ cross_width
    └─────────┬────────┘    ─┘
              │  cross_width
    ┌─────────┴────────┐
    │      arm 1 (X)   │
    └──────────────────┘

    (then union, rotate 45 ° about Z, translate to centre above fins)

Usage
-----
As a library::

    from examples.case.heat_sink_example_V2.CAD_heatSink_cross_pocket import (
        build_heat_sink_with_cross,
    )
    step_text = build_heat_sink_with_cross(fin_number=8, cross_depth=5.0)

As a script (saves to data/CAD_generated/)::

    conda run -n auto_eval_manuf \\
        python examples/case/heat_sink_example_V2/CAD_heatSink_cross_pocket.py
"""

from __future__ import annotations

import math
import sys
import tempfile
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Repo root on sys.path
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from examples.case.heat_sink_example_V2.CAD_heatSink import build_heat_sink

from OCC.Core.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCC.Core.IFSelect import IFSelect_RetDone
from OCC.Core.STEPControl import STEPControl_AsIs, STEPControl_Reader, STEPControl_Writer
from OCC.Core.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec

# ---------------------------------------------------------------------------
# Default output location
# ---------------------------------------------------------------------------
_DEFAULT_DEST = ROOT / "data" / "CAD_generated"
_DEFAULT_OUTPUT = "heat_sink_cross.step"


# ===========================================================================
# Internal helpers
# ===========================================================================

def _step_string_to_shape(step_text: str):
    """Return an OCC ``TopoDS_Shape`` loaded from a STEP text string.

    The string is written to a temporary file, read by ``STEPControl_Reader``,
    then the temp file is deleted.
    """
    with tempfile.NamedTemporaryFile(
        suffix=".stp", delete=False, mode="w", encoding="utf-8"
    ) as tmp:
        tmp.write(step_text)
        tmp_path = Path(tmp.name)

    try:
        reader = STEPControl_Reader()
        status = reader.ReadFile(str(tmp_path))
        if status != IFSelect_RetDone:
            raise RuntimeError(f"STEPControl_Reader failed (status={status})")
        reader.TransferRoots()
        shape = reader.OneShape()
    finally:
        tmp_path.unlink(missing_ok=True)

    return shape


def _build_cross_pocket(
    cross_length: float,
    cross_width: float,
    cross_depth: float,
    center_x: float,
    center_y: float,
    top_z: float,
):
    """Build the cross-shaped cutting solid.

    Construction sequence
    ---------------------
    1. Arm 1 — long axis along **X**, centred at the local origin:
       corner at ``(-cross_length/2, -cross_width/2, -cross_depth)``,
       size   ``cross_length × cross_width × cross_depth``.
       *(Top face is at z = 0 in local space.)*

    2. Arm 2 — long axis along **Y**, centred at the local origin:
       corner at ``(-cross_width/2, -cross_length/2, -cross_depth)``,
       size   ``cross_width × cross_length × cross_depth``.

    3. **Fuse** the two arms to form the cross.

    4. **Rotate** 45 ° about the Z-axis at the local origin.

    5. **Translate** to ``(center_x, center_y, top_z)`` so that:
       * the cross is centred in XY over the fin array, and
       * its top face is flush with the top of the fins.

    Parameters
    ----------
    cross_length:
        Full length of each arm  [mm].
    cross_width:
        Width of each arm  [mm].
    cross_depth:
        Depth of the pocket cut downward from the fin tops  [mm].
        Values larger than ``fin_height`` will penetrate into the base —
        no clamping is applied.
    center_x, center_y:
        XY coordinates of the centroid of the fin-array bounding box  [mm].
    top_z:
        Z-coordinate of the top face of the fin array = ``base_height + fin_height``  [mm].

    Returns
    -------
    TopoDS_Shape
        Positioned cross solid ready for boolean subtraction.
    """
    # ------------------------------------------------------------------
    # 1 & 2 — build both arms centred at the local origin
    # ------------------------------------------------------------------
    arm1 = BRepPrimAPI_MakeBox(
        gp_Pnt(-cross_length / 2.0, -cross_width / 2.0, -cross_depth),
        cross_length,
        cross_width,
        cross_depth,
    ).Shape()

    arm2 = BRepPrimAPI_MakeBox(
        gp_Pnt(-cross_width / 2.0, -cross_length / 2.0, -cross_depth),
        cross_width,
        cross_length,
        cross_depth,
    ).Shape()

    # ------------------------------------------------------------------
    # 3 — fuse into a single cross solid
    # ------------------------------------------------------------------
    fuse = BRepAlgoAPI_Fuse(arm1, arm2)
    fuse.Build()
    if not fuse.IsDone():
        raise RuntimeError("Boolean fuse of cross arms failed")
    cross = fuse.Shape()

    # ------------------------------------------------------------------
    # 4 — rotate 45 ° about the Z-axis (centred at local origin)
    # ------------------------------------------------------------------
    rot_trsf = gp_Trsf()
    rot_trsf.SetRotation(
        gp_Ax1(gp_Pnt(0.0, 0.0, 0.0), gp_Dir(0.0, 0.0, 1.0)),
        math.pi / 4.0,          # 45 °
    )
    cross = BRepBuilderAPI_Transform(cross, rot_trsf, True).Shape()

    # ------------------------------------------------------------------
    # 5 — translate to the fin-array centre, top face flush with fin tops
    # ------------------------------------------------------------------
    trans_trsf = gp_Trsf()
    trans_trsf.SetTranslation(gp_Vec(center_x, center_y, top_z))
    cross = BRepBuilderAPI_Transform(cross, trans_trsf, True).Shape()

    return cross


# ===========================================================================
# Public API
# ===========================================================================

def build_heat_sink_with_cross(
    # ------------------------------------------------------------------ #
    # Heat-sink geometry — forwarded verbatim to build_heat_sink()        #
    # ------------------------------------------------------------------ #
    fin_height: float = 20.0,
    fin_thickness: float = 2.0,
    fin_spacing: float = 5.0,
    base_height: float = 5.0,
    fin_number: int = 6,
    channel_length: float = 50.0,
    # ------------------------------------------------------------------ #
    # Cross-pocket geometry                                               #
    # ------------------------------------------------------------------ #
    cross_length: float = 20.0,
    cross_width: float = 3.0,
    cross_depth: float = 3.0,
    # ------------------------------------------------------------------ #
    # Output control                                                      #
    # ------------------------------------------------------------------ #
    save: bool = True,
    output_step: str = _DEFAULT_OUTPUT,
    dest_folder: Optional[Path | str] = None,
) -> str:
    """Build a parametric heat sink with a cross-shaped pocket cut from the fin tops.

    The function calls :func:`build_heat_sink` in-memory (no disk I/O for the
    baseline geometry) and returns the STEP content of the modified solid as a
    string.  Use ``save=True`` (the default) to also write the result to disk.

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
    cross_length:
        Full length of each arm of the cross pocket  [mm].
    cross_width:
        Width of each arm of the cross pocket  [mm].
    cross_depth:
        Depth of the pocket measured downward from the fin tops  [mm].
        If this value exceeds ``fin_height`` the cut continues into the
        base — no clamping is applied.
    save:
        Write the STEP file to disk when ``True`` (default).
    output_step:
        File name (*not* path) of the exported STEP file.
    dest_folder:
        Destination directory.  Defaults to ``<repo_root>/data/CAD_generated``.

    Returns
    -------
    str
        Full STEP file content of the heat sink with the cross pocket applied.

    Raises
    ------
    RuntimeError
        If either the STEP round-trip or the boolean cut fails.
    """
    # ------------------------------------------------------------------
    # 1. Generate the baseline heat sink (in-memory STEP string)
    # ------------------------------------------------------------------
    print("Building baseline heat sink …")
    step_text = build_heat_sink(
        fin_height=fin_height,
        fin_thickness=fin_thickness,
        fin_spacing=fin_spacing,
        base_height=base_height,
        fin_number=fin_number,
        channel_length=channel_length,
        save=False,
    )

    # ------------------------------------------------------------------
    # 2. Reload the STEP string as an OCC shape
    # ------------------------------------------------------------------
    print("Parsing baseline STEP …")
    heat_sink_shape = _step_string_to_shape(step_text)

    # ------------------------------------------------------------------
    # 3. Compute cross-pocket position from the same parameters
    # ------------------------------------------------------------------
    total_width  = fin_number * fin_thickness + (fin_number - 1) * fin_spacing
    total_height = base_height + fin_height

    center_x = channel_length / 2.0
    center_y = total_width    / 2.0

    print(
        f"Cross pocket: length={cross_length} mm, width={cross_width} mm, "
        f"depth={cross_depth} mm  (centred at x={center_x:.2f}, y={center_y:.2f}, "
        f"top z={total_height:.2f} mm, rotated 45°)"
    )

    # ------------------------------------------------------------------
    # 4. Build the cross cutting solid
    # ------------------------------------------------------------------
    cross_solid = _build_cross_pocket(
        cross_length=cross_length,
        cross_width=cross_width,
        cross_depth=cross_depth,
        center_x=center_x,
        center_y=center_y,
        top_z=total_height,
    )

    # ------------------------------------------------------------------
    # 5. Boolean cut: heat_sink − cross
    # ------------------------------------------------------------------
    print("Performing boolean cut …")
    cut = BRepAlgoAPI_Cut(heat_sink_shape, cross_solid)
    cut.Build()
    if not cut.IsDone():
        raise RuntimeError("BRepAlgoAPI_Cut failed — check input geometry")
    result_shape = cut.Shape()

    # ------------------------------------------------------------------
    # 6. Write the modified solid to STEP (via temp file)
    # ------------------------------------------------------------------
    with tempfile.NamedTemporaryFile(suffix=".stp", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    writer = STEPControl_Writer()
    writer.Transfer(result_shape, STEPControl_AsIs)
    status = writer.Write(str(tmp_path))
    if status != IFSelect_RetDone:
        tmp_path.unlink(missing_ok=True)
        raise RuntimeError("STEPControl_Writer failed")

    result_text = tmp_path.read_text(encoding="utf-8")
    tmp_path.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # 7. Optionally persist to disk
    # ------------------------------------------------------------------
    if save:
        dest = Path(dest_folder) if dest_folder is not None else _DEFAULT_DEST
        dest.mkdir(parents=True, exist_ok=True)
        out_path = dest / output_step
        out_path.write_text(result_text, encoding="utf-8")
        print(f"STEP written → {out_path}")

    return result_text


# ===========================================================================
# Script entry-point
# ===========================================================================
if __name__ == "__main__":
    build_heat_sink_with_cross(
        # Heat-sink geometry
        fin_height=4.0,
        fin_thickness=0.1,
        fin_spacing=0.1,
        base_height=3.0,
        fin_number=int((50)/(0.1+0.1)),
        channel_length=50.0,
        # Cross-pocket geometry
        cross_length=30.0,
        cross_width=3.0,
        cross_depth=3.0,
        # Output
        save=True,
        output_step="heat_sink_cross.step",
        dest_folder=None,           # → data/CAD_generated/
    )
