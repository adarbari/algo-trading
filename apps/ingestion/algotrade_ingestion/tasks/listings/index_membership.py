"""``instruments/index_membership``: the S&P 500 membership intervals since 1996 (edges ED6b-3,
ADR 0013's rule over history).

``algotrade-ingest run index-membership`` pulls fja05680/sp500's ``sp500_ticker_start_end.csv``
(one request, MIT licence) and writes it as a full snapshot for the session. In NO workflow until
the owner has run it on the real file and read the result. Rows are keyed by the ticker the
index used at the time, not by an id: ``data.listings.universe_asof`` joins them to the listing
alive on the day.

Acceptance: the intervals open on the session must number ``EXPECTED_MEMBERS`` (the index holds
about 500 names, a few more with dual share classes); a file that lists far fewer or more is a
broken pull and nothing is written.
"""

from datetime import date

import pandas as pd

from algotrade.data.listings.membership import TABLE, members_on
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.framework.run import IngestRun, NoResponseError, TaskContext
from algotrade_sources.framework.base import FetchRequest, Source

TASK = "index-membership"
KEY = "membership"
EXPECTED_MEMBERS = (450, 550)


def ingest_index_membership(
    ctx: TaskContext,
    source: Source,
    session: date,
    expected_members: tuple[int, int] = EXPECTED_MEMBERS,
) -> RunRecord:
    with IngestRun(ctx, TASK, session) as run:
        try:
            normalized = run.fetch(source, FetchRequest(KEY, session_date=session))
        except NoResponseError as error:
            run.failed(str(error))
            return run.record
        rows = None if normalized is None else normalized.parsed.get(TABLE)
        if rows is None or rows.empty:
            run.failed("the membership file held no usable interval")
            return run.record
        current = len(members_on(rows, session))
        low, high = expected_members
        if not low <= current <= high:
            run.failed(f"{current} tickers are members on {session}, expected {low}..{high}")
            return run.record
        rows = rows.copy()
        rows.insert(0, "ts", pd.Timestamp(session, tz="UTC"))
        rows = rows.astype(object).where(rows.notna(), None)
        run.write(TABLE, rows, source.name)
        run.stats.update(
            intervals=len(rows),
            tickers=int(rows["ticker"].nunique()),
            members_on_session=current,
            first_start=str(min(rows["start_date"])),
            **(normalized.notes if normalized is not None else {}),
        )
    return run.record
