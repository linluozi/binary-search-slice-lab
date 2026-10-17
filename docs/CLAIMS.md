# Claim audit

Every number in `README.md` traces to a file in `benchmarks/`. This document
records what was claimed by the reviewed write-up, what was measured, and where
the two differ.

Source reviewed: a 5-file optimisation package for
`TheAlgorithms/Python`'s `searches/simple_binary_search.py`.

Baseline integrity: the package's `original_simple_binary_search.py` hashes to
`43afd52e975b602f1e29ccbe3bdd5b981f7e975c`, identical to the file on
`raw.githubusercontent.com` at review time. Its `LICENSE.md` is byte-identical to
upstream's. Neither is reproduced here — `bsearch/core.py` carries the baseline
under its own name and `tests/test_correctness.py` asserts the shape is unchanged.

---

## Claim 1 — "the total work becomes Θ(n log n)"

**Verdict: wrong. It is Θ(n).**

The write-up's argument is "recursion depth is Θ(log n) and the average slice
length is Θ(n), so total work is Θ(n) per level → Θ(n log n) overall". The second
premise is false. Slicing keeps half the list, so the slice lengths are
`n/2, n/4, n/8, …` — a geometric series summing to `n`, not `n` per level.

Measured with `CopyCounter` (a `list` subclass that tallies every copied element
and re-wraps slices so nested levels are counted):

| n | copies | copies / n | levels | ⌊log₂n⌋ |
|---|---|---|---|---|
| 1,024 | 1,014 | 0.99 | 9 | 10 |
| 4,096 | 4,084 | 1.00 | 11 | 12 |
| 16,384 | 16,370 | 1.00 | 13 | 14 |
| 65,536 | 65,520 | 1.00 | 15 | 16 |
| 262,144 | 262,126 | 1.00 | 17 | 18 |

`copies / n` is flat across a 256× range. Under Θ(n log n) it would have climbed
from 0.99 to 1.80 as `log₂n` went 10 → 18.

**Why the error is easy to make:** a counter that returns a plain `list` from
`__getitem__` only sees the first slice, and reports `0.5n` — which looks
consistent with "Θ(n) per level" if you do not check the level count. The
counter in this repo re-wraps.

**Does it matter?** The conclusion ("this should be rewritten") survives — Θ(n)
→ Θ(log n) is still the right fix. But the write-up's only theoretical argument
is the wrong one, and the correct argument is stronger: **every element you add
to the list doubles the copying work per lookup.**

---

## Claim 2 — "can hit the recursion limit earlier than necessary"

**Verdict: false. Both arms have identical depth.**

Measured with `sys.setprofile`, counting frames on every call:

| n | slicing | index-based | ⌊log₂n⌋+1 |
|---|---|---|---|
| 1,024 | 12 | 12 | 11 |
| 16,384 | 16 | 16 | 15 |
| 262,144 | 20 | 20 | 19 |
| 1,048,576 | 22 | 22 | 21 |

Depth is determined by how many times the list is halved. Both arms halve
identically. Copying more elements per level allocates memory; it does not add
stack frames. Both arms complete `n = 5,000,000` without approaching the default
limit.

This claim should have been dropped, not argued.

---

## Claim 3 — the speed-up table

**Verdict: the numbers are misaligned by roughly one row of magnitude.**

The write-up's table, against measurement at the same `n` (target = `n//3`,
interleaved rounds):

| n | claimed speed-up | claimed baseline cost | measured baseline cost | measured speed-up |
|---|---|---|---|---|
| 100 | 5–20× | "~ few µs" | 0.20 µs | 1.8× |
| 1,000 | 30–100× | "tens of µs" | 0.56 µs | 2.8× |
| 5,000 | 100–300× | "hundreds of µs" | 1.9 µs | 7.4× |
| 10,000+ | 200–1000× | "milliseconds" | 3.5–14 µs | 12.6× |

The claimed baseline cost at `n = 10,000` is "milliseconds"; measured, it is
3.5 µs — off by 100–300×. And the write-up's own `benchmark.py`, run at
`n = 20,000`, prints **20.8×**, which contradicts its own README's "200–1000× at
n = 10,000+".

The measured values at genuinely large `n` are larger than the write-up dared
claim (476–532× at `n = 200,000`, 2,608× at `n = 1,048,576`), so this is not
bravado — it is a table whose rows were copied one level off.

---

## Claim 4 (implicit) — "faster at every size"

**Verdict: false below n ≈ 256, and false for any target near the middle.**

The write-up's `binary_search` builds a fresh `_search` closure on every call.
Measured against an otherwise identical arm with the helper at module level, that
closure costs a flat 1.2–2.2×, because allocating a function object is ~0.3 µs
regardless of `n`.

Consequence: at `n = 16` with `target = last`, the "optimised" recursive arm is
**0.52×** — half the speed of the code it replaces. Its break-even point is
`n ≈ 256`.

And at `target = mid`, the baseline finishes after one comparison and zero
copies, so *every* rewrite loses by 4–25×. The write-up's benchmark probes
`data[n//3]`, which avoids the worst case by luck rather than design; a benchmark
probing `data[n//2]` would have reported the opposite conclusion.

---

## Claim 5 — test coverage

**Verdict: the 19 doctests are not sufficient; three real defects pass them.**

Nine defects injected into the reviewed file, all 19 doctests run after each:

| defect | caught? | effect |
|---|---|---|
| iterative `else: break` | **no** | 21.5% wrong answers (20k random inputs) |
| iterative `hi = mid - 2` | **no** | 6.3% wrong answers |
| iterative `mid = lo` | **no** | 0% wrong, but 2,212× slower at n=64,000 |
| iterative `return True` at end | yes | — |
| iterative drops `hi` update | yes | infinite loop |
| recursive `_search(mid, hi)` | yes | — |
| recursive `lo >= hi` | yes | — |
| recursive `_search(lo, mid)` | yes | — |
| recursive always `True` | yes | — |

Root cause: the iterative arm shipped with 3 doctests, the recursive arm with all
14 inherited from upstream. Porting the 14 upstream cases onto the iterative arm
catches the first defect and still misses the other two — upstream's suite has no
case where the right boundary lands exactly on `mid-2`, and no case that forces a
full `log n` descent.

The third defect is the interesting one: it returns correct answers for every
input, so no behavioural test can find it. Only a read counter can.

`tests/test_counts.py::TestMutationCoverage` re-runs all three against this
repo's counters and asserts each is caught.

---

## Claim 6 — the empty check

**Verdict: a real behaviour regression, not a style nit.**

Upstream tests emptiness with `len(a_list) == 0`. The rewrite uses
`if not a_list`, which invokes `bool()`:

| input | upstream | rewrite |
|---|---|---|
| `np.arange(100)`, 50 | `True` | `ValueError` |
| `np.arange(100)`, -1 | `False` | `ValueError` |
| `np.array([])`, 1 | `False` | `ValueError` |

Upstream's own doctests pass a `range`, so the documented contract is "any
sequence". `ndarray` is a sequence. The rewrite drops every ndarray caller
silently — the failure surfaces at the call site, in the user's code, not in the
package's tests.

Fixed here by using `len()` throughout. `tests/test_correctness.py::
test_empty_check_does_not_call_bool` asserts no arm touches `__bool__`.

---

## Method notes

- **Ratios only, interleaved within the round.** All four arms run back-to-back on
  the same input; the round produces one ratio vector; the reported number is the
  median across 9 rounds, with p10–p90 shown. Absolute wall-clock for identical
  code drifts by up to 3× inside one process.
- **Two target positions, always.** See claim 4.
- **Counts are asserted in CI, timings are not.** `ops.py --check` recomputes
  every cell; a mismatch is a real change. Timings are machine-specific, so the
  CI job runs them with `--no-write`.
- **Inner-loop count varies by position, not just by `n`.** At `mid` every arm is
  sub-microsecond at any `n`, so the loop can stay long; at `last` the baseline is
  O(n) per call. Using one formula for both makes the `mid` cells noise-dominated.
