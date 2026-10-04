"""The site VRP scanner preset (``config/site/presets/screeners/vrp_scanner/v<N>.toml``): v1
(pinned, ``extends = "vrp_scanner@1"``) and v2 (the latest) resolve and validate against the
catalogue, are not scheduled, and on a
fixed fixture of rows gives the owner-decided outcomes (docs/screeners/vrp-scanner.md): the
hard gates reject or skip, liquidity misses are LIQUIDITY_RISK near misses, IBKR IV rank
only lowers the score, STRONG tier, leveraged / inverse flag, classify by near_52w, ties by
the IV-HV spread."""

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
    # meets every gate but below the STRONG tier (spread 0.12, ratio 1.28); wider-than-STRONG
    # spreads elsewhere decide the tie-break among equal scores
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
    "EQ:NOIV": {**GOOD, "feature.vrp_iv30": None},  # neither IBKR nor Cboe: SKIPPED
}
EXPECTED = {  # id: (decision, score, tier, class, flags)
    "EQ:LEV": (Decision.QUALIFIED, 100.0, "STRONG", "HIGH", ("leveraged_inverse",)),
    "EQ:STRONG": (Decision.QUALIFIED, 100.0, "STRONG", "HIGH", ()),
    "EQ:BASE": (Decision.QUALIFIED, 100.0, None, "LOW", ()),
    "EQ:NORANK": (Decision.QUALIFIED, 90.0, "STRONG", "HIGH", ()),
    "EQ:THIN": (Decision.LIQUIDITY_RISK, 95.0, "STRONG", "HIGH", ()),
    "EQ:THINOI": (Decision.LIQUIDITY_RISK, 96.0, "STRONG", "HIGH", ()),
}


@pytest.fixture(scope="module")
def preset() -> ResolvedConfig:
    """v1, pinned the way a user's copy pins it (the bare id resolves the latest version)."""
    pinned = {"id": "pinned_v1", "extends": "vrp_scanner@1"}
    return resolve_rule_draft(STORE, "pinned_v1", UserContext("tester"), pinned)


@pytest.fixture(scope="module")
def preset_v2() -> ResolvedConfig:
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
    assert spec.classify == "feature.near_52w"
    assert spec.tie_break == "feature.vrp_iv_hv_spread" and spec.tie_break_descending
    assert dict(spec.columns)["next_earnings"] == "rollup.earnings@v1.next_earnings_date"


def test_fixture_outcomes(preset: ResolvedConfig) -> None:
    result = evaluate_screen(preset.screen_spec, FeatureView(DAY, FIXTURE))
    rows = {r.instrument_id: r for r in result.rows}
    for iid, (decision, score, tier, klass, flags) in EXPECTED.items():
        row = rows[iid]
        assert (row.decision, row.tier, row.klass, row.flags) == (decision, tier, klass, flags), iid
        assert row.score == pytest.approx(score), iid
    for iid in ("EQ:ILLIQUID", "EQ:LOWIV", "EQ:LOWRATIO", "EQ:PENNY", "EQ:MID"):
        assert rows[iid].decision is Decision.REJECT, iid
    assert rows["EQ:NOIV"].decision is Decision.SKIPPED
    assert rows["EQ:NOIV"].reasons == ("no feature.vrp_iv30",)
    order = [r.instrument_id for r in result.rows][:6]
    # the 100s by IV-HV spread, then the near misses (96, 95), then no IBKR IV rank (90)
    assert order == ["EQ:LEV", "EQ:STRONG", "EQ:BASE", "EQ:THINOI", "EQ:THIN", "EQ:NORANK"]
    summary = result.summary
    assert summary.passed == 4 and dict(summary.skipped_reasons) == {"no feature.vrp_iv30": 1}
    assert {m.criterion_id for m in summary.narrow_misses} == {"adv", "target_oi"}


# ---------------------------------------------------------------------------------------- v2
WING = "rollup.put_wing@v1"
GOOD_V2: dict[str, Any] = {
    **{k: v for k, v in GOOD.items() if "option_liquidity" not in k},
    f"{WING}.wing_oi": 3_000,
    f"{WING}.wing_volume": 2_000,
    f"{WING}.wing_spread_pct": 0.08,
    "rollup.price_moves@v1.one_day_move": 0.04,
}
FIXTURE_V2: dict[str, dict[str, Any]] = {
    "EQ:STRONG": GOOD_V2,
    "EQ:GAPPY": {**GOOD_V2, "rollup.price_moves@v1.one_day_move": 0.13},  # flag only
    "EQ:NOMOVE": {**GOOD_V2, "rollup.price_moves@v1.one_day_move": None},  # flag unknown: none
    "EQ:THINOI": {**GOOD_V2, f"{WING}.wing_oi": 800},  # within 50% of 1,000
    "EQ:THINVOL": {**GOOD_V2, f"{WING}.wing_volume": 600},
    "EQ:WIDE": {**GOOD_V2, f"{WING}.wing_spread_pct": 0.18},  # 15-20%: near miss
    "EQ:EDGEOI": {**GOOD_V2, f"{WING}.wing_oi": 1_000},  # "> 1,000": exactly 1,000 misses
    "EQ:VERYWIDE": {**GOOD_V2, f"{WING}.wing_spread_pct": 0.30},  # beyond the band
    "EQ:NOWING": {  # no 8-15 delta strike: missing -> SKIPPED, never a pass
        **GOOD_V2,
        f"{WING}.wing_oi": None,
        f"{WING}.wing_volume": None,
        f"{WING}.wing_spread_pct": None,
    },
}


def test_v2_resolves_with_put_wing_liquidity(preset_v2: ResolvedConfig) -> None:
    spec = preset_v2.screen_spec
    assert spec.version == 2 and preset_v2.config.schedule is None  # on request, like v1
    soft = {
        c.id: (c.field, c.rule.op, c.rule.value, c.on_miss)
        for c in spec.criteria
        if c.mode.value == "soft"
    }
    assert soft == {
        "adv": ("rollup.price_stats@v2.adv_usd_20d", "gte", 50_000_000, "LIQUIDITY_RISK"),
        "wing_oi": (f"{WING}.wing_oi", "gt", 1_000, "LIQUIDITY_RISK"),
        "wing_volume": (f"{WING}.wing_volume", "gt", 1_000, "LIQUIDITY_RISK"),
        "wing_spread": (f"{WING}.wing_spread_pct", "lt", 0.15, "LIQUIDITY_RISK"),
    }
    assert not any("option_liquidity" in c.field for c in spec.criteria)
    assert [name for name, _ in spec.flags] == ["large_move", "leveraged_inverse"]
    columns = dict(spec.columns)
    assert columns["best_put_strike"] == f"{WING}.best_put_strike"
    assert columns["best_put_delta"] == f"{WING}.best_put_delta"
    assert columns["best_put_premium"] == f"{WING}.best_put_mid"
    assert columns["best_put_roc"] == f"{WING}.best_put_roc"


def test_v2_fixture_outcomes(preset_v2: ResolvedConfig) -> None:
    result = evaluate_screen(preset_v2.screen_spec, FeatureView(DAY, FIXTURE_V2))
    rows = {r.instrument_id: r for r in result.rows}
    assert rows["EQ:STRONG"].decision is Decision.QUALIFIED and rows["EQ:STRONG"].flags == ()
    assert rows["EQ:GAPPY"].decision is Decision.QUALIFIED
    assert rows["EQ:GAPPY"].flags == ("large_move",)
    assert rows["EQ:NOMOVE"].decision is Decision.QUALIFIED and rows["EQ:NOMOVE"].flags == ()
    for iid in ("EQ:THINOI", "EQ:THINVOL", "EQ:WIDE", "EQ:EDGEOI"):
        assert rows[iid].decision is Decision.LIQUIDITY_RISK, iid
    assert rows["EQ:VERYWIDE"].decision is Decision.REJECT
    assert rows["EQ:NOWING"].decision is Decision.SKIPPED
    assert rows["EQ:NOWING"].reasons[0] == f"no {WING}.wing_oi"
    misses = {m.instrument_id: m.criterion_id for m in result.summary.narrow_misses}
    assert misses == {
        "EQ:THINOI": "wing_oi",
        "EQ:THINVOL": "wing_volume",
        "EQ:WIDE": "wing_spread",
        "EQ:EDGEOI": "wing_oi",
    }
