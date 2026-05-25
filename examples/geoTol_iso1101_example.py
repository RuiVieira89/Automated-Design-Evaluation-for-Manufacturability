"""ISO 1101 geometric tolerancing advisor — example.

Demonstrates the geoTol_iso1101 module across all five ISO 1101 categories
and the full set of functional contexts, using two realistic engineering
scenarios:

  Scenario A — Bearing housing bore, Ø 52 mm, cylindrical grinding
      Functional class: bearing_bore
      Explores all recommended characteristics with notes.

  Scenario B — Shaft seal face, Ø 30 mm, CNC turning
      Functional class: sealing_surface

  Scenario C — Locating pin, Ø 8 mm, CNC turning
      Functional class: locating_pin

  Scenario D — All categories survey
      One characteristic per ISO 1101 category to show the full coverage.

Run from the repository root:
    python examples/geoTol_iso1101_example.py
    python examples/geoTol_iso1101_example.py --process sand_casting --nominal 80 --function structural
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tolerance_advisor.helpers import load_process_capabilities
from tolerance_advisor.geoTol_iso1101 import (
    recommend_geometric_tolerance,
    recommend_for_function,
    list_characteristics,
    list_functional_classes,
    GeoTolResult,
)

DB = load_process_capabilities()

# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _header(title: str) -> None:
    width = 68
    print()
    print("=" * width)
    print(f"  {title}")
    print("=" * width)


def _subheader(title: str) -> None:
    print()
    print(f"  --- {title} ---")


def _result_row(r: GeoTolResult) -> None:
    datum_flag = "[datum]" if r.requires_datum else "       "
    print(
        f"    {r.characteristic:<22} {datum_flag}  "
        f"{r.tolerance_mm * 1000:>8.3f} µm  "
        f"({r.tolerance_mm:.5f} mm)"
    )
    for note in r.notes:
        print(f"        ⚑  {note}")


# ---------------------------------------------------------------------------
# Scenario A — Bearing housing bore
# ---------------------------------------------------------------------------

def scenario_bearing_bore() -> None:
    _header("Scenario A — Bearing housing bore  Ø 52 mm  ·  cylindrical grinding")

    results = recommend_for_function(
        functional_class="bearing_bore",
        feature_size_mm=52.0,
        process="cylindrical_grinding",
        datum_available=True,
        process_db=DB,
    )

    print()
    print(f"  {'Characteristic':<22} {'Datum?':<10} {'Tolerance':>14}  (mm)")
    print(f"  {'-'*22} {'-'*10} {'-'*14}  {'-'*10}")
    for r in results:
        _result_row(r)

    _subheader("Detail: cylindricity")
    r_cyl = recommend_geometric_tolerance(
        characteristic="cylindricity",
        feature_size_mm=52.0,
        process="cylindrical_grinding",
        functional_class="bearing_bore",
        datum_available=True,
        process_db=DB,
    )
    print(f"    Category      : {r_cyl.category}")
    print(f"    Zone geometry : {r_cyl.zone_geometry}")
    print(f"    IT grade      : IT{r_cyl.it_grade}")
    print(f"    Tolerance     : {r_cyl.tolerance_mm * 1000:.3f} µm  ({r_cyl.tolerance_mm:.6f} mm)")


# ---------------------------------------------------------------------------
# Scenario B — Shaft seal face
# ---------------------------------------------------------------------------

def scenario_sealing_surface() -> None:
    _header("Scenario B — Shaft seal face  Ø 30 mm  ·  CNC turning")

    results = recommend_for_function(
        functional_class="sealing_surface",
        feature_size_mm=30.0,
        process="CNC_turning",
        datum_available=True,
        process_db=DB,
    )

    print()
    print(f"  {'Characteristic':<22} {'Datum?':<10} {'Tolerance':>14}  (mm)")
    print(f"  {'-'*22} {'-'*10} {'-'*14}  {'-'*10}")
    for r in results:
        _result_row(r)

    print()
    print("  Note: surface finish (Ra/Rz per ISO 4287) must complement form tolerance.")
    print("  Use iso4287_4288.propose_surface_roughness for the paired Ra recommendation.")


# ---------------------------------------------------------------------------
# Scenario C — Locating pin
# ---------------------------------------------------------------------------

def scenario_locating_pin() -> None:
    _header("Scenario C — Locating pin  Ø 8 mm  ·  CNC turning")

    results = recommend_for_function(
        functional_class="locating_pin",
        feature_size_mm=8.0,
        process="CNC_turning",
        datum_available=True,
        process_db=DB,
    )

    print()
    print(f"  {'Characteristic':<22} {'Datum?':<10} {'Tolerance':>14}  (mm)")
    print(f"  {'-'*22} {'-'*10} {'-'*14}  {'-'*10}")
    for r in results:
        _result_row(r)

    _subheader("Datum warning — position without datum reference")
    r_no_datum = recommend_geometric_tolerance(
        characteristic="position",
        feature_size_mm=8.0,
        process="CNC_turning",
        functional_class="locating_pin",
        datum_available=False,
        process_db=DB,
    )
    _result_row(r_no_datum)


# ---------------------------------------------------------------------------
# Scenario D — One characteristic per ISO 1101 category
# ---------------------------------------------------------------------------

def scenario_category_survey() -> None:
    _header("Scenario D — All five ISO 1101 categories  ·  Ø 25 mm  ·  CNC turning")

    representatives = {
        "form":        "flatness",
        "orientation": "perpendicularity",
        "location":    "position",
        "runout":      "total_runout",
        "profile":     "profile_of_a_surface",
    }

    print()
    print(f"  {'Category':<14} {'Characteristic':<24} {'Tolerance':>14}  Zone geometry")
    print(f"  {'-'*14} {'-'*24} {'-'*14}  {'-'*30}")
    for cat, char in representatives.items():
        r = recommend_geometric_tolerance(
            characteristic=char,
            feature_size_mm=25.0,
            process="CNC_turning",
            functional_class="general",
            process_db=DB,
        )
        print(
            f"  {cat:<14} {char:<24} "
            f"{r.tolerance_mm * 1000:>10.3f} µm  {r.zone_geometry}"
        )


# ---------------------------------------------------------------------------
# Catalogue — all characteristics and functional classes
# ---------------------------------------------------------------------------

def show_catalogue() -> None:
    _header("Catalogue — supported characteristics and functional classes")

    _subheader("Characteristics by category")
    for cat in ("form", "orientation", "location", "runout", "profile"):
        chars = list_characteristics(cat)
        print(f"    {cat.capitalize():<14}: {', '.join(chars)}")

    _subheader("Functional classes")
    for fc in list_functional_classes():
        print(f"    {fc}")


# ---------------------------------------------------------------------------
# Custom scenario (CLI)
# ---------------------------------------------------------------------------

def scenario_custom(process: str, nominal: float, functional_class: str) -> None:
    _header(f"Custom  Ø {nominal} mm  ·  {process}  ·  {functional_class}")

    results = recommend_for_function(
        functional_class=functional_class,
        feature_size_mm=nominal,
        process=process,
        process_db=DB,
    )
    print()
    print(f"  {'Characteristic':<22} {'Datum?':<10} {'Tolerance':>14}  (mm)")
    print(f"  {'-'*22} {'-'*10} {'-'*14}  {'-'*10}")
    for r in results:
        _result_row(r)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ISO 1101 geometric tolerancing advisor example"
    )
    parser.add_argument("--process", default=None,
                        help="Override process for custom scenario (e.g. sand_casting)")
    parser.add_argument("--nominal", type=float, default=25.0,
                        help="Nominal feature size in mm (default: 25.0)")
    parser.add_argument("--function", default="general",
                        help="Functional class for custom scenario (default: general)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    scenario_bearing_bore()
    scenario_sealing_surface()
    scenario_locating_pin()
    scenario_category_survey()
    show_catalogue()

    if args.process:
        scenario_custom(args.process, args.nominal, args.function)

    print()


if __name__ == "__main__":
    main()
