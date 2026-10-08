"""A model screen (``impl = "model"``, ADR 0053 ED7b) over a fixture scorer: it ranks the names
passing its base gates by the score, a missing score never passes, and the result is the same
whatever the order the rows arrive in. No site scorer is committed: the score here is a plain
column of the view."""

from datetime import date

import pytest

from algotrade.config.strategy.schema import parse_strategy
from algotrade.config.strategy.screen_spec import parse_screen_spec, screen_spec
from algotrade.config.user import UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.views.feature_view import FeatureView
from algotrade.services.configs import resolve_rule_draft
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.strategies.screeners import Decision
from algotrade.strategies.screeners.rules import evaluate_screen

DAY = date(2026, 10, 2)
SCORE = "feature.edge_score_drift"
DOC = {
    "criteria": {"price": {"field": "px", "op": "gt", "value": 5}},
    "score": SCORE,
}
VIEW = {
    "EQ:A": {"px": 10.0, SCORE: 0.40},
    "EQ:B": {"px": 10.0, SCORE: 0.70},
    "EQ:C": {"px": 10.0},  # no score: never passes
    "EQ:D": {"px": 1.0, SCORE: 0.99},  # fails the base gate whatever its score
    "EQ:E": {"px": 10.0, SCORE: 0.55},
}


def test_a_model_screen_ranks_by_its_score_and_gates_first() -> None:
    result = evaluate_screen(parse_screen_spec("m", DOC, "m"), FeatureView(DAY, VIEW))
    by = {r.instrument_id: r for r in result.rows}
    assert [r.instrument_id for r in result.rows if r.decision is Decision.QUALIFIED] == [
        "EQ:B",
        "EQ:E",
        "EQ:A",
    ]
    assert by["EQ:B"].rank < by["EQ:E"].rank < by["EQ:A"].rank
    assert by["EQ:D"].decision is Decision.REJECT  # the gate, not the score, decides


def test_a_missing_score_never_passes() -> None:
    result = evaluate_screen(parse_screen_spec("m", DOC, "m"), FeatureView(DAY, VIEW))
    (missing,) = [r for r in result.rows if r.instrument_id == "EQ:C"]
    assert missing.decision is not Decision.QUALIFIED


def test_the_rows_do_not_depend_on_their_order() -> None:
    spec = parse_screen_spec("m", DOC, "m")
    first = evaluate_screen(spec, FeatureView(DAY, VIEW))
    second = evaluate_screen(spec, FeatureView(DAY, dict(reversed(list(VIEW.items())))))
    assert first.rows == second.rows


def test_a_model_config_resolves_to_the_same_spec() -> None:
    config = parse_strategy(
        {"id": "m", "kind": "screener", "impl": "model", **DOC, "version": 1}, "m"
    )
    spec = screen_spec(config)
    assert spec.tie_break == SCORE and spec.tie_break_descending
    assert [c.id for c in spec.criteria] == ["price", "score"]


@pytest.mark.parametrize(
    ("doc", "message"),
    [
        ({"criteria": DOC["criteria"]}, "needs score"),
        ({**DOC, "rank": {"tie_break": "px"}}, "ranks by its score alone"),
        ({"score": "feature.iv_rank"}, "edge_score_"),
        ({"score": "feature.edge_score_"}, "edge_score_"),
    ],
)
def test_a_model_screen_is_checked(doc: dict, message: str) -> None:  # type: ignore[type-arg]
    with pytest.raises(ConfigurationError, match=message):
        config = parse_strategy({"id": "m", "kind": "screener", "impl": "model", **doc}, "m")
        screen_spec(config)


def test_a_rule_screen_has_no_score() -> None:
    with pytest.raises(ConfigurationError, match="model screen"):
        parse_strategy({"id": "r", "kind": "screener", "impl": "rules", **DOC}, "r")


def test_the_not_a_rule_screen_error_names_both_impls() -> None:
    user = UserContext("u")
    other = {"kind": "strategy", "impl": "momentum"}
    with pytest.raises(ConfigurationError, match="'rules' or 'model'"):
        resolve_rule_draft(MemoryConfigStore({}), "s", user, other)
