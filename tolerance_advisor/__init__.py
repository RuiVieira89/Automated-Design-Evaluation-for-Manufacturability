"""Tolerance advisor package.

Provides ISO tolerance calculation helpers.
"""

from .fit_iso286 import (
    IT_MULTIPLIERS,
    geometric_mean,
    standard_tolerance_factor,
    fundamental_tolerance,
    propose_tolerance,
    FitResult,
    list_fit_options,
    select_fit,
    hole_deviations,
    shaft_deviations,
    evaluate_fit,
)
from .helpers import load_process_capabilities, find_size_range, choose_process_entry
from .linTol_iso2768 import (
    linear_tol_iso2768,
    fundamental_tol_iso2768,
    angular_tol_iso2768,
    geometric_tol_iso2768,
    propose_general_tolerance,
    recommend_title_block,
    TitleBlockRecommendation,
    list_linear_classes,
    list_geo_classes,
    list_geo_characteristics,
)
from .geoTol_iso1101 import (
    GeoTolResult,
    propose_geometric_tolerance,
    recommend_geometric_tolerance,
    recommend_for_function,
    list_characteristics,
    list_functional_classes,
)
from .iso4287_4288 import propose_surface_roughness, ra_to_rz
from .GPS_iso8015 import (
    # constants
    REFERENCE_TEMPERATURE_C,
    REFERENCE_PRESSURE_PA,
    # enums
    GPSStandard,
    GPSModifier,
    GPSOperatorStep,
    FeatureType,
    # dataclasses
    GPSOperator,
    GPSInvocation,
    IndependencyResult,
    GPSFeatureSpec,
    # functions
    default_operator_chain,
    validate_invocation,
    check_independency,
    gps_specify_feature,
    dimensioning_checks,
    # backwards-compat shims
    apply_independence_principle,
    simple_dimensioning_checks,
)


__all__ = [
    "IT_MULTIPLIERS",
    "geometric_mean",
    "standard_tolerance_factor",
    "fundamental_tolerance",
    "propose_tolerance",
    "FitResult",
    "list_fit_options",
    "select_fit",
    "hole_deviations",
    "shaft_deviations",
    "evaluate_fit",
    "load_process_capabilities",
    "find_size_range",
    "choose_process_entry",
    "linear_tol_iso2768",
    "fundamental_tol_iso2768",
    "angular_tol_iso2768",
    "geometric_tol_iso2768",
    "propose_general_tolerance",
    "recommend_title_block",
    "TitleBlockRecommendation",
    "list_linear_classes",
    "list_geo_classes",
    "list_geo_characteristics",
    "GeoTolResult",
    "propose_geometric_tolerance",
    "recommend_geometric_tolerance",
    "recommend_for_function",
    "list_characteristics",
    "list_functional_classes",
    "propose_surface_roughness",
    "ra_to_rz",
    "REFERENCE_TEMPERATURE_C",
    "REFERENCE_PRESSURE_PA",
    "GPSStandard",
    "GPSModifier",
    "GPSOperatorStep",
    "FeatureType",
    "GPSOperator",
    "GPSInvocation",
    "IndependencyResult",
    "GPSFeatureSpec",
    "default_operator_chain",
    "validate_invocation",
    "check_independency",
    "gps_specify_feature",
    "dimensioning_checks",
    "apply_independence_principle",
    "simple_dimensioning_checks",
]
