#!/usr/bin/env python
"""Exact operation counts - no clock involved.

This is the deterministic half of the repo. ``--check`` recomputes every cell
and compares against the committed ``ops.json``; the counts depend only on
``n`` and the target's position, so a mismatch across machines means behaviour
changed, not that the machine is noisy.

What gets counted
-----------------
``copies``  elements copied by list slicing (arm ``slicing`` only)
``slices``  number of slice operations (arm ``slicing`` only)
``reads``   element reads through ``__getitem__`` (all arms)

Run:
    python benchmarks/ops.py            # print the table
    python benchmarks/ops.py --write    # rewrite ops.json
    python benchmarks/ops.py --check    # compare against ops.json, exit 1 on drift
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bsearch.core import ARM_ORDER, ARMS, CompareCounter, CopyCounter  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "benchmarks" / "ops.json"

SIZES = [1024, 4096, 16384, 65536, 262144]
POSITIONS = ["first", "quarter", "mid", "three_quarter", "last", "absent"]


def target_for(n: int, position: str) -> int:
    return {
        "first": 0,
        "quarter": n // 4,
        "mid": n // 2,
        "three_quarter": 3 * n // 4,
        "last": n - 1,
        "absent": n + 100,
    }[position]


def count_copy(n: int, position: str) -> tuple[int, int]:
    CopyCounter.reset()
    data = CopyCounter(range(n))
    ARMS["slicing"](data, target_for(n, position))
    return CopyCounter.copies, CopyCounter.slices


def count_reads(arm: str, n: int, position: str) -> int:
    data = CompareCounter(range(n))
    ARMS[arm](data, target_for(n, position))
    return data.reads


def build() -> dict:
    table: dict[str, dict] = {}
    for n in SIZES:
        row: dict[str, dict] = {}
        for position in POSITIONS:
            entry: dict[str, object] = {}
            copies, slices = count_copy(n, position)
            entry["copies"] = copies
            entry["slices"] = slices
            entry["copies_per_n"] = round(copies / n, 4)
            for arm in ARM_ORDER:
                entry[f"reads_{arm}"] = count_reads(arm, n, position)
            row[position] = entry
        table[str(n)] = row
    return {
        "note": (
            "Element copies and reads. Deterministic: depends only on n and the "
            "target position. copies_per_n staying flat at ~1.0 is the refutation "
            "of the n-log-n claim."
        ),
        "sizes": SIZES,
        "positions": POSITIONS,
        "table": table,
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    fresh = build()

    if args.write:
        OUT.write_text(json.dumps(fresh, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {OUT.relative_to(ROOT)}")
        return 0

    if args.check:
        if not OUT.exists():
            print(f"missing {OUT.relative_to(ROOT)}")
            return 1
        committed = json.loads(OUT.read_text(encoding="utf-8"))
        bad = 0
        for n, row in fresh["table"].items():
            for position, entry in row.items():
                old = committed["table"].get(n, {}).get(position, {})
                for key, value in entry.items():
                    if old.get(key) != value:
                        print(f"DRIFT n={n} {position} {key}: {old.get(key)} -> {value}")
                        bad += 1
        total = sum(len(row) for row in fresh["table"].values())
        if bad:
            print(f"FAIL: {bad} drifted cells")
            return 1
        print(f"OK: {total} cells match")
        return 0

    print(f"{'n':>8} | {'pos':>13} | {'copies':>9} | {'copies/n':>8} | "
          f"{'reads A':>7} | {'reads B':>7} | {'reads Bp':>8} | {'reads C':>7}")
    print("-" * 92)
    for n, row in fresh["table"].items():
        for position, entry in row.items():
            print(f"{int(n):>8,} | {position:>13} | {entry['copies']:>9,} | "
                  f"{entry['copies_per_n']:>8.2f} | {entry['reads_slicing']:>7} | "
                  f"{entry['reads_index_closure']:>7} | {entry['reads_index']:>8} | "
                  f"{entry['reads_iterative']:>7}")
    print()
    print("copies_per_n is flat at 1.00 across a 256x range of n:")
    print("  n/2 + n/4 + n/8 + ... = n, so the copy volume is linear, not n*log n.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
