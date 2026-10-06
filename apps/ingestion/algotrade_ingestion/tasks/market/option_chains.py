"""Nightly option-chain snapshot for every universe underlying.

Behaviour carried over from the original liquidity_screen.py and made stricter:
- the most important underlyings are fetched first (``prioritise``), so a run cut short by
  the vendor or the clock still has them: S&P 500 members and the configured
  ``[cboe] priority_symbols``, then by the latest ``feature.liquidity_class`` and
  ``feature.option_chain_oi`` (expression features), then the rest alphabetically;
- every ticker gets a status and a tier (``tiers.py``: core or rest, recorded at fetch time
  for the acceptance check) (OK, NO_CHAIN, NO_STANDARD_SERIES, STALE_DATA, FETCH_ERROR);
  none is dropped;
- the task is resumable: a re-run for the same session reuses finished tickers (OK, NO_CHAIN,
  NO_STANDARD_SERIES) and refetches the STALE_DATA and FETCH_ERROR ones (``RETRYABLE``), so a
  retry after Cboe's delayed feed rolls over refreshes them and keeps the earlier OK rows;
- failures get a second, gentler pass with one worker, after a cool-down the source's shared
  limiter applies to every process (``Throttled``);
- raw responses are saved before parsing (``IngestRun.fetch``), so normalisation can be
  replayed.

Per-ticker results are staged, then published as one partition per table and session. The
staging is kept while FETCH_ERROR or STALE_DATA items remain (a re-run resumes from it and
republishes the merged results), else dropped.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from functools import partial

import pandas as pd

from algotrade.data import StoreReader
from algotrade.data.reference import load_universe, resolver
from algotrade.services.jobs import as_completed
from algotrade.storage.configs.store import ConfigStore
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.framework.run import IngestRun, NoResponseError, TaskContext
from algotrade_ingestion.tasks.market.tiers import CLASS_RANK, Tiers, load_tiers
from algotrade_sources.framework.base import FetchRequest, Source, Throttled

TASK = "option_chains"
OPTIONS, UNDERLYINGS, STATUS = "chains/option_quotes", "chains/underlying_quotes", "chains/status"
CHECKPOINT_EVERY = 100
# Universe rows are all optionable, so many NO_CHAIN results point at a source problem.
MAX_NO_CHAIN_SHARE = 0.25
ORDER_TIERS = ("priority", "liquidity", "rest")


@dataclass(frozen=True)
class Underlying:
    instrument_id: str
    symbol: str


@dataclass(frozen=True)
class ChainJobConfig:
    workers: int = 4
    retry_pause_s: float = 30.0
    priority_symbols: tuple[str, ...] = field(default=())  # fetched first, in this order


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


def prioritise(
    reader: StoreReader,
    session_date: date,
    underlyings: Sequence[Underlying],
    priority_symbols: Sequence[str] = (),
    configs: ConfigStore | None = None,
    tiers: Tiers | None = None,
) -> tuple[list[Underlying], dict[str, int]]:
    """``underlyings`` in fetch order, and how many fell in each tier (``ORDER_TIERS``):

    1. ``priority``: the configured ``priority_symbols`` (in their order), then S&P 500
       members by liquidity;
    2. ``liquidity``: names with a liquidity class or chain open interest, by the
       ``feature.liquidity_class`` expression (HIGH, MEDIUM, LOW, UNKNOWN), then
       ``feature.option_chain_oi`` descending (the site features of ``configs``);
    3. ``rest``: alphabetically.

    ``tiers`` (``load_tiers``) is read from the store when not given.
    Ties break by symbol, so the order is deterministic for a given store."""
    tiers = tiers or load_tiers(reader, session_date, priority_symbols, configs)
    pinned, members, liquidity = tiers.pinned, tiers.members, tiers.liquidity
    last = (len(CLASS_RANK), 0.0)

    def key(u: Underlying) -> tuple[int, int, int, float, str]:
        rank, oi = liquidity.get(u.instrument_id, last)
        if u.symbol.upper() in pinned:
            return (0, pinned[u.symbol.upper()], 0, 0.0, u.symbol)
        if u.instrument_id in members:
            return (0, len(pinned), rank, oi, u.symbol)
        if u.instrument_id in liquidity:
            return (1, 0, rank, oi, u.symbol)
        return (2, 0, 0, 0.0, u.symbol)

    ordered = sorted(underlyings, key=key)
    counts = dict.fromkeys(ORDER_TIERS, 0)
    for u in ordered:
        counts[ORDER_TIERS[key(u)[0]]] += 1
    return ordered, counts


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


def _publish(
    run: IngestRun, universe: Sequence[Underlying], tiers: Tiers, source_name: str
) -> None:
    for table in (UNDERLYINGS, OPTIONS):
        run.publish(table)
    status = pd.DataFrame(
        [
            {
                "instrument_id": u.instrument_id,
                "symbol": u.symbol,
                "status": run.items.get(u.instrument_id, "NOT_ATTEMPTED"),
                "tier": tiers.tier(u.instrument_id, u.symbol),  # graded by check_chains
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
        tier_rule = load_tiers(run.reader, session_date, config.priority_symbols, ctx.configs)
        ordered, tiers = prioritise(
            run.reader, session_date, universe, config.priority_symbols, ctx.configs, tier_rule
        )
        _run_pass(run, source, [u for u in ordered if u.instrument_id not in run.items],
                  config.workers)  # fmt: skip
        failed = [u for u in ordered if run.items.get(u.instrument_id, "").startswith("FETCH")]
        if failed:
            if isinstance(source, Throttled):
                source.cool_down(config.retry_pause_s)
            _run_pass(run, source, failed, 1)
        _publish(run, universe, tier_rule, source.name)
        counts = run.counts()
        no_chain_share = counts.get("NO_CHAIN", 0) / len(universe) if universe else 0.0
        run.stats.update(universe=len(universe), statuses=counts, order_tiers=tiers)
        if no_chain_share > MAX_NO_CHAIN_SHARE:
            run.partial(f"{no_chain_share:.0%} of optionable names returned no chain")
    return run.record  # staging: dropped by IngestRun unless retryable items remain
