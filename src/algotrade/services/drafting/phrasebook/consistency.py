"""Whether the criteria of one field can all hold at once: ``compatible`` is false when two of
them on the same field leave no value (``rsi_14 lt 30`` with ``rsi_14 gt 70``; a category ``in
[ETF]`` with ``in [COMMON_STOCK, ADR]``; ``eq`` with a ``ne`` of the same value; ``is_null``
with ``not_null`` or any comparison). A number is an interval (open or closed ends), a category
or text a set of allowed values less the excluded ones. Every mode counts: a soft or score
criterion that contradicts a hard one is still two readings of the sentence, not one."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any


def _number(v: object) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool)


@dataclass
class _Shape:
    """What the criteria seen so far on one field allow."""

    low: float = float("-inf")
    low_open: bool = False
    high: float = float("inf")
    high_open: bool = False
    allowed: set[Any] | None = None  # eq / in values: None until one is seen
    excluded: set[Any] = field(default_factory=set)
    null: bool | None = None  # True: is_null, False: not_null

    def raise_low(self, v: float, open_: bool) -> None:
        if v > self.low or (v == self.low and open_):
            self.low, self.low_open = v, open_

    def lower_high(self, v: float, open_: bool) -> None:
        if v < self.high or (v == self.high and open_):
            self.high, self.high_open = v, open_

    def allow(self, values: Sequence[Any]) -> None:
        self.allowed = set(values) if self.allowed is None else self.allowed & set(values)

    def empty(self) -> bool:
        if self.low > self.high or (self.low == self.high and (self.low_open or self.high_open)):
            return True
        if self.allowed is None:
            return self.low == self.high and self.low in self.excluded
        return not any(v not in self.excluded and self._within(v) for v in self.allowed)

    def _within(self, v: Any) -> bool:
        if not _number(v):
            return self.low == float("-inf") and self.high == float("inf")  # no bound on text
        above = v > self.low or (v == self.low and not self.low_open)
        below = v < self.high or (v == self.high and not self.high_open)
        return above and below


def _apply(shape: _Shape, op: str, value: Any) -> None:
    members = list(value) if isinstance(value, list | tuple) else [value]
    if op in ("is_null", "not_null"):
        want = op == "is_null"
        shape.null = want if shape.null is None else (want if shape.null == want else None)
        if shape.null is None:  # both were asked
            shape.allowed = set()
    elif op in ("eq", "in"):
        shape.allow(members)
    elif op in ("ne", "not_in"):
        shape.excluded |= set(members)
    elif op in ("gt", "gte") and _number(value):
        shape.raise_low(value, op == "gt")
    elif op in ("lt", "lte") and _number(value):
        shape.lower_high(value, op == "lt")
    elif op == "between" and len(members) == 2:
        shape.raise_low(members[0], False)
        shape.lower_high(members[1], False)


def compatible(criteria: Sequence[Mapping[str, Any]]) -> bool:
    """False when two criteria (answer shape) on one field can never both hold."""
    shapes: dict[str, _Shape] = {}
    for c in criteria:
        shape = shapes.setdefault(c["field"], _Shape())
        _apply(shape, c["op"], c.get("value"))
        if shape.null is True and (
            shape.allowed is not None or shape.low > float("-inf") or shape.high < float("inf")
        ):
            return False  # null has no value to compare
        if shape.empty():
            return False
    return True
