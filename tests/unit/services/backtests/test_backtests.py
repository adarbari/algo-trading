from datetime import UTC, date, datetime
from typing import Any

import pytest

from algotrade.config.user import UserContext
from algotrade.core.model.errors import ConfigurationError, MissingDataError
from algotrade.data import StoreReader
from algotrade.services.backtests.run import PORTFOLIO, run_configured_backtest
from algotrade.services.configs import default_user, resolve_config
from algotrade.services.selection import select
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.tables.result_writer import ResultWriter
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.sources.framework.registry import fixture_source
from algotrade_ingestion.tasks.maintenance.golden import load_golden
from tests.conftest import GOLDEN_DIR
from tests.ingest_helpers import task_ctx

T0 = datetime(2026, 10, 3, tzinfo=UTC)  # the injected launch clock: backtests read as_of T0
LOADED = datetime(2026, 10, 1, tzinfo=UTC)  # when the golden data was stored (before T0)
START, END = date(2020, 1, 1), date(2022, 12, 31)


def bull_config(**extra: Any) -> dict[str, Any]:
    return {
        "id": "bull_bh",
        "kind": "strategy",
        "impl": "buy_and_hold",
        "selection": {
            "name": "bull",
            "where": {"all": [{"field": "instrument.symbol", "op": "eq", "value": "BULL"}]},
        },
        **extra,
    }


@pytest.fixture(scope="module")
def backend() -> MemoryBackend:
    b = MemoryBackend()
    load_golden(
        task_ctx(StoreWriter(b), clock=lambda: LOADED), fixture_source("synthetic", GOLDEN_DIR)
    )
    return b


def test_results_and_data_versions_are_saved(backend: MemoryBackend) -> None:
    store = MemoryConfigStore({("alice", "strategies", "bull_bh"): bull_config()})
    config = resolve_config(store, "bull_bh", UserContext("alice"))
    reader = StoreReader(backend)
    outcome = run_configured_backtest(reader, config, START, END, ResultWriter(backend), T0)
    assert outcome.run_id is not None
    equity = reader.table("results/backtest_equity", END)
    fills = reader.table("results/backtest_fills", END)
    assert equity is not None and fills is not None
    assert set(equity["instrument_id"]) == {PORTFOLIO}
    assert len(equity) == len(outcome.result.equity)
    assert list(fills["instrument_id"]) == ["EQ:BULL"]
    assert set(fills["config_hash"]) == {config.hash}
    (run,) = reader.runs("backtest-bull_bh-alice", END)
    assert run.stats["data_versions"]["bars/1d"] == outcome.versions["bars/1d"]
    assert run.stats["metrics"]["num_trades"] == 1
    assert run.stats["as_of"] == T0.isoformat()  # data pinned to the launch time
    assert run.stats["survivorship_bias"] is False
    assert run.stats["reference_snapshot"] == "2020-01-01"
    assert run_configured_backtest(reader, config, START, END).run_id is None  # no writer, no save


def test_missing_rollup_is_unknown_not_an_error(backend: MemoryBackend) -> None:
    config = bull_config(
        selection={
            "name": "liquid",
            "where": {
                "all": [{"field": "rollup.option_liquidity@v1.put_tier", "op": "eq", "value": "A"}]
            },
        }
    )
    resolved = resolve_config(
        MemoryConfigStore({("u", "strategies", "bull_bh"): config}), "bull_bh", UserContext("u")
    )
    assert resolved.selection is not None
    result = select(StoreReader(backend), resolved.selection, START)
    assert result.empty
    assert result.unknown_excluded == result.base
    assert result.as_dict()["missing_tables"] == ["rollups/instrument/option_liquidity@v1"]
    with pytest.raises(ConfigurationError, match="matched no instruments"):
        run_configured_backtest(StoreReader(backend), resolved, START, END)


def test_default_user_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ALGOTRADE_USER", raising=False)
    assert default_user("local").user_id == "local"
    monkeypatch.setenv("ALGOTRADE_USER", "alice")
    assert default_user("local").user_id == "alice"


def test_start_before_the_first_reference_snapshot_flags_survivorship(
    backend: MemoryBackend,
) -> None:
    store = MemoryConfigStore({("alice", "strategies", "bull_bh"): bull_config()})
    config = resolve_config(store, "bull_bh", UserContext("alice"))
    early = date(2019, 12, 2)  # the golden reference snapshot is 2020-01-01
    outcome = run_configured_backtest(StoreReader(backend), config, early, END, now=T0)
    assert outcome.survivorship_bias is True
    assert outcome.reference_snapshot == START
    assert outcome.data_stats()["survivorship_bias"] is True
    same = run_configured_backtest(StoreReader(backend), config, START, END, now=T0)
    assert same.survivorship_bias is False
    assert outcome.result.metrics.as_dict() == same.result.metrics.as_dict()  # no bars before


def test_as_of_pins_the_data_version(backend: MemoryBackend) -> None:
    store = MemoryConfigStore({("alice", "strategies", "bull_bh"): bull_config()})
    config = resolve_config(store, "bull_bh", UserContext("alice"))
    with pytest.raises(MissingDataError):  # nothing was stored yet at that launch time
        run_configured_backtest(
            StoreReader(backend), config, START, END, now=LOADED.replace(year=2025)
        )
