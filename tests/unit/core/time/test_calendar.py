from datetime import UTC, date, datetime, time, timedelta

import pytest

from algotrade.core.time.calendar import (
    SPECIAL_CLOSURES,
    close_time,
    early_closes,
    easter,
    holidays,
    is_session,
    last_closed_session,
    last_session_of_month,
    local_deadline,
    monthly_expiry,
    next_session,
    nth_weekday,
    previous_session,
    russell_reconstitution,
    session_offset,
    session_on_or_before,
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
        date(2025, 1, 9),  # special closure: national day of mourning (President Carter)
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


def test_sessions_ending_and_sessions_to() -> None:
    from algotrade.core.time.calendar import sessions_ending, sessions_to  # noqa: PLC0415

    assert sessions_ending(date(2026, 11, 30), 4) == [
        date(2026, 11, 24),
        date(2026, 11, 25),
        date(2026, 11, 27),  # Thanksgiving (26th) skipped
        date(2026, 11, 30),
    ]
    assert sessions_ending(date(2026, 10, 4), 1) == [date(2026, 10, 2)]  # a Sunday
    with pytest.raises(ValueError, match="n must be"):
        sessions_ending(date(2026, 10, 2), 0)
    assert sessions_to(date(2026, 11, 25), date(2026, 11, 30)) == 2
    assert sessions_to(date(2026, 11, 25), date(2026, 11, 25)) == 0
    assert sessions_to(date(2026, 11, 25), date(2026, 11, 1)) == 0


def test_special_closures_are_not_sessions() -> None:
    assert not is_session(date(2025, 1, 9)) and not is_session(date(2018, 12, 5))
    assert is_session(date(2025, 1, 8)) and is_session(date(2025, 1, 10))


def test_local_deadline_follows_daylight_saving_in_los_angeles() -> None:
    assert local_deadline(date(2026, 10, 5), time(23, 0)) == datetime(2026, 10, 6, 6, tzinfo=UTC)
    assert local_deadline(date(2026, 12, 1), time(23, 0)) == datetime(2026, 12, 2, 7, tzinfo=UTC)


def test_martin_luther_king_day_only_from_1998() -> None:
    assert is_session(date(1997, 1, 20))  # the 3rd Monday: the NYSE stayed open
    assert not is_session(date(1998, 1, 19))  # the first MLK Day closure
    assert date(1997, 1, 20) not in holidays(1997)


@pytest.mark.parametrize(
    "closed",
    [
        date(1972, 11, 7),  # presidential election days, closed through 1980
        date(1976, 11, 2),
        date(1980, 11, 4),
        date(1972, 12, 28),  # Truman
        date(1973, 1, 25),  # Johnson
        date(1977, 7, 14),  # New York blackout
        date(1985, 9, 27),  # Hurricane Gloria
        date(1994, 4, 27),  # Nixon
        date(2001, 9, 11),
        date(2001, 9, 12),
        date(2001, 9, 13),
        date(2001, 9, 14),
        date(2004, 6, 11),  # Reagan
        date(2007, 1, 2),  # Ford
        date(2012, 10, 29),  # Hurricane Sandy
        date(2012, 10, 30),
        date(2018, 12, 5),  # G. H. W. Bush
        date(2025, 1, 9),  # Carter
    ],
)
def test_unscheduled_closures_are_not_sessions(closed: date) -> None:
    assert closed in SPECIAL_CLOSURES
    assert not is_session(closed)
    assert is_session(next_session(closed))  # the exchange reopened


def test_closures_do_not_swallow_neighbours() -> None:
    assert is_session(date(2001, 9, 10)) and is_session(date(2001, 9, 17))
    assert is_session(date(2012, 10, 26)) and is_session(date(2012, 10, 31))
    assert is_session(date(1984, 11, 6))  # election day after 1980: open
    assert is_session(date(1973, 11, 6))  # off-year election day: open


def test_christmas_and_independence_day_observed_on_friday_in_the_1980s() -> None:
    assert not is_session(date(1981, 7, 3)) and not is_session(date(1982, 12, 24))
    assert date(1984, 1, 2) in holidays(1984)  # New Year's Sunday -> Monday
    assert is_session(date(1993, 12, 31))  # New Year's Day 1994 was a Saturday


@pytest.mark.parametrize(
    ("year", "count"),
    [
        # weekdays minus holidays: 1990 261 - 8, 2001 261 - 9 - 4 (Sept 11-14), 2012 261 - 9 - 2
        # (Sandy), 2020 262 - 9 (the NYSE's published session counts)
        (1990, 253),
        (2001, 248),
        (2012, 250),
        (2020, 253),
    ],
)
def test_session_counts_match_nyse_history(year: int, count: int) -> None:
    assert len(sessions_between(date(year, 1, 1), date(year, 12, 31))) == count


def test_monthly_expiry_moves_to_the_session_before_a_closed_friday() -> None:
    assert monthly_expiry(2026, 10) == date(2026, 10, 16)
    assert monthly_expiry(2025, 4) == date(2025, 4, 17)  # Good Friday
    assert monthly_expiry(2026, 6) == date(2026, 6, 18)  # Juneteenth


def test_last_session_of_month_skips_weekends_and_holidays() -> None:
    assert last_session_of_month(2026, 3) == date(2026, 3, 31)
    assert last_session_of_month(2023, 12) == date(2023, 12, 29)  # the 31st is a Sunday
    assert last_session_of_month(2024, 3) == date(2024, 3, 28)  # Good Friday on the 29th
    assert session_on_or_before(date(2026, 10, 10)) == date(2026, 10, 9)


@pytest.mark.parametrize(
    ("year", "day"),
    [(2018, date(2018, 6, 22)), (2023, date(2023, 6, 23)), (2024, date(2024, 6, 28)),
     (2025, date(2025, 6, 27))],
)  # fmt: skip
def test_russell_reconstitution_is_the_fourth_friday_of_june(year: int, day: date) -> None:
    assert russell_reconstitution(year) == day


def test_session_offset_is_signed() -> None:
    assert session_offset(date(2026, 11, 25), date(2026, 11, 30)) == 2
    assert session_offset(date(2026, 11, 30), date(2026, 11, 25)) == -2
    assert session_offset(date(2026, 11, 25), date(2026, 11, 25)) == 0
