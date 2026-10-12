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
from algotrade.services.drafting.contract import formulas as formulas_module
from algotrade.services.drafting.contract.formulas import (
    MAX_FORMULAS,
    UNSAMPLED,
    FormulaOutcome,
    check_formulas,
    dry_run_all,
)
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


def sampled(ctx: ReadContext, out: FormulaOutcome) -> tuple[Any, ...]:
    kept, notes = dry_run_all(ctx, out.formulas)
    assert notes == ()
    return kept


def only_reason(out: FormulaOutcome) -> str:
    assert out.formulas == () and len(out.dropped) == 1
    return out.dropped[0].reason


def test_a_good_formula_is_kept_pending_with_its_dry_run(ctx: ReadContext) -> None:
    out = check(ctx, formula())
    assert out.formulas[0].dry_run is UNSAMPLED  # checking does not run it
    (kept,) = sampled(ctx, out)
    assert out.dropped == () and out.rewritten == {} and out.notes == ()
    assert kept.pending and kept.name == "draft_near_high"
    assert kept.inputs == ("price_stats.close", "price_stats.high_52w")
    assert kept.criterion == {"field": "feature.draft_near_high", "op": "gte", "value": 0.95}
    stats = kept.dry_run
    assert stats.session == END and stats.rows > 0 and len(stats.sample) <= 5
    assert stats.criterion_pass is not None and 0 <= stats.criterion_pass <= stats.rows
    assert len(kept.fingerprint) == 12


def test_a_formula_without_a_criterion_is_kept_and_counts_nothing(ctx: ReadContext) -> None:
    (kept,) = sampled(ctx, check(ctx, formula(criterion=None)))
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
    (kept,) = sampled(ctx, check(ctx, formula(criterion=criterion)))
    assert kept.dry_run.criterion_pass is None and kept.criterion is not None


def test_a_formula_on_a_session_without_its_inputs_is_kept_unsampled(ctx: ReadContext) -> None:
    later = at_session(ctx, END + timedelta(days=1))
    (kept,) = sampled(later, check(later, formula()))
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
        unit="decimal",
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
            unit="usd",
            criterion={"op": "gt", "value": 10, "mode": None, "tolerance": None},
        ),
    )
    assert out.dropped[0].existing == "draft_mine"
    assert out.rewritten["draft_near_high"]["field"] == "feature.draft_mine"


def test_a_name_the_trader_already_has_is_not_shadowed(ctx: ReadContext) -> None:
    out = check(own(ctx), formula(name="draft_mine"))
    assert "already a feature" in only_reason(out)


def test_a_saved_formula_proposed_again_is_a_repeat_not_a_name_clash(ctx: ReadContext) -> None:
    again = formula(
        name="draft_mine",
        expr="price_stats.close * 2",
        inputs=["price_stats.close"],
        unit="usd",
        criterion={"op": "gt", "value": 10, "mode": None, "tolerance": None},
    )
    out = check(own(ctx), again)
    assert out.dropped[0].existing == "draft_mine"
    assert out.rewritten["draft_mine"]["field"] == "feature.draft_mine"  # the criterion survives


def test_a_bare_stored_column_is_that_field_not_a_formula(ctx: ReadContext) -> None:
    bare = formula(
        name="draft_close",
        expr="price_stats.close",
        inputs=["price_stats.close"],
        unit="usd_per_share",
        criterion={"op": "gt", "value": 5, "mode": None, "tolerance": None},
    )
    out = check(ctx, bare)
    assert out.formulas == () and out.dropped[0].existing == "price_stats.close"
    assert out.rewritten["draft_close"] == {
        "field": "rollup.price_stats@v2.close", "op": "gt", "value": 5,
    }  # fmt: skip
    assert out.notes == ("draft_close is price_stats.close: its criterion uses that field",)


def test_a_bare_feature_reference_is_that_feature(ctx: ReadContext) -> None:
    bare = formula(
        name="draft_again", expr="pct_from_high_52w", inputs=["pct_from_high_52w"], unit="decimal"
    )
    out = check(ctx, bare)
    assert out.dropped[0].existing == "pct_from_high_52w"
    assert out.rewritten["draft_again"]["field"] == "feature.pct_from_high_52w"


def repeat_with(unit: str) -> dict[str, Any]:
    return formula(
        name="draft_below_high",
        expr="price_stats.close / price_stats.high_52w - 1",
        unit=unit,
        criterion={"op": "gte", "value": -0.04, "mode": None, "tolerance": None},
    )


@pytest.mark.parametrize("unit", ["ratio", "pct_points", "usd"])
def test_a_repeat_in_another_unit_loses_its_criterion_with_a_note(
    ctx: ReadContext, unit: str
) -> None:
    out = check(ctx, repeat_with(unit))
    assert out.rewritten == {}
    assert f"proposed in {unit}, pct_from_high_52w is in decimal" in out.notes[-1]
    assert "draft_below_high" in check(ctx, repeat_with("decimal")).rewritten  # the same unit


def test_only_the_first_formulas_are_checked_and_the_cut_is_said(ctx: ReadContext) -> None:
    many = [formula(name=f"draft_f{n}") for n in range(10)]
    many[1]["expr"], many[1]["inputs"] = "price_stats.close * 3", ["price_stats.close"]
    many[2]["expr"], many[2]["inputs"] = "price_stats.close * 4", ["price_stats.close"]
    out = check(ctx, *many)
    assert len(out.formulas) + len(out.dropped) == MAX_FORMULAS
    assert out.notes == (f"7 formulas beyond the first {MAX_FORMULAS} were cut",)


def test_a_dry_run_that_breaks_leaves_the_formula_unsampled_with_a_note(
    ctx: ReadContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*_: object) -> None:
        raise OSError("the store went away")

    monkeypatch.setattr(formulas_module, "dry_run", broken)
    kept, notes = dry_run_all(ctx, check(ctx, formula()).formulas)
    assert kept[0].dry_run is UNSAMPLED and kept[0].pending
    assert notes == ("draft_near_high: the dry run could not be made (OSError)",)


def test_a_programming_error_in_a_dry_run_is_not_swallowed(
    ctx: ReadContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    def buggy(*_: object) -> None:
        raise TypeError("a bug")

    monkeypatch.setattr(formulas_module, "dry_run", buggy)
    with pytest.raises(TypeError):
        dry_run_all(ctx, check(ctx, formula()).formulas)
