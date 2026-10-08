"""``decision_sessions``: the schedule's decision sessions, a horizon apart; a month cut short by
the range is not a month end; ``entry_session`` (S = D + the offset, always after D) and the
blocks an event schedule's days are pooled into."""

from datetime import date

import pytest

from algotrade.core.model.errors import ConfigurationError
from algotrade.core.time.calendar import sessions_between
from algotrade.services.evaluation.cross_section.sessions import (
    decision_sessions,
    entry_session,
    event_blocks,
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


def test_event_days_join_a_block_while_the_gap_to_its_last_day_is_under_a_horizon() -> None:
    days = DAYS[:30]
    event_days = [days[2], days[3], days[11], days[12], days[13], days[14], days[25]]
    blocks = event_blocks(event_days, days, 5)
    # A day joins while it is fewer than 5 sessions after the block's last day: overlapping
    # event windows are one statistic, never several independent sessions.
    assert blocks == [[days[2], days[3]], [days[11], days[12], days[13], days[14]], [days[25]]]
    assert event_blocks(event_days, days, 1) == [[d] for d in event_days]
    chain = [days[0], days[4], days[8], days[12]]  # each within 5 of the last, 12 from the first
    assert event_blocks(chain, days, 5) == [chain]  # no window overlaps the next block's first
    assert event_blocks([days[0], days[5]], days, 5) == [[days[0]], [days[5]]]
    assert event_blocks([], days, 5) == []
    assert event_blocks([days[5], days[2]], days, 5) == [[days[2], days[5]]]  # order-free
    with pytest.raises(ConfigurationError, match="horizon"):
        event_blocks(event_days, days, 0)
