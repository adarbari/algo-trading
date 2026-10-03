"""Use case: run a configured strategy backtest over stored data."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from typing import Any

import pandas as pd

from algotrade.config.resolve import ResolvedConfig
from algotrade.core.errors import ConfigurationError
from algotrade.engines.backtest.config import BacktestConfig
from algotrade.engines.backtest.costs import CostModel
from algotrade.engines.backtest.engine import run_backtest
from algotrade.engines.backtest.limits import RiskLimits
from algotrade.engines.backtest.result import BacktestResult
from algotrade.engines.selection.evaluate import SelectionResult
from algotrade.services.market_data import load_price_data
from algotrade.services.selection import select
from algotrade.storage.readers import StoreReader
from algotrade.storage.result_writer import ResultWriter
from algotrade.storage.runs import RunRecord, RunStatus, new_run_id
from algotrade.strategies.trading.registry import create_strategy

PORTFOLIO = "PORTFOLIO"  # instrument_id for portfolio-level result rows (the equity curve)


def backtest_settings(settings: Mapping[str, Any]) -> BacktestConfig:
    """Resolved ``[backtest]`` settings -> engine config."""
    bt = {k: v for k, v in settings["backtest"].items() if k != "price_adjustment"}
    return BacktestConfig(
        initial_cash=float(bt["initial_cash"]),
        costs=CostModel(**bt["costs"]),
        limits=RiskLimits(**bt["limits"]),
        lot_size=float(bt["lot_size"]),
        cash_buffer=float(bt["cash_buffer"]),
        periods_per_year=int(bt["periods_per_year"]),
    )


@dataclass(frozen=True)
class BacktestOutcome:
    config: ResolvedConfig
    selection: SelectionResult
    result: BacktestResult
    versions: dict[str, list[str]]
    run_id: str | None = None  # set when results were saved


def _result_frames(
    outcome: BacktestOutcome, end: date, run_id: str, now: datetime
) -> dict[str, pd.DataFrame]:
    r, c = outcome.result, outcome.config
    equity = pd.DataFrame(
        {
            "instrument_id": PORTFOLIO,
            "ts": pd.to_datetime(r.timestamps, utc=True),
            "equity": r.equity,
            "gross_exposure": r.gross_exposure,
        }
    )
    fills = pd.DataFrame(
        [
            {
                "instrument_id": f.instrument_id,
                "ts": pd.Timestamp(f.timestamp),
                "side": f.side.value,
                "quantity": f.quantity,
                "price": f.price,
                "commission": f.commission,
                "multiplier": f.multiplier,
            }
            for f in r.fills
        ],
        columns=["instrument_id", "ts", "side", "quantity", "price", "commission", "multiplier"],
    )
    out = {}
    for name, base in (("backtest_equity", equity), ("backtest_fills", fills)):
        frame = base.assign(
            user_id=c.user.user_id,
            config_id=c.config.id,
            config_hash=c.hash,
            session_date=end,
            knowledge_ts=pd.Timestamp(now),
            source=f"backtest:{c.config.impl}",
            run_id=run_id,
        )
        out[name] = frame
    return out


def run_configured_backtest(
    reader: StoreReader,
    config: ResolvedConfig,
    start: date,
    end: date,
    writer: ResultWriter | None = None,
    now: datetime | None = None,
) -> BacktestOutcome:
    """Selection is evaluated as of ``start`` (no survivorship from today's universe).

    With a ``writer``, the equity curve and fills are saved as ``results/backtest_equity`` and
    ``results/backtest_fills`` (partitioned by ``end``), and a run record stores the metrics,
    the selection audit, the config hash and the exact data runs read.
    """
    if config.config.kind != "strategy":
        raise ConfigurationError(f"{config.config.id} is a {config.config.kind}, not a strategy")
    if config.selection is None:
        raise ConfigurationError(f"{config.config.id}: a backtest needs a selection")
    selected = select(reader, config.selection, start)
    if selected.empty:
        raise ConfigurationError(f"{config.config.id}: selection matched no instruments on {start}")
    adjustment = str(config.settings["backtest"].get("price_adjustment", "splits"))
    data = load_price_data(reader, selected.instruments, start, end, adjustment=adjustment)
    strategy = create_strategy(config.config.impl, **dict(config.config.params))
    result = run_backtest(data.series, strategy, backtest_settings(config.settings), data.terms)
    outcome = BacktestOutcome(config, selected, result, data.versions)
    if writer is None:
        return outcome
    now = now or datetime.now(UTC)
    user = config.user.user_id
    job = f"backtest-{config.config.id}-{user}"
    run_id = new_run_id(job, end, now)
    for name, frame in _result_frames(outcome, end, run_id, now).items():
        if not frame.empty:
            writer.write_result(name, end, run_id, frame)
    stats = {
        "user": user,
        "config_id": config.config.id,
        "config_hash": config.hash,
        "config_layers": list(config.layers),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "selection": selected.as_dict(),
        "metrics": result.metrics.as_dict(),
        "data_versions": data.versions,
    }
    writer.save_run(RunRecord(run_id, job, end, now, RunStatus.COMPLETE, now, stats=stats))
    return replace(outcome, run_id=run_id)
