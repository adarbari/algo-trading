"""``draft_screen`` with explained parts (ADR 0041, amended 2026-10-11): the served ``sentence``
and ``parts``, the refs of each part, the kind the server decided, the fallbacks for items the
model did not tag, parts absent from an answer that gives none, and the contract that a ``part``
tag never reaches the document (so never the saved spec or its hash)."""

import copy
import json
from typing import Any

import pytest

from algotrade.config.user import UserContext
from algotrade.services.drafting.parts.verify import doubts
from algotrade.services.drafting.screens import draft_screen, with_groups
from algotrade.services.feedback.events import document_hash
from algotrade.services.read.context import ReadContext, open_context
from algotrade_sources.framework.base import FixtureSource
from tests.helpers.api_store import api_store
from tests.unit.services.drafting.test_screens import (
    ACTIVE,
    FORMULA,
    GAP,
    OI,
    PRICE,
    PRICE_GT,
    READINGS,
    Canned,
    ctx,  # noqa: F401  (the fixture)
    proposal,
    sug,
)

SENTENCE = "active stocks over $50, deep open interest and oi per dollar for a year"
PARTS = [
    {"id": "p1", "words": "active stocks", "reading": "Active listings only"},
    {"id": "p2", "words": "over $50", "reading": "Price above $50"},
    {"id": "p3", "words": "deep open interest", "reading": "Open interest of 1,000 or more"},
    {"id": "p4", "words": "oi per dollar", "reading": "Open interest per dollar above 20"},
    {"id": "p5", "words": "for a year", "reading": "A year of history, which we do not store"},
]


def tagged(**extra: Any) -> dict[str, Any]:
    """An answer with every item tagged with its part."""
    return proposal(
        {**ACTIVE, "part": "p1"},
        {**PRICE_GT, "part": "p2"},
        tie_break={"field": PRICE, "descending": True, "part": "p2"},
        formulas=[{**FORMULA, "part": "p4"}],
        missing=[{**GAP, "part": "p5"}],
        unresolved=[{**READINGS, "part": "p3"}],
        suggestions=[sug(op="lt", value=9, part="p2")],
        parts=PARTS,
        **extra,
    )


def untagged(answer: dict[str, Any]) -> dict[str, Any]:
    """The same answer as a model that predates parts gave it."""
    out = copy.deepcopy(answer)
    out.pop("parts", None)

    def strip(node: Any) -> None:
        if isinstance(node, dict):
            node.pop("part", None)
            for v in node.values():
                strip(v)
        elif isinstance(node, list):
            for v in node:
                strip(v)

    strip(out)
    return out


def by_id(draft: Any) -> dict[str, Any]:
    return {p.id: p for p in draft.parts}


def test_every_part_serves_the_sentences_words_its_kind_and_its_refs(ctx: ReadContext) -> None:  # noqa: F811
    draft = draft_screen(ctx, Canned(tagged()), "my_screen", SENTENCE)
    assert draft.sentence == SENTENCE
    parts = by_id(draft)
    assert list(parts) == ["p1", "p2", "p3", "p4", "p5"]
    for p in parts.values():
        assert SENTENCE[p.start : p.end] == p.words  # all ASCII: code points are UTF-16 units
    assert (parts["p1"].kind, parts["p1"].criteria) == ("applied", ("active",))
    assert (parts["p2"].criteria, parts["p2"].suggestions, parts["p2"].rank) == (
        ("price",), ("s1",), True,
    )  # fmt: skip
    assert (parts["p3"].kind, parts["p3"].unresolved, parts["p3"].criteria) == (
        "needs_choice", ("deep",), ("deep",),
    )  # fmt: skip
    assert (parts["p4"].kind, parts["p4"].formulas) == ("formula", ("draft_oi_per_dollar",))
    assert (parts["p5"].kind, parts["p5"].missing) == ("not_available", ("oi_history",))
    assert [s.id for s in draft.suggestions] == ["s1"]
    assert draft.parts_stats is not None
    assert (
        draft.parts_stats.by_model == draft.parts_stats.items == 8
    )  # 3 criteria, formula, term, request, check, rank


def test_a_part_tag_never_reaches_the_document_so_the_spec_and_its_hash_do_not_change(
    ctx: ReadContext,  # noqa: F811
) -> None:
    """The contract: tagging an answer with parts changes nothing the Builder saves."""
    with_parts = draft_screen(ctx, Canned(tagged()), "my_screen", SENTENCE)
    without = draft_screen(ctx, Canned(untagged(tagged())), "my_screen", SENTENCE)
    assert with_parts.document == without.document
    assert document_hash(with_parts.document) == document_hash(without.document)
    assert '"part"' not in json.dumps(with_parts.document)
    assert (with_parts.formulas[0].criterion, with_parts.formulas[0].fingerprint) == (
        without.formulas[0].criterion, without.formulas[0].fingerprint,
    )  # fmt: skip
    assert [s.criterion for s in with_parts.suggestions] == [
        s.criterion for s in without.suggestions
    ]
    assert [a.criterion for u in with_parts.unresolved for a in u.alternatives] == [
        a.criterion for u in without.unresolved for a in u.alternatives
    ]


def test_an_answer_without_parts_is_the_draft_it_was_and_serves_no_parts(
    ctx: ReadContext,  # noqa: F811
) -> None:
    """Replay of answers recorded before parts: they pass through the fallback unchanged."""
    draft = draft_screen(ctx, Canned(untagged(tagged())), "my_screen", SENTENCE)
    assert draft.parts is None and draft.parts_stats is None and draft.sentence == SENTENCE
    assert set(draft.document["criteria"]) == {"active", "price", "deep"}


def test_items_the_model_did_not_tag_fall_back_to_the_span_then_a_catch_all(
    ctx: ReadContext,  # noqa: F811
) -> None:
    carried = {"id": "price", "field": PRICE, "op": "gt", "value": 50}
    answer = proposal(
        ACTIVE, carried, {"id": "oi", "field": OI, "op": "gt", "value": 5},
        missing=[GAP], unresolved=[READINGS],
        parts=[PARTS[2], PARTS[4]],
    )  # fmt: skip
    current = {"criteria": {"price": {"field": PRICE, "op": "gt", "value": 50}}}
    draft = draft_screen(ctx, Canned(answer), "my_screen", SENTENCE, current)
    parts = by_id(draft)
    assert (parts["p3"].unresolved, parts["p5"].missing) == (("deep",), ("oi_history",))  # by span
    assert parts["kept"].criteria == ("price",) and parts["kept"].origin == "kept"
    assert set(parts["unplaced"].criteria) == {"active", "oi"}  # nothing says where they came from
    assert (parts["unplaced"].words, parts["unplaced"].start) == ("", 0)
    assert draft.parts_stats is not None and draft.parts_stats.by_model == 0
    gap = [p for p in draft.parts if p.kind == "not_understood"]
    assert [g.words for g in gap] == [
        "active stocks over $50",
        "oi per dollar",
    ]  # nobody covers them
    assert all(g.origin == "gap" and g.criteria == () for g in gap)


def test_a_reading_that_contradicts_the_criteria_is_dropped_but_the_rows_stay(
    ctx: ReadContext,  # noqa: F811
) -> None:
    parts = [{**PARTS[1], "reading": "Price above $500"}]
    answer = proposal({**PRICE_GT, "part": "p2"}, parts=parts)
    draft = draft_screen(ctx, Canned(answer), "my_screen", SENTENCE)
    p = by_id(draft)["p2"]
    assert (p.reading, p.reading_source, p.criteria) == (None, "server", ("price",))
    assert draft.parts_stats is not None and draft.parts_stats.readings_kept == 0


def test_the_sentence_is_the_normalised_text_the_offsets_count_in(ctx: ReadContext) -> None:  # noqa: F811
    answer = proposal({**PRICE_GT, "part": "p2"}, parts=[PARTS[1]])
    draft = draft_screen(ctx, Canned(answer), "my_screen", "  active   stocks\n over   $50 🚀 ")
    assert draft.sentence == "active stocks over $50 🚀"
    p = by_id(draft)["p2"]
    assert (
        draft.sentence.encode("utf-16-le")[2 * p.start : 2 * p.end].decode("utf-16-le") == p.words
    )
    assert [g.words for g in draft.parts or () if g.kind == "not_understood"] == [
        "active stocks",
        "🚀",
    ][:1]


@pytest.mark.parametrize("bad", ["p9", "", None, 7, "P1"])
def test_a_tag_that_names_no_part_is_not_an_error(ctx: ReadContext, bad: Any) -> None:  # noqa: F811
    answer = proposal({**PRICE_GT, "part": bad}, parts=[PARTS[1]])
    draft = draft_screen(ctx, Canned(answer), "my_screen", SENTENCE)
    assert by_id(draft)["unplaced"].criteria == ("price",)


def test_a_part_never_says_rank_for_a_tie_break_the_validator_removed(ctx: ReadContext) -> None:  # noqa: F811
    for field in ("instrument.status", "rollup.nope@v1.x"):
        answer = proposal(
            {**PRICE_GT, "part": "p2"},
            tie_break={"field": field, "descending": True, "part": "p2"},
            parts=[PARTS[1]],
        )
        draft = draft_screen(ctx, Canned(answer), "my_screen", SENTENCE)
        assert "rank" not in draft.document, field
        assert not any(p.rank for p in draft.parts or ()), field


def test_criterion_ids_are_unique_across_kept_and_dropped_so_tags_never_mix(
    ctx: ReadContext,  # noqa: F811
) -> None:
    bad = {"id": "price", "field": PRICE, "op": "like", "value": 1, "part": "p1"}
    good = {**PRICE_GT, "id": "price", "part": "p2"}
    draft = draft_screen(ctx, Canned(proposal(bad, good, parts=PARTS[:2])), "my_screen", SENTENCE)
    assert [d.id for d in draft.dropped] == ["price"] and list(draft.document["criteria"]) == [
        "price_2"
    ]
    parts = by_id(draft)
    assert (parts["p1"].dropped, parts["p1"].criteria) == (("price",), ())
    assert (parts["p2"].criteria, parts["p2"].dropped) == (("price_2",), ())


@pytest.fixture
def golden_ctx(golden_source: FixtureSource) -> ReadContext:
    store = api_store(golden_source)[0]
    return open_context(store.reader, store.configs, UserContext(store.user.user_id))


def test_a_rewritten_duplicate_formula_does_not_take_a_dropped_criterions_id(
    golden_ctx: ReadContext,
) -> None:
    """A criterion dropped as ``close`` and a bare-column formula rewritten onto ``...close`` keep
    distinct ids, so each part's refs name its own item."""
    bare = {
        **FORMULA, "name": "draft_close", "expr": "price_stats.close", "unit": "usd_per_share",
        "inputs": ["price_stats.close"], "part": "p2",
        "criterion": {"op": "gt", "value": 5, "mode": None, "tolerance": None},
    }  # fmt: skip
    invented = {
        "id": "close",
        "field": "rollup.nope@v1.close",
        "op": "gt",
        "value": 1,
        "part": "p1",
    }
    parts = [
        {"id": "p1", "words": "close over $1", "reading": None},
        {"id": "p2", "words": "price above 5", "reading": None},
    ]
    draft = draft_screen(
        golden_ctx, Canned(proposal(invented, formulas=[bare], parts=parts)), "golden",
        "close over $1 and price above 5",
    )  # fmt: skip
    assert [d.id for d in draft.dropped] == ["close"]
    assert list(draft.document["criteria"]) == ["close_2"]
    got = by_id(draft)
    assert (got["p1"].dropped, got["p1"].criteria) == (("close",), ())
    assert (got["p2"].criteria, got["p2"].dropped) == (("close_2",), ())


OI_GTE = {"id": "oi", "field": OI, "op": "gte", "value": 1000, "why": "open interest 1000"}
EITHER = [
    {"id": "p1", "words": "over $50", "reading": None},
    {"id": "p2", "words": "open interest of 1000", "reading": None},
]  # the "or" between them is left out of the words


def test_an_or_between_parts_is_a_group_in_the_document_never_a_formula(ctx: ReadContext) -> None:  # noqa: F811
    """ADR 0071: "A or B" is two criteria and an ``any`` group, validated as finalise would."""
    answer = proposal({**PRICE_GT, "part": "p1"}, {**OI_GTE, "part": "p2"}, parts=EITHER)
    draft = draft_screen(ctx, Canned(answer), "my_screen", "over $50 or open interest of 1000")
    assert draft.document["groups"] == {"any_1": {"any": ["price", "oi"]}}
    assert [(p.words, p.join) for p in draft.parts or ()] == [
        ("over $50", None), ("open interest of 1000", "or"),
    ]  # fmt: skip
    assert doubts(draft.parts, False, draft.document["criteria"]) == ()
    assert draft.formulas == () and '"part"' not in json.dumps(draft.document)


def test_a_part_keeps_its_mode_inside_a_group(ctx: ReadContext) -> None:  # noqa: F811
    soft = {**OI_GTE, "mode": "score", "tolerance": 100}
    answer = proposal({**PRICE_GT, "part": "p1"}, {**soft, "part": "p2"}, parts=EITHER)
    draft = draft_screen(ctx, Canned(answer), "my_screen", "over $50 or open interest of 1000")
    assert draft.document["groups"] == {"any_1": {"any": ["price", "oi"]}}
    assert draft.document["criteria"]["price"].get("mode") is None
    assert draft.document["criteria"]["oi"]["mode"] == "score"


def test_a_formula_part_beside_an_or_keeps_the_draft_flat_and_is_doubted(ctx: ReadContext) -> None:  # noqa: F811
    """Grouping impossible (a pending formula cannot sit in a group): today's path, and the
    verifier's doubt, which now fires only here."""
    parts = [
        {"id": "p1", "words": "over $50", "reading": None},
        {"id": "p2", "words": "oi per dollar above 20", "reading": None},
    ]
    answer = proposal({**PRICE_GT, "part": "p1"}, formulas=[{**FORMULA, "part": "p2"}], parts=parts)
    draft = draft_screen(ctx, Canned(answer), "my_screen", "over $50 or oi per dollar above 20")
    assert "groups" not in draft.document
    found = doubts(draft.parts, False, draft.document["criteria"])
    assert [(d.kind, d.ref) for d in found] == [("or_not_formula", "p2")]


def test_the_groups_of_the_builders_document_survive_a_sentence_that_adds_no_connector(
    ctx: ReadContext,  # noqa: F811
) -> None:
    current = {
        "criteria": {"price": {"field": PRICE, "op": "gt", "value": 50},
                     "oi": {"field": OI, "op": "gte", "value": 1000}},
        "groups": {"mine": {"any": ["price", "oi"]}},
    }  # fmt: skip
    answer = proposal({**PRICE_GT, "part": "p1"}, {**OI_GTE, "part": "p2"}, parts=EITHER)
    draft = draft_screen(
        ctx, Canned(answer), "my_screen", "over $50 open interest of 1000", current
    )
    assert draft.document["groups"] == {"mine": {"any": ["price", "oi"]}}
    gone = {**current, "groups": {"mine": {"any": ["price", "ghost"]}}}  # a member the draft lost
    again = draft_screen(ctx, Canned(answer), "my_screen", "over $50 open interest of 1000", gone)
    assert "groups" not in again.document


def test_groups_the_validator_refuses_leave_the_draft_flat(ctx: ReadContext) -> None:  # noqa: F811
    base = {"id": "my_screen", "kind": "screener", "impl": "rules",
            "criteria": {"price": {"field": PRICE, "op": "gt", "value": 50}}}  # fmt: skip
    bad = {"g": {"any": ["price", "ghost"]}}
    good = {"g": {"any": ["price", "oi"]}}
    both = {**base, "criteria": {**base["criteria"], "oi": {"field": OI, "op": "gte", "value": 1}}}
    flat, why = with_groups(ctx, "my_screen", base, [bad])
    assert "groups" not in flat and "not applied" in why[0]  # told, never silent
    grouped, none = with_groups(ctx, "my_screen", both, [bad, good])
    assert grouped["groups"] == good and none == ()  # the next one


def test_a_new_group_never_takes_the_id_of_one_the_builder_has(ctx: ReadContext) -> None:  # noqa: F811
    current = {
        "criteria": {"price": {"field": PRICE, "op": "gt", "value": 50},
                     "oi": {"field": OI, "op": "gte", "value": 1000}},
        "groups": {"any_1": {"any": ["price", "oi"]}},
    }  # fmt: skip
    only_price = proposal({**PRICE_GT, "part": "p1"}, {**OI_GTE, "part": "p2"}, parts=EITHER)
    draft = draft_screen(
        ctx, Canned(only_price), "my_screen", "over $50 or open interest of 1000", current
    )
    assert draft.document["groups"] == {"any_1": {"any": ["price", "oi"]}}  # carried, not replaced


def test_an_or_next_to_a_missing_part_is_told_in_a_note(ctx: ReadContext) -> None:  # noqa: F811
    parts = [
        {"id": "p1", "words": "over $50", "reading": None},
        {"id": "p2", "words": "for a year", "reading": None},
    ]
    answer = proposal({**PRICE_GT, "part": "p1"}, missing=[{**GAP, "part": "p2"}], parts=parts)
    draft = draft_screen(ctx, Canned(answer), "my_screen", "over $50 or for a year")
    assert "groups" not in draft.document
    assert any("'for a year' is not available" in n for n in draft.notes)
