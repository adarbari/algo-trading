"""``compute_facets``: matched, removes, option counts, bins and unknown from one masked pass."""

import pytest

from algotrade.services.read.filtering.definitions import FilterRefusedError, ResolvedFilters
from algotrade.services.read.filtering.facets import BinCount, OptionCount, compute_facets
from algotrade.services.read.filtering.masks import FilterInput
from tests.unit.services.read.filtering.conftest import FRAME, SIZE


def facets(filter_set, *inputs: FilterInput):
    return compute_facets(FRAME, SIZE, ResolvedFilters("things", filter_set.filters), inputs)


def by_id(result, filter_id: str):
    return next(f for f in result.filters if f.id == filter_id)


def test_no_input_matches_every_row_and_counts_every_option(filter_set) -> None:
    result = facets(filter_set)
    assert (result.total, result.matched) == (6, 6) and result.matched_rows == (0, 1, 2, 3, 4, 5)
    assert by_id(result, "tag").options == (
        OptionCount("x", 3), OptionCount("y", 2), OptionCount("z", 1)
    )  # fmt: skip
    assert by_id(result, "tag").removes is None and not by_id(result, "tag").active


def test_removes_is_what_switching_the_filter_off_adds(filter_set) -> None:
    both = facets(filter_set, FilterInput("tag", values=("x",)), FilterInput("size", min=10))
    assert both.matched_rows == (2, 4)
    only_tag = facets(filter_set, FilterInput("tag", values=("x",)))
    only_size = facets(filter_set, FilterInput("size", min=10))
    assert by_id(both, "tag").removes == only_size.matched - both.matched
    assert by_id(both, "size").removes == only_tag.matched - both.matched


def test_counts_ignore_the_filters_own_mask_but_not_the_others(filter_set) -> None:
    result = facets(filter_set, FilterInput("tag", values=("x",)), FilterInput("size", min=10))
    assert by_id(result, "tag").options == (OptionCount("x", 2), OptionCount("y", 1))  # size >= 10
    # the size histogram is over the tag x rows: sizes 1, 12, 20
    assert by_id(result, "size").bins == (BinCount(0, 10, 1), BinCount(10, 20, 2))


def test_bins_have_fixed_edges_the_last_closed_and_unknown_is_counted(filter_set) -> None:
    result = facets(filter_set)
    assert by_id(result, "size").bins == (BinCount(0, 10, 3), BinCount(10, 20, 2))
    assert by_id(result, "size").unknown == 1  # row 3 has no size


def test_a_static_option_with_no_row_shows_with_zero_and_a_toggle_is_yes_no(filter_set) -> None:
    result = facets(
        filter_set, FilterInput("grade", values=("A",)), FilterInput("tag", values=("z",))
    )
    assert by_id(result, "grade").options == (OptionCount("A", 1), OptionCount("B", 0))
    assert by_id(result, "ok").options == (OptionCount("yes", 0), OptionCount("no", 1))


def test_a_switched_off_filter_is_echoed_and_changes_nothing(filter_set) -> None:
    result = facets(filter_set, FilterInput("tag", values=("x",), active=False))
    assert result.matched == 6
    echoed = by_id(result, "tag")
    assert not echoed.active and echoed.removes is None


def test_zero_results_are_recoverable_from_removes(filter_set) -> None:
    result = facets(filter_set, FilterInput("tag", values=("z",)), FilterInput("size", min=10))
    assert result.matched == 0
    assert by_id(result, "tag").removes == 2 and by_id(result, "size").removes == 1


def test_an_offered_filter_with_no_column_is_refused_even_when_not_applied(filter_set) -> None:
    frame = {k: v for k, v in FRAME.items() if k != "feature.size"}
    with pytest.raises(FilterRefusedError, match="size"):
        compute_facets(frame, SIZE, ResolvedFilters("things", filter_set.filters), [])


def test_a_pick_on_a_number_column_matches_its_text_options(filter_set) -> None:
    frame = {**FRAME, "column:tag": [3, 4, 3, None, 5, 3]}
    resolved = ResolvedFilters("things", filter_set.filters)
    result = compute_facets(frame, SIZE, resolved, [FilterInput("tag", values=("3",))])
    assert result.matched_rows == (0, 2, 5)
    assert next(f for f in result.filters if f.id == "tag").options[0] == OptionCount("3", 3)


def test_unknown_is_the_rows_the_filter_cannot_judge(filter_set) -> None:
    frame = {
        **FRAME,
        "column:tag": [("x", None), (), "x", "x", "x", "x"],
        "feature.ok": [True, False, None, None, True, False],
    }
    resolved = ResolvedFilters("things", filter_set.filters)
    result = compute_facets(frame, SIZE, resolved, [])
    assert next(f for f in result.filters if f.id == "tag").unknown == 2  # a missing part; empty
    assert next(f for f in result.filters if f.id == "ok").unknown == 2  # the two nulls


def test_a_select_or_toggle_with_two_values_is_refused(filter_set) -> None:
    resolved = ResolvedFilters("things", filter_set.filters)
    for given in (FilterInput("grade", values=("A", "B")), FilterInput("ok", values=("yes", "no"))):
        with pytest.raises(FilterRefusedError, match="one value"):
            compute_facets(FRAME, SIZE, resolved, [given])
