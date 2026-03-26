"""PyVista-based visualization helpers for CAD files."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

try:
    import numpy as np
    import pyvista as pv

    HAVE_PYVISTA = True
except Exception:  # pragma: no cover - import guard for optional dependency
    HAVE_PYVISTA = False

from load_cad.step_reader import read_step_single, tessellate_shape


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
    "load_cad_file",
    "shape_to_pyvista",
    "VisualizationError",
    "HAVE_PYVISTA",
]
