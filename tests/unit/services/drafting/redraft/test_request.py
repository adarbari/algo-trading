"""``check_request`` (ADR 0041, amended 2026-10-12): nothing the browser sends is trusted. Every
part's words must be the sentence's own slice at its UTF-16 offsets, ids unique and in order, every
id a part names an item the draft holds, the part retyped one with words of its own, the new
words and the merged sentence within their caps; each failure is a ``ConfigurationError`` (400)
before anything is asked."""

from typing import Any

import pytest

from algotrade.core.model.errors import ConfigurationError
from algotrade.services.drafting.redraft.request import MAX_CRITERIA, check_request
from algotrade.services.drafting.screens import MAX_TEXT
from algotrade.services.read.context import ReadContext
from tests.helpers.drafting.redraft import body_of, held_draft
from tests.unit.services.drafting.test_screens import ctx  # noqa: F401  (the fixture)

SENTENCE = "café stocks 🚀 over $5 and more"  # é is one UTF-16 unit, 🚀 two: offsets differ


def part(pid: str, words: str, start: int, end: int, **over: Any) -> dict[str, Any]:
    return {"id": pid, "words": words, "start": start, "end": end, "origin": "words", **over}


def at(pid: str, words: str, sentence: str = SENTENCE, **over: Any) -> dict[str, Any]:
    """A part with its words at their place in ``sentence``, offsets in UTF-16 units."""
    head = sentence[: sentence.index(words)]
    start = len(head.encode("utf-16-le")) // 2
    return part(pid, words, start, start + len(words.encode("utf-16-le")) // 2, **over)


PARTS = [at("p1", "café stocks"), at("p2", "over $5")]  # the emoji is 1 code point, 2 units


def body(**over: Any) -> dict[str, Any]:
    return {
        "sentence": SENTENCE, "document": {"criteria": {"c": {"field": "f", "op": "eq"}}},
        "parts": PARTS, "part_id": "p2", "new_words": "over $9", **over,
    }  # fmt: skip


def test_a_request_that_holds_together_is_accepted_with_utf16_offsets_read_as_code_points() -> None:
    req = check_request("s", body())
    assert (req.old_words, req.new_words, req.part.id) == ("over $5", "over $9", "p2")
    assert req.merged == "café stocks 🚀 over $9 and more"
    assert PARTS[1]["start"] == 15 and (PARTS[1]["end"] - PARTS[1]["start"]) == 7
    assert req.spans == {"p1": (0, 11), "p2": (14, 21)}  # code points: the emoji counts one
    assert req.sentence == SENTENCE


def test_the_sentence_and_the_new_words_are_normalised_like_a_description() -> None:
    req = check_request("s", body(new_words="  over\n  $9 "))
    assert req.new_words == "over $9" and req.merged.endswith("over $9 and more")


@pytest.mark.parametrize(
    ("over", "message"),
    [
        ({"sentence": "   "}, "the sentence is empty"),
        ({"sentence": "x" * (MAX_TEXT + 1)}, "the sentence is over 1000"),
        ({"new_words": " \n"}, "the new words are empty"),
        ({"new_words": "x" * 201}, "the new words are over 200"),
        ({"document": None}, "the document has no criteria table"),
        ({"document": {"criteria": [1]}}, "the document has no criteria table"),
        ({"part_id": "p9"}, "has no part 'p9'"),
        ({"parts": [PARTS[0], PARTS[0]]}, "two parts have the same id"),
    ],
)
def test_a_request_that_fails_a_check_is_refused_with_the_check_named(
    over: dict[str, Any], message: str
) -> None:
    with pytest.raises(ConfigurationError, match=message):
        check_request("s", body(**over))


def test_the_sentence_with_the_new_words_in_place_is_at_most_1000_characters() -> None:
    sentence = "word " * 150 + "over $5"  # 757 characters
    parts = [part("p1", "over $5", len(sentence) - 7, len(sentence))]
    ok = check_request("s", body(sentence=sentence, parts=parts, part_id="p1", new_words="x" * 200))
    assert len(ok.merged) == len(sentence) - 7 + 200
    tight = "w" * 900 + " over $5"
    parts = [part("p1", "over $5", len(tight) - 7, len(tight))]
    with pytest.raises(ConfigurationError, match="with the new words is over 1000"):
        check_request("s", body(sentence=tight, parts=parts, part_id="p1", new_words="x" * 200))


@pytest.mark.parametrize(
    ("parts", "message"),
    [
        ([part("p1", "cafe stocks", 0, 11)], "not the sentence's words at its offsets"),
        ([part("p1", "café stocks", 1, 12)], "not the sentence's words at its offsets"),
        ([part("p1", "🚀", 12, 13)], "falls inside a character"),  # the middle of the emoji
        ([part("p1", "more", 40, 44)], "outside the sentence"),
        ([part("p1", "more", -1, 3)], "outside the sentence"),
        ([PARTS[1], PARTS[0]], "overlaps the part before it, or is out of order"),
        ([PARTS[0], at("p2", "stocks 🚀")], "overlaps the part before it, or is out of order"),
        ([part("p1", "", 0, 0)], "has no words"),
        ([part("p1", "café", 0, 4, origin="kept")], "catch-all with words"),
        ([part("kept", "", 0, 0, origin="words")], "has no words, or an origin"),
        ([part("p1", "café", 0, 4, origin="elsewhere")], "an origin it cannot have"),
    ],
)
def test_a_part_whose_words_are_not_the_sentences_own_slice_is_refused(
    parts: list[dict[str, Any]], message: str
) -> None:
    with pytest.raises(ConfigurationError, match=message):
        check_request("s", body(parts=parts, part_id=parts[0]["id"]))


def test_a_catch_all_has_no_words_to_retype() -> None:
    kept = {"id": "kept", "words": "", "start": 0, "end": 0, "origin": "kept"}
    with pytest.raises(ConfigurationError, match="part 'kept' has no words of its own to retype"):
        check_request("s", body(parts=[*PARTS, kept], part_id="kept"))


def test_a_gap_of_words_nobody_covers_can_be_retyped() -> None:
    gap = at("g1", "more", origin="gap", kind="not_understood")
    req = check_request("s", body(parts=[*PARTS, gap], part_id="g1", new_words="even more"))
    assert req.merged.endswith("and even more") and req.part.origin == "gap"


def test_at_most_twelve_parts_with_words() -> None:
    sentence = " ".join(f"w{n:02d}" for n in range(13))
    parts = [part(f"p{n + 1}", f"w{n:02d}", n * 4, n * 4 + 3) for n in range(13)]
    with pytest.raises(ConfigurationError, match="over 12 parts with words"):
        check_request("s", body(sentence=sentence, parts=parts, part_id="p1"))


def test_the_parts_kind_is_decided_again_never_read(ctx: ReadContext) -> None:  # noqa: F811
    prior = held_draft(ctx)
    sent = body_of(prior, "p2", "over $9")
    sent["parts"] = [{**p, "kind": "not_understood"} for p in sent["parts"]]
    req = check_request("my_screen", sent)
    assert req.prior.parts is not None
    assert {p.id: p.kind for p in req.prior.parts}["p2"] == "applied"


def test_a_part_names_only_items_the_draft_holds(ctx: ReadContext) -> None:  # noqa: F811
    prior = held_draft(ctx)
    for group, ref in (
        ("formulas", "draft_nope"), ("unresolved", "nope"), ("missing", "nope"),
        ("suggestions", "s9"), ("dropped", "nope"),
    ):  # fmt: skip
        sent = body_of(prior, "p2", "over $9")
        sent["parts"] = [
            {**p, group: [*p[group], ref]} if p["id"] == "p1" else p for p in sent["parts"]
        ]
        with pytest.raises(ConfigurationError, match=rf"names {group} '{ref}', which the draft"):
            check_request("my_screen", sent)


def test_a_criterion_the_document_no_longer_has_is_not_an_error(ctx: ReadContext) -> None:  # noqa: F811
    prior = held_draft(ctx)
    sent = body_of(prior, "p2", "over $9")
    sent["document"] = {**prior.document, "criteria": {}}  # every row deleted by hand
    assert check_request("my_screen", sent).part.criteria == ("price",)


def test_one_item_belongs_to_one_part(ctx: ReadContext) -> None:  # noqa: F811
    prior = held_draft(ctx)
    sent = body_of(prior, "p2", "over $9")
    sent["parts"] = [{**p, "criteria": ["price"]} if p["id"] == "p1" else p for p in sent["parts"]]
    with pytest.raises(ConfigurationError, match="criteria 'price' belongs to two parts"):
        check_request("my_screen", sent)
    sent = body_of(prior, "p2", "over $9")
    sent["parts"] = [{**p, "rank": True} for p in sent["parts"] if p["id"] in ("p1", "p2")]
    with pytest.raises(ConfigurationError, match="the tie-break belongs to two parts"):
        check_request("my_screen", sent)


def test_an_unresolved_term_whose_default_is_no_reading_is_refused(ctx: ReadContext) -> None:  # noqa: F811
    prior = held_draft(ctx)
    sent = body_of(prior, "p2", "over $9")
    sent["unresolved"] = [{**sent["unresolved"][0], "default_index": 9}]
    with pytest.raises(ConfigurationError, match="default_index is not a reading"):
        check_request("my_screen", sent)


def test_a_criterion_with_no_field_or_op_is_a_400_not_a_key_error() -> None:
    for criterion in ({"op": "eq"}, {"field": "f"}, {"field": 3, "op": "eq"}, "price > 5", None):
        with pytest.raises(ConfigurationError, match="criterion 'c' has no field and op"):
            check_request("s", body(document={"criteria": {"c": criterion}}))


def test_the_document_has_at_most_sixty_criteria() -> None:
    row = {"field": "f", "op": "eq"}
    ok = {f"c{n}": row for n in range(MAX_CRITERIA)}
    check_request("s", body(document={"criteria": ok}))
    with pytest.raises(ConfigurationError, match="over 60 criteria"):
        check_request("s", body(document={"criteria": {**ok, "one_more": row}}))
