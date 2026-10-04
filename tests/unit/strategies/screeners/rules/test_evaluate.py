"""Rule-screen evaluation: decisions incl. SKIPPED, score, rank and tie-break, flags,
columns and the run summary."""

from datetime import date
from typing import Any

import pytest

from algotrade.config.strategy.screen_spec import parse_screen_spec
from algotrade.core.model.screen_spec import ScreenSpec
from algotrade.core.views.feature_view import FeatureView
from algotrade.strategies.screeners import SCREENERS, Decision, create_screener
from algotrade.strategies.screeners.rules import RULES, Outcome, RuleScreener, evaluate_screen
from algotrade.strategies.screeners.rules.decision import decide

DAY = date(2026, 10, 2)


def spec(**extra: Any) -> ScreenSpec:
    return parse_screen_spec(
        "vrp",
        {
            "version": 2,
            "criteria": {
                "price": {"field": "px", "op": "gt", "value": 5},
                "spread": {
                    "field": "spread",
                    "op": "gte",
                    "value": 0.10,
                    "mode": "soft",
                    "tolerance": 0.02,
                },
                "adv": {
                    "field": "adv",
                    "op": "gte",
                    "value": 50.0,
                    "mode": "soft",
                    "tolerance": {"relative": 0.2},
                    "on_miss": "LIQUIDITY_RISK",
                },
                "rank": {
                    "field": "ivr",
                    "op": "gte",
                    "value": 0.5,
                    "mode": "score",
                    "tolerance": 0.5,
                },
            },
            "flags": {"leveraged": {"all": [{"field": "lev", "op": "eq", "value": True}]}},
            "columns": {"earnings": "earn"},
            "rank": {"tie_break": "spread"},
            **extra,
        },
        "vrp",
    )


GOOD = {
    "px": 10.0,
    "spread": 0.20,
    "adv": 80.0,
    "ivr": 0.9,
    "near": "HIGH",
    "lev": True,
    "earn": "2026-11-01",
}
ROWS = {
    "EQ:GOOD": GOOD,
    "EQ:GOOD2": {**GOOD, "spread": 0.12, "lev": False},
    "EQ:WATCH": {**GOOD, "spread": 0.09},
    "EQ:THIN": {**GOOD, "spread": 0.09, "adv": 45.0},
    "EQ:REJECT": {**GOOD, "px": 4.0, "spread": 0.095},
    "EQ:FAR": {**GOOD, "spread": 0.05},
    "EQ:SKIP": {k: v for k, v in GOOD.items() if k not in ("adv", "spread")},
    "EQ:NORANK": {**{k: v for k, v in GOOD.items() if k != "ivr"}, "near": 3},
}


def result() -> Any:
    return evaluate_screen(spec(), FeatureView(DAY, ROWS))


def test_decisions() -> None:
    rows = {r.instrument_id: r for r in result().rows}
    assert rows["EQ:GOOD"].decision is Decision.QUALIFIED and rows["EQ:GOOD"].score == 100.0
    assert rows["EQ:WATCH"].decision is Decision.WATCH
    assert rows["EQ:WATCH"].reasons == ("spread near miss: 0.09, needs gte 0.1 (by 0.01)",)
    assert rows["EQ:THIN"].decision is Decision.LIQUIDITY_RISK  # most severe near miss
    assert rows["EQ:REJECT"].decision is Decision.REJECT  # hard is strict
    assert rows["EQ:FAR"].decision is Decision.REJECT  # soft beyond its band fails like hard
    skip = rows["EQ:SKIP"]
    assert skip.decision is Decision.SKIPPED and skip.score is None
    assert skip.reasons == ("no spread", "no adv")
    assert rows["EQ:NORANK"].decision is Decision.QUALIFIED  # score criteria never gate
    assert rows["EQ:NORANK"].score == 90.0


def test_score_falls_with_more_and_bigger_misses() -> None:
    rows = {r.instrument_id: r for r in result().rows}
    assert rows["EQ:WATCH"].score == pytest.approx(95.0)
    assert rows["EQ:THIN"].score == pytest.approx(95.0 - 10 * 5 / 10)
    assert rows["EQ:REJECT"].score == 0.0  # 100 - 100 - 2.5 clipped at 0: only positive scores
    assert rows["EQ:FAR"].score == pytest.approx(0.0)
    assert rows["EQ:REJECT"].score <= rows["EQ:FAR"].score < rows["EQ:THIN"].score  # type: ignore[operator]
    assert all(r.score is None or 0.0 <= r.score <= 100.0 for r in rows.values())


def test_rank_ties_break_by_column_then_id() -> None:
    order = [r.instrument_id for r in result().rows]
    assert order == [
        "EQ:GOOD",
        "EQ:GOOD2",
        "EQ:WATCH",
        "EQ:NORANK",
        "EQ:THIN",
        "EQ:REJECT",  # REJECT and FAR both clip to 0: the wider spread sorts first
        "EQ:FAR",
        "EQ:SKIP",
    ]
    assert [r.rank for r in result().rows] == list(range(1, 9))
    ascending = evaluate_screen(
        spec(rank={"tie_break": "spread", "tie_break_order": "asc"}), FeatureView(DAY, ROWS)
    )
    assert [r.instrument_id for r in ascending.rows][:2] == ["EQ:GOOD2", "EQ:GOOD"]
    plain = evaluate_screen(spec(rank={}), FeatureView(DAY, ROWS))
    assert [r.instrument_id for r in plain.rows][:2] == ["EQ:GOOD", "EQ:GOOD2"]  # by id


def test_flags_columns_and_tie_break() -> None:
    rows = {r.instrument_id: r for r in result().rows}
    good, good2 = rows["EQ:GOOD"], rows["EQ:GOOD2"]
    assert good.flags == ("leveraged",) and good2.flags == ()
    assert good.columns == (("earnings", "2026-11-01"),)
    assert good.tie_break == 0.20
    assert rows["EQ:SKIP"].tie_break is None


def test_summary() -> None:
    summary = result().summary
    assert summary.rows == 8 and summary.passed == 3 and summary.skipped == 1
    assert dict(summary.decisions) == {
        "LIQUIDITY_RISK": 1,
        "QUALIFIED": 3,
        "REJECT": 2,
        "SKIPPED": 1,
        "WATCH": 1,
    }
    assert dict(summary.skipped_reasons) == {"no adv": 1, "no spread": 1}
    misses = [(m.instrument_id, m.criterion_id) for m in summary.narrow_misses]
    assert misses == [("EQ:WATCH", "spread"), ("EQ:THIN", "spread"), ("EQ:THIN", "adv")]
    watch = summary.narrow_misses[0]
    assert (watch.value, watch.threshold) == (0.09, 0.10)
    assert watch.distance == pytest.approx(0.01) and watch.normalised == pytest.approx(0.5)
    out = summary.as_dict()
    assert out["passed"] == 3 and out["narrow_misses"][0]["criterion_id"] == "spread"


def test_screener_contract_and_registry() -> None:
    screener = create_screener(RULES, spec())
    assert isinstance(screener, RuleScreener) and RULES in SCREENERS
    rows = screener.screen(FeatureView(DAY, ROWS))
    assert len(rows) == len(ROWS)
    good = next(r for r in rows if r.instrument_id == "EQ:GOOD")
    assert good.values["spread"] == 0.20 and good.score == 100.0
    assert screener.params() == {"spec": "vrp", "version": 2}
    with pytest.raises(Exception, match="needs its spec"):
        create_screener(RULES)
    with pytest.raises(Exception, match="takes no spec"):
        create_screener("short_premium_liquidity", spec())


def test_decide_without_misses_is_qualified() -> None:
    assert decide(()) == (Decision.QUALIFIED, ())
    assert Outcome.INFO.value == "INFO"


def test_a_memo_changes_nothing_and_reevaluates_only_edits() -> None:
    memo: dict[Any, Any] = {}
    view = FeatureView(DAY, ROWS)
    assert evaluate_screen(spec(), view, memo) == result()
    assert len(memo) == 5  # 4 criteria + the display part (flags, columns, tie-break)
    assert all(len(done) == len(ROWS) for done in memo.values())
    edited = spec(criteria={"price": {"field": "px", "op": "gt", "value": 9}})
    assert evaluate_screen(edited, view, memo) == evaluate_screen(edited, view)
    assert len(memo) == 6  # one new criterion; the old results stay valid for this view
    shown = spec(columns={"spread": "spread"})
    assert evaluate_screen(shown, view, memo) == evaluate_screen(shown, view)
