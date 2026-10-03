"""Company details from SEC EDGAR as an L1 table (``instruments/company``, phase 1.7).

Each run writes a **full snapshot** for its session: one row per instrument in the latest
``instruments/reference`` whose company is known, so "as of D" reads stay point-in-time.

- CIK: the reference's (Massive, phase 1.5) when present, else the SEC ticker map.
- Incremental: submissions are fetched only for CIKs not yet stored or fetched more than
  ``refresh_days`` before the session (``force`` refetches all; ``limit`` caps a run). Every
  other CIK carries its previous details forward, so a nightly run makes few requests.
- Funds and ETFs often have no submissions (404) or no CIK at all: counted, not failures.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import pandas as pd

from algotrade.data import StoreReader
from algotrade.data.reference import instruments, snapshot
from algotrade.storage.runs import RunRecord, RunStatus, new_run_id
from algotrade.storage.writers import StoreWriter
from algotrade_ingestion.jobs.common import stamp
from algotrade_ingestion.sources.base import FetchRequest, Source
from algotrade_ingestion.sources.sec_edgar import COMPANY_COLUMNS, pad_cik

JOB = "company_details"
TABLE = "instruments/company"
REFERENCE = "instruments/reference"


@dataclass(frozen=True)
class CompanySources:
    tickers: Source  # SecTickerMap
    submissions: Source  # SecSubmissions
    refresh_days: int = 30


def _ticker_map(source: Source, writer: StoreWriter, session: date, run_id: str) -> dict[str, str]:
    """symbol -> CIK from the SEC ticker map (raw saved first)."""
    request = FetchRequest("tickers", session_date=session)
    payload = source.fetch(request)
    if payload is None:
        raise ValueError("SEC ticker map returned nothing")
    writer.raw.put(source.name, source.dataset, session, run_id, "tickers", payload)
    normalized = source.normalize(request, payload)
    if normalized is None:
        raise ValueError("SEC ticker map had no rows")
    frame = normalized.parsed["tickers"]
    return dict(zip(frame["symbol"], frame["cik"], strict=True))


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
    writer: StoreWriter,
    reader: StoreReader,
    sources: CompanySources,
    session: date,
    force: bool = False,
    limit: int | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> RunRecord:
    now = clock()
    run_id = new_run_id(JOB, session, now)
    reference = instruments(reader, session)
    failed: list[str] = []
    try:
        sec_map = _ticker_map(sources.tickers, writer, session, run_id)
    except Exception as exc:  # reference CIKs still work without the map
        failed.append(f"tickers: {exc}")
        sec_map = {}
    ids = assign_ciks(reference, sec_map)
    known = ids[ids["cik"].notna()]
    ciks = sorted(set(known["cik"]))
    previous = _previous(reader, session)
    due = due_ciks(ciks, previous, session, sources.refresh_days, force)
    todo = due if limit is None else due[: max(limit, 0)]
    fetched, not_found = [], 0
    for cik in todo:
        request = FetchRequest(cik, session_date=session)
        try:
            payload = sources.submissions.fetch(request)
            if payload is None:
                not_found += 1  # no filings under this CIK (common for funds)
                continue
            writer.raw.put(
                sources.submissions.name, sources.submissions.dataset, session, run_id, cik, payload
            )
            normalized = sources.submissions.normalize(request, payload)
            if normalized is not None:
                fetched.append(normalized.parsed["company"].assign(cik=cik, fetched_on=session))
        except Exception as exc:
            failed.append(f"{cik}: {exc}")
    details = _merge_details(previous, fetched)
    rows = known.merge(details, on="cik", how="inner") if not details.empty else known.iloc[:0]
    if not rows.empty:
        rows = rows.sort_values("instrument_id").reset_index(drop=True)
        rows = rows.astype(object).where(rows.notna(), None)
        writer.write_table(
            TABLE, session, run_id, stamp(rows, session, now, sources.submissions.name, run_id)
        )
    stats = {
        "instruments": len(ids),
        "cik_from_reference": int(ids["cik_source"].eq("reference").sum()),
        "cik_from_sec_map": int(ids["cik_source"].eq("sec_map").sum()),
        "no_cik": int(ids["cik"].isna().sum()),
        "ciks": len(ciks),
        "due": len(due),
        "requested": len(todo),
        "fetched": len(fetched),
        "no_submissions": not_found,
        "deferred_by_limit": len(due) - len(todo),
        "failed": failed[:20],
        "failed_count": len(failed),
        "rows": len(rows),
    }
    status = RunStatus.PARTIAL if failed else RunStatus.COMPLETE
    record = RunRecord(run_id, JOB, session, now, status, now, stats=stats)
    writer.save_run(record)
    return record


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
