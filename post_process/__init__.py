"""Post-processing utilities for normalized CAD topology."""

from .shape_normalizer import (
    AssemblyNode,
    FaceData,
    NormalizedShape,
    SolidData,
    normalize_shape,
)

__all__ = [
    "normalize_shape",
    "NormalizedShape",
    "SolidData",
    "FaceData",
    "AssemblyNode",
]
