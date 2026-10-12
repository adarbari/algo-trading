"""The missing features and unresolved terms of a draft (ADR 0041, amended 2026-10-11): a missing
item resolves to a backlog key (or alias) or becomes a new slug, keeps only catalogue names in
``closest`` and a known feasibility; an unresolved term keeps the alternatives whose criterion
validates, needs two, and falls back to the first when ``default_index`` is out of range."""

from typing import Any

import pytest

from algotrade.config.site.drafting.backlog import BacklogItem, FeatureBacklogSettings
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.drafting.gaps import missing_of, unresolved_of

BACKLOG = FeatureBacklogSettings(
    (
        BacklogItem("support_history", "time in the support band", "ROLLUP_FROM_STORED",
                    aliases=("support_share",)),
        BacklogItem("fcf_yield", "free cash flow over price", "NEEDS_SOURCE"),
    )
)  # fmt: skip
CATALOGUE = {"feature.dist_to_support", "feature.pct_from_high_52w", "instrument.status"}


def item(**over: Any) -> dict[str, Any]:
    base = {
        "key": "support_history",
        "new_key_slug": None,
        "span": "held within support",
        "description": "",
        "why_needed": "the sentence asks for it",
        "closest": ["dist_to_support", "feature.pct_from_high_52w", "nope"],
        "feasibility": "",
    }
    return {**base, **over}


def missing(*items: Any) -> tuple[tuple[Any, ...], tuple[str, ...]]:
    return missing_of({"criteria": [], "missing": list(items)}, BACKLOG, CATALOGUE)


def test_a_backlog_key_is_kept_with_the_backlogs_words_and_catalogue_names_only() -> None:
    (got,), notes = missing(item())
    assert (got.key, got.new_key_slug) == ("support_history", None) and notes == ()
    assert got.description == "time in the support band"
    assert got.feasibility == "ROLLUP_FROM_STORED"
    assert got.closest == ("dist_to_support", "feature.pct_from_high_52w")


def test_an_alias_is_its_item_and_the_models_own_words_win() -> None:
    (got,), _ = missing(item(key="support_share", description="mine", feasibility="UNCLEAR"))
    assert got.key == "support_history"
    assert (got.description, got.feasibility) == ("mine", "UNCLEAR")


@pytest.mark.parametrize(
    ("changes", "slug"),
    [
        ({"key": "relative_strength_rank"}, "relative_strength_rank"),
        ({"key": "Relative Strength Rank!"}, "relative_strength_rank"),
        ({"key": None, "new_key_slug": "rs_rank"}, "rs_rank"),
        ({"key": None, "new_key_slug": None}, "held_within_support"),
        (
            {"key": None, "new_key_slug": None, "span": "", "description": "Buyer count"},
            "buyer_count",
        ),
    ],
)
def test_a_key_the_backlog_does_not_know_is_a_new_slug(changes: dict[str, Any], slug: str) -> None:
    (got,), _ = missing(item(**changes))
    assert (got.key, got.new_key_slug) == (None, slug)
    assert got.feasibility == "UNCLEAR"  # nothing else said


def test_a_request_with_nothing_to_name_it_by_is_noted_not_kept() -> None:
    got, notes = missing(item(key=None, span="", description=""), {"key": 3}, "x")
    assert got == () and len(notes) == 3 and "no key" in notes[0]


def test_no_missing_or_a_non_list_is_nothing() -> None:
    for proposal in ({"criteria": []}, {"missing": None}, {"missing": "x"}):
        assert missing_of(proposal, BACKLOG, CATALOGUE) == ((), ())


def norm(raw: Any, field: str) -> dict[str, Any]:
    if field not in CATALOGUE:
        raise ConfigurationError(f"field {field!r} is not in the catalogue")
    return {"field": field, "op": raw["op"], "value": raw["value"]}


def alt(label: str, field: str = "feature.pct_from_high_52w", value: Any = 1) -> dict[str, Any]:
    crit = {"id": None, "field": field, "op": "gt", "value": value, "mode": None,
            "tolerance": None, "on_miss": None, "why": None}  # fmt: skip
    return {"label": label, "criterion": crit}


def term(*alternatives: Any, default: int = 0, **over: Any) -> dict[str, Any]:
    return {"term": "liquid", "span": "liquid", "default_index": default,
            "alternatives": list(alternatives), **over}  # fmt: skip


def unresolved(*terms: Any) -> tuple[tuple[Any, ...], tuple[str, ...]]:
    return unresolved_of({"criteria": [], "unresolved": list(terms)}, CATALOGUE, norm)


def test_each_alternative_carries_its_validated_criterion_and_the_default() -> None:
    (got,), notes = unresolved(
        term(alt("a", value=1), alt("b", value=2), alt("c", value=3), default=1)
    )
    assert notes == () and got.default_index == 1 and got.term == "liquid"
    assert [a.label for a in got.alternatives] == ["a", "b", "c"]
    assert got.alternatives[1].criterion == {
        "field": "feature.pct_from_high_52w", "op": "gt", "value": 2,
    }  # fmt: skip


def test_an_alternative_that_does_not_validate_is_dropped_and_the_default_follows_its_own() -> None:
    (got,), notes = unresolved(
        term(alt("a", "instrument.nope"), alt("b", value=2), alt("c", value=3), default=2)
    )
    assert [a.label for a in got.alternatives] == ["b", "c"] and got.default_index == 1
    assert "alternative a dropped" in notes[0]


def test_a_dropped_default_falls_back_to_the_first() -> None:
    (got,), notes = unresolved(term(alt("a", "instrument.nope"), alt("b"), alt("c"), default=0))
    assert got.default_index == 0 and got.alternatives[0].label == "b"
    assert "alternative a dropped" in notes[0] and "default alternative was dropped" in notes[1]


@pytest.mark.parametrize("default", [-1, 2, 9])
def test_a_default_out_of_range_is_the_first_and_said(default: int) -> None:
    (got,), notes = unresolved(term(alt("a"), alt("b"), default=default))
    assert got.default_index == 0 and "is out of range" in notes[0]


def test_fewer_than_two_usable_alternatives_is_not_offered() -> None:
    got, notes = unresolved(term(alt("a")), term(alt("a", "instrument.nope"), alt("b")))
    assert got == () and sum("fewer than 2" in n for n in notes) == 2


def test_an_unresolved_item_of_the_wrong_shape_is_noted() -> None:
    bad = {"term": "x", "alternatives": "a"}
    mistyped = term(alt("a"), alt("b"))
    mistyped["alternatives"][0]["criterion"] = {"field": 3}
    got, notes = unresolved(bad, "y", mistyped)
    assert len(notes) == 3 and "was not kept" in notes[0] and "criterion" in notes[2]
    assert got == ()


def test_no_unresolved_is_nothing() -> None:
    for proposal in ({"criteria": []}, {"unresolved": None}):
        assert unresolved_of(proposal, CATALOGUE, norm) == ((), ())
