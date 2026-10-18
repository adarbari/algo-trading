"""The ``insider`` task: SEC Form 4 (and 4/A) insider transactions -> ``events/insider_transaction``
(EB D6; the cluster-buy and opportunistic-insider edges read it).

**Two ways in, one row shape** (``insider_rows`` says how a row is stamped: id as of the filing
date, ``known_from`` the NY session of SEC's acceptance time, restatements later):

- **Bulk** (``--since``, the history from 2006): SEC's quarterly Insider Transactions Data Sets
  (``sec_form345_bulk``), one file per quarter from the quarter of ``--since`` through that of
  ``--until`` (default the session; a quarter not published yet is ``NO_DATA``, read again later).
  The sets carry the filing date only, so the ACCEPTANCE time comes from the submissions JSON
  of each issuer (``sec_filings`` with the insider forms: one request per issuer CIK, its older
  pages when ``--since`` precedes the recent block), joined by accession; a line whose filing
  the issuer's submissions do not list is counted (``no_acceptance``), never stored with a
  guessed time. Only issuers whose ticker resolves as of the filing date are read. A quarter an
  earlier run read ``OK`` is skipped (``--force`` reads it again; ``--limit`` caps the quarters),
  so a backfill is run in chunks (a year per run keeps a run's rows in memory) and repeated.
- **Daily index** (the nightly, with rows stored and no ``--since``): for each weekday since the
  last clean walk's ``walked_to`` (else the latest stored filing date, else a week back), the
  ``sec_daily_index`` lists the day's Form 4 filers; the universe's CIKs among them are asked for
  their submissions (acceptance time, the XML's name), and each accession not stored is read from
  its XML (``sec_form4_xml``). The sets lag the XML by weeks, so this is also what covers the
  gap after the last quarter. At most ``XML_PER_RUN`` filings a run: the walk stops after the day
  that fills it and the next run goes on. A day or filing that fails keeps ``walked_to`` unset, so
  the next run walks the same days again (stored accessions are not read twice).

``stats``: ``rows`` written, ``unresolved`` / ``no_acceptance`` / ``bad_rows`` lines dropped,
``restated`` rows stamped later than their acceptance (module ``insider_rows``).
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from functools import partial

import pandas as pd

from algotrade.core.time.calendar import exchange_date
from algotrade.data.events import ALL_TIME
from algotrade.data.listings.resolvers import listing_resolver
from algotrade.data.resolver import SymbolResolver
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.events import insider_rows as rows_of
from algotrade_ingestion.tasks.events.filings import (
    ciks_of,
    filing_days,
    last_walked,
    previous_runs,
    read_index_days,
    universe_names,
)
from algotrade_ingestion.tasks.framework.run import (
    FAILURES,
    IngestRun,
    NoResponseError,
    TaskContext,
    status_label,
)
from algotrade_sources.framework.base import Source
from algotrade_sources.framework.series import (
    FILINGS_FRAME,
    INSIDER_FORMS,
    INSIDER_FRAME,
    FilingsRequest,
    InsiderRequest,
)

TASK = "insider"
TABLE = rows_of.TABLE  # the table this task owns (architecture/tables.toml)
XML_PER_RUN = 4000  # filings a nightly reads (about four days of Form 4s)
BOOTSTRAP_DAYS = 7  # the first nightly with nothing stored reads this many days back
QUARTER_ITEM, FILING_ITEM, CIK_ITEM = "q:", "acc:", "cik:"
DATE_COLUMNS = ["filing_date", "period_of_report", "amends_date", "transaction_date"]
CHECKPOINT_EVERY = 25
Tally = dict[str, int]  # lines dropped or restamped, by reason (module doc)


@dataclass(frozen=True)
class Sources:
    """The four SEC sources the task reads."""

    acceptance: Source  # ``sec_filings``: submissions JSON, accepted time per accession
    bulk: Source  # ``sec_form345_bulk``
    xml: Source  # ``sec_form4_xml``
    index: Source  # ``sec_daily_index``


def quarter_labels(since: date, until: date) -> list[str]:
    """The quarters from the one holding ``since`` through the one holding ``until``
    (``2019q2``), oldest first."""
    year, quarter = since.year, (since.month - 1) // 3 + 1
    out = []
    while (year, quarter) <= (until.year, (until.month - 1) // 3 + 1):
        out.append(f"{year}q{quarter}")
        year, quarter = (year + 1, 1) if quarter == 4 else (year, quarter + 1)
    return out


def quarter_start(label: str) -> date:
    """The first day of a quarter label."""
    return date(int(label[:4]), 3 * (int(label[-1]) - 1) + 1, 1)


def quarters_read(run: IngestRun) -> set[str]:
    """The quarters an earlier run of this task read ``OK``."""
    return {
        key[len(QUARTER_ITEM) :]
        for record in previous_runs(run, TASK)
        for key, status in record.items.items()
        if key.startswith(QUARTER_ITEM) and status_label(status) == "OK"
    }


class Stored:
    """The table's ``columns`` as stored before the run (read once, when first needed): all of
    them for a backfill (a line may be read again, and restated), the amendment keys for the
    nightly (its filings are new, so only a 4/A's original matters)."""

    def __init__(self, run: IngestRun, columns: list[str]) -> None:
        self._run = run
        self._columns = columns
        self._frame: pd.DataFrame | None = None

    @property
    def frame(self) -> pd.DataFrame:
        if self._frame is None:
            found = self._run.reader.table_range(TABLE, *ALL_TIME, columns=self._columns)
            self._frame = found if found is not None else pd.DataFrame(columns=self._columns)
        return self._frame

    def accessions(self) -> set[str]:
        return set(self.frame["accession"].astype(str))

    def last_filing(self) -> date | None:
        days = pd.to_datetime(self.frame["filing_date"])
        return None if days.empty else days.max().date()


def acceptance_of(
    run: IngestRun, source: Source, cik: str, since: date, cache: dict[str, pd.DataFrame]
) -> pd.DataFrame:
    """The Form 4 / 4/A filings of one issuer CIK filed on or after ``since``: ``accession``,
    ``acceptance_ts``, ``filing_date``, ``primary_document`` (cached for the run)."""
    if cik not in cache:
        request = FilingsRequest(
            key=cik, session_date=run.session, since=since, forms=INSIDER_FORMS
        )
        try:
            found = run.fetch(source, request)
        except NoResponseError:
            cache[cik] = pd.DataFrame(
                columns=["accession", "acceptance_ts", "filing_date", "primary_document"]
            )
        else:
            assert found is not None
            columns = ["accession", "acceptance_ts", "filing_date", "primary_document"]
            cache[cik] = found.parsed[FILINGS_FRAME][columns]
    return cache[cik]


def build_rows(
    frame: pd.DataFrame,
    accepted: pd.DataFrame,
    resolver_on: Callable[[date], SymbolResolver],
    stored: pd.DataFrame,
    floor: date,
    tally: Tally,
) -> pd.DataFrame:
    """The table rows of a parsed ``frame`` (``INSIDER_COLUMNS``): SEC's acceptance time and
    filing date from ``accepted``, the id as of that filing date, the dates as dates, then
    ``known_from`` against the ``stored`` rows (``insider_rows``). Lines without an acceptance,
    an id, an owner or a transaction date are dropped and counted."""
    joined = frame.drop(columns="filing_date").merge(
        accepted[["accession", "acceptance_ts", "filing_date"]], on="accession", how="inner"
    )
    tally["no_acceptance"] += len(frame) - len(joined)
    joined = joined.assign(ts=pd.to_datetime(joined["acceptance_ts"], utc=True))
    resolved, unresolved = rows_of.resolve_ids(joined, resolver_on)
    tally["unresolved"] += unresolved
    usable = resolved[resolved["transaction_date"].notna() & resolved["owner_cik"].notna()]
    tally["bad_rows"] += len(resolved) - len(usable)
    for column in DATE_COLUMNS:
        days = pd.to_datetime(usable[column])
        usable = usable.assign(**{column: days.dt.date.astype(object).where(days.notna(), None)})
    stamped = rows_of.stamp_known_from(usable.reset_index(drop=True), stored, floor)
    own = rows_of.known_session(pd.to_datetime(stamped["ts"], utc=True))
    tally["restated"] += int((stamped["known_from"] > own).sum()) if len(stamped) else 0
    return rows_of.table_rows(stamped)


def _quarter(
    run: IngestRun,
    sources: Sources,
    label: str,
    since: date,
    resolver_on: Callable[[date], SymbolResolver],
    stored: Stored,
    cache: dict[str, pd.DataFrame],
    tally: Tally,
) -> str:
    """Read one quarter's bulk file, join the issuers' acceptance times, stage its rows."""
    try:
        found = run.fetch(sources.bulk, InsiderRequest(key=label, session_date=run.session))
    except NoResponseError:
        return "NO_DATA: not published yet"
    assert found is not None
    frame = found.parsed[INSIDER_FRAME]
    seen, dropped = rows_of.resolve_ids(frame, resolver_on)  # which issuers are worth a request
    tally["unresolved"] += dropped
    issuers = sorted(set(seen["issuer_cik"].dropna()))
    accepted = (
        pd.concat(
            [acceptance_of(run, sources.acceptance, cik, since, cache) for cik in issuers],
            ignore_index=True,
        )
        if issuers
        else pd.DataFrame(columns=["accession", "acceptance_ts", "filing_date"])
    )
    frame = frame[frame["issuer_cik"].isin(issuers)]
    rows = build_rows(frame, accepted, resolver_on, stored.frame, floor_of(run), tally)
    if len(rows):
        run.stage(TABLE, label, rows, sources.bulk.name)
    tally["rows"] += len(rows)
    return f"OK: {len(rows)} lines"


def floor_of(run: IngestRun) -> date:
    """The earliest ``known_from`` of a restated row (``insider_rows``), from the run's clock."""
    return rows_of.restatement_floor(run.clock())


def backfill(
    run: IngestRun,
    sources: Sources,
    resolver_on: Callable[[date], SymbolResolver],
    stored: Stored,
    since: date,
    until: date,
    limit: int | None,
    force: bool,
    tally: Tally,
) -> list[str]:
    """Read the quarters from ``since`` through ``until`` (module doc) -> the labels asked."""
    done = set() if force else quarters_read(run)
    labels = [q for q in quarter_labels(since, until) if q not in done]
    labels = labels[:limit] if limit else labels
    cache: dict[str, pd.DataFrame] = {}
    start = quarter_start(quarter_labels(since, since)[0])  # the first quarter read in full
    for i, label in enumerate(labels, 1):
        run.attempt(
            f"{QUARTER_ITEM}{label}",
            partial(_quarter, run, sources, label, start, resolver_on, stored, cache, tally),
        )
        if i % CHECKPOINT_EVERY == 0:
            run.checkpoint()
    return labels


def _one_filing(
    run: IngestRun,
    source: Source,
    accession: str,
    cik: str,
    document: str,
    bucket: list[pd.DataFrame],
) -> str:
    """Read one filing's XML into ``bucket`` (its day's lines)."""
    request = InsiderRequest(key=accession, session_date=run.session, cik=cik, document=document)
    found = run.fetch(source, request)
    assert found is not None
    frame = found.parsed[INSIDER_FRAME]
    bucket.append(frame)
    return f"OK: {len(frame)} lines"


def _asked(
    run: IngestRun, source: Source, cik: str, since: date, cache: dict[str, pd.DataFrame]
) -> str:
    """The item status of one issuer's acceptance request."""
    return f"OK: {len(acceptance_of(run, source, cik, since, cache))} filings"


def pending_filings(
    accepted: Mapping[str, pd.DataFrame], days: list[date], known: set[str], cap: int
) -> tuple[pd.DataFrame, list[date]]:
    """The filings of the walked ``days`` not stored yet (``accession``, ``filing_date``,
    ``cik``, ``primary_document``, ``acceptance_ts``), oldest first, and the days they cover:
    whole days only, stopping after the day that reaches ``cap`` filings (the first day always)."""
    parts = [f.assign(cik=cik) for cik, f in accepted.items() if len(f)]
    if not parts:
        return pd.DataFrame(), days
    every = pd.concat(parts, ignore_index=True).drop_duplicates("accession")
    every = every.assign(day=pd.to_datetime(every["filing_date"]).dt.date)
    every = every[every["day"].isin(days) & ~every["accession"].isin(known)]
    taken: list[date] = []
    total = 0
    for day in days:
        count = int((every["day"] == day).sum())
        if taken and total + count > cap:
            break
        taken.append(day)
        total += count
    chosen = every[every["day"].isin(taken)].sort_values(["day", "accession"], kind="stable")
    return chosen.reset_index(drop=True), taken


def walk(
    run: IngestRun,
    sources: Sources,
    resolver_on: Callable[[date], SymbolResolver],
    stored: Stored,
    universe: set[str],
    start: date,
    tally: Tally,
) -> date | None:
    """The nightly: read the days from ``start`` through the session from the daily index and the
    new filings of the universe's CIKs among their filers -> the last day read cleanly (None:
    a failure, or nothing read)."""
    filers, _ = read_index_days(run, sources.index, filing_days(start, run.session), INSIDER_FORMS)
    days = sorted(filers)
    if not days:
        return None
    ciks = sorted(set().union(*filers.values()) & universe)
    cache: dict[str, pd.DataFrame] = {}
    for cik in ciks:
        run.attempt(
            f"{CIK_ITEM}{cik}", partial(_asked, run, sources.acceptance, cik, days[0], cache)
        )
    chosen, taken = pending_filings(
        {c: f for c, f in cache.items() if c in ciks}, days, stored.accessions(), XML_PER_RUN
    )
    buckets: dict[date, list[pd.DataFrame]] = {day: [] for day in taken}
    for i, row in enumerate(chosen.to_dict("records"), 1):
        accession = str(row["accession"])
        run.attempt(
            f"{FILING_ITEM}{accession}",
            partial(
                _one_filing,
                run,
                sources.xml,
                accession,
                str(row["cik"]),
                str(row["primary_document"]),
                buckets[row["day"]],
            ),
        )
        if i % CHECKPOINT_EVERY == 0:
            run.checkpoint()
    for day, frames in buckets.items():
        if frames:
            accepted = chosen[chosen["day"] == day]
            rows = build_rows(
                pd.concat(frames, ignore_index=True), accepted, resolver_on, stored.frame,
                floor_of(run), tally,
            )  # fmt: skip
            if len(rows):
                run.stage(TABLE, f"d:{day}", rows, sources.xml.name)
            tally["rows"] += len(rows)
    clean = not any(status_label(s) in FAILURES for s in run.items.values())
    return taken[-1] if clean else None


def _universe_ciks(run: IngestRun) -> set[str]:
    return set(ciks_of(run, universe_names(run, []).listed))


def ingest_insider(
    ctx: TaskContext,
    sources: Sources,
    session: date,
    since: date | None = None,
    until: date | None = None,
    limit: int | None = None,
    force: bool = False,
) -> RunRecord:
    """Store Form 4 / 4/A transactions (module doc): the bulk quarters from ``since`` through
    ``until`` when ``since`` is given, else the daily walk since the last clean one."""
    with IngestRun(ctx, TASK, session) as run:
        tally = dict.fromkeys(("rows", "unresolved", "no_acceptance", "bad_rows", "restated"), 0)
        resolver_on = listing_resolver(run.reader)
        stored = Stored(run, rows_of.COLUMNS if since is not None else rows_of.AMENDMENT_COLUMNS)
        walked: date | None = None
        labels: list[str] = []
        if since is not None:
            labels = backfill(
                run, sources, resolver_on, stored, since, until or session, limit, force, tally
            )
        else:
            start = (
                last_walked(run, TASK)
                or stored.last_filing()
                or exchange_date(run.clock()) - timedelta(BOOTSTRAP_DAYS)
            )
            walked = walk(run, sources, resolver_on, stored, _universe_ciks(run), start, tally)
        written = run.publish(TABLE)
        run.stats.update(
            mode="bulk" if since is not None else "daily_index",
            quarters=labels,
            since=since.isoformat() if since else None,
            until=(until or session).isoformat() if since else None,
            walked_to=walked.isoformat() if walked else None,
            rows=written,
            items=run.counts(),
            **{k: v for k, v in tally.items() if k != "rows"},
        )
    return run.record
