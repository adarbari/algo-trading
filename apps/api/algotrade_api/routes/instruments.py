"""``/instruments/{id}``: detail, bars, events and feature series; ``/chains/{id}``: its option
chain as stored, ``/chains/{id}/live``: live quotes of one expiry (``id``: an instrument id or a
ticker)."""

from datetime import date
from enum import StrEnum
from typing import Annotated

from fastapi import APIRouter, Query

from algotrade.services.explore import instruments
from algotrade.services.explore.chains import option_chain
from algotrade_api.deps import Live, Store, name_list
from algotrade_api.schemas.instruments import (
    BarSeries,
    FeatureSeries,
    InstrumentDetail,
    InstrumentEvent,
    LiveOptionChain,
    OptionChain,
)

router = APIRouter(prefix="/instruments", tags=["instruments"])
chains = APIRouter(prefix="/chains", tags=["chains"])

From = Annotated[date | None, Query(alias="from")]


class Adjustment(StrEnum):
    splits = "splits"
    none = "none"
    total_return = "total_return"


@router.get("/{instrument_id}")
def detail(
    store: Store, instrument_id: str, on: Annotated[date | None, Query(alias="date")] = None
) -> InstrumentDetail:
    return InstrumentDetail.model_validate(instruments.instrument_detail(store, instrument_id, on))


@router.get("/{instrument_id}/bars")
def bars(
    store: Store,
    instrument_id: str,
    start: From = None,
    to: date | None = None,
    adjust: Adjustment = Adjustment.splits,
) -> BarSeries:
    series = instruments.instrument_bars(store, instrument_id, start, to, adjust.value)
    return BarSeries.model_validate(series)


@router.get("/{instrument_id}/events")
def events(
    store: Store, instrument_id: str, start: From = None, to: date | None = None
) -> list[InstrumentEvent]:
    found = instruments.instrument_events(store, instrument_id, start, to)
    return [InstrumentEvent.model_validate(e) for e in found]


@router.get("/{instrument_id}/features")
def features(
    store: Store,
    instrument_id: str,
    names: Annotated[str | None, Query(description="comma-separated field names")] = None,
    start: From = None,
    to: date | None = None,
) -> FeatureSeries:
    wanted = name_list(names) or None
    series = instruments.instrument_features(store, instrument_id, wanted, start, to)
    return FeatureSeries.model_validate(series)


@chains.get("/{underlying_id}")
def chain(
    store: Store,
    underlying_id: str,
    on: Annotated[date | None, Query(alias="date")] = None,
    expiry: date | None = None,
) -> OptionChain:
    return OptionChain.model_validate(option_chain(store, underlying_id, on, expiry))


@chains.get("/{underlying_id}/live")
def live_chain(
    store: Store,
    live: Live,
    underlying_id: str,
    expiry: date,
    strikes: Annotated[
        list[float] | None,
        Query(
            description="strikes to quote (repeat the parameter); default: those nearest "
            "the underlying"
        ),
    ] = None,
) -> LiveOptionChain:
    """Live quotes from IB Gateway (read-only, cached briefly); the stored delayed chain with
    a status when the gateway cannot answer. Each live answer is recorded (``live/*``)."""
    return LiveOptionChain.model_validate(live.chain(store, underlying_id, expiry, strikes))
