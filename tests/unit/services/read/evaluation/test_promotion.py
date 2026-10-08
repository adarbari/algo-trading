"""``promotion_problems``: a model screener beats the rule screeners only when its frozen-slice
lift AND decile spread are strictly higher at every horizon; anything not stored fails."""

from typing import Any

from algotrade.services.read.evaluation.promotion import promotion_problems
from algotrade.services.read.evaluation.runs import EdgeRow


def row(variant: str, lift: float | None, spread: float | None, **kw: Any) -> EdgeRow:
    base: dict[str, Any] = {
        "edge_variant": "main", "variant": variant, "role": "screener", "horizon_sessions": 20,
        "slice_kind": "frozen", "slice_value": "frozen", "sessions": 6, "picks": 100, "hits": 50,
        "trials": 3, "pre_snapshot_sessions": 0, "hit_rate": 0.5, "base_rate": 0.4,
        "lift": lift, "mean_excess_picks": 0.01, "decile_spread": spread, "decile_t": 1.0,
        "effect_size": 0.1, "sharpe": 0.5, "deflated_sharpe": None, "pbo": None,
    }  # fmt: skip
    return EdgeRow(**{**base, **kw})


RULE = row("rule", 1.2, 0.010)


def test_a_model_above_the_rule_on_both_numbers_wins() -> None:
    assert promotion_problems([RULE, row("model", 1.3, 0.020)], "model", ["rule"], [20]) == []


def test_one_number_not_above_is_a_loss() -> None:
    for lift, spread in ((1.3, 0.010), (1.2, 0.020), (1.1, 0.030), (1.4, 0.005)):
        out = promotion_problems([RULE, row("model", lift, spread)], "model", ["rule"], [20])
        assert len(out) == 1 and "do not both exceed" in out[0]


def test_only_the_frozen_not_in_sample_slice_counts() -> None:
    for changes in ({"slice_kind": "all"}, {"in_sample": True}, {"exploratory": True}):
        model = row("model", 9.0, 9.0, **changes)
        assert promotion_problems([RULE, model], "model", ["rule"], [20])  # no row to judge by
    year = row("model", 9.0, 9.0, slice_kind="year")
    assert promotion_problems([RULE, year], "model", ["rule"], [20])


def test_a_missing_number_row_horizon_or_rule_is_a_failure() -> None:
    assert promotion_problems([RULE, row("model", None, 0.02)], "model", ["rule"], [20])
    assert promotion_problems([row("model", 1.3, 0.02)], "model", ["rule"], [20])  # no rule row
    assert promotion_problems([RULE, row("model", 1.3, 0.02)], "model", ["rule"], [5, 20])  # h=5
    assert promotion_problems([row("model", 1.3, 0.02)], "model", [], [20])  # nothing to beat


def test_it_must_beat_every_rule_screener() -> None:
    rows = [RULE, row("rule2", 1.5, 0.05), row("model", 1.3, 0.02)]
    (problem,) = promotion_problems(rows, "model", ["rule", "rule2"], [20])
    assert "rule2" in problem
