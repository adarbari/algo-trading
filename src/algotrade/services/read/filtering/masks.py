"""``evaluate_filters``: the truth of each active filter on each row of a frame (ADR 0082
decision 2). The operator comes from the definition's kind (a pick is ``in``, a select ``eq``,
a toggle ``eq`` true / false, a range ``gte`` / ``lte`` / ``between``, a window ``between``
0 and the amount); every test runs through ``core.model.predicates.evaluate_rule``, so a value
that is missing is UNKNOWN and an UNKNOWN row never passes (a ``min`` of 0 admits no null).
A cell may hold a tuple (a row picked by several screeners): the row passes a pick when any of
them does. A switched-off filter (``active`` false) and one with nothing set are in no mask.
Pure and deterministic: no clock, no randomness."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from algotrade.config.filters.definitions import FilterDefinition
from algotrade.core.model.predicates import FieldValue, Rule, Truth, evaluate_rule, is_missing
from algotrade.services.read.filtering.definitions import FilterRefusedError, ResolvedFilters

type Cell = FieldValue | tuple[FieldValue, ...]
type Frame = Mapping[str, Sequence[Cell]]  # the rows as columns, by definition ``field``
YES, NO = "yes", "no"  # a toggle's values


@dataclass(frozen=True)
class FilterInput:
    """One filter as the viewer set it (the GraphQL ``FilterInput``): ``values`` for a pick,
    select or toggle, ``min`` / ``max`` for a range, ``within`` (amount, unit) for a window."""

    id: str
    values: tuple[str, ...] = ()
    min: float | None = None
    max: float | None = None
    within: tuple[float, str] | None = None
    active: bool = True


def _range_rule(field: str, given: FilterInput) -> Rule | None:
    lo, hi = given.min, given.max
    if lo is not None and hi is not None:
        return Rule(field, "between", (lo, hi))
    if lo is not None:
        return Rule(field, "gte", lo)
    return Rule(field, "lte", hi) if hi is not None else None


def _window_rule(definition: FilterDefinition, given: FilterInput) -> Rule | None:
    if given.within is None:
        return None
    amount, unit = given.within
    if unit != definition.window_unit:
        raise FilterRefusedError(f"{definition.id}: counts {definition.window_unit}, not {unit}")
    return Rule(definition.field, "between", (0, amount))


def rule_for(definition: FilterDefinition, given: FilterInput) -> Rule | None:
    """The rule an input is, or None when it sets nothing (so it removes nothing)."""
    kind, field = definition.kind, definition.field
    if kind in ("select", "toggle") and len(given.values) > 1:
        raise FilterRefusedError(f"{definition.id}: a {kind} takes one value")
    first = given.values[0] if given.values else None
    rule: Rule | None
    if kind == "pick":
        rule = Rule(field, "in", tuple(given.values)) if given.values else None
    elif kind == "select":
        rule = Rule(field, "eq", first) if first is not None else None
    elif kind == "toggle":
        wanted = {YES: True, NO: False}.get(first or "")
        rule = None if wanted is None else Rule(field, "eq", wanted)
    elif kind == "range":
        rule = _range_rule(field, given)
    elif kind == "window":
        rule = _window_rule(definition, given)
    else:
        raise FilterRefusedError(f"{definition.id}: a {kind} filter is not available yet")
    return rule


def _text(value: FieldValue) -> FieldValue:
    return value if is_missing(value) else str(value)


def as_text(cell: Cell) -> Cell:
    """``cell`` with each present value as text: a pick's options are text (a stored int 3 is
    the option "3")."""
    if isinstance(cell, tuple):
        return tuple(_text(v) for v in cell)
    return _text(cell)


def probe_rule(definition: FilterDefinition) -> Rule:
    """A rule every present value of the right type fails or passes alike, whose only UNKNOWN
    rows are the filter's own: the rows whose value the filter cannot judge."""
    kind, field = definition.kind, definition.field
    if kind in ("pick", "select"):
        return Rule(field, "in", ())
    return Rule(field, "eq", True) if kind == "toggle" else Rule(field, "gte", float("-inf"))


def is_text_kind(definition: FilterDefinition) -> bool:
    return definition.kind in ("pick", "select")


def truth_of(rule: Rule, cell: Cell) -> Truth:
    """``rule`` on one cell; of a tuple, TRUE when any value passes, else UNKNOWN when any is
    unknown or it is empty, else FALSE."""
    if not isinstance(cell, tuple):
        return evaluate_rule(rule, cell)
    results = [evaluate_rule(rule, v) for v in cell]
    if any(r is True for r in results):
        return True
    return None if not results or any(r is None for r in results) else False


def evaluate_filters(
    frame: Frame, size: int, resolved: ResolvedFilters, inputs: Sequence[FilterInput]
) -> dict[str, list[Truth]]:
    """``{filter id: truth per row}`` of every active input that sets something. Refuses an
    input that names a filter that is not offered, or that sees no column in the frame."""
    resolved.check(i.id for i in inputs)
    ids = [i.id for i in inputs]
    if len(set(ids)) != len(ids):
        raise FilterRefusedError(
            f"a filter is set twice: {sorted({i for i in ids if ids.count(i) > 1})}"
        )
    out: dict[str, list[Truth]] = {}
    for given in inputs:
        definition = resolved.get(given.id)
        rule = rule_for(definition, given) if definition and given.active else None
        if definition is None or rule is None:
            continue
        column = frame.get(definition.field)
        if column is None or len(column) != size:
            raise FilterRefusedError(f"{given.id}: the frame has no column {definition.field!r}")
        cells = [as_text(c) for c in column] if is_text_kind(definition) else column
        out[given.id] = [truth_of(rule, cell) for cell in cells]
    return out
