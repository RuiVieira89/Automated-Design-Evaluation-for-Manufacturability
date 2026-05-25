"""Production-ready ISO technical drawing of the fin-array heat sink.

Standard compliance
-------------------
ISO 128-20  : orthographic views, first-angle projection
ISO 5457    : A3 landscape drawing sheet (420 × 297 mm)
ISO 7200    : title block layout
ISO 129-1   : linear dimension notation
ISO 2768-m  : general tolerances (stated in title block)

Projection views
----------------
View A — Front    : XZ plane, eye along −Y axis
View B — Top      : XY plane, eye along +Z axis  [first-angle: below front]
View C — R. Side  : YZ plane, eye along +X axis  [first-angle: left of front]
View D — Isometric: right half of sheet

Outputs
-------
data/CAD_generated/heat_sink_drawing.pdf
data/CAD_generated/heat_sink_drawing.svg

Usage
-----
    conda run -n auto_eval_manuf python \\
        examples/case/heat_sink_example_V2/CAD_heatSink_dwg.py
"""

from __future__ import annotations

import sys
import math
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyArrowPatch, Rectangle

from OCC.Core.BRepAlgoAPI import BRepAlgoAPI_Fuse
from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCC.Core.gp import gp_Pnt, gp_Dir, gp_Ax2
from OCC.Core.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape
from OCC.Core.HLRAlgo import HLRAlgo_Projector
from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopAbs import TopAbs_EDGE
from OCC.Core.BRepAdaptor import BRepAdaptor_Curve
from OCC.Core.GeomAbs import GeomAbs_Line

# ---------------------------------------------------------------------------
# Repo root
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_DEFAULT_DEST = ROOT / "data" / "CAD_generated"

# ---------------------------------------------------------------------------
# Heat-sink default parameters  (mirrors CAD_heatSink.py defaults)
# ---------------------------------------------------------------------------
PARAMS: dict = {
    "fin_height":    20.0,   # mm
    "fin_thickness":  2.0,   # mm
    "fin_spacing":    5.0,   # mm
    "base_height":    5.0,   # mm
    "fin_number":     6,
    "channel_length": 50.0,  # mm
}

# ---------------------------------------------------------------------------
# Drawing constants
# ---------------------------------------------------------------------------
DRAW_SCALE      = 2.0       # 2:1 scale
SCALE_LABEL     = "2:1"
DWG_NUMBER      = "AEM-HS-001"
MATERIAL        = "AL 6061-T6"
PROJECTION_STD  = "ISO FIRST-ANGLE PROJECTION"

# A3 landscape sheet (ISO 5457) — all values in mm
SHEET_W = 420.0
SHEET_H = 297.0
MM_TO_IN = 1.0 / 25.4

# Line weights (matplotlib lw is in points, ≈ 0.353 mm)
LW_THICK   = 1.4   # visible edges, border
LW_THIN    = 0.7   # dimension lines, extension lines, thin features
LW_DASHED  = 0.5   # hidden lines
LW_CHAIN   = 0.4   # centre lines

# Colours
COL_VIS    = "#000000"   # visible edges
COL_HID    = "#606060"   # hidden edges
COL_DIM    = "#000000"   # dimensions
COL_CLINE  = "#0044cc"   # centre lines
COL_FILL   = "#f5f8ff"   # title-block header fill


# ===========================================================================
# Geometry helpers
# ===========================================================================

def _build_shape(p: dict):
    """Return the OCC compound heat-sink shape from parameter dict."""
    fh = p["fin_height"]
    ft = p["fin_thickness"]
    fs = p["fin_spacing"]
    bh = p["base_height"]
    fn = p["fin_number"]
    cl = p["channel_length"]
    tw = fn * ft + (fn - 1) * fs

    base = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), cl, tw, bh).Shape()
    compound = base
    for i in range(fn):
        y0 = i * (ft + fs)
        fin = BRepPrimAPI_MakeBox(gp_Pnt(0, y0, bh), cl, ft, fh).Shape()
        fuse = BRepAlgoAPI_Fuse(compound, fin)
        fuse.Build()
        compound = fuse.Shape()
    return compound


def _project(shape, eye_dir: tuple[float, float, float],
             x_dir: tuple[float, float, float]):
    """HLR orthographic projection.

    Parameters
    ----------
    eye_dir:
        Unit vector FROM object TO eye (projection axis / view ray direction).
    x_dir:
        Horizontal axis on the projection plane (must be ⊥ to eye_dir).

    Returns
    -------
    vis_lines, hid_lines : list[(xs, ys)]
        Polylines for visible and hidden edges.
    """
    ax2 = gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(*eye_dir), gp_Dir(*x_dir))
    proj = HLRAlgo_Projector(ax2)

    algo = HLRBRep_Algo()
    algo.Add(shape)
    algo.Projector(proj)
    algo.Update()
    algo.Hide()

    h2s = HLRBRep_HLRToShape(algo)
    return (_polylines(h2s.VCompound()),
            _polylines(h2s.HCompound()))


def _polylines(compound):
    """Discretise OCC compound of edges → list of (xs, ys) numpy arrays."""
    result = []
    if compound is None:
        return result
    try:
        if compound.IsNull():
            return result
    except Exception:
        return result

    exp = TopExp_Explorer(compound, TopAbs_EDGE)
    while exp.More():
        edge = exp.Current()
        try:
            adp = BRepAdaptor_Curve(edge)
            u0, u1 = adp.FirstParameter(), adp.LastParameter()
            npts = 2 if adp.GetType() == GeomAbs_Line else 64
            us = np.linspace(u0, u1, npts)
            pts = [adp.Value(float(u)) for u in us]
            xs = np.array([pt.X() for pt in pts])
            ys = np.array([pt.Y() for pt in pts])
            result.append((xs, ys))
        except Exception:
            pass
        exp.Next()
    return result


# ===========================================================================
# Drawing primitives
# ===========================================================================

def _plot_lines(ax, polylines, color, lw, ls="-", zo=3):
    for xs, ys in polylines:
        ax.plot(xs, ys, color=color, lw=lw, linestyle=ls,
                solid_capstyle="round", zorder=zo)


def _view(ax, vis, hid, cx, cy, scale,
          flip_x=False, flip_y=False):
    """Render one orthographic view centred at (cx, cy)."""
    sx = -scale if flip_x else scale
    sy = -scale if flip_y else scale

    for xs, ys in vis:
        ax.plot(cx + sx * xs, cy + sy * ys,
                color=COL_VIS, lw=LW_THICK, linestyle="-",
                solid_capstyle="round", zorder=3)
    for xs, ys in hid:
        ax.plot(cx + sx * xs, cy + sy * ys,
                color=COL_HID, lw=LW_DASHED, linestyle=(0, (4, 2)),
                solid_capstyle="round", zorder=2)


def _dim(ax, x1, y1, x2, y2, text,
         offset=8.0, flip=False, fontsize=5.5):
    """ISO 129-1 linear dimension annotation.

    Parameters
    ----------
    offset  : perpendicular distance from geometry to dim line [mm on plot].
    flip    : if True, offset to the right/below rather than left/above.
    """
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return
    ux, uy = dx / length, dy / length
    # Perpendicular (left of travel direction)
    px, py = -uy, ux
    if flip:
        px, py = uy, -ux

    gap = 1.5   # gap between geometry and extension line start
    ext = 2.5   # extension beyond dimension line

    # Extension lines
    for gx, gy in [(x1, y1), (x2, y2)]:
        ax.plot([gx + gap * px, gx + (offset + ext) * px],
                [gy + gap * py, gy + (offset + ext) * py],
                color=COL_DIM, lw=LW_THIN, zorder=1, solid_capstyle="butt")

    # Dimension line with arrows
    d0 = (x1 + offset * px, y1 + offset * py)
    d1 = (x2 + offset * px, y2 + offset * py)
    ax.annotate(
        "", xy=d1, xytext=d0,
        arrowprops=dict(arrowstyle="<->", color=COL_DIM,
                        lw=LW_THIN, mutation_scale=7),
        zorder=2,
    )

    # Text (centred, white box, rotated with dimension line)
    mx = (d0[0] + d1[0]) / 2
    my = (d0[1] + d1[1]) / 2
    angle = math.degrees(math.atan2(dy, dx))
    if angle > 90 or angle < -90:
        angle += 180
    ax.text(mx, my, text,
            ha="center", va="center",
            fontsize=fontsize, color=COL_DIM,
            fontfamily="monospace", rotation=angle,
            rotation_mode="anchor",
            bbox=dict(facecolor="white", edgecolor="none", pad=0.8),
            zorder=4)


def _note(ax, x, y, text, ha="left", fontsize=5, color="#333333"):
    ax.text(x, y, text, ha=ha, va="bottom",
            fontsize=fontsize, fontfamily="monospace",
            color=color, zorder=5)


def _cline(ax, x1, y1, x2, y2):
    """Centre line (ISO chain-dash)."""
    ax.plot([x1, x2], [y1, y2],
            color=COL_CLINE, lw=LW_CHAIN,
            linestyle=(0, (9, 3, 2, 3)), zorder=1)


def _view_label(ax, cx, cy_bottom, text):
    ax.text(cx, cy_bottom - 6, text,
            ha="center", va="top",
            fontsize=6, fontfamily="monospace",
            fontstyle="italic", color="#222222", zorder=5)


# ===========================================================================
# First-angle projection symbol  (ISO 128-30 Annex A)
# ===========================================================================

def _first_angle_symbol(ax, cx, cy, r=4.0):
    """Simplified first-angle truncated-cone symbol."""
    lw = 0.7
    # Cone (side view on left)
    cone_x = [cx - 2.5 * r, cx - r, cx - r, cx - 2.5 * r, cx - 2.5 * r]
    cone_y = [cy - 0.4 * r, cy - 0.65 * r, cy + 0.65 * r,
               cy + 0.4 * r, cy - 0.4 * r]
    ax.plot(cone_x, cone_y, color="black", lw=lw, zorder=6)
    # Circle (front view on right)
    circle = plt.Circle((cx + 0.4 * r, cy), 0.65 * r,
                         fill=False, edgecolor="black", lw=lw, zorder=6)
    ax.add_patch(circle)
    # Dot centre of circle
    ax.plot(cx + 0.4 * r, cy, ".", color="black", ms=1.5, zorder=6)


# ===========================================================================
# Title block  (ISO 7200)
# ===========================================================================

def _title_block(ax, x0, y0, p: dict):
    """Draw ISO 7200 title block.  Origin (x0, y0) = bottom-left corner."""
    W, H = 180.0, 55.0

    def box(xi, yi, wi, hi, label="", value="", bold=False, bg="white",
            label_size=3.5, value_size=5.5):
        ax.add_patch(Rectangle((xi, yi), wi, hi,
                                linewidth=0.4, edgecolor="black",
                                facecolor=bg, zorder=10))
        if label:
            ax.text(xi + 1, yi + hi - 1.2, label,
                    fontsize=label_size, va="top", ha="left",
                    color="#555555", fontfamily="monospace", zorder=11)
        if value:
            ax.text(xi + wi / 2, yi + hi / 2 - 0.5, value,
                    fontsize=value_size, va="center", ha="center",
                    fontweight="bold" if bold else "normal",
                    fontfamily="monospace", zorder=11)

    fh = p["fin_height"]; ft = p["fin_thickness"]
    fs = p["fin_spacing"]; bh = p["base_height"]
    fn = p["fin_number"];  cl = p["channel_length"]
    tw = fn * ft + (fn - 1) * fs

    # Outer border
    ax.add_patch(Rectangle((x0, y0), W, H,
                            linewidth=LW_THICK, edgecolor="black",
                            facecolor="white", zorder=9))

    # --- Row 0 (bottom, y0 → y0+9): material / finish / mass / scale ---
    y = y0
    box(x0,        y, 50, 9, "MATERIAL",    MATERIAL)
    box(x0 + 50,   y, 50, 9, "FINISH",      "AS MACHINED")
    box(x0 + 100,  y, 40, 9, "MASS (est.)", "~75 g")
    box(x0 + 140,  y, 40, 9, "SCALE",       SCALE_LABEL)

    # --- Row 1 (y0+9 → y0+18): tolerances / roughness ---
    y = y0 + 9
    box(x0,        y, 90, 9, "GENERAL TOLERANCES",   "ISO 2768-m")
    box(x0 + 90,   y, 90, 9, "SURFACE ROUGHNESS",    "Ra 3.2 μm")

    # --- Row 2 (y0+18 → y0+27): drawn / date / approved ---
    y = y0 + 18
    box(x0,        y, 60, 9, "DRAWN",    "auto-generated")
    box(x0 + 60,   y, 60, 9, "DATE",     "2026-05-23")
    box(x0 + 120,  y, 60, 9, "APPROVED", "—")

    # --- Row 3 (y0+27 → y0+36): project / drawing number ---
    y = y0 + 27
    box(x0,        y, 90, 9, "PROJECT",  "Auto Eval Manuf")
    box(x0 + 90,   y, 90, 9, "DWG No.",  DWG_NUMBER, bold=True)

    # --- Row 4 (y0+36 → y0+55): title (large) ---
    y = y0 + 36
    ax.add_patch(Rectangle((x0, y), W, 19,
                            linewidth=0.4, edgecolor="black",
                            facecolor=COL_FILL, zorder=10))
    ax.text(x0 + W / 2, y + 13,
            "FIN-ARRAY HEAT SINK",
            fontsize=10, va="center", ha="center",
            fontweight="bold", fontfamily="monospace", zorder=11)
    ax.text(x0 + W / 2, y + 5,
            f"L{cl:.0f} × W{tw:.0f} × H{bh:.0f}+{fh:.0f}  |  {fn} FINS  |  SYMMETRIC",
            fontsize=5, va="center", ha="center",
            fontfamily="monospace", color="#444444", zorder=11)

    # Projection symbol + label
    _first_angle_symbol(ax, x0 + 15, y0 + 4.5, r=3)
    ax.text(x0 + 30, y0 + 4.5,
            "FIRST-ANGLE PROJECTION\nISO 128-20",
            fontsize=3.5, va="center", ha="left",
            fontfamily="monospace", color="#444444", zorder=11)


# ===========================================================================
# Parameter table
# ===========================================================================

def _param_table(ax, x0, y0, p: dict):
    W, H = 170.0, 8.0
    headers = [
        ("PARAMETER", "VALUE", "UNIT"),
        ("Fin height",      f"{p['fin_height']:.1f}",     "mm"),
        ("Fin thickness",   f"{p['fin_thickness']:.1f}",  "mm"),
        ("Fin spacing",     f"{p['fin_spacing']:.1f}",    "mm"),
        ("Base height",     f"{p['base_height']:.1f}",    "mm"),
        ("No. of fins",     f"{p['fin_number']}",         "—"),
        ("Channel length",  f"{p['channel_length']:.1f}", "mm"),
    ]
    col_w = [90, 50, 30]
    for row_i, (name, val, unit) in enumerate(headers):
        y = y0 - row_i * H
        is_hdr = row_i == 0
        bg = COL_FILL if is_hdr else "white"
        for col_i, (text, cw) in enumerate(zip([name, val, unit], col_w)):
            cx_cell = x0 + sum(col_w[:col_i])
            ax.add_patch(Rectangle((cx_cell, y - H), cw, H,
                                    linewidth=0.3, edgecolor="black",
                                    facecolor=bg, zorder=7))
            ax.text(cx_cell + cw / 2, y - H / 2, text,
                    fontsize=4.5 if is_hdr else 4,
                    va="center", ha="center",
                    fontweight="bold" if is_hdr else "normal",
                    fontfamily="monospace", zorder=8)


# ===========================================================================
# Main drawing
# ===========================================================================

def generate_drawing(params: dict | None = None,
                     dest_folder: Path | str | None = None,
                     show: bool = False) -> str:
    """Generate ISO technical drawing and save PDF + SVG.

    Parameters
    ----------
    params:
        Heat-sink geometry dict (keys matching PARAMS).  None = defaults.
    dest_folder:
        Output directory.  None = ``data/CAD_generated/``.
    show:
        Display the figure interactively when True.

    Returns
    -------
    str  Path to the saved PDF file.
    """
    if params is None:
        params = PARAMS.copy()

    dest = Path(dest_folder) if dest_folder else _DEFAULT_DEST
    dest.mkdir(parents=True, exist_ok=True)

    # -----------------------------------------------------------------------
    # Derived dimensions
    # -----------------------------------------------------------------------
    fh = params["fin_height"]
    ft = params["fin_thickness"]
    fs = params["fin_spacing"]
    bh = params["base_height"]
    fn = params["fin_number"]
    cl = params["channel_length"]
    tw = fn * ft + (fn - 1) * fs   # total width  (Y)
    th = bh + fh                    # total height (Z)
    pitch = ft + fs                 # fin pitch

    s = DRAW_SCALE  # 2.0

    # -----------------------------------------------------------------------
    # HLR projections
    # -----------------------------------------------------------------------
    print("Building shape …")
    shape = _build_shape(params)

    print("Computing HLR projections …")

    # Front view  (eye along −Y → XZ plane visible)
    # eye_dir = (0,-1,0), x_dir = (1,0,0)
    # Resulting 2D: X = Px,  Y = −Pz  (height flipped; flip_y corrects it)
    vis_f, hid_f = _project(shape, (0, -1, 0), (1, 0, 0))

    # Top view  (eye along +Z → XY plane visible)
    # eye_dir = (0,0,1), x_dir = (1,0,0)
    # Resulting 2D: X = Px,  Y = Py  (depth goes up; flip_y for first-angle)
    vis_t, hid_t = _project(shape, (0, 0, 1), (1, 0, 0))

    # Right side view  (eye along +X → YZ plane visible)
    # eye_dir = (1,0,0), x_dir = (0,-1,0)
    # Resulting 2D: X = −Py,  Y = −Pz  (flip_x, flip_y corrects orientation)
    vis_r, hid_r = _project(shape, (1, 0, 0), (0, -1, 0))

    # Isometric  (eye along (1,1,1)/√3, right-hand "up" ≈ Z)
    sqrt3 = math.sqrt(3)
    sqrt2 = math.sqrt(2)
    vis_i, hid_i = _project(shape,
                             (1 / sqrt3, 1 / sqrt3, 1 / sqrt3),
                             (-1 / sqrt2, 1 / sqrt2, 0))

    # -----------------------------------------------------------------------
    # Figure  (A3 landscape)
    # -----------------------------------------------------------------------
    fig_w = SHEET_W * MM_TO_IN
    fig_h = SHEET_H * MM_TO_IN
    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=300)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_xlim(0, SHEET_W)
    ax.set_ylim(0, SHEET_H)

    # --- Sheet background ---
    ax.add_patch(Rectangle((0, 0), SHEET_W, SHEET_H,
                            facecolor="white", edgecolor="none", zorder=0))

    # --- ISO 5457 border (margins L=20, T=10, R=10, B=10) ---
    ax.add_patch(Rectangle((20, 10), SHEET_W - 30, SHEET_H - 20,
                            linewidth=LW_THICK, edgecolor="black",
                            facecolor="none", zorder=20))

    # Outer trim frame
    ax.add_patch(Rectangle((0, 0), SHEET_W, SHEET_H,
                            linewidth=0.3, edgecolor="#aaaaaa",
                            facecolor="none", zorder=0))

    # --- Title block (bottom-right, 180×55 mm) ---
    TB_W, TB_H = 180.0, 55.0
    tb_x = SHEET_W - 10 - TB_W   # = 230
    tb_y = 10
    _title_block(ax, tb_x, tb_y, params)

    # --- Header strip ---
    header_y = SHEET_H - 10 - 8
    ax.add_patch(Rectangle((20, header_y), SHEET_W - 30, 8,
                            linewidth=0.3, edgecolor="black",
                            facecolor=COL_FILL, zorder=5))
    ax.text(SHEET_W / 2, header_y + 4,
            "TECHNICAL DRAWING — PARAMETRIC FIN-ARRAY HEAT SINK",
            fontsize=7, va="center", ha="center",
            fontweight="bold", fontfamily="monospace", zorder=6)
    ax.text(SHEET_W - 12, header_y + 4,
            DWG_NUMBER,
            fontsize=7, va="center", ha="right",
            fontweight="bold", fontfamily="monospace", zorder=6)

    # -----------------------------------------------------------------------
    # View placement (ISO first-angle)
    #
    # Drawing area for orthographic views: x=[22, 228], y=[67, 277]
    # Right zone (isometric + param table): x=[234, 408], y=[67, 277]
    #
    # First-angle rules:
    #   Top view   → placed BELOW front view
    #   Right view → placed LEFT of front view
    # -----------------------------------------------------------------------

    # Front view centre
    fc_x = 178.0
    fc_y = 190.0

    # Half extents on the sheet
    f_hw = cl * s / 2   # front half-width  = 50
    f_hh = th * s / 2   # front half-height = 25

    t_hw = cl * s / 2   # top half-width  = 50
    t_hh = tw * s / 2   # top half-height = 37

    r_hw = tw * s / 2   # right half-width  = 37
    r_hh = th * s / 2   # right half-height = 25

    VIEW_GAP = 18.0     # gap between view extents (for dim lines)

    # Top view centre (first-angle: BELOW front)
    tc_x = fc_x
    tc_y = fc_y - f_hh - VIEW_GAP - t_hh

    # Right side view centre (first-angle: LEFT of front)
    rc_x = fc_x - f_hw - VIEW_GAP - r_hw
    rc_y = fc_y

    # Isometric view centre (right zone)
    ic_x = 325.0
    ic_y = 180.0
    iso_scale = s * 0.85

    # -----------------------------------------------------------------------
    # Render views
    # -----------------------------------------------------------------------
    # Front view: flip_y because 2D_Y = -Pz (eye_dir=(0,-1,0), x_dir=(1,0,0))
    _view(ax, vis_f, hid_f, fc_x, fc_y, s, flip_y=True)
    _view_label(ax, fc_x, fc_y - f_hh, "FRONT VIEW  (A)")

    # Top view: flip_y so that y=0 (front edge) is at top, adjacent to front view
    _view(ax, vis_t, hid_t, tc_x, tc_y, s, flip_y=True)
    _view_label(ax, tc_x, tc_y - t_hh, "TOP VIEW  (B)")

    # Right side view: flip_x and flip_y for correct orientation
    # (eye along +X, x_dir=(0,-1,0) → 2D_X=-Py, 2D_Y=-Pz)
    _view(ax, vis_r, hid_r, rc_x, rc_y, s, flip_x=True, flip_y=True)
    _view_label(ax, rc_x, rc_y - r_hh, "RIGHT SIDE VIEW  (C)")

    # Isometric view
    _view(ax, vis_i, hid_i, ic_x, ic_y, iso_scale)
    _view_label(ax, ic_x, ic_y - 30, "ISOMETRIC VIEW  (D)")

    # -----------------------------------------------------------------------
    # Centre lines
    # -----------------------------------------------------------------------
    # Horizontal centre line across front view
    _cline(ax, fc_x - f_hw - 5, fc_y, fc_x + f_hw + 5, fc_y)
    # Vertical centre line
    _cline(ax, fc_x, fc_y - f_hh - 5, fc_x, fc_y + f_hh + 5)

    # -----------------------------------------------------------------------
    # Dimensions on FRONT VIEW
    # -----------------------------------------------------------------------
    # Overall length — below view
    _dim(ax,
         fc_x - f_hw, fc_y - f_hh,
         fc_x + f_hw, fc_y - f_hh,
         f"{cl:.0f}", offset=10, flip=True)

    # Total height — right of view
    _dim(ax,
         fc_x + f_hw, fc_y - f_hh,
         fc_x + f_hw, fc_y + f_hh,
         f"{th:.0f}", offset=10, flip=False)

    # Base height — right of view (inner dim, further offset)
    _dim(ax,
         fc_x + f_hw, fc_y - f_hh,
         fc_x + f_hw, fc_y - f_hh + bh * s,
         f"{bh:.0f}", offset=20, flip=False)

    # Fin height — right of view (inner dim, further offset)
    _dim(ax,
         fc_x + f_hw, fc_y - f_hh + bh * s,
         fc_x + f_hw, fc_y + f_hh,
         f"{fh:.0f}", offset=30, flip=False)

    # -----------------------------------------------------------------------
    # Dimensions on TOP VIEW
    # -----------------------------------------------------------------------
    # Overall width — left of top view  (tw = total fin-array width)
    # Top view: x maps to cl direction, y maps to tw direction (flipped)
    _dim(ax,
         tc_x - t_hw, tc_y + t_hh,
         tc_x - t_hw, tc_y - t_hh,
         f"{tw:.0f}", offset=10, flip=True)

    # Fin thickness (first fin) — right of top view
    # First fin occupies y = [0, ft] → on drawing (flip_y): [tc_y + t_hh, tc_y + t_hh - ft*s]
    y_top_front = tc_y + t_hh          # y=0 edge after flip
    y_first_fin_back = tc_y + t_hh - ft * s
    _dim(ax,
         tc_x + t_hw, y_top_front,
         tc_x + t_hw, y_first_fin_back,
         f"{ft:.0f}", offset=10, flip=False)

    # Fin spacing — right of top view
    y_first_ch_back = tc_y + t_hh - (ft + fs) * s
    _dim(ax,
         tc_x + t_hw, y_first_fin_back,
         tc_x + t_hw, y_first_ch_back,
         f"{fs:.0f}", offset=20, flip=False)

    # Fin pitch annotation
    _note(ax, tc_x + t_hw + 32, tc_y,
          f"PITCH = {pitch:.0f}  (× {fn} FINS)",
          ha="left", fontsize=4.5)

    # -----------------------------------------------------------------------
    # Dimensions on RIGHT SIDE VIEW
    # -----------------------------------------------------------------------
    # Total width — below right-side view
    _dim(ax,
         rc_x - r_hw, rc_y - r_hh,
         rc_x + r_hw, rc_y - r_hh,
         f"{tw:.0f}", offset=10, flip=True)

    # -----------------------------------------------------------------------
    # General notes
    # -----------------------------------------------------------------------
    note_x = tb_x + 2
    note_y = tb_y + TB_H + 4
    notes = [
        "NOTES:",
        f"1. ALL DIMS IN MILLIMETRES UNLESS OTHERWISE STATED.",
        f"2. GENERAL TOLERANCES: ISO 2768-m.",
        f"3. SURFACE ROUGHNESS: Ra 3.2 μm ALL SURFACES.",
        f"4. MATERIAL: {MATERIAL}.  BREAK ALL SHARP EDGES R0.2.",
        f"5. FINS ARE EQUALLY SPACED AT PITCH {pitch:.0f} mm.",
        f"6. {PROJECTION_STD}.",
    ]
    for i, note in enumerate(reversed(notes)):
        ax.text(note_x, note_y + i * 4.5, note,
                fontsize=4 if i > 0 else 4.5,
                va="bottom", ha="left",
                fontfamily="monospace",
                fontweight="bold" if i == 0 else "normal",
                color="black", zorder=5)

    # -----------------------------------------------------------------------
    # Parameter table (right zone, above isometric)
    # -----------------------------------------------------------------------
    _param_table(ax, 234, 278, params)

    # -----------------------------------------------------------------------
    # Zone markers  (ISO 5457 reference grid)
    # -----------------------------------------------------------------------
    zones_x = ["1", "2", "3", "4", "5", "6", "7", "8"]
    zones_y = ["A", "B", "C", "D"]
    n_x, n_y = len(zones_x), len(zones_y)
    cell_w = (SHEET_W - 30) / n_x   # ≈ 48.75
    cell_h = (SHEET_H - 20) / n_y   # ≈ 69.25
    for i, label in enumerate(zones_x):
        cx_zone = 20 + (i + 0.5) * cell_w
        for cy_zone, y_edge in [(SHEET_H - 10 - 4, SHEET_H - 10),
                                 (10 + 4, 10)]:
            ax.text(cx_zone, cy_zone, label,
                    fontsize=4, ha="center", va="center",
                    fontfamily="monospace", color="#888888", zorder=1)
    for j, label in enumerate(zones_y):
        cy_zone = 10 + (n_y - j - 0.5) * cell_h
        for cx_zone in [20 + 4, SHEET_W - 10 - 4]:
            ax.text(cx_zone, cy_zone, label,
                    fontsize=4, ha="center", va="center",
                    fontfamily="monospace", color="#888888", zorder=1)

    # -----------------------------------------------------------------------
    # Save
    # -----------------------------------------------------------------------
    pdf_path = dest / "heat_sink_drawing.pdf"
    svg_path = dest / "heat_sink_drawing.svg"

    fig.savefig(str(pdf_path), format="pdf", bbox_inches="tight")
    fig.savefig(str(svg_path), format="svg", bbox_inches="tight")
    print(f"PDF  →  {pdf_path}")
    print(f"SVG  →  {svg_path}")

    if show:
        plt.show()
    else:
        plt.close(fig)

    return str(pdf_path)


# ---------------------------------------------------------------------------
# Script entry-point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    generate_drawing()
