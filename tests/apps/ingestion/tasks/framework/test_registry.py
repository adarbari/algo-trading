"""The task registry: defaults come from settings in one place; sources come from the context."""

from datetime import date
from pathlib import Path
from typing import Any

import pytest

from algotrade.config.site.settings import SourcesSettings
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.runs import RunRecord
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.framework import registry
from algotrade_ingestion.tasks.framework.registry import TASKS, run_task, session_of, task
from algotrade_ingestion.tasks.market import (
    bars,
    corporate_actions,
    earnings,
    etf_holdings,
    option_chains,
)
from algotrade_ingestion.tasks.profile import descriptions
from algotrade_ingestion.workflows.nightly import nightly as pipeline
from algotrade_sources.vendors.ssga.etf_holdings import SsgaHoldings
from tests.helpers.ingest_fakes import FIXED, http_for, task_ctx

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
        (etf_holdings, "ingest_etf_holdings"),
        (descriptions, "ingest_descriptions"),
    ):
        monkeypatch.setattr(module, fn, fake)
    monkeypatch.setattr(option_chains, "select_underlyings", lambda reader, d, s: list(s))
    return fake


SETTINGS = SourcesSettings(
    actions_window=(-3, 10), earnings_days=20, earnings_lookback_days=7, cboe_workers=8
)
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
    run_task("earnings", ctx(), {"session": DAY})  # the last week too: 7 back + 20 ahead
    assert calls.args[-1][1:4] == ("ea", DAY, date(2026, 9, 25))
    assert calls.args[-1][4] == {"days": 27}
    run_task("earnings", ctx(), {"session": DAY, "days": 5})
    assert calls.args[-1][4] == {"days": 12}
    run_task("earnings", ctx(), {"session": DAY, "start": date(2026, 7, 1), "days": 95})
    assert calls.args[-1][1:4] == ("ea", DAY, date(2026, 7, 1)) and calls.args[-1][4] == {
        "days": 95
    }
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


def test_etf_holdings_takes_its_defaults_from_settings(calls: Calls) -> None:
    ssga = SsgaHoldings(http_for(lambda url: b""))
    settings = SourcesSettings.from_document(
        {"etf_holdings": {"refresh_days": 3, "keep_top": 20, "fallback_scope": "all"}}
    )
    c = task_ctx(StoreWriter(MemoryBackend()), sources={"ssga_holdings": ssga}, settings=settings)
    run_task("etf-holdings", c, {"session": DAY, "symbols": "xlk, spy", "limit": 5})
    _, sources, session, force, limit, only, _ = calls.args[-1]
    assert (sources.issuers, sources.refresh_days, sources.keep_top) == ([ssga], 3, 20)
    assert (sources.fallback_scope, session, force, limit, only) == (
        "all",
        DAY,
        False,
        5,
        ["xlk", "spy"],
    )


def test_the_nightly_reads_a_slice_of_funds_and_the_cli_reads_everything(calls: Calls) -> None:
    ssga = SsgaHoldings(http_for(lambda url: b""))
    ctx = task_ctx(StoreWriter(MemoryBackend()), sources={"ssga_holdings": ssga})

    def limit_of(params: dict[str, Any], settings: SourcesSettings | None = None) -> Any:
        ctx.settings = settings or SourcesSettings()
        run_task("etf-holdings", ctx, {"session": DAY, **params})
        return calls.args[-1][4]

    assert limit_of({}) is None  # `algotrade-ingest etf-holdings`: every fund due
    assert limit_of({"nightly": True}) == 200  # [etf_holdings] per_night
    assert limit_of({"nightly": True, "limit": 7}) == 7  # an explicit limit wins
    uncapped = SourcesSettings.from_document({"etf_holdings": {"per_night": 0}})
    assert limit_of({"nightly": True}, uncapped) is None  # 0: no cap
    custom = SourcesSettings.from_document({"etf_holdings": {"per_night": 25}})
    assert limit_of({"nightly": True}, custom) == 25


def test_the_nightly_step_runs_after_bars_and_chains_with_the_nightly_flag() -> None:
    names = [step.name for step in pipeline.NIGHTLY]
    assert names.index("etf-holdings") > names.index("chains") > names.index("bars")
    step = pipeline.NIGHTLY[names.index("etf-holdings")]
    assert step.params == {"nightly": True} and step.latest_only


def test_etf_holdings_is_skipped_without_an_issuer_or_when_switched_off() -> None:
    c = task_ctx(StoreWriter(MemoryBackend()))
    c.unavailable = {"ssga_holdings": "[ssga] is disabled in sources.toml"}
    reason = pipeline.skip_reason("etf-holdings", c) or ""
    assert reason.startswith("skipped: ") and "[ssga] is disabled" in reason
    assert "ishares_holdings is not configured" in reason
    c.sources = {"ssga_holdings": SsgaHoldings(http_for(lambda url: b""))}
    assert pipeline.skip_reason("etf-holdings", c) is None
    c.settings = SourcesSettings.from_document({"etf_holdings": {"enabled": False}})
    assert (
        pipeline.skip_reason("etf-holdings", c)
        == "skipped: [etf_holdings] is disabled in sources.toml"
    )
    with pytest.raises(KeyError, match="needs one of the sources"):
        c.sources = {}
        run_task("etf-holdings", c, {"session": DAY})


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
    assert pipeline.skip_reason("rollups", c) is None


def test_every_task_declares_a_description_and_sessions_where_needed() -> None:
    for spec in TASKS.values():
        assert spec.description and spec.module.__doc__
        names = {p.name for p in spec.params}
        if spec.name not in ("migrate-ids", "golden-load"):
            assert "session" in names, spec.name
    assert Path("datasets/golden") == registry.GOLDEN_DIR


def test_descriptions_reads_every_source_it_declares(calls: Calls) -> None:
    """The CLI builds only the sources a task declares (``optional_sources``): the series source
    the ETF path matches funds with was left out once, and no run used it."""
    names = {
        "massive_overview": "mo",
        "sec_fund_tickers": "ft",
        "sec_fund_objectives": "fo",
        "sec_fund_series": "fs",
    }
    assert set(names) <= set(task("descriptions").optional_sources)
    c = task_ctx(StoreWriter(MemoryBackend()), sources=names, settings=SETTINGS)
    run_task("descriptions", c, {"session": DAY})
    wired = calls.args[-1][1]
    assert (wired.overview, wired.fund_tickers, wired.fund_objectives, wired.fund_series) == (
        "mo", "ft", "fo", "fs",
    )  # fmt: skip
