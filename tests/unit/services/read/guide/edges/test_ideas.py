"""``not_built``: the ideas researched but not built, from the Guide's idea files; an idea filed as
an edge is not shown; each is grouped under its mechanism."""

from algotrade.config.edges.document import MECHANISM_KINDS
from algotrade.config.site.guide.glossary import load_guide_glossary
from algotrade.config.site.guide.ideas import IDEA_VERDICTS, load_guide_ideas
from algotrade.services.read.context import StoreContext
from algotrade.services.read.guide.edges.ideas import (
    FEASIBILITY_TERM,
    VERDICT_TEXT,
    ideas_of,
    not_built,
)
from algotrade.services.read.guide.edges.mechanism import load_guide_mechanism


def test_only_the_ideas_no_edge_files_are_shown(site: StoreContext) -> None:
    ideas = load_guide_ideas(site.configs)
    shown = {i.id for i in not_built(site)}
    assert shown == {i.id for i in ideas.unfiled}
    assert not shown & {i.id for i in ideas.ideas if i.filed_as is not None}
    assert len(shown) > 100


def test_the_ideas_come_in_the_mechanism_order(site: StoreContext) -> None:
    found = not_built(site)
    ranks = [MECHANISM_KINDS.index(i.mechanism) for i in found]
    assert ranks == sorted(ranks)  # the catalogue's own order is kept within a mechanism


def test_each_mechanism_page_lists_its_own_ideas(site: StoreContext) -> None:
    listed = 0
    for kind in MECHANISM_KINDS:
        page = load_guide_mechanism(site, kind)
        assert page is not None
        assert {i.mechanism for i in page.not_built} <= {kind}
        assert page.not_built == ideas_of(site, kind)
        listed += len(page.not_built)
    assert listed == len(not_built(site))


def test_an_idea_has_its_grade_feasibility_and_one_reason(site: StoreContext) -> None:
    terms = {t.id for t in load_guide_glossary(site.configs).terms}
    for i in not_built(site):
        assert i.verdict in IDEA_VERDICTS and i.verdict_text == VERDICT_TEXT[i.verdict]
        assert i.feasibility_text and i.why_not_built and i.title
        assert i.feasibility_term == FEASIBILITY_TERM and FEASIBILITY_TERM in terms
