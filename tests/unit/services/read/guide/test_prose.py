"""``link_prose``: text split at the catalogue names it mentions, exactly as written and only
names the caller's catalogue holds; a trailing dot is the sentence's; the segments join back
to the text. ``mentions`` lists the names in order."""

from algotrade.services.read.guide.prose import (
    LinkedProse,
    ProseSegment,
    link_prose,
    mentions,
    name_tokens,
)

ATR = "feature.atr_pct"
REL = "rollup.momentum@v1.rel_volume"
NAMES = {ATR, REL, "instrument.symbol"}


def test_names_are_split_out_in_order() -> None:
    text = f"Compare {REL} with {ATR}, then {ATR}."
    linked = link_prose(text, NAMES)
    assert linked.segments == (
        ProseSegment("Compare "),
        ProseSegment(REL, REL),
        ProseSegment(" with "),
        ProseSegment(ATR, ATR),
        ProseSegment(", then "),
        ProseSegment(ATR, ATR),
        ProseSegment("."),  # the sentence's dot, not the name's
    )
    assert "".join(s.text for s in linked.segments) == text
    assert linked.fields == (REL, ATR, ATR)


def test_only_catalogue_names_written_in_full_are_linked() -> None:
    text = "Not rollup.nope@v1.x, not rel_volume, not momentum@v1.rel_volume, not 0.005 or e.g."
    assert link_prose(text, NAMES) == LinkedProse(text, (ProseSegment(text),))
    # A longer token is not a name it contains.
    assert link_prose(f"{ATR}_x", NAMES).fields == ()


def test_text_that_is_one_name_or_empty() -> None:
    assert link_prose(ATR, NAMES).segments == (ProseSegment(ATR, ATR),)
    assert link_prose("", NAMES) == LinkedProse("", ())


def test_mentions_across_texts() -> None:
    assert mentions([f"{ATR} and {REL}.", "instrument.symbol"], NAMES) == [
        ATR, REL, "instrument.symbol",
    ]  # fmt: skip


def test_name_tokens_are_dotted_words_without_the_sentence_dot() -> None:
    text = f"Check {ATR}. Then {REL}, not rel_volume or e.g. 0.005."
    assert name_tokens(text) == [ATR, REL, "e.g", "0.005"]


def test_a_marker_is_its_own_segment_when_the_page_has_sources() -> None:
    text = f"Quiet weeks lift {ATR}.[^2] Winners persist.[^1][^3]"
    linked = link_prose(text, NAMES, sources=3)
    assert linked.segments == (
        ProseSegment("Quiet weeks lift "),
        ProseSegment(ATR, ATR),
        ProseSegment("."),
        ProseSegment("[^2]", source=2),
        ProseSegment(" Winners persist."),
        ProseSegment("[^1]", source=1),
        ProseSegment("[^3]", source=3),
    )
    assert "".join(s.text for s in linked.segments) == text  # the segments join back
    assert linked.sources == (2, 1, 3) and linked.fields == (ATR,)


def test_a_marker_outside_the_sources_or_on_a_page_without_any_stays_text() -> None:
    text = "Winners persist.[^4] And again.[^1]"
    assert link_prose(text, NAMES).segments == (ProseSegment(text),)  # no count: plain text
    two = link_prose(text, NAMES, sources=2)
    assert two.sources == (1,) and two.segments[0] == ProseSegment(
        "Winners persist.[^4] And again."
    )
    assert link_prose("No marker.", NAMES, sources=2) == LinkedProse(
        "No marker.", (ProseSegment("No marker."),)
    )
