"""Share counts from SEC company facts as an L1 table (``instruments/shares``, phase 2b.4).

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
- Per-CIK rows are staged and published as one partition; a crashed run resumes (CIKs it
  already fetched are skipped).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from functools import partial

import pandas as pd

from algotrade.core.model.instruments import pad_cik
from algotrade.data import StoreReader
from algotrade.data.reference import instruments, snapshot
from algotrade.data.shares import CHECKED, DATES, KEY, TABLE, stored_shares
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.sources.framework.base import FetchRequest, Source
from algotrade_ingestion.tasks.framework.run import IngestRun, NoResponseError, TaskContext
from algotrade_ingestion.tasks.reference.refresh import due_keys

TASK = "shares"
COMPANY = "instruments/company"
CHECKPOINT_EVERY = 100
CARRY = "carry"  # staging key for facts copied to instruments new to a CIK


@dataclass(frozen=True)
class SharesSources:
    facts: Source  # SecCompanyFacts
    refresh_days: int = 30


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


def _rows(facts: pd.DataFrame, members: pd.DataFrame, fetched_on: date) -> pd.DataFrame:
    """One CIK's facts for each of its instruments, plus a ``checked`` marker each."""
    marker = pd.DataFrame([{"concept": CHECKED, "period_end": None, "filed": None}])
    out = pd.concat([facts.drop(columns=["cik"], errors="ignore"), marker], ignore_index=True)
    for column in DATES:
        if column in out.columns:
            day = pd.to_datetime(out[column]).dt.date
            out[column] = day.astype(object).where(out[column].notna(), None)
    # Two filings on one day for one period (a same-day amendment): the later listed wins.
    out = out.drop_duplicates(KEY[1:], keep="last")
    out = members[["instrument_id", "symbol", "cik"]].merge(out, how="cross")
    out["fetched_on"] = fetched_on
    return out


def _fetch(
    run: IngestRun, source: Source, cik: str, members: pd.DataFrame, known: set[tuple[object, ...]]
) -> str:
    try:
        normalized = run.fetch(source, FetchRequest(cik, session_date=run.session))
    except NoResponseError:
        facts = pd.DataFrame(columns=["concept"])
        status = "NO_FACTS"  # no XBRL facts under this CIK (common for funds)
    else:
        facts = normalized.parsed["shares"] if normalized is not None else pd.DataFrame()
        status = f"OK: {len(facts)} facts" if not facts.empty else "NO_SHARE_FACTS"
    rows = _rows(facts, members, run.session)
    new = [tuple(r) for r in rows[KEY].astype(object).itertuples(index=False)]
    fresh = [k not in known or k[1] == CHECKED for k in new]
    run.stage(TABLE, cik, _typed(rows[fresh]), source.name)
    return status


def _typed(rows: pd.DataFrame) -> pd.DataFrame:
    out = rows.copy()
    for column in ("fy", "class_values"):
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce").astype("Int64")
    return out.astype(object).where(out.notna(), None)


def _carry(stored: pd.DataFrame, ids: pd.DataFrame, fetched: set[str]) -> pd.DataFrame:
    """Stored facts of a CIK copied to its instruments that have none (a new listing or
    class), for CIKs not fetched this run."""
    if stored.empty:
        return stored
    have = set(stored["instrument_id"].astype(str))
    new = ids[~ids["instrument_id"].isin(have) & ~ids["cik"].isin(fetched)]
    by_cik = stored.drop_duplicates(["cik", "concept", "period_end", "filed"])
    by_cik = by_cik.drop(columns=["instrument_id", "symbol"], errors="ignore")
    return new[["instrument_id", "symbol", "cik"]].merge(by_cik, on="cik", how="inner")


def _last_fetched(stored: pd.DataFrame) -> Mapping[str, date]:
    if stored.empty:
        return {}
    return dict(stored.groupby("cik")["fetched_on"].max())


def ingest_shares(
    ctx: TaskContext,
    sources: SharesSources,
    session: date,
    force: bool = False,
    limit: int | None = None,
) -> RunRecord:
    ids = instrument_ciks(ctx.reader, session)
    stored = stored_shares(ctx.reader)
    known = {tuple(r) for r in stored[KEY].astype(object).itertuples(index=False)}
    with IngestRun(ctx, TASK, session, resume=True) as run:
        ciks = sorted(set(ids["cik"]))
        due = due_keys(ciks, _last_fetched(stored), session, sources.refresh_days, force)
        todo = due if limit is None else due[: max(limit, 0)]
        members = dict(tuple(ids.groupby("cik")))
        for i, cik in enumerate(todo, start=1):
            if cik in run.items:
                continue  # fetched before a resume
            run.attempt(cik, partial(_fetch, run, sources.facts, cik, members[cik], known))
            if i % CHECKPOINT_EVERY == 0:
                run.checkpoint()
        facts = stored[stored["concept"] != CHECKED]
        carried = _carry(facts, ids, set(todo))
        if not carried.empty:
            run.stage(TABLE, CARRY, _typed(carried), sources.facts.name)
        rows = run.publish(TABLE)
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
            carried=len(carried),
            failed=failed[:20],
            failed_count=len(failed),
            rows=rows,
        )
    return run.record
