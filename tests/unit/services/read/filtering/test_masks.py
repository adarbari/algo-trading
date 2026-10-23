"""``evaluate_filters``: the operator of each kind, UNKNOWN never passing, a switched-off or
empty input in no mask."""

import pytest

from algotrade.services.read.filtering.definitions import FilterRefusedError, ResolvedFilters
from algotrade.services.read.filtering.masks import FilterInput, evaluate_filters
from tests.unit.services.read.filtering.conftest import FRAME, SIZE


def run(filter_set, *inputs: FilterInput):
    resolved = ResolvedFilters("things", filter_set.filters)
    return evaluate_filters(FRAME, SIZE, resolved, inputs)


def passes(masks, filter_id: str) -> list[int]:
    return [i for i, t in enumerate(masks[filter_id]) if t is True]


def test_a_pick_keeps_a_row_when_any_of_its_values_is_picked(filter_set) -> None:
    masks = run(filter_set, FilterInput("tag", values=("y",)))
    assert passes(masks, "tag") == [1, 2]  # row 2 is picked by x and y
    assert masks["tag"][3] is None  # no value: UNKNOWN, never a pass


def test_a_select_is_one_value(filter_set) -> None:
    assert passes(run(filter_set, FilterInput("grade", values=("A",))), "grade") == [0, 2, 5]


def test_a_toggle_is_yes_no_or_either(filter_set) -> None:
    assert passes(run(filter_set, FilterInput("ok", values=("yes",))), "ok") == [0, 2, 4]
    assert passes(run(filter_set, FilterInput("ok", values=("no",))), "ok") == [1, 5]
    assert run(filter_set, FilterInput("ok", values=("either",))) == {}


def test_a_range_is_closed_and_min_zero_never_admits_null(filter_set) -> None:
    masks = run(filter_set, FilterInput("size", min=0))
    assert passes(masks, "size") == [0, 1, 2, 4, 5] and masks["size"][3] is None
    assert passes(run(filter_set, FilterInput("size", min=5, max=12)), "size") == [1, 2]
    assert passes(run(filter_set, FilterInput("size", max=1)), "size") == [0, 5]
    assert run(filter_set, FilterInput("size")) == {}  # nothing set


def test_a_window_counts_from_zero_in_the_definitions_unit(filter_set) -> None:
    masks = run(filter_set, FilterInput("soon", within=(3, "sessions")))
    assert passes(masks, "soon") == [0, 1, 5] and masks["soon"][2] is None
    with pytest.raises(FilterRefusedError, match="sessions"):
        run(filter_set, FilterInput("soon", within=(3, "days")))


def test_a_switched_off_input_is_in_no_mask(filter_set) -> None:
    assert run(filter_set, FilterInput("tag", values=("x",), active=False)) == {}


def test_an_unknown_duplicate_or_columnless_input_is_refused(filter_set) -> None:
    with pytest.raises(FilterRefusedError):
        run(filter_set, FilterInput("nope"))
    with pytest.raises(FilterRefusedError, match="twice"):
        run(filter_set, FilterInput("tag", values=("x",)), FilterInput("tag", values=("y",)))
    resolved = ResolvedFilters("things", filter_set.filters)
    with pytest.raises(FilterRefusedError, match="no column"):
        evaluate_filters({}, 0, resolved, [FilterInput("tag", values=("x",))])
