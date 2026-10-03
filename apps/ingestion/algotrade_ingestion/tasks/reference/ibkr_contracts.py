"""IBKR contract ids for the optionable universe (``instruments/ibkr_contracts``, ADR 0028).

Each instrument of the option-chain coverage (``option_chains.select_underlyings``) gets its
IB stock contract: ``conid``, primary exchange, security type, currency, and the session it
was resolved (``resolved_at``). Requests go through the read-only facade's allowlisted
``qualifyContracts`` (``ctx.sources["ibkr"]``, opened and closed around the work), batched
(``[ibkr] contracts_batch`` per call, each contract paced as one message).

- Refresh: an instrument is resolved when it has no stored contract (a new optionable name,
  the same night), when its symbol changed, else once per ``[ibkr] contracts_refresh_days``
  on its own slot day (``refresh.due_keys``: spread over the month by key); ``force``
  resolves everything, ``limit`` caps a run.
- Snapshot runs: every run writes the full table (rows not refreshed are carried forward;
  names that left the coverage are dropped). A name IB does not know is ``NOT_FOUND`` (not
  stored, asked again next run; not a failure); a batch IB could not answer is
  ``FETCH_ERROR`` (the run is PARTIAL and a re-run resumes).
- When the gateway cannot be opened the run records ``skipped`` (the nightly step is
  SKIPPED with a WARN, never FAILED).
"""

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import date

import pandas as pd

from algotrade.config.site.settings import IbkrSettings
from algotrade.data.reference import IBKR_CONTRACTS, ibkr_contracts
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.framework.run import IngestRun, NoResponseError, TaskContext
from algotrade_ingestion.tasks.market.option_chains import Underlying, select_underlyings
from algotrade_ingestion.tasks.reference.refresh import due_keys
from algotrade_sources.framework.base import (
    FetchRequest,
    SessionSource,
    SessionUnavailableError,
    opened,
)

TASK = "ibkr_contracts"
TABLE = IBKR_CONTRACTS
SOURCE = "ibkr"
CARRY = "carry"  # staging key of the rows carried forward
COLUMNS = ("instrument_id", "symbol", "conid", "primary_exchange", "sec_type", "currency",
           "resolved_at")  # fmt: skip
NOT_FOUND = "NOT_FOUND"


@dataclass(frozen=True)
class Plan:
    """Who is resolved this run (``due``, in order) and the stored rows kept as they are."""

    due: list[Underlying]
    carried: pd.DataFrame
    deferred: int


def plan(
    underlyings: Sequence[Underlying],
    stored: pd.DataFrame | None,
    session: date,
    settings: IbkrSettings,
    wanted: Collection[str] | None = None,
    force: bool = False,
    limit: int | None = None,
) -> Plan:
    """Who is due among ``wanted`` ids (default: every underlying; named ids are always
    due): new and renamed names first, then those past their slot day (stalest first). The
    other stored rows of ``underlyings`` are carried; rows of names not covered are dropped."""
    known = (
        pd.DataFrame(columns=list(COLUMNS))
        if stored is None
        else stored.reindex(columns=list(COLUMNS)).astype({"instrument_id": str})
    )
    by_id = {u.instrument_id: u for u in underlyings}
    current = known[known["instrument_id"].isin(list(by_id))]
    renamed = [by_id[i].symbol != s for i, s in zip(current["instrument_id"], current["symbol"],
                                                       strict=True)]  # fmt: skip
    same = current[~pd.Series(renamed, index=current.index, dtype=bool)]
    fetched = {
        str(i): pd.Timestamp(d).date()
        for i, d in zip(same["instrument_id"], same["resolved_at"], strict=True)
    }
    candidates = [k for k in by_id if wanted is None or k in set(wanted)]
    every = force or wanted is not None
    keys = due_keys(candidates, fetched, session, settings.contracts_refresh_days, every)
    capped = keys if limit is None else keys[: max(0, limit)]
    carried = same[~same["instrument_id"].isin(capped)]
    return Plan([by_id[k] for k in capped], carried.reset_index(drop=True), len(keys) - len(capped))


def _batches(items: list[Underlying], size: int) -> list[list[Underlying]]:
    return [items[i : i + size] for i in range(0, len(items), max(1, size))]


def _resolve_batch(run: IngestRun, source: SessionSource, batch: list[Underlying]) -> None:
    """One ``qualifyContracts`` call; staged under the batch's first name (stable on resume)."""
    key = "contracts__" + "+".join(u.symbol for u in batch)  # IbkrSource request keys
    first = batch[0].symbol
    normalized = run.fetch(source, FetchRequest(key, None, run.session), f"contracts__{first}")
    if normalized is None or "contracts" not in normalized.parsed:
        raise NoResponseError(f"IBKR {key}: nothing parsed")
    found = normalized.parsed["contracts"].set_index("symbol")
    rows = []
    for u in batch:
        conid = found["conid"].get(u.symbol) if u.symbol in found.index else None
        if conid is None or pd.isna(conid):
            run.record_item(u.instrument_id, NOT_FOUND)
            continue
        row = found.loc[u.symbol]
        rows.append(
            {"instrument_id": u.instrument_id, "symbol": u.symbol, "conid": int(conid),
             "primary_exchange": row.get("primary_exchange"), "sec_type": row.get("sec_type"),
             "currency": row.get("currency"), "resolved_at": run.session}
        )  # fmt: skip
        run.record_item(u.instrument_id, "OK")
    if rows:
        run.stage(TABLE, f"batch_{first}", pd.DataFrame(rows, columns=list(COLUMNS)), SOURCE)


def resolve_contracts(
    ctx: TaskContext,
    source: SessionSource,
    session: date,
    symbols: Sequence[str] = (),
    force: bool = False,
    limit: int | None = None,
) -> RunRecord:
    """Resolve the due contracts of ``session``'s coverage (``symbols``: only those tickers;
    the other stored rows are carried forward)."""
    settings = ctx.settings.ibkr
    with IngestRun(ctx, TASK, session, resume=True) as run:
        everyone = select_underlyings(run.reader, session)
        wanted = (
            {u.instrument_id for u in select_underlyings(run.reader, session, symbols)}
            if symbols
            else None
        )
        p = plan(everyone, ibkr_contracts(run.reader, session), session, settings, wanted,
                 force, limit)  # fmt: skip
        todo = [u for u in p.due if u.instrument_id not in run.items]
        try:
            with opened(source):
                for batch in _batches(todo, settings.contracts_batch):
                    try:
                        _resolve_batch(run, source, batch)
                    except SessionUnavailableError:
                        raise
                    except Exception as exc:
                        for u in batch:
                            run.fail(u.instrument_id, f"{type(exc).__name__}: {exc}")
                    run.checkpoint()
        except SessionUnavailableError as exc:
            run.stats["skipped"] = f"WARN: {exc}"
            return run.record
        if not p.carried.empty:
            carried = p.carried.drop(columns=["session_date"], errors="ignore")
            run.stage(TABLE, CARRY, carried.reindex(columns=list(COLUMNS)), SOURCE)
        rows = run.publish(TABLE)
        counts = run.counts()
        run.stats.update(
            underlyings=len(everyone),
            resolved=rows,
            refreshed=counts.get("OK", 0),
            not_found=counts.get(NOT_FOUND, 0),
            failed_count=len(run.failures()),
            deferred=p.deferred,
            coverage_pct=round(100.0 * rows / len(everyone), 1) if everyone else None,
        )
    return run.record
