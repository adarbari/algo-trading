"""``instruments/delisted_tickers``: the US names Massive lists as inactive, with the day each
stopped trading (ADR 0087, survivorship-free listing history).

``algotrade-ingest run delisted-tickers`` pulls Massive's inactive ticker list (about 24 pages
of 1000 at the free tier's 12.5 s a request, so five minutes; ``MassiveTickers``, request key
``inactive``) and writes it as a full snapshot for the session. In NO workflow: the table is
stored first and merged into ``instruments/listing_history`` in a later PR. ``end_date`` is
identity (the id merge and the data-quality report read it through ``data.listings.delisted``),
never a feature.

Acceptance: a pull of fewer than ``[quality] min_delisted_tickers`` rows is a broken pull and
FAILS before anything is written; so does an unanswered page (the list is paged in one fetch, so
one lost page loses the pull and the run is simply repeated).
"""

from datetime import date

import pandas as pd

from algotrade.data.listings.delisted import TABLE
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.framework.run import IngestRun, TaskContext
from algotrade_sources.framework.base import FetchRequest, Source

TASK = "delisted-tickers"
KEY = "inactive"  # the request key of ``MassiveTickers``' delisted list
NO_TYPE = "NULL"  # the label of a row without a security type in the stats


def _counts(values: pd.Series) -> dict[str, int]:
    """Rows per value, a missing value counted as ``NO_TYPE``."""
    return {str(k): int(v) for k, v in values.fillna(NO_TYPE).value_counts().sort_index().items()}


def ingest_delisted_tickers(ctx: TaskContext, source: Source, session: date) -> RunRecord:
    with IngestRun(ctx, TASK, session) as run:
        got = run.fetch_frame(
            source,
            FetchRequest(KEY, session_date=session),
            TABLE,
            "Massive's inactive list held no usable ticker",
        )
        if got is None:
            return run.record
        rows, notes = got
        floor = ctx.settings.min_delisted_tickers
        if len(rows) < floor:
            run.failed(f"{len(rows)} delisted tickers, expected at least {floor}")
            return run.record
        run.write(TABLE, rows, source.name)
        years = pd.to_datetime(rows["end_date"]).dt.year
        run.stats.update(
            rows=len(rows),
            by_security_type=_counts(rows["security_type"]),
            with_cik=int(rows["cik"].notna().sum()),
            with_figi=int(rows["figi"].notna().sum()),
            without_end_date=int(rows["end_date"].isna().sum()),
            by_year={
                str(y): int(n)
                for y, n in years.dropna().astype(int).value_counts().sort_index().items()
            },
            **notes,
        )
    return run.record
