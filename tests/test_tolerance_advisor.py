from tolerance_advisor.iso286 import propose_tolerance
from tolerance_advisor.helpers import load_process_capabilities


def load_sample_db():
    # Use the package helper which will prefer YAML and fall back to JSON.
    return load_process_capabilities()


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
