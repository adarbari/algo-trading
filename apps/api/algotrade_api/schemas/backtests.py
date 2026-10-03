"""``/backtests``: saved backtest runs and one run's detail."""

from datetime import date, datetime
from typing import Any

from pydantic import Field

from algotrade_api.schemas.health import Schema


class BacktestSummary(Schema):
    run_id: str
    config_id: str
    user: str = Field(description="whose run (the config's user)")
    status: str = Field(description="complete | partial | failed")
    start: str | None = Field(description="first session (ISO date)")
    end: date = Field(description="last session: the results partition")
    started_at: datetime
    finished_at: datetime | None
    metrics: dict[str, Any] = Field(
        description="performance metrics (sharpe, cagr, max drawdown, ...)"
    )


class EquityPoint(Schema):
    ts: str
    equity: float
    gross_exposure: float


class Fill(Schema):
    ts: str
    instrument_id: str
    side: str
    quantity: float
    price: float
    commission: float
    multiplier: float | None = None


class BacktestDetail(Schema):
    summary: BacktestSummary
    config_hash: str | None
    selection: dict[str, Any]
    data: dict[str, Any]
    rebalances: list[dict[str, Any]]
    equity: list[EquityPoint]
    fills: list[Fill]
