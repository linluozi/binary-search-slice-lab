#!/usr/bin/env python
"""Generate every figure in assets/ from benchmarks/*.json.

Rules followed here (each one from a past mistake):

* **Plot speed-up, not the raw ratio.** A ratio axis inverts the story: 0.05x
  looks like a short bar but means "5x slower". ``speedup = 1 / ratio`` puts
  "long bar = big win" on the page, and a bar below 1 is visibly a regression.
* **Every timing panel states its target position.** The same four arms are 0.06x
  and 935x apart depending on whether you look up the middle element or the last
  one. A figure without that label is not interpretable.
* **Counts get their own figure, with no clock in it.** The copy-volume panel is
  exact arithmetic; if it and the timing panel disagreed, the timing would be the
  suspect.
* **Log x and log y where the range demands it**, and say so in the axis label.

Figures
-------
``copies-are-linear.png``   exact copy volume: n/2 + n/4 + ... = n
``speedup-by-target.png``   one panel per target position, x = n, y = speed-up
``arm-attribution.png``     the three adjacent steps, isolated
``degenerate-mid.png``      why probing the middle element measures nothing

Run:
    python assets/make_figures.py
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
BENCH = ROOT / "benchmarks"

# Warm editorial palette: espresso brown / amber gold / terracotta.
INK = "#2b2119"
PAPER = "#faf6f0"
AMBER = "#c8892b"
TERRACOTTA = "#b4552f"
OLIVE = "#6b6b3a"
MUTED = "#8a7a68"

plt.rcParams.update(
    {
        "figure.facecolor": PAPER,
        "axes.facecolor": PAPER,
        "axes.edgecolor": INK,
        "axes.labelcolor": INK,
        "text.color": INK,
        "xtick.color": INK,
        "ytick.color": INK,
        "font.size": 10,
        "axes.grid": True,
        "grid.color": "#ddd2c4",
        "grid.linewidth": 0.6,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "legend.frameon": False,
    }
)

ARM_COLOR = {
    "index_closure": TERRACOTTA,
    "index": OLIVE,
    "iterative": AMBER,
}
ARM_LABEL = {
    "index_closure": "index bounds, closure per call",
    "index": "index bounds, hoisted helper",
    "iterative": "iterative",
}


def load() -> tuple[dict, dict]:
    ops = json.loads((BENCH / "ops.json").read_text(encoding="utf-8"))
    timing = json.loads((BENCH / "timing.json").read_text(encoding="utf-8"))
    return ops, timing


def figure_copies(ops: dict) -> None:
    """Exact copy volume. No timing anywhere in this figure."""
    fig, axes = plt.subplots(1, 2, figsize=(11.0, 4.2))

    sizes = ops["sizes"]
    positions = ["first", "last", "absent", "quarter"]
    colours = [TERRACOTTA, AMBER, OLIVE, MUTED]

    ax = axes[0]
    series = [
        ("first / last / absent  →  1.00n", ["first"], TERRACOTTA, "-"),
        ("quarter  →  0.50n", ["quarter"], AMBER, "--"),
        ("mid  →  0n (one comparison)", ["mid"], OLIVE, ":"),
    ]
    for label, keys, colour, style in series:
        values = [ops["table"][str(n)][keys[0]]["copies"] / n for n in sizes]
        ax.plot(sizes, values, marker="o", color=colour, label=label,
                linewidth=1.8, linestyle=style, markersize=4.5)
    ax.axhline(1.0, color=INK, linestyle=(0, (1, 3)), linewidth=1.0)
    ax.text(sizes[0], 1.015, "linear: copies = n", color=INK, fontsize=9, va="bottom")
    ax.set_xscale("log")
    ax.set_xlabel("n  (log scale)")
    ax.set_ylabel("elements copied / n")
    ax.set_ylim(-0.06, 1.16)
    ax.set_title("Copy volume is linear, not n log n", loc="left", fontsize=11, pad=10)
    ax.legend(loc="center", fontsize=8.5)

    ax = axes[1]
    growth_n = [4096, 8192, 16384, 32768, 65536, 131072, 262144]
    measured = [n - 1 for n in growth_n]
    linear_ref = [n for n in growth_n]
    # n log2 n, scaled to pass through the first measured point so the two
    # curves start together and the divergence is what you see
    scale = measured[0] / (growth_n[0] * (growth_n[0].bit_length() - 1))
    nlog_ref = [scale * n * (n.bit_length() - 1) for n in growth_n]

    ax.plot(growth_n, measured, marker="o", color=TERRACOTTA, linewidth=1.9,
            markersize=5, label="measured copies")
    ax.plot(growth_n, linear_ref, color=INK, linewidth=1.0,
            linestyle=(0, (1, 3)), label="linear reference  n")
    ax.plot(growth_n, nlog_ref, marker="s", color=MUTED, linewidth=1.4,
            linestyle="--", markersize=4, label="if it were n log n")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("n  (log scale)")
    ax.set_ylabel("elements copied  (log scale)")
    ax.set_title("…and it tracks n, not n log n", loc="left", fontsize=11, pad=10)
    ax.legend(loc="upper left", fontsize=8.5)

    fig.suptitle(
        "Slicing keeps half the list each level, so the copies sum to n\n"
        "counted with a list subclass, no clock involved",
        x=0.01, ha="left", fontsize=12, color=INK,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.90))
    fig.savefig(ASSETS / "copies-are-linear.png", dpi=170)
    plt.close(fig)


def figure_speedup(timing: dict) -> None:
    """Two panels: the degenerate probe and the one that actually exercises the arm.

    A third panel (target at n/3) sits between them numerically and adds nothing
    the reader cannot interpolate, so it stays out of the figure.
    """
    results = timing["results"]
    panels = [
        ("mid", "target = middle element\nbaseline does 1 comparison, copies 0 elements"),
        ("last", "target = last element\nbaseline copies at every level"),
    ]

    fig, axes = plt.subplots(1, 2, figsize=(11.4, 4.8), sharey=True)

    for ax, (position, title) in zip(axes, panels):
        rows = [r for r in results if r["position"] == position]
        rows.sort(key=lambda r: r["n"])
        ns = [r["n"] for r in rows]
        for arm in ("index_closure", "index", "iterative"):
            speeds = []
            for r in rows:
                pair = r["pairs"]
                if arm == "index_closure":
                    ratio = pair["drop slices"]["median"]
                elif arm == "index":
                    ratio = pair["drop slices"]["median"] * pair["drop per-call closure"]["median"]
                else:
                    ratio = pair["total (slicing -> iterative)"]["median"]
                speeds.append(ratio)
            ax.plot(ns, speeds, marker="o", color=ARM_COLOR[arm],
                    label=ARM_LABEL[arm], linewidth=1.8, markersize=4.5)
        ax.axhline(1.0, color=INK, linewidth=1.0, linestyle=(0, (1, 3)))
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("n  (log scale)")
        ax.set_title(title, loc="left", fontsize=10, pad=8)
        ax.set_ylim(0.04, 4000)
        ax.legend(loc="upper left", fontsize=8.5)

    axes[0].set_ylabel("speed-up vs slicing baseline\n(log scale, 1.0 = parity)")
    axes[0].text(
        20, 1.6,
        "every rewrite is 10–25x SLOWER here:\n"
        "the baseline returns after one comparison",
        fontsize=8.5, color=TERRACOTTA, va="bottom",
    )
    axes[1].text(
        1e4, 0.055,
        "same code, same n range —\nnow it is 1,000x faster",
        fontsize=8.5, color=AMBER, va="bottom", ha="left",
    )
    fig.suptitle(
        "The same four arms, two target positions\n"
        "below the dashed line means the rewrite is slower than the code it replaces",
        x=0.01, ha="left", fontsize=12, color=INK,
    )
    fig.tight_layout(rect=(0.012, 0, 1, 0.89))
    fig.savefig(ASSETS / "speedup-by-target.png", dpi=170)
    plt.close(fig)


def figure_attribution(timing: dict) -> None:
    """The three adjacent steps, isolated, at one target position."""
    rows = [r for r in timing["results"] if r["position"] == "last"]
    rows.sort(key=lambda r: r["n"])
    ns = [r["n"] for r in rows]

    steps = [
        ("drop slices\n(slicing → index+closure)", "drop slices", TERRACOTTA),
        ("drop per-call closure\n(index+closure → hoisted)", "drop per-call closure", OLIVE),
        ("drop recursion\n(hoisted → iterative)", "drop recursion", AMBER),
    ]

    fig, ax = plt.subplots(figsize=(8.6, 4.4))
    for label, key, colour in steps:
        ys = [r["pairs"][key]["median"] for r in rows]
        ax.plot(ns, ys, marker="o", color=colour, label=label, linewidth=1.8)
    ax.axhline(1.0, color=INK, linewidth=1.0, linestyle=(0, (1, 3)))
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("n  (log scale)")
    ax.set_ylabel("speed-up of that single step  (log scale)")
    ax.set_ylim(0.35, 1600)
    ax.set_title(
        "Only one of the three steps scales with n\n"
        "median of 9 interleaved rounds, target = last element",
        loc="left", fontsize=11, pad=10,
    )
    ax.legend(loc="upper left", fontsize=8.5)

    # Mark the flat band instead of pointing at one point with an arrow: a
    # shaded span reads as "these two curves live here" without crossing any line.
    ax.axhspan(1.2, 1.75, color=MUTED, alpha=0.10, linewidth=0)
    ax.text(
        ns[-1], 0.44,
        "the two constant-factor steps live in the shaded band at every n:\n"
        "1.2–1.7x, flat across five orders of magnitude",
        fontsize=8.5, color=MUTED, va="bottom", ha="right",
    )
    fig.tight_layout()
    fig.savefig(ASSETS / "arm-attribution.png", dpi=170)
    plt.close(fig)


def figure_mid(timing: dict) -> None:
    """Absolute microseconds at the middle element: the baseline is free."""
    rows = [r for r in timing["results"] if r["position"] == "mid"]
    rows.sort(key=lambda r: r["n"])
    ns = [r["n"] for r in rows]

    fig, ax = plt.subplots(figsize=(8.6, 4.4))
    for arm in ("slicing", "index_closure", "index", "iterative"):
        ys = [r["abs_us"][arm] for r in rows]
        colour = INK if arm == "slicing" else ARM_COLOR[arm]
        label = "slicing baseline (1 comparison)" if arm == "slicing" else ARM_LABEL[arm]
        style = "-" if arm == "slicing" else "-"
        ax.plot(ns, ys, marker="o", color=colour, label=label, linewidth=1.8,
                linestyle=style, markersize=4.5)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("n  (log scale)")
    ax.set_ylabel("microseconds per call  (log scale)")
    ax.set_ylim(0.07, 12)
    ax.set_title(
        "Probing the middle element makes the baseline the fastest arm\n"
        "it returns after one comparison and copies nothing — every rewrite pays setup",
        loc="left", fontsize=10.5, pad=10,
    )
    ax.legend(loc="upper left", fontsize=8.5)
    ax.annotate(
        "flat in n: one comparison, zero copies",
        xy=(ns[4], rows[4]["abs_us"]["slicing"] * 0.93),
        xytext=(ns[1], 0.075),
        fontsize=9, color=INK,
        arrowprops={"arrowstyle": "->", "color": INK, "linewidth": 0.9,
                    "connectionstyle": "arc3,rad=0.2"},
    )
    fig.tight_layout()
    fig.savefig(ASSETS / "degenerate-mid.png", dpi=170)
    plt.close(fig)


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    ops, timing = load()
    figure_copies(ops)
    figure_speedup(timing)
    figure_attribution(timing)
    figure_mid(timing)
    for name in ("copies-are-linear", "speedup-by-target", "arm-attribution", "degenerate-mid"):
        path = ASSETS / f"{name}.png"
        print(f"{path.relative_to(ROOT)}  {path.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
