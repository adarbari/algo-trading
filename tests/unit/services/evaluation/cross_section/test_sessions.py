"""``decision_sessions``: the schedule's decision sessions, a horizon apart; a month cut short by
the range is not a month end; ``entry_session`` (S = D + the offset, always after D) and the
blocks an event schedule's days are pooled into."""

from datetime import date
from itertools import pairwise

import pytest

from algotrade.core.model.errors import ConfigurationError
from algotrade.core.time.calendar import next_session, sessions_between
from algotrade.services.evaluation.cross_section.sessions import (
    Leg,
    decision_sessions,
    entry_leg,
    entry_session,
    event_blocks,
    wait_closes,
)

DAYS = sessions_between(date(2026, 1, 2), date(2026, 4, 15))


def test_every_session_takes_every_horizon_th_session() -> None:
    picked = decision_sessions("every_session", DAYS[:10], 3)
    assert picked == [DAYS[0], DAYS[3], DAYS[6], DAYS[9]]


def test_month_end_is_each_months_last_session_and_a_cut_month_is_dropped() -> None:
    assert decision_sessions("month_end", DAYS, 5) == [
        date(2026, 1, 30), date(2026, 2, 27), date(2026, 3, 31),
    ]  # fmt: skip
    assert decision_sessions("month_end", sessions_between(date(2026, 1, 2), date(2026, 3, 31)), 5)[
        -1
    ] == (date(2026, 3, 31))  # the range ends on the month's last session: it counts


def test_month_end_is_thinned_so_windows_do_not_overlap() -> None:
    picked = decision_sessions("month_end", DAYS, 30)
    assert picked == [date(2026, 1, 30), date(2026, 3, 31)]
    assert DAYS.index(picked[1]) - DAYS.index(picked[0]) >= 30


def test_an_event_schedule_is_read_through_events_and_nothing_gives_nothing() -> None:
    with pytest.raises(ConfigurationError, match=r"events\.py"):
        decision_sessions("on_event:earnings_reaction", DAYS, 20)
    with pytest.raises(ConfigurationError, match="unknown schedule"):
        decision_sessions("weekly", DAYS, 20)
    with pytest.raises(ConfigurationError, match="horizon"):
        decision_sessions("month_end", DAYS, 0)
    assert decision_sessions("month_end", [], 20) == []


def test_the_entry_session_is_the_offset_th_session_after_the_decision() -> None:
    friday = date(2026, 1, 9)
    assert entry_session(friday, 1) == date(2026, 1, 12)  # S > D: the next session's close
    assert entry_session(friday, 3) == date(2026, 1, 14)
    with pytest.raises(ConfigurationError, match="at least 1"):
        entry_session(friday, 0)  # never the decision session itself


def test_event_days_join_a_block_while_they_are_under_a_horizon_from_its_first_day() -> None:
    days = DAYS[:30]
    event_days = [days[2], days[3], days[11], days[12], days[13], days[14], days[25]]
    blocks = event_blocks(event_days, days, 5)
    # A day joins while it is fewer than 5 sessions after the block's first day: a block spans
    # at most one horizon and is one statistic.
    assert blocks == [[days[2], days[3]], [days[11], days[12], days[13], days[14]], [days[25]]]
    assert event_blocks(event_days, days, 1) == [[d] for d in event_days]
    chain = [days[0], days[4], days[8], days[12]]  # each within 5 of the last, 12 from the first
    assert event_blocks(chain, days, 5) == [[days[0], days[4]], [days[8], days[12]]]
    assert event_blocks([days[0], days[5]], days, 5) == [[days[0]], [days[5]]]
    assert event_blocks([], days, 5) == []
    assert event_blocks([days[5], days[2]], days, 5) == [[days[2], days[5]]]  # order-free
    with pytest.raises(ConfigurationError, match="horizon"):
        event_blocks(event_days, days, 0)


def test_daily_events_over_a_long_range_make_one_block_per_horizon_never_one_block() -> None:
    """2026-10-08: earnings land almost every session; blocks measured from their last day
    chained two years into ONE independent session. A block spans at most one horizon."""
    days = DAYS[:60]
    blocks = event_blocks(days, days, 20)
    assert len(blocks) == 3 and all(len(b) == 20 for b in blocks)


def test_a_calendar_window_gives_each_whole_windows_decision_session() -> None:
    days = sessions_between(date(2026, 1, 2), date(2026, 4, 15))
    # turn of month: S is the session before the month's last, D the one before S
    assert decision_sessions("calendar:turn_of_month", days, 4) == [
        date(2026, 1, 28), date(2026, 2, 25), date(2026, 3, 27),
    ]  # fmt: skip
    # the March window ends 2026-04-02 (inside the range); a range cut inside it drops it
    cut = sessions_between(date(2026, 1, 2), date(2026, 4, 1))
    assert decision_sessions("calendar:turn_of_month", cut, 4)[-1] == date(2026, 2, 25)
    assert decision_sessions("calendar:pre_holiday", days, 1) == [
        date(2026, 1, 14), date(2026, 2, 11), date(2026, 3, 31),
    ]  # fmt: skip
    assert decision_sessions("calendar:turn_of_month", [], 4) == []


def test_calendar_decisions_do_not_overlap_and_enter_the_session_after_the_decision() -> None:
    days = sessions_between(date(2020, 1, 2), date(2025, 12, 31))
    for name, length in (("opex_week", 5), ("quarter_end", 5), ("turn_of_month", 4)):
        picked = decision_sessions(f"calendar:{name}", days, length)
        gaps = [days.index(b) - days.index(a) for a, b in pairwise(picked)]
        assert min(gaps) >= length + 1, name  # D + 2 = window start; a window is `length` long
        assert entry_session(picked[0], 1) == days[days.index(picked[0]) + 1]


def test_a_calendar_horizon_must_equal_the_window_length_and_the_window_must_exist() -> None:
    with pytest.raises(ConfigurationError, match="holds 4 to 4 sessions"):
        decision_sessions("calendar:turn_of_month", DAYS, 5)
    with pytest.raises(ConfigurationError, match="unknown calendar window"):
        decision_sessions("calendar:fomc", DAYS, 1)


def test_a_sleeve_on_a_calendar_window_holds_up_to_its_gap_and_a_screen_does_not() -> None:
    """A named option sleeve's window places only the entry (ADR 0088, X1): monthly entries the
    first session after each expiry, held up to the window's gap, so holds never overlap."""
    days = sessions_between(date(2026, 1, 2), date(2026, 12, 31))
    monthly = decision_sessions("calendar:after_monthly_expiry", days, 17, sleeve=True)
    assert [d.month for d in monthly] == list(range(1, 13))  # one a month
    holds = [(entry_session(d, 1), sessions_after(entry_session(d, 1), 17)) for d in monthly]
    assert all(end <= nxt for (_, end), (nxt, _) in pairwise(holds))  # exit by the next entry
    with pytest.raises(ConfigurationError, match="holds 1 to 17"):
        decision_sessions("calendar:after_monthly_expiry", days, 18, sleeve=True)
    with pytest.raises(ConfigurationError, match="holds 1 to 1"):
        decision_sessions("calendar:after_monthly_expiry", days, 17)  # not a sleeve


def test_an_entry_leg_has_one_s_per_close_of_the_wait_and_ends_at_the_last() -> None:
    d = date(2026, 9, 3)  # Thursday; Sept 7 is a holiday
    leg = entry_leg(d, 1, 3)
    assert wait_closes(d, 3) == [d, date(2026, 9, 4), date(2026, 9, 8)]
    assert leg.entries == (date(2026, 9, 4), date(2026, 9, 8), date(2026, 9, 9))
    assert leg.entry == leg.candidates[-1] and Leg(d, date(2026, 9, 4)).candidates == (
        date(2026, 9, 4),
    )


def sessions_after(start: date, n: int) -> date:
    """The session ``n`` after ``start``."""
    for _ in range(n):
        start = next_session(start)
    return start


def test_a_sleeve_ladder_decides_every_session_and_only_a_sleeve_may() -> None:
    """index_put_ladder: every session is a decision (the holds overlap, the slots book sizes
    them); every_session keeps its spacing, and a cross-section edge cannot ladder."""
    days = sessions_between(date(2026, 1, 2), date(2026, 3, 31))
    assert decision_sessions("every_session_ladder", days, 17, sleeve=True) == days
    assert len(decision_sessions("every_session", days, 17, sleeve=True)) < len(days)
    with pytest.raises(ConfigurationError, match="named option sleeve"):
        decision_sessions("every_session_ladder", days, 17)
