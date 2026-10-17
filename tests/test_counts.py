"""Exact counts, and the tests that would have caught the bugs this repo is about.

Two kinds of test live here:

1. **Count assertions** - the copy volume is linear, not ``n log n``. Deterministic,
   no clock.
2. **Mutation tests** - inject a defect into a copy of an arm and assert the suite
   catches it. A test suite that cannot catch a known bug is decoration; this file
   names the three defects the reviewed optimisation package's own doctests let
   through, and proves the cases below catch them.
"""

from __future__ import annotations

import unittest

from bsearch import ARMS, CompareCounter, CopyCounter, binary_search_iterative, binary_search_slicing


class TestCopyVolumeIsLinear(unittest.TestCase):
    def test_copies_per_n_is_one_for_non_mid_targets(self) -> None:
        """n/2 + n/4 + ... = n. Flat ratio across a 256x range of n.

        The ratio is slightly under 1.0 (by roughly ``2*log2(n)/n``) because the
        last few levels copy a handful of elements each, so the tail of the
        geometric series is truncated. That deficit shrinks with n - which is
        itself evidence for a geometric sum, not for ``n log n``.
        """
        deficits = []
        for n in (1024, 4096, 16384, 65536, 262144):
            for position, target in [("first", 0), ("last", n - 1), ("absent", n + 100)]:
                CopyCounter.reset()
                binary_search_slicing(CopyCounter(range(n)), target)
                ratio = CopyCounter.copies / n
                self.assertGreater(ratio, 0.98, f"n={n} {position}: copies/n = {ratio:.4f}")
                self.assertLess(ratio, 1.01, f"n={n} {position}: copies/n = {ratio:.4f}")
                if position == "last":
                    deficits.append(1.0 - ratio)

        # The deficit shrinks as n grows: 2*log2(n)/n.
        for earlier, later in zip(deficits, deficits[1:]):
            self.assertGreater(earlier, later, "deficit should shrink with n")

    def test_mid_target_copies_nothing(self) -> None:
        """The degenerate case: one comparison, zero slices. Any benchmark that
        only probes the middle element measures nothing at all."""
        for n in (1024, 65536, 262144):
            CopyCounter.reset()
            binary_search_slicing(CopyCounter(range(n)), n // 2)
            self.assertEqual(CopyCounter.copies, 0)
            self.assertEqual(CopyCounter.slices, 0)

    def test_copy_volume_grows_linearly_not_n_log_n(self) -> None:
        """Doubling n must roughly double the copies, not double them times log."""
        previous = None
        for n in (4096, 8192, 16384, 32768, 65536):
            CopyCounter.reset()
            binary_search_slicing(CopyCounter(range(n)), 0)
            copies = CopyCounter.copies
            if previous is not None:
                growth = copies / previous
                # linear -> 2.0; n log n -> ~2.2 and rising
                self.assertLess(growth, 2.05, f"n={n}: copies grew {growth:.3f}x for 2x input")
            previous = copies


class TestReadCounts(unittest.TestCase):
    def test_rewrites_read_logarithmically_many_elements(self) -> None:
        for arm in ("index_closure", "index", "iterative"):
            for n in (1024, 65536, 262144):
                counter = CompareCounter(range(n))
                ARMS[arm](counter, n - 1)
                self.assertLessEqual(
                    counter.reads, n.bit_length() + 1,
                    f"{arm} n={n}: {counter.reads} reads, expected <= {n.bit_length() + 1}",
                )

    def test_slicing_arm_reads_linear_number_of_elements(self) -> None:
        """A slice copies every element, so the baseline's read count is O(n)."""
        n = 65536
        counter = CompareCounter(range(n))
        binary_search_slicing(counter, n - 1)
        self.assertGreater(counter.reads, n // 2, f"expected >{n // 2} reads, got {counter.reads}")


class TestMutationCoverage(unittest.TestCase):
    """Defects the reviewed package's doctests missed. Each must be caught here.

    The three defects below are real: injected into the package's iterative arm,
    they survived all 19 of its doctests. On 20,000 random inputs they returned
    the wrong answer 21.5%, 6.3% and 0% of the time respectively - the last one
    is correct but degrades to a linear scan, 2,212x slower at n=64,000.
    """

    def _run_cases(self, func) -> list[bool]:
        cases = []
        for n in (1, 2, 3, 5, 8, 16, 64, 128, 1000):
            data = list(range(n))
            for target in (0, n // 2, n - 1, n - 2, n, -1):
                cases.append(func(data, target))
        return cases

    def test_defect_drops_right_half(self) -> None:
        def broken(a_list, item):
            lo, hi = 0, len(a_list) - 1
            while lo <= hi:
                mid = lo + (hi - lo) // 2
                if a_list[mid] == item:
                    return True
                if item < a_list[mid]:
                    hi = mid - 1
                else:
                    break  # defect
            return False

        self.assertNotEqual(
            self._run_cases(broken), self._run_cases(binary_search_iterative),
            "the drop-right-half defect was not caught",
        )

    def test_defect_skips_an_element(self) -> None:
        def broken(a_list, item):
            lo, hi = 0, len(a_list) - 1
            while lo <= hi:
                mid = lo + (hi - lo) // 2
                if a_list[mid] == item:
                    return True
                if item < a_list[mid]:
                    hi = mid - 2  # defect
                else:
                    lo = mid + 1
            return False

        self.assertNotEqual(
            self._run_cases(broken), self._run_cases(binary_search_iterative),
            "the skip-an-element defect was not caught",
        )

    def test_defect_degrades_to_linear_scan(self) -> None:
        """Returns the right answer, so no behavioural test can see it.

        Only a read counter can. That is why ``CompareCounter`` exists.
        """

        def broken(a_list, item):
            lo, hi = 0, len(a_list) - 1
            while lo <= hi:
                mid = lo  # defect: no bisection
                if a_list[mid] == item:
                    return True
                if item < a_list[mid]:
                    hi = mid - 1
                else:
                    lo = mid + 1
            return False

        n = 4096
        good = CompareCounter(range(n))
        binary_search_iterative(good, n - 1)
        bad = CompareCounter(range(n))
        broken(bad, n - 1)

        self.assertGreater(
            bad.reads, good.reads * 100,
            f"linear-scan defect read {bad.reads} vs {good.reads}; counter did not notice",
        )


if __name__ == "__main__":
    unittest.main()
