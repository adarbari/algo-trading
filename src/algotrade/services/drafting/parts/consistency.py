"""A reading is kept only when its numbers are the part's own (ADR 0041, amended 2026-10-11): the
reading is the model's words about the trader's words, so every number it states must be a value
the part's criteria hold (a threshold, a range end, a tolerance, a formula's number), read with a
percent sign as a fraction (``10%`` is ``0.1``) and with a ``k`` / ``M`` / ``B`` suffix as its
multiple (``thousand`` / ``million`` / ``billion`` too), compared without its sign (a drop of 10%
states 0.1 against ``lt -0.1``), or a number in the name of a field the part uses (``20`` in
``ret_20d``). A part with nothing to check against (no criterion, formula or reading to choose)
may repeat the numbers of its own words. A reading that states another number is dropped (the
web shows the rows alone): it would contradict them."""

import math
import re
from collections.abc import Iterable, Mapping
from typing import Any

_NUMBER = re.compile(
    r"(?<![\w.])\$?(\d[\d,]*(?:\.\d+)?)\s*(%|[kKmMbB]n?(?!\w)|thousand|million|billion)?",
    re.IGNORECASE,
)
_SCALE = {"k": 1e3, "t": 1e3, "m": 1e6, "b": 1e9}
_IN_NAME = re.compile(r"\d+(?:\.\d+)?")


def _readings(text: str) -> list[list[float]]:
    out: list[list[float]] = []
    for m in _NUMBER.finditer(text):
        value = float(m.group(1).replace(",", ""))
        unit = (m.group(2) or "").lower()
        if unit == "%":
            out.append([value, value / 100])
        elif unit:
            out.append([value, value * _SCALE[unit[0]]])
        else:
            out.append([value])
    return out


def stated(text: str) -> list[float]:
    """Every number ``text`` states, with the other values it could mean (``50%``: 50 and 0.5)."""
    return [n for group in _readings(text) for n in group]


def values_of(value: Any) -> list[float]:
    """The numbers in a criterion's ``value`` / ``tolerance`` (a scalar, a list or
    ``{relative: x}``; booleans and text are not numbers)."""
    if isinstance(value, bool):
        return []
    if isinstance(value, int | float):
        return [float(value)]
    if isinstance(value, list):
        return [n for v in value for n in values_of(v)]
    if isinstance(value, Mapping):
        return [n for v in value.values() for n in values_of(v)]
    return []


def names_numbers(names: Iterable[str]) -> list[float]:
    """The numbers in field names (``ret_20d``, ``pct_from_low_52w``)."""
    return [float(n) for name in names for n in _IN_NAME.findall(name)]


def reading_consistent(reading: str, allowed: Iterable[float]) -> bool:
    """Whether every number in ``reading`` is one of ``allowed``."""
    pool = list(allowed)
    return all(
        any(math.isclose(n, abs(a), rel_tol=1e-6, abs_tol=1e-9) for n in group for a in pool)
        for group in _readings(reading)
    )
