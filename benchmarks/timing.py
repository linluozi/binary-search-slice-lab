#!/usr/bin/env python
"""Timing: four arms, interleaved within each round, median of per-round ratios.

Why this shape
--------------
* **Ratios, never absolute microseconds.** Absolute wall-clock for the same code
  drifts by up to 3x inside one process as the allocator warms up. A microsecond
  axis then draws a curve whose shape is measurement artefact. Absolute numbers
  are printed for scale only; every claim in the README is a ratio.
* **Interleaved within the round.** All four arms run back-to-back on the same
  input, and the round produces one ratio vector. The reported number is the
  median across rounds, with p10/p90 shown so a reader can see the spread.
* **Three target positions.** A binary search on a sorted list is not one
  workload. The middle element finishes in one comparison for the slicing arm and
  copies nothing - the baseline is then essentially free and every rewrite is
  pure overhead. The last element forces a slice at every level. Both are
  reported; quoting only one is how 0.05x turns into 935x.
* **Inner loop sized per position, not per n.** At `mid` every arm is sub-
  microsecond at any n, so the loop count can stay high; at `last` the baseline
  costs O(n) and the count has to fall. Using one formula for both makes the
  `mid` cell noise-dominated.
* **`--no-write` for CI.** Timings are machine-specific; the committed JSON is a
  record of one machine, not a target to assert against.

Run:
    python benchmarks/timing.py                # full, writes timing.json
    python benchmarks/timing.py --no-write     # print only
    python benchmarks/timing.py --quick        # small n, few rounds
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bsearch.core import ARM_ORDER, ARMS  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "benchmarks" / "timing.json"

# Adjacent pairs. Every speed-up in the README names one of these.
PAIRS = [
    ("slicing", "index_closure", "drop slices"),
    ("index_closure", "index", "drop per-call closure"),
    ("index", "iterative", "drop recursion"),
]


def pct(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = q * (len(ordered) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def inner_for(position: str, n: int) -> int:
    if position == "mid":
        # every arm is O(1) here; the loop can be long at any n
        return 20_000
    # 'last' and 'third': the baseline copies O(n) per call
    return max(8, min(20_000, 3_000_000 // max(n, 1)))


def measure(data: list[int], target: int, inner: int) -> dict[str, float]:
    """One round: all arms back-to-back. Returns seconds per call per arm."""
    out: dict[str, float] = {}
    for arm in ARM_ORDER:
        func = ARMS[arm]
        t0 = time.perf_counter()
        for _ in range(inner):
            func(data, target)
        out[arm] = (time.perf_counter() - t0) / inner
    return out


def run(n: int, rounds: int, inner: int, target: int) -> dict:
    data = list(range(n))
    per_round = [measure(data, target, inner) for _ in range(rounds)]

    abs_us = {arm: statistics.median(r[arm] for r in per_round) * 1e6 for arm in ARM_ORDER}

    pairs: dict[str, dict] = {}
    for slow, fast, label in PAIRS:
        ratios = [r[slow] / r[fast] for r in per_round]
        pairs[label] = {
            "slow": slow,
            "fast": fast,
            "median": round(statistics.median(ratios), 4),
            "p10": round(pct(ratios, 0.10), 4),
            "p90": round(pct(ratios, 0.90), 4),
        }

    total = [r["slicing"] / r["iterative"] for r in per_round]
    pairs["total (slicing -> iterative)"] = {
        "slow": "slicing",
        "fast": "iterative",
        "median": round(statistics.median(total), 4),
        "p10": round(pct(total, 0.10), 4),
        "p90": round(pct(total, 0.90), 4),
    }

    return {
        "n": n,
        "rounds": rounds,
        "inner": inner,
        "abs_us": {arm: round(v, 4) for arm, v in abs_us.items()},
        "pairs": pairs,
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser()
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()

    if args.quick:
        sizes = [256, 4_096, 65_536]
        rounds = 5
    else:
        sizes = [16, 64, 256, 1_024, 4_096, 16_384, 65_536, 262_144, 1_048_576]
        rounds = 9

    results: list[dict] = []
    for position in ["mid", "third", "last"]:
        for n in sizes:
            target = {"mid": n // 2, "third": n // 3, "last": n - 1}[position]
            inner = inner_for(position, n)
            row = run(n, rounds, inner, target)
            row["position"] = position
            row["target"] = target
            results.append(row)
            p = row["pairs"]
            print(f"{position:>5} n={n:>9,} | "
                  f"drop slices {p['drop slices']['median']:8.2f}x | "
                  f"drop closure {p['drop per-call closure']['median']:5.2f}x | "
                  f"drop recursion {p['drop recursion']['median']:5.2f}x | "
                  f"total {p['total (slicing -> iterative)']['median']:9.2f}x")

    if not args.no_write:
        OUT.write_text(
            json.dumps(
                {
                    "note": (
                        "Median of per-round ratios from one Windows machine. "
                        "Absolute microseconds are for scale only; ratios are the result."
                    ),
                    "python": sys.version.split()[0],
                    "results": results,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(f"\nwrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
