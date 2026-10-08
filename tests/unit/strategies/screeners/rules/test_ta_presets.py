"""The eight technical-analysis site presets (``docs/data/technical.md`` "Presets": breakout,
pullback, support reversal, exhaustion, trend continuation, range breakout, failed breakout,
oversold reversal): each resolves and validates against the catalogue, opens with the site's
base tradeability gates, and on a row built to satisfy every criterion is QUALIFIED while a
miss on a hard setup criterion (or a missing value) is a REJECT."""

from collections.abc import Callable
from datetime import date
from typing import Any

import pytest

from algotrade.config.user import UserContext
from algotrade.core.views.feature_view import FeatureView
from algotrade.services.configs import resolve_config
from algotrade.storage.configs.files import FileConfigStore
from algotrade.strategies.screeners import Decision
from algotrade.strategies.screeners.rules import evaluate_screen
from algotrade.strategies.screeners.rules.criteria import Criterion
from tests.conftest import REPO_ROOT

DAY = date(2022, 11, 23)
STORE = FileConfigStore(REPO_ROOT / "config")
PRESETS = (
    "breakout",
    "pullback",
    "support_reversal",
    "exhaustion",
    "trend_continuation",
    "range_breakout",
    "failed_breakout",
    "oversold_reversal",
)
BASE = ("security_type", "status", "price", "adv")


PASSING: dict[str, Callable[[Any], Any]] = {  # op -> a value satisfying it with room to spare
    "eq": lambda v: v,
    "ne": lambda v: "OTHER",
    "in": lambda v: v[0],
    "between": lambda v: (v[0] + v[1]) / 2,
    "gt": lambda v: v + 1,
    "gte": lambda v: v + 1,
    "lt": lambda v: v - 1,
    "lte": lambda v: v - 1,
}


def _passing(criterion: Criterion) -> Any:
    return PASSING[criterion.rule.op](criterion.rule.value)


@pytest.mark.parametrize("preset", PRESETS)
def test_preset_is_a_gated_rule_screen_with_a_setup(preset: str) -> None:
    config = resolve_config(STORE, preset, UserContext("site"))
    spec = config.screen_spec
    assert config.config.impl == "rules"
    assert (
        tuple(c.id for c in spec.criteria)[: len(BASE)] == BASE
    )  # who is screened and tradeable, first
    setup = [c for c in spec.criteria if c.id not in BASE]
    assert len(setup) >= 5 and any(c.mode.gating for c in setup)
    assert spec.columns  # the row shows the numbers behind the decision


@pytest.mark.parametrize("preset", PRESETS)
def test_a_row_meeting_every_criterion_qualifies_and_a_miss_rejects(preset: str) -> None:
    spec = resolve_config(STORE, preset, UserContext("site")).screen_spec
    good = {c.rule.field: _passing(c) for c in spec.criteria}
    hard = next(c for c in spec.criteria if c.id not in BASE and c.mode.value == "hard")
    broke = {**good, hard.rule.field: None}
    view = FeatureView(DAY, {"EQ:GOOD": good, "EQ:MISSING": broke, "EQ:EMPTY": {}})
    rows = {r.instrument_id: r for r in evaluate_screen(spec, view).rows}
    assert rows["EQ:GOOD"].decision is Decision.QUALIFIED
    assert rows["EQ:MISSING"].decision is Decision.REJECT  # missing data never passes
    assert rows["EQ:EMPTY"].decision is Decision.REJECT


def test_momentum_12_1_ranks_every_name_with_a_value_by_it_and_rejects_one_without() -> None:
    """The edge harness's momentum screen (ADR 0053): not a chart pattern, so none of the setup
    tests above; the criterion only asks for the value and the rank is the 12-1 momentum."""
    spec = resolve_config(STORE, "momentum_12_1", UserContext("site")).screen_spec
    assert tuple(c.id for c in spec.criteria)[: len(BASE)] == BASE
    assert [c.id for c in spec.criteria[len(BASE) :]] == ["mom_12_1"]
    assert spec.tie_break == "rollup.trend_stats@v2.mom_12_1" and spec.tie_break_descending
    base = {c.rule.field: _passing(c) for c in spec.criteria}
    mom = "rollup.trend_stats@v2.mom_12_1"
    view = FeatureView(
        DAY,
        {
            "EQ:LOW": {**base, mom: -0.3},
            "EQ:HIGH": {**base, mom: 0.8},
            "EQ:NONE": {k: v for k, v in base.items() if k != mom},
        },
    )
    rows = evaluate_screen(spec, view).rows
    assert [(r.instrument_id, r.decision) for r in rows] == [
        ("EQ:HIGH", Decision.QUALIFIED),
        ("EQ:LOW", Decision.QUALIFIED),
        ("EQ:NONE", Decision.REJECT),
    ]


def test_size_small_ranks_the_smallest_market_cap_first_and_rejects_one_without() -> None:
    """The edge harness's size baseline (ADR 0053, quality bar 9): stocks only, smallest first;
    a missing market cap never passes (ADR 0030)."""
    spec = resolve_config(STORE, "size_small", UserContext("site")).screen_spec
    assert tuple(c.id for c in spec.criteria)[: len(BASE)] == BASE
    assert [c.id for c in spec.criteria[len(BASE) :]] == ["market_cap"]
    assert spec.tie_break == "feature.market_cap" and not spec.tie_break_descending
    base = {c.rule.field: _passing(c) for c in spec.criteria}
    cap = "feature.market_cap"
    view = FeatureView(
        DAY,
        {
            "EQ:BIG": {**base, cap: 5e10},
            "EQ:SMALL": {**base, cap: 3e8},
            "EQ:NONE": {k: v for k, v in base.items() if k != cap},
        },
    )
    rows = evaluate_screen(spec, view).rows
    assert [(r.instrument_id, r.decision) for r in rows] == [
        ("EQ:SMALL", Decision.QUALIFIED),
        ("EQ:BIG", Decision.QUALIFIED),
        ("EQ:NONE", Decision.REJECT),
    ]


def test_vrp_iv_hv_reads_only_ibkr_iv_and_ranks_the_highest_ratio_first() -> None:
    """The VRP edge's history-evaluable screen (ADR 0053): IBKR IV30 and HV30 only, no chain
    field and no Cboe-mixed IV; a missing IBKR IV never passes (ADR 0030); ranked by IV/HV."""
    spec = resolve_config(STORE, "vrp_iv_hv", UserContext("site")).screen_spec
    fields = {c.rule.field for c in spec.criteria}
    assert "rollup.ibkr_iv@v1.iv30_ibkr" in fields  # the edge's iv_field
    assert not {f for f in fields if "put_wing" in f or "option_tier" in f or "vrp_iv30" in f}
    ratio = "feature.vrp_ibkr_iv_hv_ratio"
    assert spec.tie_break == ratio and spec.tie_break_descending
    base = {c.rule.field: _passing(c) for c in spec.criteria}
    iv = "rollup.ibkr_iv@v1.iv30_ibkr"
    view = FeatureView(
        DAY,
        {
            "EQ:LOW": {**base, ratio: 1.5},
            "EQ:HIGH": {**base, ratio: 3.0},
            "EQ:NOIV": {k: v for k, v in base.items() if k != iv},
            "EQ:GEARED": {**base, "instrument.is_leveraged": True},
        },
    )
    rows = evaluate_screen(spec, view).rows
    assert [(r.instrument_id, r.decision) for r in rows[:2]] == [
        ("EQ:HIGH", Decision.QUALIFIED),
        ("EQ:LOW", Decision.QUALIFIED),
    ]
    assert {r.instrument_id: r.decision for r in rows[2:]} == {
        "EQ:NOIV": Decision.REJECT,
        "EQ:GEARED": Decision.REJECT,
    }


def test_pead_small_cap_needs_a_reaction_of_five_percent_and_ranks_the_largest_first() -> None:
    """The small-cap drift screen (ADR 0053, ED4b): Nasdaq common stock under $2B, liquid before
    the report, a complete reaction window of at least +5% over SPY; a missing value never
    passes (ADR 0030); ranked by the reaction, largest first."""
    spec = resolve_config(STORE, "pead_small_cap", UserContext("site")).screen_spec
    ids = [c.id for c in spec.criteria]
    assert ids == [
        "security_type", "status", "exchange", "market_cap", "price", "pre_event_adv",
        "reaction_status", "reaction",
    ]  # fmt: skip
    reaction = "rollup.earnings_reaction@v1.reaction_excess_return"
    assert spec.tie_break == reaction and spec.tie_break_descending
    base = {c.rule.field: _passing(c) for c in spec.criteria}
    assert base["feature.market_cap"] < 2e9 and base[reaction] >= 0.05
    adv = "rollup.earnings_reaction@v1.pre_event_adv_usd_20d"
    status = "rollup.earnings_reaction@v1.reaction_status"
    view = FeatureView(
        DAY,
        {
            "EQ:SMALL": {**base, reaction: 0.08},
            "EQ:BIG": {**base, reaction: 0.30},
            "EQ:FLAT": {**base, reaction: 0.04},
            "EQ:THIN": {**base, adv: 1e6},
            "EQ:CAP": {**base, "feature.market_cap": 3e9},
            "EQ:INCOMPLETE": {**base, status: "INCOMPLETE"},
            "EQ:NONE": {k: v for k, v in base.items() if k != reaction},
        },
    )
    rows = evaluate_screen(spec, view).rows
    decisions = {r.instrument_id: r.decision for r in rows}
    assert [r.instrument_id for r in rows if r.decision is Decision.QUALIFIED] == [
        "EQ:BIG",
        "EQ:SMALL",
    ]
    assert all(
        decisions[i] is Decision.REJECT
        for i in ("EQ:FLAT", "EQ:THIN", "EQ:CAP", "EQ:INCOMPLETE", "EQ:NONE")
    )


def test_eap_presets_take_an_expected_date_never_unknown_and_eap_volume_ranks_by_volume() -> None:
    """The earnings announcement premium screens (ADR 0053, ED4c): liquid common stock or ADR
    with a SCHEDULED or PRIOR_YEAR expected report (UNKNOWN never passes); eap_volume also needs
    the earnings volume ratio and ranks by it, largest first."""
    basis = "rollup.earnings_expected@v1.expected_basis"
    ratio = "rollup.earnings_reaction@v1.earnings_volume_ratio"
    for preset, signal in (("eap_all", None), ("eap_volume", ratio)):
        spec = resolve_config(STORE, preset, UserContext("site")).screen_spec
        assert tuple(c.id for c in spec.criteria)[:4] == BASE
        base = {c.rule.field: _passing(c) for c in spec.criteria}
        view = FeatureView(
            DAY,
            {
                "EQ:SCHED": {**base, basis: "SCHEDULED", **({ratio: 3.0} if signal else {})},
                "EQ:LOW": {**base, basis: "SCHEDULED", **({ratio: 1.5} if signal else {})},
                "EQ:PRIOR": {**base, basis: "PRIOR_YEAR", **({ratio: 5.0} if signal else {})},
                "EQ:UNKNOWN": {**base, basis: "UNKNOWN"},
                "EQ:THIN": {**base, "rollup.price_stats@v2.adv_usd_20d": 1e6},
                "EQ:NORATIO": {k: v for k, v in base.items() if k != ratio},
            },
        )
        rows = evaluate_screen(spec, view).rows
        decisions = {r.instrument_id: r.decision for r in rows}
        assert decisions["EQ:UNKNOWN"] is Decision.REJECT
        assert decisions["EQ:THIN"] is Decision.REJECT
        qualified = [r.instrument_id for r in rows if r.decision is Decision.QUALIFIED]
        if signal:
            assert decisions["EQ:NORATIO"] is Decision.REJECT
            assert decisions["EQ:LOW"] is Decision.REJECT  # under the cut of 2
            assert qualified == ["EQ:PRIOR", "EQ:SCHED"]  # the larger ratio first
            assert spec.tie_break == ratio and spec.tie_break_descending
        else:
            assert set(qualified) >= {"EQ:SCHED", "EQ:PRIOR"}
