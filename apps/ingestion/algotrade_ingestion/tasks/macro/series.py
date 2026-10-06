"""The ``macro`` task: economic series and index levels -> ``macro/series`` (ADR 0048).

Every enabled series of the registry (``config/site/macro.toml``) is fetched whole (every
vintage ALFRED has for ``pit = "alfred"``; the current values for ``pit = "lag"``, which FRED
serves in one plain request, never a real-time period; a published file entire), given its
vintage by the registry's ``pit`` rule and compared with what is stored (``plan.py``); only
the rows the table lacks are written, as the run's session partition (the table merges
runs on its key, so a rerun on unchanged data writes nothing). Values are stored as published:
``transform`` (``yoy``, ``diff``) is how the macro feature group reads a series, not an
ingestion step.

Per series, an item of the run: ``OK`` (rows added), ``UNCHANGED``, ``NO_DATA`` (the source has
no such series), ``NOT_DUE`` (a published file fetched less than ``REFETCH_DAYS`` ago; FRED
series are fetched every run), ``SKIPPED`` with the reason (the source is disabled, or its
credential, ``ALGOTRADE_FRED_API_KEY``, is missing) or a ``FETCH_ERROR``. A skipped series is
never an error: ``stats["skipped_series"]`` lists them. ``stats["vintages"]`` is each series'
stored vintage count after the run, which ``check_macro`` compares with the table later.

``since`` bounds the observations stored (a backfill from that date; default all of them) and,
like ``only`` (the keys to run), fetches published files whatever their cadence. An ALFRED
series is always fetched whole: its first vintage, which dates what ALFRED's archive predates
(``plan.py``), is only known from every observation, so ``since`` drops rows afterwards.

The run has a time budget (``[macro] run_budget_s``): once spent, the series not yet fetched
are recorded as skipped (``over_budget``) and the run is PARTIAL, so a FRED outage cannot hold
the nightly up; they are still graded by ``check_macro`` (they were fetchable).
"""

from collections.abc import Mapping, Sequence
from datetime import date
from functools import partial

import pandas as pd

from algotrade.config.site.macro import MacroSeries, MacroSettings
from algotrade.data.macro.series import TABLE as SERIES_TABLE
from algotrade.data.macro.series import stored_vintages
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.framework.run import (
    IngestRun,
    NoResponseError,
    TaskContext,
    finished_runs,
    status_label,
)
from algotrade_ingestion.tasks.macro.plan import KEY, rows_to_write, vintage_count, vintage_rows
from algotrade_sources.framework.base import Source
from algotrade_sources.framework.series import SERIES_FRAME, SeriesRequest

TASK = "macro"
TABLE = SERIES_TABLE  # the table this task owns (architecture/tables.toml)
PUBLISHED = "published"
FETCHED = ("OK", "UNCHANGED")  # item statuses of a series fetched in that run
# A published file is read again after its cadence, but at most a week: a monthly file's new
# release is picked up within a week (they refetch by cadence until the weekly workflow lands).
MAX_REFETCH_DAYS = 7


def refetch_days(spec: MacroSeries) -> int:
    return min(spec.cadence_days, MAX_REFETCH_DAYS)


def _last_fetched(ctx: TaskContext) -> dict[str, date]:
    """Series key -> the session of the last run that fetched it."""
    last: dict[str, date] = {}
    for record in finished_runs(ctx.writer, TASK):
        for key, status in record.items.items():
            if status_label(status) in FETCHED:
                last[key] = max(record.session_date, last.get(key, record.session_date))
    return last


def _request(spec: MacroSeries, session: date, since: date | None) -> SeriesRequest:
    return SeriesRequest(
        spec.key,
        session_date=session,
        code=spec.vendor_code,
        url=spec.url,
        date_column=spec.date_column,
        value_column=spec.value_column,
        parser=spec.parser,
        vintages=spec.pit == "alfred",  # a lag series: FRED's current values, one plain request
        start=None if spec.pit == "alfred" else since,
    )


def _not_due(spec: MacroSeries, session: date, last: Mapping[str, date]) -> bool:
    fetched = last.get(spec.key)
    return (
        spec.source == PUBLISHED
        and fetched is not None
        and (session - fetched).days < refetch_days(spec)
    )


def _fetch_one(
    run: IngestRun,
    spec: MacroSeries,
    source: Source,
    stored: pd.DataFrame,
    since: date | None,
    counts: dict[str, int],
) -> str:
    """Fetch, apply the vintage rule, write what is new -> the item status; ``counts`` gets the
    series' stored vintages once this is written."""
    counts[spec.key] = len(stored)
    try:
        normalized = run.fetch(source, _request(spec, run.session, since))
    except NoResponseError:
        return "NO_DATA"
    fetched = normalized.parsed[SERIES_FRAME] if normalized else None
    if fetched is None or fetched.empty:
        return "NO_DATA"
    target = vintage_rows(spec, fetched)
    if since is not None:
        target = target[target["obs_date"] >= since]
    new = rows_to_write(target, stored, run.session)
    if new.empty:
        return "UNCHANGED"
    run.stage(TABLE, spec.key, new, source.name)
    counts[spec.key] = vintage_count(stored[KEY], new[KEY])
    return f"OK: {len(new)} rows"


def ingest_macro(
    ctx: TaskContext,
    registry: MacroSettings,
    session: date,
    only: Sequence[str] = (),
    since: date | None = None,
) -> RunRecord:
    """Store the new vintages of the registry's series (``only``: just these keys)."""
    chosen = [registry.by_key(k) for k in only] or list(registry.series)
    forced = bool(only) or since is not None
    last = _last_fetched(ctx)
    counts: dict[str, int] = {}
    skipped: dict[str, str] = {}
    over_budget: list[str] = []
    started = ctx.clock()
    with IngestRun(ctx, TASK, session) as run:
        held = stored_vintages(run.reader, [s.instrument_id for s in chosen])
        by_id = {str(i): rows.reset_index(drop=True) for i, rows in held.groupby("instrument_id")}
        for spec in chosen:
            stored = by_id.get(spec.instrument_id, held.iloc[0:0])
            source = ctx.sources.get(spec.source)
            if source is None:
                skipped[spec.key] = ctx.unavailable.get(spec.source, f"{spec.source} is not built")
                run.record_item(spec.key, f"SKIPPED: {skipped[spec.key]}")
            elif not forced and _not_due(spec, session, last):
                run.record_item(spec.key, "NOT_DUE")
            elif (ctx.clock() - started).total_seconds() > registry.run_budget_s:
                over_budget.append(spec.key)
                run.record_item(spec.key, f"SKIPPED: run budget of {registry.run_budget_s}s spent")
            else:
                run.attempt(spec.key, partial(_fetch_one, run, spec, source, stored, since, counts))
            run.checkpoint()
        if over_budget:
            run.partial(
                f"run budget of {registry.run_budget_s}s spent: {len(over_budget)} not fetched"
            )
        written = run.publish(TABLE)
        run.stats.update(
            series=len(chosen),
            rows=written,
            since=since.isoformat() if since else None,
            skipped_series=skipped,
            over_budget=over_budget,
            vintages={**_stored_counts(by_id, chosen), **counts},
            items=run.counts(),
        )
    return run.record


def _stored_counts(
    by_id: Mapping[str, pd.DataFrame], chosen: Sequence[MacroSeries]
) -> dict[str, int]:
    """The vintages already stored per series (what a series not fetched this run still holds)."""
    return {s.key: len(by_id[s.instrument_id]) for s in chosen if s.instrument_id in by_id}
