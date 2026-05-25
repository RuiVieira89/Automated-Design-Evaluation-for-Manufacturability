"""Parametric CAD generation of a fin-array heat sink using the Autodesk Fusion 360 Python API.

Geometry
--------
A base plate with FinNumber rectangular fins extruded upward::

         |<--- ChannelLength --->|
         ___   ___   ___   ___      ↑
        |   | |   | |   | |   |    FinHeight
     ___|   |_|   |_|   |_|   |___
    |_____________________________| ↑ BaseHeight

    |←FinThick→| |←FinSpacing→|

Coordinate system
-----------------
* x — channel / extrusion direction  (length = ChannelLength)
* y — fin-array direction             (width  = FinNumber*FinThickness
                                               + (FinNumber-1)*FinSpacing)
* z — height direction                (total  = BaseHeight + FinHeight)

Boundary condition face identification
--------------------------------------
After the model is created you can select faces for FEA BCs using the
coordinate criteria below. These match the BC_* constants in the companion
``CAD_heatSink.py`` script:

    z ≈ 0                      → BC_MECH_FIXED   (= BC_THERM_BASE)
    z ≈ BaseHeight + FinHeight → BC_MECH_LOAD_TOP
    z ≈ BaseHeight             → BC_THERM_FINS (channel floor)
    y-normal faces             → BC_THERM_FINS (fin side faces)
    x-normal faces             → BC_END_CAP    (adiabatic / symmetry)

How to run
----------
1. Open Autodesk Fusion 360.
2. Go to  Tools → Scripts and Add-Ins → Scripts tab → green "+" button.
3. Select this file (``CAD_heatSink_autodesk.py``).
4. Click Run.

The script creates a new component **"HeatSink"** in the active design with
a single merged solid body (base plate + fins).  A **"FinBasePlane"**
construction plane is added at z = BaseHeight for reference.

To save a STEP file with BC-named faces (matching ``CAD_heatSink.py``)
-----------------------------------------------------------------------
1. Export from Fusion 360: File → Export → STEP (AP 214/242).
2. Pass the exported file path through ``_rename_step_faces()`` in
   ``CAD_heatSink.py``; that function injects the BC face names without
   touching any other STEP entity.

Units
-----
All *parameters* are in **millimetres**. The Fusion 360 API works in
centimetres internally; unit conversion is handled automatically.
"""

from __future__ import annotations

import traceback
from pathlib import Path

try:
    import adsk.core
    import adsk.fusion

    _IN_FUSION = True
except ImportError:
    _IN_FUSION = False

# ===========================================================================
# GEOMETRY PARAMETERS  — edit these values to change the heat sink dimensions
# ===========================================================================
FIN_HEIGHT     = 20.0   # mm — height of each fin above the base plate
FIN_THICKNESS  =  2.0   # mm — thickness of one fin
FIN_SPACING    =  5.0   # mm — clear gap between adjacent fins (channel width)
BASE_HEIGHT    =  5.0   # mm — thickness of the base plate
FIN_NUMBER     =  6     #     — number of fins
CHANNEL_LENGTH = 50.0   # mm — length in the flow direction

# ===========================================================================
# BOUNDARY CONDITION FACE NAMES  (documentation / matching CAD_heatSink.py)
# ===========================================================================
BC_MECH_FIXED    = "mech_fixed_base"   # base bottom — clamped (mech) / heat source (therm)
BC_MECH_LOAD_TOP = "mech_load_top"     # fin tops    — applied load (mech)
BC_THERM_FINS    = "therm_conv_fins"   # fin sides + channel floors — convection (therm)
BC_END_CAP       = "end_cap"           # x-end faces — adiabatic / symmetry (no BC)

# Fusion 360 API uses centimetres; 1 mm = 0.1 cm
_MM: float = 0.1


# ---------------------------------------------------------------------------
# Fusion 360 script entry point
# ---------------------------------------------------------------------------

def run(context) -> None:  # noqa: ANN001
    """Called by Fusion 360 when the script is executed via the Scripts panel."""
    if not _IN_FUSION:
        print("This script must be run inside Autodesk Fusion 360.")
        return

    ui = None
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface

        comp = build_heat_sink(
            fin_height=FIN_HEIGHT,
            fin_thickness=FIN_THICKNESS,
            fin_spacing=FIN_SPACING,
            base_height=BASE_HEIGHT,
            fin_number=FIN_NUMBER,
            channel_length=CHANNEL_LENGTH,
        )

        total_width = (
            FIN_NUMBER * FIN_THICKNESS + (FIN_NUMBER - 1) * FIN_SPACING
        )

        msg = (
            f"Heat sink created in component '{comp.name}'.\n\n"
            f"  Fins        : {FIN_NUMBER}\n"
            f"  Fin height  : {FIN_HEIGHT} mm\n"
            f"  Fin thickness: {FIN_THICKNESS} mm\n"
            f"  Fin spacing : {FIN_SPACING} mm\n"
            f"  Base height : {BASE_HEIGHT} mm\n"
            f"  Length      : {CHANNEL_LENGTH} mm\n"
            f"  Total width : {total_width:.1f} mm\n"
            f"  Total height: {BASE_HEIGHT + FIN_HEIGHT:.1f} mm\n\n"
            "To export with BC-named STEP faces, export to STEP then run\n"
            "_rename_step_faces() from CAD_heatSink.py."
        )
        ui.messageBox(msg)

    except Exception:  # noqa: BLE001
        if ui:
            ui.messageBox("Heat sink script failed:\n" + traceback.format_exc())
        else:
            raise


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_heat_sink(
    fin_height: float = FIN_HEIGHT,
    fin_thickness: float = FIN_THICKNESS,
    fin_spacing: float = FIN_SPACING,
    base_height: float = BASE_HEIGHT,
    fin_number: int = FIN_NUMBER,
    channel_length: float = CHANNEL_LENGTH,
) -> "adsk.fusion.Component":
    """Build a parametric fin-array heat sink in the active Fusion 360 design.

    Creates a new **"HeatSink"** component containing a single merged solid
    (base plate fused with all fins) and a **"FinBasePlane"** construction
    plane at z = *base_height*.

    All length parameters are in **millimetres**.

    Parameters
    ----------
    fin_height:
        Height of each fin above the base plate [mm].
    fin_thickness:
        Thickness of one fin [mm].
    fin_spacing:
        Clear gap between adjacent fins (channel width) [mm].
    base_height:
        Thickness of the base plate [mm].
    fin_number:
        Number of fins.
    channel_length:
        Heat-sink length in the flow direction [mm].

    Returns
    -------
    adsk.fusion.Component
        The newly created "HeatSink" component.

    Raises
    ------
    RuntimeError
        If Fusion 360 modules are not available or no active design is found.
    """
    if not _IN_FUSION:
        raise RuntimeError(
            "Autodesk Fusion 360 Python modules (adsk.*) are not importable. "
            "Run this script from within Fusion 360."
        )

    # Convert mm → cm (Fusion 360 internal unit) -------------------------
    fh = fin_height     * _MM
    ft = fin_thickness  * _MM
    fs = fin_spacing    * _MM
    bh = base_height    * _MM
    cl = channel_length * _MM
    total_width = fin_number * ft + (fin_number - 1) * fs  # cm

    app = adsk.core.Application.get()
    design: adsk.fusion.Design = app.activeProduct
    if not isinstance(design, adsk.fusion.Design):
        raise RuntimeError("Active Fusion product is not a Design.")

    root = design.rootComponent

    # New sub-component for the heat sink ----------------------------------
    occ = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
    comp: adsk.fusion.Component = occ.component
    comp.name = "HeatSink"

    sketches  = comp.sketches
    extrudes  = comp.features.extrudeFeatures
    xy_plane  = comp.xYConstructionPlane

    # ------------------------------------------------------------------
    # 1. Base plate
    #    Sketch on XY, rectangle (0,0)→(cl, total_width), extrude by bh
    # ------------------------------------------------------------------
    base_sk = sketches.add(xy_plane)
    base_sk.name = "BaseSketch"
    base_sk.sketchCurves.sketchLines.addTwoPointRectangle(
        adsk.core.Point3D.create(0.0, 0.0, 0.0),
        adsk.core.Point3D.create(cl, total_width, 0.0),
    )

    base_profile = base_sk.profiles.item(0)
    base_in = extrudes.createInput(
        base_profile, adsk.fusion.FeatureOperations.NewBodyFeatureOperation
    )
    base_in.setDistanceExtent(False, adsk.core.ValueInput.createByReal(bh))
    base_ext = extrudes.add(base_in)
    base_body = base_ext.bodies.item(0)
    base_body.name = "HeatSink"   # will absorb the fins via Join below

    # ------------------------------------------------------------------
    # 2. Construction plane at z = base_height  (fin root level)
    # ------------------------------------------------------------------
    planes    = comp.constructionPlanes
    plane_in  = planes.createInput()
    plane_in.setByOffset(xy_plane, adsk.core.ValueInput.createByReal(bh))
    fin_plane = planes.add(plane_in)
    fin_plane.name = "FinBasePlane"

    # ------------------------------------------------------------------
    # 3. Fins
    #    Sketch on FinBasePlane; one rectangle per fin; single extrusion.
    #    JoinFeatureOperation fuses all fins into the base body.
    # ------------------------------------------------------------------
    fin_sk = sketches.add(fin_plane)
    fin_sk.name = "FinSketch"

    for i in range(fin_number):
        y0 = i * (ft + fs)
        fin_sk.sketchCurves.sketchLines.addTwoPointRectangle(
            adsk.core.Point3D.create(0.0, y0, 0.0),
            adsk.core.Point3D.create(cl, y0 + ft, 0.0),
        )

    actual_profiles = fin_sk.profiles.count
    if actual_profiles != fin_number:
        raise RuntimeError(
            f"Expected {fin_number} fin profile(s) in FinSketch but found "
            f"{actual_profiles}. Verify that fins are non-overlapping."
        )

    # Collect every fin profile into one ObjectCollection
    profile_col = adsk.core.ObjectCollection.create()
    for j in range(fin_sk.profiles.count):
        profile_col.add(fin_sk.profiles.item(j))

    fin_in = extrudes.createInput(
        profile_col, adsk.fusion.FeatureOperations.JoinFeatureOperation
    )
    fin_in.setDistanceExtent(False, adsk.core.ValueInput.createByReal(fh))
    extrudes.add(fin_in)

    return comp


# ---------------------------------------------------------------------------
# Optional STEP export (requires an active Fusion 360 design)
# ---------------------------------------------------------------------------

def export_to_step(output_path: "Path | str") -> Path:
    """Export the active Fusion 360 design to a STEP file.

    Call this *after* ``build_heat_sink()`` to persist the geometry.
    The exported STEP file will not yet contain BC face names; pipe it through
    ``_rename_step_faces()`` in ``CAD_heatSink.py`` to add them.

    Parameters
    ----------
    output_path:
        Destination file path (``*.step`` or ``*.stp``).

    Returns
    -------
    Path
        Resolved path of the written file.

    Raises
    ------
    RuntimeError
        If the export fails or no active Fusion design is found.
    """
    if not _IN_FUSION:
        raise RuntimeError("Fusion 360 modules are not available.")

    out = Path(output_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    app    = adsk.core.Application.get()
    design = app.activeProduct
    if not isinstance(design, adsk.fusion.Design):
        raise RuntimeError("Active product is not a Fusion 360 Design.")

    export_mgr   = design.exportManager
    step_options = export_mgr.createSTEPExportOptions(str(out))
    success      = export_mgr.execute(step_options)
    if not success:
        raise RuntimeError(f"Fusion 360 STEP export failed → {out}")

    print(f"STEP written → {out}")
    return out


# ---------------------------------------------------------------------------
# Script entry-point guard
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if _IN_FUSION:
        # Executed via Fusion's embedded Python runner
        run({})
    else:
        print(
            "This script is an Autodesk Fusion 360 add-in script.\n"
            "To run it:\n"
            "  1. Open Autodesk Fusion 360.\n"
            "  2. Tools → Scripts and Add-Ins → Scripts → Add (+).\n"
            "  3. Select this file and click Run.\n\n"
            "For a standalone (no-Fusion) STEP file with BC face names, use\n"
            "  CAD_heatSink.py  (requires pythonocc-core / conda env)."
        )
