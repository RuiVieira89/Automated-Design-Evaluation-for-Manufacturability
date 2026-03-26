"""PyVista-based visualization helpers for STEP files."""

from __future__ import annotations

from typing import Optional

try:
    import numpy as np
    import pyvista as pv

    HAVE_PYVISTA = True
except Exception:  # pragma: no cover - import guard for optional dependency
    HAVE_PYVISTA = False

from io.step_reader import read_step_single, tessellate_shape


class StepVisualizationError(RuntimeError):
    """Raised when a STEP visualization operation fails."""


def shape_to_pyvista(
    shape,
    deflection: float = 0.1,
    angle: float = 0.5,
) -> "pv.PolyData":
    """Convert a TopoDS_Shape into a PyVista PolyData mesh."""
    if not HAVE_PYVISTA:
        raise StepVisualizationError("pyvista is not installed")

    vertices, faces = tessellate_shape(shape, deflection=deflection, angle=angle)
    if not vertices or not faces:
        raise StepVisualizationError("No mesh data produced from STEP shape")

    vertices_np = np.asarray(vertices, dtype=float)
    faces_np = np.asarray(faces, dtype=int)
    face_sizes = np.full((faces_np.shape[0], 1), 3, dtype=int)
    faces_pv = np.hstack([face_sizes, faces_np]).ravel()

    return pv.PolyData(vertices_np, faces_pv)


def plot_step_file(
    path: str,
    *,
    deflection: float = 0.1,
    angle: float = 0.5,
    off_screen: bool = True,
    screenshot_path: Optional[str] = None,
) -> "pv.PolyData":
    """Load a STEP file and display it using PyVista.

    Returns the generated PolyData for further inspection.
    """
    if not HAVE_PYVISTA:
        raise StepVisualizationError("pyvista is not installed")

    shape = read_step_single(path)
    polydata = shape_to_pyvista(shape, deflection=deflection, angle=angle)

    plotter = pv.Plotter(off_screen=off_screen)
    plotter.add_mesh(polydata, color="lightgray", show_edges=False)
    plotter.show(screenshot=screenshot_path, auto_close=True)

    return polydata


__all__ = [
    "plot_step_file",
    "shape_to_pyvista",
    "StepVisualizationError",
    "HAVE_PYVISTA",
]
