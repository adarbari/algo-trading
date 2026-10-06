"""``config/site/regime/terms.py``: a how-line split into plain and linked parts, each term
once as a whole phrase, a shorter term inside a longer one not counted, overlaps refused."""

import pytest

from algotrade.config.site.regime.terms import Term, TextPart, https, split
from algotrade.core.model.errors import ConfigurationError

VIX, VIX3M = Term("VIX", "https://a.org/vix"), Term("three-month VIX", "https://a.org/vix3m")


def test_terms_are_linked_where_they_occur_in_order() -> None:
    parts = split("The VIX over the three-month VIX.", (VIX, VIX3M), "card")
    assert parts == (
        TextPart("The "),
        TextPart("VIX", VIX.url),
        TextPart(" over the "),
        TextPart("three-month VIX", VIX3M.url),
        TextPart("."),
    )
    assert split("VIX", (VIX,), "card") == (TextPart("VIX", VIX.url),)
    assert split("No terms.", (), "card") == (TextPart("No terms."),)


@pytest.mark.parametrize(
    ("sentence", "terms", "message"),
    [
        ("The VIX and the VIX.", (VIX,), r"'VIX' must occur exactly once in how, found 2"),
        ("The VIX3M.", (VIX,), r"'VIX' must occur exactly once in how, found 0"),
        ("The three-month VIX.", (VIX, VIX3M), r"'VIX' must occur exactly once in how, found 0"),
        (
            "a b c",
            (Term("a b", "https://x.org"), Term("b c", "https://y.org")),
            r"'b c' overlaps 'a b'",
        ),
        ("The VIX.", (VIX, Term("VIX", "https://b.org")), r"declared more than once: \['VIX'\]"),
    ],
)
def test_bad_terms_fail_naming_the_card(
    sentence: str, terms: tuple[Term, ...], message: str
) -> None:
    with pytest.raises(ConfigurationError, match=f"card terms: {message}"):
        split(sentence, terms, "card")


def test_links_are_https() -> None:
    assert https("https://a.org/x", "w") == "https://a.org/x"
    for bad in ("http://a.org/x", "https://", "a.org"):
        with pytest.raises(ConfigurationError, match="w: expected an https URL"):
            https(bad, "w")
