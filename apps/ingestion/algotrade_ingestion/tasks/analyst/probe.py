"""``analyst/vendor_access``: which analyst endpoints each free vendor key may call (ADR 0068).

``algotrade-ingest run analyst-probe`` makes ONE request per endpoint of FMP and Finnhub (the
probe sources' ``endpoints``, for AAPL), classifies each answer ALLOWED / DENIED / LIMITED
(``framework/access.py``) and stores one row per (vendor, endpoint). A vendor whose key is not set
is skipped and counted, never an error; an endpoint whose answer is no verdict (an outage, a 404)
fails its item (the run is PARTIAL) and keeps the verdict stored before. FMP's calls count against
``[fmp] daily_budget`` (``budget.py``); an endpoint that would pass it is not asked
(``OVER_BUDGET``).

In NO workflow: the owner runs it by hand when a plan or a key changes. The later analyst tasks
read this table to know what they may ask, and a call they make that the table says DENIED is a
bug, not a retry.
"""

from collections.abc import Mapping
from datetime import date
from typing import Any

import pandas as pd

from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.analyst.budget import NOT_MADE, PREFIX, fmp_calls_today
from algotrade_ingestion.tasks.framework.run import IngestRun, TaskContext
from algotrade_sources.framework.base import ProbeSource

TASK = "analyst-probe"
TABLE = "analyst/vendor_access"
COLUMNS = ["endpoint", "status", "http_code", "rows", "note", "checked_ts"]
SOURCES = ("fmp_probe", "finnhub_probe")  # source names in the registry, each a vendor


def run(ctx: TaskContext, params: Mapping[str, Any]) -> RunRecord:
    """The registry's entry: the ``session`` parameter (a date) is required."""
    session = params.get("session")
    if not isinstance(session, date):
        raise ValueError("task parameter 'session' (a date) is required")
    return probe_analyst_access(ctx, session)


def probe_analyst_access(ctx: TaskContext, session: date) -> RunRecord:
    with IngestRun(ctx, TASK, session) as run:
        skipped = {}
        asked = 0
        answered: set[tuple[str, str]] = set()
        for name in SOURCES:
            source = ctx.sources.get(name)
            if not isinstance(source, ProbeSource):
                skipped[name] = ctx.unavailable.get(name, f"{name} is not configured")
                continue
            asked += 1
            rows = _probe(run, source)
            if not rows.empty:
                run.stage(TABLE, source.name, rows, source.name)
                answered |= {(source.name, str(e)) for e in rows["endpoint"]}
        if skipped:
            run.stats["skipped"] = skipped
        if not asked:
            run.failed("no analyst vendor is configured: " + "; ".join(skipped.values()))
            return run.record
        run.stats["carried"] = _carry_forward(run, answered)
        run.publish(TABLE, sort_by="endpoint")
        run.stats.update(
            fmp_calls_today=fmp_calls_today(run),
            fmp_daily_budget=ctx.settings.fmp_daily_budget,
            licence={"fmp": ctx.settings.fmp_licence, "finnhub": ctx.settings.finnhub_licence},
            counts=run.counts(),
        )
    return run.record


def _carry_forward(run: IngestRun, answered: set[tuple[str, str]]) -> int:
    """Re-stage the verdicts of the latest earlier session for every (vendor, endpoint) this run
    got no verdict for (a vendor with no key, a 5xx, an endpoint over budget) and this session
    does not hold yet, keeping their ``checked_ts``: runs merge only within one session's
    partition, so without this a later session's partition would forget them. -> rows carried."""
    earlier = [d for d in run.reader.dates(TABLE) if d < run.session]
    if not earlier:
        return 0
    previous = run.reader.table(TABLE, max(earlier))
    if previous is None:
        return 0
    held = run.reader.table(TABLE, run.session)
    if held is not None:
        answered = answered | set(zip(held["source"], held["endpoint"], strict=True))
    keys = zip(previous["source"], previous["endpoint"], strict=True)
    missing = previous[[k not in answered for k in keys]]
    for vendor, rows in missing.groupby("source"):
        run.stage(TABLE, f"{vendor}:carried", rows[COLUMNS].reset_index(drop=True), str(vendor))
    return len(missing)


def _probe(run: IngestRun, source: ProbeSource) -> pd.DataFrame:
    """One row per endpoint that gave a verdict, as the vendor's ``source`` stages it."""
    rows = []
    budget = run.ctx.settings.fmp_daily_budget
    for endpoint in source.endpoints:
        key = f"{source.name}:{endpoint}"
        if key.startswith(PREFIX) and fmp_calls_today(run) >= budget:
            run.record_item(key, f"{NOT_MADE}: [fmp] daily_budget {budget} is spent")
            run.partial(f"{key} not asked: the FMP daily budget is spent")
            continue
        outcome = _one(run, source, endpoint, key)
        if outcome is not None:
            rows.append(outcome)
    return pd.DataFrame(rows, columns=COLUMNS)


def _one(run: IngestRun, source: ProbeSource, endpoint: str, key: str) -> dict[str, object] | None:
    found: dict[str, object] = {}

    def ask() -> str:
        verdict = source.probe(endpoint)
        found.update(
            endpoint=endpoint,
            status=verdict.access.value,
            http_code=verdict.http_code,
            rows=verdict.rows,
            note=verdict.note,
            checked_ts=pd.Timestamp(run.clock()),
        )
        return verdict.access.value

    run.attempt(key, ask)
    return found or None
