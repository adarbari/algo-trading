"""``redraft_part`` (ADR 0041, amended 2026-10-12): one part's words are retyped, the model is
asked about them alone, and the answer replaces that part in the draft the browser holds. The
part's own criteria are replaced as a whole, the other parts win a conflict on the same field and
operator, what the trader added by hand stays in the ``kept`` part, ids stay unique, the offsets
of the words after the new ones move (in UTF-16 units) and the call is tagged and counted as a
part re-draft."""

from typing import Any

import pytest

from algotrade.core.model.completion import CallTag, Completion
from algotrade.core.model.errors import ConfigurationError, ModelUnavailableError
from algotrade.services.drafting.prompt import PROMPT_VERSION
from algotrade.services.drafting.redraft.merge import OTHER_PART, TAKEN_FORMULA
from algotrade.services.drafting.redraft.request import MAX_ITEMS, check_request
from algotrade.services.drafting.redraft.run import redraft_part
from algotrade.services.drafting.screens import MAX_TEXT
from algotrade.services.read.context import ReadContext
from tests.helpers.drafting.redraft import (
    OI,
    PRICE,
    Canned,
    answer_for,
    body_of,
    held_draft,
)
from tests.unit.services.drafting.test_screens import (
    ALICE,
    FORMULA,
    GAP,
    READINGS,
    ctx,  # noqa: F401  (the fixture)
    sug,
)

PRICE_80 = {"id": "price", "field": PRICE, "op": "gt", "value": 80}
ROW_80 = {"field": PRICE, "op": "gt", "value": 80}  # as the document holds it (no id)


def redraft(ctx: ReadContext, model: Any, part_id: str, words: str, **over: Any):  # noqa: F811
    prior = held_draft(ctx)
    req = check_request("my_screen", body_of(prior, part_id, words, **over))
    return redraft_part(ctx, model, req), prior


def by_id(draft: Any) -> dict[str, Any]:
    return {p.id: p for p in draft.parts}


def units(text: str, start: int, end: int) -> str:
    """What the browser's ``slice`` gives: UTF-16 code units."""
    return text.encode("utf-16-le")[2 * start : 2 * end].decode("utf-16-le")


def test_the_part_is_replaced_as_a_whole_and_every_other_part_stays(ctx: ReadContext) -> None:  # noqa: F811
    model = Canned(answer_for("over $80", PRICE_80, reading="Price above $80"))
    done, prior = redraft(ctx, model, "p2", "over $80")
    draft = done.draft
    assert done.replaced_part_id == "p2" and (done.old_words, done.new_words) == (
        "over $50", "over $80",
    )  # fmt: skip
    assert draft.document["criteria"]["price"] == ROW_80
    assert draft.document["criteria"]["active"] == prior.document["criteria"]["active"]
    assert set(draft.document["criteria"]) == set(prior.document["criteria"])
    assert (
        draft.sentence == "active stocks over $80, deep open interest and oi per dollar for a year"
    )
    parts = by_id(draft)
    assert list(parts) == ["p1", "p2", "p3", "p4", "p5"]
    for part in parts.values():
        assert units(draft.sentence, part.start, part.end) == part.words
    assert (parts["p2"].words, parts["p2"].kind, parts["p2"].origin) == (
        "over $80",
        "applied",
        "words",
    )
    assert (parts["p2"].reading, parts["p2"].reading_source) == ("Price above $80", "model")
    for kept_id in ("p1", "p3", "p4", "p5"):  # nothing else of them changed
        assert parts[kept_id] == by_id(prior)[kept_id]
    # the other parts' items are carried whole
    assert [f.name for f in draft.formulas] == [f.name for f in prior.formulas]
    assert draft.formulas[0].dry_run == prior.formulas[0].dry_run  # echoed, not run again
    assert [m.new_key_slug for m in draft.missing] == [m.new_key_slug for m in prior.missing]
    assert [(u.term, u.default_index, u.alternatives) for u in draft.unresolved] == [
        (u.term, u.default_index, u.alternatives) for u in prior.unresolved
    ]
    assert [d.reason for d in draft.dropped] == [d.reason for d in prior.dropped]


def test_the_part_asked_only_about_its_own_words_with_the_other_criteria_fixed(
    ctx: ReadContext,  # noqa: F811
) -> None:
    model = Canned(answer_for("over $80", PRICE_80))
    redraft(ctx, model, "p2", "over $80")
    ((_, user),) = model.asked
    assert "Part words: over $80" in user and "Sentence:" not in user
    fixed = user.split("Fixed criteria")[1].split("Part words")[0]
    assert "active | instrument.status eq" in fixed and "deep |" in fixed
    assert "price |" not in fixed  # the part's own criteria are not fixed
    assert model.tags == [CallTag("screener-draft-part", ALICE, PROMPT_VERSION)]


def test_the_part_replaces_its_old_rows_even_when_the_trader_edited_them(
    ctx: ReadContext,  # noqa: F811
) -> None:
    prior = held_draft(ctx)
    edited = {**prior.document, "criteria": {**prior.document["criteria"]}}
    edited["criteria"]["price"] = {"field": PRICE, "op": "lt", "value": 3}  # a hand edit
    body = body_of(prior, "p2", "over $80", document=edited)
    req = check_request("my_screen", body)
    done = redraft_part(ctx, Canned(answer_for("over $80", PRICE_80)), req)
    assert done.draft.document["criteria"]["price"] == ROW_80


def test_a_criterion_another_part_sets_on_the_same_field_and_operator_is_dropped(
    ctx: ReadContext,  # noqa: F811
) -> None:
    same_as_p3 = {"id": "open_interest", "field": OI, "op": "gte", "value": 5}  # p3 has OI gte
    answer = answer_for("over $80 with oi", PRICE_80, same_as_p3, reading="Price above $80")
    done, prior = redraft(ctx, Canned(answer), "p2", "over $80 with oi")
    draft, p2 = done.draft, by_id(done.draft)["p2"]
    assert set(draft.document["criteria"]) == set(prior.document["criteria"])
    assert draft.document["criteria"]["deep"] == prior.document["criteria"]["deep"]  # p3 wins
    lost = [d for d in draft.dropped if d.reason == OTHER_PART]
    assert [(d.id, d.field) for d in lost] == [("open_interest", OI)]
    assert p2.dropped == ("open_interest",) and p2.criteria == ("price",)
    assert p2.reading is None and p2.reading_source == "server"  # it described what was dropped


def test_a_part_whose_every_criterion_was_set_by_another_part_is_not_available(
    ctx: ReadContext,  # noqa: F811
) -> None:
    only = {"id": "dup", "field": OI, "op": "gte", "value": 5}
    done, _ = redraft(ctx, Canned(answer_for("lots of oi", only)), "p2", "lots of oi")
    p2 = by_id(done.draft)["p2"]
    assert (p2.kind, p2.criteria, p2.dropped) == ("not_available", (), ("dup",))
    assert "price" not in done.draft.document["criteria"]  # the old row is gone


def test_what_the_trader_added_by_hand_stays_in_the_kept_part(ctx: ReadContext) -> None:  # noqa: F811
    prior = held_draft(ctx)
    by_hand = {"field": "instrument.optionable", "op": "eq", "value": True}
    document = {**prior.document, "criteria": {**prior.document["criteria"], "optionable": by_hand}}
    body = body_of(prior, "p2", "over $80", document=document)
    done = redraft_part(
        ctx, Canned(answer_for("over $80", PRICE_80)), check_request("my_screen", body)
    )
    parts = by_id(done.draft)
    assert done.draft.document["criteria"]["optionable"] == by_hand
    assert (parts["kept"].criteria, parts["kept"].origin, parts["kept"].kind) == (
        ("optionable",), "kept", "applied",
    )  # fmt: skip
    assert parts["kept"].words == "" and (parts["kept"].start, parts["kept"].end) == (0, 0)
    assert list(parts)[-1] == "kept"  # catch-alls last
    assert "optionable" not in parts["p2"].criteria
    again = redraft_part(  # and a second retype keeps it there
        ctx, Canned(answer_for("over $90", PRICE_80 | {"value": 90})),
        check_request("my_screen", body_of(done.draft, "p2", "over $90")),
    )  # fmt: skip
    assert by_id(again.draft)["kept"].criteria == ("optionable",)


def test_a_criterion_the_trader_deleted_is_not_an_error_and_leaves_its_part(
    ctx: ReadContext,  # noqa: F811
) -> None:
    prior = held_draft(ctx)
    smaller = dict(prior.document["criteria"])
    del smaller["active"]  # the trader deleted the row of p1
    body = body_of(prior, "p2", "over $80", document={**prior.document, "criteria": smaller})
    done = redraft_part(
        ctx, Canned(answer_for("over $80", PRICE_80)), check_request("my_screen", body)
    )
    p1 = by_id(done.draft)["p1"]
    assert "active" not in done.draft.document["criteria"]
    assert (p1.criteria, p1.kind) == ((), "not_understood")  # the part decided again from its refs


def test_the_words_after_the_new_ones_move_with_them_in_utf16_units(ctx: ReadContext) -> None:  # noqa: F811
    words = "over $80 🚀 é"
    done, prior = redraft(ctx, Canned(answer_for(words, PRICE_80)), "p2", words)
    draft = done.draft
    assert (
        draft.sentence == f"active stocks {words}, deep open interest and oi per dollar for a year"
    )
    for part in draft.parts or ():
        assert units(draft.sentence, part.start, part.end) == part.words
    delta = len(words.encode("utf-16-le")) // 2 - len("over $50")
    old, new = by_id(prior), by_id(draft)
    assert (new["p1"].start, new["p1"].end) == (old["p1"].start, old["p1"].end)
    assert (new["p3"].start, new["p3"].end) == (old["p3"].start + delta, old["p3"].end + delta)
    assert new["p5"].end - new["p5"].start == old["p5"].end - old["p5"].start


def test_a_shorter_retype_pulls_the_later_words_back(ctx: ReadContext) -> None:  # noqa: F811
    done, _ = redraft(ctx, Canned(answer_for("cheap", PRICE_80 | {"value": 5})), "p2", "cheap")
    for part in done.draft.parts or ():
        assert units(done.draft.sentence, part.start, part.end) == part.words
    assert by_id(done.draft)["p2"].words == "cheap"


def test_an_item_another_part_already_offers_is_not_offered_twice(ctx: ReadContext) -> None:  # noqa: F811
    """The retyped part brings a formula, a term and a request of the names the other parts
    already offer: the other parts keep them, the new ones are left out (a formula is listed as
    dropped), and the part does not point at what it does not own."""
    answer = answer_for(
        "liquid for a year", PRICE_80,
        formulas=[{**FORMULA, "part": "p1"}], missing=[{**GAP, "part": "p1"}],
        unresolved=[{**READINGS, "part": "p1"}],
    )  # fmt: skip
    done, _ = redraft(ctx, Canned(answer), "p2", "liquid for a year")
    p2, draft = by_id(done.draft)["p2"], done.draft
    assert p2.formulas == () and p2.unresolved == ()
    assert [f.name for f in draft.formulas] == ["draft_oi_per_dollar"]
    assert by_id(draft)["p4"].formulas == ("draft_oi_per_dollar",)  # still p4's
    assert [(d.name, d.reason) for d in draft.formulas_dropped] == [
        ("draft_oi_per_dollar", TAKEN_FORMULA)
    ]
    assert [u.term for u in draft.unresolved] == ["deep"]
    assert any("deep: not offered again" in n for n in draft.notes)
    assert [m.new_key_slug for m in draft.missing] == ["oi_history"]  # one request, two parts
    assert (p2.missing, by_id(draft)["p5"].missing) == (("oi_history",), ("oi_history",))


def test_a_new_formula_term_check_and_request_are_the_parts_own(ctx: ReadContext) -> None:  # noqa: F811
    formula = {**FORMULA, "name": "draft_oi_cover", "part": "p1"}
    term = {**READINGS, "term": "liquid", "span": "liquid", "part": "p1"}
    answer = answer_for(
        "liquid cover", PRICE_80, formulas=[formula], unresolved=[term],
        suggestions=[sug(op="lt", value=9, part="p1")],
    )  # fmt: skip
    done, _ = redraft(ctx, Canned(answer), "p2", "liquid cover")
    p2, draft = by_id(done.draft)["p2"], done.draft
    assert (p2.kind, p2.formulas, p2.unresolved) == (
        "needs_choice",
        ("draft_oi_cover",),
        ("liquid",),
    )
    assert {f.name for f in draft.formulas} == {"draft_oi_per_dollar", "draft_oi_cover"}
    assert {u.term for u in draft.unresolved} == {"deep", "liquid"}
    assert p2.suggestions == ("s1",) and [s.id for s in draft.suggestions] == [
        "s1"
    ]  # its old s1 went


def test_a_new_suggestion_takes_the_next_free_id_and_the_others_keep_theirs(
    ctx: ReadContext,  # noqa: F811
) -> None:
    prior = held_draft(ctx)
    assert [s.id for s in prior.suggestions] == ["s1"] and by_id(prior)["p2"].suggestions == ("s1",)
    answer = answer_for(
        "deep oi", {"id": "oi", "field": OI, "op": "gt", "value": 7},
        suggestions=[sug(field=PRICE, op="lt", value=9, part="p1")],
    )  # fmt: skip
    done, _ = redraft(ctx, Canned(answer), "p3", "deep oi")
    draft = done.draft
    assert [s.id for s in draft.suggestions] == ["s1", "s2"]
    assert by_id(draft)["p2"].suggestions == ("s1",) and by_id(draft)["p3"].suggestions == ("s2",)


def test_ids_of_the_new_items_never_collide_with_those_of_the_other_parts(
    ctx: ReadContext,  # noqa: F811
) -> None:
    clash = {"id": "deep", "field": "instrument.status", "op": "ne", "value": "DELISTED"}
    answer = answer_for(
        "not delisted", clash, suggestions=[sug(field=PRICE, op="lt", value=9, part="p1")]
    )
    done, prior = redraft(ctx, Canned(answer), "p2", "not delisted")
    criteria = done.draft.document["criteria"]
    assert criteria["deep"] == prior.document["criteria"]["deep"]  # p3's is untouched
    assert criteria["deep_2"]["field"] == "instrument.status"
    p2 = by_id(done.draft)["p2"]
    assert p2.criteria == ("deep_2",)
    ids = [s.id for s in done.draft.suggestions]
    assert len(ids) == len(set(ids)) and set(p2.suggestions) <= set(ids)


def test_the_tie_break_stays_when_another_part_owns_it_and_goes_with_its_own_part(
    ctx: ReadContext,  # noqa: F811
) -> None:
    prior = held_draft(ctx)
    assert by_id(prior)["p2"].rank and prior.document["rank"] == {"tie_break": PRICE}
    # the part that owns it is retyped with no rank: the document's goes
    gone, _ = redraft(ctx, Canned(answer_for("over $80", PRICE_80)), "p2", "over $80")
    assert "rank" not in gone.draft.document and not any(p.rank for p in gone.draft.parts or ())
    # another part is retyped asking for a rank of its own: the document's stays
    other = answer_for(
        "at least 5 contracts", {"id": "oi", "field": OI, "op": "gt", "value": 5},
        tie_break={"field": OI, "descending": True, "part": "p1"},
    )  # fmt: skip
    kept, _ = redraft(ctx, Canned(other), "p3", "at least 5 contracts")
    assert kept.draft.document["rank"] == {"tie_break": PRICE}
    assert [p.id for p in kept.draft.parts or () if p.rank] == ["p2"]


def test_a_part_that_asks_for_the_rank_gets_it_when_the_document_has_none(
    ctx: ReadContext,  # noqa: F811
) -> None:
    prior = held_draft(ctx)
    no_rank = {k: v for k, v in prior.document.items() if k != "rank"}
    body = body_of(
        prior, "p3", "rank by oi", document=no_rank,
        parts=[{**p, "rank": False} for p in body_of(prior, "p3", "x")["parts"]],
    )  # fmt: skip
    answer = answer_for("rank by oi", tie_break={"field": OI, "descending": True, "part": "p1"})
    done = redraft_part(ctx, Canned(answer), check_request("my_screen", body))
    assert done.draft.document["rank"] == {"tie_break": OI}
    assert by_id(done.draft)["p3"].rank and by_id(done.draft)["p3"].kind == "applied"


def test_missing_requests_are_the_re_drafted_parts_own(ctx: ReadContext) -> None:  # noqa: F811
    new_gap = {**GAP, "new_key_slug": "held_two_years", "span": "held two years", "part": "p1"}
    done, prior = redraft(
        ctx, Canned(answer_for("held two years", missing=[new_gap])), "p3", "held two years"
    )
    assert [m.new_key_slug for m in done.missing] == ["held_two_years"]  # what the log records
    assert [m.new_key_slug for m in done.draft.missing] == ["oi_history", "held_two_years"]
    assert by_id(done.draft)["p3"].missing == ("held_two_years",)
    assert by_id(done.draft)["p5"].missing == ("oi_history",)  # p5's stays, and is not re-recorded
    assert prior.missing[0].new_key_slug == "oi_history"


def test_the_model_answer_that_cannot_be_used_is_an_unavailable_model(ctx: ReadContext) -> None:  # noqa: F811
    with pytest.raises(ModelUnavailableError):
        redraft(ctx, Canned("not json at all"), "p2", "over $80")


def test_the_call_is_told_to_the_cap_as_soon_as_the_model_has_answered(
    ctx: ReadContext,  # noqa: F811
) -> None:
    class Ids(Canned):
        def complete(self, system: str, user: str, **kw: Any) -> Completion:
            return Completion(self.answer, "m", "p", call_id="call-7")

    told: list[str | None] = []
    prior = held_draft(ctx)
    req = check_request("my_screen", body_of(prior, "p2", "over $80"))
    done = redraft_part(ctx, Ids(answer_for("over $80", PRICE_80)), req, told.append)
    assert told == ["call-7"] and done.draft.call_id == "call-7"


def test_a_criterion_of_the_trader_the_validator_refuses_is_named_before_the_model_is_asked(
    ctx: ReadContext,  # noqa: F811
) -> None:
    prior = held_draft(ctx)
    broken = {**prior.document, "criteria": {**prior.document["criteria"]}}
    broken["criteria"]["active"] = {"field": "rollup.nope@v1.x", "op": "gt", "value": 1}
    body = body_of(prior, "p2", "over $80", document=broken)
    model = Canned(answer_for("over $80", PRICE_80))
    with pytest.raises(ConfigurationError, match="the criterion 'active' of your screen"):
        redraft_part(ctx, model, check_request("my_screen", body))
    assert model.asked == []  # nothing was spent on a screen that cannot be saved


def test_the_part_being_retyped_may_hold_a_refused_criterion_it_is_replaced_anyway(
    ctx: ReadContext,  # noqa: F811
) -> None:
    prior = held_draft(ctx)
    broken = {**prior.document, "criteria": {**prior.document["criteria"]}}
    broken["criteria"]["price"] = {"field": "rollup.nope@v1.x", "op": "gt", "value": 1}  # p2's own
    body = body_of(prior, "p2", "over $80", document=broken)
    done = redraft_part(ctx, Canned(answer_for("over $80", PRICE_80)), check_request("s", body))
    assert done.draft.document["criteria"]["price"] == ROW_80


def test_a_tie_break_of_the_trader_the_validator_would_remove_is_refused_before_the_model_is_asked(
    ctx: ReadContext,  # noqa: F811
) -> None:
    prior = held_draft(ctx)  # p2 owns the tie-break; p3 is retyped
    bad = {**prior.document, "rank": {"tie_break": "rollup.nope@v1.x"}}
    model = Canned(answer_for("deep oi", {"id": "oi", "field": OI, "op": "gt", "value": 5}))
    with pytest.raises(ConfigurationError, match="the tie-break of your screen is not valid"):
        redraft_part(ctx, model, check_request("s", body_of(prior, "p3", "deep oi", document=bad)))
    assert model.asked == []


def test_a_reading_is_dropped_when_the_merge_discarded_a_formula_a_term_or_the_rank(
    ctx: ReadContext,  # noqa: F811
) -> None:
    """The reading described what the model proposed; if the merge left part of it out, the
    reading would claim more than the rows hold."""
    said = "Price above $80 with a formula"
    formula = answer_for(
        "over $80", PRICE_80, reading=said, formulas=[{**FORMULA, "part": "p1"}]
    )  # p4 already offers it
    done, _ = redraft(ctx, Canned(formula), "p2", "over $80")
    assert (by_id(done.draft)["p2"].reading, by_id(done.draft)["p2"].reading_source) == (
        None, "server",
    )  # fmt: skip
    term = answer_for("over $80", PRICE_80, reading=said, unresolved=[{**READINGS, "part": "p1"}])
    done, _ = redraft(ctx, Canned(term), "p2", "over $80")  # p3 already has "deep"
    assert by_id(done.draft)["p2"].reading is None
    rank = answer_for(
        "deep oi", {"id": "oi", "field": OI, "op": "gt", "value": 5},
        reading="Open interest above 5",
        tie_break={"field": OI, "descending": True, "part": "p1"},
    )  # fmt: skip
    done, _ = redraft(ctx, Canned(rank), "p3", "deep oi")  # p2 owns the tie-break
    assert by_id(done.draft)["p3"].reading is None
    assert any(
        n.startswith("rank: the tie-break another part sets stays") for n in done.draft.notes
    )
    kept = answer_for(
        "deep oi",
        {"id": "oi", "field": OI, "op": "gt", "value": 5},
        reading="Open interest above 5",
    )
    done, _ = redraft(ctx, Canned(kept), "p3", "deep oi")  # nothing discarded: the reading stays
    assert by_id(done.draft)["p3"].reading == "Open interest above 5"


def test_the_requests_of_the_new_words_are_only_those_the_draft_did_not_have(
    ctx: ReadContext,  # noqa: F811
) -> None:
    again = {**GAP, "part": "p1"}  # oi_history: p5 asked for it already
    new = {**GAP, "new_key_slug": "held_two_years", "span": "held two years", "part": "p1"}
    done, _ = redraft(
        ctx, Canned(answer_for("held two years", missing=[again, new])), "p3", "held two years"
    )
    assert [m.new_key_slug for m in done.missing] == ["held_two_years"]
    assert by_id(done.draft)["p3"].missing == ("oi_history", "held_two_years")  # it still points


def test_what_only_grows_stays_within_what_the_next_request_may_carry(
    ctx: ReadContext,  # noqa: F811
) -> None:
    prior = held_draft(ctx)
    for n in range(45):  # forty-five retypes, each leaving two notes and a dropped check behind
        answer = answer_for(
            f"over ${n + 80}",
            {**PRICE_80, "value": n + 80},
            notes=[f"note {n} one", f"note {n} two " + "x" * 2000],
            suggestions=[sug(field="nope.x", part="p1")],
        )
        req = check_request("my_screen", body_of(prior, "p2", f"over ${n + 80}"))
        prior = redraft_part(ctx, Canned(answer), req).draft
    assert len(prior.notes) == len(prior.suggestions_dropped) == MAX_ITEMS
    assert prior.notes[-1].startswith("note 44 two") and len(prior.notes[-1]) <= MAX_TEXT
    assert "note 0 one" not in prior.notes  # the oldest went first


def test_dropped_criteria_are_bounded_and_the_parts_stop_pointing_at_the_ones_gone(
    ctx: ReadContext,  # noqa: F811
) -> None:
    invented = [{"id": f"x{n}", "field": f"rollup.nope@v1.x{n}", "op": "gt", "value": 1}
                for n in range(MAX_ITEMS + 10)]  # fmt: skip
    answer = answer_for("many things", PRICE_80, *invented)
    done, _ = redraft(ctx, Canned(answer), "p2", "many things")
    draft, p2 = done.draft, by_id(done.draft)["p2"]
    kept = {d.id for d in draft.dropped}
    assert len(draft.dropped) == MAX_ITEMS and len(kept) == MAX_ITEMS
    assert set(p2.dropped) == kept  # every one that stayed is this part's
    assert all(ref in kept for p in draft.parts or () for ref in p.dropped)  # no dangling ref
    assert "x0" not in kept and f"x{MAX_ITEMS + 9}" in kept  # the oldest went first
    # and what comes back is a request that holds together
    check_request("my_screen", body_of(draft, "p3", "deep oi"))
