"""Use case: run a configured strategy backtest over stored data."""

from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from typing import Any

import pandas as pd

from algotrade.config.site.settings import BacktestSettings
from algotrade.config.strategy.resolve import ResolvedConfig
from algotrade.core.model.errors import ConfigurationError
from algotrade.data import StoreReader
from algotrade.data.prices import load_price_data
from algotrade.engines.backtest.config import BacktestConfig
from algotrade.engines.backtest.costs import CostModel
from algotrade.engines.backtest.engine import run_backtest
from algotrade.engines.backtest.limits import RiskLimits
from algotrade.engines.backtest.result import BacktestResult
from algotrade.engines.backtest.universe import Schedule
from algotrade.engines.selection.evaluate import SelectionResult
from algotrade.engines.selection.schedule import Rebalance, turnover
from algotrade.services.backtests.rebalance import load_rebalanced
from algotrade.services.selection import select
from algotrade.storage.runs import start_run
from algotrade.storage.tables.result_writer import ResultWriter
from algotrade.strategies.trading.registry import create_strategy

PORTFOLIO = "PORTFOLIO"  # instrument_id for portfolio-level result rows (the equity curve)
EQUITY = "backtest_equity"  # results/<name> tables a saved backtest writes
FILLS = "backtest_fills"


def run_job_name(config_id: str, user: str) -> str:
    """The run-record ``job`` of a saved backtest of ``config_id`` for ``user``."""
    return f"backtest-{config_id}-{user}"


def backtest_settings(bt: BacktestSettings) -> BacktestConfig:
    """Typed ``[backtest]`` settings -> engine config (price adjustment applies on read)."""
    costs, limits = bt.costs, bt.limits
    return BacktestConfig(
        initial_cash=bt.initial_cash,
        costs=CostModel(
            commission_bps=costs.commission_bps,
            min_commission=costs.min_commission,
            slippage_bps=costs.slippage_bps,
        ),
        limits=RiskLimits(
            max_position_weight=limits.max_position_weight,
            max_gross_exposure=limits.max_gross_exposure,
            allow_short=limits.allow_short,
        ),
        lot_size=bt.lot_size,
        cash_buffer=bt.cash_buffer,
        periods_per_year=bt.periods_per_year,
    )


@dataclass(frozen=True)
class BacktestOutcome:
    config: ResolvedConfig
    selection: SelectionResult
    result: BacktestResult
    versions: dict[str, list[str]]
    as_of: datetime  # data version pin: stored data as known at launch (ADR 0007)
    reference_snapshot: date  # the instruments/reference snapshot used for ``start``
    survivorship_bias: bool  # ``start`` (or any rebalance session) is before the first snapshot
    run_id: str | None = None  # set when results were saved
    rebalances: tuple[Rebalance, ...] = ()  # every selection evaluation (rebalance_selection)

    def data_stats(self) -> dict[str, Any]:
        """What a run must record to be reproduced: the version pin and the data read."""
        stats: dict[str, Any] = {
            "as_of": self.as_of.isoformat(),
            "data_versions": self.versions,
            "reference_snapshot": self.reference_snapshot.isoformat(),
            "survivorship_bias": self.survivorship_bias,
        }
        if self.rebalances:
            bt = self.config.backtest
            stats["rebalance"] = {
                "frequency": bt.rebalance_selection,
                "lag_sessions": bt.selection_lag_sessions,
                "instruments_ever_selected": len(
                    {i for r in self.rebalances for i in r.selection.instruments}
                ),
                "mean_turnover": turnover(self.rebalances),
                "evaluations": [r.as_dict() for r in self.rebalances],
            }
        return stats


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
    for name, base in ((EQUITY, equity), (FILLS, fills)):
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


def _check_selected(config: ResolvedConfig, selected: SelectionResult, start: date) -> None:
    if selected.empty:
        raise ConfigurationError(f"{config.config.id}: selection matched no instruments on {start}")


def run_configured_backtest(
    reader: StoreReader,
    config: ResolvedConfig,
    start: date,
    end: date,
    writer: ResultWriter | None = None,
    now: datetime | None = None,
) -> BacktestOutcome:
    """Selection is evaluated on ``start`` (no survivorship from today's universe, unless
    ``start`` is before the first reference snapshot: then ``survivorship_bias`` is set).
    With ``[backtest] rebalance_selection`` it is re-evaluated point in time on each rebalance
    session and the tradable set changes (``services.backtests.rebalance``; the audit of every
    evaluation is in ``data_stats()["rebalance"]``).

    Data is read as stored at launch: ``as_of = now`` pins the version (ADR 0007), so a
    rerun with the same ``now`` reads the same rows even after later ingestion runs.

    With a ``writer``, the equity curve and fills are saved as ``results/backtest_equity`` and
    ``results/backtest_fills`` (partitioned by ``end``), and a run record stores the metrics,
    the selection audit, the config hash and the exact data runs read.
    """
    if config.config.kind != "strategy":
        raise ConfigurationError(f"{config.config.id} is a {config.config.kind}, not a strategy")
    if config.selection is None:
        raise ConfigurationError(f"{config.config.id}: a backtest needs a selection")
    now = now or datetime.now(UTC)
    bt = config.backtest
    schedule: Schedule | None = None
    history: tuple[Rebalance, ...] = ()
    if bt.rebalance_selection == "none":
        selected = select(reader, config.selection, start, as_of=now)
        _check_selected(config, selected, start)
        data = load_price_data(
            reader, selected.instruments, start, end, as_of=now, adjustment=bt.price_adjustment
        )
    else:
        rebalanced = load_rebalanced(reader, config.selection, start, end, bt, now)
        history = rebalanced.rebalances
        selected = history[0].selection
        _check_selected(config, selected, start)
        data, schedule = rebalanced.prices, rebalanced.schedule
    strategy = create_strategy(config.config.impl, **dict(config.config.params))
    result = run_backtest(data.series, strategy, backtest_settings(bt), data.terms, schedule)
    outcome = BacktestOutcome(
        config,
        selected,
        result,
        data.versions,
        now,
        data.reference.snapshot_date,
        data.reference.pre_snapshot or any(r.survivorship_bias for r in history),
        rebalances=history,
    )
    if writer is None:
        return outcome
    user = config.user.user_id
    record = start_run(run_job_name(config.config.id, user), end, now)
    run_id = record.run_id
    with writer.publishing(run_id, now):  # every result table visible at once (ADR 0022)
        for name, frame in _result_frames(outcome, end, run_id, now).items():
            if not frame.empty:
                writer.write_result(name, end, run_id, frame, pending=True)
    stats = {
        "user": user,
        "config_id": config.config.id,
        "config_hash": config.hash,
        "config_layers": list(config.layers),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "selection": selected.as_dict(),
        "metrics": result.metrics.as_dict(),
        **outcome.data_stats(),
    }
    writer.save_run(record.finish(now, stats=stats))
    return replace(outcome, run_id=run_id)
