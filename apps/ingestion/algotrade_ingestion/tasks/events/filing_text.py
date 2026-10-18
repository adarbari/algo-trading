"""The ``filing-text`` task: the item sections of every 10-K / 10-Q (and 10-K/A, 10-Q/A) of EVERY
filer, delisted companies included -> ``events/filing_text`` (edge build D10 / D10b; Lazy Prices,
risk-factor change, MD&A tone; the similarity features are track E, this is the text).

**Filer-first**: the backfill's CIKs are the filers of the window from the SEC daily form index
(``filing_text_filers.py``: one request a business day through ``sec_daily_index``, the list of a
past window recorded in the run's stats so a later run of it does not walk the days again), not
today's universe, so a company delisted before the first snapshot is covered (no stored table maps a
delisted listing to a CIK; the index is the cheapest honest source). ``--symbols`` is the narrow
read of those tickers' CIKs (no index walk). Rows are keyed by ``cik`` + ``accession`` + ``item``
+ ``parser_version`` + ``known_from``; ``instrument_id`` is nullable (see **Ids**).

**Per CIK**: the filing list is the ``sec_filings`` source read with the periodic forms
(``PERIODIC_FORMS``; one submissions request per CIK, the older pages when ``--from`` precedes the
recent block), then one document request per filing to ``sec_filing_text`` (the primary document,
parsed and dropped: only the items are stored, ``vendors/sec_text/filing_items.py``; kept items
per form by default ``DEFAULT_10K`` / ``DEFAULT_10Q``, ``--items`` narrows or widens, the only
size bound besides ``--limit``, the CIKs a run reads).

**Ids** (the D8 pattern, ``ipo_lockups.fill_instruments``): the first version of a filing's row
has a NULL ``instrument_id`` and is known from its acceptance session: the run's universe is
today's, so an id there would exist only for the survivors. When the run's session snapshot
(``instruments/company``) holds the CIK, the same row is staged again with the id (the lowest id of
its share classes) as a version of its own, known from ``max(acceptance session, the session after
the exchange date of the run's clock)``, the FETCH's session (equal to the acceptance session: the
id goes on the one row). A read before that shows NULL; readers map a CIK to its instruments
through ``instruments/company`` as of their own session (``data.filing_text``). A CIK that joins
the universe after its filings were stored keeps NULL ids until a ``--force`` run: the reader's
mapping covers it.

**Two modes**, one row shape:

- **Backfill** (``--from`` [``--to``]): the CIKs not yet read for the window, ``--limit`` of them a
  run (default ``BACKFILL_CIKS``: a run is one published unit held in memory). A CIK read OK from
  a window that covers this one by an earlier run of the same ``TAG`` (parser version + items) is
  skipped, so the loop restarts where it stopped. Within a CIK the newest filing goes first. History
  from 2010: run the windows newest first (``README.md`` "Long runs": 2021-, 2016-2020, 2010-2015),
  so recent years are usable early.
- **Nightly increment** (no ``--from``): the CIKs that are DUE (a filing stored, the latest filed
  at least ``DUE_DAYS`` ago: a report is due every ~91 days) and not asked within ``RECHECK_DAYS``,
  the longest unchecked first (``last_checked``: a CIK that never files again takes its turn like
  the rest), at most ``NIGHTLY_CIKS``. Each is read from its latest STORED filing day, never a fixed
  window, so a CIK reached late loses no filing. With nothing stored it does nothing and the run is
  PARTIAL (a WARN: run the backfill first). A CIK with no filing yet stored is the backfill's.
- **Disk**: the run ends PARTIAL when the store's volume has under ``[sec_edgar]
  filing_text_min_free_gb`` free (default 5). No raw copy is saved (the payload is the extraction
  the rows store).

**known_from** (the one rule of ``events/filing``, EB H4): the acceptance SESSION
(``acceptance_sessions``: an acceptance after the close, on a weekend or a holiday counts from the
next session), never the filing date, the period end or the fetch day. A filing's FIRST extraction
is known from there, backfilled or not. A LATER extraction of a filing that already has stored rows
(a new parser version, an item added to the kept list, ``--force``) is a revision per row: an
item identical to the stored latest (``text`` and ``quality``, NA-safe) keeps the stored row's
``known_from``; one that changed or is new takes ``max(acceptance session, next session after the
exchange date of the run's clock)``, the FETCH's session, never ``--to`` (``_learned_on``), so a
parser change never rewrites history as known earlier. ``known_from`` is in the table key, so a
rewrite that changes a text is a new row beside the old one (a read before its stamp still finds
the old text). Reads take, per item, the latest version known on or before
the session (``data.filing_text``).

**Failure is an item failure**: a listing that fails, a document that 404s or is blocked fails the
CIK (``FETCH_ERROR``); the filings that did succeed are stored and a rerun asks only for the missing
ones. A document that is short or has no item header at all (an exhibit-only 10-K/A), and a
filing SEC lists no primary document for, are stored as one row with a null item (``NO_ITEMS``) or a
``SHORT`` section, never guessed text. Only a listing or a blocked / failing document counts toward
``STOP_AFTER_FAILED`` CIKs in a row (SEC blocking us: the run ends PARTIAL); a CIK that failed
before goes last in a backfill, so one bad filing never starves the others. A day of the form index
that fails, or a gap of more than ``MAX_GAP`` business days without one, fails the run before any
CIK is read.

Items: per CIK ``OK: <from>..<to> (<n> filings)``, ``NO_DATA`` (SEC has no filings for the CIK) or
``FETCH_ERROR``. ``stats``: the window, ``tag``, filers found (and whether from an earlier run),
index days walked / without an index, filings listed / fetched / already stored, rows written,
``revised`` rows (a text stamped later than the acceptance session), ``ids_filled`` rows, rows by
``quality``, and ``pending`` CIKs left.
"""

import shutil
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from functools import partial
from pathlib import Path
from typing import Any

import pandas as pd

from algotrade.core.model.errors import MissingDataError
from algotrade.core.time.calendar import EXCHANGE_TZ, exchange_date, next_session
from algotrade.data.events import acceptance_sessions
from algotrade.data.filing_text.reading import (
    COLUMNS,
    KEY_COLUMNS,
    effective_known_from,
    latest_filing_versions,
    stored_filing_text,
)
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.events.filing_text_filers import (
    CIKS_KEY,
    WINDOW_KEY,
    discover,
    window_label,
)
from algotrade_ingestion.tasks.events.filings import Listed, Names, ciks_of, universe_names
from algotrade_ingestion.tasks.framework.run import (
    FAILURES,
    FETCH_ERROR,
    IngestRun,
    NoResponseError,
    TaskContext,
    finished_runs,
    status_label,
)
from algotrade_sources.framework.base import Source, TransientFetchError
from algotrade_sources.framework.series import (
    FILING_TEXT_COLUMNS,
    FILING_TEXT_FRAME,
    FILINGS_FRAME,
    PERIODIC_FORMS,
    FilingsRequest,
    FilingTextRequest,
    items_for,
)
from algotrade_sources.framework.series import (
    FILING_TEXT_PARSER_VERSION as PARSER_VERSION,
)

TASK = "filing_text"
TABLE = "events/filing_text"  # the table this task owns (architecture/tables.toml)
DUE_DAYS = 60  # a CIK is asked nightly once its latest stored report is this old
NIGHTLY_CIKS = 600  # at most this many due CIKs a night (the longest unchecked first)
RECHECK_DAYS = 3  # a CIK checked within this many days is not asked again by the nightly
MARGIN = timedelta(days=7)  # stored rows are read for a window widened by this (acceptance session)
GB = 1024**3
BACKFILL_CIKS = 100  # CIKs per backfill run when --limit is not given
STOP_AFTER_FAILED = 3  # CIKs failing in a row for a listing or a blocked document end the run
CHECKPOINT_EVERY = 10
DONE = ("OK", "NO_DATA")
ROW_COLUMNS = [*COLUMNS, "method", "session_date"]  # the reader's columns + what the writer stamps


def run_tag(requested: Collection[str]) -> str:
    """What a run stored: the parser version and the items asked (a change to either is a new
    read of every CIK, so coverage by an earlier run does not carry over)."""
    kept = ",".join(sorted(r.strip().upper() for r in requested)) or "default"
    return f"parser={PARSER_VERSION}|items={kept}"


def _window(since: date, until: date) -> str:
    return window_label(since, until)


def _learned_on(run: IngestRun) -> date:
    """The first session strictly after the exchange date of the run's clock: when a revision of
    a stored row becomes known, whatever ``--to`` says (a past ``--to`` is not a past fetch)."""
    return next_session(exchange_date(run.clock()))


def _same(a: object, b: object) -> bool:
    """NA-safe equality: two missing values are the same, one missing is not."""
    if pd.isna(a) and pd.isna(b):  # type: ignore[call-overload]
        return True
    if pd.isna(a) or pd.isna(b):  # type: ignore[call-overload]
        return False
    return bool(a == b)


@dataclass(frozen=True)
class Filing:
    """One periodic report of a CIK from the submissions listing."""

    cik: str
    form: str
    accession: str
    ts: pd.Timestamp  # SEC's acceptance instant, UTC
    filing_date: date
    report_date: date | None
    primary_document: str | None


def listed_filings(frame: pd.DataFrame, since: date, until: date) -> list[Filing]:
    """The periodic filings of a ``FILINGS_FRAME`` filed in ``since..until``, newest first."""
    inside = frame[
        (frame["filing_date"] >= pd.Timestamp(since))
        & (frame["filing_date"] <= pd.Timestamp(until))
    ].sort_values(["acceptance_ts", "accession"], ascending=False, kind="stable")
    accepted = pd.to_datetime(inside["acceptance_ts"], utc=True)
    filed = pd.to_datetime(inside["filing_date"]).dt.date
    period = pd.to_datetime(inside["report_date"]).dt.date
    documents = inside["primary_document"]
    return [
        Filing(
            str(cik),
            str(form),
            str(accession),
            accepted.iloc[i],
            filed.iloc[i],
            None if pd.isna(period.iloc[i]) else period.iloc[i],
            None if pd.isna(documents.iloc[i]) else str(documents.iloc[i]),
        )
        for i, (cik, form, accession) in enumerate(
            zip(inside["cik"], inside["form"], inside["accession"], strict=True)
        )
    ]


def complete_filings(stored: pd.DataFrame, wanted: dict[str, tuple[str, ...]]) -> set[str]:
    """The accessions already held at ``PARSER_VERSION``: a null-item row (nothing to find) or a
    row for each item ``wanted`` for its form (``wanted``: form -> items). ``stored``:
    ``KEY_COLUMNS`` + ``form``."""
    if stored.empty:
        return set()
    now = stored[stored["parser_version"] == PARSER_VERSION]
    done = set()
    for accession, rows in now.groupby("accession", sort=False):
        have = set(rows["item"].dropna())
        form = str(rows["form"].iloc[0])
        if rows["item"].isna().any() or set(wanted.get(form, ())) <= have:
            done.add(str(accession))
    return done


def _key(item: object) -> str | None:
    return None if pd.isna(item) else str(item)  # type: ignore[call-overload]


def _of(frame: pd.DataFrame, key: str | None) -> pd.DataFrame:
    """The rows of one item key (``_slot``) of ``frame``."""
    return frame[[k == key for k in frame["_slot"]]]


def _identified(rows: pd.DataFrame) -> tuple[str, date] | None:
    """The id the latest version carrying one has, and the session the earliest version with that
    id was known from; ``None`` when no version has an id."""
    have = rows[rows["instrument_id"].notna()].sort_values("_known", kind="stable")
    if have.empty:
        return None
    iid = str(have["instrument_id"].iloc[-1])
    return iid, have.loc[have["instrument_id"] == iid, "_known"].min()


def _held(
    prior: pd.DataFrame,
) -> tuple[dict[str | None, tuple[Any, Any, date]], dict[str | None, tuple[str, date]], Any]:
    """What a filing's stored versions (``prior``: every one, with ``text``) say: per item the
    latest version's ``(text, quality, stamp)`` (the stamp the EARLIEST version of that same text
    and quality was known from, never a later id version's), per item its id as ``(id, session
    known from)``, and the id of any item (for a new one)."""
    if prior.empty:
        return {}, {}, None
    versions = prior.assign(
        _known=effective_known_from(prior).dt.date,
        _slot=pd.Series([_key(i) for i in prior["item"]], index=prior.index, dtype=object),
    )
    texts: dict[str | None, tuple[Any, Any, date]] = {}
    ids: dict[str | None, tuple[str, date]] = {}
    for _, row in latest_filing_versions(versions).iterrows():
        mine = _of(versions, row["_slot"])
        same = [
            _same(t, row["text"]) and _same(q, row["quality"])
            for t, q in zip(mine["text"], mine["quality"], strict=True)
        ]
        texts[row["_slot"]] = (row["text"], row["quality"], mine["_known"][same].min())
        if (found := _identified(mine)) is not None:
            ids[row["_slot"]] = found
    return texts, ids, _identified(versions)


def text_rows(
    extracted: pd.DataFrame,
    filing: Filing,
    stored: pd.DataFrame,
    learned_on: date,
    fill_id: str | None = None,
) -> tuple[pd.DataFrame, int]:
    """``ROW_COLUMNS`` rows of one filing's extracted items (module doc: ``known_from``, **Ids**)
    and how many of them are id versions. ``stored``: every stored version of the filing's items
    with ``text`` (none: the first extraction). A row's text is known from its ``known_from``
    (acceptance session first, ``learned_on`` when changed or new, the stored stamp when
    identical); its id (the stored one, else ``fill_id``) from the session it was first stored (a
    new id: ``max(acceptance session, learned_on)``). An id later than its text is a second row of
    the same (cik, accession, item): the text with a NULL id, then with the id."""
    own = acceptance_sessions(pd.Series([filing.ts]))[0]
    prior = stored[(stored["cik"] == filing.cik) & (stored["accession"] == filing.accession)]
    texts, ids, anyone = _held(prior)
    position, known_from, instrument = [], [], []
    filled = 0
    for i, (item, text, quality) in enumerate(
        zip(extracted["item"], extracted["text"], extracted["quality"], strict=True)
    ):
        key = _key(item)
        if prior.empty:
            known = own
        elif key in texts and _same(texts[key][0], text) and _same(texts[key][1], quality):
            known = max(own, texts[key][2])  # unchanged: knowable as it was
        else:
            known = max(own, learned_on)  # changed or new: from the fetch's session
        found = ids.get(key) or anyone
        if found is None and fill_id is not None:
            found = (fill_id, max(own, learned_on))
        position.append(i)
        known_from.append(known)
        instrument.append(found[0] if found is not None and found[1] <= known else None)
        if found is not None and found[1] > known:  # the id comes later than the text
            position.append(i)
            known_from.append(found[1])
            instrument.append(found[0])
            filled += 1
    out = extracted.iloc[position].assign(
        instrument_id=pd.Series(instrument, index=range(len(position)), dtype=object).to_numpy(),
        known_from=known_from,
        ts=filing.ts,
        cik=filing.cik,
        form=filing.form,
        accession=filing.accession,
        filing_date=filing.filing_date,
        report_date=filing.report_date,
        session_date=own,
    )
    for column in ("text", "item", "reason", "instrument_id"):
        out[column] = out[column].astype(object).where(out[column].notna(), None)
    return out[ROW_COLUMNS].reset_index(drop=True), filled


def stored_versions(run: IngestRun, cik: str, session: date) -> pd.DataFrame:
    """Every stored version (with ``text``) of one CIK's filings accepted in ``session``: one
    acceptance-session partition, read when a filing that already has rows is read again."""
    return stored_filing_text(
        run.reader, None, (*KEY_COLUMNS, "text"), start=session, end=session, ciks=[cik]
    )


def latest_filing_day(stored: pd.DataFrame) -> dict[str, date]:
    """CIK -> the New York date of its latest stored acceptance."""
    if stored.empty:
        return {}
    local = pd.to_datetime(stored["ts"], utc=True).dt.tz_convert(EXCHANGE_TZ).dt.date
    return {str(i): d for i, d in local.groupby(stored["cik"]).max().items()}


def last_checked(runs: Sequence[RunRecord]) -> dict[str, date]:
    """CIK -> the session of the latest finished run that asked for it (any outcome: a CIK that
    failed is not first in line the next night, and one that never files again takes its turn)."""
    out: dict[str, date] = {}
    for record in sorted(runs, key=lambda r: r.session_date):
        for key in record.items:
            if not key.startswith("sym:"):
                out[key] = record.session_date
    return out


def failed_before(runs: Sequence[RunRecord]) -> set[str]:
    """CIKs whose latest recorded item is a failure: a backfill puts them last, so one bad filing
    never keeps good CIKs from their turn."""
    state: dict[str, bool] = {}
    for record in sorted(runs, key=lambda r: (r.started_at, r.run_id)):
        for key, status in record.items.items():
            state[key] = status_label(status) in FAILURES
    return {k for k, bad in state.items() if bad}


def due_ciks(stored: pd.DataFrame, checked: dict[str, date], session: date) -> dict[str, date]:
    """The CIKs the nightly asks -> the date to read from: a report stored, the latest filed at
    least ``DUE_DAYS`` before ``session``, not asked within ``RECHECK_DAYS``; the longest unchecked
    first, at most ``NIGHTLY_CIKS``. Each is read from its latest STORED filing day, never a fixed
    window, so a CIK reached late loses no filing."""
    rows = []
    for cik, newest in latest_filing_day(stored).items():
        looked = checked.get(cik)
        if newest <= session - timedelta(days=DUE_DAYS) and (
            looked is None or looked <= session - timedelta(days=RECHECK_DAYS)
        ):
            rows.append((looked or date.min, newest, cik))
    rows.sort()
    return {cik: newest for _, newest, cik in rows[:NIGHTLY_CIKS]}


def free_gb(path: Path) -> float:
    """Free space on the volume holding ``path`` (GB)."""
    return shutil.disk_usage(path).free / GB


def store_path(ctx: TaskContext) -> Path | None:
    """Where the local store lives (None for a store with no directory: memory)."""
    root = getattr(ctx.writer.backend.tables, "root", None)
    return root if isinstance(root, Path) and root.exists() else None


def no_document(filing: Filing) -> pd.DataFrame:
    """The frame of a filing SEC lists no primary document for: one ``NO_ITEMS`` row saying so."""
    row = {
        "item": None,
        "text": None,
        "char_count": 0,
        "quality": "NO_ITEMS",
        "reason": "SEC lists no primary document",
        "method": "none",
        "parser_version": PARSER_VERSION,
    }
    return pd.DataFrame([row], columns=list(FILING_TEXT_COLUMNS))


def read_done(runs: Sequence[RunRecord], tag: str, since: date, until: date) -> set[str]:
    """CIKs an earlier finished run of the same ``tag`` read OK for ``since..until`` or a wider
    window (item ``OK: <from>..<to> (...)``)."""
    done: set[str] = set()
    for record in runs:
        if record.stats.get("tag") != tag:
            continue
        for cik, status in record.items.items():
            label, _, rest = status.partition(": ")
            first, _, last = rest.split(" ")[0].partition("..")
            if (
                label in DONE
                and first
                and last
                and first <= since.isoformat()
                and last >= until.isoformat()
            ):
                done.add(cik)
    return done


class Counts:
    """What a run did, for ``stats``."""

    def __init__(self) -> None:
        self.listed = self.fetched = self.skipped = self.rows = self.revised = self.filled = 0
        self.quality: dict[str, int] = {}
        self.blocked = False  # this CIK's failure was the listing or a blocked document


def _blocking(exc: Exception) -> bool:
    """Whether ``exc`` says SEC is blocking or failing us (a block page, a request given up on,
    which carries the last HTTP ``status``), not that this one document is bad (a 404, a parse)."""
    return isinstance(exc, TransientFetchError) or hasattr(exc, "status")


def _document(text: Source, request: FilingTextRequest) -> pd.DataFrame:
    """One document's item frame. No raw copy is saved (``IngestRun.fetch`` would): the payload is
    the extraction the rows below store, so a copy is the table again, and the disk is short. A
    404 raises ``LookupError``, a block or a server failure ``TransientFetchError`` /
    ``GaveUpError``."""
    payload = text.fetch(request)
    if payload is None:
        raise LookupError("SEC has no such document (404)")
    normalized = text.normalize(request, payload)
    assert normalized is not None
    frame: pd.DataFrame = normalized.parsed[FILING_TEXT_FRAME]
    return frame


def _one_cik(
    run: IngestRun,
    listing: Source,
    text: Source,
    cik: str,
    names: list[Listed],
    window: tuple[date, date],
    requested: Sequence[str],
    force: bool,
    held: dict[str, Any],
    counts: Counts,
) -> str:
    """One CIK's periodic filings in ``window``: list, fetch each not already stored, stage
    their rows -> the item status. ``names``: the CIK's instruments in the run's universe (none for
    a delisted or never-listed filer): the id of the rows (module doc, **Ids**)."""
    since, until = window
    counts.blocked = False
    try:
        normalized = run.fetch(
            listing,
            FilingsRequest(key=cik, session_date=run.session, since=since, forms=PERIODIC_FORMS),
        )
    except NoResponseError:
        return f"NO_DATA: {_window(since, until)} (SEC has no filings for this CIK)"
    except Exception:
        counts.blocked = True
        raise
    assert normalized is not None
    filings = listed_filings(normalized.parsed[FILINGS_FRAME], since, until)
    fill_id = min((n.instrument_id for n in names), default=None)
    counts.listed += len(filings)
    wanted = {f.form: items_for(f.form, requested) for f in filings}
    complete = set() if force else complete_filings(held["keys"].get(cik, held["empty"]), wanted)
    failures: list[str] = []
    for filing in filings:
        if filing.accession in complete:
            counts.skipped += 1
            continue
        try:
            if filing.primary_document is None:
                extracted = no_document(filing)
            else:
                request = FilingTextRequest(
                    key=filing.accession,
                    session_date=run.session,
                    cik=cik,
                    form=filing.form,
                    primary_document=filing.primary_document,
                    items=tuple(requested),
                )
                extracted = _document(text, request)
                counts.fetched += 1
            seen = filing.accession in set(held["keys"].get(cik, held["empty"])["accession"])
            prior = stored_versions(run, cik, _acceptance(filing)) if seen else held["empty_text"]
            rows, filled = text_rows(extracted, filing, prior, _learned_on(run), fill_id)
        except Exception as exc:  # one filing failing must not drop the others
            counts.blocked |= _blocking(exc)
            failures.append(f"{filing.accession}: {exc}")
            continue
        counts.rows += len(rows)
        counts.filled += filled
        counts.revised += (
            int((pd.to_datetime(rows["known_from"]) > pd.to_datetime(rows["session_date"])).sum())
            - filled
        )
        for quality, n in rows["quality"].value_counts().items():
            counts.quality[str(quality)] = counts.quality.get(str(quality), 0) + int(n)
        run.stage_sessions(TABLE, filing.accession, rows, text.name)
    if failures:
        return (
            f"{FETCH_ERROR}: {len(failures)} of {len(filings)} filings failed, first {failures[0]}"
        )
    return f"OK: {_window(since, until)} ({len(filings)} filings)"


def _acceptance(filing: Filing) -> date:
    """The acceptance session of a filing: the partition its rows are in."""
    return date.fromisoformat(str(acceptance_sessions(pd.Series([filing.ts]))[0]))


@dataclass(frozen=True)
class Plan:
    """The CIKs a run asks (``todo``), the window of each, and the counts for ``stats``."""

    todo: dict[str, list[Listed]]
    windows: dict[str, tuple[date, date]]
    skipped: int
    pending: int


def _select(
    run: IngestRun,
    candidates: Sequence[str] | None,
    names: dict[str, list[Listed]],
    runs: Sequence[RunRecord],
    session: date,
    since: date | None,
    until: date,
    limit: int | None,
    force: bool,
    tag: str,
) -> Plan:
    """The nightly's due CIKs (each from its latest stored filing), or the backfill's CIKs not yet
    read for the window (failed ones last, ``limit`` of them). ``candidates``: the backfill's
    filers; for the nightly the CIKs it may ask (``None``: every stored one)."""
    if since is None:
        known = stored_filing_text(run.reader, None, ("cik", "ts"), ciks=candidates)
        if known.empty:
            run.partial("nothing stored yet: run the backfill (--from)")
        due = due_ciks(known, last_checked(runs), session)
        return Plan(
            {cik: names.get(cik, []) for cik in due},
            {cik: (start, until) for cik, start in due.items()},
            0,
            0,
        )
    done = set() if force else read_done(runs, tag, since, until)
    bad = failed_before(runs)
    left = [c for c in (candidates or ()) if c not in done]
    left.sort(key=lambda c: c in bad)  # failed ones last (stable: the index order otherwise)
    cap = limit or BACKFILL_CIKS
    todo = left[:cap]
    return Plan(
        {c: names.get(c, []) for c in todo},
        dict.fromkeys(todo, (since, until)),
        len(candidates or ()) - len(left),
        max(0, len(left) - cap),
    )


def _universe(run: IngestRun, requested: Sequence[str]) -> tuple[Names, dict[str, list[Listed]]]:
    """The universe's operating companies (``--symbols`` narrows) and their CIKs. A run with no
    universe snapshot has none (the filers need none; only ``--symbols`` does)."""
    try:
        covered = universe_names(run, requested)
    except MissingDataError:
        if requested:
            raise
        return Names([], 0, []), {}
    return covered, ciks_of(run, covered.listed)


def ingest_filing_text(
    ctx: TaskContext,
    listing: Source,
    text: Source,
    index: Source,
    session: date,
    requested_symbols: Sequence[str] = (),
    since: date | None = None,
    until: date | None = None,
    limit: int | None = None,
    items: Sequence[str] = (),
    force: bool = False,
) -> RunRecord:
    """Store the item sections of the periodic filings of every filer (module doc): the backfill
    window ``since..until`` (the filers of the daily index, ``--limit`` CIKs a run), or, without
    ``since``, the nightly increment of the due CIKs."""
    until = until or session
    if since is not None and until < since:
        raise ValueError(f"--to {until} is before --from {since}")
    tag = run_tag(items)
    with IngestRun(ctx, TASK, session) as run:
        covered, names = _universe(run, requested_symbols)
        for symbol in covered.unknown:
            run.record_item(f"sym:{symbol}", "UNKNOWN: not in the universe")
        runs = finished_runs(run.writer, TASK)
        nightly = since is None
        found = None
        if requested_symbols:  # a targeted read: those tickers' CIKs, no index walk
            candidates: list[str] | None = list(names)
        elif nightly:
            candidates = None
        else:
            assert since is not None
            found = discover(run, index, runs, since, until)
            candidates = found.ciks
            if not found.cached:
                run.stats.update({WINDOW_KEY: _window(since, until), CIKS_KEY: found.ciks})
        counts = Counts()
        plan = _select(run, candidates, names, runs, session, since, until, limit, force, tag)
        todo, windows = plan.todo, plan.windows
        starts = [w[0] for w in windows.values()]
        low, high = (min(starts), until) if starts else (until, until)
        window = (low, high)
        start, end = low - MARGIN, high + MARGIN
        empty = pd.DataFrame({c: [] for c in (*KEY_COLUMNS, "form")})
        keys = stored_filing_text(
            run.reader, None, (*KEY_COLUMNS, "form"), start=start, end=end, ciks=list(todo)
        )
        by_cik = {str(c): g for c, g in keys.groupby("cik")} if len(keys) else {}
        empty_text = pd.DataFrame({c: [] for c in (*KEY_COLUMNS, "text")})
        held = {"keys": by_cik, "empty": empty, "empty_text": empty_text}
        floor, path = ctx.settings.sec_filing_text_min_free_gb, store_path(ctx)
        blocked_in_a_row = 0
        for i, (cik, group) in enumerate(todo.items(), 1):
            if path is not None and (free := free_gb(path)) < floor:
                run.partial(
                    f"stopped: {free:.1f} GB free is under {floor:g} GB "
                    "(sources.toml [sec_edgar] filing_text_min_free_gb)"
                )
                break
            args = (run, listing, text, cik, group, windows[cik], items, force, held, counts)
            status = run.attempt(cik, partial(_one_cik, *args))
            failed = status_label(status) == FETCH_ERROR and counts.blocked
            blocked_in_a_row = blocked_in_a_row + 1 if failed else 0
            if i % CHECKPOINT_EVERY == 0:
                run.checkpoint()
            if blocked_in_a_row >= STOP_AFTER_FAILED:
                run.partial(f"stopped: {blocked_in_a_row} CIKs failed in a row ({status})")
                break
        published = run.publish_sessions(TABLE)
        run.stats.update(
            mode="nightly" if nightly else "backfill",
            window=_window(*window),
            tag=tag,
            filers=len(candidates) if candidates is not None else None,
            filers_cached=found.cached if found else None,
            index_days=found.days if found else None,
            index_days_unpublished=len(found.unpublished) if found else None,
            names=len(covered.listed),
            ciks=len(todo),
            skipped_covered=plan.skipped,
            pending=plan.pending,
            filings_listed=counts.listed,
            filings_fetched=counts.fetched,
            filings_already_stored=counts.skipped,
            rows=sum(published.values()),
            sessions_written=len(published),
            revised=counts.revised,
            ids_filled=counts.filled,
            quality=counts.quality,
            learned_on=_learned_on(run).isoformat(),
            unknown_symbols=covered.unknown,
            items=run.counts(),
        )
    return run.record
