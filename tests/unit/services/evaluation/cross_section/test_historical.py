"""A session before the first reference snapshot reads the listing history's names (ADR 0053
amendment 2026-10-09): a name delisted later is eligible and screened while it lived, today's
optionable flag decides a name alive today, the universe's liquidity floor a delisted one, and
the run says which path each name took."""

from datetime import date
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest

from algotrade.config.strategy.schema import parse_selection
from algotrade.config.user import UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.data import StoreReader
from algotrade.services.configs import resolve_config
from algotrade.services.evaluation.cross_section.historical import (
    IdentityTally,
    require_liquidity_rule,
)
from algotrade.services.evaluation.cross_section.picks import eligible, screen_variant
from algotrade.services.evaluation.cross_section.reporting.report import render_edge_report
from algotrade.services.evaluation.cross_section.results import historical_identity
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import reference_rows, stamped, universe_rows

SNAPSHOT = date(2026, 10, 2)
OLD = date(2012, 6, 1)  # before the first snapshot; DEAD is listed
LATE = date(2016, 6, 1)  # before the first snapshot; DEAD is gone (delisted 2015-06-30)
PRICE = "rollup.price_stats@v2.close"
ADV = "rollup.price_stats@v2.adv_usd_20d"
LIQUID = {
    "name": "liquid",
    "where": {
        "all": [
            {"field": "instrument.security_type", "op": "in", "value": ["COMMON_STOCK", "ADR"]},
            {"field": "instrument.status", "op": "eq", "value": "ACTIVE"},
            {"field": "instrument.optionable", "op": "eq", "value": True},
            {"field": PRICE, "op": "gt", "value": 5},
            {"field": ADV, "op": "gte", "value": 50_000_000},
        ]
    },
}
SCREEN = {
    "id": "momo", "kind": "screener", "impl": "rules", "version": 1, "selection": "liquid",
    "screening": {"min_coverage": 0.5},
    "criteria": {"price": {"field": PRICE, "op": "gt", "value": 0}},
    "rank": {"tie_break": PRICE, "tie_break_order": "desc"},
}  # fmt: skip
USER = UserContext("site")
ALIVE, NO_FLAG, DEAD = "EQ:ALIVE", "EQ:NOFLAG", "EQ:TIINGO:DEAD"


def _store(dead: dict[str, float] | None = None) -> tuple[StoreReader, MemoryConfigStore]:
    """ALIVE and NOFLAG are in today's reference (NOFLAG not optionable); DEAD only in the
    listing history, ended 2015-06-30. ``dead``: its close and adv on both sessions."""
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    universe = universe_rows(["ALIVE", "NOFLAG"])
    universe[1]["optionable"] = False
    writer.write_table("universe", SNAPSHOT, "u", stamped(universe, SNAPSHOT, "u"))
    ref = stamped(reference_rows(universe), SNAPSHOT, "u")
    writer.write_table("instruments/reference", SNAPSHOT, "u", ref)
    listings = pd.DataFrame(
        {
            "instrument_id": [ALIVE, NO_FLAG, DEAD],
            "ticker": ["ALIVE", "NOFLAG", "DEAD"],
            "exchange": "NASDAQ",
            "asset_type": "Stock",
            "perma_ticker": "",
            "start_date": pd.to_datetime(["2000-01-03"] * 3),
            "end_date": pd.to_datetime([None, None, "2015-06-30"]),
            "ts": pd.Timestamp("2026-10-05", tz="UTC"),
        }
    )
    writer.write_table(
        "instruments/listing_history",
        SNAPSHOT,
        "l",
        stamped(listings.to_dict("records"), SNAPSHOT, "l"),  # type: ignore[arg-type]
    )
    members = [{"index_name": "SP500", "ticker": "ZZZ", "start_date": date(2000, 1, 3),
                "end_date": None, "ts": pd.Timestamp("2026-10-05", tz="UTC")}]  # fmt: skip
    writer.write_table(
        "instruments/index_membership", SNAPSHOT, "m", stamped(members, SNAPSHOT, "m")
    )  # type: ignore[arg-type]
    figures = {"close": 50.0, "adv_usd_20d": 90e6, **(dead or {})}
    for day in (OLD, LATE):
        rows: list[dict[str, Any]] = [
            {"instrument_id": i, "close": 50.0, "adv_usd_20d": 90e6} for i in (ALIVE, NO_FLAG)
        ]
        rows.append({"instrument_id": DEAD, **figures})
        writer.write_table("rollups/instrument/price_stats@v2", day, "p", stamped(rows, day, "p"))
    configs = MemoryConfigStore(
        {("site", "selections", "liquid"): LIQUID, ("site", "strategies", "momo"): SCREEN}
    )
    return StoreReader(backend), configs


def test_a_name_delisted_in_2015_is_eligible_and_screened_in_2012_and_not_after() -> None:
    reader, configs = _store()
    universe = parse_selection(LIQUID, "liquid")
    config = resolve_config(configs, "momo", USER)
    old = eligible(reader, universe, OLD)
    assert DEAD in old.ids and not old.pre_snapshot  # the delisted name, never "pre_snapshot"
    assert DEAD in screen_variant(reader, config, OLD).qualified
    assert not screen_variant(reader, config, OLD).pre_snapshot
    assert DEAD not in eligible(reader, universe, LATE).ids  # after its end date: gone
    assert DEAD not in screen_variant(reader, config, LATE).ranking


def test_alive_name_uses_todays_optionable_flag_before_the_snapshot() -> None:
    reader, _ = _store()
    got = eligible(reader, parse_selection(LIQUID, "liquid"), OLD)
    assert ALIVE in got.ids and NO_FLAG not in got.ids  # today's flag, a disclosed lookahead
    assert got.identity == {"today_flag": 1, "proxy": 1}


def test_delisted_name_uses_the_liquidity_proxy() -> None:
    universe = parse_selection(LIQUID, "liquid")
    for thin in ({"close": 3.0}, {"adv_usd_20d": 1e6}):  # below the universe's own floors
        reader, _ = _store(thin)
        assert DEAD not in eligible(reader, universe, OLD).ids
    reader, _ = _store({"close": 6.0, "adv_usd_20d": 50e6})
    assert DEAD in eligible(reader, universe, OLD).ids
    bare = parse_selection(
        {"name": "bare", "where": {"all": [
            {"field": "instrument.optionable", "op": "eq", "value": True}]}}, "bare",
    )  # fmt: skip
    with pytest.raises(ConfigurationError, match="adv_usd_20d"):
        eligible(reader, bare, OLD)
    require_liquidity_rule(parse_selection(LIQUID, "liquid"))


def test_pre_snapshot_run_carries_the_caveat() -> None:
    reader, configs = _store()
    universe = parse_selection(LIQUID, "liquid")
    tally = IdentityTally()
    for day in (OLD, LATE):
        tally.note("eligible", day, eligible(reader, universe, day).identity)
        run = screen_variant(reader, resolve_config(configs, "momo", USER), day)
        tally.note("screened", day, run.identity)
    caveat = tally.caveat()
    assert caveat is not None and caveat.sessions == 2
    assert caveat.eligible == {"today_flag": 2, "proxy": 1}  # LATE has no delisted name
    assert caveat.screened == caveat.eligible
    stored = historical_identity(SimpleNamespace(historical=caveat))  # type: ignore[arg-type]
    assert stored is not None and "optionable" in str(stored["rule"])
    report = render_edge_report(
        {
            "edge": "e",
            "run_id": "r",
            "trials": 1,
            "survivorship": {},
            "historical_identity": stored,
            "unclosed_sessions": {},
            "rows": [],
        }
    )
    assert "HISTORICAL IDENTITY: 2 sessions" in report and "1 by the liquidity proxy" in report
    assert IdentityTally().caveat() is None
    assert historical_identity(SimpleNamespace(historical=None)) is None  # type: ignore[arg-type]
