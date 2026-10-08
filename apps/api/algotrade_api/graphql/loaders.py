"""The dataloaders of one request (ADR 0037): a type resolves a child object or a per-object
read only through one, so a list of N parents costs one read, not N (no N+1).

Each is keyed ``(instrument_id, *arguments)``; a batch makes one loader call per distinct
arguments for all the instruments that asked them (``features``: one ``load_feature_values``
per distinct ``names``), off the event loop. A loader's error is the result of each key in its
call. ``screener_latest_run``: keyed ``(owner, config_id)``; one ``load_latest_runs`` call (one
read of the session's screen results) per batch."""

from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import date
from functools import partial
from typing import Any

from strawberry.dataloader import DataLoader

from algotrade.services.read.context import ReadContext
from algotrade.services.read.evaluation.track_record import TrackRecord, load_track_records_for
from algotrade.services.read.events.instrument_events import (
    InstrumentEvents,
    load_instrument_events,
)
from algotrade.services.read.events.stored import Event, load_events
from algotrade.services.read.instruments.chains import (
    OptionChain,
    OptionQuote,
    load_chains,
    load_quotes,
)
from algotrade.services.read.instruments.features import FeatureValue, load_feature_values
from algotrade.services.read.instruments.holdings import Holdings, load_holdings
from algotrade.services.read.instruments.identity import Instrument, load_instruments
from algotrade.services.read.instruments.prices import Adjustment, PriceSeries, load_prices
from algotrade.services.read.instruments.series import FeatureSeries, load_series
from algotrade.services.read.screens.hits import ScreenerHit, load_screener_hits
from algotrade.services.read.screens.runs import LatestRun, RunKey, load_latest_runs
from algotrade_api.graphql.offload import off_loop

FeatureKey = tuple[str, tuple[str, ...]]  # (instrument_id, catalogue names in the order asked)
EventKey = tuple[str, date | None, date | None]  # (instrument_id, start, end)
EventStudyKey = tuple[str, int, int]  # (instrument_id, days, months)
QuoteKey = tuple[str, date]  # (underlying_id, expiry)
HoldingsKey = tuple[str, int]  # (fund_id, top)
PriceKey = tuple[str, date, date | None, Adjustment]  # (instrument_id, start, end, adjustment)
SeriesKey = tuple[str, tuple[str, ...], date, date | None]  # (instrument_id, names, start, end)

# load(ctx, instrument_ids, *arguments) -> {instrument_id: value} (absent: None)
Load = Callable[..., Mapping[str, Any]]


async def batched(
    load: Load, ctx: ReadContext, keys: Sequence[tuple[Any, ...]]
) -> list[Any | BaseException]:
    """One ``load`` call per distinct arguments (``key[1:]``) for every instrument that asked
    them; each key's value, else the error of its call."""
    by_arguments: dict[tuple[Any, ...], list[str]] = {}
    for key in keys:
        by_arguments.setdefault(tuple(key[1:]), []).append(key[0])
    found: dict[tuple[Any, ...], Any | BaseException] = {}
    for arguments, ids in by_arguments.items():
        try:  # off the event loop: the reads are parquet and pandas work
            values = await off_loop(partial(load, ctx, ids, *arguments))
        except Exception as error:  # the error is the result of each key that asked
            found.update({(iid, *arguments): error for iid in ids})
        else:
            found.update({(iid, *arguments): values.get(iid) for iid in ids})
    return [found[tuple(key)] for key in keys]


def _loader[K: tuple[Any, ...], V](load: Load, ctx: ReadContext) -> DataLoader[K, V]:
    async def load_fn(keys: list[K]) -> list[V | BaseException]:
        return await batched(load, ctx, keys)

    return DataLoader(load_fn=load_fn)


def _feature_values(
    ctx: ReadContext, keys: Sequence[FeatureKey]
) -> Awaitable[list[tuple[FeatureValue, ...] | BaseException]]:
    """The ``features`` batch (kept by name: the tests count its reads)."""
    return batched(load_feature_values, ctx, keys)


async def _latest_runs(ctx: ReadContext, keys: Sequence[RunKey]) -> list[LatestRun]:
    found = await off_loop(load_latest_runs, ctx, keys)
    return [found[key] for key in keys]


class Loaders:
    """The dataloaders of one request, over its ``ReadContext`` (one session)."""

    def __init__(self, ctx: ReadContext) -> None:
        async def feature_values(
            keys: list[FeatureKey],
        ) -> list[tuple[FeatureValue, ...] | BaseException]:
            return await _feature_values(ctx, keys)

        self.features: DataLoader[FeatureKey, tuple[FeatureValue, ...]] = DataLoader(
            load_fn=feature_values
        )
        self.instruments: DataLoader[tuple[str], Instrument | None] = _loader(load_instruments, ctx)
        self.events: DataLoader[EventKey, tuple[Event, ...]] = _loader(load_events, ctx)
        self.instrument_events: DataLoader[EventStudyKey, InstrumentEvents | None] = _loader(
            load_instrument_events, ctx
        )
        self.chains: DataLoader[tuple[str], OptionChain | None] = _loader(load_chains, ctx)
        self.quotes: DataLoader[QuoteKey, tuple[OptionQuote, ...]] = _loader(load_quotes, ctx)
        self.holdings: DataLoader[HoldingsKey, Holdings | None] = _loader(load_holdings, ctx)
        self.prices: DataLoader[PriceKey, PriceSeries] = _loader(load_prices, ctx)
        self.series: DataLoader[SeriesKey, FeatureSeries] = _loader(load_series, ctx)
        self.screener_hits: DataLoader[tuple[str], tuple[ScreenerHit, ...]] = _loader(
            load_screener_hits, ctx
        )

        self.track_records: DataLoader[tuple[str], tuple[TrackRecord, ...]] = _loader(
            load_track_records_for, ctx
        )

        async def latest_runs(keys: list[RunKey]) -> list[LatestRun]:
            return await _latest_runs(ctx, keys)

        self.screener_latest_run: DataLoader[RunKey, LatestRun] = DataLoader(load_fn=latest_runs)
