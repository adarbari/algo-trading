"""The ``ipo-lockups`` task: IPO facts and lock-up expiry dates from EDGAR 424B4 final
prospectuses -> ``events/ipo_lockup`` (ADR 0050, edge build D8; EDGAR only: Nasdaq's terms forbid
automated capture, so its IPO calendar is not used).

**Which prospectuses**: EDGAR full-text search (``sec_prospectus_search``) lists the 424B4 filings
that mention a lock-up, one request a calendar month of the window (pages of 100). It is the only
list by form across issuers, so a company in no universe (a new IPO, one since delisted) is
covered; the universe-bound ``events/filing`` 424B4 rows are not the source. A month that fails
is an item (``win:YYYY-MM``) and the others still run.

**What is read**: per prospectus, the issuer's submissions (``sec_filings``, one request per CIK
and run: the acceptance instant and the main document's name; ``events/filing`` is not read) and
the document itself (``sec_prospectus``, fetched once: fair access, 10 requests/second), whose
facts the source extracts (``sec_prospectus/prospectus.py`` holds the rules and their failure modes:
a fact the text does not state is null with ``extraction`` and ``reason``, never guessed). A 424B4
that is not an IPO (a follow-on, a note offering) is stored too, ``NOT_IPO``: it is not read twice.

**The row** (``events/ipo_lockup``, one per ``cik`` + ``accession``): ``ts`` the acceptance
instant; ``known_from`` the session of the acceptance (``core.time.calendar.acceptance_session``:
an after-close acceptance counts from the next session); ``lockup_days``
and ``lockup_expiry`` from the prospectus date and the term (``lockup_dates``: the first session
after the last restricted day), both null unless ``extraction`` is ``EXTRACTED`` and the text has a
prospectus date. ``instrument_id`` of a first version is always null: the backfill runs on
today's universe while the row is known from an old session, so an id there would exist only for
issuers that survived. Each run stages the id as a version of its own (``fill_instruments``,
known from ``restated_known_from``, no fetch): the universe instrument of the issuer's CIK in the
run session's snapshot (``instruments/company``; of several share classes the one whose symbol
is the prospectus ticker, through the ``SymbolResolver``). A reader maps a CIK to an instrument
through ``instruments/company`` as of its own session.

**Versions** (point in time): a row first stored is known from its acceptance session whenever it
is found (a backfill is not "known today"). A row read again whose facts changed
(or whose id was found) is written as a new version with ``known_from`` = the later of
its acceptance session and the session after the fetch's exchange date (``restated_known_from``:
the run's own clock, never ``--until``); an identical row writes nothing, and one only the rules
version moved for is restaged under its own ``known_from`` (no new version). Readers keep the rows
known by their session and the latest of each key (``data.events.latest_versions``).

**Runs**: with no ``--since`` the window is the 30 days before the session (the nightly: a
prospectus already stored is skipped, so only new ones cost a request). ``--since 2005-01-01`` is
the backfill (EDGAR full-text search starts in 2001): it skips every prospectus already stored at
the current rules version, so it is resumable, ``--limit N`` caps the prospectuses read a run
(oldest first), and it can be repeated or run detached (README "Long runs"). Items:
``win:<month>`` (``OK: n hits``), ``acc:<accession>`` (``OK: <extraction>``, ``UNCHANGED``,
``NO_DATA`` when the submissions or the document are not served, ``FETCH_ERROR``) and ``ids``
(``OK: n``).
"""

from dataclasses import dataclass
from datetime import date, timedelta
from functools import partial
from typing import Any

import pandas as pd

from algotrade.core.model.errors import MissingDataError
from algotrade.core.model.instruments import pad_cik
from algotrade.data.events import ALL_TIME, latest_versions
from algotrade.data.reference import companies, load_universe
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.events.lockup_dates import acceptance_session, restated_known_from
from algotrade_ingestion.tasks.events.lockup_rows import (
    KEY,
    RULES_VERSION,
    Hit,
    as_frame,
    build_row,
    hits_of,
    same_values,
)
from algotrade_ingestion.tasks.framework.run import IngestRun, NoResponseError, TaskContext
from algotrade_sources.framework.base import Normalized, Source
from algotrade_sources.framework.series import (
    FILINGS_FRAME,
    HITS_FRAME,
    IPO_FRAME,
    FilingsRequest,
    ProspectusRequest,
    ProspectusSearchRequest,
)

TASK = "ipo_lockups"
TABLE = "events/ipo_lockup"  # the table this task owns (architecture/tables.toml)
FORM = "424B4"
LOOKBACK_DAYS = 30  # the default window: the nightly reads the last month's prospectuses
CHECKPOINT_EVERY = 25
WINDOW_PREFIX, ACCESSION_PREFIX = "win:", "acc:"


@dataclass(frozen=True)
class Issuers:
    """CIK (10 digits) -> the universe instruments (id, symbol) it holds as of the session."""

    by_cik: dict[str, list[tuple[str, str]]]
    available: bool


def months_between(start: date, end: date) -> list[tuple[date, date]]:
    """Calendar-month windows ``(first, last)`` covering ``start..end``, clipped to it."""
    out, day = [], date(start.year, start.month, 1)
    while day <= end and start <= end:
        following = date(day.year + day.month // 12, day.month % 12 + 1, 1)
        out.append((max(day, start), min(following - timedelta(1), end)))
        day = following
    return out


def issuers(run: IngestRun) -> Issuers:
    """The universe's CIKs as of the run session (``instruments/company`` on or before it);
    empty and ``available`` false when no snapshot of either is stored (ids stay null)."""
    try:
        universe = load_universe(run.reader, run.session).frame
    except MissingDataError:  # no universe snapshot: the facts are still worth storing
        return Issuers({}, False)
    company = companies(run.reader, run.session, [str(i) for i in universe["instrument_id"]])
    if company is None or company.empty or "cik" not in company.columns:
        return Issuers({}, False)
    symbols = dict(
        zip(universe["instrument_id"].astype(str), universe["symbol"].astype(str), strict=True)
    )
    out: dict[str, list[tuple[str, str]]] = {}
    for iid, cik in zip(company["instrument_id"].astype(str), company["cik"], strict=True):
        if (padded := pad_cik(cik)) and iid in symbols:
            out.setdefault(padded, []).append((iid, symbols[iid]))
    return Issuers(out, True)


def instrument_for(run: IngestRun, known: Issuers, cik: str, ticker: str | None) -> str | None:
    """The universe instrument of ``cik``: its only one, else the one the prospectus ticker
    resolves to among them (through the ``SymbolResolver``), else null."""
    held = known.by_cik.get(cik, [])
    if len(held) == 1:
        return held[0][0]
    if len(held) > 1 and ticker:
        try:
            resolved, _ = run.resolver().resolve(
                pd.DataFrame({"symbol": [ticker.replace("-", ".")]})
            )
        except MissingDataError:  # no reference snapshot: the share class stays unknown
            return None
        iid = str(resolved["instrument_id"].iloc[0])
        return iid if iid in {i for i, _ in held} else None
    return None


def held_rows(run: IngestRun) -> dict[tuple[str, str], dict[str, Any]]:
    """(cik, accession) -> the latest stored version, as a dict."""
    frame = latest_versions(run.reader, TABLE, KEY)
    if frame.empty:
        return {}
    frame = frame.astype(object).where(frame.notna(), None)
    rows = [{str(k): v for k, v in r.items()} for r in frame.to_dict("records")]
    return {(str(r["cik"]), str(r["accession"])): r for r in rows}


def list_hits(run: IngestRun, search: Source, start: date, end: date) -> tuple[list[Hit], int]:
    """The prospectuses filed in ``start..end`` by calendar month and the months that failed."""
    found, failed = [], 0
    for first, last in months_between(start, end):
        key = f"{WINDOW_PREFIX}{first:%Y-%m}"
        request = ProspectusSearchRequest(
            key=f"{first}..{last}", session_date=run.session, start=first, end=last
        )
        try:
            normalized = run.fetch(search, request)
            assert normalized is not None
            hits = normalized.parsed[HITS_FRAME]
        except NoResponseError:
            run.record_item(key, "NO_DATA: the search answered nothing")
            continue
        except Exception as exc:  # one month failing must not stop the others
            run.fail(key, str(exc))
            failed += 1
            continue
        found.append(hits)
        run.record_item(key, f"OK: {len(hits)} hits")
        run.checkpoint()
    if not found:
        return [], failed
    frame = pd.concat(found, ignore_index=True).drop_duplicates("accession")
    return hits_of(frame), failed


class Submissions:
    """One request per CIK and run for its 424B4 rows (acceptance and main document)."""

    def __init__(self, run: IngestRun, source: Source) -> None:
        self.run, self.source = run, source
        self._memo: dict[str, Normalized | None] = {}

    def accepted(self, cik: str, accession: str, since: date) -> tuple[pd.Timestamp, str] | None:
        """(acceptance instant, main document) of a 424B4, ``None`` when SEC lists none."""
        if cik not in self._memo:
            request = FilingsRequest(key=cik, session_date=self.run.session, since=since)
            try:
                self._memo[cik] = self.run.fetch(self.source, request)
            except NoResponseError:
                self._memo[cik] = None
        normalized = self._memo[cik]
        if normalized is None:
            return None
        frame = normalized.parsed[FILINGS_FRAME]
        row = frame[(frame["accession"] == accession) & (frame["form"] == FORM)]
        if row.empty:
            return None
        document = row["primary_document"].iloc[0]
        return pd.Timestamp(row["acceptance_ts"].iloc[0]), "" if pd.isna(document) else str(
            document
        )


def _one(
    run: IngestRun,
    hit: Hit,
    since: date,
    held: dict[tuple[str, str], dict[str, Any]],
    sources: tuple[Submissions, Source],
) -> str:
    """Read one prospectus, stage its row (new or changed) -> the item status."""
    submissions, prospectus = sources
    found = submissions.accepted(hit.cik, hit.accession, since)
    if found is None:
        return "NO_DATA: the issuer's submissions list no such 424B4"
    accepted, document = found
    request = ProspectusRequest(
        key=hit.accession, session_date=run.session, cik=hit.cik, document=document
    )
    try:
        normalized = run.fetch(prospectus, request)
    except NoResponseError:
        return "NO_DATA: the prospectus document is not served"
    assert normalized is not None
    facts = {str(k): v for k, v in normalized.parsed[IPO_FRAME].iloc[0].to_dict().items()}
    before = held.get((hit.cik, hit.accession))
    # A first version carries no id: the universe is today's, the row is known from an old
    # session. ``fill_instruments`` stages the id as a version of its own.
    row = build_row(hit, accepted, document, facts, (before or {}).get("instrument_id"))
    if before is not None:
        if same_values(row, before):
            if before["rules_version"] == RULES_VERSION:
                return "UNCHANGED"
            row["known_from"] = before["known_from"]  # only the rules moved: not a restatement
            status = "(rules)"
        else:
            row["known_from"] = restated_known_from(row["known_from"], run.clock())
            status = "(changed)"
    else:
        status = ""
    run.stage(TABLE, f"{ACCESSION_PREFIX}{hit.accession}", as_frame([row]), "sec_edgar")
    return f"OK: {row['extraction']} {status}".rstrip()


def fill_instruments(
    run: IngestRun, held: dict[tuple[str, str], dict[str, Any]], known: Issuers, skip: set[str]
) -> int:
    """Stage a new version of each stored row of the current rules version (not read this run)
    whose CIK is now in the universe: the id filled, known from the restated session. -> rows."""
    rows = []
    for (cik, accession), before in held.items():
        if (
            before.get("instrument_id")
            or accession in skip
            or before["rules_version"] != RULES_VERSION
        ):
            continue
        if (iid := instrument_for(run, known, cik, before.get("ticker"))) is None:
            continue
        accepted = pd.Timestamp(before["ts"])
        row = {**before, "instrument_id": iid}
        row["known_from"] = restated_known_from(acceptance_session(accepted), run.clock())
        rows.append(row)
    if rows:
        run.stage(TABLE, "ids", as_frame(rows), "sec_edgar")
        run.record_item("ids", f"OK: {len(rows)}")
    return len(rows)


def filing_gap(run: IngestRun, hits: list[Hit], start: date, end: date) -> tuple[int, list[str]]:
    """The 424B4 rows D1 stored in ``events/filing`` filed in ``start..end`` and the accessions
    among them the search did not list (its recall gap, e.g. a "lockup" spelling)."""
    frame = run.reader.table_range(
        "events/filing", *ALL_TIME, columns=["accession", "form", "filing_date"]
    )
    if frame is None or frame.empty:
        return 0, []
    day = pd.to_datetime(frame["filing_date"]).dt.date
    mine = frame[(frame["form"] == FORM) & (day >= start) & (day <= end)]
    stored = set(mine["accession"].astype(str))
    missing = sorted(stored - {h.accession for h in hits})
    return len(stored), missing


def ingest_ipo_lockups(
    ctx: TaskContext,
    session: date,
    search: Source,
    filings: Source,
    prospectus: Source,
    since: date | None = None,
    until: date | None = None,
    limit: int | None = None,
) -> RunRecord:
    """Store the IPO facts and lock-up dates of the 424B4 prospectuses filed in ``since..until``
    (module doc; defaults: the 30 days before ``session`` through it), at most ``limit`` read."""
    start, end = since or session - timedelta(LOOKBACK_DAYS), until or session
    with IngestRun(ctx, TASK, session) as run:
        known, held = issuers(run), held_rows(run)
        hits, failed_windows = list_hits(run, search, start, end)
        due = [
            h
            for h in hits
            if (h.cik, h.accession) not in held
            or held[(h.cik, h.accession)]["rules_version"] != RULES_VERSION
        ]  # hits_of lists the oldest filing first
        skipped = len(hits) - len(due)
        due = due[:limit] if limit else due
        sources = (Submissions(run, filings), prospectus)
        first: dict[str, date] = {}
        for h in due:
            first[h.cik] = min(first.get(h.cik, h.filing_date), h.filing_date)
        for i, hit in enumerate(due, 1):
            run.attempt(
                f"{ACCESSION_PREFIX}{hit.accession}",
                partial(_one, run, hit, first[hit.cik], held, sources),
            )
            if i % CHECKPOINT_EVERY == 0:
                run.checkpoint()
        filled = fill_instruments(run, held, known, {h.accession for h in due})
        in_filings, unlisted = filing_gap(run, hits, start, end)
        written = run.publish(TABLE, sort_by="accession")
        run.stats.update(
            since=start.isoformat(),
            until=end.isoformat(),
            windows=len(months_between(start, end)),
            windows_failed=failed_windows,
            hits=len(hits),
            skipped_stored=skipped,
            read=len(due),
            universe_available=known.available,
            instruments_filled=filled,
            filing_424b4_in_window=in_filings,
            filing_424b4_not_listed=len(unlisted) if not failed_windows else None,
            filing_424b4_not_listed_sample=unlisted[:20] if not failed_windows else [],
            rows=written,
            items=run.counts(),
        )
    return run.record
