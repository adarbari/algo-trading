"""``build_parts``: the model's parts located (a bad one dropped, its items falling back), gaps
as not-understood parts, the kind decided from the refs (needs_choice > formula > not_available >
applied; nothing: not understood), the reading kept only with its numbers, the caps, the
catch-alls, UTF-16 offsets and the stats."""

from algotrade.services.drafting.parts.build import build_parts
from algotrade.services.drafting.parts.model import MAX_READING, MAX_WORDS, Item

SENTENCE = "liquid stocks with IV rank above 50% and no earnings in the next 10 sessions"
PARTS = [
    {"id": "p1", "words": "liquid stocks", "reading": "Stocks trading about $50M a day"},
    {"id": "p2", "words": "IV rank above 50%", "reading": "IV rank of 50% or more"},
    {"id": "p3", "words": "no earnings in the next 10 sessions", "reading": None},
]
ITEMS = [
    Item("criteria", "liquid", "p1", field="f", numbers=(50_000_000.0,)),
    Item("criteria", "iv", "p2", field="f", numbers=(0.5,)),
    Item("missing", "earnings_gap", "p3", span="no earnings"),
]


def build(raw=PARTS, items=ITEMS, sentence=SENTENCE):
    got = build_parts(sentence, raw, items, [])
    assert got is not None
    return {p.id: p for p in got[0]}, got[1]


def test_every_part_carries_the_servers_words_offsets_kind_and_refs() -> None:
    parts, stats = build()
    assert list(parts) == ["p1", "p2", "p3"]
    p2 = parts["p2"]
    assert (p2.words, SENTENCE[p2.start : p2.end]) == ("IV rank above 50%",) * 2
    assert (p2.kind, p2.origin, p2.criteria) == ("applied", "words", ("iv",))
    assert (parts["p3"].kind, parts["p3"].missing) == ("not_available", ("earnings_gap",))
    assert stats.items == 3 and stats.by_model == 3 and stats.by_fallback == 0
    assert (stats.spans, stats.located, stats.not_understood) == (3, 3, 0)


def test_no_parts_from_the_model_is_none_and_so_is_none_located() -> None:
    assert build_parts(SENTENCE, None, ITEMS, []) is None
    assert build_parts(SENTENCE, [], ITEMS, []) is None
    assert build_parts(SENTENCE, [{"id": "p1", "words": "dividend yield"}], ITEMS, []) is None
    assert build_parts(SENTENCE, "nonsense", ITEMS, []) is None


def test_the_kind_follows_the_refs_by_priority_and_suggestions_never_change_it() -> None:
    def kind(*groups: str) -> str:
        items = [Item(g, f"r{n}", "p1") for n, g in enumerate(groups)]
        return build([{"id": "p1", "words": "liquid stocks", "reading": None}], items)[0]["p1"].kind

    assert kind("criteria", "missing", "formulas", "unresolved") == "needs_choice"
    assert kind("criteria", "missing", "formulas") == "formula"
    assert kind("criteria", "missing") == "not_available"
    assert kind("criteria", "dropped") == "not_available"
    assert kind("criteria", "suggestions") == "applied"
    assert kind("rank") == "applied"
    assert kind("suggestions") == "not_understood"  # a suggestion alone understands nothing
    assert kind() == "not_understood"


def test_a_part_that_is_not_found_or_malformed_is_dropped_and_its_items_fall_back() -> None:
    raw = [
        {"id": "p1", "words": "liquid stocks", "reading": None},
        {"id": "p2", "words": "dividend yield", "reading": "Yield"},  # not in the sentence
        {"id": "x9", "words": "no earnings", "reading": None},  # not a part id
        {"id": "p1", "words": "IV rank", "reading": None},  # the id is taken
        {"id": "p3", "words": "  ", "reading": None},
        "junk",
    ]
    items = [Item("criteria", "yield", "p2", span=None, field="f")]
    parts, stats = build(raw, items)
    assert "p2" not in parts
    assert parts["unplaced"].criteria == ("yield",) and parts["unplaced"].words == ""
    assert (parts["unplaced"].start, parts["unplaced"].end) == (0, 0)
    assert stats.spans == 2 and stats.located == 1 and stats.by_model == 0


def test_parts_are_searched_in_order_so_a_reordered_part_is_dropped_not_overlapped() -> None:
    raw = [
        {"id": "p1", "words": "IV rank above 50%", "reading": None},
        {"id": "p2", "words": "liquid stocks", "reading": None},  # before p1: not after it
    ]
    parts, _ = build(raw, [])
    assert [p for p in parts if p.startswith("p")] == ["p1"]


def test_repeated_words_are_located_after_the_previous_part() -> None:
    sentence = "above 50 and then above 50"
    raw = [{"id": "p1", "words": "above 50"}, {"id": "p2", "words": "above 50"}]
    parts, _ = build(raw, [], sentence)
    assert (parts["p1"].start, parts["p2"].start) == (0, 18)


def test_uncovered_words_become_a_not_understood_part_but_connectors_do_not() -> None:
    sentence = "liquid stocks and zzz blorp with IV rank above 50%"
    raw = [{"id": "p1", "words": "liquid stocks"}, {"id": "p2", "words": "IV rank above 50%"}]
    parts, stats = build(raw, [Item("criteria", "a", "p1"), Item("criteria", "b", "p2")], sentence)
    gap = parts["g1"]
    assert (gap.words, gap.kind, gap.origin, gap.reading, gap.reading_source) == (
        "zzz blorp", "not_understood", "gap", None, "server",
    )  # fmt: skip
    assert stats.not_understood == 1
    assert list(parts) == ["p1", "g1", "p2"]  # in sentence order
    assert "g2" not in parts


def test_the_catch_alls_come_last_and_say_where_their_criteria_came_from() -> None:
    items = [*ITEMS, Item("criteria", "old", None, carried=True), Item("criteria", "new", None)]
    parts, stats = build(PARTS, items)
    assert list(parts)[-2:] == ["kept", "unplaced"]
    assert (parts["kept"].origin, parts["kept"].criteria) == ("kept", ("old",))
    assert (parts["unplaced"].origin, parts["unplaced"].criteria) == ("unplaced", ("new",))
    assert stats.by_model == 3 and stats.items == 4  # the kept one has no words to tag


def test_a_reading_with_a_number_the_criteria_lack_is_dropped_by_the_server() -> None:
    raw = [{"id": "p1", "words": "liquid stocks", "reading": "About $80M a day"}]
    parts, stats = build(raw, [Item("criteria", "liquid", "p1", numbers=(50_000_000.0,))])
    assert (parts["p1"].reading, parts["p1"].reading_source) == (None, "server")
    assert (stats.readings, stats.readings_kept) == (1, 0)
    kept, stats = build(PARTS, ITEMS)
    assert (kept["p1"].reading, kept["p1"].reading_source) == (PARTS[0]["reading"], "model")
    assert (stats.readings, stats.readings_kept) == (2, 2)


def test_a_part_with_no_rows_of_its_own_may_repeat_the_numbers_of_its_words() -> None:
    raw = [
        {
            "id": "p3",
            "words": "no earnings in the next 10 sessions",
            "reading": "Ten sessions, 10 days",
        }
    ]
    parts, _ = build(raw, [Item("missing", "m", "p3")])
    assert (
        parts["p3"].reading is not None
    )  # the 10 is in its words; it has no criterion to contradict
    raw = [{"id": "p3", "words": "no earnings in the next 10 sessions", "reading": "Over 20 days"}]
    assert build(raw, [Item("missing", "m", "p3")])[0]["p3"].reading is None


def test_a_reading_of_a_part_nothing_points_at_is_dropped() -> None:
    parts, _ = build([{"id": "p1", "words": "liquid stocks", "reading": "Liquid"}], [])
    assert (parts["p1"].kind, parts["p1"].reading) == ("not_understood", None)


def test_the_caps_words_reading_and_parts() -> None:
    long = " ".join(["word"] * 80)  # 399 characters
    assert build_parts(long, [{"id": "p1", "words": long}], [], []) is None  # over MAX_WORDS
    assert MAX_WORDS == 200
    reading = "Stocks " * 40
    parts, _ = build(
        [{"id": "p1", "words": "liquid stocks", "reading": reading}], [Item("criteria", "a", "p1")]
    )
    assert parts["p1"].reading is not None and len(parts["p1"].reading) <= MAX_READING

    many = " ".join(f"w{n}x" for n in range(30))  # 30 one-word parts
    raw = [{"id": f"p{n}", "words": f"w{n}x"} for n in range(30)]
    got = build_parts(many, raw, [], [])
    assert got is not None
    words_parts = [p for p in got[0] if p.origin != "kept" and p.words]
    assert len(words_parts) <= 12
    assert all(p.kind == "not_understood" for p in words_parts)
    texts = [p.words for p in words_parts]
    assert texts[0] == "w0x"  # nothing is silently lost: the rest is a not-understood gap
    assert any("w29x" in t for t in texts)


def test_offsets_are_utf16_units() -> None:
    sentence = "🚀 liquid stocks"
    parts, _ = build([{"id": "p1", "words": "liquid stocks"}], [], sentence)
    p = parts["p1"]
    assert (p.start, p.end) == (3, 16)  # the rocket is two units and a space
    assert sentence.encode("utf-16-le")[2 * p.start : 2 * p.end].decode("utf-16-le") == p.words
