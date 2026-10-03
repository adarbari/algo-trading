from datetime import UTC, date, datetime
from typing import Any

import pytest

from algotrade.config.user import UserContext
from algotrade.core.errors import ConfigurationError
from algotrade.services.backtests import PORTFOLIO, run_configured_backtest
from algotrade.services.configs import default_user, resolve_config
from algotrade.services.selection import select
from algotrade.storage.backends.config_files import MemoryConfigStore
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.readers import StoreReader
from algotrade.storage.result_writer import ResultWriter
from algotrade.storage.writers import StoreWriter
from algotrade_ingestion.jobs.golden import load_golden
from algotrade_ingestion.sources.synthetic.files import GoldenFiles
from tests.conftest import GOLDEN_DIR

T0 = datetime(2026, 10, 3, tzinfo=UTC)
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
    load_golden(StoreWriter(b), GoldenFiles(GOLDEN_DIR))
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
