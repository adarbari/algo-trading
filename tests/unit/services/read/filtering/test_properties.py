"""Property tests (tests/property is at its module cap): the filtering pass (ADR 0082) holds for
any rows and inputs: deterministic; ``removes(f)`` is the rows passing every other active filter
minus ``matched``; an UNKNOWN value never passes; a switched-off filter changes nothing."""

from hypothesis import given, settings
from hypothesis import strategies as st

from algotrade.config.filters.definitions import parse_filter_set
from algotrade.core.model.predicates import is_missing
from algotrade.services.read.filtering.definitions import ResolvedFilters
from algotrade.services.read.filtering.facets import compute_facets
from algotrade.services.read.filtering.masks import (
    FilterInput,
    WindowUnit,
    Within,
    evaluate_filters,
)
from tests.unit.services.read.filtering.conftest import SURFACE

FILTER_SET = parse_filter_set("things", SURFACE)
RESOLVED = ResolvedFilters("things", FILTER_SET.filters)
NUM = st.one_of(st.none(), st.just(float("nan")), st.floats(-5, 25))
SPEC = st.sampled_from("xyz")
TAG = st.one_of(st.none(), SPEC, st.tuples(SPEC, SPEC))
BOOL = st.one_of(st.none(), st.booleans())
SESSIONS = st.one_of(st.none(), st.integers(0, 12))
GRADE = st.one_of(st.none(), st.sampled_from("ABC"))
LIMIT = st.one_of(st.none(), st.floats(-5, 25))


def _rows(n: int):
    def column(item):
        return st.lists(item, min_size=n, max_size=n)

    return st.fixed_dictionaries(
        {
            "column:tag": column(TAG),
            "feature.size": column(NUM),
            "feature.ok": column(BOOL),
            "feature.soon": column(SESSIONS),
            "feature.grade": column(GRADE),
        }
    )


ROWS = st.integers(0, 40).flatmap(_rows)
INPUTS = st.fixed_dictionaries(
    {},
    optional={
        "tag": st.builds(
            FilterInput, st.just("tag"), st.lists(SPEC, max_size=3).map(tuple), active=st.booleans()
        ),
        "size": st.builds(FilterInput, st.just("size"), min=LIMIT, max=LIMIT, active=st.booleans()),
        "ok": st.builds(
            FilterInput,
            st.just("ok"),
            st.sampled_from([("yes",), ("no",), ("either",)]),
            active=st.booleans(),
        ),
        "soon": st.builds(
            FilterInput,
            st.just("soon"),
            within=st.builds(Within, st.integers(0, 12).map(float), st.just(WindowUnit.SESSIONS)),
            active=st.booleans(),
        ),
        "grade": st.builds(
            FilterInput,
            st.just("grade"),
            st.sampled_from("ABC").map(lambda v: (v,)),
            active=st.booleans(),
        ),
    },
).map(lambda d: list(d.values()))


def size_of(frame) -> int:
    return len(frame["feature.size"])


def passing(frame, inputs, skip: str | None = None) -> set[int]:
    masks = evaluate_filters(frame, size_of(frame), RESOLVED, inputs)
    rows = set(range(size_of(frame)))
    for fid, truth in masks.items():
        if fid != skip:
            rows &= {i for i, t in enumerate(truth) if t is True}
    return rows


@settings(max_examples=60, deadline=None)
@given(frame=ROWS, inputs=INPUTS)
def test_the_same_rows_and_inputs_give_the_same_facets(frame, inputs) -> None:
    """Catches: any unordered iteration or hidden state in option order, bins or counts."""
    n = size_of(frame)
    assert compute_facets(frame, n, RESOLVED, inputs) == compute_facets(frame, n, RESOLVED, inputs)


@settings(max_examples=60, deadline=None)
@given(frame=ROWS, inputs=INPUTS)
def test_removes_is_the_rows_passing_the_others_minus_matched(frame, inputs) -> None:
    """Catches: a removes computed from the filter's own mask, or double counting."""
    n = size_of(frame)
    result = compute_facets(frame, n, RESOLVED, inputs)
    matched = passing(frame, inputs)
    assert result.matched == len(matched) and set(result.matched_rows) == matched
    applied = evaluate_filters(frame, n, RESOLVED, inputs)
    for f in result.items:
        if f.id in applied:
            assert f.removes == len(passing(frame, inputs, skip=f.id)) - len(matched)
        else:
            assert f.removes is None


@settings(max_examples=60, deadline=None)
@given(frame=ROWS, inputs=INPUTS)
def test_an_unknown_value_never_passes_its_filter(frame, inputs) -> None:
    """Catches: a null admitted by a range from 0, by a pick, a toggle or a window."""
    masks = evaluate_filters(frame, size_of(frame), RESOLVED, inputs)
    for fid, truth in masks.items():
        field = FILTER_SET.get(fid).field
        for cell, t in zip(frame[field], truth, strict=True):
            if cell is None or is_missing(cell):
                assert t is not True


@settings(max_examples=60, deadline=None)
@given(frame=ROWS, inputs=INPUTS)
def test_a_switched_off_filter_changes_nothing_but_its_own_echo(frame, inputs) -> None:
    """Catches: an inactive filter leaking into the mask, the counts or another's removes."""
    n = size_of(frame)
    off = [FilterInput(i.id, i.values, i.min, i.max, i.within, False) for i in inputs]
    dropped = compute_facets(frame, n, RESOLVED, [])
    result = compute_facets(frame, n, RESOLVED, off)
    assert (result.matched, result.matched_rows) == (dropped.matched, dropped.matched_rows)
    for f, g in zip(result.items, dropped.items, strict=True):
        assert (f.removes, f.unknown, f.options, f.bins) == (
            g.removes,
            g.unknown,
            g.options,
            g.bins,
        )
