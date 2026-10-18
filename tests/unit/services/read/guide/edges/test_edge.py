"""``GuideEdgeEntry``: every site edge's page loads, from the document alone; the published
figure carries its planning haircut only where the document has one; no harness result, note
or expected size reaches the page."""

import dataclasses
from typing import Any

from algotrade.config.edges.verdict import VerdictSettings
from algotrade.config.site.settings import site_document
from algotrade.services.read.context import StoreContext
from algotrade.services.read.guide.edges.edge import GuideEdgeEntry, load_guide_edge
from algotrade.services.read.guide.edges.site_edges import site_edges
from tests.unit.services.read.guide.edges.conftest import DRAFT_ID

# What a harness run or a document's private fields would be called: none is on the page.
FORBIDDEN = (
    "verdict", "win_rate", "hit_rate", "base_rate", "lift", "curve", "run_id", "expected_size",
    "notes", "evidence", "implementation", "audit", "sharpe", "decile",
)  # fmt: skip


def _field_names(cls: type) -> set[str]:
    """Every field name of the dataclass ``cls`` and of the dataclasses its fields name."""
    found: set[str] = set()
    for f in dataclasses.fields(cls):
        found.add(f.name)
        for inner in _dataclasses_in(f.type):
            found |= _field_names(inner)
    return found


def _dataclasses_in(annotation: Any) -> list[type]:
    if isinstance(annotation, type) and dataclasses.is_dataclass(annotation):
        return [annotation]
    args = getattr(annotation, "__args__", ())
    return [d for a in args for d in _dataclasses_in(a)]


def test_every_site_edge_has_a_page(site: StoreContext) -> None:
    for e in site_edges(site):
        page = load_guide_edge(site, e.edge.id)
        assert page is not None, e.edge.id
        assert page.summary.id == e.edge.id
        assert page.mechanism is not None and page.mechanism.id == e.mechanism
        assert page.other_side.text and page.lasts.text and page.tests
        assert {f.key for f in page.tests} >= {"outcome", "horizon", "trigger", "universe"}


def test_no_such_edge_and_no_users_edge(site: StoreContext, with_draft: StoreContext) -> None:
    assert load_guide_edge(site, "nope") is None
    assert load_guide_edge(with_draft, DRAFT_ID) is None


def test_the_page_carries_no_harness_result_or_private_field() -> None:
    names = _field_names(GuideEdgeEntry)
    assert [n for n in names if any(word in n for word in FORBIDDEN)] == []


def test_the_published_figure_has_its_leg_haircut(site: StoreContext) -> None:
    settings = VerdictSettings.from_document(site_document(site.configs.load, "verdict"))
    with_figure = []
    for e in site_edges(site):
        page = load_guide_edge(site, e.edge.id)
        assert page is not None
        if e.edge.published is None:
            assert page.research is None, e.edge.id
            continue
        with_figure.append(e.edge.id)
        cut = settings.published_haircut(e.edge.published.leg)
        research = page.research
        assert research is not None
        assert research.haircut == f"{cut * 100:.0f}% planning haircut"
        assert research.source == e.edge.sources[e.edge.published.source].title
    assert "momentum_12_1" in with_figure


def test_the_haircut_is_taken_off_the_figure(site: StoreContext) -> None:
    page = load_guide_edge(site, "momentum_12_1")
    assert page is not None and page.research is not None
    published = next(e.edge.published for e in site_edges(site) if e.edge.id == "momentum_12_1")
    assert published is not None
    assert page.research.figure == f"{published.value * 100:.2f}%"
    assert page.research.expect == f"{published.value * 0.5 * 100:.2f}%"  # a long-short figure
    assert page.research.terms == ("published_number", "published_haircut")


def test_the_notes_and_the_expected_size_are_not_shown(site: StoreContext) -> None:
    for e in site_edges(site):
        page = load_guide_edge(site, e.edge.id)
        assert page is not None
        shown = " ".join(
            p.text
            for p in (page.thesis, page.other_side, page.lasts, page.failure_modes, page.decoys,
                      page.rejection, page.capacity)
            if p is not None
        )  # fmt: skip
        for private in (e.edge.notes, e.edge.quality_bar.get("expected_size", "")):
            if len(private) > 80:
                assert private[:80] not in shown, e.edge.id


def test_a_closed_edge_says_why(site: StoreContext) -> None:
    closed = [e for e in site_edges(site) if e.edge.status in ("rejected", "blocked")]
    assert closed
    for e in closed:
        page = load_guide_edge(site, e.edge.id)
        assert page is not None and page.rejection is not None, e.edge.id
    open_ = next(e for e in site_edges(site) if e.edge.status == "candidate")
    page = load_guide_edge(site, open_.edge.id)
    assert page is not None and page.rejection is None


def test_how_it_is_built_links_the_playbooks_and_their_fields(site: StoreContext) -> None:
    page = load_guide_edge(site, "momentum_12_1")
    assert page is not None
    assert page.playbooks[0].id == "momentum_12_1"
    assert page.playbooks[0].family
    assert page.fields and not any(f.startswith("instrument.") for f in page.fields)
    assert len(set(page.fields)) == len(page.fields)


def test_related_edges_exclude_the_edge_and_are_site_edges(site: StoreContext) -> None:
    ids = {e.edge.id for e in site_edges(site)}
    for e in site_edges(site):
        page = load_guide_edge(site, e.edge.id)
        assert page is not None
        related = [r.id for r in page.related]
        assert e.edge.id not in related and set(related) <= ids and len(related) <= 6


def test_sources_have_a_form(site: StoreContext) -> None:
    page = load_guide_edge(site, "momentum_12_1")
    assert page is not None and page.sources
    assert {s.form for s in page.sources} <= {"Paper", "Working paper", "Filing", "Source"}
    assert all(s.url is None or s.url.startswith("http") for s in page.sources)
