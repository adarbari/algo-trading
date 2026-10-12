"""B1 formulas of a draft (ADR 0041, amended 2026-10-11): a formula is offered only when it
type-checks as the trader's own feature, reads exactly the inputs it lists, is not a repeat of a
site or own feature (a repeat is dropped and its criterion uses that field), and is dry-run on the
session. Each failure is a dropped formula with its reason; nothing is saved."""

from dataclasses import replace
from datetime import timedelta
from typing import Any

import pytest

from algotrade.config.site.features.definitions import FeatureDefinition
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.drafting.formulas import FormulaOutcome, check_formulas
from algotrade.services.read.context import ReadContext, at_session, open_context
from algotrade_sources.framework.base import FixtureSource
from tests.helpers.api_store import END, api_store

EXPR = "if(price_stats.high_52w > 0, price_stats.close / price_stats.high_52w, null)"
OPS = ("gt", "gte", "lt", "lte", "eq", "ne", "between")


@pytest.fixture(scope="module")
def ctx(golden_source: FixtureSource) -> ReadContext:
    store = api_store(golden_source)[0]
    return open_context(store.reader, store.configs, store.user)


def normalise(raw: Any, field: str) -> dict[str, Any]:
    if raw["op"] not in OPS:
        raise ConfigurationError(f"unknown op {raw['op']!r}")
    return {"field": field, "op": raw["op"], "value": raw["value"]}


def formula(**over: Any) -> dict[str, Any]:
    base = {
        "name": "draft_near_high",
        "expr": EXPR,
        "dtype": "float",
        "unit": "ratio",
        "description": "the close over the 52-week high",
        "null_meaning": "no 52-week high",
        "inputs": ["price_stats.close", "price_stats.high_52w"],
        "criterion": {"op": "gte", "value": 0.95, "mode": None, "tolerance": None},
    }
    return {**base, **over}


def check(ctx: ReadContext, *formulas: Any) -> FormulaOutcome:
    return check_formulas(ctx, {"criteria": [], "formulas": list(formulas)}, normalise)


def only_reason(out: FormulaOutcome) -> str:
    assert out.formulas == () and len(out.dropped) == 1
    return out.dropped[0].reason


def test_a_good_formula_is_kept_pending_with_its_dry_run(ctx: ReadContext) -> None:
    out = check(ctx, formula())
    (kept,) = out.formulas
    assert out.dropped == () and out.rewritten == {} and out.notes == ()
    assert kept.pending and kept.name == "draft_near_high"
    assert kept.inputs == ("price_stats.close", "price_stats.high_52w")
    assert kept.criterion == {"field": "feature.draft_near_high", "op": "gte", "value": 0.95}
    stats = kept.dry_run
    assert stats.session == END and stats.rows > 0 and len(stats.sample) <= 5
    assert stats.criterion_pass is not None and 0 <= stats.criterion_pass <= stats.rows
    assert len(kept.fingerprint) == 12


def test_a_formula_without_a_criterion_is_kept_and_counts_nothing(ctx: ReadContext) -> None:
    (kept,) = check(ctx, formula(criterion=None)).formulas
    assert kept.criterion is None and kept.dry_run.criterion_pass is None


@pytest.mark.parametrize(
    "criterion",
    [
        {"op": "between", "value": [0.9, 1.0], "mode": None, "tolerance": None},
        {"op": "gt", "value": "high", "mode": None, "tolerance": None},
        {"op": "gt", "value": True, "mode": None, "tolerance": None},
    ],
)
def test_only_a_numeric_comparison_is_counted_in_the_dry_run(
    ctx: ReadContext, criterion: dict[str, Any]
) -> None:
    (kept,) = check(ctx, formula(criterion=criterion)).formulas
    assert kept.dry_run.criterion_pass is None and kept.criterion is not None


def test_a_formula_on_a_session_without_its_inputs_is_kept_unsampled(ctx: ReadContext) -> None:
    later = at_session(ctx, END + timedelta(days=1))
    (kept,) = check(later, formula()).formulas
    assert kept.dry_run.session is None and kept.dry_run.sample == []
    assert kept.dry_run.missing


@pytest.mark.parametrize(
    ("changes", "word"),
    [
        ({"name": "near_high"}, "draft_"),
        ({"name": "draft_Bad Name"}, "draft_"),
        ({"expr": "price_stats.nope + 1"}, "nope"),
        ({"expr": "price_stats.close +"}, ""),
        ({"inputs": ["price_stats.close"]}, "inputs"),
        ({"inputs": [*formula()["inputs"], "price_stats.low_52w"]}, "inputs"),
        ({"unit": "furlongs"}, "unit"),
        ({"dtype": "complex"}, "dtype"),
        ({"criterion": {"op": "near", "value": 1, "mode": None, "tolerance": None}}, "op"),
    ],
)
def test_an_invalid_formula_is_dropped_with_its_reason(
    ctx: ReadContext, changes: dict[str, Any], word: str
) -> None:
    out = check(ctx, formula(**changes))
    assert word in only_reason(out)
    assert out.dropped[0].existing is None and out.rewritten == {}


@pytest.mark.parametrize(
    "item", [{"name": "draft_x"}, "draft_x", None, {**formula(), "inputs": "a"}]
)
def test_a_formula_of_the_wrong_shape_is_dropped(ctx: ReadContext, item: Any) -> None:
    out = check(ctx, item)
    assert "not the formula shape" in only_reason(out)


def test_a_name_used_twice_keeps_the_first(ctx: ReadContext) -> None:
    out = check(ctx, formula(), formula(expr="price_stats.close * 2", inputs=["price_stats.close"]))
    assert [f.name for f in out.formulas] == ["draft_near_high"]
    assert "another proposed formula" in out.dropped[0].reason


def test_no_formulas_or_a_non_list_is_nothing(ctx: ReadContext) -> None:
    for proposal in ({"criteria": []}, {"criteria": [], "formulas": None}, {"formulas": "x"}):
        assert check_formulas(ctx, proposal, normalise) == FormulaOutcome((), (), {}, ())


def test_a_repeat_of_a_site_feature_is_dropped_and_its_criterion_uses_the_field(
    ctx: ReadContext,
) -> None:
    repeat = formula(
        name="draft_below_high",
        expr="price_stats.close / price_stats.high_52w - 1",
        criterion={"op": "gte", "value": -0.04, "mode": None, "tolerance": None},
    )
    out = check(ctx, repeat)
    assert out.formulas == ()
    (gone,) = out.dropped
    assert gone.existing == "pct_from_high_52w" and "pct_from_high_52w" in gone.reason
    assert out.rewritten == {
        "draft_below_high": {"field": "feature.pct_from_high_52w", "op": "gte", "value": -0.04}
    }
    assert out.notes == ("draft_below_high is pct_from_high_52w: its criterion uses that field",)


def test_a_repeat_of_a_site_feature_written_differently_is_still_a_repeat(ctx: ReadContext) -> None:
    out = check(
        ctx, formula(expr="(price_stats.close / price_stats.high_52w) + -1", criterion=None)
    )
    assert out.dropped[0].existing == "pct_from_high_52w" and out.rewritten == {}


def own(ctx: ReadContext) -> ReadContext:
    mine = FeatureDefinition(
        "draft_mine", "builder", "price_stats.close * 2", "float", "usd", "x", "x", owner="local"
    )
    return replace(ctx, features=ctx.features.with_user([mine]))


def test_a_repeat_of_the_traders_own_feature_is_dropped(ctx: ReadContext) -> None:
    out = check(
        own(ctx),
        formula(
            expr="2 * price_stats.close",
            inputs=["price_stats.close"],
            criterion={"op": "gt", "value": 10, "mode": None, "tolerance": None},
        ),
    )
    assert out.dropped[0].existing == "draft_mine"
    assert out.rewritten["draft_near_high"]["field"] == "feature.draft_mine"


def test_a_name_the_trader_already_has_is_not_shadowed(ctx: ReadContext) -> None:
    out = check(own(ctx), formula(name="draft_mine"))
    assert "already a feature" in only_reason(out)
