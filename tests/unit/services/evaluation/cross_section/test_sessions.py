"""``edge_sessions``: the schedule's start sessions, a horizon apart; a month cut short by the
range is not a month end; an event schedule is ED4's."""

from datetime import date

import pytest

from algotrade.core.model.errors import ConfigurationError
from algotrade.core.time.calendar import sessions_between
from algotrade.services.evaluation.cross_section.sessions import edge_sessions

DAYS = sessions_between(date(2026, 1, 2), date(2026, 4, 15))


def test_every_session_takes_every_horizon_th_session() -> None:
    picked = edge_sessions("every_session", DAYS[:10], 3)
    assert picked == [DAYS[0], DAYS[3], DAYS[6], DAYS[9]]


def test_month_end_is_each_months_last_session_and_a_cut_month_is_dropped() -> None:
    assert edge_sessions("month_end", DAYS, 5) == [
        date(2026, 1, 30), date(2026, 2, 27), date(2026, 3, 31),
    ]  # fmt: skip
    assert edge_sessions("month_end", sessions_between(date(2026, 1, 2), date(2026, 3, 31)), 5)[
        -1
    ] == (date(2026, 3, 31))  # the range ends on the month's last session: it counts


def test_month_end_is_thinned_so_windows_do_not_overlap() -> None:
    picked = edge_sessions("month_end", DAYS, 30)
    assert picked == [date(2026, 1, 30), date(2026, 3, 31)]
    assert DAYS.index(picked[1]) - DAYS.index(picked[0]) >= 30


def test_an_event_schedule_arrives_with_ed4_and_nothing_gives_nothing() -> None:
    with pytest.raises(ConfigurationError, match="ED4"):
        edge_sessions("on_event:earnings", DAYS, 20)
    with pytest.raises(ConfigurationError, match="unknown schedule"):
        edge_sessions("weekly", DAYS, 20)
    with pytest.raises(ConfigurationError, match="horizon"):
        edge_sessions("month_end", DAYS, 0)
    assert edge_sessions("month_end", [], 20) == []
