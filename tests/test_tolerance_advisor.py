import sys
from pathlib import Path

# Make the repository root importable when running this file directly with
# plain `python tests/test_tolerance_advisor.py` so `tolerance_advisor` can be
# imported without requiring pytest to manage sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tolerance_advisor.iso286 import propose_tolerance


# In tests we prefer a small in-memory sample database to avoid requiring
# PyYAML or file-system access. This mirrors the entries in
# `tolerance_advisor/process_capabilities.yaml` used by the package.
SAMPLE_DB = {
    "CNC_turning": {
        "typical_it_grade": "IT8",
        "iso_it_grades": ["IT6", "IT7", "IT8", "IT9"],
        "surface_roughness_ra_um": [0.8, 1.6, 3.2],
        "min_feature_size_mm": 0.5,
        "applicable_materials": ["steel", "aluminium", "brass", "titanium"],
        "dimensional_range_mm": [1, 500],
    }
}


def load_sample_db():
    return SAMPLE_DB


def test_propose_tolerance_happy_path():
    db = load_sample_db()
    res = propose_tolerance(25.0, "CNC_turning", db)
    assert res["nominal_mm"] == 25.0
    assert res["process"] == "CNC_turning"
    assert res["it_grade"] == "IT8"
    # Tolerance should be a small positive number (around a few 10^-2 mm)
    assert 0.0 < res["tolerance_mm"] < 0.1


def test_propose_tolerance_unknown_process():
    db = load_sample_db()
    try:
        propose_tolerance(10.0, "nonexistent", db)
    except ValueError as e:
        assert "Unknown process" in str(e)
    else:
        raise AssertionError("Expected ValueError for unknown process")
