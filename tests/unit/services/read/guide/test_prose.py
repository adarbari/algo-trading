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
