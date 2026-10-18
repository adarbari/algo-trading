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
