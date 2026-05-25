"""Parametric GPU water-cooled cold plate using PythonOCC.

Geometry
--------
The cold plate is assembled from up to four components:

Base
    A rectangular plate with **rounded corners**, centred at the origin:
    * X/Y centre at (0, 0, 0); the plate spans ±base_length/2 in X,
      ±base_width/2 in Y, and 0 → base_height in Z.
    * Corner radius ``corner_radius`` (same value reused by the wall's
      outer edge).

Fins
    Parallel rectangular fins on top of the base, centred in X and Y.
    Parameterisation is identical to :func:`build_heat_sink` in
    :mod:`CAD_heatSink` (same variable names, same box-per-fin approach).
    The fin-construction code is **replicated** rather than importing
    ``build_heat_sink`` because that function returns a STEP string and
    would require an unnecessary round-trip; building the boxes directly
    is cleaner.

Wall  *(optional — created when* ``wall_height > 0`` *)*
    A rectangular frame that sits on top of the base, surrounding the fins.
    * Outer boundary is inset from the base edge by ``wall_inset``.
    * Outer corners share ``corner_radius`` with the base.
    * Inner cavity has sharp (radius = 0) corners.
    * The frame is constructed as: *rounded outer prism* − *inner box*.

Holes
    Cylindrical through-holes, all centred on the Z-axis:

    * **Screw holes** — pass through the full stack height
      (base + wall if present).  Count must be 0, 4, or 8.
    * **Centering pin holes** — pass through the base only.

Return value
------------
:func:`build_cold_plate` returns a ``dict`` with the following keys:

``"solid"``
    Final assembled ``TopoDS_Shape`` with *all* holes subtracted.
    This is the geometry you want to mesh or export.

``"base"``
    Raw base solid — **without** holes.  Useful for downstream
    component-level analysis or visualization.

``"fins"``
    Fin array as a single fused solid — **without** holes.

``"wall"``
    Raw wall frame solid — **without** holes, or ``None`` if
    ``wall_height == 0``.

``"screw_holes"``
    ``list`` of cylindrical ``TopoDS_Shape`` cutter tools used for screw
    holes (before subtraction), or ``None`` if there are none.

``"pin_holes"``
    Same, for centering pin holes.

``"step_path"``
    Absolute path to the saved STEP file as a ``str``, or ``None`` if
    ``save=False``.

.. note::
    ``"base"``, ``"fins"``, and ``"wall"`` are the **raw** (pre-holes)
    component shapes.  Only ``"solid"`` has holes subtracted.

Coordinate system
-----------------
* **x** — fin channel / extrusion direction  (length = ``channel_length``)
* **y** — fin-array direction                (width  = ``fin_number × fin_thickness``
                                              ``+ (fin_number − 1) × fin_spacing``)
* **z** — height                             (0 at base bottom)

Validation
----------
:func:`build_cold_plate` raises :exc:`ValueError` if:

* ``corner_radius`` is not positive or ``2 × corner_radius ≥ min(base_length, base_width)``.
* ``fin_number < 1``.
* The fin array does not fit within the base (or within the wall's inner
  cavity when a wall is present).
* ``len(screw_hole_positions)`` is not 0, 4, or 8.
* ``screw_hole_diameter > 0`` but no positions are given (or vice-versa).
* ``pin_hole_diameter > 0`` but no positions are given (or vice-versa).
* Any hole centre lies outside the base axis-aligned bounding rectangle.
* ``wall_height > 0`` and ``wall_thickness ≤ 0``.
* ``wall_height > 0`` and the inner cavity is too small for the fin array.

Usage
-----
As a library::

    from examples.case.heat_sink_example_V3.cold_plate_cad import build_cold_plate
    result = build_cold_plate(
        base_length=100.0, base_width=80.0, base_height=4.0, corner_radius=5.0,
        fin_height=8.0, fin_thickness=1.5, fin_spacing=2.0,
        fin_number=16, channel_length=80.0,
        save=True,
    )
    solid = result["solid"]

As a script (saves to ``data/CAD_generated/``)::

    conda run -n auto_eval_manuf \\
        python examples/case/heat_sink_example_V3/cold_plate_cad.py
"""

from __future__ import annotations

import math
import sys
import tempfile
from pathlib import Path
from typing import Optional, Sequence

# ---------------------------------------------------------------------------
# Repo root on sys.path
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from OCC.Core.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCC.Core.BRepBuilderAPI import (
    BRepBuilderAPI_MakeEdge,
    BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_MakeWire,
)
from OCC.Core.BRepPrimAPI import (
    BRepPrimAPI_MakeBox,
    BRepPrimAPI_MakeCylinder,
    BRepPrimAPI_MakePrism,
)
from OCC.Core.GC import GC_MakeArcOfCircle, GC_MakeSegment
from OCC.Core.IFSelect import IFSelect_RetDone
from OCC.Core.STEPControl import STEPControl_AsIs, STEPControl_Writer
from OCC.Core.gp import gp_Ax2, gp_Circ, gp_Dir, gp_Pnt, gp_Vec

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_DEFAULT_DEST = ROOT / "data" / "CAD_generated"

# Small geometric extension used to guarantee clean boolean-cut faces.
# Cutters are made slightly taller / longer than the material they remove
# so the tool's faces do not coincide exactly with the target faces.
_EPS: float = 1e-3   # mm  (1 µm — invisible at machining scale)


# ===========================================================================
# Internal geometry helpers
# ===========================================================================

def _make_rounded_rect_wire(
    cx: float, cy: float,
    half_l: float, half_w: float,
    r: float,
    z: float = 0.0,
):
    """Return a **CCW closed** ``TopoDS_Wire`` for a rounded-corner rectangle.

    The wire lies in the horizontal plane at height *z*.  It is
    counter-clockwise (CCW) when viewed from +Z, which is required for
    :func:`BRepBuilderAPI_MakeFace` to produce a face with +Z normal.

    Parameters
    ----------
    cx, cy:
        Centre of the rectangle in X and Y  [mm].
    half_l, half_w:
        Half-extents in X and Y  [mm].
    r:
        Corner radius  [mm].  Must satisfy ``r < min(half_l, half_w)``.
    z:
        Z-coordinate of the wire plane  [mm].

    Raises
    ------
    RuntimeError
        If OCC fails to construct any edge or the final wire.
    """
    # Convenience factories
    def p(x_: float, y_: float) -> gp_Pnt:
        return gp_Pnt(x_ + cx, y_ + cy, z)

    def arc_circle(ax: float, ay: float) -> gp_Circ:
        """gp_Circ centred at (cx+ax, cy+ay, z) with normal +Z and radius r."""
        return gp_Circ(gp_Ax2(p(ax, ay), gp_Dir(0.0, 0.0, 1.0)), r)

    def line_edge(x1: float, y1: float, x2: float, y2: float):
        seg = GC_MakeSegment(p(x1, y1), p(x2, y2))
        if not seg.IsDone():
            raise RuntimeError(
                f"GC_MakeSegment failed for ({x1},{y1})→({x2},{y2})"
            )
        return BRepBuilderAPI_MakeEdge(seg.Value()).Edge()

    def arc_edge(ax: float, ay: float, alpha1: float, alpha2: float):
        """Quarter-circle arc CCW from alpha1 to alpha2 (radians)."""
        arc = GC_MakeArcOfCircle(arc_circle(ax, ay), alpha1, alpha2, True)
        if not arc.IsDone():
            raise RuntimeError(
                f"GC_MakeArcOfCircle failed at centre ({ax},{ay}), "
                f"α1={math.degrees(alpha1):.0f}° → α2={math.degrees(alpha2):.0f}°"
            )
        return BRepBuilderAPI_MakeEdge(arc.Value()).Edge()

    hl, hw = half_l, half_w
    pi = math.pi

    # ------------------------------------------------------------------
    # 8 edges forming a CCW loop:
    #   bottom  → BR-arc → right → TR-arc → top → TL-arc → left → BL-arc
    # ------------------------------------------------------------------
    edges = [
        line_edge(-hl + r, -hw,     +hl - r, -hw     ),   # bottom (L→R)
        arc_edge( +hl - r, -hw + r, -pi / 2,  0.0    ),   # bottom-right arc
        line_edge(+hl,     -hw + r, +hl,      +hw - r ),   # right  (↑)
        arc_edge( +hl - r, +hw - r,  0.0,     pi / 2  ),   # top-right arc
        line_edge(+hl - r, +hw,     -hl + r,  +hw     ),   # top    (R→L)
        arc_edge( -hl + r, +hw - r,  pi / 2,  pi      ),   # top-left arc
        line_edge(-hl,     +hw - r, -hl,      -hw + r ),   # left   (↓)
        arc_edge( -hl + r, -hw + r,  pi,      3 * pi / 2), # bottom-left arc
    ]

    wm = BRepBuilderAPI_MakeWire()
    for edge in edges:
        wm.Add(edge)

    if not wm.IsDone():
        raise RuntimeError(
            f"BRepBuilderAPI_MakeWire failed for rounded rectangle "
            f"({2*hl:.2f}×{2*hw:.2f} mm, r={r:.2f} mm, z={z:.2f} mm); "
            f"error code: {wm.Error()}"
        )

    return wm.Wire()


def _make_rounded_rect_prism(
    cx: float, cy: float,
    half_l: float, half_w: float,
    r: float,
    z_start: float,
    height: float,
):
    """Return a ``TopoDS_Shape`` (solid prism) with a rounded-corner cross-section.

    The bottom face sits at *z_start*; the top face at *z_start + height*.
    """
    wire = _make_rounded_rect_wire(cx, cy, half_l, half_w, r, z=z_start)
    face_maker = BRepBuilderAPI_MakeFace(wire, True)   # True = only planar
    if not face_maker.IsDone():
        raise RuntimeError(
            f"BRepBuilderAPI_MakeFace failed (error {face_maker.Error()}) "
            f"for rounded rect at z={z_start:.2f}"
        )
    prism = BRepPrimAPI_MakePrism(face_maker.Face(), gp_Vec(0.0, 0.0, height))
    prism.Build()
    if not prism.IsDone():
        raise RuntimeError("BRepPrimAPI_MakePrism failed")
    return prism.Shape()


def _fuse(shape_a, shape_b):
    """Return the boolean union of two ``TopoDS_Shape`` objects."""
    op = BRepAlgoAPI_Fuse(shape_a, shape_b)
    op.Build()
    if not op.IsDone():
        raise RuntimeError("BRepAlgoAPI_Fuse failed")
    return op.Shape()


def _cut(target, tool):
    """Return *target* with *tool* subtracted (boolean cut)."""
    op = BRepAlgoAPI_Cut(target, tool)
    op.Build()
    if not op.IsDone():
        raise RuntimeError("BRepAlgoAPI_Cut failed")
    return op.Shape()


def _make_cylinder_cutter(x: float, y: float, z_start: float,
                           height: float, radius: float):
    """Return a cylindrical ``TopoDS_Shape`` for boolean subtraction.

    The cylinder axis is along +Z; it starts at *z_start* and has the
    given *height*.  *z_start* is typically set to ``-_EPS`` and *height*
    extended by ``2 * _EPS`` so the cutter slightly over-shoots the
    target faces and avoids co-planar ambiguity.
    """
    ax2 = gp_Ax2(gp_Pnt(x, y, z_start), gp_Dir(0.0, 0.0, 1.0))
    return BRepPrimAPI_MakeCylinder(ax2, radius, height).Shape()


# ===========================================================================
# Parameter validation
# ===========================================================================

def _validate_params(
    base_length: float, base_width: float, base_height: float,
    corner_radius: float,
    fin_height: float, fin_thickness: float, fin_spacing: float,
    fin_number: int, channel_length: float,
    wall_thickness: float, wall_height: float, wall_inset: float,
    screw_hole_positions: Sequence[tuple[float, float]],
    screw_hole_diameter: float,
    pin_hole_positions: Sequence[tuple[float, float]],
    pin_hole_diameter: float,
) -> float:
    """Validate all parameters and return the pre-computed fin-array width.

    Raises :exc:`ValueError` on any geometric inconsistency.

    Returns
    -------
    float
        ``fin_array_width`` (avoids recomputing it in the caller).
    """
    # ------------------------------------------------------------------
    # Base corner radius
    # ------------------------------------------------------------------
    if corner_radius <= 0.0:
        raise ValueError(
            f"corner_radius must be positive; got {corner_radius} mm"
        )
    min_base_dim = min(base_length, base_width)
    if 2.0 * corner_radius >= min_base_dim:
        raise ValueError(
            f"corner_radius={corner_radius} mm is too large: "
            f"2·corner_radius ({2*corner_radius:.4g} mm) must be strictly less "
            f"than min(base_length, base_width) = {min_base_dim:.4g} mm"
        )

    # ------------------------------------------------------------------
    # Fins
    # ------------------------------------------------------------------
    if fin_number < 1:
        raise ValueError(f"fin_number must be ≥ 1; got {fin_number}")

    fin_array_width = (
        fin_number * fin_thickness + max(0, fin_number - 1) * fin_spacing
    )

    if channel_length > base_length:
        raise ValueError(
            f"channel_length={channel_length} mm exceeds "
            f"base_length={base_length} mm"
        )
    if fin_array_width > base_width:
        raise ValueError(
            f"Fin array width {fin_array_width:.4g} mm exceeds "
            f"base_width={base_width} mm"
        )

    # ------------------------------------------------------------------
    # Screw holes
    # ------------------------------------------------------------------
    if len(screw_hole_positions) not in (0, 4, 8):
        raise ValueError(
            f"screw_hole_positions must have exactly 0, 4, or 8 entries; "
            f"got {len(screw_hole_positions)}"
        )
    if screw_hole_diameter > 0.0 and len(screw_hole_positions) == 0:
        raise ValueError(
            "screw_hole_diameter > 0 but screw_hole_positions is empty"
        )
    if len(screw_hole_positions) > 0 and screw_hole_diameter <= 0.0:
        raise ValueError(
            f"screw_hole_positions has {len(screw_hole_positions)} entries "
            "but screw_hole_diameter is not positive"
        )

    # ------------------------------------------------------------------
    # Centering pin holes
    # ------------------------------------------------------------------
    if pin_hole_diameter > 0.0 and len(pin_hole_positions) == 0:
        raise ValueError(
            "pin_hole_diameter > 0 but pin_hole_positions is empty"
        )
    if len(pin_hole_positions) > 0 and pin_hole_diameter <= 0.0:
        raise ValueError(
            f"pin_hole_positions has {len(pin_hole_positions)} entries "
            "but pin_hole_diameter is not positive"
        )

    # ------------------------------------------------------------------
    # Hole positions within base AABB
    # ------------------------------------------------------------------
    half_l, half_w = base_length / 2.0, base_width / 2.0
    for label, positions in [
        ("screw", screw_hole_positions),
        ("pin",   pin_hole_positions),
    ]:
        for i, (x, y) in enumerate(positions):
            if not (-half_l < x < half_l and -half_w < y < half_w):
                raise ValueError(
                    f"{label} hole #{i} at ({x:.4g}, {y:.4g}) mm lies outside "
                    f"the base bounding rectangle "
                    f"[−{half_l:.4g}, +{half_l:.4g}] × [−{half_w:.4g}, +{half_w:.4g}] mm"
                )

    # ------------------------------------------------------------------
    # Wall
    # ------------------------------------------------------------------
    if wall_height > 0.0:
        if wall_thickness <= 0.0:
            raise ValueError(
                f"wall_height={wall_height} mm > 0 requires wall_thickness > 0; "
                f"got {wall_thickness} mm"
            )
        if wall_inset < 0.0:
            raise ValueError(
                f"wall_inset must be ≥ 0; got {wall_inset} mm"
            )

        outer_l = base_length - 2.0 * wall_inset
        outer_w = base_width  - 2.0 * wall_inset
        inner_l = outer_l - 2.0 * wall_thickness
        inner_w = outer_w - 2.0 * wall_thickness

        if inner_l <= 0.0 or inner_w <= 0.0:
            raise ValueError(
                f"Wall geometry is inconsistent: inner cavity dimensions are "
                f"{inner_l:.4g} × {inner_w:.4g} mm ≤ 0.  "
                f"Reduce wall_thickness ({wall_thickness} mm) or wall_inset "
                f"({wall_inset} mm)."
            )

        if channel_length > inner_l:
            raise ValueError(
                f"channel_length={channel_length} mm exceeds wall inner cavity "
                f"length {inner_l:.4g} mm.  "
                f"Reduce channel_length, wall_thickness, or wall_inset."
            )
        if fin_array_width > inner_w:
            raise ValueError(
                f"Fin array width {fin_array_width:.4g} mm exceeds wall inner "
                f"cavity width {inner_w:.4g} mm.  "
                f"Reduce fin parameters, wall_thickness, or wall_inset."
            )

        # Corner radius must also be valid for the wall's outer dimensions
        min_wall_outer = min(outer_l, outer_w)
        if 2.0 * corner_radius >= min_wall_outer:
            raise ValueError(
                f"corner_radius={corner_radius} mm is too large for wall outer "
                f"dimensions {outer_l:.4g}×{outer_w:.4g} mm: "
                f"2·corner_radius ({2*corner_radius:.4g}) must be < {min_wall_outer:.4g} mm.  "
                f"Reduce corner_radius or wall_inset."
            )

    return fin_array_width


# ===========================================================================
# STEP export helper
# ===========================================================================

def _write_step(shape, dest: Path, filename: str) -> Path:
    """Write *shape* to a STEP file and return the full path."""
    dest.mkdir(parents=True, exist_ok=True)
    out_path = dest / filename

    with tempfile.NamedTemporaryFile(suffix=".stp", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    writer = STEPControl_Writer()
    writer.Transfer(shape, STEPControl_AsIs)
    status = writer.Write(str(tmp_path))

    if status != IFSelect_RetDone:
        tmp_path.unlink(missing_ok=True)
        raise RuntimeError(f"STEPControl_Writer failed (status={status})")

    import shutil
    shutil.move(str(tmp_path), str(out_path))
    return out_path


# ===========================================================================
# Public API
# ===========================================================================

def build_cold_plate(
    # ------------------------------------------------------------------ #
    # Base geometry                                                       #
    # ------------------------------------------------------------------ #
    base_length: float,
    base_width: float,
    base_height: float,
    corner_radius: float,
    # ------------------------------------------------------------------ #
    # Fin array (same parameterisation as build_heat_sink)               #
    # ------------------------------------------------------------------ #
    fin_height: float,
    fin_thickness: float,
    fin_spacing: float,
    fin_number: int,
    channel_length: float,
    # ------------------------------------------------------------------ #
    # Surrounding wall  (wall_height = 0 → no wall)                      #
    # ------------------------------------------------------------------ #
    wall_thickness: float = 0.0,
    wall_height: float = 0.0,
    wall_inset: float = 0.0,
    # ------------------------------------------------------------------ #
    # Screw holes  (count must be 0, 4, or 8)                            #
    # ------------------------------------------------------------------ #
    screw_hole_positions: Sequence[tuple[float, float]] = (),
    screw_hole_diameter: float = 0.0,
    # ------------------------------------------------------------------ #
    # Centering pin holes  (through base only)                           #
    # ------------------------------------------------------------------ #
    pin_hole_positions: Sequence[tuple[float, float]] = (),
    pin_hole_diameter: float = 0.0,
    # ------------------------------------------------------------------ #
    # Output                                                              #
    # ------------------------------------------------------------------ #
    save: bool = False,
    output_step: str = "cold_plate.step",
    dest_folder: Optional[Path | str] = None,
) -> dict:
    """Build a parametric GPU water-cooled cold plate.

    See the module docstring for a full description of the geometry and
    the convention for the returned ``dict``.

    Parameters
    ----------
    base_length:
        Overall length of the base plate in the X direction  [mm].
    base_width:
        Overall width of the base plate in the Y direction  [mm].
    base_height:
        Thickness of the base plate  [mm].
    corner_radius:
        Radius of the base plate's rounded corners  [mm].
        Reused for the outer corners of the wall.
        Must satisfy ``2 × corner_radius < min(base_length, base_width)``.
    fin_height:
        Height of each fin above the base plate  [mm].
    fin_thickness:
        Thickness of one fin  [mm].
    fin_spacing:
        Clear distance between adjacent fins (channel width)  [mm].
    fin_number:
        Number of fins  (≥ 1).
    channel_length:
        Length of the fins in the X direction  [mm].
        Must not exceed ``base_length``.
    wall_thickness:
        Thickness of the surrounding wall  [mm].
        Required (> 0) when ``wall_height > 0``.
    wall_height:
        Height of the surrounding wall above the base top face  [mm].
        Set to ``0`` (default) to omit the wall entirely.
    wall_inset:
        Distance from the outer edge of the base to the outer edge of the
        wall  [mm].  ``0`` places the wall flush with the base perimeter.
    screw_hole_positions:
        Ordered ``[(x, y), …]`` positions of screw-hole centres in the
        base's local frame  [mm].  Length must be exactly 0, 4, or 8.
    screw_hole_diameter:
        Diameter of each screw hole  [mm].
        Must be positive if and only if ``screw_hole_positions`` is non-empty.
    pin_hole_positions:
        ``[(x, y), …]`` positions of centering-pin hole centres  [mm].
    pin_hole_diameter:
        Diameter of each pin hole  [mm].
    save:
        Write the assembled ``"solid"`` to a STEP file when ``True``.
        Default ``False``.
    output_step:
        File name of the STEP file (not a path).
    dest_folder:
        Destination directory.  Defaults to
        ``<repo_root>/data/CAD_generated``.

    Returns
    -------
    dict
        Keys: ``"solid"``, ``"base"``, ``"fins"``, ``"wall"``,
        ``"screw_holes"``, ``"pin_holes"``, ``"step_path"``.
        See module docstring for full documentation of each key.

    Raises
    ------
    ValueError
        On any geometric or parameter inconsistency (see *Validation*
        section in the module docstring).
    RuntimeError
        If any OCC boolean or STEP operation fails.
    """
    # ------------------------------------------------------------------
    # 0. Validate
    # ------------------------------------------------------------------
    fin_array_width = _validate_params(
        base_length=base_length, base_width=base_width,
        base_height=base_height, corner_radius=corner_radius,
        fin_height=fin_height, fin_thickness=fin_thickness,
        fin_spacing=fin_spacing, fin_number=fin_number,
        channel_length=channel_length,
        wall_thickness=wall_thickness, wall_height=wall_height,
        wall_inset=wall_inset,
        screw_hole_positions=screw_hole_positions,
        screw_hole_diameter=screw_hole_diameter,
        pin_hole_positions=pin_hole_positions,
        pin_hole_diameter=pin_hole_diameter,
    )

    # ------------------------------------------------------------------
    # 1. Base plate  (rounded corner rectangular prism, centred at origin)
    # ------------------------------------------------------------------
    print("  Building base …")
    base_solid = _make_rounded_rect_prism(
        cx=0.0, cy=0.0,
        half_l=base_length / 2.0,
        half_w=base_width  / 2.0,
        r=corner_radius,
        z_start=0.0,
        height=base_height,
    )

    # ------------------------------------------------------------------
    # 2. Fins  (same box-per-fin approach as build_heat_sink; replicated
    #           here to keep components available as separate shapes
    #           without a STEP round-trip)
    #
    #   Fin array is centred in X and Y over the base.  Each fin runs
    #   the full channel_length in X and extends upward from z=base_height.
    # ------------------------------------------------------------------
    print(f"  Building {fin_number} fins …")
    x0_fin   = -channel_length  / 2.0
    y0_fin   = -fin_array_width / 2.0

    fin_shapes: list = []
    for i in range(fin_number):
        y_start = y0_fin + i * (fin_thickness + fin_spacing)
        fin_shapes.append(
            BRepPrimAPI_MakeBox(
                gp_Pnt(x0_fin, y_start, base_height),
                channel_length, fin_thickness, fin_height,
            ).Shape()
        )

    fins_solid = fin_shapes[0]
    for fin in fin_shapes[1:]:
        fins_solid = _fuse(fins_solid, fin)

    # ------------------------------------------------------------------
    # 3. Wall  (optional — outer rounded prism minus inner box)
    # ------------------------------------------------------------------
    wall_solid = None
    if wall_height > 0.0:
        print("  Building wall …")
        outer_l = base_length - 2.0 * wall_inset
        outer_w = base_width  - 2.0 * wall_inset
        inner_l = outer_l - 2.0 * wall_thickness
        inner_w = outer_w - 2.0 * wall_thickness

        outer_prism = _make_rounded_rect_prism(
            cx=0.0, cy=0.0,
            half_l=outer_l / 2.0,
            half_w=outer_w / 2.0,
            r=corner_radius,
            z_start=base_height,
            height=wall_height,
        )
        # Inner cavity: plain box (sharp inner corners), extended by ±_EPS
        # in Z to ensure a clean boolean subtraction.
        inner_box = BRepPrimAPI_MakeBox(
            gp_Pnt(-inner_l / 2.0, -inner_w / 2.0, base_height - _EPS),
            inner_l,
            inner_w,
            wall_height + 2.0 * _EPS,
        ).Shape()

        wall_solid = _cut(outer_prism, inner_box)

    # ------------------------------------------------------------------
    # 4. Hole cutter cylinders
    #
    #   Screw holes: pass through base + wall (full stack height).
    #   Pin holes  : pass through base only.
    #
    #   Each cylinder is extended by ±_EPS in Z so its faces do not
    #   coincide with the target material faces.
    # ------------------------------------------------------------------
    total_stack = base_height + wall_height   # height of full stack

    screw_hole_cyls: list = []
    for x, y in screw_hole_positions:
        screw_hole_cyls.append(
            _make_cylinder_cutter(
                x=x, y=y,
                z_start=-_EPS,
                height=total_stack + 2.0 * _EPS,
                radius=screw_hole_diameter / 2.0,
            )
        )

    pin_hole_cyls: list = []
    for x, y in pin_hole_positions:
        pin_hole_cyls.append(
            _make_cylinder_cutter(
                x=x, y=y,
                z_start=-_EPS,
                height=base_height + 2.0 * _EPS,
                radius=pin_hole_diameter / 2.0,
            )
        )

    # ------------------------------------------------------------------
    # 5. Assemble: fuse components, then subtract all holes
    # ------------------------------------------------------------------
    print("  Assembling components …")
    assembly = _fuse(base_solid, fins_solid)
    if wall_solid is not None:
        assembly = _fuse(assembly, wall_solid)

    print(
        f"  Subtracting "
        f"{len(screw_hole_cyls)} screw hole(s) + "
        f"{len(pin_hole_cyls)} pin hole(s) …"
    )
    for cyl in screw_hole_cyls:
        assembly = _cut(assembly, cyl)
    for cyl in pin_hole_cyls:
        assembly = _cut(assembly, cyl)

    solid = assembly

    # ------------------------------------------------------------------
    # 6. STEP export
    # ------------------------------------------------------------------
    step_path_str: Optional[str] = None
    if save:
        dest = Path(dest_folder) if dest_folder is not None else _DEFAULT_DEST
        out_path = _write_step(solid, dest, output_step)
        print(f"  STEP written → {out_path}")
        step_path_str = str(out_path)

    # ------------------------------------------------------------------
    # 7. Return result dict
    #
    #   "base", "fins", "wall"  are the RAW component shapes (no holes).
    #   "solid"                 is the fully assembled shape with all holes.
    # ------------------------------------------------------------------
    return {
        "solid":       solid,
        "base":        base_solid,
        "fins":        fins_solid,
        "wall":        wall_solid,
        "screw_holes": screw_hole_cyls if screw_hole_cyls else None,
        "pin_holes":   pin_hole_cyls   if pin_hole_cyls   else None,
        "step_path":   step_path_str,
    }


# ===========================================================================
# Script entry-point
# ===========================================================================
if __name__ == "__main__":

    # Common geometry shared by both variants
    _COMMON = dict(
        base_length=100.0,
        base_width=80.0,
        base_height=4.0,
        corner_radius=5.0,
        # Fin array — 16 fins of 1.5 mm, 2 mm channels, 80 mm long
        fin_height=8.0,
        fin_thickness=1.5,
        fin_spacing=2.0,
        fin_number=16,
        channel_length=80.0,
        # Screw holes at four corners (M3.5 drill ⌀3.5 mm)
        screw_hole_positions=[
            (-44.0, -34.0), (+44.0, -34.0),
            (+44.0, +34.0), (-44.0, +34.0),
        ],
        screw_hole_diameter=3.5,
        # Centering pin holes along centre line (⌀2.5 mm)
        pin_hole_positions=[(0.0, +25.0), (0.0, -25.0)],
        pin_hole_diameter=2.5,
        save=True,
        dest_folder=None,   # → data/CAD_generated/
    )

    # ------------------------------------------------------------------
    # Variant A: flat base — no surrounding wall
    # ------------------------------------------------------------------
    print("Building cold plate — variant A (no wall) …")
    result_a = build_cold_plate(
        **_COMMON,
        wall_height=0.0,
        output_step="cold_plate_base.step",
    )
    print(f"  solid type : {result_a['solid'].ShapeType()}")
    print(f"  STEP       : {result_a['step_path']}")
    print()

    # ------------------------------------------------------------------
    # Variant B: with surrounding wall
    #   wall 3 mm thick, 10 mm tall, inset 2 mm from base edge
    #   → outer 96×76 mm, inner 90×70 mm cavity
    #   → fin array 80×54 mm fits inside ✓
    # ------------------------------------------------------------------
    print("Building cold plate — variant B (with wall) …")
    result_b = build_cold_plate(
        **_COMMON,
        wall_thickness=3.0,
        wall_height=10.0,
        wall_inset=2.0,
        output_step="cold_plate_wall.step",
    )
    print(f"  solid type : {result_b['solid'].ShapeType()}")
    print(f"  STEP       : {result_b['step_path']}")
    print()
    print("Done.")
