"""Run the full strategy x golden-dataset grid, reading data only from storage."""

import math
from collections.abc import Iterable
from dataclasses import dataclass

from algotrade.core.errors import AlgoTradeError
from algotrade.data import StoreReader
from algotrade.engines.backtest.config import BacktestConfig
from algotrade.engines.backtest.engine import run_backtest
from algotrade.services.datasets import load_datasets
from algotrade.strategies.trading.registry import STRATEGIES, create_strategy

BENCHMARK = "buy_and_hold"


@dataclass(frozen=True)
class EvaluationRow:
    strategy: str
    dataset: str
    metrics: dict[str, float]

    @property
    def key(self) -> str:
        return f"{self.strategy}@{self.dataset}"


def run_suite(
    reader: StoreReader,
    strategies: Iterable[str] | None = None,
    datasets: Iterable[str] | None = None,
    config: BacktestConfig | None = None,
) -> list[EvaluationRow]:
    rows: list[EvaluationRow] = []
    for dataset, (data, terms) in load_datasets(reader, datasets).items():
        for name in strategies or sorted(STRATEGIES):
            result = run_backtest(data, create_strategy(name), config, terms)
            metrics = result.metrics.as_dict()
            bad = [k for k, v in metrics.items() if not math.isfinite(v)]
            if bad:
                raise AlgoTradeError(f"{name}@{dataset} produced non-finite metrics: {bad}")
            rows.append(EvaluationRow(name, dataset, metrics))
    return rows


def with_benchmark_excess(rows: list[EvaluationRow]) -> list[dict[str, float | str]]:
    """Flatten rows for reporting, adding Sharpe/return in excess of buy-and-hold."""
    bench = {r.dataset: r.metrics for r in rows if r.strategy == BENCHMARK}
    out: list[dict[str, float | str]] = []
    for r in rows:
        flat: dict[str, float | str] = {"strategy": r.strategy, "dataset": r.dataset, **r.metrics}
        if r.dataset in bench:
            flat["excess_return"] = r.metrics["total_return"] - bench[r.dataset]["total_return"]
            flat["excess_sharpe"] = r.metrics["sharpe"] - bench[r.dataset]["sharpe"]
        out.append(flat)
    return out
