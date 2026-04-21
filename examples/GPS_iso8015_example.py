"""GPS master specification example — ISO 8015 orchestrating ISO 286, ISO 1101, ISO 2768.

This example demonstrates how GPS_iso8015 acts as the master GPS standard,
using gps_specify_feature() to drive ISO 286, ISO 1101, and ISO 2768 together
into a single, coherent feature specification under ISO 8015 rules.

Three engineering scenarios:

  Scenario A — Bearing housing bore  Ø 52 mm, cylindrical grinding
      Precision bore requiring tight ISO 286 fit, ISO 1101 geometric control,
      and an ISO 2768-fH title-block class.  Independency principle applies
      (size and form fulfilled separately).

  Scenario B — Locating pin  Ø 8 mm, CNC turning
      Critical location feature.  Same GPS chain, but demonstrates the
      Envelope requirement (ⓔ) coupling size and form at MMC.

  Scenario C — Sand-cast flange face  80 mm, sand casting
      Non-critical structural surface showing how coarse processes produce
      conservative ISO 2768-cL recommendations with corresponding ISO 1101
      form tolerances and the ISO 8015 scope warnings.

  Scenario D — ASME Y14.5 comparison
      Same bore as Scenario A but declared under ASME Y14.5 — shows how
      Rule #1 (envelope by default) changes the effective form limit vs. the
      ISO 8015 independency default.

Run from the repository root:
    python examples/GPS_iso8015_example.py
    python examples/GPS_iso8015_example.py --process injection_moulding --nominal 35 --function sliding_fit
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tolerance_advisor.helpers import load_process_capabilities
from tolerance_advisor.GPS_iso8015 import (
    gps_specify_feature,
    check_independency,
    GPSFeatureSpec,
    GPSInvocation,
    GPSModifier,
    GPSStandard,
    FeatureType,
    REFERENCE_TEMPERATURE_C,
    REFERENCE_PRESSURE_PA,
)

DB = load_process_capabilities()

WIDTH = 68


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _header(title: str) -> None:
    print()
    print("=" * WIDTH)
    print(f"  {title}")
    print("=" * WIDTH)


def _section(title: str) -> None:
    print()
    print(f"  --- {title} ---")


def _row(label: str, value: str) -> None:
    print(f"  {label:<36} {value}")


def _print_spec(spec: GPSFeatureSpec) -> None:
    """Render a GPSFeatureSpec to stdout in a structured, readable layout."""

    # Header block
    _row("Feature ID", spec.feature_id)
    _row("Feature type", spec.feature_type.value)
    _row("Nominal size", f"{spec.nominal_size_mm} mm")
    _row("Process", spec.process)
    _row("Functional class", spec.functional_class)
    _row("GPS modifier", spec.modifier.value)
    _row("GPS standard", spec.invocation.standard.value)
    _row("Reference conditions",
         f"{spec.reference_temperature_c} °C  /  {spec.reference_pressure_pa} Pa")

    # ISO 286 — dimensional fit
    _section("ISO 286 — Dimensional fit")
    if spec.size_tolerance:
        st = spec.size_tolerance
        _row("IT grade", st["it_grade"])
        _row("Tolerance", f"±{st['tolerance_mm']*1000:.3f} µm  ({st['tolerance_mm']:.6f} mm)")
        _row("Achievable grades", ", ".join(st.get("achievable_grades", [])))
    else:
        print("  ISO 286 not applicable for this feature type.")

    # ISO 2768 — general tolerance
    _section("ISO 2768 — General tolerance (background default)")
    if spec.general_tolerance:
        gt = spec.general_tolerance
        _row("Class", f"{gt['class']}  (covers unannotated, non-critical features only)")
        _row("Tolerance @ nominal", f"±{gt['tolerance_mm']} mm")
    else:
        print("  ISO 2768 not available.")

    # ISO 1101 — geometric tolerances
    _section("ISO 1101 — Geometric tolerances")
    if spec.geometric_tolerances:
        print(f"  {'Characteristic':<22} {'Category':<14} {'Tolerance':>12}  Zone geometry")
        print(f"  {'-'*22} {'-'*14} {'-'*12}  {'-'*28}")
        for r in spec.geometric_tolerances:
            datum_flag = "[D]" if r.requires_datum else "   "
            print(
                f"  {r.characteristic:<22} {r.category:<14} "
                f"{r.tolerance_mm*1000:>9.3f} µm  {datum_flag}  {r.zone_geometry}"
            )
    else:
        print("  No geometric tolerances available.")

    # ISO 4287/4288 — surface roughness
    _section("ISO 4287/4288 — Surface roughness")
    if spec.surface_texture:
        ra = spec.surface_texture["Ra_um"]
        rz = spec.surface_texture["Rz_um"]
        ra_str = str(ra) if isinstance(ra, list) else f"{ra:.2f}"
        _row("Ra (µm)", ra_str)
        _row("Rz (µm, approx)", f"{rz:.2f}")
    else:
        print("  Surface roughness not available.")

    # ISO 8015 — independency / envelope principle
    _section("ISO 8015 — Independency principle")
    if spec.independency:
        ind = spec.independency
        _row("Modifier", ind.modifier.value)
        _row("Independent (size ⊥ form)", str(ind.independent))
        _row("Envelope active", str(ind.envelope_active))
        _row("Size tolerance", f"{ind.size_tolerance_mm*1000:.3f} µm")
        _row("Form tolerance (tightest)", f"{ind.form_tolerance_mm*1000:.3f} µm")
        _row("Effective form limit", f"{ind.effective_form_limit_mm*1000:.3f} µm")
        for note in ind.notes:
            print(f"  ⚑  {note}")
    else:
        print("  Independency check not applicable (no size + form overlap).")

    # GPS operator chain
    _section("GPS operator chain (ISO 8015 §4.3)")
    for op in spec.operator_chain:
        print(f"  {op.step.name:<14}  {op.description}")

    # Warnings
    if spec.warnings:
        _section("Warnings")
        for w in spec.warnings:
            print(f"  ⚠  {w}")


# ---------------------------------------------------------------------------
# Scenario A — Bearing housing bore (independency default)
# ---------------------------------------------------------------------------

def scenario_bearing_bore() -> None:
    _header("Scenario A — Bearing housing bore  Ø 52 mm  ·  cylindrical grinding")
    print(
        "\n  GPS modifier : Ⓘ  (ISO 8015 independency — size and form independent)"
        "\n  The bore must satisfy its IT5 size tolerance AND each ISO 1101 geometric"
        "\n  tolerance separately.  Neither constrains the other automatically."
    )

    spec = gps_specify_feature(
        feature_id="bore_A",
        feature_type=FeatureType.INTERNAL_CYLINDER,
        nominal_size_mm=52.0,
        process="cylindrical_grinding",
        functional_class="bearing_bore",
        modifier=GPSModifier.INDEPENDENCY,
        process_db=DB,
    )
    print()
    _print_spec(spec)


# ---------------------------------------------------------------------------
# Scenario B — Locating pin (envelope requirement)
# ---------------------------------------------------------------------------

def scenario_locating_pin() -> None:
    _header("Scenario B — Locating pin  Ø 8 mm  ·  CNC turning")
    print(
        "\n  GPS modifier : ⓔ  (envelope requirement — couples size and form at MMC)"
        "\n  The pin must fit within a perfect cylindrical envelope at its MMC diameter."
        "\n  Form error cannot exceed the size tolerance at MMC — tighter than the"
        "\n  independency default when the form tolerance would otherwise be larger."
    )

    spec = gps_specify_feature(
        feature_id="pin_B",
        feature_type=FeatureType.EXTERNAL_CYLINDER,
        nominal_size_mm=8.0,
        process="CNC_turning",
        functional_class="locating_pin",
        modifier=GPSModifier.ENVELOPE,
        process_db=DB,
    )
    print()
    _print_spec(spec)


# ---------------------------------------------------------------------------
# Scenario C — Sand-cast flange face (coarse process, structural)
# ---------------------------------------------------------------------------

def scenario_flange_face() -> None:
    _header("Scenario C — Sand-cast flange face  80 mm  ·  sand casting")
    print(
        "\n  GPS modifier : Ⓘ  (independency — structural, non-critical surface)"
        "\n  ISO 2768-cL governs unannotated features.  ISO 1101 provides flatness and"
        "\n  position tolerances scaled to the coarse process capability.  ISO 8015"
        "\n  ensures each requirement is checked independently."
    )

    spec = gps_specify_feature(
        feature_id="flange_C",
        feature_type=FeatureType.FLAT_SURFACE,
        nominal_size_mm=80.0,
        process="sand_casting",
        functional_class="structural",
        modifier=GPSModifier.INDEPENDENCY,
        process_db=DB,
    )
    print()
    _print_spec(spec)


# ---------------------------------------------------------------------------
# Scenario D — ISO 8015 vs ASME Y14.5 side-by-side
# ---------------------------------------------------------------------------

def scenario_standard_comparison() -> None:
    _header("Scenario D — ISO 8015 vs ASME Y14.5  ·  Ø 52 mm bore  ·  cylindrical grinding")

    iso_inv = GPSInvocation(
        standard=GPSStandard.ISO_8015,
        title_block_text="Tolerancing according to ISO 8015",
    )
    asme_inv = GPSInvocation(
        standard=GPSStandard.ASME_Y14_5,
        title_block_text="ASME Y14.5-2018",
    )

    iso_spec = gps_specify_feature(
        "bore_iso", FeatureType.INTERNAL_CYLINDER, 52.0,
        "cylindrical_grinding", "bearing_bore",
        modifier=GPSModifier.INDEPENDENCY,
        invocation=iso_inv,
        process_db=DB,
    )
    asme_spec = gps_specify_feature(
        "bore_asme", FeatureType.INTERNAL_CYLINDER, 52.0,
        "cylindrical_grinding", "bearing_bore",
        modifier=GPSModifier.INDEPENDENCY,
        invocation=asme_inv,
        process_db=DB,
    )

    print()
    print(f"  {'Property':<38} {'ISO 8015':>12}   {'ASME Y14.5':>12}")
    print(f"  {'-'*38} {'-'*12}   {'-'*12}")

    iso_ind = iso_spec.independency
    asme_ind = asme_spec.independency

    rows = [
        ("Size tolerance (µm)",
         f"{iso_ind.size_tolerance_mm*1000:.3f}",
         f"{asme_ind.size_tolerance_mm*1000:.3f}"),
        ("Form tolerance — circularity (µm)",
         f"{iso_ind.form_tolerance_mm*1000:.3f}",
         f"{asme_ind.form_tolerance_mm*1000:.3f}"),
        ("Independency default",
         "YES  (Ⓘ)",
         "NO   (Rule #1)"),
        ("Envelope active",
         str(iso_ind.envelope_active),
         str(asme_ind.envelope_active)),
        ("Effective form limit (µm)",
         f"{iso_ind.effective_form_limit_mm*1000:.3f}",
         f"{asme_ind.effective_form_limit_mm*1000:.3f}"),
    ]
    for label, iso_val, asme_val in rows:
        print(f"  {label:<38} {iso_val:>12}   {asme_val:>12}")

    print()
    print("  Under ISO 8015 the circularity tolerance is checked independently of")
    print("  the size tolerance — a larger form error is permissible if the feature")
    print("  is within its size band.")
    print()
    print("  Under ASME Y14.5 Rule #1 (envelope by default) the effective form limit")
    print("  is capped at the size tolerance — the bore must fit within a perfect")
    print(f"  cylindrical envelope at MMC (Ø {52.0 - asme_ind.size_tolerance_mm:.4f} mm).")


# ---------------------------------------------------------------------------
# Custom scenario (CLI)
# ---------------------------------------------------------------------------

def scenario_custom(process: str, nominal: float, functional_class: str) -> None:
    _header(f"Custom  Ø {nominal} mm  ·  {process}  ·  {functional_class}")

    # Infer feature type from functional class
    cylindrical = {"bearing_bore", "locating_pin", "sliding_fit", "rotating_shaft"}
    flat = {"sealing_surface", "assembly_locator", "structural", "cosmetic", "general"}
    if functional_class in cylindrical:
        ftype = FeatureType.INTERNAL_CYLINDER
    elif functional_class in flat:
        ftype = FeatureType.FLAT_SURFACE
    else:
        ftype = FeatureType.EXTERNAL_CYLINDER

    spec = gps_specify_feature(
        feature_id=f"custom_{functional_class}",
        feature_type=ftype,
        nominal_size_mm=nominal,
        process=process,
        functional_class=functional_class,
        modifier=GPSModifier.INDEPENDENCY,
        process_db=DB,
    )
    print()
    _print_spec(spec)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="GPS master specification example — ISO 8015 / 286 / 1101 / 2768"
    )
    parser.add_argument("--process", default=None,
                        help="Process for custom scenario (e.g. injection_moulding)")
    parser.add_argument("--nominal", type=float, default=30.0,
                        help="Nominal size in mm (default: 30.0)")
    parser.add_argument("--function", default="general",
                        help="Functional class (default: general)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    scenario_bearing_bore()
    scenario_locating_pin()
    scenario_flange_face()
    scenario_standard_comparison()

    if args.process:
        scenario_custom(args.process, args.nominal, args.function)

    print()


if __name__ == "__main__":
    main()
