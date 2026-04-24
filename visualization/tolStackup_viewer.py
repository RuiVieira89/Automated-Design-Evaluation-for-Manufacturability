"""Tolerance stack-up visualizer.

Renders a three-panel matplotlib figure for a
:class:`~tolerance_advisor.toleranceStackup.StackUpResult`:

  Panel 1 — Dimension Chain Waterfall
    Floating bar chart showing how each contributor's signed nominal
    accumulates toward the final gap.  Tolerance ± bands are overlaid
    as shaded spans at each step.

  Panel 2 — Monte Carlo Gap Distribution
    Histogram of MC samples with vertical markers for the nominal gap,
    worst-case (WC) limits, RSS 3σ limits, and specification limits.

  Panel 3 — Sensitivity Pareto
    Horizontal bar chart ranking contributors by % variance contribution
    with a cumulative percentage line.  Guides where to tighten tolerances
    for maximum yield improvement.

Usage — library
---------------
    from tolerance_advisor.toleranceStackup import StackUpResult
    from visualization.tolStackup_viewer import view_stack_up
    view_stack_up(result)

Usage — CLI (self-contained demo, no STEP file needed)
-------------------------------------------------------
    python visualization/tolStackup_viewer.py
    python visualization/tolStackup_viewer.py --process CNC_milling
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, Tuple

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tolerance_advisor.toleranceStackup import StackUpResult, DimensionContributor

# ── colour palette ────────────────────────────────────────────────────────────
_C_POS     = "#2196F3"   # blue  — positive contributor
_C_NEG     = "#FF7043"   # deep-orange — negative contributor
_C_NOMINAL = "#E53935"   # red   — nominal gap line
_C_WC      = "#37474F"   # dark-grey — worst-case
_C_RSS     = "#1565C0"   # dark-blue  — RSS 3σ
_C_SPEC    = "#2E7D32"   # dark-green — spec limits
_C_MC_BAR  = "#90CAF9"   # light-blue — MC histogram bars
_C_PARETO  = "#7B1FA2"   # purple — sensitivity bars
_C_CUM     = "#D32F2F"   # red    — cumulative line on pareto

_ALPHA_TOL = 0.18        # transparency of tolerance shading in waterfall
_ALPHA_HIST = 0.75       # MC histogram bar alpha


# ══════════════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════════════

def view_stack_up(
    result: StackUpResult,
    title: str = "",
    show: bool = True,
    save_path: Optional[str] = None,
) -> Tuple[plt.Figure, np.ndarray]:
    """Render the three-panel tolerance stack-up figure.

    Parameters
    ----------
    result:
        Output of :func:`~tolerance_advisor.toleranceStackup.compute_stack_up`.
    title:
        Optional figure title override.
    show:
        Call ``plt.show()`` when *True*.  Pass *False* for testing or
        embedding in a larger figure.
    save_path:
        If given, save to this file path before showing (PNG/PDF/SVG).

    Returns
    -------
    (fig, axes)
        The matplotlib Figure and a 1-D array of the three Axes objects.
    """
    fig = plt.figure(figsize=(18, 7), constrained_layout=False)
    fig.subplots_adjust(left=0.13, right=0.97, bottom=0.13, top=0.91, wspace=0.42)
    gs  = fig.add_gridspec(1, 3, wspace=0.42)
    ax1 = fig.add_subplot(gs[0])
    ax2 = fig.add_subplot(gs[1])
    ax3 = fig.add_subplot(gs[2])
    axes = np.array([ax1, ax2, ax3])

    _draw_waterfall(ax1, result)
    _draw_histogram(ax2, result)
    _draw_pareto(ax3, result)

    heading = title or f"Tolerance Stack-Up: «{result.chain_name}»"
    fig.suptitle(heading, fontsize=13, fontweight="bold", y=1.01)

    _add_summary_text(fig, result)

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
    if show:
        plt.show()
    return fig, axes


# ══════════════════════════════════════════════════════════════════════════════
# Panel 1 — Dimension Chain Waterfall
# ══════════════════════════════════════════════════════════════════════════════

def _draw_waterfall(ax: plt.Axes, result: StackUpResult) -> None:
    cs = result.contributors
    if not cs:
        ax.text(0.5, 0.5, "No contributors", ha="center", va="center",
                transform=ax.transAxes)
        return

    n = len(cs)
    y_positions = list(range(n))
    labels      = [_short(c.name, 32) for c in cs]

    # Cumulative sums: bar i starts at cumsum[i-1] and spans contrib[i]
    contribs = np.array([c.effective_nominal for c in cs])
    tols     = np.array([c.tol_sym * abs(c.sensitivity) for c in cs])
    starts   = np.concatenate([[0.0], np.cumsum(contribs)[:-1]])
    colors   = [_C_POS if v >= 0 else _C_NEG for v in contribs]

    # ── floating bars ──
    ax.barh(
        y_positions, contribs, left=starts,
        color=colors, edgecolor="white", height=0.6, zorder=3,
    )

    # ── tolerance shading: semi-transparent bands around each bar ──
    for i, (start, contrib, tol, color) in enumerate(
        zip(starts, contribs, tols, colors)
    ):
        bar_lo = min(start, start + contrib) - tol
        bar_hi = max(start, start + contrib) + tol
        ax.barh(
            i, bar_hi - bar_lo, left=bar_lo,
            color=color, alpha=_ALPHA_TOL, height=0.6, zorder=2,
        )

    # ── cumulative step markers ──
    cum = np.cumsum(contribs)
    for i, (y, c_end) in enumerate(zip(y_positions, cum)):
        ax.plot(c_end, y, "o", color="#455A64", ms=5, zorder=4)

    # ── final nominal gap line ──
    ax.axvline(
        x=result.nominal_gap, color=_C_NOMINAL,
        linestyle="--", linewidth=1.6, zorder=5,
        label=f"Gap = {result.nominal_gap:+.3f} mm",
    )

    # ── spec limits (if provided) ──
    if result.spec_min is not None:
        ax.axvline(x=result.spec_min, color=_C_SPEC, linestyle=":",
                   linewidth=1.4, label=f"Spec min = {result.spec_min:+.3f}")
    if result.spec_max is not None:
        ax.axvline(x=result.spec_max, color=_C_SPEC, linestyle=":",
                   linewidth=1.4, label=f"Spec max = {result.spec_max:+.3f}")

    # ── aesthetics ──
    ax.set_yticks(y_positions)
    ax.set_yticklabels(labels, fontsize=8)
    ax.set_xlabel("Cumulative gap (mm)", fontsize=9)
    ax.set_title("Dimension Chain — Waterfall", fontsize=10, fontweight="bold")
    ax.invert_yaxis()
    ax.grid(axis="x", linestyle="--", alpha=0.4, zorder=0)
    ax.legend(fontsize=7.5, loc="lower right")

    # ── legend patches for + / – ──
    pos_patch = mpatches.Patch(color=_C_POS, label="Positive (+)")
    neg_patch = mpatches.Patch(color=_C_NEG, label="Negative (−)")
    ax.legend(
        handles=[pos_patch, neg_patch],
        loc="upper left", fontsize=7.5,
        title="Contribution", title_fontsize=7.5,
    )

    # ── nominal label ──
    ax.axvline(
        x=result.nominal_gap, color=_C_NOMINAL,
        linestyle="--", linewidth=1.5,
    )
    ax.text(
        result.nominal_gap, n - 0.3,
        f" Gap\n {result.nominal_gap:+.3f}",
        color=_C_NOMINAL, fontsize=7.5, va="top",
    )


# ══════════════════════════════════════════════════════════════════════════════
# Panel 2 — Monte Carlo Histogram
# ══════════════════════════════════════════════════════════════════════════════

def _draw_histogram(ax: plt.Axes, result: StackUpResult) -> None:
    samples = result.mc_samples
    n_bins  = min(120, max(40, len(samples) // 500))

    counts, bins, patches = ax.hist(
        samples, bins=n_bins,
        color=_C_MC_BAR, edgecolor="white", linewidth=0.3,
        alpha=_ALPHA_HIST, zorder=2,
        label=f"MC samples (n={len(samples):,})",
    )

    # ── shade spec region ──
    if result.spec_min is not None and result.spec_max is not None:
        ax.axvspan(
            result.spec_min, result.spec_max,
            color=_C_SPEC, alpha=0.08, zorder=1, label="Spec zone",
        )

    # ── vertical markers ──
    vlines = [
        (result.nominal_gap, _C_NOMINAL, "-",  2.0, f"Nominal {result.nominal_gap:+.3f}"),
        (result.wc_min,      _C_WC,      "--", 1.4, f"WC min {result.wc_min:+.3f}"),
        (result.wc_max,      _C_WC,      "--", 1.4, f"WC max {result.wc_max:+.3f}"),
        (result.rss_min,     _C_RSS,     "-.", 1.4, f"RSS min {result.rss_min:+.3f}"),
        (result.rss_max,     _C_RSS,     "-.", 1.4, f"RSS max {result.rss_max:+.3f}"),
    ]
    if result.spec_min is not None:
        vlines.append((result.spec_min, _C_SPEC, ":", 1.6, f"Spec min {result.spec_min:+.3f}"))
    if result.spec_max is not None:
        vlines.append((result.spec_max, _C_SPEC, ":", 1.6, f"Spec max {result.spec_max:+.3f}"))

    for x, color, ls, lw, label in vlines:
        ax.axvline(x=x, color=color, linestyle=ls, linewidth=lw,
                   label=label, zorder=4)

    # ── MC ±σ shading ──
    ax.axvspan(
        result.mc_mean - result.mc_std,
        result.mc_mean + result.mc_std,
        color="#B0BEC5", alpha=0.25, zorder=1, label="MC ±1σ",
    )

    # ── stats annotation box ──
    lines = [
        f"μ = {result.mc_mean:+.4f} mm",
        f"σ = {result.mc_std:.4f} mm",
        f"WC spread: {result.wc_max - result.wc_min:.4f} mm",
        f"RSS spread: {result.rss_max - result.rss_min:.4f} mm",
    ]
    if result.mc_yield_pct is not None:
        lines.append(f"Yield: {result.mc_yield_pct:.2f}%")
    if result.wc_passes_spec is not None:
        lines.append(f"WC: {'✓ PASS' if result.wc_passes_spec else '✗ FAIL'}")
    if result.rss_passes_spec is not None:
        lines.append(f"RSS: {'✓ PASS' if result.rss_passes_spec else '✗ FAIL'}")

    ax.text(
        0.97, 0.97, "\n".join(lines),
        transform=ax.transAxes,
        fontsize=7.5, va="top", ha="right",
        fontfamily="monospace",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="white",
                  alpha=0.9, edgecolor="#BDBDBD"),
    )

    # ── aesthetics ──
    ax.set_xlabel("Gap value (mm)", fontsize=9)
    ax.set_ylabel("Frequency", fontsize=9)
    ax.set_title("Monte Carlo Gap Distribution", fontsize=10, fontweight="bold")
    ax.legend(fontsize=7, loc="upper left", ncol=1)
    ax.grid(axis="y", linestyle="--", alpha=0.35, zorder=0)
    ax.tick_params(labelsize=8)


# ══════════════════════════════════════════════════════════════════════════════
# Panel 3 — Sensitivity Pareto
# ══════════════════════════════════════════════════════════════════════════════

def _draw_pareto(ax: plt.Axes, result: StackUpResult) -> None:
    if not result.sensitivity_ranking:
        ax.text(0.5, 0.5, "No data", ha="center", va="center",
                transform=ax.transAxes)
        return

    names = [_short(n, 28) for n, _ in result.sensitivity_ranking]
    pcts  = [p for _, p in result.sensitivity_ranking]
    cum   = np.cumsum(pcts)
    y_pos = list(range(len(names)))

    # ── colour by dominance ──
    bar_colors = []
    running = 0.0
    for p in pcts:
        running += p
        if running <= 50:
            bar_colors.append("#6A1B9A")   # deep purple — top contributors
        elif running <= 80:
            bar_colors.append("#AB47BC")   # medium purple
        else:
            bar_colors.append("#CE93D8")   # light purple

    ax.barh(y_pos, pcts, color=bar_colors, edgecolor="white",
            height=0.65, zorder=3)

    # ── cumulative % on twin x-axis ──
    ax2 = ax.twiny()
    ax2.plot(cum, y_pos, color=_C_CUM, marker="o", ms=4,
             linewidth=1.6, zorder=4, label="Cumulative %")
    ax2.set_xlim(0, 105)
    ax2.set_xlabel("Cumulative %", color=_C_CUM, fontsize=8)
    ax2.tick_params(axis="x", colors=_C_CUM, labelsize=7)

    # ── 80 % reference line ──
    ax2.axvline(x=80, color=_C_CUM, linestyle="--",
                linewidth=0.9, alpha=0.5, label="80 %")

    # ── % labels on bars ──
    for i, (p, y) in enumerate(zip(pcts, y_pos)):
        ax.text(p + 0.4, y, f"{p:.1f}%", va="center",
                fontsize=7, color="#37474F")

    # ── aesthetics ──
    ax.set_yticks(y_pos)
    ax.set_yticklabels(names, fontsize=8)
    ax.set_xlabel("% Variance Contribution", fontsize=9)
    ax.set_title("Sensitivity Pareto", fontsize=10, fontweight="bold")
    ax.set_xlim(0, max(pcts) * 1.25)
    ax.invert_yaxis()
    ax.grid(axis="x", linestyle="--", alpha=0.35, zorder=0)

    # ── colour legend ──
    patches = [
        mpatches.Patch(color="#6A1B9A", label="Top 50 %"),
        mpatches.Patch(color="#AB47BC", label="50–80 %"),
        mpatches.Patch(color="#CE93D8", label="Tail (>80 %)"),
    ]
    ax.legend(handles=patches, fontsize=7, loc="lower right")


# ══════════════════════════════════════════════════════════════════════════════
# Figure-level summary text box
# ══════════════════════════════════════════════════════════════════════════════

def _add_summary_text(fig: plt.Figure, result: StackUpResult) -> None:
    lines = [
        f"Chain: {result.chain_name}",
        f"Contributors: {len(result.contributors)}",
        f"Nominal gap: {result.nominal_gap:+.4f} mm",
        "",
        f"WC:  [{result.wc_min:+.4f}, {result.wc_max:+.4f}]",
        f"RSS: [{result.rss_min:+.4f}, {result.rss_max:+.4f}]",
        f"MC:  {result.mc_mean:+.4f} ± {result.mc_std:.4f}",
    ]
    if result.mc_yield_pct is not None:
        lines.append(f"Yield: {result.mc_yield_pct:.2f}%")

    fig.text(
        0.01, 0.99, "\n".join(lines),
        va="top", ha="left", fontsize=7.5,
        fontfamily="monospace",
        bbox=dict(
            boxstyle="round,pad=0.4",
            facecolor="white", alpha=0.88,
            edgecolor="#BDBDBD",
        ),
        transform=fig.transFigure,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Helper
# ══════════════════════════════════════════════════════════════════════════════

def _short(s: str, maxlen: int) -> str:
    """Truncate a string to *maxlen* characters with an ellipsis."""
    return s if len(s) <= maxlen else s[:maxlen - 1] + "…"


# ══════════════════════════════════════════════════════════════════════════════
# CLI entry point — self-contained demo (no STEP file required)
# ══════════════════════════════════════════════════════════════════════════════

def _cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Tolerance stack-up viewer — self-contained demo"
    )
    parser.add_argument(
        "--process", default="CNC_milling",
        help="Manufacturing process (used for demo chain tolerances)",
    )
    parser.add_argument(
        "--save", default=None,
        help="Optional output file path (PNG/PDF/SVG)",
    )
    parser.add_argument(
        "--step", default=None,
        help="Optional STEP file — derives chain from solid bounding box",
    )
    args = parser.parse_args()

    from tolerance_advisor.toleranceStackup import (
        StackUpChain, DimensionContributor, compute_stack_up,
        print_stack_up_report, contributors_from_solid,
    )

    if args.step:
        # ── derive chain from a real STEP file ──────────────────────────────
        try:
            from load_cad.step_reader import read_step_single
            from post_process.shape_normalizer import normalize_shape
            from post_process.shape_dimension import infer_dimensions
            from tolerance_advisor.helpers import load_process_capabilities
        except ImportError as exc:
            print(f"STEP loading requires pythonocc-core: {exc}", file=sys.stderr)
            sys.exit(1)

        print(f"Loading {args.step} …")
        compound   = read_step_single(args.step)
        normalized = normalize_shape(compound)
        shape_dims = infer_dimensions(normalized)
        db         = load_process_capabilities()

        contributors = contributors_from_solid(
            shape_dims.solids[0], process=args.process, db=db,
            include_cylinders=True, include_walls=False,
        )
        chain = StackUpChain(
            name=f"{Path(args.step).stem} — {args.process}",
            contributors=contributors,
        )

    else:
        # ── textbook 4-part linear stack demo ───────────────────────────────
        # Housing → Shaft → Spacer A → Spacer B → Housing datum
        # Critical gap: end-play between shaft shoulder and housing wall.
        chain = StackUpChain(
            name="shaft_end_play (demo)",
            spec_min=0.05,
            spec_max=0.40,
            contributors=[
                DimensionContributor(
                    "housing_internal_depth", 62.00, 0.12, 0.12,
                    sensitivity=-1.0, description="CNC milling",
                ),
                DimensionContributor(
                    "shaft_length", 55.00, 0.08, 0.08,
                    sensitivity=+1.0, description="CNC turning",
                ),
                DimensionContributor(
                    "spacer_A_width", 4.00, 0.04, 0.04,
                    sensitivity=+1.0, description="CNC turning",
                ),
                DimensionContributor(
                    "spacer_B_width", 2.80, 0.04, 0.04,
                    sensitivity=+1.0, description="CNC turning",
                ),
            ],
        )

    result = compute_stack_up(chain)
    print_stack_up_report(result)
    view_stack_up(result, save_path=args.save)


if __name__ == "__main__":
    _cli()
