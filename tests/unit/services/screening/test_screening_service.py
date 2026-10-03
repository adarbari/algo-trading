import csv
from datetime import date, timedelta
from pathlib import Path

import pytest

from algotrade.config.strategy.resolve import ResolvedConfig
from algotrade.config.user import SITE_USER, UserContext
from algotrade.core.model.errors import ConfigurationError, MissingDataError
from algotrade.data import StoreReader
from algotrade.data.reference import load_universe
from algotrade.engines.screening.runner import RunCoverage
from algotrade.services.configs import resolve_config
from algotrade.services.screening.exports import LEGACY_COLUMNS, write_legacy_exports
from algotrade.services.screening.run import run_screener
from algotrade.services.views import to_value
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import FileConfigStore
from algotrade.storage.runs import RunStatus
from algotrade.storage.tables.writers import StoreWriter
from tests.conftest import REPO_ROOT
from tests.helpers.stored_frames import T0, reference_rows, stamped, universe_rows

SITE_CONFIGS = FileConfigStore(REPO_ROOT / "config")


def preset(**overrides: object) -> ResolvedConfig:
    """The real site preset, with run-time overrides (e.g. a lower coverage threshold)."""
    return resolve_config(
        SITE_CONFIGS, "short_premium_liquidity", UserContext(SITE_USER), overrides or None
    )


DAY = date(2026, 10, 2)
FEATURE = "rollups/instrument/option_liquidity@v1"


def seeded(last_verified: str = "2026-10-01") -> tuple[StoreReader, StoreWriter]:
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    universe = universe_rows(["AAA", "BBB", "CCC"], last_verified=last_verified)
    universe += universe_rows(["ETF1"], security_type="ETF", asset_class="ETF")
    universe += universe_rows(["DEAD"], status="DELISTED") + universe_rows(
        ["WRNT"], security_type="WARRANT"
    )
    snapshot = DAY - timedelta(days=2)
    writer.write_table("universe", snapshot, "u1", stamped(universe, DAY, "u1"))
    writer.write_table(
        "instruments/reference", snapshot, "u1", stamped(reference_rows(universe), DAY, "u1")
    )
    features = [
        {
            "instrument_id": "EQ:AAA",
            "liq_status": "OK",
            "put_tier": "A",
            "call_tier": "B",
            "short_put_ok": True,
            "short_call_ok": True,
            "put_spread_pct": 0.0247,
            "put_spread_abs": 0.2,
            "put_strike": 95.0,
            "put_strike_oi": 3852.0,
            "put_zone_oi": 44445.0,
            "chain_oi": 4985059.0,
            "target_expiry": date(2026, 11, 20),
            "target_dte": 49.0,
            "underlying_price": 100.0,
        },
        {
            "instrument_id": "EQ:BBB",
            "liq_status": "OK",
            "put_tier": "D",
            "call_tier": "D",
            "short_put_ok": False,
            "short_call_ok": False,
        },
        {"instrument_id": "EQ:ETF1", "liq_status": "NO_CHAIN", "put_tier": "D", "call_tier": "D"},
    ]
    writer.write_table(FEATURE, DAY, "f1", stamped(features, DAY, "f1"))
    return StoreReader(backend), writer


def test_universe_keeps_every_row() -> None:
    reader, _ = seeded()
    universe = load_universe(reader, DAY)
    assert len(universe.instruments) == universe.rows_loaded == 6
    assert universe.last_verified == date(2026, 10, 1)


def test_site_preset_reproduces_the_old_production_filter() -> None:
    reader, writer = seeded()
    outcome = run_screener(reader, writer, preset(), DAY, now=T0)
    selection = outcome.audit["selection"]
    assert [r.instrument_id for r in outcome.run.rows] == ["EQ:AAA", "EQ:BBB", "EQ:CCC", "EQ:ETF1"]
    assert selection["base"] == 6
    assert [r["remaining"] for r in selection["rules"]] == [5, 4, 4]  # type, status, optionable


def test_run_screener_saves_audited_result() -> None:
    reader, writer = seeded()
    outcome = run_screener(reader, writer, preset(screening={"min_coverage": 0.7}), DAY, now=T0)
    assert outcome.run.coverage is RunCoverage.COMPLETE
    assert outcome.audit["decisions"] == {
        "QUALIFIED": 1,
        "LIQUIDITY_RISK": 1,
        "UNKNOWN": 1,
        "REJECT": 1,
    }
    assert outcome.audit["universe_version"] == "v1"
    saved = reader.table("results/short_premium_liquidity", DAY)
    assert saved is not None
    assert set(saved["decision"]) == {"QUALIFIED", "LIQUIDITY_RISK", "UNKNOWN", "REJECT"}
    (record,) = reader.runs("screen-short_premium_liquidity-site", DAY)
    assert record.status is RunStatus.COMPLETE


def test_partial_and_stale_universe() -> None:
    reader, writer = seeded()
    partial = run_screener(reader, writer, preset(), DAY, now=T0)
    assert partial.run.coverage is RunCoverage.PARTIAL  # 3/4 processed < 98%
    stale_reader, stale_writer = seeded(last_verified="2026-06-01")
    stale = run_screener(
        stale_reader, stale_writer, preset(screening={"min_coverage": 0.5}), DAY, now=T0
    )
    assert stale.run.coverage is RunCoverage.UNIVERSE_INCOMPLETE


def test_missing_inputs_raise_with_hint() -> None:
    reader, writer = StoreReader(MemoryBackend()), StoreWriter(MemoryBackend())
    with pytest.raises(MissingDataError, match="universe import"):
        run_screener(reader, writer, preset(), DAY)
    seeded_reader, seeded_writer = seeded()
    with pytest.raises(MissingDataError, match="ingest rollups"):
        run_screener(seeded_reader, seeded_writer, preset(), DAY + timedelta(days=1))


def test_legacy_exports_match_original_layout(tmp_path: Path) -> None:
    reader, writer = seeded()
    outcome = run_screener(reader, writer, preset(screening={"min_coverage": 0.5}), DAY, now=T0)
    full, candidates = write_legacy_exports(outcome, tmp_path, "2026-10")
    with full.open() as fh:
        rows = list(csv.DictReader(fh))
    assert tuple(rows[0]) == LEGACY_COLUMNS
    assert [r["ticker"] for r in rows] == ["AAA", "BBB", "CCC", "ETF1"]  # stocks first
    aaa = rows[0]
    assert (aaa["process_further"], aaa["short_put_ok"], aaa["put_tier"]) == ("TRUE", "TRUE", "A")
    assert (aaa["put_spread_pct_of_mid"], aaa["put_strike_oi"], aaa["target_dte"]) == (
        "2.47",
        "3852",
        "49",
    )
    assert aaa["target_expiry"] == "2026-11-20"
    assert rows[2]["liq_status"] == "NOT_SCREENED"
    with candidates.open() as fh:
        assert [r["ticker"] for r in csv.DictReader(fh)] == ["AAA"]


def test_to_value() -> None:
    import numpy as np  # noqa: PLC0415

    assert to_value(np.int64(3)) == 3
    assert to_value(float("nan")) is None
    assert to_value(date(2026, 1, 2)) == "2026-01-02"
    assert to_value([1]) == "[1]"


def test_results_carry_user_and_config_hash() -> None:
    reader, writer = seeded()
    config = preset(screening={"min_coverage": 0.5})
    run_screener(reader, writer, config, DAY, now=T0)
    saved = reader.table("results/short_premium_liquidity", DAY)
    assert saved is not None
    assert set(saved["user_id"]) == {"site"}
    assert set(saved["config_hash"]) == {config.hash}
    (record,) = reader.runs("screen-short_premium_liquidity-site", DAY)
    assert record.stats["config_hash"] == config.hash


def test_empty_selection_is_reported() -> None:
    reader, writer = seeded()
    narrowed = preset(
        selection_overrides={"all": [{"field": "instrument.symbol", "op": "eq", "value": "ZZZ"}]}
    )
    outcome = run_screener(reader, writer, narrowed, DAY, now=T0)
    assert outcome.run.coverage is RunCoverage.EMPTY_SELECTION
    assert outcome.run.rows == ()


def test_wrong_kind_or_missing_selection_is_rejected() -> None:
    reader, writer = seeded()
    strategy = resolve_config(SITE_CONFIGS, "sma_trend", UserContext(SITE_USER))
    with pytest.raises(ConfigurationError, match="not a screener"):
        run_screener(reader, writer, strategy, DAY)
    no_selection = ResolvedConfig(
        preset().config.__class__(id="x", kind="screener", impl="short_premium_liquidity"),
        None,
        preset().settings,
        UserContext(),
    )
    with pytest.raises(ConfigurationError, match="needs a selection"):
        run_screener(reader, writer, no_selection, DAY)
