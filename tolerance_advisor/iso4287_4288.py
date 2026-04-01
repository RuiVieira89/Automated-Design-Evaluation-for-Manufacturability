"""Helpers for ISO 4287 / ISO 4288 (surface texture and roughness guidance).

This module provides pragmatic helpers to propose surface roughness (Ra)
and conversions (approximate Rz from Ra) based on process capabilities.
"""
from __future__ import annotations

from typing import Dict, Tuple

from .helpers import choose_process_entry


def propose_surface_roughness(process: str, feature_size_mm: float, process_db: Dict | None = None) -> Dict[str, float]:
    """Return recommended roughness values (Ra and approximate Rz) in micrometers.

    Uses the process DB's 'surface_roughness_ra_um' when available, otherwise
    derives a pragmatic estimate.
    """
    entry = choose_process_entry(process, process_db)
    ra = entry.get("surface_roughness_ra_um")
    if ra is None:
        # fallback heuristic: rougher for larger features
        base = 1.6  # micrometers
        factor = 1.0 + (feature_size_mm / 100.0)
        ra = base * factor
    # approximate Rz (common engineering relation: Rz ≈ 4 * Ra) - pragmatic
    rz = ra * 4.0
    return {"Ra_um": float(ra), "Rz_um": float(rz)}


def ra_to_rz(ra_um: float) -> float:
    """Approximate conversion from Ra to Rz (engineering heuristic)."""
    return ra_um * 4.0
