"""A backtest's market features (ADR 0049): read from the market feature store onto the bar
timeline (session t at index t, unknown where nothing is stored), and the regime overlay in a
configured backtest."""

from datetime import date

import pytest

from algotrade.config.user import UserContext
from algotrade.core.model.errors import ConfigurationError, MissingDataError
from algotrade.core.time.clock import business_days
from algotrade.data import StoreReader
from algotrade.services.backtests.market import MARKET, load_market_features
from algotrade.services.backtests.run import run_configured_backtest
from algotrade.services.configs import resolve_config
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.tables.result_writer import ResultWriter
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped
from tests.unit.services.backtests.test_backtests import LOADED, START, T0, backend, bull_config

__all__ = ["backend"]  # the golden store fixture, shared with test_backtests

LABEL = "market.regime@v1.label"
REGIME = "rollups/market/regime@v1"


def write_labels(writer: StoreWriter, labels: dict[date, str | None]) -> None:
    for day, label in labels.items():
        row = {"instrument_id": MARKET, "label": label}
        writer.write_table(REGIME, day, "m1", stamped([row], day, "m1", LOADED))


def test_values_sit_on_the_bar_timeline_without_lookahead() -> None:
    b = MemoryBackend()
    timeline = business_days("2024-01-01", 5)  # Mon 1 .. Fri 5 January
    days = [d.item() for d in timeline.astype("datetime64[D]")]
    write_labels(StoreWriter(b), {days[0]: "CALM", days[1]: "STRESS", days[3]: None})
    market = load_market_features(StoreReader(b), [LABEL], timeline)
    assert [market.at(t)[LABEL] for t in range(5)] == ["CALM", "STRESS", None, None, None]
    assert market.timestamps is timeline


def test_nothing_stored_is_missing_data_and_other_fields_are_refused() -> None:
    reader = StoreReader(MemoryBackend())
    timeline = business_days("2024-01-01", 3)
    with pytest.raises(MissingDataError, match="market-rollups"):
        load_market_features(reader, [LABEL], timeline)
    with pytest.raises(ConfigurationError, match="not a market feature field"):
        load_market_features(reader, ["rollup.iv30@v1.iv30"], timeline)
    assert load_market_features(reader, [LABEL], timeline[:0]).names == (LABEL,)


def test_a_configured_backtest_applies_the_regime_overlay(backend: MemoryBackend) -> None:
    end = date(2020, 3, 31)
    bars = business_days(START.isoformat(), 70).astype("datetime64[D]")  # the golden timeline
    sessions = [d.item() for d in bars if d.item() <= end]
    stress = set(sessions[20:30])
    write_labels(StoreWriter(backend), {d: "STRESS" if d in stress else "CALM" for d in sessions})
    reader = StoreReader(backend)
    on = bull_config(regime={"enabled": True})
    store = MemoryConfigStore({("alice", "strategies", "bull_bh"): on})
    config = resolve_config(store, "bull_bh", UserContext("alice"))
    outcome = run_configured_backtest(reader, config, START, end, ResultWriter(backend), T0)
    assert outcome.result.overlay_reasons == {"regime=STRESS: x0.5": 10}
    assert outcome.result.metrics.num_trades == 3  # buy, halve in the storm, back to full
    (run,) = reader.runs("backtest-bull_bh-alice", end)
    assert run.stats["overlay_reasons"] == {"regime=STRESS: x0.5": 10}

    off = MemoryConfigStore({("alice", "strategies", "bull_bh"): bull_config()})
    plain = run_configured_backtest(
        reader, resolve_config(off, "bull_bh", UserContext("alice")), START, end
    )
    assert plain.result.metrics.num_trades == 1 and plain.result.overlay_reasons == {}
    assert plain.config.hash != config.hash
