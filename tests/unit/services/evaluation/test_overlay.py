"""The regime overlay's with-versus-without evaluation (ADR 0049) on a synthetic store."""

from dataclasses import replace
from datetime import date

import pytest

from algotrade.config.strategy.regime import RegimeSettings
from algotrade.core.time.clock import business_days
from algotrade.data import StoreReader
from algotrade.services.evaluation.overlay import NO_ROWS, compare_overlay, overlay_report
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.writers import StoreWriter
from tests.unit.services.backtests.test_backtests import backend
from tests.unit.services.backtests.test_market import write_labels

__all__ = ["backend"]  # the golden store fixture

REGIME = RegimeSettings()  # off: the evaluation applies it anyway


def test_without_market_rows_the_report_says_so(backend: MemoryBackend) -> None:
    unstored = replace(REGIME, label="market.unstored@v1.label")  # no table in any store
    rows = compare_overlay(StoreReader(backend), unstored, ["buy_and_hold"], ["bull_trend"])
    assert rows == [] and overlay_report(rows) == NO_ROWS


@pytest.fixture(scope="module")
def stormy(backend: MemoryBackend) -> StoreReader:
    """Every bull_trend session labelled: a storm in 20..39, CALM to 59, then stored nulls."""
    days = [d.item() for d in business_days("2020-01-01", 756).astype("datetime64[D]")]
    labels: dict[date, str | None] = dict.fromkeys(days, None)
    labels.update(dict.fromkeys(days[:60], "CALM"))
    labels.update(dict.fromkeys(days[20:40], "STRESS"))
    write_labels(StoreWriter(backend), labels)
    return StoreReader(backend)


def test_each_strategy_runs_without_and_with_the_overlay(stormy: StoreReader) -> None:
    (row,) = compare_overlay(stormy, REGIME, ["buy_and_hold"], ["bull_trend"])
    assert (row.strategy, row.dataset) == ("buy_and_hold", "bull_trend")
    assert set(row.without) == set(row.overlaid) == {"max_drawdown", "sharpe", "exposure"}
    assert row.without["exposure"] > row.overlaid["exposure"]  # flat once the label is unknown
    assert row.reasons["regime=STRESS: x0.5"] == 20 and row.reasons["regime unknown"] > 0
    again = compare_overlay(stormy, REGIME, ["buy_and_hold"], ["bull_trend"])
    assert again == [row]  # deterministic
    report = overlay_report([row])
    assert report.startswith("regime overlay (without vs with)")
    assert "max_drawdown_overlay" in report and "| buy_and_hold | bull_trend |" in report
