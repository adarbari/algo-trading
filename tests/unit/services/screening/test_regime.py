"""The regime gate in screen runs (ADR 0049): the session's label read from the market feature
store, PAUSED picks with their reason, coverage unchanged, and every result row carrying the
session's ``regime`` and ``size_multiplier``."""

from typing import Any

import pandas as pd

from algotrade.config.user import SITE_USER, UserContext
from algotrade.data import StoreReader
from algotrade.engines.screening.runner import RunCoverage
from algotrade.services.configs import resolve_config
from algotrade.services.screening.regime import MARKET, session_market
from algotrade.services.screening.run import ScreenOutcome, run_screener
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import T0, stamped
from tests.unit.services.screening import test_screening_service as legacy
from tests.unit.services.screening.test_rule_screens import DAY, configs, seeded

LABEL = "market.regime@v1.label"
REGIME = "rollups/market/regime@v1"
ON = {"enabled": True, "pause_in": ["STRESS", "CRISIS"]}


def store_label(writer: StoreWriter, label: str | None) -> None:
    row = {"instrument_id": MARKET, "label": label, "market_stress": 70.0}
    writer.write_table(REGIME, DAY, "m1", stamped([row], DAY, "m1"))


def screen(
    label: str | None, regime: dict[str, Any] | None, store: bool = True
) -> tuple[ScreenOutcome, StoreReader]:
    reader, writer = seeded()
    if store:
        store_label(writer, label)
    extra = {"regime": regime} if regime is not None else {}
    config = resolve_config(configs(**extra), "big_liquid", UserContext(SITE_USER))
    return run_screener(reader, writer, config, DAY, now=T0), reader


def rows(reader: StoreReader) -> pd.DataFrame:
    frame = reader.table("results/rule_screen", DAY)
    assert frame is not None
    return frame.set_index("instrument_id")


def test_the_session_market_values_are_read_for_exactly_that_session() -> None:
    reader, writer = seeded()
    assert session_market(reader, [LABEL], DAY) == {LABEL: None}  # nothing stored: unknown
    store_label(writer, "CAUTION")
    assert session_market(reader, [LABEL, "market.regime@v1.market_stress"], DAY) == {
        LABEL: "CAUTION",
        "market.regime@v1.market_stress": 70.0,
    }
    assert session_market(reader, [], DAY) == {}


def test_a_storm_pauses_the_picks_of_a_screener_that_pauses_in_it() -> None:
    outcome, reader = screen("STRESS", ON)
    assert outcome.run.coverage is RunCoverage.COMPLETE  # PAUSED is processed
    assert outcome.audit["decisions"] == {"PAUSED": 2, "REJECT": 2}
    assert outcome.audit["summary"]["passed"] == 0
    assert outcome.audit["regime"] == {
        "label": "STRESS",
        "size_multiplier": 0.0,
        "paused_reason": "regime=STRESS: big_liquid pauses in STRESS",
    }
    saved = rows(reader)
    assert saved.loc["EQ:AAA", "decision"] == "PAUSED"
    assert saved.loc["EQ:AAA", "reasons"].startswith("regime=STRESS: big_liquid pauses in STRESS")
    assert saved.loc["EQ:AAA", "rank"] == 1  # ranks are kept: the row is never dropped
    assert set(saved["regime"]) == {"STRESS"} and set(saved["size_multiplier"]) == {0.0}


def test_an_unknown_regime_fails_closed() -> None:
    for label, stored in ((None, True), ("STRESS", False)):
        outcome, reader = screen(label, {"enabled": True, "pause_in": ["CRISIS"]}, store=stored)
        assert outcome.audit["decisions"] == {"PAUSED": 2, "REJECT": 2}
        saved = rows(reader)
        assert saved.loc["EQ:BBB", "reasons"].startswith("regime unknown")
        assert saved["regime"].isna().all() and set(saved["size_multiplier"]) == {0.0}


def test_an_unknown_regime_does_not_pause_an_ungated_screener() -> None:
    outcome, reader = screen(None, {"enabled": True})  # pause_in is empty
    assert outcome.audit["decisions"] == {"QUALIFIED": 1, "WATCH": 1, "REJECT": 2}
    assert outcome.audit["regime"]["paused_reason"] is None
    saved = rows(reader)
    assert saved["regime"].isna().all() and set(saved["size_multiplier"]) == {0.0}


def test_a_regime_the_screener_does_not_pause_in_only_sizes() -> None:
    outcome, reader = screen("CAUTION", ON)
    assert outcome.audit["decisions"] == {"QUALIFIED": 1, "WATCH": 1, "REJECT": 2}
    saved = rows(reader)
    assert set(saved["regime"]) == {"CAUTION"} and set(saved["size_multiplier"]) == {0.75}


def test_the_gate_is_off_by_default() -> None:
    outcome, reader = screen("CRISIS", None)
    assert outcome.audit["decisions"] == {"QUALIFIED": 1, "WATCH": 1, "REJECT": 2}
    assert "regime" not in outcome.audit
    saved = rows(reader)
    assert saved["regime"].isna().all() and set(saved["size_multiplier"]) == {1.0}


def test_a_coded_screener_is_gated_by_the_engine_too() -> None:
    reader, writer = legacy.seeded()
    regime = {"enabled": True, "pause_in": ["CRISIS"]}
    config = legacy.preset(screening={"min_coverage": 0.7}, regime=regime)
    outcome = run_screener(reader, writer, config, DAY, now=T0)  # no regime row: unknown
    assert outcome.run.coverage is RunCoverage.COMPLETE
    assert outcome.audit["decisions"] == {
        "PAUSED": 1,
        "LIQUIDITY_RISK": 1,
        "UNKNOWN": 1,
        "REJECT": 1,
    }
    saved = reader.table("results/short_premium_liquidity", DAY)
    assert saved is not None
    paused = saved[saved["decision"] == "PAUSED"].iloc[0]
    assert paused["reasons"].startswith("regime unknown")
    assert saved["regime"].isna().all() and set(saved["size_multiplier"]) == {0.0}
