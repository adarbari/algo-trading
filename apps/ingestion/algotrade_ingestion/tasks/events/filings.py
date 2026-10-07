"""The ``filings`` task: SEC 8-K filings of the scoped names -> ``events/filing``, and their Item
2.02 results releases -> ``events/earnings`` (ADR 0050).

One request per CIK to the registered ``sec_filings`` source (the recent block, plus the older
pages when ``since`` precedes it; pacing and ``User-Agent`` are the ``sec_edgar`` source's).
The names are the event-study scope (``config/site/events/scope.toml`` plus ``--symbols``),
resolved to ids through the reference snapshot of the run's session (``resolve_scope``: the one
place to swap for the scope owner of ADR 0050 decision 2 when it lands); their CIKs come from
``instruments/company`` as of the session. Share classes of one CIK get a row each.

- **Since**: ``--since`` for every CIK, else each CIK's latest stored acceptance (its New York
  date, so the day's later filings are read again), else 2018-01-01 for a CIK never stored (a
  first run is the backfill). Every filing read is written again each run (the table merges on
  ``instrument_id`` + ``accession``): an evening 8-K a nightly run stored on its own day is
  stored again the next night, when it is a past fact for that session.
- **``events/filing``**: ``ts`` is the acceptance instant (UTC), ``known_from`` the session of
  the acceptance time in New York: an acceptance after the close was public that evening, so it
  is that day's session. ``items`` keeps SEC's string ("2.02,9.01").
- **Earnings**: an ``8-K`` (not an amendment) whose items include 2.02 is also one
  ``events/earnings`` row with ``source = "sec_8k"``: ``earnings_date`` the acceptance date in
  New York; ``time`` ``pre_market`` before 09:30 New York time, ``after_hours`` from 16:00, else
  ``intraday``; ``reported`` true; ``known_from`` that date; ``fiscal_quarter`` the month of the
  8-K's ``report_date`` as the calendar writes it ("Sep/2026"), null when SEC gives none (the
  release date, not the quarter end: SEC's date is the earliest event reported). ``ts`` is the
  acceptance instant, never midnight, so it cannot collide with the calendar's row of the day
  (key ``instrument_id`` + ``ts``). The rows are written into the run session's partition like
  the calendar's; the one report per quarter is chosen by the rollup, not here.

Per CIK, an item of the run: ``OK: <n> 8-K, <m> results`` (none is still ``OK``), ``NO_DATA``
(SEC has no filings for the CIK) or ``FETCH_ERROR``; a name the reference does not know is
``UNKNOWN`` (``sym:<SYMBOL>``) and one without a CIK ``NO_CIK`` (``cik:<SYMBOL>``): counted,
never fetched. ``stats["ciks_failed"]`` / ``stats["ciks"]`` is what the ``filings_fetched``
acceptance check grades.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from functools import partial

import pandas as pd

from algotrade.core.model.instruments import pad_cik
from algotrade.core.time.calendar import EXCHANGE_TZ
from algotrade.data.events import ALL_TIME, read_events
from algotrade.data.reference import companies
from algotrade.storage.runs import RunRecord
from algotrade.storage.tables.schemas import EARNINGS_8K_SOURCE
from algotrade_ingestion.tasks.framework.run import IngestRun, NoResponseError, TaskContext
from algotrade_sources.framework.base import Source
from algotrade_sources.framework.series import FILINGS_FRAME, FilingsRequest

TASK = "filings"
TABLE = "events/filing"  # the table this task owns (architecture/tables.toml)
EARNINGS = "events/earnings"  # also written: the Item 2.02 rows (its writers: tables.toml)
DEFAULT_SINCE = date(2018, 1, 1)
RESULTS_ITEM = "2.02"
RESULTS_FORM = "8-K"  # an 8-K/A amends a release, it is no new report
PRE_MARKET, INTRADAY, AFTER_HOURS = "pre_market", "intraday", "after_hours"
OPEN_MINUTE, CLOSE_MINUTE = 9 * 60 + 30, 16 * 60  # New York clock, in minutes after midnight
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
CHECKPOINT_EVERY = 25
COLUMNS = [
    "instrument_id",
    "ts",
    "cik",
    "form",
    "accession",
    "filing_date",
    "items",
    "report_date",
    "primary_document",
    "known_from",
]
EARNINGS_COLUMNS = [
    "instrument_id",
    "ts",
    "symbol",
    "earnings_date",
    "time",
    "fiscal_quarter",
    "reported",
    "known_from",
]


@dataclass(frozen=True)
class Name:
    """A scoped name: its ticker and its instrument id."""

    symbol: str
    instrument_id: str


def resolve_scope(run: IngestRun, symbols: Sequence[str]) -> tuple[list[Name], list[str]]:
    """``symbols`` (upper-cased, first spelling wins) -> (the names the session's reference
    snapshot knows, one per instrument; the symbols it does not know). The one function to
    replace by ``services.events.scope.scoped_instruments`` (ADR 0050 decision 2)."""
    resolver = run.resolver()
    names: list[Name] = []
    unknown: list[str] = []
    seen: set[str] = set()
    for symbol in dict.fromkeys(s.strip().upper() for s in symbols if s.strip()):
        if not resolver.knows(symbol):
            unknown.append(symbol)
        elif (instrument_id := resolver.id_for(symbol)) not in seen:
            seen.add(instrument_id)
            names.append(Name(symbol, instrument_id))
    return names, unknown


def ciks_of(run: IngestRun, names: Sequence[Name]) -> dict[str, list[Name]]:
    """CIK (10 digits) -> the names that have it, from the company details on or before the
    run's session (a later snapshot never stands in); names without a CIK are left out."""
    frame = companies(run.reader, run.session, [n.instrument_id for n in names])
    if frame is None or frame.empty or "cik" not in frame.columns:
        return {}
    by_id = {str(i): pad_cik(c) for i, c in zip(frame["instrument_id"], frame["cik"], strict=True)}
    out: dict[str, list[Name]] = {}
    for name in names:
        if cik := by_id.get(name.instrument_id):
            out.setdefault(cik, []).append(name)
    return out


def acceptance_day(ts: pd.Series) -> pd.Series:
    """The New York calendar date of each acceptance instant (a ``date`` per row)."""
    return pd.Series(ts.dt.tz_convert(EXCHANGE_TZ).dt.date, index=ts.index, dtype=object)


def release_time(ts: pd.Series) -> pd.Series:
    """``pre_market`` before 09:30 New York time, ``after_hours`` from 16:00, else ``intraday``."""
    local = ts.dt.tz_convert(EXCHANGE_TZ)
    minute = local.dt.hour * 60 + local.dt.minute
    label = pd.Series(INTRADAY, index=ts.index, dtype=object)
    label[minute < OPEN_MINUTE] = PRE_MARKET
    label[minute >= CLOSE_MINUTE] = AFTER_HOURS
    return label


def _days(column: pd.Series) -> pd.Series:
    """A datetime column as ``date`` objects, null where missing."""
    days = pd.to_datetime(column).dt.date
    return days.astype(object).where(column.notna(), None)


def filing_rows(filings: pd.DataFrame, instrument_id: str) -> pd.DataFrame:
    """``COLUMNS`` rows of one instrument from the source's frame (module doc)."""
    ts = pd.to_datetime(filings["acceptance_ts"], utc=True)
    return pd.DataFrame(
        {
            "instrument_id": instrument_id,
            "ts": ts,
            "cik": filings["cik"],
            "form": filings["form"],
            "accession": filings["accession"],
            "filing_date": _days(filings["filing_date"]),
            "items": filings["items"].fillna(""),
            "report_date": _days(filings["report_date"]),
            "primary_document": filings["primary_document"],
            "known_from": acceptance_day(ts),
        },
        columns=COLUMNS,
    ).reset_index(drop=True)


def is_results_release(filings: pd.DataFrame) -> pd.Series:
    """The rows that are an original 8-K reporting Item 2.02."""
    listed = filings["items"].fillna("").astype(str).str.split(",")
    has_item = listed.map(lambda items: RESULTS_ITEM in {i.strip() for i in items})
    return (filings["form"] == RESULTS_FORM) & has_item


def fiscal_quarter(report_date: pd.Series) -> pd.Series:
    """The calendar's label ("Sep/2026") of each report date's month, null where missing."""
    days = pd.to_datetime(report_date)
    label = [f"{MONTHS[d.month - 1]}/{d.year}" if pd.notna(d) else None for d in days]
    return pd.Series(label, index=report_date.index, dtype=object)


def earnings_rows(filings: pd.DataFrame, name: Name) -> pd.DataFrame:
    """``EARNINGS_COLUMNS`` rows (``source = sec_8k`` is the writer's stamp) of the Item 2.02
    8-Ks in ``filings`` for one name (module doc); one per acceptance instant."""
    results = filings[is_results_release(filings)]
    ts = pd.to_datetime(results["acceptance_ts"], utc=True)
    day = acceptance_day(ts)
    out = pd.DataFrame(
        {
            "instrument_id": name.instrument_id,
            "ts": ts,
            "symbol": name.symbol,
            "earnings_date": day,
            "time": release_time(ts),
            "fiscal_quarter": fiscal_quarter(results["report_date"]),
            "reported": True,
            "known_from": day,
        },
        columns=EARNINGS_COLUMNS,
    )
    return out.drop_duplicates(["instrument_id", "ts"]).reset_index(drop=True)


def since_by_cik(
    run: IngestRun, ciks: dict[str, list[Name]], explicit: date | None
) -> dict[str, date]:
    """Where each CIK's read starts: ``explicit`` for all, else the New York date of its latest
    stored acceptance, else ``DEFAULT_SINCE``."""
    if explicit is not None:
        return dict.fromkeys(ciks, explicit)
    ids = [n.instrument_id for names in ciks.values() for n in names]
    stored = read_events(run.reader, TABLE, *ALL_TIME, instruments=ids).frame
    latest: dict[str, date] = {}
    if len(stored) and "cik" in stored.columns:
        ts = pd.to_datetime(stored["ts"], utc=True)
        newest = ts.groupby(stored["cik"]).max()
        latest = {str(cik): moment.tz_convert(EXCHANGE_TZ).date() for cik, moment in newest.items()}
    return {cik: latest.get(cik, DEFAULT_SINCE) for cik in ciks}


def _one_cik(run: IngestRun, source: Source, cik: str, names: list[Name], since: date) -> str:
    """Fetch one CIK's 8-Ks, stage its filing and earnings rows -> the item status."""
    request = FilingsRequest(key=cik, session_date=run.session, since=since)
    try:
        normalized = run.fetch(source, request)
    except NoResponseError:
        return "NO_DATA: SEC has no filings for this CIK"
    assert normalized is not None
    filings = normalized.parsed[FILINGS_FRAME]
    rows = pd.concat([filing_rows(filings, n.instrument_id) for n in names], ignore_index=True)
    results = pd.concat([earnings_rows(filings, n) for n in names], ignore_index=True)
    if len(rows):
        run.stage(TABLE, cik, rows, source.name)
    if len(results):
        run.stage(EARNINGS, cik, results, EARNINGS_8K_SOURCE)
    return f"OK: {len(filings)} 8-K, {int(is_results_release(filings).sum())} results"


def ingest_filings(
    ctx: TaskContext,
    source: Source,
    session: date,
    symbols: Sequence[str],
    since: date | None = None,
    limit: int | None = None,
) -> RunRecord:
    """Store the 8-K filings of ``symbols`` (the scope) read since ``since`` (default per CIK,
    module doc), at most ``limit`` CIKs."""
    with IngestRun(ctx, TASK, session) as run:
        names, unknown = resolve_scope(run, symbols)
        for symbol in unknown:
            run.record_item(f"sym:{symbol}", "UNKNOWN: not in the session's reference snapshot")
        ciks = ciks_of(run, names)
        have = {n.instrument_id for group in ciks.values() for n in group}
        without = [n for n in names if n.instrument_id not in have]
        for name in without:
            run.record_item(f"cik:{name.symbol}", "NO_CIK: no CIK in the company details")
        ciks = dict(list(ciks.items())[:limit]) if limit else ciks
        starts = since_by_cik(run, ciks, since)
        for i, (cik, group) in enumerate(ciks.items(), 1):
            run.attempt(cik, partial(_one_cik, run, source, cik, group, starts[cik]))
            if i % CHECKPOINT_EVERY == 0:
                run.checkpoint()
        written = run.publish(TABLE)
        results = run.publish(EARNINGS, sort_by="ts")
        run.stats.update(
            names=len(names),
            ciks=len(ciks),
            ciks_failed=len(run.failures()),
            without_cik=[n.symbol for n in without],
            unknown_symbols=unknown,
            since=since.isoformat() if since else None,
            filings=written,
            results=results,
            items=run.counts(),
        )
    return run.record
