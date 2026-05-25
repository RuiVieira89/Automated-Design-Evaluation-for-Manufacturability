"""Production drawing of the cold plate via FreeCAD TechDraw.

Two-mode architecture
---------------------
This single file acts as **two different programs** depending on how it is
invoked:

Mode A — conda Python (normal interpreter)
    ``conda run -n auto_eval_manuf python cold_plate_drawing_freecad.py``

    1. Builds the cold plate with :func:`build_cold_plate`.
    2. Saves it to a temporary STEP file.
    3. Re-invokes itself under ``freecadcmd`` passing the STEP path as
       ``sys.argv[1]``.
    4. Waits for freecadcmd to finish.
    5. Converts the DXF produced by FreeCAD to PDF using ezdxf + matplotlib.
    6. Prints the summary.

Mode B — FreeCAD Python (freecadcmd <this_file> <step_path>)
    ``freecadcmd cold_plate_drawing_freecad.py /tmp/cold_plate_fc.step``

    1. Imports the STEP into a FreeCAD document.
    2. Creates a TechDraw page (A3 landscape, blank template).
    3. Adds four DrawViewPart objects: Front, Top, Right, Isometric.
    4. Adds DrawViewAnnotation objects for all dimensions.
    5. Exports the page to DXF via ``TechDraw.writeDXFPage``.
    6. Exits FreeCAD.

Output files
------------
``data/drawings/cold_plate_freecad.dxf``
``data/drawings/cold_plate_freecad.pdf``

Both paths are relative to the repository root.  The data/drawings/
directory is created automatically.

Dependencies
------------
* Mode A: OCP / PythonOCC (from the ``auto_eval_manuf`` conda env), ezdxf ≥ 1.4
* Mode B: FreeCAD 1.0 or newer (``freecadcmd`` on PATH, or full path below)

Notes
-----
* All dimension text uses :func:`get_default_tolerance` — the value 0.1 is
  **never hardcoded** in dimension strings.
* Third-angle projection layout:
  - Front view  — lower-left quadrant
  - Top view    — above the front view
  - Right view  — to the right of the front view
  - Isometric   — upper-right quadrant

"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Repo root
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# ---------------------------------------------------------------------------
# freecadcmd location — adjust if not on PATH
# ---------------------------------------------------------------------------
_FREECADCMD = os.environ.get(
    "FREECADCMD",
    "/Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd",
)

# ---------------------------------------------------------------------------
# FreeCAD A3 template path
# ---------------------------------------------------------------------------
_FC_TEMPLATE = (
    "/Applications/FreeCAD.app/Contents/Resources/share/Mod/TechDraw"
    "/Templates/A3_Landscape_blank.svg"
)

# ---------------------------------------------------------------------------
# Cold-plate parameters (walled variant — matches occt_ezdxf script)
# ---------------------------------------------------------------------------
CP = dict(
    base_length=100.0,
    base_width=80.0,
    base_height=4.0,
    corner_radius=5.0,
    fin_height=8.0,
    fin_thickness=1.5,
    fin_spacing=2.0,
    fin_number=16,
    channel_length=80.0,
    wall_thickness=3.0,
    wall_height=10.0,
    wall_inset=2.0,
    screw_hole_positions=[
        (-44.0, -34.0), (+44.0, -34.0),
        (+44.0, +34.0), (-44.0, +34.0),
    ],
    screw_hole_diameter=3.5,
    pin_hole_positions=[(0.0, +25.0), (0.0, -25.0)],
    pin_hole_diameter=2.5,
    save=False,
)

# A3 sheet dimensions (mm) — same as occt_ezdxf layout
_SHEET_W = 420.0
_SHEET_H = 297.0

# Page coordinates in FreeCAD TechDraw use (0,0) = bottom-left of sheet,
# +X right, +Y up  (same convention as ezdxf paper space).
# View centres in third-angle layout:
_SCALE = 1.5   # drawing scale

# Front, Top, Right, Iso centre positions (X, Y) on the A3 sheet [mm]
_FRONT_C  = (  80.0,  75.0)
_TOP_C    = (  80.0, 195.0)
_RIGHT_C  = ( 215.0,  75.0)
_ISO_C    = ( 330.0, 195.0)


# ===========================================================================
# Shared dimension helpers (used in both mode-A summary and mode-B annotations)
# ===========================================================================

def _dim_text(value: float, decimals: int = 1) -> str:
    """Format a dimension with tolerance suffix using get_default_tolerance().

    Imports drawing_tolerances lazily so this module can be imported in
    FreeCAD mode (where the conda env is not available) without error — as
    long as drawing_tolerances.py is on sys.path, which it is because we
    added _ROOT and _HERE to sys.path.
    """
    from examples.case.heat_sink_example_V3.drawing_tolerances import (
        get_default_tolerance,
    )
    tol = get_default_tolerance()
    return tol.format_dim(value, decimals=decimals)


def _tol_note() -> str:
    from examples.case.heat_sink_example_V3.drawing_tolerances import (
        get_default_tolerance,
    )
    return get_default_tolerance().format_general_note()


# ===========================================================================
# MODE B — FreeCAD TechDraw script
# ===========================================================================

def _run_freecad_mode(step_path: str, out_dxf: str) -> None:
    """Build TechDraw page, add views + annotations, export DXF.

    This function is executed inside freecadcmd.
    """
    import FreeCAD          # type: ignore  # FreeCAD built-in
    import TechDraw         # type: ignore  # FreeCAD built-in
    import Part             # type: ignore  # FreeCAD built-in

    # ------------------------------------------------------------------
    # 1. Create document & import STEP
    # ------------------------------------------------------------------
    doc = FreeCAD.newDocument("ColdPlateDrawing")
    Part.insert(step_path, doc.Name)
    doc.recompute()

    # Find the imported shape object
    shape_obj = None
    for obj in doc.Objects:
        if hasattr(obj, "Shape") and not obj.Shape.isNull():
            shape_obj = obj
            break

    if shape_obj is None:
        raise RuntimeError(
            f"No shape found after importing STEP: {step_path}"
        )

    # ------------------------------------------------------------------
    # 2. Create TechDraw page with A3 blank template
    # ------------------------------------------------------------------
    page = doc.addObject("TechDraw::DrawPage", "Page")
    template = doc.addObject("TechDraw::DrawSVGTemplate", "Template")
    template.Template = _FC_TEMPLATE
    page.Template = template
    doc.recompute()

    # ------------------------------------------------------------------
    # 3. Helper: add a DrawViewPart
    # ------------------------------------------------------------------
    def add_view(name: str, direction: tuple, x_dir: tuple,
                 cx: float, cy: float) -> object:
        """Add a DrawViewPart to the page.

        Parameters
        ----------
        name:    label / object name
        direction: view normal (gaze direction, pointing toward viewer)
        x_dir:   X-axis direction on paper
        cx, cy:  centre of the view on the page [mm]
        """
        import FreeCAD as App
        view = doc.addObject("TechDraw::DrawViewPart", name)
        view.Source = [shape_obj]
        view.Direction = App.Vector(*direction)
        view.XDirection = App.Vector(*x_dir)
        view.Scale = _SCALE
        view.ScaleType = 1   # 1 = Custom
        # TechDraw page coords: X from left, Y from bottom
        view.X = cx
        view.Y = cy
        page.addView(view)
        doc.recompute()
        return view

    # ------------------------------------------------------------------
    # 4. Add the four standard views (third-angle projection)
    # ------------------------------------------------------------------
    # Front: looking along +Y (normal = -Y direction into page = -Y)
    #   Direction=(0,-1,0)  XDirection=(1,0,0)
    v_front = add_view("Front",   (0, -1,  0), (1, 0, 0),
                       *_FRONT_C)

    # Top: looking down along -Z (bird's eye)
    #   Direction=(0,0,-1)  XDirection=(1,0,0)
    v_top   = add_view("Top",     (0,  0, -1), (1, 0, 0),
                       *_TOP_C)

    # Right: looking along -X (from right side)
    #   Direction=(-1,0,0)  XDirection=(0,1,0)
    v_right = add_view("Right",   (-1, 0,  0), (0, 1, 0),
                       *_RIGHT_C)

    # Isometric: looking from (+1,+1,+1) direction
    #   Direction=(1,1,1)  XDirection=(1,-1,0) (normalised internally)
    v_iso   = add_view("Iso",     (1,  1,  1), (1, -1, 0),
                       *_ISO_C)

    # ------------------------------------------------------------------
    # 5. Dimension annotations (DrawViewAnnotation = text-based)
    # ------------------------------------------------------------------
    # Each annotation is a text label placed at a page position.
    # We use page coords directly rather than trying to name HLR edges
    # (edge names are non-deterministic for imported OCCT shapes).

    def _add_annotation(label: str, text: str,
                        px: float, py: float) -> None:
        ann = doc.addObject("TechDraw::DrawViewAnnotation", label)
        ann.Text = [text]
        ann.X = px
        ann.Y = py
        ann.TextSize = 3.5
        page.addView(ann)
        doc.recompute()

    # Convenience: offset from view centre
    fx, fy = _FRONT_C
    tx, ty = _TOP_C
    rx, ry = _RIGHT_C
    ix, iy = _ISO_C

    # -- Front view annotations --
    _add_annotation(
        "DimFrontLength",
        _dim_text(CP["base_length"]),
        fx, fy - 40,        # below front view
    )
    _add_annotation(
        "DimFrontHeight",
        _dim_text(CP["base_height"] + CP["wall_height"]),
        fx - 55, fy,        # left of front view
    )
    _add_annotation(
        "DimFinHeight",
        "FIN H=" + _dim_text(CP["fin_height"]),
        fx + 55, fy + 10,
    )
    _add_annotation(
        "DimScrewFront",
        "⌀" + _dim_text(CP["screw_hole_diameter"]),
        fx - 40, fy - 20,
    )

    # -- Top view annotations --
    _add_annotation(
        "DimTopWidth",
        _dim_text(CP["base_width"]),
        tx - 55, ty,        # left of top view
    )
    _add_annotation(
        "DimTopLength",
        _dim_text(CP["base_length"]),
        tx, ty + 40,        # above top view
    )
    _add_annotation(
        "DimChannelLen",
        "CHANNEL L=" + _dim_text(CP["channel_length"]),
        tx, ty - 5,
    )
    _add_annotation(
        "DimPinHoleDia",
        "PIN ⌀" + _dim_text(CP["pin_hole_diameter"]),
        tx + 40, ty - 20,
    )

    # -- Right view annotations --
    _add_annotation(
        "DimRightWidth",
        _dim_text(CP["base_width"]),
        rx, ry - 40,        # below right view
    )
    _add_annotation(
        "DimRightHeight",
        _dim_text(CP["base_height"] + CP["wall_height"]),
        rx + 55, ry,        # right of right view
    )
    _add_annotation(
        "DimWallThk",
        "WALL T=" + _dim_text(CP["wall_thickness"]),
        rx, ry + 25,
    )

    # -- General tolerance note --
    _add_annotation(
        "TolNote",
        _tol_note(),
        _SHEET_W / 2, 15,   # near bottom centre (above title block)
    )

    # -- Tolerance value (explicit) --
    from examples.case.heat_sink_example_V3.drawing_tolerances import (
        get_default_tolerance,
    )
    tol = get_default_tolerance()
    _add_annotation(
        "TolValue",
        f"DIM TOL: {tol.format_suffix()} {tol.unit}",
        _SHEET_W - 60, 25,
    )

    # ------------------------------------------------------------------
    # 6. Title block text annotations
    # ------------------------------------------------------------------
    title_x = _SHEET_W - 100
    title_y_base = 5

    _add_annotation("TitlePart",     "COLD PLATE — GPU WATER COOLED",
                    title_x, title_y_base + 30)
    _add_annotation("TitleDwgNo",    "DWG: CP-V3-001",
                    title_x, title_y_base + 22)
    _add_annotation("TitleMaterial", "MATERIAL: AL6061-T6",
                    title_x, title_y_base + 14)
    _add_annotation("TitleScale",    f"SCALE: {_SCALE}:1",
                    title_x, title_y_base + 6)
    _add_annotation("TitleProjection","PROJECTION: THIRD ANGLE",
                    title_x - 50, title_y_base + 6)

    # ------------------------------------------------------------------
    # 7. Export to DXF
    # ------------------------------------------------------------------
    Path(out_dxf).parent.mkdir(parents=True, exist_ok=True)
    TechDraw.writeDXFPage(page, str(out_dxf))
    doc.recompute()

    n_views = sum(
        1 for o in doc.Objects
        if o.isDerivedFrom("TechDraw::DrawView")
        and not o.isDerivedFrom("TechDraw::DrawViewAnnotation")
    )
    n_ann = sum(
        1 for o in doc.Objects
        if o.isDerivedFrom("TechDraw::DrawViewAnnotation")
    )

    print(f"[freecadcmd] Views: {n_views}  Annotations: {n_ann}")
    print(f"[freecadcmd] DXF written: {out_dxf}")


# ===========================================================================
# MODE A — conda Python orchestrator
# ===========================================================================

def _run_conda_mode() -> None:
    """Build cold plate, invoke freecadcmd, convert DXF → PDF."""

    # ------------------------------------------------------------------
    # Lazy imports (not available in freecadcmd environment)
    # ------------------------------------------------------------------
    import ezdxf
    from ezdxf.addons.drawing import RenderContext, Frontend
    from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
    import matplotlib.pyplot as plt

    from examples.case.heat_sink_example_V3.cold_plate_cad import build_cold_plate
    from examples.case.heat_sink_example_V3.drawing_tolerances import (
        get_default_tolerance,
    )
    from OCC.Core.STEPControl import STEPControl_AsIs, STEPControl_Writer
    from OCC.Core.IFSelect import IFSelect_RetDone

    tol = get_default_tolerance()

    # ------------------------------------------------------------------
    # 1. Build cold plate
    # ------------------------------------------------------------------
    print("Building cold plate …")
    result = build_cold_plate(**CP)
    solid = result["solid"]

    # ------------------------------------------------------------------
    # 2. Save STEP to temp file for freecadcmd
    # ------------------------------------------------------------------
    tmp_step = Path(tempfile.mktemp(suffix="_cold_plate_fc.step"))
    writer = STEPControl_Writer()
    writer.Transfer(solid, STEPControl_AsIs)
    status = writer.Write(str(tmp_step))
    if status != IFSelect_RetDone:
        raise RuntimeError(
            f"STEPControl_Writer failed with status {status}"
        )
    print(f"STEP saved to: {tmp_step}")

    # ------------------------------------------------------------------
    # 3. Output paths
    # ------------------------------------------------------------------
    drawings_dir = _ROOT / "data" / "drawings"
    drawings_dir.mkdir(parents=True, exist_ok=True)
    out_dxf = str(drawings_dir / "cold_plate_freecad.dxf")
    out_pdf = str(drawings_dir / "cold_plate_freecad.pdf")

    # ------------------------------------------------------------------
    # 4. Invoke freecadcmd
    # ------------------------------------------------------------------
    # Pass only the STEP path — do NOT pass the DXF path as an argument,
    # because freecadcmd treats any recognised file extension (.dxf) as a
    # document to open, which fails when the file doesn't exist yet.
    # The FreeCAD script computes the DXF output path from _ROOT.
    fc_cmd = [_FREECADCMD, str(Path(__file__).resolve()), str(tmp_step)]
    print(f"Invoking: {' '.join(fc_cmd)}")

    try:
        proc = subprocess.run(
            fc_cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minutes
        )
        if proc.stdout:
            for line in proc.stdout.splitlines():
                print(f"  [fc] {line}")
        if proc.stderr:
            for line in proc.stderr.splitlines():
                if line.strip():
                    print(f"  [fc-err] {line}", file=sys.stderr)
        if proc.returncode != 0:
            raise RuntimeError(
                f"freecadcmd exited with code {proc.returncode}"
            )
    finally:
        tmp_step.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # 5. Convert DXF → PDF via ezdxf + matplotlib
    # ------------------------------------------------------------------
    if not Path(out_dxf).exists():
        raise FileNotFoundError(
            f"Expected DXF not found after freecadcmd: {out_dxf}"
        )

    print(f"Converting DXF → PDF …")
    dxf_doc = ezdxf.readfile(out_dxf)
    msp = dxf_doc.modelspace()

    fig = plt.figure(figsize=(420 / 25.4, 297 / 25.4))  # A3 in inches
    ax = fig.add_axes([0, 0, 1, 1])
    ctx = RenderContext(dxf_doc)
    out_backend = MatplotlibBackend(ax)
    Frontend(ctx, out_backend).draw_layout(msp)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.savefig(out_pdf, dpi=150, bbox_inches="tight")
    plt.close(fig)

    # ------------------------------------------------------------------
    # 6. Summary
    # ------------------------------------------------------------------
    print()
    print("=" * 60)
    print("  Cold-Plate Production Drawing — FreeCAD TechDraw")
    print("=" * 60)
    print(f"  Views:           4  (Front, Top, Right, Isometric)")
    print(f"  Annotation set:  DrawViewAnnotation (text-based)")
    print(f"  Tolerance:       {tol.format_suffix()} {tol.unit}  "
          f"← from get_default_tolerance()")
    print(f"  General note:    {tol.format_general_note()}")
    print(f"  Scale:           {_SCALE}:1")
    print(f"  DXF output:      {out_dxf}")
    print(f"  PDF output:      {out_pdf}")
    print("=" * 60)


# ===========================================================================
# Entry point — detect mode based on FreeCAD availability
# ===========================================================================
# IMPORTANT: freecadcmd executes scripts with __name__ set to the *module*
# name (e.g. 'cold_plate_drawing_freecad'), NOT '__main__'.  Therefore the
# conventional `if __name__ == '__main__':` guard is DEAD CODE in FreeCAD
# mode and must not be used as the sole discriminator.
#
# Strategy:
#   • FreeCAD importable  → Mode B  (running under freecadcmd)
#   • FreeCAD not found AND __name__ == '__main__'  → Mode A (conda Python)
#   • FreeCAD not found AND __name__ != '__main__'  → imported as a library;
#     do nothing (functions are still available for external callers).
# ===========================================================================

def _freecad_available() -> bool:
    """Return True when the FreeCAD C-extension can be imported."""
    try:
        import FreeCAD  # type: ignore  # noqa: F401
        return True
    except ImportError:
        return False


if _freecad_available():
    # ---- Mode B: running under freecadcmd ----
    # argv layout: freecadcmd [0]  script.py [1]  step_path [2]  (dxf [3])
    if len(sys.argv) >= 3:
        _step_arg = sys.argv[2]
        _default_dxf = str(
            _ROOT / "data" / "drawings" / "cold_plate_freecad.dxf"
        )
        _dxf_arg = sys.argv[3] if len(sys.argv) > 3 else _default_dxf
        _run_freecad_mode(_step_arg, _dxf_arg)
    else:
        print(
            "Usage (freecadcmd mode): "
            "freecadcmd cold_plate_drawing_freecad.py <step_path>",
            file=sys.stderr,
        )

elif __name__ == "__main__":
    # ---- Mode A: conda Python script ----
    _run_conda_mode()
