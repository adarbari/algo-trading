"""``OptionGrid`` (``Instrument.optionGrid``): the puts and calls of one underlying at our delta
bands and expiry buckets for the session, each cell the figures of the short option picked there
(services/read/options/grid.py, ADR 0083 amendment of 2026-11-01). Derived figures only: our mid
premium, delta and IV, return on collateral, yield a year, breakeven, the chance below the
strike, the spread as a share of the mid and open interest; no field carries a vendor bid, ask,
last or size (a fitness test holds it). A cell or column that is not there is an ``Unknown``
saying why, never a number."""

import datetime as dt
from typing import Annotated, Self

import strawberry

from algotrade.services.read.options import grid
from algotrade.services.read.values import Unknown as ReadUnknown
from algotrade_api.graphql.types.instruments.feature import Unknown


@strawberry.type(
    description="The short option at one delta band of one expiry: strike, our delta (signed "
    "as the right) and IV, the mid premium per share (the middle of the stored quote), the "
    "return on collateral (a put's premium over its strike, a call's over the share price), "
    "yield a year (simple, 365 days), breakeven, the model chance of ending below the strike "
    "(r = q = 0), the spread as a share of the mid and open interest"
)
class GridCell:
    band: float
    strike: float
    delta: float
    iv: float
    mid: float
    roc: float
    yield_ann: float
    breakeven: float
    p_below: float
    spread_pct: float
    open_interest: int

    @classmethod
    def of(cls, d: grid.GridCell) -> Self:
        return cls(
            band=d.band, strike=d.strike, delta=d.delta, iv=d.iv, mid=d.mid, roc=d.roc,
            yield_ann=d.yield_ann, breakeven=d.breakeven, p_below=d.p_below,
            spread_pct=d.spread_pct, open_interest=d.open_interest,
        )  # fmt: skip


OptionGridCell = Annotated[
    GridCell | Unknown,
    strawberry.union("OptionGridCell", description="A cell, or why there is none"),
]


def cell_of(d: grid.GridCell | ReadUnknown) -> GridCell | Unknown:
    return GridCell.of(d) if isinstance(d, grid.GridCell) else Unknown.of(d)


@strawberry.type(
    description="A row of the grid: the expiry that stands for `bucket` calendar days and its "
    "days, or `gap` (no listed expiry near it, or one a nearer bucket took). `reportInside` is "
    "true when the next report falls after the session and on or before the expiry; null with "
    "`reportInsideUnknown` when its date is not known (never false then)"
)
class GridExpiry:
    bucket: int
    expiry: dt.date | None
    days: int | None
    report_inside: bool | None
    report_inside_unknown: Unknown | None
    gap: Unknown | None

    @classmethod
    def of(cls, d: grid.GridExpiry) -> Self:
        return cls(
            bucket=d.bucket,
            expiry=d.expiry,
            days=d.days,
            report_inside=d.report_inside,
            report_inside_unknown=_gap_of(d.report_inside_unknown),
            gap=_gap_of(d.gap),
        )


def _gap_of(d: ReadUnknown | None) -> Unknown | None:
    return Unknown.of(d) if d is not None else None


@strawberry.type(
    description="An underlying's option grid for the session. `puts[i][j]` and `calls[i][j]` "
    "are the cell of `columns[i]` at `bands[j]` (|delta|). `pricedAt` is the underlying's price "
    "the cells are priced at; `qKnown` false: the dividend yield was not stored and was priced "
    "as 0. The IV rank is a feature (`features`), not a grid field"
)
class OptionGrid:
    underlying_id: str
    session: dt.date
    priced_at: float
    q_known: bool
    bands: list[float]
    columns: list[GridExpiry]
    puts: list[list[OptionGridCell]]
    calls: list[list[OptionGridCell]]

    @classmethod
    def of(cls, d: grid.OptionGrid) -> Self:
        return cls(
            underlying_id=d.underlying_id,
            session=d.session,
            priced_at=d.priced_at,
            q_known=d.q_known,
            bands=list(d.bands),
            columns=[GridExpiry.of(c) for c in d.columns],
            puts=[[cell_of(c) for c in row] for row in d.puts],
            calls=[[cell_of(c) for c in row] for row in d.calls],
        )


OptionGridResult = Annotated[
    OptionGrid | Unknown,
    strawberry.union("OptionGridResult", description="The grid, or why there is none"),
]


def result_of(d: grid.OptionGrid | ReadUnknown) -> OptionGrid | Unknown:
    return OptionGrid.of(d) if isinstance(d, grid.OptionGrid) else Unknown.of(d)
