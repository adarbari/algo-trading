"""``periods``: the windows of a range and the stretches beside them come from the calendar alone,
so a longer range only adds periods and a period's sessions never touch another's."""

from datetime import date

import pytest

from algotrade.core.time.calendar import next_session, previous_session
from algotrade.core.time.windows import WINDOW_LENGTHS, WINDOW_NAMES, windows
from algotrade.services.evaluation.time_series.periods import periods


@pytest.mark.parametrize("name", WINDOW_NAMES)
def test_periods_hold_every_window_and_stretches_of_the_same_length(name: str) -> None:
    first, last = date(2023, 1, 1), date(2025, 12, 31)
    found = periods(name, first, last)
    assert [p.first for p in found if p.inside] == [w[0] for w in windows(name, first, last)]
    assert found == sorted(found, key=lambda p: p.first)
    for p in found:
        assert p.entry == previous_session(p.first)
        assert p.decision == previous_session(p.entry)
    # no two periods share a session: a period spans WINDOW_LENGTHS sessions from its first
    span = WINDOW_LENGTHS[name]
    seen: set[date] = set()
    for p in found:
        day, sessions = p.first, []
        for _ in range(span):
            sessions.append(day)
            day = next_session(day)
        assert not seen & set(sessions)
        seen |= set(sessions)
        assert sessions[-1] <= last


@pytest.mark.parametrize("name", WINDOW_NAMES)
def test_a_window_rule_never_peeks_at_the_future(name: str) -> None:
    """The periods of a range are exactly those of any longer range that end by the first
    range's last session: nothing placed depends on what follows it."""
    first = date(2022, 1, 1)
    long = periods(name, first, date(2025, 12, 31))
    for last in (date(2022, 9, 30), date(2023, 6, 30), date(2024, 3, 31), date(2025, 1, 15)):
        short = periods(name, first, last)
        span = WINDOW_LENGTHS[name]
        inside_range = [p for p in long if _ends_by(p.first, span, last)]
        assert short == inside_range


def _ends_by(first: date, span: int, last: date) -> bool:
    day = first
    for _ in range(span - 1):
        day = next_session(day)
    return day <= last


def test_the_tiling_is_deterministic() -> None:
    a = periods("opex_week", date(2020, 1, 1), date(2024, 12, 31))
    assert a == periods("opex_week", date(2020, 1, 1), date(2024, 12, 31))
