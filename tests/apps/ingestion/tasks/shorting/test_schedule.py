"""When FINRA's data counts as known (``known_from``): the 7th business day after settlement,
checked against the dates FINRA's schedule page lists, then the session after it."""

from datetime import date

import pytest

from algotrade_ingestion.tasks.shorting import schedule


@pytest.mark.parametrize(
    ("settlement", "published"),
    [  # the dates FINRA's schedule page lists
        (date(2026, 9, 30), date(2026, 10, 9)),
        (date(2026, 10, 15), date(2026, 10, 26)),
        (date(2026, 10, 30), date(2026, 11, 10)),
    ],
)
def test_publication_is_the_seventh_business_day(settlement: date, published: date) -> None:
    assert schedule.publication_date(settlement) == published
    assert schedule.short_interest_known_from(settlement) > published  # never the day itself


def test_known_from_is_the_session_after() -> None:
    assert schedule.short_interest_known_from(date(2026, 9, 30)) == date(2026, 10, 12)  # Fri -> Mon
    assert schedule.short_volume_known_from(date(2026, 10, 16)) == date(2026, 10, 19)  # Fri -> Mon
    assert schedule.short_volume_known_from(date(2026, 10, 14)) == date(2026, 10, 15)


@pytest.mark.parametrize(
    ("settlement", "published"),
    [  # FINRA's schedule page: across Thanksgiving, MLK Day and Presidents Day
        (date(2025, 11, 14), date(2025, 11, 25)),
        (date(2025, 12, 15), date(2025, 12, 24)),
        (date(2026, 1, 15), date(2026, 1, 27)),
        (date(2026, 2, 13), date(2026, 2, 25)),
        (date(2026, 10, 30), date(2026, 11, 10)),
        (date(2026, 11, 13), date(2026, 11, 24)),
    ],
)
def test_published_dates_across_market_holidays(settlement: date, published: date) -> None:
    """The exchange calendar reproduces every published date in the schedule that crosses a
    holiday. None of the published pairs spans Columbus or Veterans Day (FINRA lists none), so
    those two are untested: a row would only be early by a day, and the fetch floor
    (``known_from`` >= the session after the fetch) covers a backfill."""
    assert schedule.publication_date(settlement) == published
