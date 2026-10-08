"""A rule screen through the screen use case: selection, field view, evaluation, the two
result tables (published together), the run summary in the run record."""

from datetime import date, timedelta
from typing import Any

import pytest

from algotrade.config.user import SITE_USER, UserContext
from algotrade.data import StoreReader
from algotrade.engines.screening.runner import RunCoverage
from algotrade.services.configs import nightly_screeners, resolve_config
from algotrade.services.jobs import JobStatus, LocalJobRunner
from algotrade.services.jobs.handlers import LIBRARY_HANDLERS
from algotrade.services.screening import run as run_module
from algotrade.services.screening.run import run_screener
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.runs import RunStatus
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import T0, reference_rows, stamped, universe_rows

DAY = date(2026, 10, 2)
LIQ = "rollup.option_liquidity@v1"
SCREEN: dict[str, Any] = {
    "id": "big_liquid",
    "kind": "screener",
    "impl": "rules",
    "version": 4,
    "selection": "active",
    "screening": {"min_coverage": 0.5},
    "criteria": {
        "price": {"field": f"{LIQ}.underlying_price", "op": "gt", "value": 50},
        "oi": {
            "field": f"{LIQ}.chain_oi",
            "op": "gte",
            "value": 1000,
            "mode": "soft",
            "tolerance": {"relative": 0.5},
        },
    },
    "flags": {"cheap": {"all": [{"field": f"{LIQ}.underlying_price", "op": "lt", "value": 70}]}},
    "columns": {"tier": f"{LIQ}.put_tier"},
    "rank": {"tie_break": f"{LIQ}.underlying_price"},
}
ACTIVE = {
    "name": "active",
    "where": {
        "all": [
            {"field": "instrument.status", "op": "eq", "value": "ACTIVE"},
            {"field": "instrument.security_type", "op": "in", "value": ["COMMON_STOCK", "ETF"]},
        ]
    },
}


def configs(**screen: Any) -> MemoryConfigStore:
    return MemoryConfigStore(
        {
            ("site", "selections", "active"): ACTIVE,
            ("site", "strategies", "big_liquid"): {**SCREEN, **screen},
        }
    )


def seeded(features_stored: bool = True) -> tuple[StoreReader, StoreWriter]:
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    universe = universe_rows(["AAA", "BBB", "CCC"], last_verified="2026-10-01")
    universe += universe_rows(["ETF1"], security_type="ETF", asset_class="ETF")
    universe += universe_rows(["DEAD"], status="DELISTED")
    snapshot = DAY - timedelta(days=2)
    writer.write_table("universe", snapshot, "u1", stamped(universe, DAY, "u1"))
    writer.write_table(
        "instruments/reference", snapshot, "u1", stamped(reference_rows(universe), DAY, "u1")
    )
    features = [
        {"instrument_id": "EQ:AAA", "underlying_price": 100.0, "chain_oi": 5000, "put_tier": "A"},
        {"instrument_id": "EQ:BBB", "underlying_price": 60.0, "chain_oi": 700, "put_tier": "C"},
        {"instrument_id": "EQ:ETF1", "underlying_price": 40.0, "chain_oi": 5000, "put_tier": "B"},
    ]
    if features_stored:
        writer.write_table(
            "rollups/instrument/option_liquidity@v1", DAY, "f1", stamped(features, DAY, "f1")
        )
    return StoreReader(backend), writer


def test_a_missing_rollup_table_is_a_partial_run_not_a_clean_one() -> None:
    """ADR 0030: every row would read as missing data and a HARD criterion rejects it; the run
    must not come out COMPLETE (it used to, by skipping every row)."""
    reader, writer = seeded(features_stored=False)
    config = resolve_config(configs(), "big_liquid", UserContext(SITE_USER))
    outcome = run_screener(reader, writer, config, DAY, now=T0)
    assert outcome.run.coverage is RunCoverage.PARTIAL
    assert outcome.audit["missing_tables"] == ["rollups/instrument/option_liquidity@v1"]
    assert set(outcome.audit["decisions"]) == {"REJECT"}


def test_rule_screen_writes_both_tables_and_the_summary() -> None:
    reader, writer = seeded()
    config = resolve_config(configs(), "big_liquid", UserContext(SITE_USER))
    outcome = run_screener(reader, writer, config, DAY, now=T0)
    assert outcome.run.coverage is RunCoverage.COMPLETE  # every row is decided: none is skipped
    assert outcome.audit["decisions"] == {"QUALIFIED": 1, "WATCH": 1, "REJECT": 2}
    summary = outcome.audit["summary"]
    assert summary["passed"] == 1 and "skipped" not in summary
    (miss,) = summary["narrow_misses"]
    assert (miss["instrument_id"], miss["criterion_id"], miss["distance"]) == ("EQ:BBB", "oi", 300)
    assert outcome.audit["config_version"] == 4

    screen = reader.table("results/rule_screen", DAY)
    assert screen is not None
    by_id = screen.set_index("instrument_id")
    assert list(screen.sort_values("rank")["instrument_id"]) == [
        "EQ:AAA",
        "EQ:BBB",
        "EQ:ETF1",
        "EQ:CCC",
    ]
    assert by_id.loc["EQ:AAA", "score"] == 100.0
    assert by_id.loc["EQ:BBB", "decision"] == "WATCH" and by_id.loc["EQ:BBB", "near_missed"] == "oi"
    assert by_id.loc["EQ:ETF1", "failed"] == "price"
    assert by_id.loc["EQ:CCC", "missing"] == "price,oi"
    assert set(screen["config_hash"]) == {config.hash} and set(screen["config_version"]) == {4}
    assert set(screen["user_id"]) == {SITE_USER} and set(screen["run_id"]) == {outcome.run_id}

    values = reader.table("results/rule_screen_values", DAY)
    assert values is not None
    assert len(values) == 4 * 3  # two criteria + one display column per instrument
    oi = values[(values["instrument_id"] == "EQ:BBB") & (values["criterion_id"] == "oi")]
    assert oi.iloc[0][["outcome", "value_num", "normalised"]].tolist() == ["NEAR", 700.0, 0.6]
    column = values[(values["mode"] == "column") & (values["instrument_id"] == "EQ:AAA")]
    assert column.iloc[0][["outcome", "value_str"]].tolist() == ["INFO", "A"]

    (record,) = reader.runs("screen-big_liquid-site", DAY)
    assert record.status is RunStatus.COMPLETE and record.stats["summary"] == summary


def test_two_configs_share_the_tables_without_hiding_each_other() -> None:
    reader, writer = seeded()
    store = MemoryConfigStore(
        {
            ("site", "selections", "active"): ACTIVE,
            ("site", "strategies", "big_liquid"): SCREEN,
            ("site", "strategies", "other"): {**SCREEN, "id": "other"},
        }
    )
    for cid, at in (("big_liquid", T0), ("other", T0 + timedelta(minutes=1))):
        run_screener(
            reader, writer, resolve_config(store, cid, UserContext(SITE_USER)), DAY, now=at
        )
    screen = reader.table("results/rule_screen", DAY)
    assert screen is not None
    assert sorted(set(screen["config_id"])) == ["big_liquid", "other"]
    assert len(screen) == 8


def test_failed_write_publishes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    reader, writer = seeded()
    config = resolve_config(configs(), "big_liquid", UserContext(SITE_USER))
    real = run_module.rule_frames

    def broken(*args: Any) -> dict[str, Any]:
        frames = real(*args)
        frames["rule_screen_values"] = frames["rule_screen_values"].drop(columns="outcome")
        return frames

    monkeypatch.setattr(run_module, "rule_frames", broken)
    with pytest.raises(Exception, match="outcome"):
        run_screener(reader, writer, config, DAY, now=T0)
    assert reader.table("results/rule_screen", DAY) is None  # the first table rolled back too


def test_a_rule_screen_runs_as_a_screen_job() -> None:
    """The nightly ``screens`` step submits each screener as a ``screen`` job."""
    reader, writer = seeded()
    store = configs()
    (nightly,) = nightly_screeners(store)
    assert nightly.config.impl == "rules"
    runner = LocalJobRunner(
        writer.runs_backend,
        LIBRARY_HANDLERS,
        {"reader": reader, "writer": writer, "configs": store},
        workers=1,
    )
    params = {"config": "big_liquid", "session": DAY.isoformat(), "export_dir": None}
    job = runner.run("screen", params, UserContext(SITE_USER), force=True)
    runner.shutdown()
    assert job.status is JobStatus.COMPLETE, job.error
    assert job.result["summary"]["passed"] == 1
    assert reader.table("results/rule_screen", DAY) is not None


IBKR = "rollups/instrument/ibkr_iv@v1"
VRP_SCREEN: dict[str, Any] = {
    "id": "vrp_like",
    "kind": "screener",
    "impl": "rules",
    "version": 1,
    "selection": "active",
    "screening": {"min_coverage": 0.5},
    "criteria": {"iv": {"field": "feature.vrp_iv30", "op": "gt", "value": 0.1}},
}


def test_an_optional_table_read_through_a_coalescing_feature_is_complete_not_partial() -> None:
    """ADR 0055: with IB Gateway down the session has no ``ibkr_iv@v1`` partition, but
    ``vrp_iv30`` coalesces it with Cboe's IV30: the run is COMPLETE, the optional miss is
    audited apart, never PARTIAL (which failed the critical nightly ``screens`` step)."""
    reader, writer = seeded()
    cboe = [
        {"instrument_id": "EQ:AAA", "iv30_cboe": 0.3},
        {"instrument_id": "EQ:BBB", "iv30_cboe": 0.05},
        {"instrument_id": "EQ:ETF1", "iv30_cboe": 0.2},
    ]
    writer.write_table("rollups/instrument/iv30@v1", DAY, "f1", stamped(cboe, DAY, "f1"))
    store = MemoryConfigStore(
        {("site", "selections", "active"): ACTIVE, ("site", "strategies", "vrp_like"): VRP_SCREEN}
    )
    config = resolve_config(store, "vrp_like", UserContext(SITE_USER))
    outcome = run_screener(reader, writer, config, DAY, now=T0)
    assert outcome.run.coverage is RunCoverage.COMPLETE
    assert outcome.audit["missing_tables"] == []
    assert outcome.audit["missing_optional_tables"] == [IBKR]
    assert outcome.audit["decisions"] == {"QUALIFIED": 2, "REJECT": 2}  # CCC: UNKNOWN
    (record,) = reader.runs("screen-vrp_like-site", DAY)
    assert record.status is RunStatus.COMPLETE


def test_a_required_table_missing_beside_an_optional_one_is_still_partial() -> None:
    reader, writer = seeded(features_stored=False)
    screen = {**SCREEN, "criteria": {**SCREEN["criteria"], **VRP_SCREEN["criteria"]}}
    store = MemoryConfigStore(
        {("site", "selections", "active"): ACTIVE, ("site", "strategies", "big_liquid"): screen}
    )
    config = resolve_config(store, "big_liquid", UserContext(SITE_USER))
    outcome = run_screener(reader, writer, config, DAY, now=T0)
    assert outcome.run.coverage is RunCoverage.PARTIAL
    assert IBKR in outcome.audit["missing_optional_tables"]
    assert IBKR not in outcome.audit["missing_tables"]
    assert "rollups/instrument/option_liquidity@v1" in outcome.audit["missing_tables"]
