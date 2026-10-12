"""Suggested checks (ADR 0041, amended 2026-10-11): a soft or score suggestion is kept with its
reason and source; a hard (or modeless) one, one of the wrong shape, one the criterion check
refuses or one past the cap is dropped with a reason; a repeat of a criterion of the draft or of
another suggestion is dropped quietly."""

from collections.abc import Mapping
from typing import Any

from algotrade.core.model.errors import ConfigurationError
from algotrade.services.drafting.suggestions import MAX_SUGGESTIONS, suggestions_of


def build(item: Mapping[str, Any], name: str) -> dict[str, Any]:
    if name == "nope":
        raise ConfigurationError(f"field {name!r} is not in the catalogue")
    return {"field": name, "op": item["op"], "value": item["value"], "mode": item["mode"]}


def one(**over: Any) -> dict[str, Any]:
    base = {
        "field": "feature.trend_state", "op": "ne", "value": "DOWNTREND", "mode": "score",
        "tolerance": None, "on_miss": None, "why": "a falling price", "source": "feature.div_yield",
    }  # fmt: skip
    return {**base, **over}


def got(*items: Any, held: list[dict[str, Any]] | None = None) -> Any:
    return suggestions_of({"criteria": [], "suggestions": list(items)}, build, held or [])


def test_a_soft_or_score_suggestion_is_kept_with_its_reason_and_source() -> None:
    kept, dropped = got(
        one(), one(field="feature.rsi", op="lt", value=70, mode="soft", source=None)
    )
    assert dropped == ()
    assert [(s.criterion["field"], s.criterion["mode"], s.why, s.source) for s in kept] == [
        ("feature.trend_state", "score", "a falling price", "feature.div_yield"),
        ("feature.rsi", "soft", "a falling price", None),
    ]


def test_a_hard_or_modeless_suggestion_is_refused() -> None:
    kept, dropped = got(one(mode="hard"), one(mode=None, field="feature.rsi"))
    assert kept == ()
    assert [(d.field, "never hard" in d.reason) for d in dropped] == [
        ("feature.trend_state", True),
        ("feature.rsi", True),
    ]
    assert "no mode" in dropped[1].reason


def test_a_suggestion_the_criterion_check_refuses_is_dropped_with_its_reason() -> None:
    kept, dropped = got(one(field="nope"))
    assert kept == () and dropped[0].field == "nope" and "not in the catalogue" in dropped[0].reason


def test_a_suggestion_of_the_wrong_shape_or_without_a_reason_is_dropped() -> None:
    bare = {k: v for k, v in one().items() if k != "why"}
    kept, dropped = got(bare, "text", one(why="  "))
    assert kept == ()
    assert "not the suggestion shape" in dropped[0].reason
    assert dropped[1].field == "" and "not the suggestion shape" in dropped[1].reason
    assert "needs a short reason" in dropped[2].reason


def test_a_repeat_of_a_criterion_of_the_draft_or_of_another_suggestion_is_dropped_quietly() -> None:
    held = [{"field": "feature.trend_state", "op": "ne", "value": "DOWNTREND"}]
    kept, dropped = got(one(), one(field="feature.rsi", value=[1, 2], op="in"),
                        one(field="feature.rsi", value=[1, 2], op="in"), held=held)  # fmt: skip
    assert [s.criterion["field"] for s in kept] == ["feature.rsi"] and dropped == ()


def test_a_repeat_is_dropped_before_it_is_checked_so_an_unfit_one_is_not_reported() -> None:
    held = [{"field": "feature.trend_state", "op": "ne", "value": "DOWNTREND"}]
    kept, dropped = got(one(mode="hard"), held=held)
    assert kept == () and dropped == ()


def test_at_most_five_are_offered_and_the_rest_are_said() -> None:
    items = [one(field=f"feature.f{n}", value=n) for n in range(MAX_SUGGESTIONS + 2)]
    kept, dropped = got(*items)
    assert len(kept) == MAX_SUGGESTIONS
    assert [(d.field, "over the 5 allowed" in d.reason) for d in dropped] == [
        ("feature.f5", True),
        ("feature.f6", True),
    ]


def test_no_suggestions_or_a_non_list_is_nothing() -> None:
    assert suggestions_of({"criteria": []}, build, []) == ((), ())
    assert suggestions_of({"criteria": [], "suggestions": None}, build, []) == ((), ())
    assert suggestions_of({"criteria": [], "suggestions": "x"}, build, []) == ((), ())
