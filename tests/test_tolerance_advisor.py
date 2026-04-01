import json
from tolerance_advisor.iso286 import propose_tolerance


def load_sample_db():
    p = "tolerance_advisor/process_capabilities.json"
    with open(p, "r") as fh:
        return json.load(fh)


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
