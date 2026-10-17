"""Four binary-search arms, and an operation counter.

Design rules enforced here
--------------------------
1. **Arms differ by exactly one idea.** ``slicing`` -> ``index_closure``
   isolates "stop copying the list". ``index_closure`` -> ``index`` isolates
   "stop rebuilding the closure on every call". ``index`` -> ``iterative``
   isolates "stop recursing". Anything reported as a speed-up must name the two
   adjacent arms that isolate it.

2. **Empty-check is ``len(x) == 0`` everywhere.** ``if not x`` calls
   ``bool(x)``, and ``numpy.ndarray.__bool__`` raises on more than one element.
   The upstream file this repo measures uses ``len()``; a rewrite that switches
   to truthiness silently drops every ndarray caller.

3. **The baseline is verbatim upstream.** ``binary_search_slicing`` below is
   byte-identical to ``TheAlgorithms/Python``'s ``searches/simple_binary_search.py``
   apart from the function name. Do not "tidy" it: a baseline that has been
   quietly improved is not a baseline.

4. **No ``random`` inside timed regions.** Benchmarks build input outside the
   clock; see ``benchmarks/timing.py``.
"""

from __future__ import annotations

from typing import Any, Protocol, Sequence, TypeVar


class Comparable(Protocol):
    """Anything with ``__lt__`` and ``__eq__``. This is the whole contract."""

    def __lt__(self, other: Any, /) -> bool: ...


T = TypeVar("T", bound=Comparable)


# ---------------------------------------------------------------------------
# Arm A - baseline: recursive, copies a slice at every level.
# Verbatim from TheAlgorithms/Python (MIT), only the name changed.
# ---------------------------------------------------------------------------


def binary_search_slicing(a_list: Sequence[T], item: T) -> bool:
    """Baseline arm: recursive, slices the list at every level.

    ``a_list[:midpoint]`` allocates and copies. Slicing keeps only half, so the
    copy volume per call is ``n/2 + n/4 + n/8 + ... = n`` - linear, not
    ``n log n``. ``benchmarks/ops.py`` counts this exactly.

    >>> binary_search_slicing([0, 1, 2, 8, 13, 17, 19, 32, 42], 13)
    True
    >>> binary_search_slicing([0, 1, 2, 8, 13, 17, 19, 32, 42], 3)
    False
    >>> binary_search_slicing([], 1)
    False
    """
    if len(a_list) == 0:
        return False
    midpoint = len(a_list) // 2
    if a_list[midpoint] == item:
        return True
    if item < a_list[midpoint]:
        return binary_search_slicing(a_list[:midpoint], item)
    else:
        return binary_search_slicing(a_list[midpoint + 1 :], item)


# ---------------------------------------------------------------------------
# Arm B - index-based, but a fresh closure per call.
# This is what the reviewed optimisation package shipped.
# ---------------------------------------------------------------------------


def binary_search_index_closure(a_list: Sequence[T], item: T) -> bool:
    """Arm B: index bounds instead of slices, but rebuilds ``_search`` per call.

    Creating a function object is a *fixed* cost per call - measured at roughly
    0.3 us on CPython 3.13, independent of ``n``. That is enough to make this
    arm slower than the slicing baseline below n ~ 256.

    >>> binary_search_index_closure([0, 1, 2, 8, 13, 17, 19, 32, 42], 13)
    True
    >>> binary_search_index_closure([], 1)
    False
    """

    def _search(lo: int, hi: int) -> bool:
        if lo > hi:
            return False
        mid = lo + (hi - lo) // 2
        mid_val = a_list[mid]
        if mid_val == item:
            return True
        if item < mid_val:
            return _search(lo, mid - 1)
        return _search(mid + 1, hi)

    if len(a_list) == 0:
        return False
    return _search(0, len(a_list) - 1)


# ---------------------------------------------------------------------------
# Arm B' - same algorithm, helper hoisted to module level.
# ---------------------------------------------------------------------------


def _search_hoisted(a_list: Sequence[T], item: T, lo: int, hi: int) -> bool:
    if lo > hi:
        return False
    mid = lo + (hi - lo) // 2
    mid_val = a_list[mid]
    if mid_val == item:
        return True
    if item < mid_val:
        return _search_hoisted(a_list, item, lo, mid - 1)
    return _search_hoisted(a_list, item, mid + 1, hi)


def binary_search_index(a_list: Sequence[T], item: T) -> bool:
    """Arm B': index bounds, helper at module level, no per-call closure.

    Removing the closure is worth 1.39-1.69x on top of removing the slices, at
    every ``n`` tested. The empty check is unnecessary here: ``lo=0 > hi=-1``
    already returns ``False``, so no ``len()`` call and no ``bool()`` call.

    >>> binary_search_index([0, 1, 2, 8, 13, 17, 19, 32, 42], 13)
    True
    >>> binary_search_index([], 1)
    False
    """
    return _search_hoisted(a_list, item, 0, len(a_list) - 1)


# ---------------------------------------------------------------------------
# Arm C - iterative.
# ---------------------------------------------------------------------------


def binary_search_iterative(a_list: Sequence[T], item: T) -> bool:
    """Arm C: iterative. No recursion, no closure, O(1) extra space.

    Removing recursion on top of removing the closure is worth only 1.23-1.35x,
    and that ratio is flat across five orders of magnitude of ``n`` - it buys a
    constant, not a complexity class.

    >>> binary_search_iterative([0, 1, 2, 8, 13, 17, 19, 32, 42], 13)
    True
    >>> binary_search_iterative([0, 1, 2, 8, 13, 17, 19, 32, 42], 3)
    False
    >>> binary_search_iterative([], 1)
    False
    """
    lo, hi = 0, len(a_list) - 1
    while lo <= hi:
        mid = lo + (hi - lo) // 2
        mid_val = a_list[mid]
        if mid_val == item:
            return True
        if item < mid_val:
            hi = mid - 1
        else:
            lo = mid + 1
    return False


# ---------------------------------------------------------------------------
# Counting helpers - deterministic, used by benchmarks/ops.py
# ---------------------------------------------------------------------------


class CopyCounter(list):
    """A list that tallies how many elements get copied out of it.

    Slices are re-wrapped so nested levels are counted too. A naive counter that
    returns a plain ``list`` only sees the first slice and reports ``0.5n``
    instead of ``n`` - which is exactly the mistake that makes the ``n log n``
    claim look plausible.
    """

    copies: int = 0
    slices: int = 0

    def __getitem__(self, key: Any) -> Any:
        result = list.__getitem__(self, key)
        if isinstance(key, slice):
            CopyCounter.copies += len(result)
            CopyCounter.slices += 1
            return CopyCounter(result)
        return result

    @classmethod
    def reset(cls) -> None:
        cls.copies = 0
        cls.slices = 0


class CompareCounter:
    """Wrap a sorted list; count ``__getitem__`` and comparisons on elements."""

    def __init__(self, data: Sequence[int]) -> None:
        self._data = list(data)
        self.reads = 0

    def __len__(self) -> int:
        return len(self._data)

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, slice):
            self.reads += len(self._data[key])
            return CompareCounter(self._data[key])
        self.reads += 1
        return self._data[key]


ARMS = {
    "slicing": binary_search_slicing,
    "index_closure": binary_search_index_closure,
    "index": binary_search_index,
    "iterative": binary_search_iterative,
}

ARM_ORDER = ["slicing", "index_closure", "index", "iterative"]
