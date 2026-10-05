"""``PriceSeries`` and ``FeatureSeries``: an instrument's daily bars, and catalogue features
per session, over an explicit window (range grain: ``start`` given, ``end`` the session's
date unless given)."""

import datetime as dt
from typing import Self

import strawberry
from strawberry.scalars import JSON

from algotrade.services.read.instruments import prices, series

strawberry.enum(prices.Adjustment, description="How bars are adjusted for corporate actions")


@strawberry.type(description="One session's daily bar, adjusted")
class PriceBar:
    session: dt.date
    open: float
    high: float
    low: float
    close: float
    volume: float
    vwap: float | None

    @classmethod
    def of(cls, d: prices.PriceBar) -> Self:
        return cls(
            session=d.session,
            open=d.open,
            high=d.high,
            low=d.low,
            close=d.close,
            volume=d.volume,
            vwap=d.vwap,
        )


@strawberry.type(description="Daily bars of `start..end`, oldest first")
class PriceSeries:
    instrument_id: str
    adjustment: prices.Adjustment
    start: dt.date
    end: dt.date
    bars: list[PriceBar]

    @classmethod
    def of(cls, d: prices.PriceSeries) -> Self:
        return cls(
            instrument_id=d.instrument_id,
            adjustment=d.adjustment,
            start=d.start,
            end=d.end,
            bars=[PriceBar.of(b) for b in d.bars],
        )


@strawberry.type(description="One session's values, in the order of `FeatureSeries.names`")
class SeriesPoint:
    session: dt.date
    values: list[JSON | None]

    @classmethod
    def of(cls, d: series.SeriesPoint) -> Self:
        return cls(session=d.session, values=[JSON(v) for v in d.values])


@strawberry.type(description="Catalogue features per stored session of `start..end`")
class FeatureSeries:
    instrument_id: str
    names: list[str]
    start: dt.date
    end: dt.date
    points: list[SeriesPoint]

    @classmethod
    def of(cls, d: series.FeatureSeries) -> Self:
        return cls(
            instrument_id=d.instrument_id,
            names=list(d.names),
            start=d.start,
            end=d.end,
            points=[SeriesPoint.of(p) for p in d.points],
        )
