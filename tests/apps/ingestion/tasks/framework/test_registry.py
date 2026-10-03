"""The task registry: defaults come from settings in one place; sources come from the context."""

from datetime import date
from pathlib import Path
from typing import Any

import pytest

from algotrade.config.settings import SourcesSettings
from algotrade.storage.backends.config_files import MemoryConfigStore
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunRecord
from algotrade.storage.writers import StoreWriter
from algotrade_ingestion.tasks.framework import registry
from algotrade_ingestion.tasks.framework.registry import TASKS, run_task, session_of, task
from algotrade_ingestion.tasks.market import bars, corporate_actions, earnings, option_chains
from algotrade_ingestion.workflows.nightly import nightly as pipeline
from tests.ingest_helpers import FIXED, task_ctx

DAY = date(2026, 10, 2)


class Calls:
    def __init__(self) -> None:
        self.args: list[tuple[Any, ...]] = []

    def __call__(self, *args: Any, **kwargs: Any) -> RunRecord:
        self.args.append((*args, kwargs))
        return RunRecord("r", "t", DAY, FIXED)


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> Calls:
    fake = Calls()
    for module, fn in (
        (corporate_actions, "ingest_corporate_actions"),
        (earnings, "ingest_earnings"),
        (bars, "ingest_daily_bars"),
        (option_chains, "ingest_option_chains"),
    ):
        monkeypatch.setattr(module, fn, fake)
    monkeypatch.setattr(option_chains, "select_underlyings", lambda reader, d, s: list(s))
    return fake


SETTINGS = SourcesSettings(actions_window=(-3, 10), earnings_days=20, cboe_workers=8)
SOURCES: dict[str, Any] = {
    "massive_corporate_actions": "ca",
    "nasdaq_earnings": "ea",
    "massive_bars": "mb",
    "cboe": "cb",
}


def ctx() -> Any:
    return task_ctx(StoreWriter(MemoryBackend()), sources=SOURCES, settings=SETTINGS)


def test_settings_defaults_are_applied_by_the_task(calls: Calls) -> None:
    run_task("corporate-actions", ctx(), {"session": DAY})
    assert calls.args[-1][2:5] == (DAY, date(2026, 9, 29), date(2026, 10, 12))
    run_task("earnings", ctx(), {"session": DAY})
    assert calls.args[-1][1:4] == ("ea", DAY, None) and calls.args[-1][4] == {"days": 20}
    run_task("earnings", ctx(), {"session": DAY, "days": 5})
    assert calls.args[-1][4] == {"days": 5}
    run_task("chains", ctx(), {"session": DAY, "symbols": "spy, aapl"})
    _, source, underlyings, _, config, _ = calls.args[-1]
    assert (source, underlyings, config.workers) == ("cb", ["spy", " aapl"], 8)


def test_bars_window_defaults_to_the_session(calls: Calls) -> None:
    run_task("bars", ctx(), {"session": DAY})
    assert calls.args[-1][2] == [DAY]
    run_task("bars", ctx(), {"session": DAY, "start": date(2026, 9, 28), "force": True})
    assert len(calls.args[-1][2]) == 5 and calls.args[-1][3] is True


def test_missing_sources_and_session_fail_early() -> None:
    with pytest.raises(KeyError, match="needs sources"):
        run_task("bars", task_ctx(StoreWriter(MemoryBackend())), {"session": DAY})
    with pytest.raises(KeyError, match="unknown task"):
        task("nope")
    with pytest.raises(ValueError, match="session"):
        session_of({})


def test_universe_build_needs_a_directory_source() -> None:
    c = task_ctx(StoreWriter(MemoryBackend()), sources={"nasdaq_trader": 1, "spy_holdings": 2})
    c.configs = MemoryConfigStore({})
    with pytest.raises(TypeError, match="DirectorySource"):
        run_task("universe-build", c, {"session": DAY})


def test_nightly_skips_tasks_without_sources_or_by_rule() -> None:
    c = task_ctx(StoreWriter(MemoryBackend()), sources={"nasdaq_trader": 1, "spy_holdings": 2})
    assert pipeline.skip_reason("bars", c) == "skipped: massive_bars is not configured"
    c.unavailable = {"massive_bars": "ALGOTRADE_MASSIVE_API_KEY is not set: add it"}
    assert (
        pipeline.skip_reason("bars", c) == "skipped: ALGOTRADE_MASSIVE_API_KEY is not set: add it"
    )
    assert pipeline.skip_reason("universe-build", c) == "skipped: csv_import mode"  # no configs
    c.configs = MemoryConfigStore({("site", "settings", "universe"): {"source": "nasdaq_trader"}})
    assert pipeline.skip_reason("universe-build", c) is None
    assert pipeline.skip_reason("features", c) is None


def test_every_task_declares_a_description_and_sessions_where_needed() -> None:
    for spec in TASKS.values():
        assert spec.description and spec.module.__doc__
        names = {p.name for p in spec.params}
        if spec.name not in ("migrate-ids", "golden-load"):
            assert "session" in names, spec.name
    assert Path("datasets/golden") == registry.GOLDEN_DIR
