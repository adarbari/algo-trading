"""The site VRP scanner preset (``config/site/presets/screeners/vrp_scanner/v<N>.toml``): v1
and v2 (pinned, ``extends = "vrp_scanner@N"``) and v3 (the latest) resolve and validate against
the catalogue, are not scheduled, and on a
fixed fixture of rows gives the owner-decided outcomes (docs/screeners/vrp-scanner.md): the
hard gates reject (a missing value too), liquidity misses are LIQUIDITY_RISK near misses,
IBKR IV rank only lowers the score, leveraged / inverse flag, ties by the IV-HV spread."""

from datetime import date
from typing import Any

import pytest

from algotrade.config.strategy.resolve import ResolvedConfig
from algotrade.config.user import UserContext
from algotrade.core.views.feature_view import FeatureView
from algotrade.services.configs import resolve_config, resolve_rule_draft
from algotrade.storage.configs.files import FileConfigStore
from algotrade.strategies.screeners import Decision
from algotrade.strategies.screeners.rules import evaluate_screen
from tests.conftest import REPO_ROOT

DAY = date(2026, 10, 2)
STORE = FileConfigStore(REPO_ROOT / "config")

GOOD: dict[str, Any] = {
    "feature.vrp_iv30": 0.60,
    "rollup.price_stats@v2.close": 40.0,
    "feature.vrp_iv_hv_spread": 0.20,
    "feature.vrp_iv_hv_ratio": 1.50,
    "feature.near_52w": "HIGH",
    "rollup.price_stats@v2.adv_usd_20d": 200e6,
    "feature.option_chain_volume": 20_000,
    "rollup.option_liquidity@v1.put_zone_oi": 5_000,
    "rollup.ibkr_iv@v1.iv_rank_252d_ibkr": 0.8,
    "rollup.option_liquidity@v1.put_spread_pct": 0.05,
    "feature.option_tier": "A",
    "instrument.is_leveraged": False,
    "instrument.is_inverse": False,
    "rollup.earnings@v1.next_earnings_date": date(2026, 10, 30),
}
FIXTURE: dict[str, dict[str, Any]] = {
    "EQ:STRONG": GOOD,
    # meets every gate with a small spread (0.12, ratio 1.28); wider spreads elsewhere
    # decide the tie-break among equal scores
    "EQ:BASE": {
        **GOOD,
        "feature.vrp_iv_hv_spread": 0.12,
        "feature.vrp_iv_hv_ratio": 1.28,
        "feature.near_52w": "LOW",
    },
    "EQ:NORANK": {**GOOD, "rollup.ibkr_iv@v1.iv_rank_252d_ibkr": None},  # Cboe only: no points
    "EQ:LEV": {**GOOD, "instrument.is_inverse": True, "feature.vrp_iv_hv_spread": 0.30},
    "EQ:THIN": {**GOOD, "rollup.price_stats@v2.adv_usd_20d": 45e6},  # within 20% of $50M
    "EQ:THINOI": {**GOOD, "rollup.option_liquidity@v1.put_zone_oi": 800},
    "EQ:ILLIQUID": {**GOOD, "rollup.price_stats@v2.adv_usd_20d": 10e6},  # beyond the band
    "EQ:LOWIV": {**GOOD, "feature.vrp_iv30": 0.45},  # hard: no tolerance
    "EQ:LOWRATIO": {**GOOD, "feature.vrp_iv_hv_ratio": 1.24},
    "EQ:PENNY": {**GOOD, "rollup.price_stats@v2.close": 5.0},  # price must be > $5
    "EQ:MID": {**GOOD, "feature.near_52w": "NONE"},
    "EQ:NOIV": {
        **GOOD,
        "feature.vrp_iv30": None,
    },  # neither IBKR nor Cboe: a missing HARD value is a REJECT
}
EXPECTED = {  # id: (decision, score, flags)
    "EQ:LEV": (Decision.QUALIFIED, 100.0, ("leveraged_inverse",)),
    "EQ:STRONG": (Decision.QUALIFIED, 100.0, ()),
    "EQ:BASE": (Decision.QUALIFIED, 100.0, ()),
    "EQ:NORANK": (Decision.QUALIFIED, 90.0, ()),
    "EQ:THIN": (Decision.LIQUIDITY_RISK, 95.0, ()),
    "EQ:THINOI": (Decision.LIQUIDITY_RISK, 96.0, ()),
}


@pytest.fixture(scope="module")
def preset() -> ResolvedConfig:
    """v1, pinned the way a user's copy pins it (the bare id resolves the latest version)."""
    pinned = {"id": "pinned_v1", "extends": "vrp_scanner@1"}
    return resolve_rule_draft(STORE, "pinned_v1", UserContext("tester"), pinned)


@pytest.fixture(scope="module")
def preset_v2() -> ResolvedConfig:
    pinned = {"id": "pinned_v2", "extends": "vrp_scanner@2"}
    return resolve_rule_draft(STORE, "pinned_v2", UserContext("tester"), pinned)


@pytest.fixture(scope="module")
def preset_v3() -> ResolvedConfig:
    """The bare id resolves the latest version."""
    return resolve_config(STORE, "vrp_scanner", UserContext("site"))


def test_preset_resolves_and_validates(preset: ResolvedConfig) -> None:
    spec = preset.screen_spec
    assert preset.config.impl == "rules" and preset.config.schedule is None  # on request only
    assert preset.selection is not None and preset.selection.name == "liquid_optionable"
    gates = [(c.id, c.mode.value) for c in spec.criteria]
    assert gates[:5] == [
        ("iv30", "hard"),
        ("price", "hard"),
        ("iv_hv_spread", "hard"),
        ("iv_hv_ratio", "hard"),
        ("near_52w", "hard"),
    ]
    assert {c.id: c.on_miss for c in spec.criteria if c.mode.value == "soft"} == {
        "adv": "LIQUIDITY_RISK",
        "option_volume": "LIQUIDITY_RISK",
        "target_oi": "LIQUIDITY_RISK",
    }
    assert not any("earnings" in c.field for c in spec.criteria)  # a column, never a criterion
    assert spec.tie_break == "feature.vrp_iv_hv_spread" and spec.tie_break_descending
    assert dict(spec.columns)["next_earnings"] == "rollup.earnings@v1.next_earnings_date"


def test_fixture_outcomes(preset: ResolvedConfig) -> None:
    result = evaluate_screen(preset.screen_spec, FeatureView(DAY, FIXTURE))
    rows = {r.instrument_id: r for r in result.rows}
    for iid, (decision, score, flags) in EXPECTED.items():
        row = rows[iid]
        assert (row.decision, row.flags) == (decision, flags), iid
        assert row.score == pytest.approx(score), iid
    for iid in ("EQ:ILLIQUID", "EQ:LOWIV", "EQ:LOWRATIO", "EQ:PENNY", "EQ:MID", "EQ:NOIV"):
        assert rows[iid].decision is Decision.REJECT, iid
    assert rows["EQ:NOIV"].reasons == ("no feature.vrp_iv30",) and rows["EQ:NOIV"].score == 0.0
    order = [r.instrument_id for r in result.rows][:6]
    # the 100s by IV-HV spread, then the near misses (96, 95), then no IBKR IV rank (90)
    assert order == ["EQ:LEV", "EQ:STRONG", "EQ:BASE", "EQ:THINOI", "EQ:THIN", "EQ:NORANK"]
    summary = result.summary
    assert summary.passed == 4
    assert {m.criterion_id for m in summary.narrow_misses} == {"adv", "target_oi"}


# ---------------------------------------------------------------------------------------- v2
WING = "rollup.put_wing@v1"
GOOD_V2: dict[str, Any] = {
    **{k: v for k, v in GOOD.items() if "option_liquidity" not in k},
    f"{WING}.delta_band_distance": 0.0,
    f"{WING}.best_put_oi": 3_000,
    f"{WING}.best_put_volume": 2_000,
    f"{WING}.best_put_spread_pct": 0.08,
    f"{WING}.best_put_strike": 40.0,
    f"{WING}.target_expiry": date(2026, 11, 20),
    "rollup.price_moves@v1.one_day_move": 0.04,
}
PUT_FIELDS = ("delta_band_distance", "best_put_oi", "best_put_volume", "best_put_spread_pct")
FIXTURE_V2: dict[str, dict[str, Any]] = {
    "EQ:STRONG": GOOD_V2,
    "EQ:D20": {**GOOD_V2, f"{WING}.delta_band_distance": 0.05},  # best put 20 delta
    "EQ:D25": {**GOOD_V2, f"{WING}.delta_band_distance": 0.10},  # best put 25 delta
    "EQ:THINOI": {**GOOD_V2, f"{WING}.best_put_oi": 500},
    "EQ:WIDE": {**GOOD_V2, f"{WING}.best_put_spread_pct": 0.20},
    "EQ:GAPPY": {**GOOD_V2, "rollup.price_moves@v1.one_day_move": 0.13},  # flag only
    "EQ:NOMOVE": {**GOOD_V2, "rollup.price_moves@v1.one_day_move": None},  # unknown: no flag
    "EQ:NOPUT": {**GOOD_V2, **{f"{WING}.{f}": None for f in PUT_FIELDS}},  # never filtered
}
EXPECTED_V2 = {  # id: (score, flags)
    "EQ:STRONG": (100.0, ()),
    "EQ:GAPPY": (100.0, ("large_move",)),
    "EQ:NOMOVE": (100.0, ()),
    "EQ:D20": (97.5, ()),
    "EQ:WIDE": (100 - 10 * 0.05 / 0.15, ()),
    "EQ:D25": (95.0, ()),
    "EQ:THINOI": (95.0, ()),
    "EQ:NOPUT": (60.0, ()),
}


def test_v2_resolves_with_scored_put_criteria(preset_v2: ResolvedConfig) -> None:
    spec = preset_v2.screen_spec
    assert spec.version == 2 and preset_v2.config.schedule is None  # on request, like v1
    assert preset_v2.config.name == "VRP"
    modes = {c.id: c.mode.value for c in spec.criteria}
    assert {k: v for k, v in modes.items() if v == "soft"} == {"adv": "soft"}
    put = {c.id: (c.field, c.rule.op, c.rule.value) for c in spec.criteria if WING in c.field}
    assert put == {
        "delta_closeness": (f"{WING}.delta_band_distance", "lte", 0),
        "put_open_interest": (f"{WING}.best_put_oi", "gt", 1_000),
        "put_trading_volume": (f"{WING}.best_put_volume", "gt", 1_000),
        "put_bid_ask": (f"{WING}.best_put_spread_pct", "lt", 0.15),
    }
    assert all(modes[c] == "score" for c in put)  # OI, volume, spread, delta: never gates
    assert not any("option_liquidity" in c.field for c in spec.criteria)
    assert [name for name, _ in spec.flags] == ["large_move", "leveraged_inverse"]
    columns = dict(spec.columns)
    assert {k: columns[k] for k in ("put_strike", "put_delta", "put_premium", "put_roc")} == {
        "put_strike": f"{WING}.best_put_strike",
        "put_delta": f"{WING}.best_put_delta",
        "put_premium": f"{WING}.best_put_mid",
        "put_roc": f"{WING}.best_put_roc",
    }
    assert columns["put_expiry"] == f"{WING}.target_expiry"
    # a put column never shares a name with a criterion over another field
    assert not {c for c in columns if c.startswith("put_")} & set(modes)


def test_v2_fixture_outcomes(preset_v2: ResolvedConfig) -> None:
    result = evaluate_screen(preset_v2.screen_spec, FeatureView(DAY, FIXTURE_V2))
    rows = {r.instrument_id: r for r in result.rows}
    for iid, (score, flags) in EXPECTED_V2.items():
        row = rows[iid]
        assert (row.decision, row.flags) == (Decision.QUALIFIED, flags), iid
        assert row.score == pytest.approx(score), iid
    assert rows["EQ:D20"].score > rows["EQ:D25"].score > rows["EQ:NOPUT"].score
    assert result.summary.passed == len(FIXTURE_V2)
    assert not result.summary.narrow_misses  # score criteria never make a near miss decision


# ---------------------------------------------------------------------------------------- v3
BASE_V3: dict[str, Any] = {
    **GOOD_V2,
    "instrument.security_type": "COMMON_STOCK",
    "instrument.status": "ACTIVE",
    "instrument.optionable": True,
    "feature.dist_52w": 0.04,
}
FIXTURE_V3: dict[str, dict[str, Any]] = {
    "EQ:STRONG": BASE_V3,
    "EQ:ETF": {**BASE_V3, "instrument.security_type": "ETF"},
    "EQ:LOW": {**BASE_V3, "feature.dist_52w": 0.10, "feature.near_52w": "LOW"},  # on the edge
    "EQ:NOADV": {**BASE_V3, "rollup.price_stats@v2.adv_usd_20d": None},  # SOFT: points only
    "EQ:NOTOPT": {**BASE_V3, "instrument.optionable": False},
    "EQ:DEAD": {**BASE_V3, "instrument.status": "DELISTED"},
    "EQ:PREF": {**BASE_V3, "instrument.security_type": "PREFERRED"},
    "EQ:NOTYPE": {**BASE_V3, "instrument.security_type": None},
    "EQ:MID": {**BASE_V3, "feature.dist_52w": 0.15},
    "EQ:NOIV": {**BASE_V3, "feature.vrp_iv30": None},
}


def test_v3_has_no_selection_and_opens_with_the_base_gates(preset_v3: ResolvedConfig) -> None:
    spec = preset_v3.screen_spec
    assert spec.version == 3 and preset_v3.config.schedule is None
    assert preset_v3.config.selection is None
    assert preset_v3.selection is not None and preset_v3.selection.name == "all"  # every instrument
    assert not preset_v3.selection.where.children
    gates = [(c.id, c.field, c.mode.value) for c in spec.criteria[:8]]
    assert gates == [
        ("security_type", "instrument.security_type", "hard"),
        ("status", "instrument.status", "hard"),
        ("optionable", "instrument.optionable", "hard"),
        ("iv30", "feature.vrp_iv30", "hard"),
        ("price", "rollup.price_stats@v2.close", "hard"),
        ("iv_hv_spread", "feature.vrp_iv_hv_spread", "hard"),
        ("iv_hv_ratio", "feature.vrp_iv_hv_ratio", "hard"),
        ("near_52w", "feature.dist_52w", "hard"),
    ]
    near = next(c for c in spec.criteria if c.id == "near_52w")
    assert (near.rule.op, near.rule.value) == ("lte", 0.10)
    ops = {c.id: c.rule.op for c in spec.criteria}
    assert [i for i, op in ops.items() if op == "in"] == ["security_type", "execution"]  # text only
    assert {k: dict(spec.columns)[k] for k in ("near_52w", "pct_from_high_52w")} == {
        "near_52w": "feature.near_52w",
        "pct_from_high_52w": "feature.pct_from_high_52w",
    }


def test_v3_fixture_outcomes(preset_v3: ResolvedConfig) -> None:
    result = evaluate_screen(preset_v3.screen_spec, FeatureView(DAY, FIXTURE_V3))
    rows = {r.instrument_id: r for r in result.rows}
    for iid in ("EQ:STRONG", "EQ:ETF", "EQ:LOW"):  # an ETF qualifies; 10% is inside the gate
        assert (rows[iid].decision, rows[iid].score) == (Decision.QUALIFIED, 100.0), iid
    noadv = rows["EQ:NOADV"]  # no ADV: never a pass, never a skip, points off
    assert noadv.decision is Decision.QUALIFIED and noadv.score == 90.0
    assert noadv.reasons == ("no rollup.price_stats@v2.adv_usd_20d",)
    for iid in ("EQ:NOTOPT", "EQ:DEAD", "EQ:PREF", "EQ:NOTYPE", "EQ:MID", "EQ:NOIV"):
        assert rows[iid].decision is Decision.REJECT, iid
    assert rows["EQ:NOTYPE"].reasons == ("no instrument.security_type",)
    assert rows["EQ:NOIV"].reasons == ("no feature.vrp_iv30",)
    assert result.summary.passed == 4
    assert dict(result.summary.decisions) == {"QUALIFIED": 4, "REJECT": 6}
