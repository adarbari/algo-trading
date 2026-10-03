from datetime import UTC, date, datetime, timedelta

import pytest

from algotrade.core.time.calendar import (
    close_time,
    early_closes,
    easter,
    holidays,
    is_session,
    last_closed_session,
    next_session,
    nth_weekday,
    previous_session,
    sessions_between,
    third_friday,
)

# NYSE published full-day holidays (nyse.com hours & calendars).
NYSE_HOLIDAYS = {
    2024: [
        date(2024, 1, 1),
        date(2024, 1, 15),
        date(2024, 2, 19),
        date(2024, 3, 29),
        date(2024, 5, 27),
        date(2024, 6, 19),
        date(2024, 7, 4),
        date(2024, 9, 2),
        date(2024, 11, 28),
        date(2024, 12, 25),
    ],
    2025: [
        date(2025, 1, 1),
        date(2025, 1, 20),
        date(2025, 2, 17),
        date(2025, 4, 18),
        date(2025, 5, 26),
        date(2025, 6, 19),
        date(2025, 7, 4),
        date(2025, 9, 1),
        date(2025, 11, 27),
        date(2025, 12, 25),
    ],
    2026: [
        date(2026, 1, 1),
        date(2026, 1, 19),
        date(2026, 2, 16),
        date(2026, 4, 3),
        date(2026, 5, 25),
        date(2026, 6, 19),
        date(2026, 7, 3),  # July 4 is a Saturday
        date(2026, 9, 7),
        date(2026, 11, 26),
        date(2026, 12, 25),
    ],
    2027: [
        date(2027, 1, 1),
        date(2027, 1, 18),
        date(2027, 2, 15),
        date(2027, 3, 26),
        date(2027, 5, 31),
        date(2027, 6, 18),  # June 19 is a Saturday
        date(2027, 7, 5),  # July 4 is a Sunday
        date(2027, 9, 6),
        date(2027, 11, 25),
        date(2027, 12, 24),  # Christmas is a Saturday
    ],
}
NYSE_EARLY_CLOSES = {
    2024: [date(2024, 7, 3), date(2024, 11, 29), date(2024, 12, 24)],
    2025: [date(2025, 7, 3), date(2025, 11, 28), date(2025, 12, 24)],
    2026: [date(2026, 11, 27), date(2026, 12, 24)],  # July 3 is the holiday itself
    2027: [date(2027, 11, 26)],  # Dec 24 is the observed Christmas
    2028: [date(2028, 7, 3), date(2028, 11, 24)],
}


@pytest.mark.parametrize("year", sorted(NYSE_HOLIDAYS))
def test_full_day_holidays_match_nyse(year: int) -> None:
    assert sorted(holidays(year)) == NYSE_HOLIDAYS[year]


@pytest.mark.parametrize("year", sorted(NYSE_EARLY_CLOSES))
def test_early_closes_match_nyse(year: int) -> None:
    assert sorted(early_closes(year)) == NYSE_EARLY_CLOSES[year]


def test_new_year_observance() -> None:
    assert date(2023, 1, 2) in holidays(2023)  # Sunday -> Monday
    assert not holidays(2028) & {date(2027, 12, 31), date(2028, 1, 1)}  # Saturday: none
    assert is_session(date(2027, 12, 31))


def test_juneteenth_only_from_2022() -> None:
    assert date(2022, 6, 20) in holidays(2022)  # Sunday -> Monday
    assert not any(d.month == 6 for d in holidays(2021))


def test_easter_computus() -> None:
    assert [easter(y) for y in (2024, 2025, 2026, 2027, 2038)] == [
        date(2024, 3, 31),
        date(2025, 4, 20),
        date(2026, 4, 5),
        date(2027, 3, 28),
        date(2038, 4, 25),
    ]


def test_weekday_helpers() -> None:
    assert nth_weekday(2026, 5, 0, -1) == date(2026, 5, 25)
    assert nth_weekday(2026, 12, 3, -1) == date(2026, 12, 31)
    assert third_friday(2026, 10) == date(2026, 10, 16)


def test_session_navigation() -> None:
    assert not is_session(date(2026, 10, 3))  # Saturday
    assert previous_session(date(2026, 10, 5)) == date(2026, 10, 2)
    assert previous_session(date(2026, 11, 27)) == date(2026, 11, 25)  # over Thanksgiving
    assert next_session(date(2026, 12, 24)) == date(2026, 12, 28)
    assert sessions_between(date(2026, 12, 23), date(2026, 12, 29)) == [
        date(2026, 12, 23),
        date(2026, 12, 24),
        date(2026, 12, 28),
        date(2026, 12, 29),
    ]
    assert sessions_between(date(2026, 10, 3), date(2026, 10, 4)) == []


def test_close_times_in_utc() -> None:
    assert close_time(date(2026, 10, 2)) == datetime(2026, 10, 2, 20, tzinfo=UTC)  # EDT
    assert close_time(date(2026, 12, 24)) == datetime(2026, 12, 24, 18, tzinfo=UTC)  # EST 13:00
    with pytest.raises(ValueError, match="not a session"):
        close_time(date(2026, 12, 25))


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (datetime(2026, 10, 2, 20, 29, tzinfo=UTC), date(2026, 10, 1)),  # before close + settle
        (datetime(2026, 10, 2, 20, 30, tzinfo=UTC), date(2026, 10, 2)),
        (datetime(2026, 10, 2, 15, tzinfo=UTC), date(2026, 10, 1)),  # woke during market hours
        (datetime(2026, 10, 5, 3, tzinfo=UTC), date(2026, 10, 2)),  # Sunday night in New York
        (datetime(2026, 12, 24, 18, 45, tzinfo=UTC), date(2026, 12, 24)),  # early close
        (datetime(2026, 12, 25, 23, tzinfo=UTC), date(2026, 12, 24)),  # Christmas
        (datetime(2027, 3, 26, 23, tzinfo=UTC), date(2027, 3, 25)),  # Good Friday
    ],
)
def test_last_closed_session(now: datetime, expected: date) -> None:
    assert last_closed_session(now) == expected


def test_settle_margin_is_configurable() -> None:
    now = datetime(2026, 10, 2, 20, 5, tzinfo=UTC)
    assert last_closed_session(now, timedelta(0)) == date(2026, 10, 2)
    assert last_closed_session(now, timedelta(minutes=10)) == date(2026, 10, 1)
