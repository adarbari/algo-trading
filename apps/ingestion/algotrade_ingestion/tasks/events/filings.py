"""The ``filings`` task: SEC 8-K filings of every operating company in the universe ->
``events/filing``, and their Item 2.02 results releases -> ``events/earnings`` (ADR 0050).

**Names**: the session's universe snapshot minus the funds (``security_type`` ETF / ETN: a fund
files no 8-K), each name's CIK from ``instruments/company`` as of the session. Share classes of
one CIK share one request and get a row each; a name without a CIK is counted
(``stats["without_cik"]``), never fetched. ``--symbols`` narrows the run to those tickers
(``UNKNOWN`` for one the universe does not hold). The event-study scope is no longer used here.

Two ways to read SEC, one row shape (``_one_cik`` is the only writer of rows):

- **Per CIK** (the backfill): one request per CIK to the registered ``sec_filings`` source (the
  recent block, plus the older pages when ``since`` precedes it; pacing and ``User-Agent`` are
  the ``sec_edgar`` source's). Used with ``--since`` (every CIK from that date; one whose stored
  filings already reach it is skipped, so a run can be repeated, and ``--limit`` caps the CIKs
  a run asks), and when nothing is stored yet (each CIK from ``DEFAULT_SINCE``). Never-stored
  CIKs come first.
- **Daily index** (the nightly, once filings are stored and without ``--since``): for each
  weekday from the latest stored ``filing_date`` (inclusive: a rerun changes nothing) through
  the session, the ``sec_daily_index`` source reads that day's form index; the universe CIKs
  with an 8-K or 8-K/A on it are the only ones asked for their submissions (the index has no
  items or acceptance time). A day without an index is ``NO_DATA`` (a weekend or holiday when a
  later day is published, else "not published yet": the next run reads it again, because the
  start stays the latest stored day); one older than ``STALE_DAYS`` business days with nothing
  published after it is ``FETCH_ERROR``. A day that fails stops the walk, and rows are kept only
  up to the last day read, so the stored history never skips a day. ``--limit`` does not apply.

- **Since** (per CIK): ``--since`` for every CIK, else each CIK's latest stored acceptance (its
  New York date, so the day's later filings are read again), else 2018-01-01. Every filing read
  is written again each run (the table merges on ``instrument_id`` + ``accession``).
- **``events/filing``**: ``ts`` is the acceptance instant (UTC), ``known_from`` the session of
  the acceptance time in New York: an acceptance after the close was public that evening, so it
  is that day's session. ``items`` keeps SEC's string ("2.02,9.01").
- **Earnings**: an ``8-K`` (not an amendment) whose items include 2.02 is also one
  ``events/earnings`` row with ``source = "sec_8k"``: ``earnings_date`` the acceptance date in
  New York; ``time`` ``pre_market`` before 09:30 New York time, ``after_hours`` from 16:00, else
  ``intraday``; ``reported`` true; ``known_from`` that date; ``fiscal_quarter`` null (the
  calendar's label names a quarter end; the 8-K's ``report_date`` is the release date, another
  thing, so the per-quarter precedence of ADR 0050 is the rollup's to derive). ``ts`` is the
  acceptance instant (one at exactly midnight UTC is written one second later), so it never
  shares the calendar row's key (``instrument_id`` + ``ts``). The rows are written into the run
  session's partition like the calendar's; the one report per quarter is chosen by the rollup,
  not here.

Items: per CIK ``OK: <n> 8-K, <m> results`` (none is still ``OK``), ``NO_DATA`` (SEC has no
filings for the CIK) or ``FETCH_ERROR``; per index day ``idx:<date>``. A name the universe does
not hold is ``UNKNOWN`` (``sym:<SYMBOL>``). ``stats``: ``ciks`` / ``ciks_failed`` (submissions
requests) and ``days`` / ``days_failed`` (index requests) are what the ``filings_fetched``
acceptance check grades.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from functools import partial

import pandas as pd

from algotrade.core.model.instruments import pad_cik
from algotrade.core.time.calendar import EXCHANGE_TZ, is_weekend
from algotrade.data.events import ALL_TIME
from algotrade.data.reference import companies, load_universe
from algotrade.storage.runs import RunRecord
from algotrade.storage.tables.schemas import EARNINGS_8K_SOURCE
from algotrade_ingestion.tasks.framework.run import (
    FAILURES,
    IngestRun,
    NoResponseError,
    TaskContext,
    status_label,
)
from algotrade_sources.framework.base import Source
from algotrade_sources.framework.series import (
    DAILY_INDEX_FRAME,
    FILINGS_FRAME,
    DailyIndexRequest,
    FilingsRequest,
)

TASK = "filings"
TABLE = "events/filing"  # the table this task owns (architecture/tables.toml)
EARNINGS = "events/earnings"  # also written: the Item 2.02 rows (its writers: tables.toml)
DEFAULT_SINCE = date(2018, 1, 1)
FUND_TYPES = ("ETF", "ETN")  # security types that file no 8-K
STALE_DAYS = 7  # business days after which a missing daily index is an error, not "not yet"
RESULTS_ITEM = "2.02"
RESULTS_FORM = "8-K"  # an 8-K/A amends a release, it is no new report
PRE_MARKET, INTRADAY, AFTER_HOURS = "pre_market", "intraday", "after_hours"
OPEN_MINUTE, CLOSE_MINUTE = 9 * 60 + 30, 16 * 60  # New York clock, in minutes after midnight
CHECKPOINT_EVERY = 25
INDEX_PREFIX = "idx:"  # item keys of the daily index days
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
class Listed:
    """One operating company in the universe: its id and its ticker in the snapshot."""

    instrument_id: str
    symbol: str


@dataclass(frozen=True)
class Names:
    """The names a run covers and why others are not: ``funds`` excluded, ``unknown`` requested
    tickers the universe does not hold."""

    listed: list[Listed]
    funds: int
    unknown: list[str]


def universe_names(run: IngestRun, requested: Sequence[str]) -> Names:
    """The session's universe without funds (``--symbols`` narrows it); ``MissingDataError``
    when no universe snapshot is stored."""
    frame = load_universe(run.reader, run.session).frame
    wanted = {s.upper() for s in requested}
    unknown = sorted(wanted - {str(s).upper() for s in frame["symbol"]})
    if wanted:
        frame = frame[frame["symbol"].astype(str).str.upper().isin(wanted)]
    fund = frame["security_type"].isin(FUND_TYPES)
    names = [
        Listed(str(i), str(s))
        for i, s in zip(frame.loc[~fund, "instrument_id"], frame.loc[~fund, "symbol"], strict=True)
    ]
    return Names(names, int(fund.sum()), unknown)


def ciks_of(run: IngestRun, names: Sequence[Listed]) -> dict[str, list[Listed]]:
    """CIK (10 digits) -> the names that have it, from the company details on or before the
    run's session (a later snapshot never stands in); names without a CIK are left out."""
    frame = companies(run.reader, run.session, [n.instrument_id for n in names])
    if frame is None or frame.empty or "cik" not in frame.columns:
        return {}
    by_id = {str(i): pad_cik(c) for i, c in zip(frame["instrument_id"], frame["cik"], strict=True)}
    out: dict[str, list[Listed]] = {}
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


def earnings_rows(filings: pd.DataFrame, name: Listed) -> pd.DataFrame:
    """``EARNINGS_COLUMNS`` rows (``source = sec_8k`` is the writer's stamp) of the Item 2.02
    8-Ks in ``filings`` for one name (module doc); one per acceptance instant."""
    results = filings[is_results_release(filings)]
    ts = pd.to_datetime(results["acceptance_ts"], utc=True)
    # An acceptance at exactly 20:00:00 EDT (19:00 EST) is midnight UTC: the calendar row's key.
    # One second later keeps the two rows apart (the instant is a key, not a fact anyone reads).
    ts = ts.where(ts != ts.dt.normalize(), ts + pd.Timedelta(seconds=1))
    day = acceptance_day(ts)
    out = pd.DataFrame(
        {
            "instrument_id": name.instrument_id,
            "ts": ts,
            "symbol": name.symbol,
            "earnings_date": day,
            "time": release_time(ts),
            "fiscal_quarter": None,  # the calendar's label (a quarter end); an 8-K has none
            "reported": True,
            "known_from": day,
        },
        columns=EARNINGS_COLUMNS,
    )
    return out.drop_duplicates(["instrument_id", "ts"]).reset_index(drop=True)


def stored_filings(run: IngestRun) -> pd.DataFrame:
    """``instrument_id``, ``ts`` (UTC) and ``filing_date`` (a ``date``) of every stored filing."""
    frame = run.reader.table_range(TABLE, *ALL_TIME, columns=["ts", "filing_date"])
    if frame is None or frame.empty:
        return pd.DataFrame({"instrument_id": [], "ts": [], "filing_date": []})
    return pd.DataFrame(
        {
            "instrument_id": frame["instrument_id"].astype(str),
            "ts": pd.to_datetime(frame["ts"], utc=True),
            "filing_date": pd.to_datetime(frame["filing_date"]).dt.date,
        }
    )


def since_by_cik(
    ciks: dict[str, list[Listed]], stored: pd.DataFrame, explicit: date | None
) -> dict[str, date]:
    """Where each CIK's read starts: ``explicit`` for all, else the earliest of its names' starts,
    a name's start being the New York date of its latest stored acceptance, else
    ``DEFAULT_SINCE`` (a share class newly in scope gets the CIK's history re-read; the rows
    already stored are rewritten unchanged)."""
    if explicit is not None:
        return dict.fromkeys(ciks, explicit)
    latest: dict[str, date] = {}
    if len(stored):
        newest = stored["ts"].groupby(stored["instrument_id"]).max()
        latest = {str(iid): moment.tz_convert(EXCHANGE_TZ).date() for iid, moment in newest.items()}
    return {
        cik: min(latest.get(n.instrument_id, DEFAULT_SINCE) for n in names)
        for cik, names in ciks.items()
    }


def order_and_skip(
    ciks: dict[str, list[Listed]], stored: pd.DataFrame, explicit: date | None
) -> tuple[dict[str, list[Listed]], int]:
    """The CIKs to ask, never-stored ones first, and how many were skipped: with an explicit
    ``since``, a CIK whose every name already has a stored filing on or before it is covered."""
    first = stored.groupby("instrument_id")["filing_date"].min().to_dict() if len(stored) else {}

    def covered(names: list[Listed]) -> bool:
        return explicit is not None and all(
            first.get(n.instrument_id, date.max) <= explicit for n in names
        )

    def untouched(names: list[Listed]) -> bool:
        return not any(n.instrument_id in first for n in names)

    todo = {cik: names for cik, names in ciks.items() if not covered(names)}
    ordered = sorted(todo, key=lambda cik: not untouched(todo[cik]))  # stable: False first
    return {cik: todo[cik] for cik in ordered}, len(ciks) - len(todo)


def filing_days(first: date, last: date) -> list[date]:
    """The weekdays from ``first`` through ``last`` (EDGAR is open on every one that is no
    federal holiday; a holiday simply has no index)."""
    days = (first + timedelta(n) for n in range((last - first).days + 1))
    return [d for d in days if not is_weekend(d)]


def read_index_days(
    run: IngestRun, index: Source, days: list[date]
) -> tuple[dict[date, set[str]], int]:
    """Each day's 8-K filer CIKs by day for the days with a published index (module doc), and
    the days asked. Records one ``idx:<date>`` item per day; a failing day stops the walk."""
    filers: dict[date, set[str]] = {}
    unpublished: list[date] = []
    asked = 0
    for day in days:
        asked += 1
        try:
            normalized = run.fetch(
                index, DailyIndexRequest(key=day.isoformat(), session_date=run.session, day=day)
            )
        except NoResponseError:
            unpublished.append(day)
            continue
        except Exception as exc:  # a failed day must not let later days be stored over it
            run.fail(f"{INDEX_PREFIX}{day}", str(exc))
            break
        assert normalized is not None
        ciks = set(normalized.parsed[DAILY_INDEX_FRAME]["cik"])
        filers[day] = ciks
        run.record_item(f"{INDEX_PREFIX}{day}", f"OK: {len(ciks)} CIKs with an 8-K")
        for gap in unpublished:  # a later day exists: the gap was a weekend or holiday
            run.record_item(f"{INDEX_PREFIX}{gap}", "NO_DATA: no index (a holiday)")
        unpublished.clear()
    for gap in unpublished:  # nothing published after it: not yet, unless it is long overdue
        stale = len(filing_days(gap, run.session)) - 1 > STALE_DAYS
        if stale:
            run.fail(f"{INDEX_PREFIX}{gap}", f"no index for more than {STALE_DAYS} business days")
        else:
            run.record_item(
                f"{INDEX_PREFIX}{gap}", "NO_DATA: not published yet, read again next run"
            )
    return filers, asked


def _one_cik(
    run: IngestRun,
    source: Source,
    cik: str,
    names: list[Listed],
    since: date,
    until: date | None = None,
) -> str:
    """Fetch one CIK's 8-Ks (filed on or before ``until`` when given), stage its filing and
    earnings rows -> the item status."""
    request = FilingsRequest(key=cik, session_date=run.session, since=since)
    try:
        normalized = run.fetch(source, request)
    except NoResponseError:
        return "NO_DATA: SEC has no filings for this CIK"
    assert normalized is not None
    filings = normalized.parsed[FILINGS_FRAME]
    if until is not None:
        filings = filings[filings["filing_date"] <= pd.Timestamp(until)]
    rows = pd.concat([filing_rows(filings, n.instrument_id) for n in names], ignore_index=True)
    results = pd.concat([earnings_rows(filings, n) for n in names], ignore_index=True)
    if len(rows):
        run.stage(TABLE, cik, rows, source.name)
    if len(results):
        run.stage(EARNINGS, cik, results, EARNINGS_8K_SOURCE)
    return f"OK: {len(filings)} 8-K, {int(is_results_release(filings).sum())} results"


def _ask(
    run: IngestRun,
    source: Source,
    ciks: dict[str, list[Listed]],
    starts: dict[str, date],
    until: date | None = None,
) -> None:
    """One submissions request per CIK, checkpointing as it goes."""
    for i, (cik, group) in enumerate(ciks.items(), 1):
        run.attempt(cik, partial(_one_cik, run, source, cik, group, starts[cik], until))
        if i % CHECKPOINT_EVERY == 0:
            run.checkpoint()


def _failed(run: IngestRun, *, days: bool) -> int:
    """Failed items of the index days (``days``) or of the CIKs."""
    return sum(
        status_label(status) in FAILURES
        for key, status in run.items.items()
        if key.startswith(INDEX_PREFIX) == days and not key.startswith(("sym:", "cik:"))
    )


def ingest_filings(
    ctx: TaskContext,
    source: Source,
    session: date,
    requested: Sequence[str],
    since: date | None = None,
    limit: int | None = None,
    index: Source | None = None,
) -> RunRecord:
    """Store the 8-K filings of the universe's operating companies (module doc): per CIK from
    ``since`` (at most ``limit`` CIKs), or, without ``since`` and with filings stored, the CIKs
    the daily ``index`` shows filing since the latest stored day."""
    with IngestRun(ctx, TASK, session) as run:
        covered = universe_names(run, requested)
        names = covered.listed
        for symbol in covered.unknown:
            run.record_item(f"sym:{symbol}", "UNKNOWN: not in the universe")
        ciks = ciks_of(run, names)
        have = {n.instrument_id for group in ciks.values() for n in group}
        without = [n.symbol for n in names if n.instrument_id not in have]
        stored = stored_filings(run)
        latest = max(stored["filing_date"]) if len(stored) else None
        daily = index is not None and since is None and latest is not None
        skipped, days_asked, first_day, last_day = 0, 0, None, None
        if daily:
            assert index is not None and latest is not None
            filers, days_asked = read_index_days(run, index, filing_days(latest, session))
            first_day, last_day = (min(filers), max(filers)) if filers else (None, None)
            asked = set().union(*filers.values()) & set(ciks)
            ciks = {cik: ciks[cik] for cik in ciks if cik in asked}
            starts = dict.fromkeys(ciks, first_day) if first_day else {}
            _ask(run, source, ciks, starts, last_day)
        else:
            ciks, skipped = order_and_skip(ciks, stored, since)
            ciks = dict(list(ciks.items())[:limit]) if limit else ciks
            _ask(run, source, ciks, since_by_cik(ciks, stored, since))
        written = run.publish(TABLE)
        results = run.publish(EARNINGS, sort_by="ts")
        run.stats.update(
            mode="daily_index" if daily else "per_cik",
            names=len(names),
            with_cik=len(have),
            funds_excluded=covered.funds,
            ciks=len(ciks),
            ciks_failed=_failed(run, days=False),
            skipped_covered=skipped,
            days=days_asked,
            days_failed=_failed(run, days=True),
            without_cik=without,
            unknown_symbols=covered.unknown,
            since=since.isoformat() if since else (first_day.isoformat() if first_day else None),
            until=last_day.isoformat() if last_day else None,
            filings=written,
            results=results,
            items=run.counts(),
        )
    return run.record
