"""The date rules of ``events/ipo_lockup`` (edge build D8): the acceptance session (New York, never
earlier, a non-session moves on), the restriction end in days and calendar months, the expiry (the
first session after it) and the known_from of a re-extracted version."""

from datetime import UTC, date, datetime

import pandas as pd
import pytest

from algotrade_ingestion.tasks.events.lockup_dates import (
    acceptance_session,
    expiry_session,
    restated_known_from,
    restriction_end,
)


@pytest.mark.parametrize(
    ("accepted", "session"),
    [
        ("2026-06-12T13:29:00Z", date(2026, 6, 12)),  # morning, New York
        ("2026-06-12T21:30:00Z", date(2026, 6, 12)),  # 17:30: after the close, still that day
        ("2026-06-13T03:30:00Z", date(2026, 6, 12)),  # 23:30 New York is still the 12th
        ("2026-06-13T04:00:00Z", date(2026, 6, 15)),  # 00:00 Saturday: no session, the Monday
        ("2026-07-03T15:00:00Z", date(2026, 7, 6)),  # Independence Day observed: the Monday
    ],
)
def test_the_acceptance_session_is_the_new_york_date_moved_to_a_session(
    accepted: str, session: date
) -> None:
    assert acceptance_session(pd.Timestamp(accepted)) == session


def test_a_term_in_days_adds_calendar_days_and_in_months_calendar_months() -> None:
    assert restriction_end(date(2026, 6, 12), 180, "days") == date(2026, 12, 9)
    assert restriction_end(date(2025, 8, 31), 6, "months") == date(2026, 2, 28)  # clamped
    assert restriction_end(date(2026, 1, 15), 12, "months") == date(2027, 1, 15)
    assert restriction_end(date(2026, 11, 30), 3, "months") == date(2027, 2, 28)
    with pytest.raises(ValueError, match="unit"):
        restriction_end(date(2026, 1, 1), 1, "weeks")


def test_the_expiry_is_the_first_session_strictly_after_the_last_restricted_day() -> None:
    assert expiry_session(date(2026, 12, 9)) == date(2026, 12, 10)  # Wednesday -> Thursday
    assert expiry_session(date(2026, 12, 11)) == date(2026, 12, 14)  # Friday -> Monday
    assert expiry_session(date(2026, 12, 24)) == date(2026, 12, 28)  # Christmas Day is no session


@pytest.mark.parametrize(
    ("now", "known"),
    [
        (datetime(2026, 10, 2, 22, tzinfo=UTC), date(2026, 10, 5)),  # Friday 18:00 -> Monday
        (datetime(2026, 10, 5, 14, tzinfo=UTC), date(2026, 10, 6)),  # Monday morning -> Tuesday
        (datetime(2026, 10, 6, 3, tzinfo=UTC), date(2026, 10, 6)),  # Monday 23:00 NY -> Tuesday
    ],
)
def test_a_restated_version_is_known_from_the_session_after_the_fetch(
    now: datetime, known: date
) -> None:
    assert restated_known_from(date(2026, 6, 12), now) == known


def test_a_restatement_is_never_earlier_than_the_acceptance_session() -> None:
    future = date(2026, 12, 1)  # an acceptance session after the fetch (a bad clock)
    assert restated_known_from(future, datetime(2026, 10, 2, 22, tzinfo=UTC)) == future
