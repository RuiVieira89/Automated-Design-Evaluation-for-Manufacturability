"""Production drawing of the cold plate using OCCT Hidden-Line Removal + ezdxf.

No FreeCAD dependency.  Everything runs in the conda environment that has
PythonOCC and ezdxf installed.

Pipeline
--------
1. Build the 3D solid via :func:`build_cold_plate`.
2. For each of four views (front, top, right, isometric), run OCCT's
   ``HLRBRep_Algo`` to project the solid onto a 2D plane and extract
   visible and hidden edges separately.
3. Convert the projected edges to ezdxf entities (LINE, CIRCLE, ARC,
   LWPOLYLINE for curves).
4. Lay out the four views on an A3 landscape sheet at scale 1:1.
5. Add linear, diametric, and annotation dimensions derived from the known
   geometry parameters.  Dimension text is formatted with the tolerance
   value from :func:`get_default_tolerance`.
6. Draw a title block.
7. Save to DXF, then render to PDF via ``ezdxf.addons.drawing`` + Matplotlib.

Projection axes (third-angle projection)
-----------------------------------------
+---------+-----------------------------------+---------+-----------+
| View    | ``gp_Ax2`` main direction N       | Vx      | flip_y?   |
+=========+===================================+=========+===========+
| Front   | (0, −1, 0)   (camera at +Y)       | (1,0,0) | No        |
| Top     | (0,  0, −1)  (camera at +Z)       | (1,0,0) | Yes       |
| Right   | (−1, 0, 0)  (camera at +X)        | (0,1,0) | Yes       |
| Iso     | (1,  1,  1)  normalized            | (1,−1,0)| No        |
+---------+-----------------------------------+---------+-----------+

After HLR projection, ``flip_y=True`` negates the V coordinate before placing
on paper, so that +Z (up in 3-D) appears as +Y (up on sheet) in the top and
right views.

Output files
------------
* ``data/drawings/cold_plate_occt.dxf``
* ``data/drawings/cold_plate_occt.pdf``

Launch
------
::

    conda run -n auto_eval_manuf \\
        python examples/case/heat_sink_example_V3/cold_plate_drawing_occt_ezdxf.py
"""

from __future__ import annotations

import math
import sys
from datetime import date
from pathlib import Path
from typing import Callable

# ---------------------------------------------------------------------------
# Repo root on sys.path
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from examples.case.heat_sink_example_V3.cold_plate_cad import build_cold_plate
from examples.case.heat_sink_example_V3.drawing_tolerances import (
    Tolerance,
    get_default_tolerance,
)

import ezdxf
from ezdxf.addons.drawing import Frontend, RenderContext
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
import matplotlib
matplotlib.use("Agg")            # headless
import matplotlib.pyplot as plt

from OCC.Core.BRep import BRep_Builder
from OCC.Core.BRepAdaptor import BRepAdaptor_Curve
from OCC.Core.GeomAbs import GeomAbs_Circle, GeomAbs_Ellipse, GeomAbs_Line
from OCC.Core.HLRAlgo import HLRAlgo_Projector
from OCC.Core.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape
from OCC.Core.TopAbs import TopAbs_EDGE
from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopoDS import TopoDS_Compound
from OCC.Core.gp import gp_Ax2, gp_Dir, gp_Pnt

# ===========================================================================
# Cold-plate parameters
# ===========================================================================

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

# Drawing parameters
DRAWING_NUMBER = "CP-001"
PART_NAME      = "Cold Plate"
MATERIAL       = "Aluminium 6061-T6 (TBD)"
SURFACE_FINISH = "Ra 1.6 μm (TBD)"
SHEET_SIZE     = "A3"           # 420 × 297 mm landscape
SCALE_LABEL    = "1:1"          # nominal scale (1 unit in DXF = 1 mm in reality)

# Sheet dimensions (A3 landscape)
SHEET_W = 420.0   # mm
SHEET_H = 297.0   # mm

# Title block area (bottom strip)
TITLE_H = 40.0    # height of title block

# Outer border margin
MARGIN = 10.0

# View layout centres on the drawing sheet (mm from bottom-left)
#   Third-angle projection:  top view above front view,
#                            right view to the right of front view.
SCALE = 1.0   # scale factor (1:1)

_total_height = CP["base_height"] + max(CP["fin_height"], CP["wall_height"])
_bw2 = CP["base_width"]  / 2.0   # 40
_bl2 = CP["base_length"] / 2.0   # 50
_rw2 = CP["base_width"]  / 2.0   # right view width  half = world Y half
_rh2 = _total_height     / 2.0   # right view height half

# Paper positions of each view (centre of bounding box, mm from sheet origin)
# We derive them from the geometry so changing CP params auto-adjusts layout.
_HGAP = 25.0   # horizontal gap between views
_VGAP = 25.0   # vertical gap between views
_DIM  = 20.0   # extra space reserved for dimension lines

# Front view bbox half-extents
_fhl = _bl2                         # ±50  (u = world X)
_fhv = _total_height / 2.0          # ±7   (v = world Z, offset so bbox center at v=0)
# Top view bbox half-extents
_thl = _bl2                         # ±50  (u = world X)
_thv = CP["base_width"] / 2.0       # ±40  (drawing_v = world Y)
# Right view bbox half-extents
_rhl = _rw2                         # ±40  (u = world Y)
_rhv = _rh2                         # ±7

FRONT_C_X = MARGIN + _DIM + _fhl                               # 80
FRONT_C_Y = TITLE_H + _DIM + _rhv                              # 67

TOP_C_X   = FRONT_C_X
TOP_C_Y   = FRONT_C_Y + _fhv + _VGAP + _DIM + _thv            # 67+7+25+20+40=159

RIGHT_C_X = FRONT_C_X + _fhl + _HGAP + _DIM + _rhl            # 80+50+25+20+40=215
RIGHT_C_Y = FRONT_C_Y

ISO_C_X   = RIGHT_C_X + _rhl + _HGAP + 55.0                    # iso ~60 wide
ISO_C_Y   = TOP_C_Y

# Output paths
OUT_DIR   = ROOT / "data" / "drawings"
DXF_OUT   = OUT_DIR / "cold_plate_occt.dxf"
PDF_OUT   = OUT_DIR / "cold_plate_occt.pdf"


# ===========================================================================
# OCCT helpers
# ===========================================================================

def _make_compound(*shapes) -> TopoDS_Compound:
    """Return a compound containing all non-null shapes."""
    b = BRep_Builder()
    c = TopoDS_Compound()
    b.MakeCompound(c)
    for s in shapes:
        if s is not None and not s.IsNull():
            b.Add(c, s)
    return c


def project_view(shape, ax2: gp_Ax2):
    """Run HLR on *shape* with the given projector axes.

    Returns
    -------
    tuple[TopoDS_Compound, TopoDS_Compound]
        ``(visible_compound, hidden_compound)``
    """
    proj = HLRAlgo_Projector(ax2)
    algo = HLRBRep_Algo()
    algo.Add(shape)
    algo.Projector(proj)
    algo.Update()
    algo.Hide()
    ex = HLRBRep_HLRToShape(algo)
    vis = _make_compound(ex.VCompound(), ex.OutLineVCompound())
    hid = _make_compound(ex.HCompound(), ex.OutLineHCompound())
    return vis, hid


def extract_edges_2d(compound, n_approx: int = 24) -> list[dict]:
    """Extract 2D edge geometry from an HLR compound.

    All returned coordinates are in the HLR projector's XY plane (Z ≈ 0).

    Returns a list of dicts with key ``"type"`` and type-specific fields:

    * ``{"type": "line",  "p1": (x,y), "p2": (x,y)}``
    * ``{"type": "circle",  "center": (x,y), "r": r}``
    * ``{"type": "arc",     "center": (x,y), "r": r, "a1": deg, "a2": deg}``
    * ``{"type": "polyline","points": [(x,y), ...]}``
    """
    result: list[dict] = []
    if compound.IsNull():
        return result

    exp = TopExp_Explorer(compound, TopAbs_EDGE)
    while exp.More():
        edge = exp.Current()
        try:
            cur = BRepAdaptor_Curve(edge)
            t1, t2 = cur.FirstParameter(), cur.LastParameter()
            ct = cur.GetType()

            if ct == GeomAbs_Line:
                p1 = cur.Value(t1)
                p2 = cur.Value(t2)
                result.append({
                    "type": "line",
                    "p1": (p1.X(), p1.Y()),
                    "p2": (p2.X(), p2.Y()),
                })

            elif ct == GeomAbs_Circle:
                circ = cur.Circle()
                cx = circ.Location().X()
                cy = circ.Location().Y()
                r  = circ.Radius()
                span = abs(t2 - t1)
                if span >= 2.0 * math.pi - 1e-4:
                    result.append({"type": "circle", "center": (cx, cy), "r": r})
                else:
                    p1s = cur.Value(t1)
                    p2s = cur.Value(t2)
                    a1 = math.degrees(math.atan2(p1s.Y() - cy, p1s.X() - cx))
                    a2 = math.degrees(math.atan2(p2s.Y() - cy, p2s.X() - cx))
                    result.append({
                        "type": "arc",
                        "center": (cx, cy),
                        "r": r,
                        "a1": a1,
                        "a2": a2,
                    })

            elif ct == GeomAbs_Ellipse:
                # Approximate as polyline (isometric projection of circles)
                pts = []
                for j in range(n_approx + 1):
                    t = t1 + (t2 - t1) * j / n_approx
                    p = cur.Value(t)
                    pts.append((p.X(), p.Y()))
                result.append({"type": "polyline", "points": pts})

            else:
                # Generic curve — sample as polyline
                pts = []
                for j in range(n_approx + 1):
                    t = t1 + (t2 - t1) * j / n_approx
                    p = cur.Value(t)
                    pts.append((p.X(), p.Y()))
                result.append({"type": "polyline", "points": pts})

        except Exception:
            pass

        exp.Next()
    return result


# ===========================================================================
# 2D projection helpers
# ===========================================================================

def project_3d_point(x: float, y: float, z: float, ax2: gp_Ax2) -> tuple[float, float]:
    """Project a 3-D point onto the HLR projector plane.

    Returns ``(u, v)`` consistent with the coordinates in :func:`extract_edges_2d`.
    """
    loc = ax2.Location()
    dx  = x - loc.X()
    dy  = y - loc.Y()
    dz  = z - loc.Z()
    vx  = ax2.XDirection()
    vy  = ax2.YDirection()
    u   = dx * vx.X() + dy * vx.Y() + dz * vx.Z()
    v   = dx * vy.X() + dy * vy.Y() + dz * vy.Z()
    return u, v


def make_view_transform(
    paper_cx: float, paper_cy: float,
    hlr_cx: float,   hlr_cy: float,
    scale: float,
    flip_y: bool,
) -> Callable[[float, float], tuple[float, float]]:
    """Return a function ``f(u, v) → (px, py)`` that maps HLR coords to paper.

    *paper_cx / paper_cy*: paper position of the HLR bounding-box centre.
    *hlr_cx / hlr_cy*: bounding-box centre in HLR coords.
    *flip_y*: negate v before placing (needed for top and right views).
    """
    def _transform(u: float, v: float) -> tuple[float, float]:
        u_rel  = u - hlr_cx
        v_rel  = v - hlr_cy
        v_draw = -v_rel if flip_y else v_rel
        return paper_cx + u_rel * scale, paper_cy + v_draw * scale
    return _transform


# ===========================================================================
# DXF builders
# ===========================================================================

def _setup_dimstyle(doc: ezdxf.document.Drawing) -> None:
    """Create the ``ISODIM`` dimstyle used for all dimensions."""
    if "ISODIM" in doc.dimstyles:
        return
    ds = doc.dimstyles.new("ISODIM")
    ds.dxf.dimtxt  = 2.5     # text height [mm]
    ds.dxf.dimasz  = 2.0     # arrow size  [mm]
    ds.dxf.dimdec  = 1       # decimal places
    ds.dxf.dimexo  = 1.0     # ext-line offset
    ds.dxf.dimexe  = 1.5     # ext-line extension
    ds.dxf.dimgap  = 0.8     # gap between text and dim line


def add_edges_to_dxf(
    msp,
    edges: list[dict],
    transform: Callable[[float, float], tuple[float, float]],
    flip_y: bool,
    layer: str,
) -> int:
    """Add extracted 2D edges to *msp* and return the count added.

    Entities are created with **no explicit color** so they inherit the
    layer colour (BYLAYER).  Setting ``color=0`` (BYBLOCK) on entities
    placed directly in modelspace causes ezdxf's matplotlib renderer to
    treat them as the background colour, making them invisible on a white
    PDF.
    """
    n = 0
    attribs = {"layer": layer}  # BYLAYER colour — inherits from layer definition

    for e in edges:
        try:
            if e["type"] == "line":
                p1 = transform(*e["p1"])
                p2 = transform(*e["p2"])
                if math.dist(p1, p2) < 1e-6:
                    continue
                msp.add_line(p1, p2, dxfattribs=attribs)
                n += 1

            elif e["type"] == "circle":
                cx, cy = e["center"]
                pcx, pcy = transform(cx, cy)
                # Radius via a second point
                prx, _  = transform(cx + e["r"], cy)
                r_paper = abs(prx - pcx)
                if r_paper < 1e-6:
                    continue
                msp.add_circle((pcx, pcy), r_paper, dxfattribs=attribs)
                n += 1

            elif e["type"] == "arc":
                cx, cy = e["center"]
                pcx, pcy = transform(cx, cy)
                prx, _  = transform(cx + e["r"], cy)
                r_paper = abs(prx - pcx)
                if r_paper < 1e-6:
                    continue
                a1, a2 = e["a1"], e["a2"]
                if flip_y:
                    a1, a2 = -e["a2"], -e["a1"]
                msp.add_arc((pcx, pcy), r_paper, a1, a2, dxfattribs=attribs)
                n += 1

            elif e["type"] == "polyline":
                pts = [transform(u, v) for u, v in e["points"]]
                # Remove duplicate consecutive points
                pts = [pts[0]] + [
                    pts[i] for i in range(1, len(pts))
                    if math.dist(pts[i], pts[i - 1]) > 1e-6
                ]
                if len(pts) >= 2:
                    msp.add_lwpolyline(pts, dxfattribs=attribs)
                    n += 1
        except Exception:
            pass

    return n


def add_view_label(msp, label: str, cx: float, cy_top: float,
                   offset: float = 8.0) -> None:
    """Add a centred view label (e.g. 'FRONT') above the view."""
    msp.add_text(
        label,
        dxfattribs={
            "layer": "ANNOTATIONS",
            "height": 3.5,
            "style": "Standard",
            "halign": 1,   # centred
            "insert": (cx, cy_top + offset),
        },
    ).set_placement((cx, cy_top + offset), align=ezdxf.enums.TextEntityAlignment.MIDDLE_CENTER)


def _add_dim(
    msp,
    tol: Tolerance,
    base: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    value: float,
    angle: float = 0,
    layer: str = "DIMENSIONS",
) -> bool:
    """Add one linear dimension with tolerance text; return True on success."""
    text = tol.format_dim(value)
    try:
        dim = msp.add_linear_dim(
            base=base,
            p1=p1,
            p2=p2,
            angle=angle,
            text=text,
            dimstyle="ISODIM",
            dxfattribs={"layer": layer},
        )
        dim.render()
        return True
    except Exception as exc:
        print(f"  WARNING: could not place dimension {value:.4g}: {exc}")
        return False


def _add_diam_dim(
    msp,
    tol: Tolerance,
    center: tuple[float, float],
    radius: float,
    layer: str = "DIMENSIONS",
) -> bool:
    """Add a diametric dimension annotation for a circular feature."""
    text = tol.format_dim(2 * radius, decimals=1)
    try:
        mpoint = (center[0] + radius, center[1])
        dim = msp.add_diameter_dim(
            center=center,
            mpoint=mpoint,
            text=f"⌀{text}",
            dimstyle="ISODIM",
            dxfattribs={"layer": layer},
        )
        dim.render()
        return True
    except Exception as exc:
        print(f"  WARNING: could not place diameter dim r={radius:.4g}: {exc}")
        return False


def _add_note(
    msp,
    text: str,
    x: float,
    y: float,
    height: float = 2.5,
    layer: str = "ANNOTATIONS",
) -> None:
    """Add a single-line text annotation."""
    msp.add_text(
        text,
        dxfattribs={"layer": layer, "height": height},
    ).set_placement((x, y), align=ezdxf.enums.TextEntityAlignment.MIDDLE_LEFT)


# ===========================================================================
# Title block
# ===========================================================================

def add_title_block(
    msp,
    tol: Tolerance,
    part_name: str,
    drawing_number: str,
    scale_label: str,
    material: str,
    surface_finish: str,
    sheet_w: float,
    sheet_h: float,
    title_h: float,
) -> None:
    """Draw a title block in the bottom strip of the sheet."""
    layer = "TITLE_BLOCK"
    th    = title_h
    # Outer border
    msp.add_lwpolyline(
        [(0, 0), (sheet_w, 0), (sheet_w, th), (0, th), (0, 0)],
        close=True,
        dxfattribs={"layer": layer, "lineweight": 50},
    )

    # Vertical dividers
    cols = [sheet_w * 0.30, sheet_w * 0.55, sheet_w * 0.75, sheet_w]
    y_mid = th / 2.0

    for xc in cols[:-1]:
        msp.add_line((xc, 0), (xc, th), dxfattribs={"layer": layer})
    # Horizontal divider (top half / bottom half)
    for xc0, xc1 in zip([0] + cols[:-1], cols):
        msp.add_line((xc0, y_mid), (xc1, y_mid), dxfattribs={"layer": layer})

    def _text(text: str, x: float, y: float, ht: float = 2.5) -> None:
        msp.add_text(
            text,
            dxfattribs={"layer": layer, "height": ht},
        ).set_placement((x, y), align=ezdxf.enums.TextEntityAlignment.MIDDLE_LEFT)

    # Column 1: part name + description
    _text(f"PART: {part_name}",     2, y_mid + th * 0.25,  ht=4.0)
    _text(f"DRG NO: {drawing_number}", 2, y_mid - th * 0.25, ht=3.0)

    # Column 2: material + finish
    _text(f"MATERIAL: {material}",       cols[0] + 2, y_mid + th * 0.25)
    _text(f"FINISH: {surface_finish}",   cols[0] + 2, y_mid - th * 0.25)

    # Column 3: scale, date, projection
    _text(f"SCALE: {scale_label}",       cols[1] + 2, y_mid + th * 0.25)
    _text(f"DATE: {date.today():%Y-%m-%d}", cols[1] + 2, y_mid - th * 0.25)
    _text("PROJECTION: 3rd ANGLE",       cols[1] + 2, 2)

    # Column 4: tolerance note + units
    _text(tol.format_general_note(),     cols[2] + 2, y_mid + th * 0.25)
    _text("UNITS: mm",                   cols[2] + 2, y_mid - th * 0.25)


# ===========================================================================
# Sheet border
# ===========================================================================

def add_sheet_border(msp, sheet_w: float, sheet_h: float,
                     title_h: float, margin: float) -> None:
    """Draw the outer sheet border and inner drawing frame."""
    msp.add_lwpolyline(
        [(0, 0), (sheet_w, 0), (sheet_w, sheet_h), (0, sheet_h), (0, 0)],
        close=True,
        dxfattribs={"layer": "BORDER", "lineweight": 50},
    )
    msp.add_lwpolyline(
        [
            (margin, title_h + margin),
            (sheet_w - margin, title_h + margin),
            (sheet_w - margin, sheet_h - margin),
            (margin, sheet_h - margin),
            (margin, title_h + margin),
        ],
        close=True,
        dxfattribs={"layer": "BORDER"},
    )


# ===========================================================================
# Main drawing function
# ===========================================================================

def build_drawing() -> tuple[Path, Path]:
    """Build the cold-plate drawing and write DXF + PDF.

    Returns
    -------
    tuple[Path, Path]
        ``(dxf_path, pdf_path)``
    """
    tol = get_default_tolerance()
    print(f"  Tolerance: {tol.format_suffix()} (from get_default_tolerance())")

    # ------------------------------------------------------------------
    # 1. Build 3-D solid
    # ------------------------------------------------------------------
    print("  Building cold plate …")
    result = build_cold_plate(**CP)
    solid  = result["solid"]

    # ------------------------------------------------------------------
    # 2. Define projector axes (see module docstring for convention)
    # ------------------------------------------------------------------
    # Front (camera at +Y, looking toward −Y; +X right, +Z up)
    ax_front = gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, -1, 0), gp_Dir(1, 0, 0))
    # Top (camera at +Z, looking toward −Z; +X right)
    ax_top   = gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, -1), gp_Dir(1, 0, 0))
    # Right (camera at +X, looking toward −X; world +Y right, flip Y needed)
    ax_right = gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(-1, 0, 0), gp_Dir(0, 1, 0))
    # Isometric (looking from (1,1,1))
    ax_iso   = gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(1, 1, 1),  gp_Dir(1, -1, 0))

    # ------------------------------------------------------------------
    # 3. Run HLR for all views
    # ------------------------------------------------------------------
    print("  Running HLR projections …")
    vis_front, hid_front = project_view(solid, ax_front)
    vis_top,   hid_top   = project_view(solid, ax_top)
    vis_right, hid_right = project_view(solid, ax_right)
    vis_iso,   _         = project_view(solid, ax_iso)   # iso: visible only

    # ------------------------------------------------------------------
    # 4. Extract 2-D edges
    # ------------------------------------------------------------------
    print("  Extracting 2-D edges …")
    ef = extract_edges_2d(vis_front)
    ef_h = extract_edges_2d(hid_front)
    et = extract_edges_2d(vis_top)
    et_h = extract_edges_2d(hid_top)
    er = extract_edges_2d(vis_right)
    er_h = extract_edges_2d(hid_right)
    ei = extract_edges_2d(vis_iso)

    # ------------------------------------------------------------------
    # 5. Build ezdxf document
    # ------------------------------------------------------------------
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4    # mm
    msp = doc.modelspace()

    # Layers
    # Color 7 = "white/black" — DXF viewers and ezdxf's matplotlib backend
    # render it as BLACK when the background is white, so it is always
    # visible on a white PDF without hard-coding an RGB black.
    # Color 8 = medium-dark grey  (used for hidden/dashed lines — subtle but legible).
    # Color 1 = red               (industry standard for centre lines).
    _layers = {
        "BORDER":      (7,                  "Continuous"),  # black on white
        "VISIBLE":     (7,                  "Continuous"),  # black on white
        "HIDDEN":      (8,                  "DASHED"),      # grey dashed
        "DIMENSIONS":  (7,                  "Continuous"),  # black on white
        "ANNOTATIONS": (7,                  "Continuous"),  # black on white
        "TITLE_BLOCK": (7,                  "Continuous"),  # black on white
        "CENTERLINES": (ezdxf.colors.RED,   "CENTER"),      # red centre marks
    }
    for name, (color, lt) in _layers.items():
        doc.layers.new(name, dxfattribs={"color": color, "linetype": lt})

    _setup_dimstyle(doc)

    # ------------------------------------------------------------------
    # 6. Sheet border + title block
    # ------------------------------------------------------------------
    add_sheet_border(msp, SHEET_W, SHEET_H, TITLE_H, MARGIN)
    add_title_block(
        msp, tol,
        part_name=PART_NAME,
        drawing_number=DRAWING_NUMBER,
        scale_label=SCALE_LABEL,
        material=MATERIAL,
        surface_finish=SURFACE_FINISH,
        sheet_w=SHEET_W,
        sheet_h=SHEET_H,
        title_h=TITLE_H,
    )

    # ------------------------------------------------------------------
    # 7. Place view edges with transforms
    # ------------------------------------------------------------------
    # Geometry constants
    bl  = CP["base_length"]
    bw  = CP["base_width"]
    bh  = CP["base_height"]
    fh  = CP["fin_height"]
    ft  = CP["fin_thickness"]
    fs  = CP["fin_spacing"]
    fn  = CP["fin_number"]
    cl  = CP["channel_length"]
    wt  = CP["wall_thickness"]
    wh  = CP["wall_height"]
    wi  = CP["wall_inset"]
    cr  = CP["corner_radius"]
    shd = CP["screw_hole_diameter"]
    phd = CP["pin_hole_diameter"]
    sh_pos = CP["screw_hole_positions"]
    ph_pos = CP["pin_hole_positions"]
    z_top = bh + max(fh, wh)    # top of tallest feature

    # HLR bounding-box centres (used to align views on paper)
    # Front: u ∈ [-bl/2, bl/2], v ∈ [0, z_top]  → hlr centre = (0, z_top/2)
    # Top:   u ∈ [-bl/2, bl/2], v ∈ [-bw/2, bw/2] → hlr centre = (0, 0)
    # Right: u ∈ [-bw/2, bw/2], v ∈ [-z_top, 0]  → hlr centre = (0, -z_top/2)
    # Iso:   compute after extraction

    tf_front = make_view_transform(FRONT_C_X, FRONT_C_Y, 0, z_top / 2,  SCALE, False)
    tf_top   = make_view_transform(TOP_C_X,   TOP_C_Y,   0, 0,           SCALE, True)
    tf_right = make_view_transform(RIGHT_C_X, RIGHT_C_Y, 0, -z_top / 2, SCALE, True)

    # Iso: compute bbox centre from extracted edges
    all_iso_pts = [(p[0], p[1]) for e in ei for p in (
        [e["p1"], e["p2"]] if e["type"] == "line" else
        e.get("points", [])
    )]
    if all_iso_pts:
        ux = [p[0] for p in all_iso_pts]
        uy = [p[1] for p in all_iso_pts]
        iso_hlr_cx = (min(ux) + max(ux)) / 2
        iso_hlr_cy = (min(uy) + max(uy)) / 2
    else:
        iso_hlr_cx, iso_hlr_cy = 0.0, 0.0
    tf_iso = make_view_transform(ISO_C_X, ISO_C_Y, iso_hlr_cx, iso_hlr_cy, SCALE, False)

    # Add edges
    n_vis = 0
    n_hid = 0
    n_vis += add_edges_to_dxf(msp, ef,   tf_front, False, "VISIBLE")
    n_hid += add_edges_to_dxf(msp, ef_h, tf_front, False, "HIDDEN")
    n_vis += add_edges_to_dxf(msp, et,   tf_top,   True,  "VISIBLE")
    n_hid += add_edges_to_dxf(msp, et_h, tf_top,   True,  "HIDDEN")
    n_vis += add_edges_to_dxf(msp, er,   tf_right, True,  "VISIBLE")
    n_hid += add_edges_to_dxf(msp, er_h, tf_right, True,  "HIDDEN")
    n_vis += add_edges_to_dxf(msp, ei,   tf_iso,   False, "VISIBLE")

    # View labels
    add_view_label(msp, "FRONT VIEW",   FRONT_C_X, FRONT_C_Y + z_top / 2)
    add_view_label(msp, "TOP VIEW",     TOP_C_X,   TOP_C_Y   + bw / 2)
    add_view_label(msp, "RIGHT VIEW",   RIGHT_C_X, RIGHT_C_Y + z_top / 2)
    add_view_label(msp, "ISOMETRIC",    ISO_C_X,   ISO_C_Y   + 50)

    # ------------------------------------------------------------------
    # 8. Dimensions
    #
    #   All dimension endpoints are computed by projecting known 3-D
    #   geometry points through the same HLR axes — more robust than
    #   identifying edges from the HLR compound.
    # ------------------------------------------------------------------
    n_dims = 0

    # Helper: project a world point using the same ax2 and then transform to paper
    def front_pt(x, y, z):
        return tf_front(*project_3d_point(x, y, z, ax_front))

    def top_pt(x, y, z):
        u, v = project_3d_point(x, y, z, ax_top)
        return tf_top(u, v)

    def right_pt(x, y, z):
        u, v = project_3d_point(x, y, z, ax_right)
        return tf_right(u, v)

    DIM_OFF = 12.0    # perpendicular offset for dimension lines [mm]
    DIM_OFF2 = 22.0
    DIM_OFF3 = 32.0

    # ── Front view dimensions ──────────────────────────────────────────

    # base_length (horizontal, below bottom of base)
    p1 = front_pt(-bl / 2, 0, 0)
    p2 = front_pt( bl / 2, 0, 0)
    by = min(p1[1], p2[1]) - DIM_OFF
    n_dims += _add_dim(msp, tol, (FRONT_C_X, by), p1, p2, bl, angle=0)

    # channel_length (horizontal, further below)
    p1c = front_pt(-cl / 2, 0, 0)
    p2c = front_pt( cl / 2, 0, 0)
    by2 = min(p1[1], p2[1]) - DIM_OFF2
    n_dims += _add_dim(msp, tol, (FRONT_C_X, by2), p1c, p2c, cl, angle=0)

    # base_height (vertical, to the left of the front view)
    p1 = front_pt(-bl / 2, 0, 0)
    p2 = front_pt(-bl / 2, 0, bh)
    lx = min(p1[0], p2[0]) - DIM_OFF
    n_dims += _add_dim(msp, tol, (lx, FRONT_C_Y), p1, p2, bh, angle=90)

    # wall_height (vertical, further left)
    if wh > 0:
        p1w = front_pt(-bl / 2, 0, bh)
        p2w = front_pt(-bl / 2, 0, bh + wh)
        lx2 = min(p1[0], p2[0]) - DIM_OFF2
        n_dims += _add_dim(msp, tol, (lx2, FRONT_C_Y + bh + wh / 2), p1w, p2w, wh, angle=90)

    # fin_height (vertical, to the right)
    p1f = front_pt(bl / 2, 0, bh)
    p2f = front_pt(bl / 2, 0, bh + fh)
    rx  = max(p1f[0], p2f[0]) + DIM_OFF
    n_dims += _add_dim(msp, tol, (rx, FRONT_C_Y + bh + fh / 2), p1f, p2f, fh, angle=90)

    # total height (further right, arrow pointing from z=0 to z=z_top)
    p1z = front_pt(bl / 2, 0, 0)
    p2z = front_pt(bl / 2, 0, z_top)
    rx2 = max(p1f[0], p2f[0]) + DIM_OFF2
    n_dims += _add_dim(msp, tol, (rx2, FRONT_C_Y), p1z, p2z, z_top, angle=90)

    # fin_thickness note (annotation — too narrow to dimension individually)
    ft_px, ft_py = tf_front(0, z_top / 2)
    _add_note(msp, f"FIN T={ft:g} SP={fs:g} N={fn}", ft_px + 5, ft_py + 5)

    # ── Top view dimensions ────────────────────────────────────────────

    # base_width (vertical dimension in top view = world Y extent)
    p1 = top_pt(0, -bw / 2, 0)
    p2 = top_pt(0,  bw / 2, 0)
    tx = min(p1[0], p2[0]) - DIM_OFF
    n_dims += _add_dim(msp, tol, (tx, TOP_C_Y), p1, p2, bw, angle=90)

    # base_length (horizontal in top view = world X extent)
    p1 = top_pt(-bl / 2, 0, 0)
    p2 = top_pt( bl / 2, 0, 0)
    ty_top = max(p1[1], p2[1]) + DIM_OFF
    n_dims += _add_dim(msp, tol, (TOP_C_X, ty_top), p1, p2, bl, angle=0)

    # wall_thickness (annotation — narrow feature)
    if wh > 0:
        _add_note(msp, f"WALL T={wt:g} H={wh:g} INSET={wi:g}", TOP_C_X + bl / 2 + 5, TOP_C_Y)

    # corner_radius (annotation)
    _add_note(msp, f"R={cr:g} (4×)", TOP_C_X - bl / 2 - 30, TOP_C_Y + bw / 2 + 5)

    # Screw holes: annotate position and diameter
    for i, (sx, sy) in enumerate(sh_pos):
        px, py = top_pt(sx, sy, 0)
        # Center mark
        msp.add_line((px - 3, py), (px + 3, py),
                     dxfattribs={"layer": "CENTERLINES"})
        msp.add_line((px, py - 3), (px, py + 3),
                     dxfattribs={"layer": "CENTERLINES"})
    # Screw hole diameter dimension (using first hole)
    if sh_pos:
        sx0, sy0 = sh_pos[0]
        scx, scy = top_pt(sx0, sy0, 0)
        r_screw  = shd / 2.0
        _add_diam_dim(msp, tol, (scx, scy), r_screw)
        n_dims += 1
    _add_note(msp, f"⌀{shd:g} ±{tol.plus:g} × {len(sh_pos)} HOLES",
              TOP_C_X, TOP_C_Y - bw / 2 - 15)

    # Screw hole X and Y positions
    if sh_pos:
        sx0, sy0 = sh_pos[0]  # bottom-left hole
        p_orig   = top_pt(0, 0, 0)             # origin (base center)
        p_hole   = top_pt(sx0, 0, 0)           # same Y
        p_holeY  = top_pt(0,  sy0, 0)
        by_sh    = top_pt(sx0, sy0, 0)[1] - DIM_OFF
        _add_dim(msp, tol, (top_pt(sx0, 0, 0)[0], by_sh),
                 p_orig, top_pt(sx0, 0, 0), abs(sx0), angle=0)
        bx_sh = top_pt(sx0, sy0, 0)[0] - DIM_OFF
        _add_dim(msp, tol, (bx_sh, top_pt(0, sy0, 0)[1]),
                 p_orig, top_pt(0, sy0, 0), abs(sy0), angle=90)
        n_dims += 2

    # Pin holes
    for px_, py_ in ph_pos:
        ppcx, ppcy = top_pt(px_, py_, 0)
        msp.add_line((ppcx - 3, ppcy), (ppcx + 3, ppcy),
                     dxfattribs={"layer": "CENTERLINES"})
        msp.add_line((ppcx, ppcy - 3), (ppcx, ppcy + 3),
                     dxfattribs={"layer": "CENTERLINES"})
    _add_note(msp, f"⌀{phd:g} ±{tol.plus:g} PIN HOLES × {len(ph_pos)}",
              TOP_C_X + 5, TOP_C_Y + bw / 2 + 10)

    # ── Right view dimensions ──────────────────────────────────────────

    # base_width (horizontal in right view = world Y extent)
    p1 = right_pt(0, -bw / 2, 0)
    p2 = right_pt(0,  bw / 2, 0)
    ry = min(p1[1], p2[1]) - DIM_OFF
    n_dims += _add_dim(msp, tol, (RIGHT_C_X, ry), p1, p2, bw, angle=0)

    # Total height (vertical in right view = world Z extent)
    p1 = right_pt(0, -bw / 2, 0)
    p2 = right_pt(0, -bw / 2, z_top)
    rx = min(p1[0], p2[0]) - DIM_OFF
    n_dims += _add_dim(msp, tol, (rx, RIGHT_C_Y), p1, p2, z_top, angle=90)

    # ------------------------------------------------------------------
    # 9. Scale and projection note
    # ------------------------------------------------------------------
    _add_note(msp, f"SCALE {SCALE_LABEL} — THIRD-ANGLE PROJECTION",
              MARGIN + 5, TITLE_H + MARGIN + 5, height=2.5)

    # ------------------------------------------------------------------
    # 10. Save DXF
    # ------------------------------------------------------------------
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    doc.saveas(str(DXF_OUT))
    print(f"  DXF saved → {DXF_OUT}")

    # ------------------------------------------------------------------
    # 11. Render to PDF via ezdxf + Matplotlib
    # ------------------------------------------------------------------
    fig = plt.figure(figsize=(SHEET_W / 25.4, SHEET_H / 25.4), dpi=150)
    ax  = fig.add_axes([0, 0, 1, 1])
    ax.set_aspect("equal")
    ax.set_axis_off()

    ctx = RenderContext(doc)
    # Declare a white background so colour-7 entities (VISIBLE, DIMENSIONS,
    # ANNOTATIONS, etc.) are rendered as black rather than white.
    try:
        from ezdxf.addons.drawing.properties import LayoutProperties
        lp = LayoutProperties.from_layout(msp)
        lp.set_colors("#FFFFFF")          # white paper
        out = MatplotlibBackend(ax)
        Frontend(ctx, out).draw_layout(msp, finalize=True,
                                       layout_properties=lp)
    except Exception:
        # Fallback for older ezdxf versions that don't expose LayoutProperties
        out = MatplotlibBackend(ax)
        Frontend(ctx, out).draw_layout(msp)

    fig.savefig(str(PDF_OUT), dpi=150, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.close(fig)
    print(f"  PDF saved → {PDF_OUT}")

    # ------------------------------------------------------------------
    # 12. Summary
    # ------------------------------------------------------------------
    print("\n  ┌─ Summary ─────────────────────────────────────────────")
    print(f"  │  Views generated  : 4 (front, top, right, isometric)")
    print(f"  │  Visible edges    : {n_vis}")
    print(f"  │  Hidden edges     : {n_hid}")
    print(f"  │  Dimensions placed: {n_dims}")
    print(f"  │  Tolerance used   : {tol.format_suffix()} (from get_default_tolerance())")
    print(f"  │  DXF              : {DXF_OUT}")
    print(f"  │  PDF              : {PDF_OUT}")
    print("  └──────────────────────────────────────────────────────")

    return DXF_OUT, PDF_OUT


# ===========================================================================
# Entry point
# ===========================================================================
if __name__ == "__main__":
    build_drawing()
