"""``load_guide_term`` and ``load_guide_start_page``: a term with its body linked and its
see-also terms (an unknown id left out), a Start here page with its sections linked and its
links titled (a link to no entry left out); ``None`` for an unknown id; the shipped files."""

from algotrade.services.read.context import StoreContext
from algotrade.services.read.guide.index import GuideStartEntry, GuideTermEntry
from algotrade.services.read.guide.written import (
    GuideLink,
    load_guide_start_page,
    load_guide_term,
)
from tests.unit.services.read.guide.conftest import ADV, DOCUMENTS, stores

GLOSSARY = {
    "term": [
        {"id": "near_miss", "term": "Near miss", "short": "Close.",
         "body": f"Within tolerance; see {ADV}.", "see_also": ["tolerance", "gone"]},
        {"id": "tolerance", "term": "tolerance", "short": "How far.", "body": "A band."},
    ]
}  # fmt: skip
START = {
    "page": [
        {
            "id": "build",
            "order": 1,
            "title": "Build a screen",
            "summary": "Step by step.",
            "section": [{"title": "Gate", "body": f"Gate on {ADV} first."}],
            "links": [
                {"kind": "term", "id": "near_miss"},
                {"kind": "playbook", "id": "alpha"},
                {"kind": "field", "id": ADV},
                {"kind": "situation", "id": "no-such-situation"},
            ],
        }
    ]
}
WRITTEN = {
    **DOCUMENTS,
    ("site", "guide", "glossary"): GLOSSARY,
    ("site", "guide", "start"): START,
}


def test_a_term_page() -> None:
    term = load_guide_term(stores(WRITTEN), "near_miss")
    assert term is not None
    assert term.entry == GuideTermEntry("near_miss", "Near miss", "Close.")
    assert term.body.fields == (ADV,)
    assert term.see_also == (GuideTermEntry("tolerance", "tolerance", "How far."),)  # no "gone"
    assert load_guide_term(stores(WRITTEN), "Near miss") is None


def test_a_start_page() -> None:
    page = load_guide_start_page(stores(WRITTEN), "build")
    assert page is not None
    assert page.entry == GuideStartEntry("build", 1, "Build a screen", "Step by step.")
    (section,) = page.sections
    assert section.title == "Gate" and section.body.fields == (ADV,)
    assert page.links == (
        GuideLink("term", "near_miss", "Near miss"),
        GuideLink("playbook", "alpha", "Alpha"),
        GuideLink("field", ADV, ADV),
    )  # the unknown situation is left out
    assert load_guide_start_page(stores(WRITTEN), "nope") is None


def test_the_shipped_pages(site: StoreContext) -> None:
    term = load_guide_term(site, "liquidity_risk")
    assert term is not None and ADV in term.body.fields and term.see_also
    page = load_guide_start_page(site, "read_the_regime_page")
    assert page is not None and page.entry.order == 5
    assert ("indicator", "curve_10y3m") in {(link.kind, link.id) for link in page.links}
    assert all(link.title for link in page.links)
