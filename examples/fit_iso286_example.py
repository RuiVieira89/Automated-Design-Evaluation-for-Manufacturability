"""ISO 286 fit advisor example.

Demonstrates evaluate_fit() with fit_category and clearance_type as inputs
— the pattern used when these values are supplied by upstream modules.

Scenarios
---------
  1. Single fit evaluation: Ø 25 mm shaft/bore, sliding clearance fit
  2. Same nominal across all standard fits (comparison table)
  3. Same fit type across a range of nominal diameters
  4. Simulated upstream-module inputs (fit_category + clearance_type as variables)

Run from the repository root:
    python examples/fit_iso286_example.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tolerance_advisor.fit_iso286 import (
    FitResult,
    evaluate_fit,
    list_fit_options,
    select_fit,
)


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _header(title: str) -> None:
    print()
    print("=" * 66)
    print(f"  {title}")
    print("=" * 66)


def _row(label: str, value: str) -> None:
    print(f"  {label:<38} {value}")


def _print_fit(result: FitResult) -> None:
    print()
    _row("Fit designation", result.fit_designation)
    _row("Nominal diameter", f"{result.nominal_mm} mm")
    _row("Description", result.description)
    print()
    _row("Hole limits",
         f"{result.hole_min_mm:.4f} / {result.hole_max_mm:.4f} mm"
         f"  (EI={result.hole_EI_mm*1000:+.1f} µm, ES={result.hole_ES_mm*1000:+.1f} µm)")
    _row("Shaft limits",
         f"{result.shaft_min_mm:.4f} / {result.shaft_max_mm:.4f} mm"
         f"  (ei={result.shaft_ei_mm*1000:+.1f} µm, es={result.shaft_es_mm*1000:+.1f} µm)")
    print()
    max_c = result.max_clearance_mm * 1000
    min_c = result.min_clearance_mm * 1000
    label_max = "Max clearance" if max_c >= 0 else "Max clearance (−=interference)"
    label_min = "Min clearance" if min_c >= 0 else "Min clearance (−=interference)"
    _row(label_max, f"{max_c:+.1f} µm")
    _row(label_min, f"{min_c:+.1f} µm")

    if result.is_always_clearance():
        assembly = "Always clearance"
    elif result.is_always_interference():
        assembly = "Always interference"
    else:
        assembly = "Transition (clearance or interference depending on actual sizes)"
    _row("Assembly character", assembly)


# ---------------------------------------------------------------------------
# Scenario 1: Single fit evaluation
# ---------------------------------------------------------------------------

def demo_single_fit() -> None:
    _header("Scenario 1 — Single fit: Ø 25 mm, sliding clearance")

    # These values come from an upstream module in the real pipeline
    fit_category   = "clearance"
    clearance_type = "sliding"
    nominal_mm     = 25.0

    result = evaluate_fit(nominal_mm, fit_category, clearance_type)
    _print_fit(result)


# ---------------------------------------------------------------------------
# Scenario 2: All standard fits for one nominal diameter
# ---------------------------------------------------------------------------

def demo_all_fits() -> None:
    _header("Scenario 2 — All standard ISO 286-2 preferred fits at Ø 50 mm")

    nominal_mm = 50.0
    header = f"  {'Fit':<10} {'Category':<14} {'Type':<22} {'Max cl. µm':>10} {'Min cl. µm':>10}  {'Character'}"
    print()
    print(header)
    print("  " + "-" * 84)

    for category, types in list_fit_options().items():
        for ctype in types:
            r = evaluate_fit(nominal_mm, category, ctype)
            max_c = r.max_clearance_mm * 1000
            min_c = r.min_clearance_mm * 1000
            if r.is_always_clearance():
                char = "clearance"
            elif r.is_always_interference():
                char = "interference"
            else:
                char = "transition"
            print(f"  {r.fit_designation:<10} {category:<14} {ctype:<22} "
                  f"{max_c:>+10.1f} {min_c:>+10.1f}  {char}")


# ---------------------------------------------------------------------------
# Scenario 3: One fit type across multiple nominal sizes
# ---------------------------------------------------------------------------

def demo_size_series() -> None:
    _header("Scenario 3 — H7/k6 transition fit across nominal diameters")

    fit_category   = "transition"
    clearance_type = "accurate_location"

    nominals = [6, 10, 18, 25, 40, 50, 80, 100]
    print()
    print(f"  {'Nominal mm':>10}  {'Hole min':>10}  {'Hole max':>10}  "
          f"{'Shaft min':>10}  {'Shaft max':>10}  {'Max cl µm':>10}  {'Min cl µm':>10}")
    print("  " + "-" * 76)
    for nom in nominals:
        r = evaluate_fit(nom, fit_category, clearance_type)
        print(f"  {nom:>10.1f}  {r.hole_min_mm:>10.4f}  {r.hole_max_mm:>10.4f}  "
              f"{r.shaft_min_mm:>10.4f}  {r.shaft_max_mm:>10.4f}  "
              f"{r.max_clearance_mm*1000:>+10.1f}  {r.min_clearance_mm*1000:>+10.1f}")


# ---------------------------------------------------------------------------
# Scenario 4: Simulated upstream-module inputs
# ---------------------------------------------------------------------------

def demo_upstream_inputs(fit_category: str, clearance_type: str, nominal_mm: float) -> None:
    _header(f"Scenario 4 — Upstream inputs: category={fit_category!r}, "
            f"type={clearance_type!r}, Ø {nominal_mm} mm")

    result = evaluate_fit(nominal_mm, fit_category, clearance_type)
    _print_fit(result)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    demo_single_fit()
    demo_all_fits()
    demo_size_series()

    # Simulated upstream module outputs — replace with real module calls in production
    demo_upstream_inputs("interference", "medium", 80.0)

    print()


if __name__ == "__main__":
    main()
