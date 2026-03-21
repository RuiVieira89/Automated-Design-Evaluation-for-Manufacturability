"""
Rule registry - maps check names to check classes.

Enables dynamic rule loading and scheduling without hard-wiring execution order.
"""

from typing import Dict, Type, Optional
from .base import DfxCheck


class RuleRegistry:
    """
    Registry of available DfX checks.

    Maps string names to check classes for dynamic instantiation.
    Used by dependency graph to schedule checks by name at runtime.
    """

    def __init__(self):
        """Initialize empty registry."""
        self._checks: Dict[str, Type[DfxCheck]] = {}

    def register(self, name: str, check_class: Type[DfxCheck]) -> None:
        """
        Register a check class.

        Args:
            name: Unique check identifier
            check_class: The DfxCheck subclass

        Raises:
            ValueError: If name already registered
        """
        if name in self._checks:
            raise ValueError(f"Check {name} already registered")
        self._checks[name] = check_class

    def unregister(self, name: str) -> None:
        """
        Unregister a check.

        Args:
            name: Check identifier

        Raises:
            KeyError: If check not found
        """
        del self._checks[name]

    def get(self, name: str) -> Type[DfxCheck]:
        """
        Get check class by name.

        Args:
            name: Check identifier

        Returns:
            The DfxCheck subclass

        Raises:
            KeyError: If check not found
        """
        if name not in self._checks:
            raise KeyError(f"Unknown check: {name}")
        return self._checks[name]

    def instantiate(self, name: str) -> DfxCheck:
        """
        Instantiate a check by name.

        Args:
            name: Check identifier

        Returns:
            An instance of the DfxCheck subclass

        Raises:
            KeyError: If check not found
        """
        check_class = self.get(name)
        return check_class(name)

    def list_checks(self) -> list:
        """Get list of registered check names."""
        return list(self._checks.keys())

    def is_registered(self, name: str) -> bool:
        """Check if a check is registered."""
        return name in self._checks