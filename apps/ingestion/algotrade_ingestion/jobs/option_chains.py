"""Nightly option-chain snapshot for every universe underlying.

Behaviour carried over from the original liquidity_screen.py and made stricter:
- every ticker gets a status (OK, NO_CHAIN, NO_STANDARD_SERIES, STALE_DATA, FETCH_ERROR);
  none is dropped;
- the job is resumable: a re-run for the same session reuses finished tickers;
- failures get a second, gentler pass with one worker;
- raw responses are saved before parsing, so normalisation can be replayed.

Per-ticker results are staged, then published as one partition per table and session.
"""

import concurrent.futures as cf
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime

import pandas as pd

from algotrade.storage.runs import RunRecord, RunStatus, new_run_id
from algotrade.storage.writers import StoreWriter
from algotrade_ingestion.jobs.common import stamp
from algotrade_ingestion.sources.base import FetchRequest, Source

JOB = "option_chains"
OPTIONS, UNDERLYINGS, STATUS = "chains/option_quotes", "chains/underlying_quotes", "chains/status"
CHECKPOINT_EVERY = 100
# Universe rows are all optionable, so many NO_CHAIN results point at a source problem.
MAX_NO_CHAIN_SHARE = 0.25


@dataclass(frozen=True)
class Underlying:
    instrument_id: str
    symbol: str


@dataclass(frozen=True)
class ChainJobConfig:
    workers: int = 4
    retry_pause_s: float = 30.0


def _resume_or_start(writer: StoreWriter, session: date, now: datetime) -> RunRecord:
    previous = [r for r in writer.runs_for(JOB, session) if r.status is not RunStatus.COMPLETE]
    if previous:
        record = previous[-1]
        record.items = {k: v for k, v in record.items.items() if not v.startswith("FETCH_ERROR")}
        return record
    return RunRecord(new_run_id(JOB, session, now), JOB, session, now)


def _process(
    source: Source,
    writer: StoreWriter,
    run: RunRecord,
    u: Underlying,
    clock: Callable[[], datetime],
) -> str:
    request = FetchRequest(u.symbol, u.instrument_id, run.session_date)
    payload = source.fetch(request)
    if payload is None:
        return "NO_CHAIN"
    writer.raw.put(source.name, source.dataset, run.session_date, run.run_id, u.symbol, payload)
    normalized = source.normalize(request, payload)
    if normalized is None:
        return "NO_CHAIN"
    if normalized.session_date != run.session_date:
        return f"STALE_DATA: chain is for {normalized.session_date}"
    now = clock()
    for table in (UNDERLYINGS, OPTIONS):
        frame = normalized.tables.get(table)
        if frame is not None and not frame.empty:
            stamped = stamp(frame, run.session_date, now, source.name, run.run_id)
            writer.staging.put(run.run_id, table, u.symbol, stamped)
    options = normalized.tables.get(OPTIONS)
    return "NO_STANDARD_SERIES" if options is None or options.empty else "OK"


def _run_pass(
    source: Source,
    writer: StoreWriter,
    run: RunRecord,
    todo: Sequence[Underlying],
    workers: int,
    clock: Callable[[], datetime],
) -> None:
    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_process, source, writer, run, u, clock): u for u in todo}
        for done, future in enumerate(cf.as_completed(futures), start=1):
            u = futures[future]
            try:
                run.items[u.instrument_id] = future.result()
            except Exception as exc:
                run.items[u.instrument_id] = f"FETCH_ERROR: {exc}"
            if done % CHECKPOINT_EVERY == 0:
                writer.save_run(run)


def _publish(
    writer: StoreWriter,
    run: RunRecord,
    universe: Sequence[Underlying],
    now: datetime,
    source_name: str,
) -> None:
    for table in (UNDERLYINGS, OPTIONS):
        frame = writer.staging.collect(run.run_id, table)
        if frame is not None:
            frame = frame.sort_values("instrument_id", kind="stable").reset_index(drop=True)
            frame["knowledge_ts"] = pd.Timestamp(now)
            writer.write_table(table, run.session_date, run.run_id, frame)
    status = pd.DataFrame(
        [
            {
                "instrument_id": u.instrument_id,
                "symbol": u.symbol,
                "status": run.items.get(u.instrument_id, "NOT_ATTEMPTED"),
            }
            for u in universe
        ]
    )
    writer.write_table(
        STATUS,
        run.session_date,
        run.run_id,
        stamp(status, run.session_date, now, source_name, run.run_id),
    )


def ingest_option_chains(
    writer: StoreWriter,
    source: Source,
    universe: Sequence[Underlying],
    session_date: date,
    config: ChainJobConfig | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleep: Callable[[float], None] = time.sleep,
) -> RunRecord:
    config = config or ChainJobConfig()
    run = _resume_or_start(writer, session_date, clock())
    writer.save_run(run)
    _run_pass(
        source,
        writer,
        run,
        [u for u in universe if u.instrument_id not in run.items],
        config.workers,
        clock,
    )
    failed = [u for u in universe if run.items.get(u.instrument_id, "").startswith("FETCH_ERROR")]
    if failed:
        sleep(config.retry_pause_s)
        _run_pass(source, writer, run, failed, 1, clock)
    now = clock()
    _publish(writer, run, universe, now, source.name)
    counts: dict[str, int] = {}
    for status in run.items.values():
        counts[status.split(":")[0]] = counts.get(status.split(":")[0], 0) + 1
    errors = counts.get("FETCH_ERROR", 0) + counts.get("STALE_DATA", 0)
    no_chain_share = counts.get("NO_CHAIN", 0) / len(universe) if universe else 0.0
    suspicious = no_chain_share > MAX_NO_CHAIN_SHARE
    run.status = RunStatus.PARTIAL if errors or suspicious else RunStatus.COMPLETE
    run.finished_at = now
    run.stats = {"universe": len(universe), "statuses": counts}
    if suspicious:
        run.stats["warning"] = f"{no_chain_share:.0%} of optionable names returned no chain"
    writer.save_run(run)
    if run.status is RunStatus.COMPLETE:
        writer.staging.clear(run.run_id)
    return run
