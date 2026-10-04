"""Rule screens are deterministic and fail closed, for any data (ADR 0029)."""

import math
from datetime import date

from hypothesis import given
from hypothesis import strategies as st

from algotrade.config.strategy.screen_spec import parse_screen_spec
from algotrade.core.views.feature_view import FeatureView
from algotrade.strategies.screeners import Decision
from algotrade.strategies.screeners.rules import Outcome, evaluate_screen

DAY = date(2026, 10, 2)
SPEC = parse_screen_spec(
    "p",
    {
        "criteria": {
            "a": {"field": "a", "op": "gt", "value": 0.0},
            "b": {"field": "b", "op": "gte", "value": 1.0, "mode": "soft", "tolerance": 0.5},
            "c": {
                "field": "c",
                "op": "lte",
                "value": 2.0,
                "mode": "soft",
                "tolerance": {"relative": 0.25},
            },
            "d": {
                "field": "d",
                "op": "between",
                "value": [0.0, 1.0],
                "mode": "score",
                "tolerance": 1.0,
            },
        },
        "tiers": {"T": {"all": [{"field": "b", "op": "gte", "value": 1.5}]}},
        "flags": {"f": {"any": [{"field": "d", "op": "gt", "value": 0.5}]}},
        "rank": {"tie_break": "d"},
    },
    "p",
)
value = st.one_of(st.none(), st.floats(-3, 4), st.sampled_from([math.nan, "x", True]))
row = st.fixed_dictionaries(dict.fromkeys("abcd", value)).map(
    lambda r: {k: v for k, v in r.items() if v is not None}
)
rows = st.dictionaries(st.from_regex(r"EQ:[A-Z]{1,3}", fullmatch=True), row, max_size=12)


@given(rows, st.randoms())
def test_same_input_same_output_whatever_the_row_order(data: dict, rnd) -> None:  # type: ignore[no-untyped-def, type-arg]
    items = list(data.items())
    rnd.shuffle(items)
    first = evaluate_screen(SPEC, FeatureView(DAY, data))
    second = evaluate_screen(SPEC, FeatureView(DAY, dict(items)))
    assert first.rows == second.rows and first.summary == second.summary
    assert sorted(r.instrument_id for r in first.rows) == sorted(data)
    assert [r.rank for r in first.rows] == list(range(1, len(data) + 1))


@given(rows)
def test_missing_gating_data_is_skipped_never_passed(data: dict) -> None:  # type: ignore[type-arg]
    for r in evaluate_screen(SPEC, FeatureView(DAY, data)).rows:
        gating_missing = any(x.gating and x.outcome is Outcome.MISSING for x in r.results)
        assert (r.decision is Decision.SKIPPED) == gating_missing
        if r.decision is Decision.SKIPPED:
            assert r.score is None and all(reason.startswith("no ") for reason in r.reasons)
        else:
            assert r.score is not None and r.score <= 100.0
        if r.decision is Decision.QUALIFIED:
            assert all(x.outcome is Outcome.PASS for x in r.results if x.gating)


@given(rows)
def test_scores_order_rows_and_full_marks_mean_every_threshold_met(data: dict) -> None:  # type: ignore[type-arg]
    result = evaluate_screen(SPEC, FeatureView(DAY, data))
    scores = [r.score for r in result.rows if r.score is not None]
    assert scores == sorted(scores, reverse=True)
    for r in result.rows:
        met = all(x.outcome is Outcome.PASS for x in r.results)
        if r.score is not None:
            assert (r.score == 100.0) == (met or all(x.penalty == 0 for x in r.results))
    narrow = {m.instrument_id for m in result.summary.narrow_misses}
    assert all(r.only_near_misses() for r in result.rows if r.instrument_id in narrow)


@given(st.floats(0.0, 0.999), st.floats(0.0, 0.999))
def test_a_bigger_miss_never_scores_higher(x: float, y: float) -> None:
    near, far = (max(x, y), min(x, y))  # b's threshold is 1.0: the lower value misses more
    view = FeatureView(DAY, {"EQ:N": {"a": 1.0, "b": near, "c": 1.0, "d": 0.5},
                             "EQ:F": {"a": 1.0, "b": far, "c": 1.0, "d": 0.5}})  # fmt: skip
    rows = {r.instrument_id: r for r in evaluate_screen(SPEC, view).rows}
    assert rows["EQ:N"].score >= rows["EQ:F"].score  # type: ignore[operator]
