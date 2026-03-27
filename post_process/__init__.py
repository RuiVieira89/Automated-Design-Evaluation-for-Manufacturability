"""Post-processing utilities for normalized CAD topology."""

from .shape_normalizer import (
    AssemblyNode,
    FaceData,
    NormalizedShape,
    SolidData,
    extract_solids,
    normalize_shape,
)

__all__ = [
    "normalize_shape",
    "extract_solids",
    "NormalizedShape",
    "SolidData",
    "FaceData",
    "AssemblyNode",
]
