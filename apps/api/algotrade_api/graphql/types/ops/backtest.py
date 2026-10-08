"""``Backtest`` (a saved backtest run) and ``BacktestDetail`` (what it decided on and did: the
selection audit, data versions, rebalances, equity curve and fills)."""

import datetime as dt
from typing import Any, Self

import strawberry
from strawberry.scalars import JSON

from algotrade.services.read.availability.cause import public_audit
from algotrade.services.read.ops import backtests
from algotrade_api.graphql.permissions import AdminCause


@strawberry.type(
    description="A saved backtest run: `status` complete, partial or failed; `start` / `end` "
    "its first and last session; `metrics` (sharpe, cagr, max drawdown, ...)"
)
class Backtest:
    run_id: str
    config_id: str
    user: str
    status: str
    start: str | None
    end: dt.date
    started_at: dt.datetime
    finished_at: dt.datetime | None
    metrics: JSON

    @classmethod
    def of(cls, d: backtests.Backtest) -> Self:
        return cls(
            run_id=d.run_id,
            config_id=d.config_id,
            user=d.user,
            status=d.status,
            start=d.start,
            end=d.end,
            started_at=d.started_at,
            finished_at=d.finished_at,
            metrics=JSON(d.metrics),
        )


@strawberry.type(description="The portfolio after one bar: equity and gross exposure")
class EquityPoint:
    ts: str
    equity: float | None
    gross_exposure: float | None

    @classmethod
    def of(cls, d: backtests.EquityPoint) -> Self:
        return cls(ts=d.ts, equity=d.equity, gross_exposure=d.gross_exposure)


@strawberry.type(description="One simulated fill")
class Fill:
    ts: str
    instrument_id: str
    side: str
    quantity: float | None
    price: float | None
    commission: float | None
    multiplier: float | None

    @classmethod
    def of(cls, d: backtests.Fill) -> Self:
        return cls(
            ts=d.ts,
            instrument_id=d.instrument_id,
            side=d.side,
            quantity=d.quantity,
            price=d.price,
            commission=d.commission,
            multiplier=d.multiplier,
        )


def _public(_: object, document: Any) -> JSON:
    """A trader's copy of a stored document: without the tables a run went without (ADR 0056)."""
    return JSON(public_audit(document))


@strawberry.type(
    description="A saved run with its config hash, selection audit, `data` (as_of, "
    "data_versions, reference_snapshot, survivorship_bias), rebalance evaluations, equity "
    "curve and fills"
)
class BacktestDetail:
    summary: Backtest
    config_hash: str | None
    selection: JSON = strawberry.field(extensions=[AdminCause(public=_public)])
    data: JSON = strawberry.field(extensions=[AdminCause(public=_public)])
    rebalances: list[JSON] = strawberry.field(
        extensions=[AdminCause(public=lambda _, found: [_public(_, r) for r in found])]
    )
    equity: list[EquityPoint]
    fills: list[Fill]

    @classmethod
    def of(cls, d: backtests.BacktestDetail) -> Self:
        return cls(
            summary=Backtest.of(d.summary),
            config_hash=d.config_hash,
            selection=JSON(d.selection),
            data=JSON(d.data),
            rebalances=[JSON(r) for r in d.rebalances],
            equity=[EquityPoint.of(p) for p in d.equity],
            fills=[Fill.of(f) for f in d.fills],
        )
