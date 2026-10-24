"""``compute_facets``: what one masked pass over a frame tells (ADR 0082 decision 2). ``matched``
is the rows passing every active filter; ``removes(f)`` the rows passing every OTHER active
filter minus ``matched`` (what switching ``f`` off would add: the zero-result recovery is the
same number); a filter's option counts, histogram bins and ``unknown`` count its rows among
those passing the other active filters (the filter's own mask never narrows its own counts).
A switched-off or empty input is echoed, ``removes`` None, and is in no mask. One pass: each
row's number of failing filters says which rows pass all, or all but one.

Order and edges are fixed so the same input gives the same bytes: options by count (largest
first) then value; a range's bins are the definition's ascending edges, each ``[lo, hi)`` but
the last, ``[lo, hi]``, so a value outside the first and last edge is in none (a tuple cell is
not a number: it is in no bin); a toggle's options
are yes / no; ``unknown`` counts rows whose value for the filter is UNKNOWN (never passing)."""

import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise

from algotrade.config.filters.definitions import FilterDefinition
from algotrade.core.model.predicates import Truth, is_missing
from algotrade.services.read.filtering.definitions import FilterRefusedError, ResolvedFilters
from algotrade.services.read.filtering.masks import (
    NO,
    YES,
    Cell,
    FilterInput,
    Frame,
    as_text,
    evaluate_filters,
    is_text_kind,
    probe_rule,
    truth_of,
)


@dataclass(frozen=True)
class OptionCount:
    value: str
    count: int


@dataclass(frozen=True)
class BinCount:
    lo: float
    hi: float
    count: int


@dataclass(frozen=True)
class FilterFacet:
    """``removes``: None when the filter is not applied (switched off, or nothing set)."""

    id: str
    active: bool
    removes: int | None
    unknown: int
    options: tuple[OptionCount, ...] = ()
    bins: tuple[BinCount, ...] = ()


@dataclass(frozen=True)
class Facets:
    """``matched_rows``: indexes of the rows passing every active filter, in frame order."""

    total: int
    matched: int
    matched_rows: tuple[int, ...]
    items: tuple[FilterFacet, ...]


def _values(cell: Cell) -> tuple[object, ...]:
    return cell if isinstance(cell, tuple) else (cell,)


def _option_counts(
    definition: FilterDefinition, column: Sequence[Cell], rows: Sequence[int]
) -> tuple[OptionCount, ...]:
    if definition.kind == "toggle":
        seen: Counter[str] = Counter()
        for i in rows:
            seen.update(
                {YES if v is True else NO for v in _values(column[i]) if isinstance(v, bool)}
            )
        return tuple(OptionCount(v, seen[v]) for v in (YES, NO))
    counts: Counter[str] = Counter()
    for i in rows:
        counts.update({str(v) for v in _values(column[i]) if not is_missing(v)})  # type: ignore[arg-type]
    for option in definition.static:  # an offered value no row has still shows, with 0
        counts.setdefault(option.value, 0)
    return tuple(
        OptionCount(v, n) for v, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    )


def _numbers(column: Sequence[Cell], rows: Sequence[int]) -> list[float]:
    return [
        float(v)
        for i in rows
        if not isinstance(v := column[i], bool)
        and isinstance(v, int | float)
        and not is_missing(v)
        and math.isfinite(v)
    ]


def nice_edges(values: Sequence[float], bins: int = 10) -> tuple[float, ...]:
    """Fixed-looking histogram edges for a range that declares none (a filter made on the fly): a
    step of 1, 2 or 5 times a power of ten, about ``bins`` of them over the values; the same values
    give the same edges. Empty (no histogram) for fewer than two distinct values."""
    if len(set(values)) < 2:
        return ()
    low, high = min(values), max(values)
    raw = (high - low) / bins
    power = 10 ** math.floor(math.log10(raw))
    step = next(m * power for m in (1, 2, 5, 10) if m * power >= raw)
    start = math.floor(low / step)
    stop = math.ceil(high / step)
    digits = max(12, 3 - math.floor(math.log10(step)))
    edges = tuple(round(k * step, digits) for k in range(start, stop + 1))
    return edges if all(a < b for a, b in pairwise(edges)) else ()


def _bin_counts(
    edges: Sequence[float], column: Sequence[Cell], rows: Sequence[int]
) -> tuple[BinCount, ...]:
    if len(edges) < 2:
        return ()
    counts = [0] * (len(edges) - 1)
    last = len(counts) - 1
    for i in rows:
        v = column[i]
        if isinstance(v, bool) or not isinstance(v, int | float) or is_missing(v):
            continue
        for b in range(len(counts)):
            if edges[b] <= v < edges[b + 1] or (b == last and v == edges[-1]):
                counts[b] += 1
                break
    return tuple(BinCount(edges[b], edges[b + 1], n) for b, n in enumerate(counts))


def compute_facets(
    frame: Frame, size: int, resolved: ResolvedFilters, inputs: Sequence[FilterInput]
) -> Facets:
    """The facets of every offered filter over ``size`` rows (``frame``: the columns by field)."""
    truths: dict[str, list[Truth]] = evaluate_filters(frame, size, resolved, inputs)
    failing = [0] * size  # active filters each row does not pass
    for truth in truths.values():
        for i, t in enumerate(truth):
            if t is not True:
                failing[i] += 1
    matched_rows = tuple(i for i in range(size) if failing[i] == 0)
    given = {i.id: i for i in inputs}
    facets: list[FilterFacet] = []
    for definition in resolved.offered:
        mine = truths.get(definition.id)
        if mine is None:  # not applied: every row that passes the active filters counts
            rows: Sequence[int] = matched_rows
        else:
            rows = [
                i
                for i in range(size)
                if failing[i] == 0 or (failing[i] == 1 and mine[i] is not True)
            ]
        column = frame.get(definition.field)
        if column is None or len(column) != size:
            raise FilterRefusedError(
                f"{definition.id}: the frame has no column {definition.field!r}"
            )
        options: tuple[OptionCount, ...] = ()
        bins: tuple[BinCount, ...] = ()
        if definition.kind in ("pick", "select", "toggle"):
            options = _option_counts(definition, column, rows)
        elif definition.kind == "range":
            edges = definition.bins or nice_edges(_numbers(column, range(len(column))))
            bins = _bin_counts(edges, column, rows)
        probe = probe_rule(definition)
        cells = [as_text(c) for c in column] if is_text_kind(definition) else column
        unknown = sum(1 for i in rows if truth_of(probe, cells[i]) is None)
        removes = None if mine is None else len(rows) - len(matched_rows)
        facets.append(
            FilterFacet(
                definition.id,
                definition.id in given and given[definition.id].active,
                removes,
                unknown,
                options,
                bins,
            )
        )
    return Facets(size, len(matched_rows), matched_rows, tuple(facets))
