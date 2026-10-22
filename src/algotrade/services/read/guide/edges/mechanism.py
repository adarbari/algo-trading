"""``GuideMechanism`` (ADR 0051; spec ``docs/ui/guide.md``, "Edges"): one mechanism's page, the
reason an edge should work (``config/site/guide/mechanisms/<id>.toml``, ``MechanismProse``)
with the site edges that rest on it as rows (``GuideEdgeRow``, in Guide order, every status:
the row says which are candidates and which are set aside) and the ideas researched but not
built that would rest on it (``not_built``, ``ideas.py``). Its paragraphs are split at the
catalogue names they mention, its ``see_also`` are the glossary terms that exist, and its
stats and sources are as written (a stat's ``source`` indexes ``sources``, 1-based; ``None``:
our own bar). Session-free; ``None`` for an id that is no mechanism."""

from dataclasses import dataclass

from algotrade.config.site.guide.glossary import load_guide_glossary
from algotrade.config.site.guide.mechanisms import MechanismProse, load_guide_mechanisms
from algotrade.services.configs import field_catalog
from algotrade.services.read.context import Stores
from algotrade.services.read.guide.edges.edge import GuideEdgeRow, edge_row
from algotrade.services.read.guide.edges.ideas import GuideIdea, ideas_of
from algotrade.services.read.guide.edges.site_edges import site_edges
from algotrade.services.read.guide.prose import LinkedProse, link_prose


@dataclass(frozen=True)
class GuideMechanismStat:
    """A tile: ``title``, ``value`` as shown, ``reading`` and ``source`` (1-based index into the
    page's sources; ``None``: our own bar from ``verdict.toml``)."""

    title: str
    value: str
    reading: str
    source: int | None


@dataclass(frozen=True)
class GuideMechanismSource:
    """A source: the citation ``title``, its https ``url`` and ``reading`` (what it shows)."""

    title: str
    url: str
    reading: str


@dataclass(frozen=True)
class GuideMechanism:
    id: str
    title: str
    question: str
    examples: str
    short: str
    how_it_works: tuple[LinkedProse, ...]
    why_it_survives: tuple[LinkedProse, ...]
    research: tuple[LinkedProse, ...]
    real_vs_decoy: tuple[LinkedProse, ...]
    dont: LinkedProse
    see_also: tuple[str, ...]
    stats: tuple[GuideMechanismStat, ...]
    sources: tuple[GuideMechanismSource, ...]
    edges: tuple[GuideEdgeRow, ...]
    not_built: tuple[GuideIdea, ...]


def load_guide_mechanism(ctx: Stores, mechanism_id: str) -> GuideMechanism | None:
    """The mechanism page ``mechanism_id`` names (module docstring), built once per cache
    (site files only); an unknown id (``None``) is never cached, so the key space stays the
    mechanisms'."""
    key = ("guide-mechanism", mechanism_id)
    return ctx.cache.get_or_compute(key, lambda: _mechanism(ctx, mechanism_id))  # type: ignore[no-any-return]


def _mechanism(ctx: Stores, mechanism_id: str) -> GuideMechanism | None:
    prose = load_guide_mechanisms(ctx.configs).get(mechanism_id)
    return mechanism_of(ctx, prose) if prose is not None else None


def mechanism_of(ctx: Stores, prose: MechanismProse) -> GuideMechanism:
    """``prose`` with its edges and linked text."""
    fields = field_catalog(ctx.configs).fields
    terms = {t.id for t in load_guide_glossary(ctx.configs).terms}

    def linked(texts: tuple[str, ...]) -> tuple[LinkedProse, ...]:
        return tuple(link_prose(t, fields) for t in texts)

    return GuideMechanism(
        id=prose.id,
        title=prose.title,
        question=prose.question,
        examples=prose.examples,
        short=prose.short,
        how_it_works=linked(prose.how_it_works),
        why_it_survives=linked(prose.why_it_survives),
        research=linked(prose.research),
        real_vs_decoy=linked(prose.real_vs_decoy),
        dont=link_prose(prose.dont, fields),
        see_also=tuple(t for t in prose.see_also if t in terms),
        stats=tuple(GuideMechanismStat(s.label, s.value, s.note, s.source) for s in prose.stats),
        sources=tuple(GuideMechanismSource(s.title, s.url, s.note) for s in prose.sources),
        edges=tuple(edge_row(e) for e in site_edges(ctx) if e.mechanism == prose.id),
        not_built=ideas_of(ctx, prose.id),
    )
