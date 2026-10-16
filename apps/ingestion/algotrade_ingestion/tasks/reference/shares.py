"""Share counts, basic financials and financial statement lines from SEC company facts as
two L1 tables (``instruments/shares``, phase 2b.4, with revenue, net income and diluted EPS for
``financials@v2``; ``instruments/statements``, ADR 0067), written from ONE fetch of each
company's document.

- CIK per instrument: the latest ``instruments/company`` snapshot on or before the session
  (the reference's CIK or the SEC ticker map, chosen by ``company_details``), else the
  reference's own CIK.
- Share classes: companyfacts has no class-specific counts (it drops dimensional facts), so
  every instrument with the same CIK (GOOGL and GOOG, BRK.A and BRK.B) gets the CIK's facts,
  the company total. A class-specific source would win once one exists.
- Incremental: a CIK is fetched when never fetched or past its refresh slot
  (``refresh.due_keys``: once per ``[sec_edgar] facts_refresh_days``, spread over the window
  by CIK); ``force`` refetches all, ``limit`` caps a run. Each run stores only facts not
  stored yet, plus a ``checked`` marker per instrument of every fetched CIK (``fetched_on``),
  so a CIK without facts (404, a fund) is not refetched every night. An instrument new to a
  CIK that is not due gets the CIK's stored facts copied.
- Two tables, one fetch: a CIK is due when EITHER table is due (its older ``fetched_on`` decides;
  a CIK with no marker in one of them is new there), so a table that failed to stage for a CIK
  that the other table stored is due again the next night, not in 30 days. A table's rows are
  staged separately, the shares first.
- Per-CIK rows are staged and published as one partition per table; a crashed run resumes
  (CIKs it already fetched are skipped).
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from functools import partial

import pandas as pd

from algotrade.core.model.instruments import pad_cik
from algotrade.data import StoreReader
from algotrade.data.reference import instruments, snapshot
from algotrade.data.shares import CHECKED, DATES, KEY, TABLE, stored_shares
from algotrade.data.statements.reading import KEY as STATEMENT_KEY
from algotrade.data.statements.reading import TABLE as STATEMENTS
from algotrade.data.statements.reading import stored_statements
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.framework.refresh import due_keys
from algotrade_ingestion.tasks.framework.run import IngestRun, NoResponseError, TaskContext
from algotrade_sources.framework.base import FetchRequest, Source

TASK = "shares"
COMPANY = "instruments/company"
CHECKPOINT_EVERY = 100
CARRY = "carry"  # staging key for facts copied to instruments new to a CIK


@dataclass(frozen=True)
class SharesSources:
    facts: Source  # SecCompanyFacts
    refresh_days: int = 30


@dataclass(frozen=True)
class Target:
    """One table the task writes from the fetched document."""

    table: str
    parsed: str  # its frame in ``Normalized.parsed``
    key: list[str]
    stored: Callable[[StoreReader], pd.DataFrame]  # every stored row: key, ``cik``, ``fetched_on``
    donors: Callable[[StoreReader, list[str]], pd.DataFrame]  # full stored rows of instruments


def _share_donors(reader: StoreReader, ids: list[str]) -> pd.DataFrame:
    stored = stored_shares(reader)
    return stored[stored["instrument_id"].isin(ids)]


TARGETS = (
    Target(TABLE, "shares", KEY, stored_shares, _share_donors),
    Target(
        STATEMENTS,
        "statements",
        STATEMENT_KEY,
        lambda reader: stored_statements(reader, columns=["fetched_on"]),
        lambda reader, ids: stored_statements(reader, instruments=ids),
    ),
)


def instrument_ciks(reader: StoreReader, session: date) -> pd.DataFrame:
    """``instrument_id``, ``symbol``, ``cik`` for every instrument with a known CIK."""
    reference = instruments(reader, session)
    own = (
        reference["cik"].map(pad_cik)
        if "cik" in reference.columns
        else pd.Series(None, index=reference.index, dtype=object)
    )
    out = pd.DataFrame(
        {
            "instrument_id": reference["instrument_id"].astype(str),
            "symbol": reference["symbol"].astype(str),
            "cik": own,
        }
    )
    snap = snapshot(reader, COMPANY, session)
    company = (
        None if snap is None or snap.pre_snapshot else reader.table(COMPANY, snap.snapshot_date)
    )
    if company is not None and not company.empty:
        sec = company.set_index(company["instrument_id"].astype(str))["cik"].map(pad_cik)
        mapped = out["instrument_id"].map(sec)
        out["cik"] = mapped.where(mapped.notna(), out["cik"])
    return out[out["cik"].notna()].reset_index(drop=True)


def _rows(
    facts: pd.DataFrame, members: pd.DataFrame, fetched_on: date, key: list[str] = KEY
) -> pd.DataFrame:
    """One CIK's facts for each of its instruments, plus a ``checked`` marker each."""
    marker = pd.DataFrame(
        [{"concept": CHECKED, "tag": None, "period_start": None, "period_end": None, "filed": None}]
    )
    out = pd.concat([facts.drop(columns=["cik"], errors="ignore"), marker], ignore_index=True)
    for column in DATES:
        if column in out.columns:
            day = pd.to_datetime(out[column]).dt.date
            out[column] = day.astype(object).where(out[column].notna(), None)
    # Two filings on one day for one period and tag (a same-day amendment): the later listed
    # wins; other tags of the period are kept (the rollups rank them).
    out = out.drop_duplicates(key[1:], keep="last")
    out = members[["instrument_id", "symbol", "cik"]].merge(out, how="cross")
    out["fetched_on"] = fetched_on
    return out


def _fetch(
    run: IngestRun,
    source: Source,
    cik: str,
    members: pd.DataFrame,
    known: Mapping[str, set[tuple[object, ...]]],
) -> str:
    """One document, both tables: each table's new rows are staged in turn, so a failure to
    stage the statements leaves the shares staged (and the statements due again)."""
    try:
        normalized = run.fetch(source, FetchRequest(cik, session_date=run.session))
    except NoResponseError:
        parsed: Mapping[str, pd.DataFrame] = {}
        status = "NO_FACTS"  # no XBRL facts under this CIK (common for funds)
    else:
        parsed = normalized.parsed if normalized is not None else {}
        sizes = {t.parsed: len(parsed.get(t.parsed, ())) for t in TARGETS}
        status = f"OK: {sizes['shares']} facts, {sizes['statements']} statements"
        if not any(sizes.values()):
            status = "NO_SHARE_FACTS"
    for target in TARGETS:
        facts = parsed.get(target.parsed)
        facts = pd.DataFrame(columns=["concept"]) if facts is None else facts
        rows = _rows(facts, members, run.session, target.key)
        new = [tuple(r) for r in rows[target.key].astype(object).itertuples(index=False)]
        fresh = [k not in known[target.table] or k[1] == CHECKED for k in new]
        run.stage(target.table, cik, _typed(rows[fresh]), source.name)
    return status


def _typed(rows: pd.DataFrame) -> pd.DataFrame:
    out = rows.copy()
    for column in ("fy", "class_values"):
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce").astype("Int64")
    return out.astype(object).where(out.notna(), None)


def _carry(
    reader: StoreReader, target: Target, stored: pd.DataFrame, ids: pd.DataFrame, fetched: set[str]
) -> pd.DataFrame:
    """Stored facts of a CIK copied to its instruments that have none (a new listing or
    class), for CIKs not fetched this run; only the rows of one stored instrument per CIK are
    read in full."""
    stored = stored[stored["concept"] != CHECKED]
    if stored.empty:
        return stored
    have = set(stored["instrument_id"].astype(str))
    new = ids[~ids["instrument_id"].isin(have) & ~ids["cik"].isin(fetched)]
    donors = stored[stored["cik"].isin(new["cik"])].drop_duplicates("cik")
    if donors.empty:
        return donors
    facts = target.donors(reader, list(donors["instrument_id"].astype(str)))
    facts = facts[facts["concept"] != CHECKED]
    by_cik = facts.drop_duplicates(["cik", *target.key[1:]])
    by_cik = by_cik.drop(columns=["instrument_id", "symbol"], errors="ignore")
    return new[["instrument_id", "symbol", "cik"]].merge(by_cik, on="cik", how="inner")


def _last_fetched(*stored: pd.DataFrame) -> Mapping[str, date]:
    """Per CIK the older of the tables' latest fetch; a CIK one table never stored is absent
    (new, so due): the CIK is due when either table is."""
    per = [{} if s.empty else dict(s.groupby("cik")["fetched_on"].max()) for s in stored]
    return {c: min(p[c] for p in per) for c in per[0] if all(c in p for p in per)}


def ingest_shares(
    ctx: TaskContext,
    sources: SharesSources,
    session: date,
    force: bool = False,
    limit: int | None = None,
) -> RunRecord:
    ids = instrument_ciks(ctx.reader, session)
    stored = {t.table: t.stored(ctx.reader) for t in TARGETS}
    known = {
        t.table: {tuple(r) for r in stored[t.table][t.key].astype(object).itertuples(index=False)}
        for t in TARGETS
    }
    with IngestRun(ctx, TASK, session, resume=True) as run:
        ciks = sorted(set(ids["cik"]))
        fetched = _last_fetched(*(stored[t.table] for t in TARGETS))
        due = due_keys(ciks, fetched, session, sources.refresh_days, force)
        todo = due if limit is None else due[: max(limit, 0)]
        members = dict(tuple(ids.groupby("cik")))
        for i, cik in enumerate(todo, start=1):
            if cik in run.items:
                continue  # fetched before a resume
            run.attempt(cik, partial(_fetch, run, sources.facts, cik, members[cik], known))
            if i % CHECKPOINT_EVERY == 0:
                run.checkpoint()
        carried = {}
        for target in TARGETS:
            carried[target.table] = _carry(ctx.reader, target, stored[target.table], ids, set(todo))
            if not carried[target.table].empty:
                frame = _typed(carried[target.table])
                run.stage(target.table, CARRY, frame, sources.facts.name)
        rows = {t.table: run.publish(t.table) for t in TARGETS}
        counts = run.counts()
        failed = run.failures()
        run.stats.update(
            instruments=len(ids),
            ciks=len(ciks),
            due=len(due),
            requested=len(todo),
            with_facts=sum(n for s, n in counts.items() if s == "OK"),
            no_facts=counts.get("NO_FACTS", 0) + counts.get("NO_SHARE_FACTS", 0),
            deferred_by_limit=len(due) - len(todo),
            carried=len(carried[TABLE]),
            statements_carried=len(carried[STATEMENTS]),
            failed=failed[:20],
            failed_count=len(failed),
            rows=rows[TABLE],
            statement_rows=rows[STATEMENTS],
        )
    return run.record
