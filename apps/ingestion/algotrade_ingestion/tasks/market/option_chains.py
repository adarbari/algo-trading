"""Nightly option-chain snapshot for every universe underlying.

Behaviour carried over from the original liquidity_screen.py and made stricter:
- every ticker gets a status (OK, NO_CHAIN, NO_STANDARD_SERIES, STALE_DATA, FETCH_ERROR);
  none is dropped;
- the task is resumable: a re-run for the same session reuses finished tickers;
- failures get a second, gentler pass with one worker, after a cool-down the source's shared
  limiter applies to every process (``Throttled``);
- raw responses are saved before parsing (``IngestRun.fetch``), so normalisation can be
  replayed.

Per-ticker results are staged, then published as one partition per table and session.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from functools import partial

import pandas as pd

from algotrade.data import StoreReader
from algotrade.data.reference import load_universe, resolver
from algotrade.services.jobs import as_completed
from algotrade.storage.runs import RunRecord, RunStatus
from algotrade_ingestion.sources.framework.base import FetchRequest, Source, Throttled
from algotrade_ingestion.tasks.framework.run import IngestRun, NoResponseError, TaskContext

TASK = "option_chains"
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


def universe_underlyings(reader: StoreReader, session_date: date) -> list[Underlying]:
    """Option-chain coverage (a site rule, not a user choice): every active, optionable
    instrument in the universe. Strategies narrow this further with their selections."""
    frame = load_universe(reader, session_date).frame
    covered = frame[(frame["status"].str.upper() == "ACTIVE") & frame["optionable"].astype(bool)]
    return [Underlying(str(r.instrument_id), str(r.symbol)) for r in covered.itertuples()]


def select_underlyings(
    reader: StoreReader, session_date: date, symbols: Sequence[str] = ()
) -> list[Underlying]:
    """The chain coverage, narrowed to ``symbols`` (tickers, any case) when given."""
    underlyings = universe_underlyings(reader, session_date)
    if not symbols:
        return underlyings
    wanted = set(resolver(reader, session_date).ids_for(list(symbols)).values())
    return [u for u in underlyings if u.instrument_id in wanted]


def _process(run: IngestRun, source: Source, u: Underlying) -> str:
    request = FetchRequest(u.symbol, u.instrument_id, run.session)
    try:
        normalized = run.fetch(source, request)
    except NoResponseError:
        return "NO_CHAIN"
    if normalized is None:
        return "NO_CHAIN"
    if normalized.session_date != run.session:
        return f"STALE_DATA: chain is for {normalized.session_date}"
    for table in (UNDERLYINGS, OPTIONS):
        frame = normalized.tables.get(table)
        if frame is not None and not frame.empty:
            run.stage(table, u.symbol, frame, source.name)
    options = normalized.tables.get(OPTIONS)
    return "NO_STANDARD_SERIES" if options is None or options.empty else "OK"


def _run_pass(run: IngestRun, source: Source, todo: Sequence[Underlying], workers: int) -> None:
    work = as_completed(partial(_process, run, source), todo, workers)
    for done, (underlying, outcome) in enumerate(work, start=1):
        run.attempt(underlying.instrument_id, outcome)
        if done % CHECKPOINT_EVERY == 0:
            run.checkpoint()


def _publish(run: IngestRun, universe: Sequence[Underlying], source_name: str) -> None:
    for table in (UNDERLYINGS, OPTIONS):
        run.publish(table)
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
    run.write(STATUS, status, source_name)


def ingest_option_chains(
    ctx: TaskContext,
    source: Source,
    universe: Sequence[Underlying],
    session_date: date,
    config: ChainJobConfig | None = None,
) -> RunRecord:
    config = config or ChainJobConfig()
    with IngestRun(ctx, TASK, session_date, resume=True) as run:
        run.checkpoint()
        _run_pass(run, source, [u for u in universe if u.instrument_id not in run.items],
                  config.workers)  # fmt: skip
        failed = [u for u in universe if run.items.get(u.instrument_id, "").startswith("FETCH")]
        if failed:
            if isinstance(source, Throttled):
                source.cool_down(config.retry_pause_s)
            _run_pass(run, source, failed, 1)
        _publish(run, universe, source.name)
        counts = run.counts()
        no_chain_share = counts.get("NO_CHAIN", 0) / len(universe) if universe else 0.0
        run.stats.update(universe=len(universe), statuses=counts)
        if no_chain_share > MAX_NO_CHAIN_SHARE:
            run.partial(f"{no_chain_share:.0%} of optionable names returned no chain")
    if run.record.status is RunStatus.COMPLETE:
        run.clear_staging()
    return run.record
