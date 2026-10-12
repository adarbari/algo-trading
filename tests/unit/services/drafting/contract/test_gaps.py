"""The missing features and unresolved terms of a draft (ADR 0041, amended 2026-10-11): a missing
item resolves to a backlog key (or alias) or becomes a new slug, keeps only catalogue names in
``closest`` and a known feasibility; an unresolved term keeps the alternatives whose criterion
validates, needs two, and falls back to the first when ``default_index`` is out of range."""

from typing import Any

import pytest

from algotrade.config.site.drafting.backlog import BacklogItem, FeatureBacklogSettings
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.drafting.contract.gaps import missing_of, unresolved_of

BACKLOG = FeatureBacklogSettings(
    (
        BacklogItem("support_history", "time in the support band", "ROLLUP_FROM_STORED",
                    aliases=("support_share",)),
        BacklogItem("fcf_yield", "free cash flow over price", "NEEDS_SOURCE"),
        BacklogItem("built_one", "built", "NEEDS_SOURCE", status="PROMOTED", promoted_to="x"),
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
        (
            {"key": None, "new_key_slug": None, "description": "Time in the band"},
            "time_in_the_band",
        ),
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


def test_the_traders_words_never_become_a_slug() -> None:
    got, notes = missing(
        item(key=None, new_key_slug=None, span="held within support", description="")
    )
    assert got == () and "no key, slug or description" in notes[0]
    (kept,), _ = missing(
        item(key=None, new_key_slug=None, span="my words", description="Band time")
    )
    assert kept.new_key_slug == "band_time"


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
    assert [a.text for a in got.alternatives] == ["a", "b", "c"]
    assert got.alternatives[1].criterion == {
        "field": "feature.pct_from_high_52w", "op": "gt", "value": 2,
    }  # fmt: skip


def test_an_alternative_that_does_not_validate_is_dropped_and_the_default_follows_its_own() -> None:
    (got,), notes = unresolved(
        term(alt("a", "instrument.nope"), alt("b", value=2), alt("c", value=3), default=2)
    )
    assert [a.text for a in got.alternatives] == ["b", "c"] and got.default_index == 1
    assert "alternative a dropped" in notes[0]


def test_a_dropped_default_falls_back_to_the_first() -> None:
    (got,), notes = unresolved(term(alt("a", "instrument.nope"), alt("b"), alt("c"), default=0))
    assert got.default_index == 0 and got.alternatives[0].text == "b"
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


def test_a_curated_key_sent_as_a_new_slug_is_still_the_curated_one() -> None:
    (by_slug, by_alias), _ = missing(
        item(key=None, new_key_slug="support_history"), item(key=None, new_key_slug="support_share")
    )
    assert (by_slug.key, by_slug.new_key_slug) == ("support_history", None)
    assert by_alias.key == "support_history"


def test_a_closed_backlog_key_is_not_requested_again() -> None:
    got, notes = missing(item(key="built_one"), item(key=None, new_key_slug="built_one"))
    assert got == () and notes == ("built_one is PROMOTED in the backlog; request not kept",) * 2


def test_the_lists_are_capped_and_the_cut_is_said() -> None:
    many = [item(key=None, new_key_slug=f"s{n}", closest=["dist_to_support"] * 9) for n in range(8)]
    got, notes = missing(*many)
    assert len(got) == 5 and notes == ("3 missing features beyond the first 5 were cut",)
    assert all(len(m.closest) == 5 for m in got)
    terms = [term(alt("a"), alt("b"), alt("c"), alt("d"), term=f"t{n}") for n in range(5)]
    kept, said = unresolved(*terms)
    assert len(kept) == 3 and all(len(t.alternatives) == 3 for t in kept)
    assert "2 ambiguous terms beyond the first 3 were cut" in said
    assert any("1 t0 alternatives beyond the first 3 were cut" in n for n in said)
