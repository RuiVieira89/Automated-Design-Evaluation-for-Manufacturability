"""Post-processing utilities for normalized CAD topology."""

# shape_normalizer requires pythonocc-core at import time; guard so that
# shape_dimension (and pure-Python consumers) can still be imported without OCC.
try:
    from .shape_normalizer import (
        AssemblyNode,
        FaceData,
        NormalizedShape,
        SolidData,
        extract_solids,
        normalize_shape,
    )
except ImportError:
    pass

from .shape_dimension import (
    infer_dimensions,
    infer_solid_dimensions,
    ShapeDimensions,
    SolidDimensions,
    CylindricalFeature,
    PlaneGroup,
    WallThickness,
)
from .dimension_minimal import (
    minimal_dimensions,
    minimal_solid_dimensions,
    MinimalDimensionSet,
    DimensionEntry,
)

__all__ = [
    "normalize_shape",
    "extract_solids",
    "NormalizedShape",
    "SolidData",
    "FaceData",
    "AssemblyNode",
    "infer_dimensions",
    "infer_solid_dimensions",
    "ShapeDimensions",
    "SolidDimensions",
    "CylindricalFeature",
    "PlaneGroup",
    "WallThickness",
    "minimal_dimensions",
    "minimal_solid_dimensions",
    "MinimalDimensionSet",
    "DimensionEntry",
]
