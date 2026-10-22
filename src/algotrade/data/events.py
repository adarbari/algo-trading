"""Event tables (``events/split``, ``events/dividend``, …) read by EVENT date, known as of a
session.

An event is stored in the partition of the run that learned it (a backfill run on
2026-10-02 stores 2015 splits in ``date=2026-10-02``), so the partition date says nothing
about when the event happened. Readers therefore scan every partition, keep rows whose
``ts`` (the event date) is in the requested window, and keep the latest ``knowledge_ts`` per
event key. ``as_of`` pins the stored version (ADR 0007).

**The one read rule** (ADR 0050 decision 3): as of session S a reader keeps only rows known
on or before S. A row is known from its ``known_from`` date (``schemas.KNOWN_FROM``: the
session the fact was knowable on, e.g. a backfilled report's report date), else, when the
column is absent or null, from the session that stored it (``session_date``). So a 2019
report backfilled into a 2026 partition with ``known_from = 2019-05-01`` is visible to a
2019-05-01 session, and a row without ``known_from`` is invisible before the session that
stored it. ``through`` is S; ``None`` keeps every row.

**Facts of record** (``FACTS_OF_RECORD``: splits, dividends, reference and index changes) are
applied to bars at read time (ADR 0016) and read by event date without a knowledge bound:
they carry no ``known_from``, and ``knowledge_bound`` gives them none, so a pinned past
session shows the split its own adjusted bars used.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import pandas as pd

from algotrade.core.time.calendar import EXCHANGE_TZ, close_time, is_session, next_session
from algotrade.storage.runs import published
from algotrade.storage.tables.readers import StoreReader
from algotrade.storage.tables.schemas import KNOWN_FROM

ALL_TIME = (date(1900, 1, 1), date(9999, 12, 31))
# Read by event date with no knowledge bound (module doc): applied to bars at read time
# (``events/bar_flag``: the bars the quality check rejects are dropped, ADR 0061).
FACTS_OF_RECORD = frozenset(
    {
        "events/split",
        "events/dividend",
        "events/reference_change",
        "events/index_change",
        "events/bar_flag",
    }
)
# Tables whose writer stores ``instrument_id`` NULL in every row (keyed by the filer's CIK; a
# reader maps the CIK through ``instruments/company``): an ``instruments`` filter finds nothing in
# them, so a per-instrument read leaves them out instead of decoding them (``events/filing_text``:
# 4.3 GB read for 0 rows). ``events/ipo_lockup`` is not here: its later versions carry the id.
# Fitness test: ``tests/architecture/ingestion/test_events_no_instrument_rows.py``.
NO_INSTRUMENT_ROWS = frozenset({"events/filing_text"})


@dataclass(frozen=True)
class Events:
    frame: pd.DataFrame  # one row per event key, sorted by (instrument_id, ts)
    runs: list[str]  # the stored runs the rows came from (for reproducibility)


def event_key(frame: pd.DataFrame) -> list[str]:
    """``instrument_id`` + ``ts`` (+ ``change`` for tables with several kinds a day, + ``accession``
    for filings: two filings accepted the same second are two events)."""
    extra = [c for c in ("change", "accession") if c in frame.columns]
    return ["instrument_id", "ts", *extra]


def known_from(frame: pd.DataFrame) -> pd.Series:
    """Each row's effective ``known_from`` as a datetime64 (midnight): the column when set,
    else the row's ``session_date`` (the one read rule, module doc)."""
    stored = pd.to_datetime(frame["session_date"])
    if KNOWN_FROM not in frame.columns:
        return stored
    return pd.to_datetime(frame[KNOWN_FROM]).fillna(stored)


def _known_by(frame: pd.DataFrame, through: date | None) -> pd.DataFrame:
    """The rows known on or before ``through`` (None: all)."""
    if through is None:
        return frame
    return frame[known_from(frame) <= pd.Timestamp(through)]


def acceptance_sessions(ts: pd.Series) -> pd.Series:
    """The session each acceptance instant of ``ts`` (UTC, aware) is known from: the first
    session whose close is strictly after it (``calendar.acceptance_session``, vectorised): an
    acceptance before the close counts that session, one at or after it, on a weekend or on a
    holiday the next. A missing instant stays null. The one ``known_from`` of a filing (ADR 0050
    amendment, EB H4): never the New York DAY of the acceptance, which counts a 16:30 filing as
    public in that day's close and puts a Sunday filing on a non-session."""
    accepted = pd.to_datetime(ts, utc=True)
    local = accepted.dt.tz_convert(EXCHANGE_TZ).dt.date
    days = set(local.dropna())
    after = {d: next_session(d) for d in days}
    close = {d: close_time(d) for d in days if is_session(d)}
    closes = pd.to_datetime(local.map(close), utc=True)  # NaT on a day that is no session
    on_time = accepted.notna() & (accepted < closes)
    out = local.where(on_time, local.map(after))
    return out.astype(object).where(out.notna(), None)


def knowledge_bound(table: str, session: date) -> date | None:
    """The ``through`` a read as of ``session`` passes for ``table``: the session, or None for
    a fact of record (module doc)."""
    return None if table in FACTS_OF_RECORD else session


def read_events(
    reader: StoreReader,
    table: str,
    start: date,
    end: date,
    instruments: Sequence[str] | None = None,
    as_of: datetime | None = None,
    through: date | None = None,
) -> Events:
    """Events with ``start <= ts (UTC date) <= end`` among the rows known on or before
    ``through`` (None: every row), the latest stored version of each."""
    frame = reader.table_range(table, *ALL_TIME, as_of, instruments)
    if frame is None or frame.empty:
        return Events(pd.DataFrame(columns=["instrument_id", "ts"]), [])
    frame = _known_by(frame, through)
    day = pd.to_datetime(frame["ts"], utc=True).dt.date
    frame = frame[(day >= start) & (day <= end)]
    if frame.empty:
        return Events(frame.reset_index(drop=True), [])
    frame = frame.sort_values("knowledge_ts", kind="stable").drop_duplicates(
        event_key(frame), keep="last"
    )
    frame = frame.sort_values(["instrument_id", "ts"], kind="stable").reset_index(drop=True)
    return Events(frame, sorted(map(str, frame["run_id"].unique())))


def latest_versions(
    reader: StoreReader,
    table: str,
    key: Sequence[str],
    through: date | None = None,
    as_of: datetime | None = None,
) -> pd.DataFrame:
    """The rows of ``table`` known on or before ``through`` (None: every row), the latest stored
    version of each ``key`` among them: how a table keyed by something other than
    (``instrument_id``, ``ts``) is read (``events/ipo_lockup``: ``cik`` + ``accession``). A
    version known later than ``through`` is skipped, so the version before it is the one read.
    Sorted by ``key``; empty (no columns) when nothing is stored."""
    frame = reader.table_range(table, *ALL_TIME, as_of)
    if frame is None or frame.empty:
        return pd.DataFrame()
    frame = _known_by(frame, through).assign(**{KNOWN_FROM: lambda f: known_from(f).dt.date})
    return latest_of(frame, key)


def latest_of(frame: pd.DataFrame, key: Sequence[str]) -> pd.DataFrame:
    """The latest stored version (``knowledge_ts``, then ``run_id``) of each ``key`` in
    ``frame``, sorted by ``key``: the one rule ``latest_versions`` and a per-session read of
    the stored versions share."""
    frame = frame.sort_values(["knowledge_ts", "run_id"], kind="stable")
    frame = frame.drop_duplicates(list(key), keep="last")
    return frame.sort_values(list(key), kind="stable").reset_index(drop=True)


def events_by_acceptance(
    reader: StoreReader, table: str, start: date, end: date, as_of: datetime | None = None
) -> pd.DataFrame:
    """The filings of ``table`` (``events/filing``) that became known in ``start..end``, with an
    ``event_date`` column: the session each is known from (``acceptance_sessions`` of its ``ts``,
    never its stored ``known_from``: a row stamped by the old New York-day rule is still read
    right), sorted by (``event_date``, ``instrument_id``). Never a later one. The latest stored
    version of each filing, whatever its stamp."""
    margin = timedelta(days=5)  # a filing is known at most a long weekend after it is accepted
    frame = read_events(reader, table, start - margin, end, as_of=as_of).frame
    frame = frame.drop(columns=[c for c in ("session_date", KNOWN_FROM) if c in frame.columns])
    if frame.empty:
        return frame.assign(event_date=pd.Series(dtype=object)).reset_index(drop=True)
    frame = frame.assign(event_date=acceptance_sessions(frame["ts"]))
    frame = frame[(frame["event_date"] >= start) & (frame["event_date"] <= end)]
    return frame.sort_values(["event_date", "instrument_id"], kind="stable").reset_index(drop=True)


def stored_events(
    reader: StoreReader, table: str, through: date, as_of: datetime | None = None
) -> pd.DataFrame:
    """Every stored row of ``table`` known on or before ``through``, as stored, with
    ``known_from`` set to each row's effective date (the one read rule).

    Unlike ``read_events`` nothing is merged: each row keeps the ``session_date`` of the run
    that stored it, so a consumer can tell what was known on each session (e.g. the earnings
    calendar as of D: the snapshots stored on or before D, and the reports backfilled later
    but known by D). Sorted by ``known_from`` then ``session_date``; empty when nothing is
    stored."""
    frame = reader.table_range(table, *ALL_TIME, as_of)
    if frame is None:
        return pd.DataFrame(columns=["instrument_id", "ts", "session_date", KNOWN_FROM])
    frame = _known_by(frame, through)
    frame = frame.assign(**{KNOWN_FROM: known_from(frame).dt.date})
    order = [KNOWN_FROM, "session_date", "instrument_id", "ts"]
    return frame.sort_values(order, kind="stable").reset_index(drop=True)


def events_by_event_date(
    reader: StoreReader,
    table: str,
    start: date,
    end: date,
    as_of: datetime | None = None,
    through: date | None = None,
) -> pd.DataFrame:
    """``read_events`` for ``start..end`` (known on or before ``through``; None: every row)
    with an ``event_date`` column (the UTC date of ``ts``), sorted by (``event_date``,
    ``instrument_id``). The stored partition date is dropped: it says when we learned of the
    event, not when it happened. Never a later event (a declared future ex-date stays out
    until its date)."""
    frame = read_events(reader, table, start, end, as_of=as_of, through=through).frame
    frame = frame.drop(columns=[c for c in ("session_date",) if c in frame.columns])
    frame = frame.assign(event_date=pd.to_datetime(frame["ts"], utc=True).dt.date)
    frame = frame.sort_values(["event_date", "instrument_id"], kind="stable")
    return frame.reset_index(drop=True)


FILINGS_JOB = "filings"  # the ingestion task that writes events/filing: its run records


FILINGS_DEFAULT_SINCE = date(2018, 1, 1)  # where a full per-CIK read of the filings task starts
_READ_OK = ("OK", "NO_DATA")  # item statuses of a CIK that was read (a CIK with none is NO_DATA)


@dataclass(frozen=True)
class FilingCoverage:
    """What the filings task's published runs say the stored ``events/filing`` rows are complete
    for (``filing_coverage``): the clean daily-index walks (``walks``: ``session_date`` of the
    run, ``walked_to``) and the full per-CIK reads (``reads``: ``cik``, the run's
    ``session_date`` and ``covers_since``; one row per CIK and run, sorted by ``session_date``).
    A walk says every CIK is complete through ``walked_to``; a read says that one CIK is
    complete from ``covers_since`` through its run's session, whenever the session is asked
    about: the filings known on a past session are the same on every later run."""

    walks: pd.DataFrame
    reads: pd.DataFrame

    @property
    def walked_to(self) -> date | None:
        """The last index day an earlier clean walk read: where the next walk starts. Stored
        filing dates do not say: a per-CIK run or a failed CIK moves them past unread days."""
        return None if self.walks.empty else self.walks["walked_to"].max()

    def asked_since(self) -> dict[str, date]:
        """CIK -> the earliest date a read covers it from."""
        if self.reads.empty:
            return {}
        return {str(c): s for c, s in self.reads.groupby("cik")["covers_since"].min().items()}


def filing_coverage(
    reader: StoreReader, forms: str | None = None, exclude: str | None = None
) -> FilingCoverage:
    """The coverage the filings task's published runs record. ``forms`` (the task's form-set
    tag, ``stats["forms"]``) keeps only runs that read that form set (a run before the set grew
    does not count: the ingestion backfill re-reads every CIK once; ``filing_activity`` needs
    8-Ks only and passes none); ``exclude`` is a run id to leave out (the run asking).

    A per-CIK run (``stats["covers_since"]``) reads each CIK it asked from that date; a nightly
    only the CIKs it read in full (``stats["backfilled"]``) from ``FILINGS_DEFAULT_SINCE``. A CIK
    counts when its item is OK or NO_DATA."""
    walks, reads = [], []
    for record in reader.runs(FILINGS_JOB):
        if not published(record) or record.run_id == exclude:
            continue
        stats = record.stats
        if stats.get("walked_to"):
            walked = date.fromisoformat(stats["walked_to"])
            walks.append({"session_date": record.session_date, "walked_to": walked})
        if forms is not None and stats.get("forms") != forms:
            continue
        if stats.get("covers_since"):
            start, ciks = date.fromisoformat(stats["covers_since"]), list(record.items)
        else:
            start, ciks = FILINGS_DEFAULT_SINCE, list(stats.get("backfilled") or [])
        reads += [
            {"cik": c, "session_date": record.session_date, "covers_since": start}
            for c in ciks
            if c.isdigit() and record.items.get(c, "").split(":", 1)[0] in _READ_OK
        ]
    frames = (
        pd.DataFrame(walks, columns=["session_date", "walked_to"]),
        pd.DataFrame(reads, columns=["cik", "session_date", "covers_since"]),
    )
    walk_frame, read_frame = (
        f.sort_values("session_date", kind="stable").reset_index(drop=True) for f in frames
    )
    return FilingCoverage(walk_frame, read_frame)


def filing_walks(reader: StoreReader) -> pd.DataFrame:
    """The clean daily-index walks of the filings task (``filing_coverage(reader).walks``):
    ``session_date`` of the run, ``walked_to``, sorted by ``session_date``; empty when none."""
    return filing_coverage(reader).walks
