"""Shared tolerance definitions for cold-plate production drawings.

A single :func:`get_default_tolerance` entry-point returns a :class:`Tolerance`
instance.  Both drawing scripts (FreeCAD TechDraw and OCCT + ezdxf) import only
this function so tolerance values are never hardcoded outside this module.

Extensibility
-------------
:class:`Tolerance` is a frozen dataclass with ``plus``, ``minus``, and
``unit`` fields.  To support per-feature tolerances later, callers can be
updated to accept a ``Tolerance`` for each measured feature; the formatter
methods remain identical.

Example future usage::

    tols = {
        "hole_diameter": Tolerance(plus=0.0, minus=0.05, unit="mm"),
        "linear":        get_default_tolerance(),
    }
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Tolerance:
    """Symmetric or asymmetric dimensional tolerance.

    Attributes
    ----------
    plus:
        Upper deviation (positive, ≥ 0)  [unit].
    minus:
        Lower deviation (positive, ≥ 0)  [unit].
    unit:
        Unit string (default ``"mm"``).
    """

    plus:  float
    minus: float
    unit:  str = "mm"

    def __post_init__(self) -> None:
        if self.plus < 0.0 or self.minus < 0.0:
            raise ValueError(
                f"Tolerance values must be non-negative; "
                f"got plus={self.plus}, minus={self.minus}"
            )

    # ------------------------------------------------------------------
    # Constructors
    # ------------------------------------------------------------------

    @classmethod
    def symmetric(cls, value: float, unit: str = "mm") -> "Tolerance":
        """Create a symmetric ±value tolerance."""
        return cls(plus=value, minus=value, unit=unit)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_symmetric(self) -> bool:
        """True when ``plus == minus``."""
        return self.plus == self.minus

    def as_float(self) -> float:
        """Return the tolerance value for symmetric tolerances.

        Raises :exc:`ValueError` for asymmetric tolerances.
        """
        if not self.is_symmetric:
            raise ValueError(
                "as_float() is only valid for symmetric tolerances; "
                f"this tolerance has plus={self.plus}, minus={self.minus}"
            )
        return self.plus

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    def format_suffix(self) -> str:
        """Return the compact tolerance suffix, e.g. ``"±0.1"`` or ``"+0.1/-0.05"``."""
        if self.is_symmetric:
            return f"±{self.plus:g}"          # ±0.1
        return f"+{self.plus:g}/−{self.minus:g}"   # +0.1/−0.05

    def format_dim(self, value: float, decimals: int = 1) -> str:
        """Return a formatted dimension string with tolerance suffix.

        Example: ``format_dim(100.0)`` → ``"100.0 ±0.1"``.
        """
        fmt = f"{value:.{decimals}f} {self.format_suffix()}"
        return fmt

    def format_general_note(self) -> str:
        """Return the general tolerance note for the title block.

        Example: ``"UNLESS OTHERWISE SPECIFIED, ALL DIMENSIONS ±0.1 mm"``.
        """
        if self.is_symmetric:
            return (
                f"UNLESS OTHERWISE SPECIFIED, "
                f"ALL DIMENSIONS ±{self.plus:g} {self.unit}"
            )
        return (
            f"UNLESS OTHERWISE SPECIFIED, "
            f"ALL DIMENSIONS +{self.plus:g}/−{self.minus:g} {self.unit}"
        )


# ===========================================================================
# Public API
# ===========================================================================

def get_default_tolerance() -> Tolerance:
    """Return the project default dimensional tolerance: ±0.1 mm.

    Returns
    -------
    Tolerance
        Symmetric tolerance of 0.1 mm.  All drawing scripts must import and
        call this function; the value 0.1 must **not** be hardcoded elsewhere.
    """
    return Tolerance.symmetric(0.1, unit="mm")
