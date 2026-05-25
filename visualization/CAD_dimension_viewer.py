"""Interactive 3D dimension viewer for minimal drawing dimension sets.

Renders the actual tessellated CAD solid in a rotatable PyVista window and
overlays every DimensionEntry as a double-headed arrow running from the
measured start point to the end point, labelled with ``nominal ±tolerance``.

Arrow colour encodes priority:
  red  — critical  (at or beyond process capability)
  blue — important  (primary drawing dimension)
  grey — informational

Usage — library
---------------
    from visualization.CAD_dimension_viewer import view_dimensions
    view_dimensions(solid_shape, solid_dims, mds)

Usage — CLI  (requires pythonocc-core for STEP loading)
--------------------------------------------------------
    python visualization/CAD_dimension_viewer.py
    python visualization/CAD_dimension_viewer.py data/part.step --process CNC_milling
    python visualization/CAD_dimension_viewer.py data/part.step --solid 1
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pyvista as pv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from post_process.dimension_minimal import DimensionEntry, MinimalDimensionSet
from post_process.shape_dimension import CylindricalFeature, PlaneGroup, SolidDimensions
from visualization.viewer import shape_to_pyvista

# ── visual constants ───────────────────────────────────────────────────────────

_PRIORITY_COLOR: Dict[str, str] = {
    "critical":      "#d62728",
    "important":     "#1f77b4",
    "informational": "#7f7f7f",
}
_EXT_COLOR   = "#bbbbbb"
_STANDOFF    = 0.20
# Arrowhead height as a fraction of the bounding-box diagonal; clamped per arrow.
_AH_DIAG_FRAC = 0.018
_AH_RADIUS_FRAC = 0.30   # cone base radius as fraction of cone height


# ══════════════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════════════

def view_dimensions(
    shape,
    solid_dims: SolidDimensions,
    mds: MinimalDimensionSet,
    title: str = "",
    show: bool = True,
    deflection: float = 0.05,
) -> pv.Plotter:
    """Render the tessellated CAD solid with dimension annotations.

    Parameters
    ----------
    shape:
        ``TopoDS_Shape`` for the solid to display (e.g. from
        :func:`~post_process.shape_normalizer.extract_solids`).
    solid_dims:
        Geometry metadata — bounding box, cylinders, plane groups.
    mds:
        Minimal dimension set from
        :func:`~post_process.dimension_minimal.minimal_dimensions`.
    title:
        Optional window title override.
    show:
        Call ``pl.show()`` when *True*.  Set *False* for testing or embedding.
    deflection:
        Linear deflection for tessellation (smaller → finer mesh).

    Returns
    -------
    pv.Plotter
    """
    pl = pv.Plotter(window_size=[1400, 900])
    pl.set_background("white")

    bb  = solid_dims.bounding_box
    off = _standoff(bb)
    ah  = _arrowhead_size(bb)

    # ── render the actual CAD solid ──
    mesh = shape_to_pyvista(shape, deflection=deflection)
    pl.add_mesh(
        mesh,
        color="#c8c8c8",
        opacity=0.70,
        show_edges=True,
        edge_color="#888888",
        line_width=0.4,
        smooth_shading=True,
    )

    # ── build geometry look-up tables ──
    cyl_by_fid: Dict[int, CylindricalFeature] = {
        c.face_id: c for c in solid_dims.cylinders
    }
    pg_by_fid: Dict[int, PlaneGroup] = {}
    for pg in solid_dims.plane_groups:
        for fid in pg.face_ids:
            pg_by_fid[fid] = pg

    axis_map = _build_axis_map(bb)

    # ── draw dimension arrows ──
    for dim in mds.dimensions:
        color = _PRIORITY_COLOR.get(dim.priority, "#7f7f7f")
        result = _resolve(dim, solid_dims, axis_map, cyl_by_fid, pg_by_fid, bb, off)
        if result is None:
            continue
        pt1, pt2, ext_segs = result
        _draw_extension_lines(pl, ext_segs)
        _draw_dim_arrow(pl, pt1, pt2, dim.drawing_annotation(), color, ah)

    _setup_camera(pl, bb, off)
    _add_info(pl, mds)

    title_str = title or (
        f"Solid {mds.solid_id}  ·  {mds.process}"
        f"  ·  {mds.it_grade} ({mds.process_class})"
        f"  ·  {mds.count()} dims  ·  drag to rotate"
    )
    pl.add_text(title_str, position="upper_edge", font_size=9, color="black")

    if show:
        pl.show(title="Dimension Viewer")

    return pl


# ══════════════════════════════════════════════════════════════════════════════
# Endpoint resolution  (pure geometry — no rendering dependency)
# ══════════════════════════════════════════════════════════════════════════════

def _resolve(
    dim: DimensionEntry,
    sd: SolidDimensions,
    axis_map: dict,
    cyl_by_fid: dict,
    pg_by_fid: dict,
    bb: tuple,
    off: float,
) -> Optional[Tuple[np.ndarray, np.ndarray, List]]:
    kind = dim.kind
    fid0 = dim.face_ids[0] if dim.face_ids else None

    if kind in ("length", "width", "height"):
        return _resolve_overall(dim, axis_map, bb, off)
    if kind == "diameter":
        cyl = cyl_by_fid.get(fid0)
        return _resolve_diameter(cyl, bb) if cyl else None
    if kind == "depth":
        cyl = cyl_by_fid.get(fid0)
        return _resolve_depth(cyl, bb) if cyl else None
    if kind in ("position_x", "position_y", "position_z"):
        cyl = cyl_by_fid.get(fid0)
        return _resolve_position(kind, cyl, bb) if cyl else None
    if kind == "wall_thickness":
        fid1 = dim.face_ids[1] if len(dim.face_ids) > 1 else None
        pg   = pg_by_fid.get(fid0)
        if pg is None or fid1 is None:
            return None
        return _resolve_wall(pg, fid0, fid1, bb)
    return None


def _resolve_overall(dim, axis_map, bb, off):
    xmin, ymin, zmin, xmax, ymax, zmax = bb
    info = axis_map.get(dim.kind)
    if info is None:
        return None
    axis_char, lo, hi = info

    if axis_char == "x":
        y0, z0 = ymin - off, zmin - off
        pt1 = np.array([xmin, y0, z0])
        pt2 = np.array([xmax, y0, z0])
        ext = [
            (np.array([xmin, ymin, z0]), pt1),
            (np.array([xmax, ymin, z0]), pt2),
        ]
    elif axis_char == "y":
        x0, z0 = xmax + off, zmin - off
        pt1 = np.array([x0, ymin, z0])
        pt2 = np.array([x0, ymax, z0])
        ext = [
            (np.array([xmax, ymin, z0]), pt1),
            (np.array([xmax, ymax, z0]), pt2),
        ]
    else:
        x0, y0 = xmax + off, ymin - off
        pt1 = np.array([x0, y0, zmin])
        pt2 = np.array([x0, y0, zmax])
        ext = [
            (np.array([xmax, y0, zmin]), pt1),
            (np.array([xmax, y0, zmax]), pt2),
        ]

    return pt1, pt2, ext


def _resolve_diameter(cyl: CylindricalFeature, bb: tuple):
    cx, cy, cz = cyl.center
    r  = cyl.radius_est
    ax = cyl.axis

    if ax == "z":
        pt1 = np.array([cx - r, cy, cz])
        pt2 = np.array([cx + r, cy, cz])
    elif ax == "x":
        pt1 = np.array([cx, cy - r, cz])
        pt2 = np.array([cx, cy + r, cz])
    else:
        pt1 = np.array([cx, cy, cz - r])
        pt2 = np.array([cx, cy, cz + r])

    return pt1, pt2, []


def _resolve_depth(cyl: CylindricalFeature, bb: tuple):
    cx, cy, cz = cyl.center
    ax  = cyl.axis
    r   = cyl.radius_est
    cbx = cyl.bounding_box
    SIDE_OFF = r * 0.6

    if ax == "z":
        xoff = cx + r + SIDE_OFF
        pt1  = np.array([xoff, cy, cbx[2]])
        pt2  = np.array([xoff, cy, cbx[5]])
        ext  = [
            (np.array([cx, cy, cbx[2]]), pt1),
            (np.array([cx, cy, cbx[5]]), pt2),
        ]
    elif ax == "x":
        yoff = cy + r + SIDE_OFF
        pt1  = np.array([cbx[0], yoff, cz])
        pt2  = np.array([cbx[3], yoff, cz])
        ext  = [
            (np.array([cbx[0], cy, cz]), pt1),
            (np.array([cbx[3], cy, cz]), pt2),
        ]
    else:
        xoff = cx + r + SIDE_OFF
        pt1  = np.array([xoff, cbx[1], cz])
        pt2  = np.array([xoff, cbx[4], cz])
        ext  = [
            (np.array([cx, cbx[1], cz]), pt1),
            (np.array([cx, cbx[4], cz]), pt2),
        ]

    return pt1, pt2, ext


def _resolve_position(kind: str, cyl: CylindricalFeature, bb: tuple):
    xmin, ymin, zmin, xmax, ymax, zmax = bb
    cx, cy, cz = cyl.center
    r   = cyl.radius_est
    cbx = cyl.bounding_box
    cz_mid = (cbx[2] + cbx[5]) / 2.0

    if kind == "position_x":
        z_off = cz_mid - r * 0.3
        pt1 = np.array([xmin, cy, z_off])
        pt2 = np.array([cx,   cy, z_off])
        ext = [(np.array([cx, cy, cz_mid]), pt2)]
    elif kind == "position_y":
        z_off = cz_mid + r * 0.3
        pt1 = np.array([cx, ymin, z_off])
        pt2 = np.array([cx, cy,   z_off])
        ext = [(np.array([cx, cy, cz_mid]), pt2)]
    else:
        pt1 = np.array([cx + r * 1.2, cy, zmin])
        pt2 = np.array([cx + r * 1.2, cy, cz])
        ext = [(np.array([cx, cy, cz]), pt2)]

    return pt1, pt2, ext


def _resolve_wall(pg: PlaneGroup, fid1: int, fid2: int, bb: tuple):
    n    = np.array(pg.normal, float)
    norm = np.linalg.norm(n)
    if norm < 1e-9:
        return None
    n /= norm

    xmin, ymin, zmin, xmax, ymax, zmax = bb
    c = np.array([(xmin + xmax) / 2, (ymin + ymax) / 2, (zmin + zmax) / 2])

    pos_map = dict(zip(pg.face_ids, pg.positions))
    p1 = pos_map.get(fid1)
    p2 = pos_map.get(fid2)
    if p1 is None or p2 is None:
        return None

    c_proj = float(np.dot(c, n))
    pt1 = c + (p1 - c_proj) * n
    pt2 = c + (p2 - c_proj) * n

    return pt1, pt2, []


# ══════════════════════════════════════════════════════════════════════════════
# PyVista drawing primitives
# ══════════════════════════════════════════════════════════════════════════════

def _draw_dim_arrow(
    pl: pv.Plotter,
    pt1: np.ndarray,
    pt2: np.ndarray,
    label: str,
    color: str,
    ah: float,
) -> None:
    """Draw a double-headed dimension arrow with a label.

    *ah* is the global arrowhead height computed from the bounding-box diagonal.
    It is clamped so it never exceeds 35 % of the arrow length.
    """
    vec    = pt2 - pt1
    length = float(np.linalg.norm(vec))
    if length < 1e-9:
        return

    unit  = vec / length
    ah    = min(ah, length * 0.35)   # never overwhelm a short arrow
    r_tip = ah * _AH_RADIUS_FRAC

    # Dimension line
    pl.add_mesh(pv.Line(pt1, pt2), color=color, line_width=1.0)

    # Arrowhead at pt1: tip at pt1, body extends outside (away from pt2).
    # pv.Cone: tip = center + direction_hat * height/2  →  center = pt1 - unit*ah/2
    pl.add_mesh(
        pv.Cone(center=pt1 - unit * (ah / 2), direction=unit,
                height=ah, radius=r_tip, resolution=16, capping=True),
        color=color,
    )

    # Arrowhead at pt2: tip at pt2, center = pt2 + unit*ah/2
    pl.add_mesh(
        pv.Cone(center=pt2 + unit * (ah / 2), direction=-unit,
                height=ah, radius=r_tip, resolution=16, capping=True),
        color=color,
    )

    # Label at midpoint offset perpendicular to the arrow
    mid  = (pt1 + pt2) / 2.0
    perp = _perp_offset(unit, length * 0.08)
    pl.add_point_labels(
        [mid + perp],
        [label],
        font_size=9,
        text_color=color,
        show_points=False,
        always_visible=True,
        shape="rounded_rect",
        shape_color="white",
        shape_opacity=0.88,
        fill_shape=True,
    )


def _draw_extension_lines(pl: pv.Plotter, segments: List) -> None:
    """Batch all extension line segments into a single PolyData."""
    if not segments:
        return
    pts_list: List[np.ndarray] = []
    lines: List[int] = []
    idx = 0
    for a, b in segments:
        pts_list.extend([np.asarray(a, float), np.asarray(b, float)])
        lines.extend([2, idx, idx + 1])
        idx += 2
    mesh = pv.PolyData()
    mesh.points = np.array(pts_list)
    mesh.lines  = np.array(lines)
    pl.add_mesh(mesh, color=_EXT_COLOR, line_width=0.5, opacity=0.9)


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _build_axis_map(bb: tuple) -> Dict[str, Tuple[str, float, float]]:
    xmin, ymin, zmin, xmax, ymax, zmax = bb
    extents = sorted(
        [
            ("x", xmax - xmin, xmin, xmax),
            ("y", ymax - ymin, ymin, ymax),
            ("z", zmax - zmin, zmin, zmax),
        ],
        key=lambda t: t[1],
        reverse=True,
    )
    return {
        "length": (extents[0][0], extents[0][2], extents[0][3]),
        "width":  (extents[1][0], extents[1][2], extents[1][3]),
        "height": (extents[2][0], extents[2][2], extents[2][3]),
    }


def _standoff(bb: tuple) -> float:
    xmin, ymin, zmin, xmax, ymax, zmax = bb
    diag = np.sqrt((xmax - xmin)**2 + (ymax - ymin)**2 + (zmax - zmin)**2)
    return max(diag * _STANDOFF, 2.0)


def _arrowhead_size(bb: tuple) -> float:
    """Global arrowhead height: a small fraction of the bounding-box diagonal."""
    xmin, ymin, zmin, xmax, ymax, zmax = bb
    diag = np.sqrt((xmax - xmin)**2 + (ymax - ymin)**2 + (zmax - zmin)**2)
    return max(diag * _AH_DIAG_FRAC, 0.3)


def _perp_offset(unit: np.ndarray, magnitude: float) -> np.ndarray:
    ref = np.array([0.0, 0.0, 1.0])
    if abs(np.dot(unit, ref)) > 0.9:
        ref = np.array([1.0, 0.0, 0.0])
    perp = np.cross(unit, ref)
    norm = np.linalg.norm(perp)
    return perp / norm * magnitude if norm > 1e-9 else np.zeros(3)


def _setup_camera(pl: pv.Plotter, bb: tuple, off: float) -> None:
    """Approximate matplotlib's elev=22, azim=-50 starting view."""
    xmin, ymin, zmin, xmax, ymax, zmax = bb
    cx = (xmin + xmax) / 2
    cy = (ymin + ymax) / 2
    cz = (zmin + zmax) / 2
    diag = np.sqrt((xmax - xmin)**2 + (ymax - ymin)**2 + (zmax - zmin)**2)
    dist = diag * 2.2
    el = np.radians(22)
    az = np.radians(-50)
    pl.camera_position = [
        (cx + dist * np.cos(el) * np.cos(az),
         cy + dist * np.cos(el) * np.sin(az),
         cz + dist * np.sin(el)),
        (cx, cy, cz),
        (0.0, 0.0, 1.0),
    ]


def _add_info(pl: pv.Plotter, mds: MinimalDimensionSet) -> None:
    pl.add_legend(
        [
            ["Critical",      _PRIORITY_COLOR["critical"]],
            ["Important",     _PRIORITY_COLOR["important"]],
            ["Informational", _PRIORITY_COLOR["informational"]],
        ],
        face="rectangle",
        size=(0.22, 0.10),
        loc="lower right",
        bcolor="white",
        border=True,
    )

    counts: Dict[str, int] = {"critical": 0, "important": 0, "informational": 0}
    for d in mds.dimensions:
        counts[d.priority] = counts.get(d.priority, 0) + 1

    gen_note = mds.general_tolerance_note.split("(")[0].strip()
    lines = [
        f"Process:   {mds.process}",
        f"IT grade:  {mds.it_grade}  ({mds.process_class})",
        f"Gen. tol:  {gen_note}",
        "",
        f"Dimensions: {mds.count()} total",
        f"  critical:      {counts['critical']}",
        f"  important:     {counts['important']}",
        f"  informational: {counts['informational']}",
    ]
    if mds.warnings:
        lines += ["", f"Warnings: {len(mds.warnings)}"]

    pl.add_text(
        "\n".join(lines),
        position="upper_left",
        font_size=8,
        color="black",
        font="courier",
    )


# ══════════════════════════════════════════════════════════════════════════════
# CLI entry point  (requires pythonocc-core)
# ══════════════════════════════════════════════════════════════════════════════

def _cli() -> None:
    import argparse

    default_step = ROOT / "data" / "FlandersMake_part_NOK-Merger.step"

    parser = argparse.ArgumentParser(
        description="Interactive 3-D dimension viewer for a STEP file (PyVista)"
    )
    parser.add_argument(
        "path", nargs="?", default=str(default_step),
        help="Path to STEP file (default: FlandersMake example)",
    )
    parser.add_argument(
        "--process", default="CNC_milling",
        help="Manufacturing process key (default: CNC_milling)",
    )
    parser.add_argument(
        "--solid", type=int, default=0,
        help="Solid index to display (default: 0)",
    )
    args = parser.parse_args()

    try:
        from load_cad.step_reader import read_step_single
        from post_process.shape_normalizer import normalize_shape, extract_solids
        from post_process.shape_dimension import infer_dimensions
        from post_process.dimension_minimal import minimal_dimensions
        from tolerance_advisor.helpers import load_process_capabilities
    except ImportError as exc:
        print(f"CLI requires pythonocc-core: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading {args.path} …")
    compound      = read_step_single(args.path)
    solid_shapes  = extract_solids(compound)
    normalized    = normalize_shape(compound)
    shape_dims    = infer_dimensions(normalized)

    db      = load_process_capabilities()
    results = minimal_dimensions(shape_dims, args.process, db)

    idx = args.solid
    if idx >= len(results):
        print(f"Solid {idx} not found — only {len(results)} solid(s) in file.",
              file=sys.stderr)
        sys.exit(1)

    mds = results[idx]
    sd  = shape_dims.solids[idx]
    solid_shape = solid_shapes[idx]

    print(f"Solid {idx}:  {mds.count()} dimensions  |  "
          f"{len(mds.critical())} critical  |  process = {args.process}")
    if mds.warnings:
        for w in mds.warnings:
            print(f"  (!) {w}")

    view_dimensions(solid_shape, sd, mds)


if __name__ == "__main__":
    _cli()
