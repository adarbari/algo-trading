"""Calendar windows: placement across weekends, holidays, early closes and quarter boundaries;
windows of one kind never overlap; D and S sit before the window."""

from datetime import date

import pytest

from algotrade.config.edges.document import SCHEDULES
from algotrade.core.time.calendar import is_session, next_session, previous_session
from algotrade.core.time.windows import (
    WINDOW_LENGTHS,
    WINDOW_NAMES,
    decision_session,
    entry_session,
    out_of_window_stretches,
    window_length,
    window_name,
    windows,
)

FIRST, LAST = date(2018, 1, 1), date(2025, 12, 31)


def test_window_name_reads_only_the_calendar_prefix() -> None:
    assert window_name("calendar:turn_of_month") == "turn_of_month"
    assert window_name("month_end") is None
    assert window_name("on_event:earnings_reaction") is None


def test_turn_of_month_is_the_last_session_and_three_after_it() -> None:
    w = windows("turn_of_month", date(2026, 1, 1), date(2026, 3, 31))
    assert w[0] == [date(2026, 1, 30), date(2026, 2, 2), date(2026, 2, 3), date(2026, 2, 4)]
    # February 2026 ends on Friday the 27th; March 2nd follows the weekend
    assert w[1] == [date(2026, 2, 27), date(2026, 3, 2), date(2026, 3, 3), date(2026, 3, 4)]
    assert entry_session(w[0]) == date(2026, 1, 29)  # S: the session before the month's last
    assert decision_session(w[0]) == date(2026, 1, 28)  # D = S - 1


def test_turn_of_month_skips_a_weekend_month_end_and_a_holiday() -> None:
    # 2026-05-31 is a Sunday: the last session is Friday the 29th; Memorial Day is not in it
    w = windows("turn_of_month", date(2026, 5, 1), date(2026, 6, 30))[0]
    assert w == [date(2026, 5, 29), date(2026, 6, 1), date(2026, 6, 2), date(2026, 6, 3)]
    # 2024-12-31 then New Year's Day: 2025-01-01 is closed
    w = windows("turn_of_month", date(2024, 12, 1), date(2025, 1, 31))[0]
    assert w == [date(2024, 12, 31), date(2025, 1, 2), date(2025, 1, 3), date(2025, 1, 6)]


def test_the_early_close_the_day_after_thanksgiving_is_a_session_of_the_window() -> None:
    w = windows("quarter_end", date(2024, 9, 1), date(2024, 12, 31))
    assert w[-1][-1] == date(2024, 12, 31)
    # 2024-11-29 is an early close; the turn-of-month window of November includes Dec 2..4
    assert windows("turn_of_month", date(2024, 11, 1), date(2024, 12, 31))[0] == [
        date(2024, 11, 29), date(2024, 12, 2), date(2024, 12, 3), date(2024, 12, 4),
    ]  # fmt: skip


def test_opex_week_is_five_sessions_ending_on_the_expiry() -> None:
    w = windows("opex_week", date(2026, 1, 1), date(2026, 2, 28))
    assert w[0] == [date(2026, 1, d) for d in (12, 13, 14, 15, 16)]
    # Good Friday 2026-04-03 is not the expiry month; Good Friday 2019-04-19 is the third
    # Friday: the expiry is Thursday the 18th and the window starts the Friday before
    april = windows("opex_week", date(2019, 4, 1), date(2019, 4, 30))[0]
    assert april == [date(2019, 4, d) for d in (12, 15, 16, 17, 18)]


def test_quarter_end_is_the_last_five_sessions_of_a_quarter() -> None:
    w = windows("quarter_end", date(2026, 1, 1), date(2026, 6, 30))
    assert [x[-1] for x in w] == [date(2026, 3, 31), date(2026, 6, 30)]
    assert w[0] == [date(2026, 3, d) for d in (25, 26, 27, 30, 31)]
    # a quarter ending on a weekend: 2025-06-30 is a Monday; 2024-09-30 a Monday; 2023-12-29 Fri
    assert windows("quarter_end", date(2023, 12, 1), date(2023, 12, 31))[0][-1] == date(
        2023, 12, 29
    )


def test_pre_holiday_is_the_session_before_a_scheduled_closure() -> None:
    w = windows("pre_holiday", date(2026, 1, 1), date(2026, 12, 31))
    days = [x[0] for x in w]
    assert date(2026, 7, 2) in days  # Independence Day observed Friday July 3
    assert date(2026, 11, 25) in days  # Thanksgiving
    assert date(2026, 4, 2) in days  # Good Friday April 3
    assert all(len(x) == 1 for x in w)
    assert all((next_session(d) - d).days > 1 for d in days)


def test_pre_holiday_ignores_closures_that_were_not_known_ahead() -> None:
    days = {x[0] for x in windows("pre_holiday", date(2012, 1, 1), date(2012, 12, 31))}
    assert date(2012, 10, 26) not in days  # Hurricane Sandy closed 29-30 October
    days = {x[0] for x in windows("pre_holiday", date(2018, 11, 1), date(2018, 12, 31))}
    assert date(2018, 12, 4) not in days  # day of mourning, 5 December


def test_a_year_boundary_holiday_eve_belongs_to_the_old_year() -> None:
    days = {x[0] for x in windows("pre_holiday", date(2020, 12, 1), date(2021, 1, 31))}
    assert date(2020, 12, 24) in days  # Christmas Friday the 25th
    assert date(2020, 12, 31) in days  # New Year's Day Friday


def test_only_whole_windows_inside_the_range_are_returned() -> None:
    assert windows("quarter_end", date(2026, 3, 26), date(2026, 3, 31)) == []
    assert len(windows("quarter_end", date(2026, 3, 25), date(2026, 3, 31))) == 1


@pytest.mark.parametrize("name", WINDOW_NAMES)
def test_windows_have_their_length_never_overlap_and_decide_before_they_start(
    name: str,
) -> None:
    found = windows(name, FIRST, LAST)
    assert found
    seen: set[date] = set()
    for w in found:
        assert len(w) == window_length(name) == WINDOW_LENGTHS[name]
        assert all(is_session(d) for d in w)
        assert w == sorted(set(w))
        assert not seen & set(w), f"{name}: {w} overlaps an earlier window"
        seen |= set(w)
        s = entry_session(w)
        assert s == previous_session(w[0])
        assert decision_session(w) == previous_session(s)
        assert next_session(s) == w[0]


def test_an_unknown_window_is_refused() -> None:
    with pytest.raises(KeyError):
        windows("fomc", FIRST, LAST)
    with pytest.raises(KeyError):
        window_length("fomc")


def test_stretches_tile_from_the_session_after_each_window_and_never_touch_one() -> None:
    placed = windows("turn_of_month", FIRST, LAST)
    stretches = out_of_window_stretches(placed, 4, LAST)
    inside = {d for w in placed for d in w}
    assert stretches and all(len(s) == 4 for s in stretches)
    assert not any(d in inside for s in stretches for d in s)
    assert stretches[0][0] == next_session(placed[0][-1])  # the first tile starts after a window
    flat = [d for s in stretches for d in s]
    assert len(flat) == len(set(flat))  # non-overlapping
    assert all(s[-1] <= LAST for s in stretches)


def test_stretches_are_deterministic_and_do_not_depend_on_what_follows_the_range() -> None:
    placed = windows("opex_week", FIRST, date(2022, 12, 31))
    a = out_of_window_stretches(placed, 5, date(2022, 12, 31))
    assert a == out_of_window_stretches(list(reversed(placed)), 5, date(2022, 12, 31))
    longer = out_of_window_stretches(windows("opex_week", FIRST, LAST), 5, LAST)
    assert longer[: len(a) - 1] == a[:-1]  # the later range only adds (the last tile may extend)


def test_a_stretch_that_does_not_fit_whole_is_dropped() -> None:
    first_window = windows("pre_holiday", date(2025, 1, 1), date(2025, 12, 31))[0]
    short = out_of_window_stretches([first_window], 3, next_session(next_session(first_window[0])))
    assert short == []


@pytest.mark.parametrize("name", WINDOW_NAMES)
def test_windows_of_one_kind_never_overlap_over_forty_years(name: str) -> None:
    seen: set[date] = set()
    for w in windows(name, date(2000, 1, 1), date(2040, 12, 31)):
        assert not seen & set(w), f"{name}: {w} overlaps an earlier window"
        seen |= set(w)


def test_pre_month_end_is_the_last_three_sessions_of_each_month() -> None:
    w = windows("pre_month_end", date(2026, 1, 1), date(2026, 3, 31))
    assert len(w) == 3
    assert w[0] == [date(2026, 1, 28), date(2026, 1, 29), date(2026, 1, 30)]
    assert w[1] == [date(2026, 2, 25), date(2026, 2, 26), date(2026, 2, 27)]


def test_year_turn_spans_december_and_january_and_is_found_once() -> None:
    w = windows("year_turn", date(2025, 12, 1), date(2027, 1, 31))
    assert len(w) == 2
    assert w[0] == [
        date(2025, 12, 24), date(2025, 12, 26), date(2025, 12, 29), date(2025, 12, 30),
        date(2025, 12, 31), date(2026, 1, 2), date(2026, 1, 5), date(2026, 1, 6),
        date(2026, 1, 7), date(2026, 1, 8),
    ]  # fmt: skip
    assert len(w[0]) == window_length("year_turn") == 10
    # a range cutting the window in two finds none; the window is found by either scan year once
    assert windows("year_turn", date(2025, 12, 1), date(2026, 1, 5)) == []
    assert windows("year_turn", date(2025, 12, 24), date(2026, 1, 8)) == [w[0]]
    assert windows("year_turn", date(2026, 1, 1), date(2026, 12, 1)) == []


def test_window_names_do_not_clash_with_the_document_schedules() -> None:
    assert not set(WINDOW_NAMES) & set(SCHEDULES)
