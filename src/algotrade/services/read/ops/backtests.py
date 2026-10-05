"""Saved backtest runs (``Backtest``): every run of every strategy config the user sees (theirs
and the site's), newest first, and one run's detail (``BacktestDetail``): metrics, selection
audit, data versions, rebalances, the equity curve and the fills.

Run records, not session data: a run is identified by its ``run_id`` and its results are the
rows it wrote to ``results/backtest_{equity,fills}`` for its own end session, read as the run
left them (``context.run_partition``)."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from algotrade.config.user import SITE_USER
from algotrade.services.backtests.run import EQUITY, FILLS, run_job_name
from algotrade.services.read.context import Stores, run_partition
from algotrade.services.read.ops.configs import configs_of
from algotrade.services.read.values import to_scalar
from algotrade.storage.runs import RunRecord
from algotrade.storage.tables.schemas import result_table

JOB_PREFIX = "backtest-"
STRATEGY = "strategy"
DATA_KEYS = ("as_of", "data_versions", "reference_snapshot", "survivorship_bias")


@dataclass(frozen=True)
class Backtest:
    """One saved run. ``user``: whose run; ``status``: complete, partial or failed; ``start``:
    the first session (ISO date); ``end``: the last session (its results partition);
    ``metrics``: sharpe, cagr, max drawdown, ..."""

    run_id: str
    config_id: str
    user: str
    status: str
    start: str | None
    end: date
    started_at: datetime
    finished_at: datetime | None
    metrics: dict[str, Any]


@dataclass(frozen=True)
class EquityPoint:
    ts: str
    equity: float | None
    gross_exposure: float | None


@dataclass(frozen=True)
class Fill:
    ts: str
    instrument_id: str
    side: str
    quantity: float | None
    price: float | None
    commission: float | None
    multiplier: float | None


@dataclass(frozen=True)
class BacktestDetail:
    """A run with what it decided on and what it did. ``data``: ``as_of``, ``data_versions``,
    ``reference_snapshot``, ``survivorship_bias``; ``rebalances``: the selection's
    evaluations, one per rebalance."""

    summary: Backtest
    config_hash: str | None
    selection: dict[str, Any]
    data: dict[str, Any]
    rebalances: tuple[dict[str, Any], ...]
    equity: tuple[EquityPoint, ...]
    fills: tuple[Fill, ...]


def _backtest(run: RunRecord) -> Backtest:
    stats = run.stats
    return Backtest(
        run_id=run.run_id,
        config_id=str(stats.get("config_id", "")),
        user=str(stats.get("user", "")),
        status=run.status.value,
        start=stats.get("start"),
        end=run.session_date,
        started_at=run.started_at,
        finished_at=run.finished_at,
        metrics=dict(stats.get("metrics") or {}),
    )


def load_backtests(ctx: Stores) -> tuple[Backtest, ...]:
    """Every saved run of every strategy config ``ctx.user`` sees, newest first."""
    owners = _owners(ctx)
    ids = sorted(
        {c.config_id for c in configs_of(ctx.configs, ctx.user) if c.kind in (STRATEGY, None)}
    )
    runs = [r for i in ids for o in owners for r in ctx.reader.runs(run_job_name(i, o))]
    return tuple(_backtest(r) for r in sorted(runs, key=lambda r: r.started_at, reverse=True))


def _rows(ctx: Stores, name: str, run: RunRecord) -> list[Mapping[str, Any]]:
    frame = run_partition(ctx, result_table(name), run)
    if frame is None:
        return []
    ordered = frame.sort_values("ts", kind="stable")
    return [{str(k): to_scalar(v) for k, v in r.items()} for r in ordered.to_dict("records")]


def _amount(value: Any) -> float | None:
    """A stored number, or None for a stored null (never NaN: JSON has none)."""
    return float(value) if value is not None else None


def _equity(row: Mapping[str, Any]) -> EquityPoint:
    return EquityPoint(str(row["ts"]), _amount(row["equity"]), _amount(row["gross_exposure"]))


def _fill(row: Mapping[str, Any]) -> Fill:
    return Fill(
        ts=str(row["ts"]),
        instrument_id=str(row["instrument_id"]),
        side=str(row["side"]),
        quantity=_amount(row["quantity"]),
        price=_amount(row["price"]),
        commission=_amount(row["commission"]),
        multiplier=_amount(row.get("multiplier")),
    )


def _owners(ctx: Stores) -> list[str]:
    """Whose runs the user sees: their own, then the site's."""
    return list(dict.fromkeys([ctx.user.user_id, SITE_USER]))


def load_backtest(ctx: Stores, run_id: str) -> BacktestDetail | None:
    """The saved run ``run_id``; ``None`` when there is no such backtest run, or it is
    another user's (only the user's own and the site's runs are theirs to see)."""
    try:
        run = ctx.reader.run(run_id)
    except ValueError:  # not a run id at all
        return None
    if run is None or not run.job.startswith(JOB_PREFIX):
        return None
    if str(run.stats.get("user", "")) not in _owners(ctx):
        return None
    stats = run.stats
    return BacktestDetail(
        summary=_backtest(run),
        config_hash=stats.get("config_hash"),
        selection=dict(stats.get("selection") or {}),
        data={k: stats.get(k) for k in DATA_KEYS},
        rebalances=tuple((stats.get("rebalance") or {}).get("evaluations") or []),
        equity=tuple(_equity(r) for r in _rows(ctx, EQUITY, run)),
        fills=tuple(_fill(r) for r in _rows(ctx, FILLS, run)),
    )
