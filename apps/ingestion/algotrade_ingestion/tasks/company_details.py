"""Company details from SEC EDGAR as an L1 table (``instruments/company``, phase 1.7).

Each run writes a **full snapshot** for its session: one row per instrument in the latest
``instruments/reference`` whose company is known, so "as of D" reads stay point-in-time.

- CIK: the reference's (Massive, phase 1.5) when present, else the SEC ticker map.
- Incremental: submissions are fetched only for CIKs not yet stored or fetched more than
  ``refresh_days`` before the session (``force`` refetches all; ``limit`` caps a run). Every
  other CIK carries its previous details forward, so a nightly run makes few requests.
- Funds and ETFs often have no submissions (404) or no CIK at all: counted, not failures.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from functools import partial

import pandas as pd

from algotrade.core.fields import COMPANY_COLUMNS
from algotrade.core.instruments import pad_cik
from algotrade.data import StoreReader
from algotrade.data.reference import instruments, snapshot
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.sources.base import FetchRequest, Source
from algotrade_ingestion.tasks.framework import IngestRun, NoResponseError, TaskContext

TASK = "company_details"
TABLE = "instruments/company"
REFERENCE = "instruments/reference"


@dataclass(frozen=True)
class CompanySources:
    tickers: Source  # SecTickerMap
    submissions: Source  # SecSubmissions
    refresh_days: int = 30


def _ticker_map(run: IngestRun, source: Source, out: dict[str, str]) -> str:
    """symbol -> CIK from the SEC ticker map, into ``out``."""
    normalized = run.fetch(source, FetchRequest("tickers", session_date=run.session))
    if normalized is None:
        raise ValueError("SEC ticker map had no rows")
    frame = normalized.parsed["tickers"]
    out.update(zip(frame["symbol"], frame["cik"], strict=True))
    return f"OK: {len(frame)} tickers"


def _submissions(run: IngestRun, source: Source, cik: str, fetched: list[pd.DataFrame]) -> str:
    try:
        normalized = run.fetch(source, FetchRequest(cik, session_date=run.session))
    except NoResponseError:
        return "NO_SUBMISSIONS"  # no filings under this CIK (common for funds)
    if normalized is None:
        return "EMPTY"
    fetched.append(normalized.parsed["company"].assign(cik=cik, fetched_on=run.session))
    return "OK"


def assign_ciks(reference: pd.DataFrame, sec_map: dict[str, str]) -> pd.DataFrame:
    """-> ``instrument_id``, ``symbol``, ``cik``, ``cik_source`` (``reference``/``sec_map``)."""
    own = (
        reference["cik"].map(pad_cik)
        if "cik" in reference.columns
        else pd.Series(None, index=reference.index, dtype=object)
    )
    mapped = reference["symbol"].map(sec_map)
    out = pd.DataFrame(
        {
            "instrument_id": reference["instrument_id"].astype(str),
            "symbol": reference["symbol"].astype(str),
            "cik": own.where(own.notna(), mapped),
        }
    )
    out["cik_source"] = None
    out.loc[mapped.notna(), "cik_source"] = "sec_map"
    out.loc[own.notna(), "cik_source"] = "reference"
    return out


def due_ciks(
    ciks: list[str], previous: pd.DataFrame | None, session: date, refresh_days: int, force: bool
) -> list[str]:
    """CIKs to fetch: never stored first, then the stalest; all of them with ``force``."""
    if force or previous is None or previous.empty:
        return sorted(ciks)
    on = pd.to_datetime(previous["fetched_on"]).dt.date
    fetched = on.groupby(previous["cik"]).max()
    cutoff = session - timedelta(days=refresh_days)
    new = sorted(c for c in ciks if c not in fetched.index)
    stale = sorted((c for c in ciks if c in fetched.index and fetched[c] <= cutoff),
                   key=lambda c: (fetched[c], c))  # fmt: skip
    return new + stale


def _previous(reader: StoreReader, session: date) -> pd.DataFrame | None:
    snap = snapshot(reader, TABLE, session)
    if snap is None or snap.pre_snapshot:  # never reuse details fetched after ``session``
        return None
    return reader.table(TABLE, snap.snapshot_date)


def ingest_company_details(
    ctx: TaskContext,
    sources: CompanySources,
    session: date,
    force: bool = False,
    limit: int | None = None,
) -> RunRecord:
    reference = instruments(ctx.reader, session)
    with IngestRun(ctx, TASK, session) as run:
        sec_map: dict[str, str] = {}  # reference CIKs still work without the map
        run.attempt("tickers", partial(_ticker_map, run, sources.tickers, sec_map))
        ids = assign_ciks(reference, sec_map)
        known = ids[ids["cik"].notna()]
        ciks = sorted(set(known["cik"]))
        previous = _previous(ctx.reader, session)
        due = due_ciks(ciks, previous, session, sources.refresh_days, force)
        todo = due if limit is None else due[: max(limit, 0)]
        fetched: list[pd.DataFrame] = []
        for cik in todo:
            run.attempt(cik, partial(_submissions, run, sources.submissions, cik, fetched))
        details = _merge_details(previous, fetched)
        rows = known.merge(details, on="cik", how="inner") if not details.empty else known.iloc[:0]
        if not rows.empty:
            rows = rows.sort_values("instrument_id").reset_index(drop=True)
            rows = rows.astype(object).where(rows.notna(), None)
            run.write(TABLE, rows, sources.submissions.name)
        failed = run.failures()
        run.stats.update(
            instruments=len(ids),
            cik_from_reference=int(ids["cik_source"].eq("reference").sum()),
            cik_from_sec_map=int(ids["cik_source"].eq("sec_map").sum()),
            no_cik=int(ids["cik"].isna().sum()),
            ciks=len(ciks),
            due=len(due),
            requested=len(todo),
            fetched=len(fetched),
            no_submissions=run.counts().get("NO_SUBMISSIONS", 0),
            deferred_by_limit=len(due) - len(todo),
            failed=failed[:20],
            failed_count=len(failed),
            rows=len(rows),
        )
    return run.record


def _merge_details(previous: pd.DataFrame | None, fetched: list[pd.DataFrame]) -> pd.DataFrame:
    """Company details per CIK: newly fetched rows win over the previous snapshot's."""
    columns = [*COMPANY_COLUMNS, "fetched_on"]
    frames = []
    if previous is not None and not previous.empty:
        frames.append(previous[[c for c in columns if c in previous.columns]])
    frames.extend(fetched)
    if not frames:
        return pd.DataFrame(columns=columns)
    merged = pd.concat(frames, ignore_index=True)
    return merged.drop_duplicates("cik", keep="last").reset_index(drop=True)
