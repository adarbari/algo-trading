"""FINRA Reg SHO daily short-sale volume -> ``events/short_volume`` (EB D9): one partition per
trade date.

The window is the sessions of ``start..end``; the nightly default is the last ``[finra]
short_volume_lookback_days`` calendar days not stored yet (the file is posted by 18:00 New York;
a date not published yet is ``NO_DATA`` and asked again). The API serves a rolling year, so a
backfill (``algotrade-ingest run short-volume --from D``) reaches back at most that far; older
days exist only as ``cdn.finra.org`` files, which the finra.org website terms bar from machine
learning and from building a database, so they are not read. ``known_from`` is the session after
the trade date (``schedule.py``). The table is ``no_ml`` (see ``short_interest``).
"""

from collections.abc import Mapping
from datetime import date, timedelta
from typing import Any

import pandas as pd

from algotrade.core.time.calendar import sessions_between
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.framework.run import TaskContext
from algotrade_ingestion.tasks.shorting import schedule
from algotrade_ingestion.tasks.shorting.daily import store_days

TASK = "short-volume"
TABLE = "events/short_volume"
SOURCE = "finra_short_volume"


def known(trade_date: date) -> dict[str, date]:
    """The column the schedule adds to a trade date's rows."""
    return {"known_from": schedule.short_volume_known_from(trade_date)}


def one_row_per_instrument(rows: pd.DataFrame) -> pd.DataFrame:
    """Rows of tickers that resolved to one id summed into one row (volumes and facilities):
    FINRA lists ``TpC`` beside ``TPC``, and the resolver reads both as ``TPC``. The vendor sums
    facilities per exact ticker; the table key is the id, so the sum is finished here."""
    counts = ["short_volume", "short_exempt_volume", "total_volume", "facilities"]
    if not rows.duplicated(["instrument_id", "ts"]).any():
        return rows
    summed = rows.groupby(["instrument_id", "ts"], sort=True)[counts].sum(min_count=1)
    return summed.astype("Int64").reset_index()[list(rows.columns)]


def run(ctx: TaskContext, params: Mapping[str, Any]) -> RunRecord:
    """The registry's entry: ``session`` is required; ``start`` / ``end`` default to the nightly
    window; ``force`` refetches stored dates."""
    session = params.get("session")
    if not isinstance(session, date):
        raise ValueError("task parameter 'session' (a date) is required")
    end = params.get("end") or session
    days = ctx.settings.finra_short_volume_lookback_days
    start = params.get("start") or end - timedelta(days - 1)
    return store_days(
        ctx,
        TASK,
        TABLE,
        ctx.sources[SOURCE],
        known,
        sessions_between(start, end),
        session,
        bool(params.get("force")),
        one_row_per_instrument,
    )
