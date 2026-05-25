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
       a command-line argument.
    4. Waits for freecadcmd to finish.
    5. Converts the SVG produced by FreeCAD to PDF using ``rsvg-convert``.
    6. Prints the summary.

Mode B — FreeCAD Python (freecadcmd <this_file> <step_path>)
    ``freecadcmd cold_plate_drawing_freecad.py /tmp/cold_plate_fc.step``

    1. Imports the STEP into a FreeCAD document.
    2. Creates a TechDraw page (A3 landscape, blank template).
    3. Adds four DrawViewPart objects: Front, Top, Right, Isometric.
    4. Adds DrawViewAnnotation objects for all dimensions.
    5. Exports the rendered page SVG via ``page.PageResult`` (the path to
       FreeCAD's internal rendered SVG — this includes full view geometry,
       unlike ``TechDraw.writeDXFPage`` which omits projected edges and
       mis-positions all annotation text at the sheet centre).
    6. Exits FreeCAD.

Output files
------------
``data/drawings/cold_plate_freecad.svg``
``data/drawings/cold_plate_freecad.pdf``

Both paths are relative to the repository root.  The data/drawings/
directory is created automatically.

Why SVG instead of DXF
-----------------------
``TechDraw.writeDXFPage`` has two fatal flaws:

* **No geometry**: projected edges from ``DrawViewPart`` objects are never
  written to the DXF; only annotation text entities appear.
* **Wrong positions**: every ``DrawViewAnnotation`` is placed at the sheet
  centre (210, 148.5) regardless of the ``X``/``Y`` attributes set on the
  object.

FreeCAD renders TechDraw pages to SVG internally after every ``recompute()``.
``page.PageResult`` gives the path to that fully-rendered SVG, which contains
correct geometry and annotation positions.  We copy it out and convert to PDF
with ``rsvg-convert`` (part of ``librsvg``, already present in the conda env).

Dependencies
------------
* Mode A: OCP / PythonOCC (from the ``auto_eval_manuf`` conda env),
  ``rsvg-convert`` on PATH (provided by the ``librsvg`` package)
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

def _run_freecad_mode(step_path: str, out_svg: str) -> None:
    """Project views synchronously via TechDraw.projectToSVG, write A3 SVG.

    This function is executed inside freecadcmd.

    Why not DrawPage / DrawViewPart?
    --------------------------------
    FreeCAD 1.0 computes Hidden Line Removal in a worker thread triggered by
    a Qt timer callback.  In freecadcmd mode the script runs before the
    Qt event loop starts, so those callbacks never fire — DrawViewPart
    geometry is always empty and PageResult stays at the blank 519-byte
    template regardless of how long we wait or how many times we call
    ``doc.recompute()`` or ``QCoreApplication.processEvents()``.

    ``TechDraw.projectToSVG(shape, direction, type, tol, vdir)`` is a
    **synchronous** C++ call that runs HLR immediately and returns an SVG
    fragment string.  We call it for each of the four views and assemble
    the A3 sheet SVG ourselves, which is far more reliable in headless
    mode.

    Parameters
    ----------
    step_path : path to the STEP file to import
    out_svg   : destination path for the assembled A3 SVG
    """
    import xml.sax.saxutils as _xml  # for escaping annotation text
    import FreeCAD                    # type: ignore  # FreeCAD built-in
    import TechDraw                   # type: ignore  # FreeCAD built-in
    import Part                       # type: ignore  # FreeCAD built-in

    # ------------------------------------------------------------------
    # 1. Load STEP
    # ------------------------------------------------------------------
    doc = FreeCAD.newDocument("ColdPlateDrawing")
    Part.insert(step_path, doc.Name)
    doc.recompute()

    shape_obj = next(
        (o for o in doc.Objects if hasattr(o, "Shape") and not o.Shape.isNull()),
        None,
    )
    if shape_obj is None:
        raise RuntimeError(f"No shape found after importing STEP: {step_path}")
    shape = shape_obj.Shape

    # ------------------------------------------------------------------
    # 2. Project each view synchronously via TechDraw.projectToSVG
    # ------------------------------------------------------------------
    # projectToSVG(shape, direction, type, tolerance, vdir) → SVG fragment
    #   direction : FreeCAD.Vector pointing FROM the scene TOWARD the viewer
    #   type      : "FromWire" = visible edges | "HiddenLine" = hidden edges
    #   tolerance : HLR chord tolerance (mm)
    #   vdir      : FreeCAD.Vector = paper X direction (right in the view)
    #
    # The returned fragment is an SVG <g> subtree in the view's LOCAL
    # coordinate system (origin at shape bbox centre, Y going DOWN as per
    # SVG convention).  Scale is 1:1 model mm.
    #
    # We apply scale + position ourselves via an SVG <g transform>.
    # ------------------------------------------------------------------
    _VIEWS = [
        # name     direction           paper-X           page-centre
        ("Front",  ( 0, -1,  0),  (1,  0, 0),  _FRONT_C),
        ("Top",    ( 0,  0, -1),  (1,  0, 0),  _TOP_C),
        ("Right",  (-1,  0,  0),  (0,  1, 0),  _RIGHT_C),
        ("Iso",    ( 1,  1,  1),  (1, -1, 0),  _ISO_C),
    ]

    def _project(shp, direction, vdir, edge_type: str) -> str:
        """Return SVG fragment or '' on failure.

        FreeCAD 1.0.2: projectToSVG vdir must be a "x,y,z" string, not a
        FreeCAD.Vector.  We try the string form first, then fall back to
        omitting vdir entirely (FreeCAD picks a default X direction).
        """
        view_dir = FreeCAD.Vector(*direction)
        vdir_str = f"{vdir[0]},{vdir[1]},{vdir[2]}"

        # Try 1: string vdir (FreeCAD 1.0.x)
        try:
            frag = TechDraw.projectToSVG(shp, view_dir, edge_type, 0.05, vdir_str)
            if frag:
                return frag
        except Exception:
            pass

        # Try 2: no vdir argument (let FreeCAD choose the default X direction)
        try:
            frag = TechDraw.projectToSVG(shp, view_dir, edge_type, 0.05)
            if frag:
                return frag
        except Exception:
            pass

        # Try 3: keyword arguments (future-proof)
        try:
            frag = TechDraw.projectToSVG(
                shp, view_dir, edge_type, 0.05,
                vdir=FreeCAD.Vector(*vdir),
            )
            if frag:
                return frag
        except Exception as _e:
            print(f"[freecadcmd] projectToSVG({edge_type}) all forms failed: {_e}",
                  file=sys.stderr)
        return ""

    # ------------------------------------------------------------------
    # 3. Build A3 SVG
    # ------------------------------------------------------------------
    # Coordinate mapping:
    #   TechDraw page  (0,0) = bottom-left, Y up
    #   SVG            (0,0) = top-left,    Y down
    #   SVG_y = SHEET_H - TD_y
    #
    # Each view is centred at (cx, cy) in TechDraw coords.
    # The projectToSVG fragment is centred at (0,0) in view-local space.
    # We position it with:
    #   transform="translate(cx, SHEET_H-cy) scale(SCALE, SCALE)"
    # ------------------------------------------------------------------
    _LW_VIS = f"{0.35 / _SCALE:.4f}"   # visible line width (scaled back to 1:1)
    _LW_HID = f"{0.25 / _SCALE:.4f}"   # hidden line width

    out_lines: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg"'
        f' width="{_SHEET_W}mm" height="{_SHEET_H}mm"'
        f' viewBox="0 0 {_SHEET_W} {_SHEET_H}"'
        f' version="1.1">',
        # Sheet border
        f'  <rect x="5" y="5" width="{_SHEET_W - 10}" height="{_SHEET_H - 10}"'
        f'   fill="none" stroke="#000000" stroke-width="0.5"/>',
    ]

    for vname, vdir_model, vdir_paper, (cx, cy) in _VIEWS:
        vis_frag = _project(shape, vdir_model, vdir_paper, "FromWire")
        hid_frag = _project(shape, vdir_model, vdir_paper, "HiddenLine")
        svg_y    = _SHEET_H - cy

        out_lines.append(
            f'  <!-- === {vname} view  centre TD({cx},{cy}) SVG({cx},{svg_y}) === -->'
        )
        out_lines.append(
            f'  <g id="{vname}"'
            f' transform="translate({cx},{svg_y}) scale({_SCALE},{_SCALE})">'
        )
        if hid_frag:
            out_lines += [
                f'    <g id="{vname}_hid" fill="none"'
                f' stroke="#000000" stroke-dasharray="4,2"'
                f' stroke-width="{_LW_HID}">',
                f'      {hid_frag}',
                f'    </g>',
            ]
        if vis_frag:
            out_lines += [
                f'    <g id="{vname}_vis" fill="none"'
                f' stroke="#000000" stroke-width="{_LW_VIS}">',
                f'      {vis_frag}',
                f'    </g>',
            ]
        if not vis_frag and not hid_frag:
            print(f"[freecadcmd] Warning: {vname} view produced no geometry",
                  file=sys.stderr)
        out_lines.append(f'  </g>')

    # ------------------------------------------------------------------
    # 4. Dimension + title block annotations (SVG <text>)
    # ------------------------------------------------------------------
    # TechDraw page coords → SVG coords: SVG_y = SHEET_H - TD_y
    # text-anchor="middle" centres the label on the given point.
    # ------------------------------------------------------------------
    _FS  = 3.5   # font size (mm) — matches DrawViewAnnotation.TextSize
    _FF  = "font-family='sans-serif'"
    _TA  = "text-anchor='middle'"

    def _txt(td_x: float, td_y: float, content: str) -> str:
        safe = _xml.escape(content)
        return (
            f"  <text x='{td_x}' y='{_SHEET_H - td_y}'"
            f" font-size='{_FS}' {_FF} {_TA}>{safe}</text>"
        )

    fx, fy = _FRONT_C
    tx, ty = _TOP_C
    rx, ry = _RIGHT_C

    from examples.case.heat_sink_example_V3.drawing_tolerances import (
        get_default_tolerance,
    )
    tol = get_default_tolerance()

    annotations = [
        # --- Front ---
        (fx,      fy - 40, _dim_text(CP["base_length"])),
        (fx - 55, fy,      _dim_text(CP["base_height"] + CP["wall_height"])),
        (fx + 55, fy + 10, "FIN H=" + _dim_text(CP["fin_height"])),
        (fx - 40, fy - 20, "Ø" + _dim_text(CP["screw_hole_diameter"])),
        # --- Top ---
        (tx - 55, ty,      _dim_text(CP["base_width"])),
        (tx,      ty + 40, _dim_text(CP["base_length"])),
        (tx,      ty - 5,  "CHANNEL L=" + _dim_text(CP["channel_length"])),
        (tx + 40, ty - 20, "PIN Ø" + _dim_text(CP["pin_hole_diameter"])),
        # --- Right ---
        (rx,      ry - 40, _dim_text(CP["base_width"])),
        (rx + 55, ry,      _dim_text(CP["base_height"] + CP["wall_height"])),
        (rx,      ry + 25, "WALL T=" + _dim_text(CP["wall_thickness"])),
        # --- Tolerance notes ---
        (_SHEET_W / 2,  15, _tol_note()),
        (_SHEET_W - 60, 25, f"DIM TOL: {tol.format_suffix()} {tol.unit}"),
    ]

    # Title block (right-side panel, bottom of sheet)
    _tx  = _SHEET_W - 100
    _ty0 = 5
    annotations += [
        (_tx,      _ty0 + 30, "COLD PLATE — GPU WATER COOLED"),
        (_tx,      _ty0 + 22, "DWG: CP-V3-001"),
        (_tx,      _ty0 + 14, "MATERIAL: AL6061-T6"),
        (_tx,      _ty0 + 6,  f"SCALE: {_SCALE}:1"),
        (_tx - 50, _ty0 + 6,  "PROJECTION: THIRD ANGLE"),
    ]

    for (td_x, td_y, label) in annotations:
        out_lines.append(_txt(td_x, td_y, label))

    out_lines.append("</svg>")

    # ------------------------------------------------------------------
    # 5. Write SVG
    # ------------------------------------------------------------------
    Path(out_svg).parent.mkdir(parents=True, exist_ok=True)
    with open(out_svg, "w", encoding="utf-8") as _f:
        _f.write("\n".join(out_lines) + "\n")
    Path(out_svg).chmod(0o644)

    print(f"[freecadcmd] Views: 4  Annotations: {len(annotations)}")
    print(f"[freecadcmd] SVG written: {out_svg}"
          f"  ({Path(out_svg).stat().st_size} B)")


# ===========================================================================
# MODE A — conda Python orchestrator
# ===========================================================================

def _run_conda_mode() -> None:
    """Build cold plate, invoke freecadcmd, convert SVG → PDF."""

    # ------------------------------------------------------------------
    # Lazy imports (not available in freecadcmd environment)
    # ------------------------------------------------------------------
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
    _fd, _tmp = tempfile.mkstemp(suffix="_cold_plate_fc.step")
    os.close(_fd)
    tmp_step = Path(_tmp)
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
    out_svg = str(drawings_dir / "cold_plate_freecad.svg")
    out_pdf = str(drawings_dir / "cold_plate_freecad.pdf")

    # ------------------------------------------------------------------
    # 4. Invoke freecadcmd
    # ------------------------------------------------------------------
    # Only the STEP path is passed as an argument.  The SVG output path
    # is computed inside Mode B from _ROOT so we never hand freecadcmd a
    # path with a file extension it might try to open as a document.
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
    # 5. Convert SVG → PDF via rsvg-convert (part of librsvg)
    # ------------------------------------------------------------------
    # We use rsvg-convert rather than ezdxf/matplotlib because FreeCAD
    # TechDraw's DXF exporter omits all projected view geometry and
    # mis-positions every annotation at the sheet centre.  The SVG
    # produced by page.PageResult contains the full, correct drawing.
    # ------------------------------------------------------------------
    if not Path(out_svg).exists():
        raise FileNotFoundError(
            f"Expected SVG not found after freecadcmd: {out_svg}\n"
            "Check the [fc-err] lines above for FreeCAD errors."
        )

    # Resolve rsvg-convert: honour env override, then search PATH
    # (conda envs add their bin/ to PATH but subprocess may not inherit it).
    import shutil as _shutil_main
    _rsvg = os.environ.get("RSVG_CONVERT") or _shutil_main.which("rsvg-convert")
    if _rsvg is None:
        # Fallback: look next to the current Python interpreter
        _py_bin = Path(sys.executable).parent
        _candidate = _py_bin / "rsvg-convert"
        if _candidate.exists():
            _rsvg = str(_candidate)
    if _rsvg is None:
        raise FileNotFoundError(
            "rsvg-convert not found on PATH.\n"
            "Install it with:  conda install -n auto_eval_manuf librsvg\n"
            "Or set the RSVG_CONVERT environment variable to its full path."
        )
    print(f"Converting SVG → PDF via {_rsvg} …")
    conv = subprocess.run(
        [_rsvg, "-f", "pdf", "-o", out_pdf, out_svg],
        capture_output=True,
        text=True,
    )
    if conv.returncode != 0:
        raise RuntimeError(
            f"rsvg-convert failed (exit {conv.returncode}):\n{conv.stderr}"
        )

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
    print(f"  SVG output:      {out_svg}")
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
    # Different FreeCAD versions place argv differently:
    #   some: sys.argv = [script, step_path, ...]
    #   some: sys.argv = [freecadcmd, script, step_path, ...]
    # Search by extension so the position doesn't matter.
    _step_arg = next(
        (a for a in sys.argv[1:] if a.lower().endswith((".step", ".stp"))),
        None,
    )
    if _step_arg:
        _default_svg = str(
            _ROOT / "data" / "drawings" / "cold_plate_freecad.svg"
        )
        _run_freecad_mode(_step_arg, _default_svg)
    else:
        print(
            "Usage (freecadcmd mode): "
            "freecadcmd cold_plate_drawing_freecad.py <step_path>",
            file=sys.stderr,
        )

elif __name__ == "__main__":
    # ---- Mode A: conda Python script ----
    _run_conda_mode()
