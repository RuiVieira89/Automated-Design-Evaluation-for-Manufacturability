"""Post-process a parametric heat sink by subtracting an arbitrary smooth pocket.

The baseline heat sink is generated in-memory by calling :func:`build_heat_sink`
from :mod:`CAD_heatSink`.  An arbitrary 2D profile defined by ordered (x, y)
control points is interpolated as a smooth **periodic B-spline**, extruded into
a 3D pocket, and subtracted from the top of the fin array.

Profile coordinate convention
------------------------------
Points are supplied in a **local 2D frame** whose reference point is the
**bounding-box centre** of the supplied point set (min+max)/2 for each axis).
Before building the B-spline the function shifts all points so that this
centre lands exactly at the local origin; the resulting pocket is then centred
over the mid-point of the fin-array bounding box in X and Y.

If the last supplied point is equal to the first (within 1 × 10⁻⁹ mm) it is
dropped automatically, because the periodic B-spline closes the curve without
a repeated endpoint.

Pipeline
--------
::

    (x, y) control points
        → drop closing duplicate (if any)
        → auto-centre to bounding-box centre
        → enforce CCW orientation (shoelace test → reverse if CW)
        → GeomAPI_Interpolate(PeriodicFlag=True)  →  Geom_BSplineCurve
        → BRepBuilderAPI_MakeEdge   →  closed edge
        → BRepBuilderAPI_MakeWire   →  closed wire
        → BRepBuilderAPI_MakeFace(wire, OnlyPlane=True)  →  planar face (z = 0 local)
        → BRepPrimAPI_MakePrism(face, (0, 0, −depth))  →  pocket solid
        → rotate  shape_rotation_deg  about Z at local origin
        → translate to  (center_x, center_y, top_z)
        → BRepAlgoAPI_Cut(heat_sink, pocket)
        → STEP export

Validation
----------
The function raises a :exc:`RuntimeError` with a descriptive message if:

* fewer than 3 distinct control points are supplied,
* the B-spline interpolation fails,
* the resulting wire is not topologically closed,
* the face construction fails (wire not planar), or
* the boolean cut fails.

Coordinate system  (same as :mod:`CAD_heatSink`)
-------------------------------------------------
* x — channel / extrusion direction  (length = ``channel_length``)
* y — fin-array direction             (width  = ``fin_number × fin_thickness``
                                               ``+ (fin_number − 1) × fin_spacing``)
* z — height                          (total  = ``base_height + fin_height``)

Usage
-----
As a library::

    from examples.case.heat_sink_example_V2.CAD_heatSink_shape import (
        build_heat_sink_with_shape,
        EXAMPLE_SHAPE_POINTS,
    )
    step_text = build_heat_sink_with_shape(
        shape_points=EXAMPLE_SHAPE_POINTS,
        shape_depth=5.0,
        shape_rotation_deg=45.0,
    )

As a script (saves to ``data/CAD_generated/``)::

    conda run -n auto_eval_manuf \\
        python examples/case/heat_sink_example_V2/CAD_heatSink_shape.py
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

from examples.case.heat_sink_example_V2.CAD_heatSink import build_heat_sink

from OCC.Core.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCC.Core.BRepBuilderAPI import (
    BRepBuilderAPI_MakeEdge,
    BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_MakeWire,
    BRepBuilderAPI_Transform,
)
from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakePrism
from OCC.Core.GeomAPI import GeomAPI_Interpolate
from OCC.Core.IFSelect import IFSelect_RetDone
from OCC.Core.STEPControl import STEPControl_AsIs, STEPControl_Reader, STEPControl_Writer
from OCC.Core.TColgp import TColgp_HArray1OfPnt
from OCC.Core.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec

# ---------------------------------------------------------------------------
# Default output location
# ---------------------------------------------------------------------------
_DEFAULT_DEST   = ROOT / "data" / "CAD_generated"
_DEFAULT_OUTPUT = "heat_sink_shape.step"

# ===========================================================================
# Example shape
# ===========================================================================

#: Default 6-point organic blob used when running the script directly.
#:
#: The smooth periodic B-spline through these six points produces a gently
#: asymmetric closed curve — neither a circle nor a regular polygon, with
#: continuously varying curvature and no sharp corners.
#:
#: Bounding box of the raw points: x ∈ [−10, +10] mm, y ∈ [−10, +10] mm.
#: After the auto-centering step the bounding-box centre is at the origin,
#: so the resulting pocket is 20 mm × 20 mm and sits well within the default
#: 50 mm × 37 mm fin-array footprint.
EXAMPLE_SHAPE_POINTS: list[tuple[float, float]] = [
    ( 10.0,   1.0),   # right of centre, slightly above mid-line
    (  5.0,   9.0),   # upper-right quadrant
    ( -4.0,  10.0),   # near top, offset left
    (-10.0,  -1.0),   # left of centre, slightly below mid-line
    ( -5.0, -10.0),   # lower-left quadrant
    (  6.0,  -9.0),   # lower-right quadrant
]


# ===========================================================================
# Internal helpers
# ===========================================================================

def _step_string_to_shape(step_text: str):
    """Return an OCC ``TopoDS_Shape`` loaded from a STEP text string.

    The string is written to a temporary file, read by ``STEPControl_Reader``,
    and the temporary file is immediately deleted.
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


def _signed_area_2d(pts: list[tuple[float, float]]) -> float:
    """Signed area of a polygon via the shoelace formula.

    Returns
    -------
    float
        Positive  → counter-clockwise (CCW) winding.
        Negative  → clockwise (CW) winding.
    """
    n = len(pts)
    acc = 0.0
    for i in range(n):
        j = (i + 1) % n
        acc += pts[i][0] * pts[j][1] - pts[j][0] * pts[i][1]
    return acc * 0.5


def _build_shape_pocket(
    shape_points: Sequence[tuple[float, float]],
    shape_depth: float,
    shape_rotation_deg: float,
    center_x: float,
    center_y: float,
    top_z: float,
):
    """Construct a positioned pocket solid from an arbitrary smooth 2D profile.

    Construction sequence
    ---------------------
    1. **Drop closing duplicate** — if the last point equals the first it is
       removed; the periodic B-spline closes without it.
    2. **Auto-centre** — shift all points so the bounding-box centre of the
       input set maps to the local origin (0, 0).
    3. **Enforce CCW winding** — compute signed area (shoelace); reverse the
       point order if it is negative.  This ensures the extruded prism has
       outward-pointing normals consistent with an additive boolean cut.
    4. **Periodic B-spline** via ``GeomAPI_Interpolate(PeriodicFlag=True)``.
       The curve is C² everywhere and passes through every control point.
       All z-coordinates are set to 0 so the profile lies in the XY plane.
    5. **Edge → wire** via ``BRepBuilderAPI_MakeEdge`` and
       ``BRepBuilderAPI_MakeWire``.  The wire is checked for topological
       closure before proceeding.
    6. **Planar face** via ``BRepBuilderAPI_MakeFace(wire, OnlyPlane=True)``.
       ``OnlyPlane=True`` causes the constructor to fail rather than silently
       produce a non-planar face.
    7. **Extrude downward** with ``BRepPrimAPI_MakePrism(face, (0, 0, −depth))``.
       The top face of the resulting solid is at z = 0 (local); the bottom is
       at z = −depth.  No depth clamping is applied — if depth > fin_height
       the pocket penetrates into the base plate.
    8. **Rotate** ``shape_rotation_deg`` degrees about the Z-axis at the local
       origin.
    9. **Translate** to ``(center_x, center_y, top_z)`` so the pocket is
       centred over the fin array with its top face flush with the fin tops.

    Parameters
    ----------
    shape_points:
        Ordered ``(x, y)`` control points in the shape's local frame [mm].
    shape_depth:
        Extrusion depth downward from ``top_z`` [mm].
    shape_rotation_deg:
        Rotation about the Z-axis [degrees] applied before translation.
    center_x, center_y:
        Global XY coordinates of the fin-array centroid [mm].
    top_z:
        Z-coordinate of the top face of the fin array [mm].

    Returns
    -------
    TopoDS_Shape
        Positioned pocket solid ready for ``BRepAlgoAPI_Cut``.

    Raises
    ------
    ValueError
        Fewer than 3 distinct control points after deduplication.
    RuntimeError
        Any OCC operation (interpolation, edge, wire, face, prism) fails.
    """
    # ------------------------------------------------------------------
    # 1. Drop closing duplicate
    # ------------------------------------------------------------------
    pts: list[tuple[float, float]] = list(shape_points)
    if (len(pts) >= 2
            and abs(pts[-1][0] - pts[0][0]) < 1e-9
            and abs(pts[-1][1] - pts[0][1]) < 1e-9):
        pts = pts[:-1]

    if len(pts) < 3:
        raise ValueError(
            f"At least 3 distinct control points are required; got {len(pts)} "
            "(after removing any closing duplicate)."
        )

    # ------------------------------------------------------------------
    # 2. Auto-centre: shift bounding-box centre to local origin
    # ------------------------------------------------------------------
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    bbox_cx = (min(xs) + max(xs)) * 0.5
    bbox_cy = (min(ys) + max(ys)) * 0.5
    pts = [(x - bbox_cx, y - bbox_cy) for x, y in pts]

    # ------------------------------------------------------------------
    # 3. Enforce CCW winding for correct prism solid orientation
    # ------------------------------------------------------------------
    if _signed_area_2d(pts) < 0.0:
        pts = list(reversed(pts))

    # ------------------------------------------------------------------
    # 4. Build TColgp_HArray1OfPnt (1-indexed) and run periodic B-spline
    # ------------------------------------------------------------------
    n = len(pts)
    occ_pts = TColgp_HArray1OfPnt(1, n)
    for idx, (x, y) in enumerate(pts):
        occ_pts.SetValue(idx + 1, gp_Pnt(x, y, 0.0))

    interp = GeomAPI_Interpolate(occ_pts, True, 1e-6)   # True = periodic / closed
    interp.Perform()
    if not interp.IsDone():
        raise RuntimeError(
            "GeomAPI_Interpolate failed.  Check that all control points are "
            "distinct (minimum separation 1 × 10⁻⁶ mm) and the profile is "
            "non-degenerate."
        )
    bspline = interp.Curve()   # Geom_BSplineCurve (periodic, C²)

    # ------------------------------------------------------------------
    # 5. Edge → wire, with closure validation
    # ------------------------------------------------------------------
    edge_maker = BRepBuilderAPI_MakeEdge(bspline)
    if not edge_maker.IsDone():
        raise RuntimeError(
            "BRepBuilderAPI_MakeEdge failed — the B-spline curve may be "
            "degenerate."
        )
    edge = edge_maker.Edge()

    wire_maker = BRepBuilderAPI_MakeWire(edge)
    if not wire_maker.IsDone():
        raise RuntimeError("BRepBuilderAPI_MakeWire failed.")
    wire = wire_maker.Wire()

    if not wire.Closed():
        raise RuntimeError(
            "The constructed wire is not topologically closed.  The periodic "
            "B-spline should produce a closed edge; verify the input points "
            "are well-separated and the profile is non-self-intersecting."
        )

    # ------------------------------------------------------------------
    # 6. Planar face (OnlyPlane=True → fail if wire is not planar)
    # ------------------------------------------------------------------
    face_maker = BRepBuilderAPI_MakeFace(wire, True)
    if not face_maker.IsDone():
        raise RuntimeError(
            f"BRepBuilderAPI_MakeFace failed (error code {face_maker.Error()}).  "
            "Ensure all control points have the same z-coordinate (the profile "
            "must be planar) and that the wire is properly closed."
        )
    face = face_maker.Face()

    # ------------------------------------------------------------------
    # 7. Extrude downward — top face at z = 0, bottom at z = −shape_depth
    # ------------------------------------------------------------------
    prism = BRepPrimAPI_MakePrism(face, gp_Vec(0.0, 0.0, -shape_depth))
    prism.Build()
    if not prism.IsDone():
        raise RuntimeError(
            "BRepPrimAPI_MakePrism failed.  The planar face may be invalid."
        )
    pocket = prism.Shape()

    # ------------------------------------------------------------------
    # 8. Optional rotation about Z
    # ------------------------------------------------------------------
    if abs(shape_rotation_deg) > 1e-9:
        rot = gp_Trsf()
        rot.SetRotation(
            gp_Ax1(gp_Pnt(0.0, 0.0, 0.0), gp_Dir(0.0, 0.0, 1.0)),
            math.radians(shape_rotation_deg),
        )
        pocket = BRepBuilderAPI_Transform(pocket, rot, True).Shape()

    # ------------------------------------------------------------------
    # 9. Translate to global position
    #    (center_x, center_y, top_z): centred over fins, top flush with tops
    # ------------------------------------------------------------------
    trs = gp_Trsf()
    trs.SetTranslation(gp_Vec(center_x, center_y, top_z))
    pocket = BRepBuilderAPI_Transform(pocket, trs, True).Shape()

    return pocket


# ===========================================================================
# Public API
# ===========================================================================

def build_heat_sink_with_shape(
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
    # Shape-pocket geometry                                               #
    # ------------------------------------------------------------------ #
    shape_points: Sequence[tuple[float, float]] = EXAMPLE_SHAPE_POINTS,
    shape_depth: float = 3.0,
    shape_rotation_deg: float = 45.0,
    # ------------------------------------------------------------------ #
    # Output control                                                      #
    # ------------------------------------------------------------------ #
    save: bool = True,
    output_step: str = _DEFAULT_OUTPUT,
    dest_folder: Optional[Path | str] = None,
) -> str:
    """Build a heat sink with a smooth arbitrary pocket cut from the fin tops.

    The function calls :func:`build_heat_sink` in-memory (no existing STEP
    file is read), round-trips the result through a temporary STEP file to
    recover an OCC solid, builds and positions the pocket, performs the boolean
    subtraction, and returns the modified solid as a STEP string.

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
    shape_points:
        Ordered ``[(x, y), …]`` control points defining the pocket profile
        in the shape's local 2D frame [mm].  A smooth periodic B-spline
        (C²-continuous) is interpolated through all points.

        * The profile is **auto-centred**: the bounding-box centre of the
          supplied point set is mapped to the local origin before building
          the B-spline.  You may pass non-centred points; they will be
          shifted automatically.
        * A closing duplicate endpoint is removed if present.
        * At least **3 distinct** points are required.
        * Defaults to :data:`EXAMPLE_SHAPE_POINTS`.

    shape_depth:
        Pocket depth [mm] measured downward from the top of the fins.
        If ``shape_depth > fin_height`` the cut continues into the base —
        no clamping is applied.
    shape_rotation_deg:
        Rotation of the pocket about the Z-axis [degrees] applied before
        translating to the fin-array centre.  Default 45°.
    save:
        Write the result to disk when ``True`` (default).
    output_step:
        File name of the output STEP file.
    dest_folder:
        Destination directory.  Defaults to
        ``<repo_root>/data/CAD_generated``.

    Returns
    -------
    str
        Full STEP file content of the heat sink with the pocket applied.

    Raises
    ------
    ValueError
        ``shape_points`` contains fewer than 3 distinct points.
    RuntimeError
        Any OCC operation (B-spline, wire, face, prism, boolean cut,
        or STEP export) fails.
    """
    # ------------------------------------------------------------------
    # 1. Build baseline heat sink (in-memory STEP string, no file I/O)
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
    # 2. Reload STEP string as an OCC shape
    # ------------------------------------------------------------------
    print("Parsing baseline STEP …")
    heat_sink_shape = _step_string_to_shape(step_text)

    # ------------------------------------------------------------------
    # 3. Derive pocket placement from heat-sink geometry
    # ------------------------------------------------------------------
    total_width  = fin_number * fin_thickness + (fin_number - 1) * fin_spacing
    total_height = base_height + fin_height

    center_x = channel_length / 2.0
    center_y = total_width    / 2.0

    n_pts = len(list(shape_points))
    print(
        f"Shape pocket: {n_pts} control points, depth={shape_depth} mm, "
        f"rotation={shape_rotation_deg}°  "
        f"(centred at x={center_x:.2f} mm, y={center_y:.2f} mm, "
        f"top z={total_height:.2f} mm)"
    )

    # ------------------------------------------------------------------
    # 4. Build the pocket solid
    # ------------------------------------------------------------------
    pocket_solid = _build_shape_pocket(
        shape_points=shape_points,
        shape_depth=shape_depth,
        shape_rotation_deg=shape_rotation_deg,
        center_x=center_x,
        center_y=center_y,
        top_z=total_height,
    )

    # ------------------------------------------------------------------
    # 5. Boolean cut: heat_sink − pocket
    # ------------------------------------------------------------------
    print("Performing boolean cut …")
    cut = BRepAlgoAPI_Cut(heat_sink_shape, pocket_solid)
    cut.Build()
    if not cut.IsDone():
        raise RuntimeError(
            "BRepAlgoAPI_Cut failed.  The pocket solid may be invalid, or it "
            "may lie entirely outside the heat-sink bounding box."
        )
    result_shape = cut.Shape()

    # ------------------------------------------------------------------
    # 6. Export modified solid to STEP (via temp file)
    # ------------------------------------------------------------------
    with tempfile.NamedTemporaryFile(suffix=".stp", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    writer = STEPControl_Writer()
    writer.Transfer(result_shape, STEPControl_AsIs)
    status = writer.Write(str(tmp_path))
    if status != IFSelect_RetDone:
        tmp_path.unlink(missing_ok=True)
        raise RuntimeError("STEPControl_Writer failed.")

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
    build_heat_sink_with_shape(
        # Heat-sink geometry (defaults match CAD_heatSink.py)
        fin_height=4.0,
        fin_thickness=0.1,
        fin_spacing=0.1,
        base_height=3.0,
        fin_number=int((50)/(0.1+0.1)),
        channel_length=50.0,
        # Pocket geometry
        shape_points=EXAMPLE_SHAPE_POINTS,
        shape_depth=3.0,
        shape_rotation_deg=45.0,
        # Output
        save=True,
        output_step="heat_sink_shape.step",
        dest_folder=None,           # → data/CAD_generated/
    )
