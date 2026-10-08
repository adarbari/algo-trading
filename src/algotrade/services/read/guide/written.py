"""The Guide's own written pages (ADR 0051), the two kinds whose only source is Guide prose:

- ``GuideTerm``: a glossary term (``config/site/guide/glossary.toml``) by its id: the index's
  entry (id, term, short), the body split at the catalogue names it mentions and its
  ``see_also`` terms as index entries (an id that is no term is left out; a fitness test
  forbids that in the shipped file);
- ``GuideStartPage``: a Start here page (``config/site/guide/start.toml``) by its id: the
  index's entry (id, number, title, summary), its sections with each body linked, and its
  links as Guide references with the entry's title (``search.entry_titles``: the one list of
  the Guide's entries; a reference to no entry is left out, a fitness test forbids that)."""

from dataclasses import dataclass

from algotrade.config.site.guide.glossary import GlossaryTerm, load_guide_glossary
from algotrade.config.site.guide.start import load_guide_start
from algotrade.services.configs import catalog_of
from algotrade.services.read.context import Stores
from algotrade.services.read.guide.index import GuideStartEntry, GuideTermEntry
from algotrade.services.read.guide.prose import LinkedProse, link_prose
from algotrade.services.read.guide.search import entry_titles


@dataclass(frozen=True)
class GuideTerm:
    entry: GuideTermEntry
    body: LinkedProse
    see_also: tuple[GuideTermEntry, ...]


@dataclass(frozen=True)
class GuideStartSection:
    title: str
    body: LinkedProse


@dataclass(frozen=True)
class GuideLink:
    """A Guide entry a page sends the reader on to: ``kind`` (``start.ENTRY_KINDS``), ``id``
    (its page's key) and its ``title``."""

    kind: str
    id: str
    title: str


@dataclass(frozen=True)
class GuideStartPage:
    entry: GuideStartEntry
    sections: tuple[GuideStartSection, ...]
    links: tuple[GuideLink, ...]


def load_guide_term(ctx: Stores, term_id: str) -> GuideTerm | None:
    """The term ``term_id`` names (module docstring); ``None``: no such term."""
    glossary = load_guide_glossary(ctx.configs)
    term = glossary.get(term_id)
    if term is None:
        return None
    others = (glossary.get(other) for other in term.see_also)
    return GuideTerm(
        entry=_term_entry(term),
        body=link_prose(term.body, catalog_of(ctx.features).fields),
        see_also=tuple(_term_entry(t) for t in others if t is not None),
    )


def load_guide_start_page(ctx: Stores, page_id: str) -> GuideStartPage | None:
    """The Start here page ``page_id`` names (module docstring); ``None``: no such page."""
    page = load_guide_start(ctx.configs).get(page_id)
    if page is None:
        return None
    fields = catalog_of(ctx.features).fields
    titles = entry_titles(ctx)
    return GuideStartPage(
        entry=GuideStartEntry(page.id, page.order, page.title, page.summary),
        sections=tuple(
            GuideStartSection(s.title, link_prose(s.body, fields)) for s in page.sections
        ),
        links=tuple(
            GuideLink(link.kind, link.id, titles[(link.kind, link.id)])
            for link in page.links
            if (link.kind, link.id) in titles
        ),
    )


def _term_entry(term: GlossaryTerm) -> GuideTermEntry:
    return GuideTermEntry(term.id, term.term, term.short)
