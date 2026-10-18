"""FINRA short interest -> ``events/short_interest`` (EB D9): one partition per settlement date.

Settlement dates are the 15th of the month (the session before it when it is not one) and the
last session of the month; FINRA publishes each on the 7th business day after, and the source
``schedule.py`` gives ``known_from``. The nightly window is the settlement dates
of the last ``[finra] short_interest_lookback_days`` calendar days not stored yet (a date not
published yet is ``NO_DATA`` and asked again the next night); a backfill is
``algotrade-ingest run short-interest --from 2017-12-29`` (the API's first partition), resumable
because a stored date is skipped. The table is ``no_ml``: no learned scorer reads it
(``architecture/tables.toml``, ``tests/architecture/data/test_no_ml_tables.py``).
"""

from collections.abc import Mapping
from datetime import date, timedelta
from typing import Any

from algotrade.core.time.calendar import last_session_of_month, session_on_or_before
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.framework.run import TaskContext
from algotrade_ingestion.tasks.shorting import schedule
from algotrade_ingestion.tasks.shorting.daily import store_days

TASK = "short-interest"
TABLE = "events/short_interest"
SOURCE = "finra_short_interest"


def settlement_dates(start: date, end: date) -> list[date]:
    """The settlement dates in ``start..end``, oldest first."""
    found: list[date] = []
    year, month = start.year, start.month
    while date(year, month, 1) <= end:
        found += [session_on_or_before(date(year, month, 15)), last_session_of_month(year, month)]
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return [d for d in found if start <= d <= end]


def known(settlement: date) -> dict[str, date]:
    """The columns the schedule adds to a settlement date's rows."""
    return {
        "published": schedule.publication_date(settlement),
        "known_from": schedule.short_interest_known_from(settlement),
    }


def run(ctx: TaskContext, params: Mapping[str, Any]) -> RunRecord:
    """The registry's entry: ``session`` is required; ``start`` / ``end`` default to the nightly
    window; ``force`` refetches stored dates."""
    session = params.get("session")
    if not isinstance(session, date):
        raise ValueError("task parameter 'session' (a date) is required")
    end = params.get("end") or session
    days = ctx.settings.finra_short_interest_lookback_days
    start = params.get("start") or end - timedelta(days)
    return store_days(
        ctx,
        TASK,
        TABLE,
        ctx.sources[SOURCE],
        known,
        settlement_dates(start, end),
        session,
        bool(params.get("force")),
    )
