"""PyVista-based visualization helpers for CAD files."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import numpy as np
    import pyvista as pv

    HAVE_PYVISTA = True
except Exception:  # pragma: no cover - import guard for optional dependency
    HAVE_PYVISTA = False

from load_cad.step_reader import read_step_single, tessellate_shape

# Colour palette for surface types – visually distinct, colour-blind friendly
_SURFACE_COLOURS: Dict[str, str] = {
    "Plane":    "#4C72B0",  # blue
    "Cylinder": "#C44E52",  # red
    "Cone":     "#DD8452",  # orange
    "Sphere":   "#55A868",  # green
    "Torus":    "#8172B3",  # purple
    "Bezier":   "#937860",  # brown
    "BSpline":  "#DA8BC3",  # pink
    "Other":    "#8C8C8C",  # grey
}


class VisualizationError(RuntimeError):
    """Raised when a visualization operation fails."""


def shape_to_pyvista(
    shape,
    deflection: float = 0.1,
    angle: float = 0.5,
) -> "pv.PolyData":
    """Convert a TopoDS_Shape into a PyVista PolyData mesh."""
    if not HAVE_PYVISTA:
        raise VisualizationError("pyvista is not installed")

    vertices, faces = tessellate_shape(shape, deflection=deflection, angle=angle)
    if not vertices or not faces:
        raise VisualizationError("No mesh data produced from STEP shape")

    vertices_np = np.asarray(vertices, dtype=float)
    faces_np = np.asarray(faces, dtype=int)
    face_sizes = np.full((faces_np.shape[0], 1), 3, dtype=int)
    faces_pv = np.hstack([face_sizes, faces_np]).ravel()

    return pv.PolyData(vertices_np, faces_pv)


def _face_to_pyvista(
    face,
    deflection: float = 0.1,
    angle: float = 0.5,
) -> Optional["pv.PolyData"]:
    """Tessellate a single ``TopoDS_Face`` into a PyVista PolyData.

    Returns ``None`` if the face produces no mesh triangles (degenerate face).
    """
    if not HAVE_PYVISTA:
        raise VisualizationError("pyvista is not installed")

    # Reuse the shape-level tessellator on a single face shape.
    vertices, tris = tessellate_shape(face, deflection=deflection, angle=angle)
    if not vertices or not tris:
        return None

    verts = np.asarray(vertices, dtype=float)
    f_np = np.asarray(tris, dtype=int)
    face_sizes = np.full((f_np.shape[0], 1), 3, dtype=int)
    faces_pv = np.hstack([face_sizes, f_np]).ravel()
    return pv.PolyData(verts, faces_pv)


def build_labeled_meshes(
    normalized_shape,
    solid_shapes: List,
    deflection: float = 0.1,
    angle: float = 0.5,
) -> Tuple[List["pv.PolyData"], List[str], List[Tuple[float, float, float]]]:
    """Build per-face coloured meshes, label strings, and label anchor points.

    Returns a 3-tuple:
    * ``face_meshes`` – one PolyData per face that tessellated successfully,
      with a ``"face_id"`` point scalar array attached.
    * ``labels`` – strings of the form ``"S{solid_id} F{face_id}\\n{type}"``
      for each successfully tessellated face.
    * ``centers`` – face centre-of-mass coordinates for label anchors.
    """
    if not HAVE_PYVISTA:
        raise VisualizationError("pyvista is not installed")

    from OCC.Core.TopTools import TopTools_IndexedMapOfShape
    from OCC.Core.TopAbs import TopAbs_FACE
    from OCC.Core.TopExp import TopExp_Explorer
    from OCC.Core.TopoDS import topods

    face_meshes: List["pv.PolyData"] = []
    labels: List[str] = []
    centers: List[Tuple[float, float, float]] = []

    for solid_data, solid_shape in zip(normalized_shape.solids, solid_shapes):
        # Collect indexed faces from the solid shape so we can tessellate them
        # individually in the same order as face_data.face_id.
        face_map = TopTools_IndexedMapOfShape()
        exp = TopExp_Explorer(solid_shape, TopAbs_FACE)
        while exp.More():
            face_map.Add(exp.Current())
            exp.Next()

        for face_data in solid_data.faces:
            occ_idx = face_data.face_id + 1  # TopTools uses 1-based indexing
            if occ_idx > face_map.Size():
                continue
            topoface = topods.Face(face_map.FindKey(occ_idx))
            mesh = _face_to_pyvista(topoface, deflection=deflection, angle=angle)
            if mesh is None:
                continue

            # Attach a scalar so each face can be coloured by face_id
            n_pts = mesh.n_points
            mesh.point_data["face_id"] = np.full(n_pts, face_data.face_id, dtype=int)

            face_meshes.append(mesh)
            labels.append(f"S{solid_data.solid_id} F{face_data.face_id}\n{face_data.surface_type}")
            centers.append(face_data.center)

    return face_meshes, labels, centers


def plot_normalized_shape(
    normalized_shape,
    solid_shapes: List,
    *,
    deflection: float = 0.1,
    angle: float = 0.5,
    show_labels: bool = True,
    show_edges: bool = True,
    off_screen: bool = False,
    screenshot_path: Optional[str] = None,
    window_size: Tuple[int, int] = (1400, 900),
) -> "pv.Plotter":
    """Render a :class:`~post_process.shape_normalizer.NormalizedShape` with
    per-face colour coding, arrow annotations, and text labels.

    Each face is coloured by its surface type (Plane = blue, Cylinder = orange,
    …).  An outward-pointing arrow is drawn from the face centre of mass and
    labelled with ``"S{solid_id} F{face_id}\\n{surface_type}"``.

    Parameters
    ----------
    normalized_shape:
        Result of :func:`~post_process.shape_normalizer.normalize_shape`.
    solid_shapes:
        List of ``TopoDS_Solid`` objects in the same order as
        ``normalized_shape.solids`` (returned by the collector in
        ``shape_normalizer._collect_solids``).
    deflection:
        Linear deflection used when tessellating faces.
    angle:
        Angular deflection used when tessellating faces.
    show_labels:
        When ``True``, add text labels at each face centre.
    show_edges:
        When ``True``, draw face edges as a wireframe overlay.
    off_screen:
        Render off-screen (useful for saving screenshots without a display).
    screenshot_path:
        If given, save a screenshot to this path after rendering.
    window_size:
        ``(width, height)`` of the render window in pixels.

    Returns
    -------
    pv.Plotter
        The configured plotter (after :meth:`~pyvista.Plotter.show` has been
        called).
    """
    if not HAVE_PYVISTA:
        raise VisualizationError("pyvista is not installed")

    face_meshes, labels, centers = build_labeled_meshes(
        normalized_shape, solid_shapes, deflection=deflection, angle=angle
    )
    if not face_meshes:
        raise VisualizationError("No face meshes could be tessellated")

    plotter = pv.Plotter(off_screen=off_screen, window_size=list(window_size))
    plotter.set_background("white")

    # --- Draw faces coloured by surface type ---
    # Build a lookup so we can quickly get the surface type for each face mesh.
    # face_meshes and labels are in the same order.
    for mesh, label in zip(face_meshes, labels):
        surf_type = label.split("\n")[-1]
        colour = _SURFACE_COLOURS.get(surf_type, _SURFACE_COLOURS["Other"])
        plotter.add_mesh(
            mesh,
            color=colour,
            opacity=0.85,
            show_edges=show_edges,
            edge_color="black",
            line_width=0.5,
        )

    # --- Labels ---
    if show_labels:
        centers_np = np.asarray(centers, dtype=float)
        label_pts = pv.PolyData(centers_np)
        label_pts["labels"] = labels
        plotter.add_point_labels(
            label_pts,
            "labels",
            font_size=10,
            point_color="red",
            point_size=6,
            render_points_as_spheres=True,
            always_visible=True,
            shape_opacity=0.6,
            shape_color="white",
        )

    # --- Legend ---
    legend_entries = [
        [surf_type, colour]
        for surf_type, colour in _SURFACE_COLOURS.items()
    ]
    plotter.add_legend(legend_entries, bcolor="white", border=True, size=(0.15, 0.35))

    plotter.show(screenshot=screenshot_path, auto_close=True)
    return plotter


def load_cad_file(
    path: str,
    *,
    deflection: float = 0.1,
    angle: float = 0.5,
) -> "pv.DataSet":
    """Load a CAD file into a PyVista dataset.

    STEP files are loaded via pythonocc-core and tessellated. Other formats are
    delegated to PyVista's reader backend.
    """
    if not HAVE_PYVISTA:
        raise VisualizationError("pyvista is not installed")

    suffix = Path(path).suffix.lower()
    if suffix in {".step", ".stp"}:
        shape = read_step_single(path)
        return shape_to_pyvista(shape, deflection=deflection, angle=angle)

    return pv.read(path)


def plot_cad_file(
    path: str,
    *,
    deflection: float = 0.1,
    angle: float = 0.5,
    off_screen: bool = True,
    screenshot_path: Optional[str] = None,
) -> "pv.DataSet":
    """Load a CAD file and display it using PyVista.

    Returns the generated dataset for further inspection.
    """
    if not HAVE_PYVISTA:
        raise VisualizationError("pyvista is not installed")

    dataset = load_cad_file(path, deflection=deflection, angle=angle)

    plotter = pv.Plotter(off_screen=off_screen)
    plotter.add_mesh(dataset, color="lightgray", show_edges=False)
    plotter.show(screenshot=screenshot_path, auto_close=True)

    return dataset


__all__ = [
    "plot_cad_file",
    "plot_normalized_shape",
    "build_labeled_meshes",
    "load_cad_file",
    "shape_to_pyvista",
    "VisualizationError",
    "HAVE_PYVISTA",
]
