"""Four binary-search arms, and what each one actually costs."""

from __future__ import annotations

from .core import (
    ARM_ORDER,
    ARMS,
    CompareCounter,
    CopyCounter,
    binary_search_index,
    binary_search_index_closure,
    binary_search_iterative,
    binary_search_slicing,
)

__all__ = [
    "ARM_ORDER",
    "ARMS",
    "CompareCounter",
    "CopyCounter",
    "binary_search_index",
    "binary_search_index_closure",
    "binary_search_iterative",
    "binary_search_slicing",
]
__version__ = "1.0.0"
