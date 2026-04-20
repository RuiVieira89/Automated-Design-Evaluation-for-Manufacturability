"""Small shared helpers for the tolerance_advisor package.

These are pragmatic utilities (not full ISO specifications). The goal is to
provide small helpers used by the isoXXX modules in this package.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def load_process_capabilities(path: Optional[Path] = None) -> Dict[str, Any]:
    """Load the included process capabilities file.

        Behavior:
        - If `path` is provided, it must be a YAML file and will be loaded.
        - If `path` is not provided, `process_capabilities.yaml` in the package
            directory is required and will be loaded.

        YAML support requires PyYAML (`pip install pyyaml`). If PyYAML is not
        installed the function will raise ImportError with a helpful message.
    """
    pkg_dir = Path(__file__).parent
    if path is None:
        yaml_path = pkg_dir / "process_capabilities.yaml"
        if not yaml_path.exists():
            raise FileNotFoundError(
                "process_capabilities.yaml not found in package. "
                "Create it or pass a path to a YAML file to load."
            )
        path = yaml_path

    path = Path(path)
    suffix = path.suffix.lower()
    if suffix not in {".yaml", ".yml"}:
        raise ValueError("Only YAML process capability files are supported; provide a .yaml file")

    try:
        import yaml  # type: ignore
    except Exception as e:  # pragma: no cover - environment dependent
        raise ImportError(
            "PyYAML is required to load YAML process capability files. "
            "Install with 'pip install pyyaml'"
        ) from e

    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


SIZE_RANGES: List[Tuple[float, float]] = [
    (0.0, 3.0),
    (3.0, 6.0),
    (6.0, 30.0),
    (30.0, 120.0),
    (120.0, 400.0),
]


def find_size_range(nominal_mm: float) -> int:
    """Return index of SIZE_RANGES that contains nominal_mm.

    If out of range, returns the closest index (0 or last).
    """
    for i, (a, b) in enumerate(SIZE_RANGES):
        if a <= nominal_mm <= b:
            return i
    if nominal_mm < SIZE_RANGES[0][0]:
        return 0
    return len(SIZE_RANGES) - 1


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def choose_process_entry(process: str, process_db: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Return process DB entry; if missing, raise ValueError.

    Loads the bundled DB if not provided.
    """
    if process_db is None:
        process_db = load_process_capabilities()
    entry = process_db.get(process)
    if entry is None:
        raise ValueError(f"Unknown process: {process}")
    return entry
