"""Tolerance advisor example.

Demonstrates all five ISO helpers in the tolerance_advisor package using a
realistic engineering scenario: a machined shaft with a bearing housing.

    Shaft Ø 25 mm  ─── CNC turning
    Housing bore Ø 52 mm  ─── cylindrical grinding
    Housing flange face (flatness)  ─── CNC turning
    Sand-cast base plate, several nominal dimensions  ─── sand casting

Run from the repository root:
    python examples/tolerance_advisor_example.py
    python examples/tolerance_advisor_example.py --process injection_moulding --nominal 18
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make the repository root importable when this file is run directly.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tolerance_advisor.helpers import load_process_capabilities
from tolerance_advisor.fit_iso286 import propose_tolerance, fundamental_tolerance
from tolerance_advisor.linTol_iso2768 import linear_tol_iso2768 as fundamental_tol_iso2768, propose_general_tolerance
from tolerance_advisor.geoTol_iso1101 import propose_geometric_tolerance
from tolerance_advisor.iso4287_4288 import propose_surface_roughness, ra_to_rz
from tolerance_advisor.iso8015 import apply_independence_principle, simple_dimensioning_checks

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _header(title: str) -> None:
    width = 60
    print()
    print("=" * width)
    print(f"  {title}")
    print("=" * width)


def _row(label: str, value: str) -> None:
    print(f"  {label:<35} {value}")


# ---------------------------------------------------------------------------
# Scenario data
# ---------------------------------------------------------------------------

# Nominal dimensions used throughout the example
SHAFT_DIAMETER_MM = 25.0
BORE_DIAMETER_MM = 52.0
FLANGE_FACE_MM = 80.0  # feature size for flatness check

# The process capability database is loaded once from the bundled YAML.
# You can pass a custom path: load_process_capabilities(Path("my_db.yaml"))
DB = load_process_capabilities()


# ---------------------------------------------------------------------------
# ISO 286 — Fundamental tolerances
# ---------------------------------------------------------------------------

def demo_iso286() -> None:
    _header("ISO 286-1 — Fundamental tolerances")

    shaft_result = propose_tolerance(SHAFT_DIAMETER_MM, "CNC_turning", DB)
    bore_result = propose_tolerance(BORE_DIAMETER_MM, "cylindrical_grinding", DB)

    print()
    print("  Shaft (CNC turning)")
    _row("  Nominal diameter", f"{shaft_result['nominal_mm']} mm")
    _row("  IT grade", shaft_result["it_grade"])
    _row("  Tolerance (±)", f"{shaft_result['tolerance_mm'] * 1000:.3f} µm  "
                             f"({shaft_result['tolerance_mm']:.6f} mm)")
    _row("  Achievable grades", ", ".join(shaft_result["achievable_grades"]))
    _row("  Typical Ra", f"{shaft_result['typical_ra_um']} µm")

    print()
    print("  Housing bore (cylindrical grinding)")
    _row("  Nominal diameter", f"{bore_result['nominal_mm']} mm")
    _row("  IT grade", bore_result["it_grade"])
    _row("  Tolerance (±)", f"{bore_result['tolerance_mm'] * 1000:.3f} µm  "
                             f"({bore_result['tolerance_mm']:.6f} mm)")

    # Full ISO 286-1 grade table for the shaft diameter
    print()
    print("  ISO 286-1 full grade table (Ø 25 mm, IT01–IT18)")
    all_grades = ["IT01", "IT0"] + [f"IT{n}" for n in range(1, 19)]
    for grade in all_grades:
        tol = fundamental_tolerance(SHAFT_DIAMETER_MM, grade)
        _row(f"    {grade}", f"{tol * 1000:>9.3f} µm  ({tol:.6f} mm)")


# ---------------------------------------------------------------------------
# ISO 2768 — General tolerances
# ---------------------------------------------------------------------------

def demo_iso2768() -> None:
    _header("ISO 2768 — General tolerances")

    print()
    print("  General tolerance classes for Ø 25 mm")
    for cls in ("f", "m", "c", "v"):
        names = {"f": "fine", "m": "medium", "c": "coarse", "v": "very coarse"}
        tol = fundamental_tol_iso2768(SHAFT_DIAMETER_MM, cls)
        _row(f"    Class {cls} ({names[cls]})", f"± {tol:.4f} mm")

    print()
    print("  Process-suggested general tolerance")
    for proc in ("CNC_turning", "sand_casting", "injection_moulding"):
        res = propose_general_tolerance(SHAFT_DIAMETER_MM, proc, DB)
        _row(f"    {proc}", f"class={res['class']}  ±{res['tolerance_mm']:.4f} mm")


# ---------------------------------------------------------------------------
# ISO 1101 — Geometric tolerances
# ---------------------------------------------------------------------------

def demo_iso1101() -> None:
    _header("ISO 1101 — Geometric tolerancing")

    print()
    print("  Proposed geometric tolerances — housing flange (CNC turning)")
    for symbol in ("flatness", "parallelism", "perpendicularity", "position"):
        res = propose_geometric_tolerance(symbol, FLANGE_FACE_MM, "CNC_turning", DB)
        _row(f"    {symbol.capitalize()}", f"{res['tolerance_mm']:.4f} mm")

    print()
    print("  Proposed geometric tolerances — bore (cylindrical grinding)")
    for symbol in ("concentricity", "position"):
        res = propose_geometric_tolerance(symbol, BORE_DIAMETER_MM, "cylindrical_grinding", DB)
        _row(f"    {symbol.capitalize()}", f"{res['tolerance_mm']:.4f} mm")


# ---------------------------------------------------------------------------
# ISO 4287/4288 — Surface roughness
# ---------------------------------------------------------------------------

def demo_iso4287_4288() -> None:
    _header("ISO 4287/4288 — Surface texture (roughness)")

    print()
    for proc in ("CNC_turning", "cylindrical_grinding", "sand_casting", "injection_moulding"):
        res = propose_surface_roughness(proc, SHAFT_DIAMETER_MM, DB)
        ra = res["Ra_um"]
        rz = res["Rz_um"]
        # Handle lists (e.g. range of Ra values from DB)
        if isinstance(ra, list):
            ra_str = f"[{', '.join(str(v) for v in ra)}]"
            rz_str = f"[{', '.join(f'{ra_to_rz(v):.2f}' for v in ra)}]"
        else:
            ra_str = f"{ra:.2f}"
            rz_str = f"{rz:.2f}"
        _row(f"  {proc}", f"Ra = {ra_str} µm   Rz ≈ {rz_str} µm")

    print()
    print("  Ra → Rz conversions (heuristic Rz ≈ 4 × Ra)")
    for ra in (0.1, 0.4, 0.8, 1.6, 3.2, 6.3, 12.5, 25.0):
        _row(f"    Ra = {ra:>5.1f} µm", f"Rz ≈ {ra_to_rz(ra):.1f} µm")


# ---------------------------------------------------------------------------
# ISO 8015 — Independence principle and dimensioning checks
# ---------------------------------------------------------------------------

def demo_iso8015() -> None:
    _header("ISO 8015 — Dimensioning and tolerancing checks")

    # Example: shaft diameter + form tolerance modifiers from other checks
    shaft_tol = propose_tolerance(SHAFT_DIAMETER_MM, "CNC_turning", DB)["tolerance_mm"]
    bore_tol = propose_tolerance(BORE_DIAMETER_MM, "cylindrical_grinding", DB)["tolerance_mm"]

    print()
    print("  Independence principle — shaft vs bore assembly")
    # Modifiers: e.g. thermal expansion effect factor 1.1, assembly misalignment 0.9
    combined_shaft = apply_independence_principle(shaft_tol, modifiers=[1.1, 0.9])
    combined_bore = apply_independence_principle(bore_tol, modifiers=[1.05])
    _row("  Shaft tol (base)", f"{shaft_tol * 1000:.3f} µm")
    _row("  Shaft tol (with modifiers)", f"{combined_shaft * 1000:.3f} µm")
    _row("  Bore tol (base)", f"{bore_tol * 1000:.3f} µm")
    _row("  Bore tol (with modifiers)", f"{combined_bore * 1000:.3f} µm")

    print()
    print("  Dimensioning sanity checks")
    # Mix of valid and intentionally suspect dimensions
    dimensions = [
        ("shaft_diameter", SHAFT_DIAMETER_MM, shaft_tol),
        ("bore_diameter", BORE_DIAMETER_MM, bore_tol),
        ("bad_zero_nominal", 0.0, 0.005),      # nominal = 0 → warning
        ("bad_tol_too_large", 5.0, 10.0),       # tolerance > nominal → warning
    ]
    warnings = simple_dimensioning_checks(dimensions)
    if warnings:
        for w in warnings:
            print(f"    ⚠  {w}")
    else:
        print("    All dimensions OK")


# ---------------------------------------------------------------------------
# Custom-process demo (CLI)
# ---------------------------------------------------------------------------

def demo_custom(process: str, nominal: float) -> None:
    _header(f"Custom: Ø {nominal} mm  ·  process: {process}")
    print()

    t286 = propose_tolerance(nominal, process, DB)
    t2768 = propose_general_tolerance(nominal, process, DB)
    t1101_flat = propose_geometric_tolerance("flatness", nominal, process, DB)
    t_rough = propose_surface_roughness(process, nominal, DB)
    base_tol = t286["tolerance_mm"]
    final_tol = apply_independence_principle(base_tol)

    _row("  ISO 286 IT grade / tolerance",
         f"{t286['it_grade']}  →  ±{base_tol * 1000:.3f} µm")
    _row("  ISO 2768 general class / tolerance",
         f"{t2768['class']}  →  ±{t2768['tolerance_mm']:.4f} mm")
    _row("  ISO 1101 flatness",
         f"{t1101_flat['tolerance_mm']:.4f} mm")
    ra = t_rough["Ra_um"]
    if isinstance(ra, list):
        _row("  ISO 4287 Ra", f"{ra} µm")
    else:
        _row("  ISO 4287 Ra / Rz", f"{ra:.2f} µm  /  {t_rough['Rz_um']:.2f} µm")
    _row("  ISO 8015 final tolerance (independence)", f"±{final_tol * 1000:.3f} µm")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Tolerance advisor example — all five ISO helpers"
    )
    parser.add_argument(
        "--process",
        default=None,
        help="Process name (e.g. CNC_turning, cylindrical_grinding, sand_casting, injection_moulding)",
    )
    parser.add_argument(
        "--nominal",
        type=float,
        default=25.0,
        help="Nominal dimension in mm for the custom demo (default: 25.0)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Always run the full showcase
    demo_iso286()
    demo_iso2768()
    demo_iso1101()
    demo_iso4287_4288()
    demo_iso8015()

    # If a custom process was requested, run the combined summary as well
    if args.process:
        demo_custom(args.process, args.nominal)

    print()


if __name__ == "__main__":
    main()
