"""The licence of a trial and of its ledger columns (ADR 0064 decision 10): the strictest
catalogue licence of what each is derived from; a field the catalogue does not know is open."""

from dataclasses import replace

from algotrade.config.edges.portfolio import Canary
from algotrade.config.strategy.schema import parse_selection
from algotrade.config.user import UserContext
from algotrade.core.model.predicates import Group, Rule
from algotrade.services.configs import resolve_config
from algotrade.services.evaluation.cross_section.detail.licences import (
    screen_fields,
    trial_licences,
)
from algotrade.services.features import catalogue
from algotrade.storage.configs.files import MemoryConfigStore
from tests.unit.services.evaluation.cross_section.conftest import ACTIVE, PRICE, edge, screen

IBKR = "rollup.ibkr_iv@v1.iv30_ibkr"  # a personal-licence feature (ADR 0028)
VIX_PCT = "market.market_conditions@v2.vix_pct_252"  # personal: VIX-derived (ADR 0028)
OPEN_GATE = "market.market_conditions@v2.sessions_to_fomc"  # open
USER = UserContext("site")


def configs(tie_break: str) -> MemoryConfigStore:
    doc = {**screen(), "rank": {"tie_break": tie_break, "tie_break_order": "desc"}}
    return MemoryConfigStore(
        {("site", "selections", "active"): ACTIVE, ("site", "strategies", "momo"): doc}
    )


def licences(tie_break: str, iv: str | None):  # type: ignore[no-untyped-def]
    store = configs(tie_break)
    resolved = resolve_config(store, "momo", USER)
    universe = parse_selection(ACTIVE, "active")
    return trial_licences(catalogue(store, "site"), edge(), universe, [resolved], iv)


def test_an_open_trial_has_open_columns() -> None:
    found = licences(PRICE, None)
    assert (found.trial, found.value, found.score, found.adv) == ("open",) * 4


def test_a_screen_reading_a_personal_feature_makes_the_score_and_the_trial_personal() -> None:
    found = licences(IBKR, None)
    assert (found.trial, found.score, found.value) == ("personal", "personal", "open")
    assert IBKR in screen_fields(resolve_config(configs(IBKR), "momo", USER), edge())


def test_a_personal_implied_vol_makes_the_value_and_the_trial_personal() -> None:
    found = licences(PRICE, "personal")
    assert (found.trial, found.value, found.score) == ("personal", "personal", "open")


def test_a_personal_outcome_makes_the_trial_personal_and_nothing_else() -> None:
    store = configs(PRICE)
    resolved = resolve_config(store, "momo", USER)
    universe = parse_selection(ACTIVE, "active")
    found = trial_licences(
        catalogue(store, "site"), edge(), universe, [resolved], None, outcome="personal"
    )
    assert (found.trial, found.outcome) == ("personal", "personal")
    assert (found.value, found.score, found.adv) == ("open",) * 3  # the columns keep their own
    assert licences(PRICE, None).outcome == "open"


def test_an_entry_condition_over_a_personal_feature_makes_the_trial_personal() -> None:
    store = configs(PRICE)
    resolved = resolve_config(store, "momo", USER)
    universe = parse_selection(ACTIVE, "active")
    entering = edge(
        outcome={
            "kind": "excess_return", "horizon_sessions": [2], "benchmark": "SPY",
            "start_offset_sessions": 1,
            "entry": {"when": {"all": [{"field": IBKR, "op": "gt", "value": 0.2}]}},
        }
    )  # fmt: skip
    found = trial_licences(catalogue(store, "site"), entering, universe, [resolved], None)
    assert (found.trial, found.score, found.value) == ("personal", "open", "open")


def test_a_case_rule_over_a_personal_feature_makes_the_trial_personal() -> None:
    store = configs(PRICE)
    resolved = resolve_config(store, "momo", USER)
    universe = parse_selection(ACTIVE, "active")
    rule = {"all": [{"field": IBKR, "op": "gt", "value": 0.2}]}
    cased = edge(outcome={
        "kind": "option_pnl", "horizon_sessions": [2], "benchmark": "none",
        "start_offset_sessions": 1, "position": "short_put", "strike_delta": 0.25,
        "tenor_days": {"cases": [{"when": rule, "value": 45}], "default": 30},
    })  # fmt: skip
    found = trial_licences(catalogue(store, "site"), cased, universe, [resolved], None)
    assert (found.trial, found.score) == ("personal", "open")


def test_a_gate_reading_a_personal_field_makes_the_trial_personal_and_nothing_else() -> None:
    """X1 review: the setup gate's fields are read by the trial (E1), so a gate over the
    personal VIX statistics in ``market_conditions`` makes the trial personal; an open gate
    field leaves it open, and the ledger columns keep their own licences."""
    store = configs(PRICE)
    resolved = resolve_config(store, "momo", USER)
    universe = parse_selection(ACTIVE, "active")
    features = catalogue(store, "site")

    def gated(field: str):  # type: ignore[no-untyped-def]
        gate = Group("all", (Rule(field, "lt", 0.5),))
        return trial_licences(features, replace(edge(), gate=gate), universe, [resolved], None)

    found = gated(VIX_PCT)
    assert features.feature(VIX_PCT).licence == "personal"  # type: ignore[union-attr]
    assert found.trial == "personal"
    assert (found.value, found.score, found.adv, found.outcome) == ("open",) * 4
    assert gated(OPEN_GATE).trial == "open"


def test_a_book_overlay_reading_a_personal_field_makes_the_trial_personal() -> None:
    """The canary and the volatility target read a field at D (ADR 0074): a personal one makes
    the trial personal, as a gate's does."""
    store = configs(PRICE)
    resolved = resolve_config(store, "momo", USER)
    universe = parse_selection(ACTIVE, "active")
    features = catalogue(store, "site")
    base = edge()

    def with_outcome(**kw: object):  # type: ignore[no-untyped-def]
        moved = replace(base, outcome=replace(base.outcome, **kw))  # type: ignore[arg-type]
        return trial_licences(features, moved, universe, [resolved], None).trial

    canary = Canary(("SPY",), IBKR, 1, ("CASH",))
    assert with_outcome(canary=canary) == "personal"
    assert with_outcome(vol_target=0.1, vol_return_field=IBKR) == "personal"
    assert with_outcome(vol_return_field=IBKR) == "open"  # read only with a target
