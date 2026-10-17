"""``analyst/estimate_snapshots``: our own point-in-time history of analyst data (ADR 0068).

Both vendors serve only today's value and restate their history, so the only history that is
point in time is the one we store ourselves: each night's fetch is kept as rows that a later night
never replaces (the partition is the session the fetch is for; ``ts`` the fetch instant;
``knowledge_ts`` the publish instant of the run, never a vendor date). Per run:

- the names are the S&P 500 members of the reference snapshot plus the event-study scope list
  (``config/site/events/scope.toml``) and the stocks its funds track, as ``SymbolResolver`` knows
  them; what the probe stored in ``analyst/vendor_access`` as DENIED is not asked (a kind with no
  verdict is);
- FMP: three calls a name (price-target consensus, grades consensus, annual estimates), as many
  names as ``[fmp] daily_budget`` still allows tonight (``budget.py``; the probe's calls and every
  earlier run of the day count). A name is due when never fetched or past its slot in ``[fmp]
  refresh_days`` (``due_keys``: new names first, then the stalest), so every name is refreshed on
  that cadence as far as the budget goes. A name FMP refuses (402, not on the free plan) is
  ``NOT_COVERED`` after one call and is asked again only after four refresh windows. FMP gates by
  endpoint, so a name any of whose calls answered is never held (a refused later kind just has no
  rows); the free
  plan covers few names, so most nights spend their budget on the covered large caps;
- Finnhub: one call a name (recommendation trend), at most ``[finnhub] per_night`` names, due on
  the same cadence, stalest first;
- which names a night asked is the run record's items (``fmp:SYM:price_target``,
  ``finnhub:SYM``...), read back by the next night: the rotation keeps no state of its own. An
  empty answer is ``EMPTY``, a refusal ``NOT_COVERED`` (neither fails the run); an error is a
  ``FETCH_ERROR`` item and the name is asked again next night;
- every attempt of a vendor for a name also stores one ``kind = "coverage"`` row (``period``
  ``current``, ``status`` OK / EMPTY / NOT_COVERED / FAILED, ``ts`` the attempt), so a feature can
  tell a name the vendor refuses from one not yet fetched or one whose call failed, from the
  store alone. A refused name has that marker and no estimate rows.

The run has a time budget (``[fmp] run_budget_s``, both vendors' calls): once spent no further call
is made and the names not yet asked are ``OVER_BUDGET`` items (the next night continues, stalest
first), so a stalling vendor cannot hold the ingest lock. A hand run for a session before the last
closed one is refused: the vendors serve only today's values, which would land in an old partition.

Rows are staged per item and published as one partition (atomic, ADR 0022); the step is optional,
so a vendor outage only warns. Features over the history come later (track E): nothing reads the
table yet, and its rows carry the vendors' ``licence = "personal"`` (``stats["licence"]``).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd

from algotrade.core.time.calendar import last_closed_session
from algotrade.data.reference import instruments
from algotrade.services.events.scope import LIST, REFERENCE, scoped_instruments
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.analyst.budget import NOT_MADE, PREFIX, fmp_calls_today
from algotrade_ingestion.tasks.framework import source_guards
from algotrade_ingestion.tasks.framework.refresh import due_keys
from algotrade_ingestion.tasks.framework.run import (
    PUBLISHED,
    IngestRun,
    TaskContext,
    status_label,
)
from algotrade_sources.framework.base import FetchRequest, Source

TASK = "analyst-snapshot"
TABLE = "analyst/estimate_snapshots"
ACCESS = "analyst/vendor_access"
SOURCES = source_guards.ANALYST_SOURCES
NOT_COVERED, EMPTY, OK, FAILED = "NOT_COVERED", "EMPTY", "OK", "FAILED"
COVERAGE = "coverage"  # the snapshot ``kind`` of an attempt's marker row
PLAN_REFUSAL = 402  # FMP: "Premium Query Parameter", a symbol the free plan does not serve
RETRY_WINDOWS = 4  # a refused name waits this many refresh windows before it is asked again
CHECKPOINT_EVERY = 25
FINNHUB = "finnhub:"

# FMP calls of a name in order: (item kind, source name, probe endpoint, snapshot kind).
FMP_CALLS = (
    ("price_target", "fmp_targets", "price_targets", "price_target"),
    ("grades", "fmp_ratings", "ratings_summary", "grades"),
    ("estimates", "fmp_estimates", "estimates_annual", "estimates_annual"),
)
RECOMMENDATION = ("recommendation", "finnhub_recommendations", "recommendation")


@dataclass(frozen=True)
class Name:
    instrument_id: str
    symbol: str


def run(ctx: TaskContext, params: Mapping[str, Any]) -> RunRecord:
    """The registry's entry: ``session`` (a date) is required; ``limit`` caps the FMP names."""
    session = params.get("session")
    if not isinstance(session, date):
        raise ValueError("task parameter 'session' (a date) is required")
    return snapshot_analyst(ctx, session, params.get("limit"))


def names_for(run: IngestRun, ctx: TaskContext) -> list[Name]:
    """The S&P 500 members of the session's reference plus the scope list's names, by symbol."""
    reference = instruments(run.reader, run.session)
    members = reference["in_sp500"] if "in_sp500" in reference.columns else pd.Series(False)
    found = {
        str(i): str(s)
        for i, s, m in zip(reference["instrument_id"], reference["symbol"], members, strict=False)
        if pd.notna(m) and bool(m) and isinstance(s, str) and s
    }
    scope = scoped_instruments(run.reader, ctx.configs, run.session, reasons=(LIST, REFERENCE))
    found.update({n.instrument_id: n.symbol for n in scope.names if n.symbol})
    return sorted((Name(i, s) for i, s in found.items()), key=lambda n: (n.symbol, n.instrument_id))


def denied(run: IngestRun) -> set[tuple[str, str]]:
    """(vendor, endpoint) the probe's newest verdicts say are DENIED; none stored, none denied."""
    days = run.reader.dates(ACCESS)
    earlier = [d for d in days if d <= run.session]
    frame = run.reader.table(ACCESS, max(earlier)) if earlier else None
    if frame is None:
        return set()
    rows = frame[frame["status"] == "DENIED"]
    return set(zip(rows["source"], rows["endpoint"], strict=True))


def history(run: IngestRun) -> tuple[dict[str, date], dict[str, date], dict[str, date]]:
    """From the earlier published runs' items: the session each symbol's FMP data was last
    answered (``fmp``, any of its calls: the probe may deny some kinds), refused (``refused``)
    and its Finnhub call answered (``finnhub``). Dated by the run's session, the day the
    rotation counts in (a nightly starts after midnight UTC, so its start date is a day late)."""
    answered: dict[str, date] = {}
    refused_on: dict[str, date] = {}
    finnhub: dict[str, date] = {}
    for record in sorted(run.writer.runs_for(TASK), key=lambda r: r.started_at):
        if record.run_id == run.run_id or record.status not in PUBLISHED:
            continue
        day = record.session_date
        labels: dict[str, list[str]] = {}  # symbol -> its FMP calls' labels in this run
        for key, status in record.items.items():
            label = status_label(status)
            if key.startswith(PREFIX):
                labels.setdefault(key.split(":")[1], []).append(label)
            elif key.startswith(FINNHUB) and label in (OK, EMPTY):
                finnhub[key[len(FINNHUB) :]] = day
        for symbol, calls in labels.items():  # FMP gates by endpoint: held only if none answered
            if OK in calls or EMPTY in calls:
                answered[symbol] = day
                refused_on.pop(symbol, None)
            elif NOT_COVERED in calls:
                refused_on[symbol] = day
    return answered, refused_on, finnhub


def estimate_rows(frame: pd.DataFrame, instrument_id: str) -> pd.DataFrame:
    """FMP annual estimates -> snapshot rows: ``period`` the fiscal year end, ISO date."""
    out = frame.drop(columns=["symbol", "period"]).copy()
    out["period"] = out.pop("fiscal_date").dt.strftime("%Y-%m-%d")
    return out.assign(instrument_id=instrument_id, kind="estimates_annual")


def counts_rows(frame: pd.DataFrame, instrument_id: str, kind: str, period: str) -> pd.DataFrame:
    """Grades or recommendation counts -> snapshot rows (a recommendation month ``period``)."""
    out = frame.drop(columns=["symbol"]).copy()
    if "period" in out.columns:
        out["period"] = out["period"].dt.strftime("%Y-%m-%d")
    else:
        out["period"] = period
    return out.assign(instrument_id=instrument_id, kind=kind)


def target_rows(frame: pd.DataFrame, instrument_id: str) -> pd.DataFrame:
    return frame.drop(columns=["symbol"]).assign(
        instrument_id=instrument_id, kind="price_target", period="current"
    )


def build_rows(kind: str, parsed: pd.DataFrame, instrument_id: str) -> pd.DataFrame:
    """One parsed vendor frame -> snapshot rows of ``kind`` (``ts`` is set by the caller); a
    ``period`` the vendor repeats keeps its last row (the table key is unique per item)."""
    if kind == "price_target":
        rows = target_rows(parsed, instrument_id)
    elif kind == "estimates_annual":
        rows = estimate_rows(parsed, instrument_id)
    else:
        rows = counts_rows(parsed, instrument_id, kind, "current")
    return rows.drop_duplicates("period", keep="last").reset_index(drop=True)


def coverage_status(labels: Sequence[str]) -> str:
    """One vendor attempt for a name -> its marker ``status``, from its calls' item labels. FMP
    gates by endpoint, so a name any call answered is ``OK`` (rows) or ``EMPTY``, whatever else
    was refused; only a name nothing answered is ``NOT_COVERED`` (the plan refuses it) or, when
    an error is all there is, ``FAILED`` (the name is unknown, not uncovered)."""
    if OK in labels:
        return OK
    if EMPTY in labels:
        return EMPTY
    return NOT_COVERED if NOT_COVERED in labels else FAILED


def mark_coverage(run: IngestRun, name: Name, vendor: str, labels: Sequence[str]) -> None:
    """Stage the coverage marker of one (name, vendor) attempt; none when no call was made."""
    if not labels:
        return
    row = {
        "instrument_id": name.instrument_id,
        "ts": pd.Timestamp(run.clock()),
        "kind": COVERAGE,
        "period": "current",
        "status": coverage_status(labels),
    }
    run.stage(TABLE, f"{COVERAGE}:{vendor}:{name.symbol}", pd.DataFrame([row]), vendor)


def snapshot_analyst(ctx: TaskContext, session: date, limit: Any = None) -> RunRecord:
    latest = last_closed_session(ctx.clock(), timedelta(0))
    if session < latest:
        raise ValueError(
            f"session {session} is before the last closed session {latest}: the vendors serve "
            "only today's values, so a run for it would store them in an old partition"
        )
    with IngestRun(ctx, TASK, session) as run:
        started = run.clock()
        sources = {n: s for n in SOURCES if isinstance((s := ctx.sources.get(n)), Source)}
        fmp_ready = all(n in sources for _, n, _, _ in FMP_CALLS)
        finnhub_ready = RECOMMENDATION[1] in sources
        if not (fmp_ready or finnhub_ready):
            run.failed("no analyst vendor is configured: " + _why_not(ctx))
            return run.record
        names = names_for(run, ctx)
        no = denied(run)
        answered, refused_on, finnhub_on = history(run)
        stats: dict[str, Any] = {
            "candidates": len(names),
            "denied": sorted("/".join(d) for d in no),
        }
        if fmp_ready:
            stats["fmp"] = _fmp(run, sources, names, no, (answered, refused_on), limit, started)
        else:
            stats["fmp"] = {"skipped": _why_not(ctx, "fmp")}
        if finnhub_ready:
            stats["finnhub"] = _finnhub(
                run, sources[RECOMMENDATION[1]], names, no, finnhub_on, started
            )
        else:
            stats["finnhub"] = {"skipped": _why_not(ctx, "finnhub")}
        run.stats.update(
            stats,
            licence={"fmp": ctx.settings.fmp_licence, "finnhub": ctx.settings.finnhub_licence},
        )
        run.stats.update(rows=run.publish(TABLE), counts=run.counts())
    return run.record


def _why_not(ctx: TaskContext, vendor: str = "") -> str:
    why = [v for k, v in ctx.unavailable.items() if vendor in k and k in SOURCES]
    return "; ".join(why) or "the sources are not configured"


def _fmp(
    run: IngestRun,
    sources: Mapping[str, Source],
    names: Sequence[Name],
    no: set[tuple[str, str]],
    state: tuple[dict[str, date], dict[str, date]],
    limit: Any,
    started: datetime,
) -> dict[str, Any]:
    answered, refused_on = state
    settings = run.ctx.settings
    window = settings.fmp_refresh_days
    calls = [c for c in FMP_CALLS if ("fmp", c[2]) not in no]
    spent = fmp_calls_today(run)
    left = max(settings.fmp_daily_budget - spent, 0)
    by_symbol = {n.symbol: n for n in names}
    holding = {
        s
        for s, day in refused_on.items()
        if run.session - day < timedelta(days=RETRY_WINDOWS * window)
    }
    due = due_keys([s for s in by_symbol if s not in holding], answered, run.session, window)
    capacity = left // max(len(calls), 1) if calls else 0
    take = due[: capacity if limit is None else min(capacity, int(limit))]
    fetched = refused_n = 0
    for symbol in take:
        name = by_symbol[symbol]
        labels: list[str] = []
        unmade = False
        for item, source_name, _, kind in calls:
            key = f"{PREFIX}{symbol}:{item}"
            if out_of_time(run, started):
                run.record_item(key, f"{NOT_MADE}: [fmp] run_budget_s is spent")
                unmade = True
                break
            if left <= 0:
                run.record_item(key, f"{NOT_MADE}: [fmp] daily_budget is spent")
                unmade = True
                break
            left -= 1
            status = _ask(run, sources[source_name], key, name, kind, "fmp")
            labels.append(status)
            if status == NOT_COVERED and OK not in labels and EMPTY not in labels:
                break  # nothing answered yet: the plan does not serve this name, spare the rest
        if coverage_status(labels) == NOT_COVERED:
            refused_n += 1
        elif not unmade:
            fetched += 1
        mark_coverage(run, name, "fmp", labels)
        if (fetched + refused_n) % CHECKPOINT_EVERY == 0:
            run.checkpoint()
    return {
        "calls_before": spent,
        "budget": settings.fmp_daily_budget,
        "due": len(due),
        "held_not_covered": len(holding),
        "asked": len(take),
        "fetched": fetched,
        "not_covered": refused_n,
        "kinds": [c[3] for c in calls],
        "names": take,
    }


def out_of_time(run: IngestRun, started: datetime) -> bool:
    """Whether the run has spent ``[fmp] run_budget_s`` (the clock, between two calls)."""
    return (run.clock() - started).total_seconds() > run.ctx.settings.fmp_run_budget_s


def _finnhub(
    run: IngestRun,
    source: Source,
    names: Sequence[Name],
    no: set[tuple[str, str]],
    answered: dict[str, date],
    started: datetime,
) -> dict[str, Any]:
    settings = run.ctx.settings
    if ("finnhub", RECOMMENDATION[2]) in no:
        return {"skipped": "the probe says stock/recommendation is DENIED"}
    by_symbol = {n.symbol: n for n in names}
    due = due_keys(by_symbol, answered, run.session, settings.finnhub_refresh_days)
    take = due[: settings.finnhub_per_night]
    for done, symbol in enumerate(take, 1):
        name = by_symbol[symbol]
        if out_of_time(run, started):
            run.record_item(f"{FINNHUB}{symbol}", f"{NOT_MADE}: [fmp] run_budget_s is spent")
            continue
        label = _ask(run, source, f"{FINNHUB}{symbol}", name, "recommendation", "finnhub")
        mark_coverage(run, name, "finnhub", [label])
        if done % CHECKPOINT_EVERY == 0:
            run.checkpoint()
    return {"due": len(due), "asked": len(take), "names": take}


def _ask(run: IngestRun, source: Source, key: str, name: Name, kind: str, vendor: str) -> str:
    """One vendor call -> its item label; the rows (stamped ``ts`` = now) are staged."""

    def ask() -> str:
        request = FetchRequest(name.symbol, name.instrument_id, run.session)
        fetched_at = pd.Timestamp(run.clock())
        try:
            normalized = run.fetch(source, request)
        except Exception as exc:  # an HttpError (the sources' own type) names its ``status``
            if vendor == "fmp" and getattr(exc, "status", None) == PLAN_REFUSAL:
                return f"{NOT_COVERED}: HTTP {PLAN_REFUSAL}"
            raise
        assert normalized is not None
        parsed = next(iter(normalized.parsed.values()))
        if parsed.empty:
            return EMPTY
        rows = build_rows(kind, parsed, name.instrument_id).assign(ts=fetched_at)
        run.stage(TABLE, key, rows, vendor)
        return OK

    return status_label(run.attempt(key, ask))
