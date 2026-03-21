"""
Geometry Kernel - Layer 2

Provides geometry processing capabilities with separate B-Rep and mesh tracks.
"""

from .geometry_kernel import GeometryKernel, GeometryInputs, GeometryOutputs, BRepResults, MeshResults
from .brep_kernel import BRepKernel
from .mesh_kernel import MeshKernel
from .tessellation import TessellationEngine

__all__ = [
    'GeometryKernel',
    'GeometryInputs',
    'GeometryOutputs',
    'BRepResults',
    'MeshResults',
    'BRepKernel',
    'MeshKernel',
    'TessellationEngine'
]