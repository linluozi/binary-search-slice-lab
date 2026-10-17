"""Correctness: differential against the baseline, plus the contract cases."""

from __future__ import annotations

import random
import unittest

from bsearch import (
    ARM_ORDER,
    ARMS,
    binary_search_index,
    binary_search_index_closure,
    binary_search_iterative,
    binary_search_slicing,
)

REWRITES = ["index_closure", "index", "iterative"]


class TestDifferential(unittest.TestCase):
    """Every rewrite must agree with the baseline on every input."""

    def test_random_sorted_lists(self) -> None:
        rng = random.Random(20261017)
        checked = 0
        for _ in range(4000):
            n = rng.randint(0, 80)
            data = sorted(rng.randint(-60, 60) for _ in range(n))
            target = rng.randint(-65, 65)
            expected = binary_search_slicing(data, target)
            for arm in REWRITES:
                self.assertEqual(
                    ARMS[arm](data, target),
                    expected,
                    f"{arm} disagreed on n={n} target={target} data={data}",
                )
                checked += 1
        self.assertEqual(checked, 12000)

    def test_every_position_in_every_size(self) -> None:
        """Hit the first, last, middle, off-by-one and absent positions."""
        for n in range(0, 130):
            data = list(range(n))
            probes = [-1, 0, n // 2, n - 1, n, n + 1]
            if n >= 2:
                probes += [n // 2 - 1, n // 2 + 1, 1, n - 2]
            for target in probes:
                expected = binary_search_slicing(data, target)
                for arm in REWRITES:
                    self.assertEqual(ARMS[arm](data, target), expected, f"{arm} n={n} t={target}")

    def test_all_arm_names_present(self) -> None:
        self.assertEqual(ARM_ORDER, ["slicing", "index_closure", "index", "iterative"])
        self.assertEqual(set(ARMS), set(ARM_ORDER))


class TestContract(unittest.TestCase):
    """The upstream file accepts any sequence; the rewrites must not narrow that."""

    def test_sequences_that_are_not_lists(self) -> None:
        for data, target, expected in [
            (tuple(range(10)), 5, True),
            (range(0, 10000, 5), 2, False),
            ("abcdefghij", "e", True),
            (b"abcdefghij", ord("e"), True),
            ([], 1, False),
            ((7,), 7, True),
        ]:
            for arm in ARM_ORDER:
                self.assertEqual(ARMS[arm](data, target), expected, f"{arm} on {type(data)}")

    def test_duplicates(self) -> None:
        for data, target in [([4, 4, 5, 6, 7], 4), ([2, 2, 2, 2], 2), ([2, 2, 2, 2], 3)]:
            expected = binary_search_slicing(data, target)
            for arm in REWRITES:
                self.assertEqual(ARMS[arm](data, target), expected, f"{arm} {data} {target}")

    def test_nan_parity(self) -> None:
        """A sorted list containing NaN is not really sorted; both must agree anyway."""
        nan = float("nan")
        data = [1.0, 2.0, nan, 4.0, 5.0]
        for target in (1.0, 4.0, nan, 3.0):
            expected = binary_search_slicing(data, target)
            for arm in REWRITES:
                self.assertEqual(ARMS[arm](data, target), expected, f"{arm} target={target}")

    def test_only_lt_and_eq_required(self) -> None:
        """Nothing here may depend on __le__, __gt__ or __ge__."""

        class LtEqOnly:
            def __init__(self, value: int) -> None:
                self.value = value

            def __lt__(self, other: "LtEqOnly") -> bool:
                return self.value < other.value

            def __eq__(self, other: object) -> bool:
                return isinstance(other, LtEqOnly) and self.value == other.value

            def __hash__(self) -> int:
                return hash(self.value)

        data = [LtEqOnly(i) for i in range(16)]
        for arm in ARM_ORDER:
            self.assertTrue(ARMS[arm](data, data[9]), f"{arm} missed a present element")
            self.assertFalse(ARMS[arm](data, LtEqOnly(99)), f"{arm} invented an absent element")

    def test_empty_check_does_not_call_bool(self) -> None:
        """`if not a_list` would call __bool__ and break ndarray-style containers."""

        class AmbiguousTruth:
            def __init__(self, data: list[int]) -> None:
                self._data = data

            def __len__(self) -> int:
                return len(self._data)

            def __bool__(self) -> bool:
                raise ValueError("truth value is ambiguous")

            def __getitem__(self, key):
                if isinstance(key, slice):
                    return AmbiguousTruth(self._data[key])
                return self._data[key]

        container = AmbiguousTruth(list(range(10)))
        for arm in ARM_ORDER:
            self.assertTrue(ARMS[arm](container, 5), f"{arm} called __bool__")
            self.assertFalse(ARMS[arm](container, 99), f"{arm} called __bool__")


class TestUpstreamDoctests(unittest.TestCase):
    """The upstream file's 14 doctest cases, run against every rewrite."""

    CASES = [
        (([0, 1, 2, 8, 13, 17, 19, 32, 42], 3), False),
        (([0, 1, 2, 8, 13, 17, 19, 32, 42], 13), True),
        (([4, 4, 5, 6, 7], 4), True),
        (([4, 4, 5, 6, 7], -10), False),
        (([-18, 2], -18), True),
        (([5], 5), True),
        ((["a", "c", "d"], "c"), True),
        ((["a", "c", "d"], "f"), False),
        (([], 1), False),
        (([-0.1, 0.1, 0.8], 0.1), True),
        ((range(-5000, 5000, 10), 80), True),
        ((range(-5000, 5000, 10), 1255), False),
        ((range(0, 10000, 5), 2), False),
    ]

    def test_all_arms_pass_upstream_cases(self) -> None:
        for (data, target), expected in self.CASES:
            for arm in ARM_ORDER:
                self.assertEqual(ARMS[arm](data, target), expected, f"{arm} {(data, target)}")


class TestSlicingArmIsUpstream(unittest.TestCase):
    """Guard against someone 'tidying' the baseline into something faster."""

    def test_body_matches_upstream_shape(self) -> None:
        import inspect

        source = inspect.getsource(binary_search_slicing)
        self.assertIn("if len(a_list) == 0:", source)
        self.assertIn("midpoint = len(a_list) // 2", source)
        self.assertIn("a_list[:midpoint]", source)
        self.assertIn("a_list[midpoint + 1 :]", source)


if __name__ == "__main__":
    unittest.main()
