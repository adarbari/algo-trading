"""The regime overlay's evaluation (ADR 0049): every strategy on every golden dataset run
without and with the overlay over the same sessions, compared on max drawdown, Sharpe and time
in market (``exposure``: the share of bars with a position).

The overlay is the site's ``[regime]`` (its multipliers, pauses and unknown size) whether or not
it is enabled. A dataset whose sessions have no market feature rows in the store is left out;
with none at all the report says so instead of failing (the golden store has no regime rows
until the regime group is backfilled over it).
"""

from collections.abc import Iterable
from dataclasses import dataclass, replace

from algotrade.analytics.report import markdown_table
from algotrade.config.strategy.regime import RegimeSettings
from algotrade.core.model.errors import MissingDataError
from algotrade.data import StoreReader
from algotrade.engines.backtest.config import BacktestConfig
from algotrade.engines.backtest.engine import run_backtest
from algotrade.services.backtests.market import load_market_features
from algotrade.services.backtests.run import regime_overlays
from algotrade.services.datasets import load_datasets, strategy_datasets
from algotrade.strategies.trading.registry import STRATEGIES, create_strategy

NO_ROWS = "regime overlay: no market feature rows in the store"
METRICS = ("max_drawdown", "sharpe", "exposure")


@dataclass(frozen=True)
class OverlayComparison:
    strategy: str
    dataset: str
    without: dict[str, float]  # METRICS without the overlay
    overlaid: dict[str, float]  # METRICS with it
    reasons: dict[str, int]  # bars per overlay reason

    def as_row(self) -> dict[str, float | str]:
        row: dict[str, float | str] = {"strategy": self.strategy, "dataset": self.dataset}
        for m in METRICS:
            row[m], row[f"{m}_overlay"] = self.without[m], self.overlaid[m]
        return row


def compare_overlay(
    reader: StoreReader,
    regime: RegimeSettings,
    strategies: Iterable[str] | None = None,
    datasets: Iterable[str] | None = None,
    config: BacktestConfig | None = None,
) -> list[OverlayComparison]:
    """Each strategy x dataset with market feature rows, without and with the overlay."""
    overlays = regime_overlays(replace(regime, enabled=True))
    rows: list[OverlayComparison] = []
    if datasets is None:
        datasets = strategy_datasets(reader)
    for dataset, (data, terms) in load_datasets(reader, datasets).items():
        timeline = next(iter(data.values())).timestamps
        try:
            market = load_market_features(reader, [regime.label], timeline)
        except MissingDataError:
            continue
        for name in strategies or sorted(STRATEGIES):
            base = run_backtest(data, create_strategy(name), config, terms).metrics.as_dict()
            with_overlay = run_backtest(
                data, create_strategy(name), config, terms, overlays=overlays, market=market
            )
            over = with_overlay.metrics.as_dict()
            rows.append(
                OverlayComparison(
                    name,
                    dataset,
                    {m: base[m] for m in METRICS},
                    {m: over[m] for m in METRICS},
                    dict(with_overlay.overlay_reasons),
                )
            )
    return rows


def overlay_report(rows: list[OverlayComparison]) -> str:
    """The comparison as a Markdown table, or ``NO_ROWS`` when nothing could be compared."""
    if not rows:
        return NO_ROWS
    columns = ["strategy", "dataset", *(c for m in METRICS for c in (m, f"{m}_overlay"))]
    table = markdown_table([r.as_row() for r in rows], columns)
    return f"regime overlay (without vs with):\n\n{table}"
