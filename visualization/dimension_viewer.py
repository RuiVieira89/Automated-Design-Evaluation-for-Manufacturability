"""Interactive 3D dimension viewer for minimal drawing dimension sets.

Renders the part geometry (bounding box + cylindrical features) in a
rotatable 3D matplotlib window and overlays every DimensionEntry as a
double-headed arrow that runs from the measured start point to the measured
end point, labelled with  ``nominal ±tolerance``.

Arrow colour encodes priority:
  red  — critical  (at or beyond process capability)
  blue — important  (primary drawing dimension)
  grey — informational

Usage — library
---------------
    from visualization.dimension_viewer import view_dimensions
    view_dimensions(solid_dims, mds)

Usage — CLI  (requires pythonocc-core for STEP loading)
--------------------------------------------------------
    python visualization/dimension_viewer.py
    python visualization/dimension_viewer.py data/part.step --process CNC_milling
    python visualization/dimension_viewer.py data/part.step --solid 1
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from mpl_toolkits.mplot3d import Axes3D          # registers 3D projection  # noqa: F401
from mpl_toolkits.mplot3d.art3d import Line3DCollection, Poly3DCollection

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from post_process.dimension_minimal import DimensionEntry, MinimalDimensionSet
from post_process.shape_dimension import CylindricalFeature, PlaneGroup, SolidDimensions

# ── visual constants ───────────────────────────────────────────────────────────

_PRIORITY_COLOR: Dict[str, str] = {
    "critical":      "#d62728",  # red
    "important":     "#1f77b4",  # steel-blue
    "informational": "#7f7f7f",  # grey
}
_BOX_COLOR   = "#999999"
_CYL_COLOR   = "#7799bb"   # slightly lighter blue so arrows stand out
_EXT_COLOR   = "#bbbbbb"   # extension lines (dashed)
_FACE_ALPHA  = 0.06        # bounding-box face transparency

# Fraction of bounding-box diagonal used as dim-line standoff
_STANDOFF = 0.20
# Arrowhead length as fraction of the full dim-line length.
# No absolute cap — arrowheads scale with the dimension they annotate.
_AH_FRAC  = 0.13


# ══════════════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════════════

def view_dimensions(
    solid_dims: SolidDimensions,
    mds: MinimalDimensionSet,
    title: str = "",
    show: bool = True,
) -> Tuple[plt.Figure, "Axes3D"]:
    """Render an interactive 3D dimension view.

    Parameters
    ----------
    solid_dims:
        Geometry source — bounding box, cylinders, plane groups.
    mds:
        Minimal dimension set from
        :func:`~post_process.dimension_minimal.minimal_solid_dimensions`.
    title:
        Optional figure title override.
    show:
        Call ``plt.show()`` when *True*.  Set *False* for testing or embedding.

    Returns
    -------
    (fig, ax)
    """
    fig = plt.figure(figsize=(15, 10))
    ax: Axes3D = fig.add_subplot(111, projection="3d")

    bb  = solid_dims.bounding_box
    off = _standoff(bb)

    # ── geometry look-up tables ──
    cyl_by_fid: Dict[int, CylindricalFeature] = {
        c.face_id: c for c in solid_dims.cylinders
    }
    pg_by_fid: Dict[int, PlaneGroup] = {}
    for pg in solid_dims.plane_groups:
        for fid in pg.face_ids:
            pg_by_fid[fid] = pg

    axis_map = _build_axis_map(bb)   # "length"/"width"/"height" → (char, lo, hi)

    # ── draw geometry ──
    _draw_box(ax, bb)
    for cyl in solid_dims.cylinders:
        _draw_cylinder_geom(ax, cyl)

    # ── draw each dimension ──
    for dim in mds.dimensions:
        color = _PRIORITY_COLOR.get(dim.priority, "#7f7f7f")
        result = _resolve(dim, solid_dims, axis_map, cyl_by_fid, pg_by_fid, bb, off)
        if result is None:
            continue
        pt1, pt2, ext_segs = result
        _draw_extension_lines(ax, ext_segs)
        _draw_dim_arrow(ax, pt1, pt2, dim.drawing_annotation(), color)

    # ── aesthetics ──
    _setup_axes(ax, bb, off)
    _add_legend(fig, mds)

    fig.suptitle(
        title or (
            f"Solid {mds.solid_id}  ·  {mds.process}"
            f"  ·  {mds.it_grade} ({mds.process_class})"
            f"  ·  {mds.count()} dims  ·  drag to rotate"
        ),
        fontsize=10, y=0.99,
    )

    plt.tight_layout(rect=(0, 0, 1, 0.97))
    if show:
        plt.show()
    return fig, ax


# ══════════════════════════════════════════════════════════════════════════════
# Endpoint resolution  —  compute (pt1, pt2, ext_segments) per dimension kind
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
    """Return (pt1, pt2, ext_segs) or None if geometry cannot be resolved.

    *ext_segs* is a list of (from_pt, to_pt) pairs for extension lines.
    """
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


# ── overall bounding-box dimensions ──────────────────────────────────────────

def _resolve_overall(dim, axis_map, bb, off):
    xmin, ymin, zmin, xmax, ymax, zmax = bb
    info = axis_map.get(dim.kind)
    if info is None:
        return None
    axis_char, lo, hi = info

    # Place each overall dim arrow on a different face so they don't collide.
    # Extension lines run from the bounding-box edge to the arrow endpoint.
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
    else:  # z
        x0, y0 = xmax + off, ymin - off
        pt1 = np.array([x0, y0, zmin])
        pt2 = np.array([x0, y0, zmax])
        ext = [
            (np.array([xmax, y0, zmin]), pt1),
            (np.array([xmax, y0, zmax]), pt2),
        ]

    return pt1, pt2, ext


# ── cylindrical feature — diameter ───────────────────────────────────────────

def _resolve_diameter(cyl: CylindricalFeature, bb: tuple):
    cx, cy, cz = cyl.center
    r  = cyl.radius_est
    ax = cyl.axis

    # Draw the diameter arrow through the cylinder centre in the measurement plane.
    # Choose a perpendicular direction that lies in the plane perpendicular to the axis.
    if ax == "z":
        pt1 = np.array([cx - r, cy, cz])
        pt2 = np.array([cx + r, cy, cz])
    elif ax == "x":
        pt1 = np.array([cx, cy - r, cz])
        pt2 = np.array([cx, cy + r, cz])
    else:  # y
        pt1 = np.array([cx, cy, cz - r])
        pt2 = np.array([cx, cy, cz + r])

    return pt1, pt2, []   # no extension lines — arrow sits on the cylinder itself


# ── cylindrical feature — depth (blind holes only) ───────────────────────────

def _resolve_depth(cyl: CylindricalFeature, bb: tuple):
    cx, cy, cz = cyl.center
    ax = cyl.axis
    r  = cyl.radius_est
    cbx = cyl.bounding_box   # (xmin, ymin, zmin, xmax, ymax, zmax) of face

    # Offset the arrow slightly outside the cylinder so it doesn't overlap
    # with the diameter arrow.
    SIDE_OFF = r * 0.6

    if ax == "z":
        xoff = cx + r + SIDE_OFF
        pt1  = np.array([xoff, cy, cbx[2]])   # z_bottom
        pt2  = np.array([xoff, cy, cbx[5]])   # z_top
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
    else:  # y
        xoff = cx + r + SIDE_OFF
        pt1  = np.array([xoff, cbx[1], cz])
        pt2  = np.array([xoff, cbx[4], cz])
        ext  = [
            (np.array([cx, cbx[1], cz]), pt1),
            (np.array([cx, cbx[4], cz]), pt2),
        ]

    return pt1, pt2, ext


# ── positional dimensions — cylinder centre from datum face ──────────────────

def _resolve_position(kind: str, cyl: CylindricalFeature, bb: tuple):
    xmin, ymin, zmin, xmax, ymax, zmax = bb
    cx, cy, cz = cyl.center
    ax = cyl.axis

    # Place the position arrow at the cylinder mid-height / mid-radius level,
    # offset from the cylinder so it is visible next to the depth arrow.
    r   = cyl.radius_est
    cbx = cyl.bounding_box
    cz_mid = (cbx[2] + cbx[5]) / 2.0  # mid-height of cylinder

    if kind == "position_x":
        z_off = cz_mid - r * 0.3   # slightly below mid-height
        pt1 = np.array([xmin, cy, z_off])
        pt2 = np.array([cx,   cy, z_off])
        ext = [(np.array([cx, cy, cz_mid]), pt2)]
    elif kind == "position_y":
        z_off = cz_mid + r * 0.3
        pt1 = np.array([cx, ymin, z_off])
        pt2 = np.array([cx, cy,   z_off])
        ext = [(np.array([cx, cy, cz_mid]), pt2)]
    else:  # position_z  (only emitted when axis != z)
        pt1 = np.array([cx + r * 1.2, cy, zmin])
        pt2 = np.array([cx + r * 1.2, cy, cz])
        ext = [(np.array([cx, cy, cz]), pt2)]

    return pt1, pt2, ext


# ── wall / step thickness ─────────────────────────────────────────────────────

def _resolve_wall(pg: PlaneGroup, fid1: int, fid2: int, bb: tuple):
    """Place the wall arrow along the plane-group normal through the bbox centre."""
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

    # Project bbox centre onto the group normal to get the reference offset.
    # Reconstruct 3-D points that lie on each plane at the bbox-centre transverse.
    c_proj = float(np.dot(c, n))
    pt1 = c + (p1 - c_proj) * n
    pt2 = c + (p2 - c_proj) * n

    return pt1, pt2, []


# ══════════════════════════════════════════════════════════════════════════════
# Drawing primitives
# ══════════════════════════════════════════════════════════════════════════════

def _draw_dim_arrow(
    ax: "Axes3D",
    pt1: np.ndarray,
    pt2: np.ndarray,
    label: str,
    color: str,
) -> None:
    """Draw a double-headed dimension arrow from *pt1* to *pt2* with a label."""
    vec    = pt2 - pt1
    length = float(np.linalg.norm(vec))
    if length < 1e-9:
        return

    unit = vec / length
    ah   = length * _AH_FRAC   # arrowhead length scales with the dimension

    # ── main dimension line ──
    ax.plot(
        [pt1[0], pt2[0]], [pt1[1], pt2[1]], [pt1[2], pt2[2]],
        color=color, linewidth=2.0, solid_capstyle="butt", zorder=4,
    )

    # ── arrowheads: tip at pt1 pointing toward pt2 (inward), and vice versa ──
    # ax.quiver: tail at (x,y,z), tip at (x+u, y+v, z+w).
    # arrow_length_ratio=1.0 → entire length is the cone (no shaft drawn).
    ax.quiver(
        pt1[0] - unit[0] * ah, pt1[1] - unit[1] * ah, pt1[2] - unit[2] * ah,
        unit[0] * ah,  unit[1] * ah,  unit[2] * ah,
        color=color, arrow_length_ratio=1.0, linewidth=0, zorder=5,
    )
    ax.quiver(
        pt2[0] + unit[0] * ah, pt2[1] + unit[1] * ah, pt2[2] + unit[2] * ah,
        -unit[0] * ah, -unit[1] * ah, -unit[2] * ah,
        color=color, arrow_length_ratio=1.0, linewidth=0, zorder=5,
    )

    # ── label at midpoint, offset slightly perpendicular to the arrow ──
    mid  = (pt1 + pt2) / 2.0
    perp = _perp_offset(unit, length * 0.10)
    lpos = mid + perp
    ax.text(
        lpos[0], lpos[1], lpos[2],
        label,
        color=color, fontsize=8, fontweight="bold",
        ha="center", va="center", zorder=6,
        bbox=dict(
            boxstyle="round,pad=0.3",
            facecolor="white", alpha=0.90,
            edgecolor=color,  linewidth=0.8,
        ),
    )


def _draw_extension_lines(ax: "Axes3D", segments: List) -> None:
    """Draw thin dashed extension lines (list of (from_pt, to_pt) pairs)."""
    if not segments:
        return
    segs = [[list(a), list(b)] for a, b in segments]
    lc = Line3DCollection(
        segs,
        colors=_EXT_COLOR, linewidths=0.7,
        linestyles="dashed", zorder=2,
    )
    ax.add_collection3d(lc)


def _draw_box(ax: "Axes3D", bb: tuple) -> None:
    """Draw the bounding box as a wireframe with lightly shaded faces."""
    x0, y0, z0, x1, y1, z1 = bb

    # 8 corners
    verts = np.array([
        [x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],   # bottom
        [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1],   # top
    ])

    # 12 edges
    edges = [
        (0,1),(1,2),(2,3),(3,0),
        (4,5),(5,6),(6,7),(7,4),
        (0,4),(1,5),(2,6),(3,7),
    ]
    segs = [[list(verts[i]), list(verts[j])] for i, j in edges]
    lc = Line3DCollection(segs, colors=_BOX_COLOR, linewidths=0.9, zorder=1)
    ax.add_collection3d(lc)

    # 6 semi-transparent faces
    faces = [
        [verts[0], verts[1], verts[2], verts[3]],   # bottom  z=z0
        [verts[4], verts[5], verts[6], verts[7]],   # top     z=z1
        [verts[0], verts[1], verts[5], verts[4]],   # front   y=y0
        [verts[2], verts[3], verts[7], verts[6]],   # back    y=y1
        [verts[0], verts[3], verts[7], verts[4]],   # left    x=x0
        [verts[1], verts[2], verts[6], verts[5]],   # right   x=x1
    ]
    poly = Poly3DCollection(faces, alpha=_FACE_ALPHA, facecolor="#aaaaaa", edgecolor="none")
    ax.add_collection3d(poly)


def _draw_cylinder_geom(ax: "Axes3D", cyl: CylindricalFeature) -> None:
    """Draw the cylinder silhouette as two end circles + four generator lines."""
    cx, cy, cz = cyl.center
    r   = cyl.radius_est
    cbx = cyl.bounding_box   # (xmin, ymin, zmin, xmax, ymax, zmax)
    axi = cyl.axis

    theta = np.linspace(0, 2 * np.pi, 64)
    cos_t, sin_t = np.cos(theta), np.sin(theta)

    kw = dict(color=_CYL_COLOR, linewidth=0.9, alpha=0.55, zorder=2)
    gen_kw = dict(color=_CYL_COLOR, linewidth=0.5, alpha=0.35, zorder=2)

    if axi == "z":
        z0, z1 = cbx[2], cbx[5]
        xc, yc = cx + r * cos_t, cy + r * sin_t
        ax.plot(xc, yc, np.full_like(theta, z0), **kw)
        ax.plot(xc, yc, np.full_like(theta, z1), **kw)
        for t in np.linspace(0, 2 * np.pi, 5)[:-1]:
            ax.plot([cx + r * np.cos(t)] * 2,
                    [cy + r * np.sin(t)] * 2,
                    [z0, z1], **gen_kw)

    elif axi == "x":
        x0, x1 = cbx[0], cbx[3]
        yc, zc = cy + r * cos_t, cz + r * sin_t
        ax.plot(np.full_like(theta, x0), yc, zc, **kw)
        ax.plot(np.full_like(theta, x1), yc, zc, **kw)
        for t in np.linspace(0, 2 * np.pi, 5)[:-1]:
            ax.plot([x0, x1],
                    [cy + r * np.cos(t)] * 2,
                    [cz + r * np.sin(t)] * 2, **gen_kw)

    else:  # y
        y0, y1 = cbx[1], cbx[4]
        xc, zc = cx + r * cos_t, cz + r * sin_t
        ax.plot(xc, np.full_like(theta, y0), zc, **kw)
        ax.plot(xc, np.full_like(theta, y1), zc, **kw)
        for t in np.linspace(0, 2 * np.pi, 5)[:-1]:
            ax.plot([cx + r * np.cos(t)] * 2,
                    [y0, y1],
                    [cz + r * np.sin(t)] * 2, **gen_kw)


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _build_axis_map(bb: tuple) -> Dict[str, Tuple[str, float, float]]:
    """Map 'length'/'width'/'height' → (axis_char, lo, hi) from the bounding box."""
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
    """Dimension-line standoff: a fraction of the bounding-box diagonal."""
    xmin, ymin, zmin, xmax, ymax, zmax = bb
    diag = np.sqrt((xmax - xmin)**2 + (ymax - ymin)**2 + (zmax - zmin)**2)
    return max(diag * _STANDOFF, 2.0)


def _perp_offset(unit: np.ndarray, magnitude: float) -> np.ndarray:
    """Return a small offset vector perpendicular to *unit* for label placement."""
    # Pick a reference vector not parallel to unit
    ref = np.array([0.0, 0.0, 1.0])
    if abs(np.dot(unit, ref)) > 0.9:
        ref = np.array([1.0, 0.0, 0.0])
    perp = np.cross(unit, ref)
    norm = np.linalg.norm(perp)
    return perp / norm * magnitude if norm > 1e-9 else np.zeros(3)


def _setup_axes(ax: "Axes3D", bb: tuple, off: float) -> None:
    xmin, ymin, zmin, xmax, ymax, zmax = bb
    pad = off * 1.1
    ax.set_xlim(xmin - pad, xmax + pad)
    ax.set_ylim(ymin - pad, ymax + pad)
    ax.set_zlim(zmin - pad, zmax + pad)
    ax.set_xlabel("X (mm)", labelpad=6, fontsize=8)
    ax.set_ylabel("Y (mm)", labelpad=6, fontsize=8)
    ax.set_zlabel("Z (mm)", labelpad=6, fontsize=8)
    ax.tick_params(labelsize=7)
    # Isometric-ish view: tilted enough to see all three overall arrows
    ax.view_init(elev=22, azim=-50)
    ax.set_box_aspect([
        max((xmax - xmin), 1e-3),
        max((ymax - ymin), 1e-3),
        max((zmax - zmin), 1e-3),
    ])


def _add_legend(fig: plt.Figure, mds: MinimalDimensionSet) -> None:
    """Add a priority-colour legend and a dimension-count summary."""
    patches = [
        mpatches.Patch(color=_PRIORITY_COLOR["critical"],      label="Critical"),
        mpatches.Patch(color=_PRIORITY_COLOR["important"],     label="Important"),
        mpatches.Patch(color=_PRIORITY_COLOR["informational"], label="Informational"),
    ]
    legend = fig.legend(
        handles=patches,
        loc="lower left",
        fontsize=8,
        framealpha=0.9,
        title="Priority",
        title_fontsize=8,
    )

    # Count per priority
    counts = {"critical": 0, "important": 0, "informational": 0}
    for d in mds.dimensions:
        counts[d.priority] = counts.get(d.priority, 0) + 1

    summary_lines = [
        f"Process:   {mds.process}",
        f"IT grade:  {mds.it_grade}  ({mds.process_class})",
        f"Gen. tol:  {mds.general_tolerance_note.split('(')[0].strip()}",
        "",
        f"Dimensions: {mds.count()} total",
        f"  critical:      {counts['critical']}",
        f"  important:     {counts['important']}",
        f"  informational: {counts['informational']}",
    ]
    if mds.warnings:
        summary_lines += ["", f"Warnings: {len(mds.warnings)}"]

    fig.text(
        0.01, 0.99, "\n".join(summary_lines),
        va="top", ha="left", fontsize=7.5,
        fontfamily="monospace",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="white",
                  alpha=0.88, edgecolor="#cccccc"),
    )


# ══════════════════════════════════════════════════════════════════════════════
# CLI entry point  (requires pythonocc-core)
# ══════════════════════════════════════════════════════════════════════════════

def _cli() -> None:
    import argparse

    default_step = ROOT / "data" / "FlandersMake_part_NOK-Merger.step"

    parser = argparse.ArgumentParser(
        description="Interactive 3-D dimension viewer for a STEP file"
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
        from post_process.shape_normalizer import normalize_shape
        from post_process.shape_dimension import infer_dimensions
        from post_process.dimension_minimal import minimal_dimensions
        from tolerance_advisor.helpers import load_process_capabilities
    except ImportError as exc:
        print(f"CLI requires pythonocc-core: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading {args.path} …")
    compound  = read_step_single(args.path)
    normalized = normalize_shape(compound)
    shape_dims = infer_dimensions(normalized)

    db      = load_process_capabilities()
    results = minimal_dimensions(shape_dims, args.process, db)

    idx = args.solid
    if idx >= len(results):
        print(f"Solid {idx} not found — only {len(results)} solid(s) in file.",
              file=sys.stderr)
        sys.exit(1)

    mds = results[idx]
    sd  = shape_dims.solids[idx]

    print(f"Solid {idx}:  {mds.count()} dimensions  |  "
          f"{len(mds.critical())} critical  |  process = {args.process}")
    if mds.warnings:
        for w in mds.warnings:
            print(f"  (!) {w}")

    view_dimensions(sd, mds)


if __name__ == "__main__":
    _cli()
