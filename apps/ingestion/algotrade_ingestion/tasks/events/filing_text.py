"""The ``filing-text`` task: the item sections of every 10-K / 10-Q (and 10-K/A, 10-Q/A) of the
universe's operating companies -> ``events/filing_text`` (edge build D10; Lazy Prices, risk-factor
change, MD&A tone; the similarity features are track E, this is the text).

**Per CIK**: the filing list is the ``sec_filings`` source read with the periodic forms
(``PERIODIC_FORMS``; one submissions request per CIK, the older pages when ``--from`` precedes the
recent block), then one document request per filing to ``sec_filing_text`` (the primary document,
parsed and dropped: only the items are stored, ``vendors/sec_text/filing_items.py``; kept items
per form by default ``DEFAULT_10K`` / ``DEFAULT_10Q``, ``--items`` narrows or widens). Names are the
session's universe snapshot minus the funds, each CIK from ``instruments/company`` as of the
session (``events/filings.py``'s ``universe_names`` / ``ciks_of``: the same names as the 8-K
history, share classes of one CIK get a row set each from one fetch). Rows carry the stable FIGI
instrument id; no ticker is resolved, so a recycled ticker never names another company.

**Two modes**, one row shape:

- **Backfill** (``--from`` [``--to``]): the CIKs not yet read for the window, ``--limit`` of them a
  run (default ``BACKFILL_CIKS``: a run is one published unit held in memory). A CIK read OK from
  a window that covers this one by an earlier run of the same ``TAG`` (parser version + items) is
  skipped, so the loop restarts where it stopped. Within a CIK the newest filing goes first. History
  from 2010: run the windows newest first (``README.md`` "Long runs": 2021-, 2016-2020, 2010-2015),
  so recent years are usable early.
- **Nightly increment** (no ``--from``): the last ``LOOKBACK_DAYS`` days for the CIKs that are DUE
  (a filing stored, the latest older than ``DUE_DAYS``: a report is due every ~91 days), at most
  ``NIGHTLY_CIKS``, oldest first. With nothing stored it does nothing and the run is PARTIAL
  (a WARN: run the backfill first). A CIK with no filing yet stored is the backfill's.

**known_from** (the one rule of ``events/filing``, EB H4): the acceptance SESSION
(``acceptance_sessions``: an acceptance after the close, on a weekend or a holiday counts from the
next session), never the filing date, the period end or the fetch day. A filing's FIRST extraction
is known from there, backfilled or not. A LATER extraction of a filing that already has stored rows
(a new parser version, an item added to the kept list, ``--force``) is a revision per row: an
item identical to the stored latest (``text`` and ``quality``, NA-safe) keeps the stored row's
``known_from``; one that changed or is new takes ``max(acceptance session, next session after the
exchange date of the run's clock)``, the FETCH's session, never ``--to`` (``_learned_on``), so a
parser change never rewrites history as known earlier. A same-version rewrite of a changed item
replaces its row (the key has no ``knowledge_ts``) and its earlier text is not served: the cost of
the key, as for ``events/fund_nav``. Reads take, per item, the latest version known on or before
the session (``data.filing_text``).

**Failure is an item failure**: a listing that fails, a document that 404s, is blocked, is too
short or holds no text fails the CIK (``FETCH_ERROR``); the filings that did succeed are stored
and a rerun asks only for the missing ones. A document with no item header at all is stored as one
row with a null item (``NO_ITEMS``), never guessed text. ``STOP_AFTER_FAILED`` CIKs failing in a
row end the run PARTIAL (SEC blocking us).

Items: per CIK ``OK: <from>..<to> (<n> filings)``, ``NO_DATA`` (SEC has no filings for the CIK) or
``FETCH_ERROR``. ``stats``: the window, ``tag``, filings listed / fetched / already stored, rows
written, ``revised`` rows (a stamp later than the acceptance session), rows by ``quality``, and
``pending`` CIKs left.
"""

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from functools import partial
from typing import Any

import pandas as pd

from algotrade.core.time.calendar import EXCHANGE_TZ, exchange_date, next_session
from algotrade.data.events import acceptance_sessions
from algotrade.data.filing_text.reading import (
    COLUMNS,
    KEY_COLUMNS,
    latest_filing_versions,
    stored_filing_text,
)
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.events.filings import Listed, ciks_of, universe_names
from algotrade_ingestion.tasks.framework.run import (
    FETCH_ERROR,
    IngestRun,
    NoResponseError,
    TaskContext,
    finished_runs,
    status_label,
)
from algotrade_sources.framework.base import Source
from algotrade_sources.framework.series import (
    FILING_TEXT_PARSER_VERSION as PARSER_VERSION,
)
from algotrade_sources.framework.series import (
    FILINGS_FRAME,
    PERIODIC_FORMS,
    FilingsRequest,
    FilingTextRequest,
    items_for,
)

TASK = "filing_text"
TABLE = "events/filing_text"  # the table this task owns (architecture/tables.toml)
LOOKBACK_DAYS = 14  # the nightly window
DUE_DAYS = 60  # a CIK is asked nightly once its latest stored report is this old
NIGHTLY_CIKS = 600  # at most this many due CIKs a night (oldest first)
BACKFILL_CIKS = 100  # CIKs per backfill run when --limit is not given
STOP_AFTER_FAILED = 3  # CIKs failing in a row end the run
CHECKPOINT_EVERY = 10
DONE = ("OK", "NO_DATA")
ROW_COLUMNS = [*COLUMNS, "method", "session_date"]  # the reader's columns + what the writer stamps


def run_tag(requested: Collection[str]) -> str:
    """What a run stored: the parser version and the items asked (a change to either is a new
    read of every CIK, so coverage by an earlier run does not carry over)."""
    kept = ",".join(sorted(r.strip().upper() for r in requested)) or "default"
    return f"parser={PARSER_VERSION}|items={kept}"


def _window(since: date, until: date) -> str:
    return f"{since.isoformat()}..{until.isoformat()}"


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


def complete_filings(
    stored: pd.DataFrame, wanted: dict[str, tuple[str, ...]], ids: Sequence[str]
) -> set[str]:
    """The accessions every one of ``ids`` already holds at ``PARSER_VERSION``: a null-item row
    (nothing to find) or a row for each item ``wanted`` for its form (``wanted``: form -> items).
    ``stored``: ``KEY_COLUMNS`` + ``form``."""
    if stored.empty:
        return set()
    now = stored[stored["parser_version"] == PARSER_VERSION]
    have: dict[tuple[str, str], tuple[set[str], bool, str]] = {}
    for (iid, accession), rows in now.groupby(["instrument_id", "accession"], sort=False):
        have[(str(iid), str(accession))] = (
            set(rows["item"].dropna()),
            bool(rows["item"].isna().any()),
            str(rows["form"].iloc[0]),
        )

    def holds(iid: str, accession: str) -> bool:
        found = have.get((iid, accession))
        return found is not None and (found[1] or set(wanted.get(found[2], ())) <= found[0])

    return {a for _, a in have if all(holds(i, a) for i in ids)}


def text_rows(
    extracted: pd.DataFrame,
    filing: Filing,
    instrument_ids: Sequence[str],
    stored: pd.DataFrame,
    learned_on: date,
) -> pd.DataFrame:
    """``ROW_COLUMNS`` rows of one filing's extracted items for each instrument (module doc:
    ``known_from``). ``stored``: the LATEST stored version of each (instrument, accession, item)
    with ``text`` (``latest_filing_versions``); an instrument with none for this accession is on its
    first extraction."""
    own = acceptance_sessions(pd.Series([filing.ts]))[0]
    parts = []
    for iid in instrument_ids:
        prior = stored[(stored["instrument_id"] == iid) & (stored["accession"] == filing.accession)]
        before = {
            (None if pd.isna(i) else str(i)): (t, q)
            for i, t, q in zip(prior["item"], prior["text"], prior["quality"], strict=True)
        }
        stamp = dict(
            zip(
                ((None if pd.isna(i) else str(i)) for i in prior["item"]),
                prior["known_from"],
                strict=True,
            )
        )
        known = []
        for item, text, quality in zip(
            extracted["item"], extracted["text"], extracted["quality"], strict=True
        ):
            key = None if pd.isna(item) else str(item)
            if prior.empty:
                known.append(own)
            elif key in before and _same(before[key][0], text) and _same(before[key][1], quality):
                known.append(max(own, stamp[key]))  # unchanged: knowable as it was
            else:
                known.append(max(own, learned_on))  # changed or new: from the fetch's session
        parts.append(
            extracted.assign(
                instrument_id=iid,
                ts=filing.ts,
                known_from=known,
                cik=filing.cik,
                form=filing.form,
                accession=filing.accession,
                filing_date=filing.filing_date,
                report_date=filing.report_date,
                session_date=own,
            )
        )
    out = pd.concat(parts, ignore_index=True)
    out["text"] = out["text"].astype(object).where(out["text"].notna(), None)
    out["item"] = out["item"].astype(object).where(out["item"].notna(), None)
    out["reason"] = out["reason"].astype(object).where(out["reason"].notna(), None)
    return out[ROW_COLUMNS]


def stored_latest(run: IngestRun, ids: Sequence[str]) -> pd.DataFrame:
    """The latest stored version of each item of ``ids`` (with ``text``), every ``known_from``."""
    stored = stored_filing_text(run.reader, ids, (*KEY_COLUMNS, "text"))
    return latest_filing_versions(stored) if len(stored) else stored


def due_ciks(
    ciks: dict[str, list[Listed]], stored: pd.DataFrame, session: date
) -> dict[str, list[Listed]]:
    """The CIKs the nightly asks: a report stored, the latest accepted (New York date) at least
    ``DUE_DAYS`` before ``session``, oldest first, at most ``NIGHTLY_CIKS``."""
    if stored.empty:
        return {}
    local = pd.to_datetime(stored["ts"], utc=True).dt.tz_convert(EXCHANGE_TZ).dt.date
    last = local.groupby(stored["instrument_id"]).max()
    latest = {
        cik: max(last[n.instrument_id] for n in names if n.instrument_id in last.index)
        for cik, names in ciks.items()
        if any(n.instrument_id in last.index for n in names)
    }
    due = sorted((d, cik) for cik, d in latest.items() if d <= session - timedelta(days=DUE_DAYS))
    return {cik: ciks[cik] for _, cik in due[:NIGHTLY_CIKS]}


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
        self.listed = self.fetched = self.skipped = self.rows = self.revised = 0
        self.quality: dict[str, int] = {}


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
    their rows -> the item status."""
    since, until = window
    try:
        normalized = run.fetch(
            listing,
            FilingsRequest(key=cik, session_date=run.session, since=since, forms=PERIODIC_FORMS),
        )
    except NoResponseError:
        return f"NO_DATA: {_window(since, until)} (SEC has no filings for this CIK)"
    assert normalized is not None
    filings = listed_filings(normalized.parsed[FILINGS_FRAME], since, until)
    ids = [n.instrument_id for n in names]
    counts.listed += len(filings)
    wanted = {f.form: items_for(f.form, requested) for f in filings}
    complete = set() if force else complete_filings(held["keys"], wanted, ids)
    failures: list[str] = []
    for filing in filings:
        if filing.accession in complete:
            counts.skipped += 1
            continue
        try:
            if filing.primary_document is None:
                raise ValueError("SEC lists no primary document")
            got = run.fetch(
                text,
                FilingTextRequest(
                    key=filing.accession,
                    session_date=run.session,
                    cik=cik,
                    form=filing.form,
                    primary_document=filing.primary_document,
                    items=tuple(requested),
                ),
            )
            assert got is not None
            counts.fetched += 1
            rows = text_rows(
                got.parsed["filing_text"], filing, ids, held["latest"](), _learned_on(run)
            )
        except Exception as exc:  # one filing failing must not drop the others
            failures.append(f"{filing.accession}: {exc}")
            continue
        counts.rows += len(rows)
        counts.revised += int(
            (pd.to_datetime(rows["known_from"]) > pd.to_datetime(rows["session_date"])).sum()
        )
        for quality, n in rows["quality"].value_counts().items():
            counts.quality[str(quality)] = counts.quality.get(str(quality), 0) + int(n)
        run.stage_sessions(TABLE, filing.accession, rows, text.name)
    if failures:
        return (
            f"{FETCH_ERROR}: {len(failures)} of {len(filings)} filings failed, first {failures[0]}"
        )
    return f"OK: {_window(since, until)} ({len(filings)} filings)"


def ingest_filing_text(
    ctx: TaskContext,
    listing: Source,
    text: Source,
    session: date,
    requested_symbols: Sequence[str] = (),
    since: date | None = None,
    until: date | None = None,
    limit: int | None = None,
    items: Sequence[str] = (),
    force: bool = False,
) -> RunRecord:
    """Store the item sections of the periodic filings of the universe's operating companies
    (module doc): the backfill window ``since..until`` (``--limit`` CIKs a run), or, without
    ``since``, the nightly increment of the due CIKs."""
    until = until or session
    if since is not None and until < since:
        raise ValueError(f"--to {until} is before --from {since}")
    tag = run_tag(items)
    with IngestRun(ctx, TASK, session) as run:
        covered = universe_names(run, requested_symbols)
        for symbol in covered.unknown:
            run.record_item(f"sym:{symbol}", "UNKNOWN: not in the universe")
        ciks = ciks_of(run, covered.listed)
        nightly = since is None
        counts = Counts()
        every = [n.instrument_id for group in ciks.values() for n in group]
        if nightly:
            window = (session - timedelta(days=LOOKBACK_DAYS), session)
            known = stored_filing_text(run.reader, every, ("instrument_id", "ts"))
            todo = due_ciks(ciks, known, session)
            if known.empty:
                run.partial("nothing stored yet: run the backfill (--from)")
            skipped, pending = 0, 0
        else:
            assert since is not None
            window = (since, until)
            done = set() if force else read_done(finished_runs(run.writer, TASK), tag, since, until)
            left = {c: n for c, n in ciks.items() if c not in done}
            skipped, pending = len(ciks) - len(left), max(0, len(left) - (limit or BACKFILL_CIKS))
            todo = dict(list(left.items())[: limit or BACKFILL_CIKS])
        ids = [n.instrument_id for group in todo.values() for n in group]
        keys = stored_filing_text(run.reader, ids, (*KEY_COLUMNS, "form"))
        cache: dict[str, pd.DataFrame] = {}

        def latest() -> pd.DataFrame:  # the text of what is stored: read once, only when needed
            if "frame" not in cache:
                cache["frame"] = (
                    stored_latest(run, ids)
                    if len(keys)
                    else pd.DataFrame({c: [] for c in (*KEY_COLUMNS, "text")})
                )
            return cache["frame"]

        held = {"keys": keys, "latest": latest}
        failed_in_a_row = 0
        for i, (cik, group) in enumerate(todo.items(), 1):
            status = run.attempt(
                cik,
                partial(
                    _one_cik, run, listing, text, cik, group, window, items, force, held, counts
                ),
            )
            failed_in_a_row = failed_in_a_row + 1 if status_label(status) == FETCH_ERROR else 0
            if i % CHECKPOINT_EVERY == 0:
                run.checkpoint()
            if failed_in_a_row >= STOP_AFTER_FAILED:
                run.partial(f"stopped: {failed_in_a_row} CIKs failed in a row ({status})")
                break
        published = run.publish_sessions(TABLE)
        run.stats.update(
            mode="nightly" if nightly else "backfill",
            window=_window(*window),
            tag=tag,
            names=len(covered.listed),
            ciks=len(todo),
            skipped_covered=skipped,
            pending=pending,
            filings_listed=counts.listed,
            filings_fetched=counts.fetched,
            filings_already_stored=counts.skipped,
            rows=sum(published.values()),
            sessions_written=len(published),
            revised=counts.revised,
            quality=counts.quality,
            learned_on=_learned_on(run).isoformat(),
            unknown_symbols=covered.unknown,
            items=run.counts(),
        )
    return run.record
