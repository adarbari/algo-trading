"""``GuideEdgeEntry`` (ADR 0051; spec ``docs/ui/guide.md``, "Edges"): one site edge's Guide page,
read from the edge document alone, session-free and with no harness result. In the page's order:

- ``summary``: the edge as a row (``GuideEdgeRow``: name, thesis, asset, side, holding, status);
  ``mechanism``: its mechanism page (id, title);
- ``other_side`` (the document's ``mechanism`` text: who is on the other side) and ``lasts``
  (its ``persistence``: why it lasts), split at the catalogue names they mention;
- ``research``: the ``[published]`` figure with the planning haircut of ``verdict.toml``
  ``[published_haircut]`` for its leg, only where the document has one; display only, never a
  verdict;
- ``tests``: how we test it, as structured facts (outcome, horizon, trigger, entry, universe,
  picks, cost, baselines, frozen period), each with the glossary term that explains it;
- ``screeners`` and ``fields``: how it is built (the site screeners among its screeners and the
  catalogue fields their criteria read);
- ``failure_modes``, ``decoys`` and ``rejection``: what fools it (the quality bar's answers
  and, for a rejected or blocked edge, why);
- ``capacity``: can you trade it (the quality bar's capacity and costs answer);
- ``sources`` (the document's, with a form derived from the url or title) and ``related``:
  other edges that share a screener, then the mechanism's, and the mechanism's glossary terms.

Never read: the document's ``notes``, ``expected_size`` answer, ``[evidence]``, ``[implementation]``
or ``[audit]``; nothing here comes from a run (a fitness test)."""

import re
from dataclasses import dataclass

from algotrade.config.edges.document import Edge, Outcome, Published
from algotrade.config.edges.portfolio import benchmark_words
from algotrade.config.edges.verdict import VerdictSettings
from algotrade.config.site.guide.glossary import load_guide_glossary
from algotrade.config.site.guide.mechanisms import load_guide_mechanisms
from algotrade.config.site.guide.sections import load_guide_sections
from algotrade.config.site.settings import site_document
from algotrade.services.configs import catalog_of
from algotrade.services.read.context import Stores
from algotrade.services.read.guide.edges.schedule import trigger_term
from algotrade.services.read.guide.edges.site_edges import SiteEdge, screeners_of, site_edges
from algotrade.services.read.guide.edges.universe import universe_text
from algotrade.services.read.guide.prose import LinkedProse, link_prose

ASSET_TEXT = {"stocks": "Stocks", "etfs": "ETFs and funds", "options": "Options"}
SIDE_TERMS = {"long": "side_long", "short": "side_short", "long_short": "side_long_short"}
MAX_RELATED = 6
GATE_PREFIX = "instrument."  # identity gates (type, status): every screen has them, so not listed
HAIRCUT_NAME = "planning haircut"
MEASURE_WORDS = {
    "mean_excess": "Average return above the benchmark, per pick",
    "decile_spread": "Best tenth of names minus the worst tenth",
    "lift_pts": "Hit rate above the base rate, in points",
}
LEG_WORDS = {"long": "long side", "short": "short side", "long_short": "long-short spread"}
OUTCOME_WORDS = {
    "expires_otm": "A short option that expires out of the money",
    "option_model_pnl": "Modelled profit on an option position",
    "option_pnl": "Profit on an option position, from stored quotes",
    "pair_spread": "The cheap share class against its sibling",
}
FORMS = (  # (found in the url or title, form), first match wins
    ("ssrn.com", "Working paper"),
    ("nber.org", "Working paper"),
    ("sec.gov", "Filing"),
    ("Working Paper", "Working paper"),
    ("Journal", "Paper"),
    ("Review", "Paper"),
    ("Quarterly", "Paper"),
)


@dataclass(frozen=True)
class GuideMechanismRef:
    """A mechanism page by its id and title."""

    id: str
    title: str


@dataclass(frozen=True)
class GuideEdgeRow:
    """An edge in a list: ``asset`` (``universe.ASSETS``) and ``asset_text``, ``side`` with its
    glossary term, ``holding_sessions`` with ``holding_text`` and ``holding_band``
    (``schedule.BANDS``), ``status`` (``document.STATUSES``) and ``mechanism`` (its id)."""

    id: str
    name: str
    thesis: str
    mechanism: str | None
    asset: str
    asset_text: str
    side: str
    side_term: str
    holding_sessions: tuple[int, ...]
    holding_text: str
    holding_band: str
    status: str


@dataclass(frozen=True)
class GuideEdgeResearch:
    """What the paper behind the edge reports: ``measure`` in words, the published ``figure``
    and what to ``expect`` once ``haircut`` of it is lost (the planning haircut of its leg),
    over ``horizon_text`` on the ``leg``, from ``source`` (a title; the sample, in years, when
    stated). Display only."""

    measure: str
    figure: str
    expect: str
    haircut: str
    horizon_text: str
    leg: str
    sample: str | None
    source: str
    terms: tuple[str, ...]


@dataclass(frozen=True)
class GuideEdgeFact:
    """One line of how the edge is tested: ``key`` (``FACTS``), its ``title``, the ``text`` and
    the glossary ``term`` that explains it (``None``: none)."""

    key: str
    title: str
    text: str
    term: str | None


@dataclass(frozen=True)
class GuideEdgeScreener:
    """A site screener an edge's screeners include: its id, name and family title."""

    id: str
    name: str
    family: str | None


@dataclass(frozen=True)
class GuideEdgeSource:
    """A source of the document: ``title``, ``url`` (``None``: none) and its ``form``."""

    title: str
    url: str | None
    form: str


@dataclass(frozen=True)
class GuideEdgeEntry:
    summary: GuideEdgeRow
    mechanism: GuideMechanismRef | None
    thesis: LinkedProse
    other_side: LinkedProse
    lasts: LinkedProse
    research: GuideEdgeResearch | None
    tests: tuple[GuideEdgeFact, ...]
    screeners: tuple[GuideEdgeScreener, ...]
    fields: tuple[str, ...]
    failure_modes: LinkedProse | None
    decoys: LinkedProse | None
    rejection: LinkedProse | None
    capacity: LinkedProse | None
    sources: tuple[GuideEdgeSource, ...]
    related: tuple[GuideEdgeRow, ...]
    see_also: tuple[str, ...]


def edge_row(e: SiteEdge) -> GuideEdgeRow:
    """``e`` as a list row."""
    return GuideEdgeRow(
        id=e.edge.id,
        name=e.edge.name,
        thesis=e.edge.thesis,
        mechanism=e.mechanism,
        asset=e.asset,
        asset_text=ASSET_TEXT[e.asset],
        side=e.side,
        side_term=SIDE_TERMS[e.side],
        holding_sessions=e.holding,
        holding_text=e.holding_text,
        holding_band=e.band,
        status=e.edge.status,
    )


def load_guide_edge(ctx: Stores, edge_id: str) -> GuideEdgeEntry | None:
    """The site edge ``edge_id`` (module docstring); ``None``: no such site edge."""
    edges = site_edges(ctx)
    found = next((e for e in edges if e.edge.id == edge_id), None)
    if found is None:
        return None
    edge = found.edge
    fields = catalog_of(ctx.features).fields
    terms = {t.id for t in load_guide_glossary(ctx.configs).terms}
    mechanisms = load_guide_mechanisms(ctx.configs)
    prose = mechanisms.get(found.mechanism) if found.mechanism is not None else None
    screeners = {p.id: p for p in screeners_of(ctx)}
    titles = {f.id: f.title for f in load_guide_sections(ctx.configs).families}
    mine = [screeners[p] for p in found.screeners]

    def linked(text: str) -> LinkedProse | None:
        return link_prose(text, fields) if text.strip() else None

    return GuideEdgeEntry(
        summary=edge_row(found),
        mechanism=GuideMechanismRef(prose.id, prose.title) if prose is not None else None,
        thesis=link_prose(edge.thesis, fields),
        other_side=link_prose(edge.mechanism, fields),
        lasts=link_prose(edge.persistence, fields),
        research=_research(ctx, edge, terms),
        tests=_tests(found, edge, terms, {p.id: p.name for p in screeners.values()}),
        screeners=tuple(
            GuideEdgeScreener(p.id, p.name, titles.get(p.family) if p.family else None)
            for p in mine
        ),
        fields=tuple(
            dict.fromkeys(
                c.field
                for p in mine
                for c in p.spec.criteria
                if c.field in fields and not c.field.startswith(GATE_PREFIX)
            )
        ),
        failure_modes=linked(edge.quality_bar.get("failure_modes", "")),
        decoys=linked(edge.quality_bar.get("decoys", "")),
        rejection=linked(edge.plain_reason),
        capacity=linked(edge.quality_bar.get("capacity_costs", "")),
        sources=tuple(_source(s.title, s.url) for s in edge.sources),
        related=tuple(edge_row(e) for e in _related(found, edges)),
        see_also=tuple(t for t in (prose.see_also if prose is not None else ()) if t in terms),
    )


def _related(found: SiteEdge, edges: tuple[SiteEdge, ...]) -> tuple[SiteEdge, ...]:
    """Edges sharing a screener with ``found``, then the others of its mechanism."""
    others = [e for e in edges if e.edge.id != found.edge.id]
    shared = [e for e in others if set(e.edge.screeners) & set(found.edge.screeners)]
    same = [e for e in others if e.mechanism == found.mechanism and e not in shared]
    return tuple((*shared, *(same if found.mechanism is not None else ()))[:MAX_RELATED])


def _research(ctx: Stores, edge: Edge, terms: set[str]) -> GuideEdgeResearch | None:
    p = edge.published
    if p is None:
        return None
    settings = VerdictSettings.from_document(site_document(ctx.configs.load, "verdict"))
    cut = settings.published_haircut(p.leg)
    return GuideEdgeResearch(
        measure=MEASURE_WORDS[p.measure],
        figure=_shown(p),
        expect=_shown(p, 1.0 - cut),
        haircut=f"{cut * 100:.0f}% {HAIRCUT_NAME}",
        horizon_text=f"over {p.horizon_sessions} session"
        + ("" if p.horizon_sessions == 1 else "s"),
        leg=LEG_WORDS.get(p.leg, p.leg.replace("_", "-")),
        sample=(f"{p.sample} year" + ("" if p.sample == 1 else "s")) if p.sample else None,
        source=edge.sources[p.source].title,
        terms=tuple(t for t in ("published_number", "published_haircut") if t in terms),
    )


def _shown(p: Published, keep: float = 1.0) -> str:
    value = p.value * keep
    return f"{value:.1f} points" if p.measure == "lift_pts" else f"{value * 100:.2f}%"


def _source(title: str, url: str) -> GuideEdgeSource:
    where = f"{url} {title}"
    form = next((form for needle, form in FORMS if needle.lower() in where.lower()), "Source")
    return GuideEdgeSource(title, url or None, form)


def _tests(
    found: SiteEdge, edge: Edge, terms: set[str], names: dict[str, str]
) -> tuple[GuideEdgeFact, ...]:
    o = edge.outcome
    event = edge.event_class is not None
    n = o.start_offset_sessions
    anchor = "event" if event else "decision session"
    sessions = f"{abs(n)} session{'' if abs(n) == 1 else 's'}"
    entry = (
        f"At the close of the {anchor}"
        if n == 0
        else f"At the close {sessions} {'after' if n > 0 else 'before'} the {anchor}"
    )
    facts = [
        ("outcome", "What counts as working", _outcome_text(o), f"outcome_{o.kind}"),
        ("horizon", "How long it is held", found.holding_text, None),
        ("trigger", "What sets it off", found.trigger, trigger_term(edge.schedule, terms)),
        ("entry", "When it enters", entry, None),
        ("universe", "Who it trades", universe_text(found.universe), "selection"),
        ("picks", "Which names it picks", _picks_text(edge), None),
        *(
            [("cost", "Cost assumed", f"{o.cost_bps:g} basis points per round trip", None)]
            if o.cost_bps is not None
            else []
        ),
        *(
            [("baselines", "What it is compared with", _names(edge.baselines, names), "baselines")]
            if edge.baselines
            else []
        ),
        *(
            [("frozen", "Out of sample from", edge.frozen_from.isoformat(), "out_of_sample")]
            if edge.frozen_from is not None
            else []
        ),
    ]
    return tuple(
        GuideEdgeFact(k, t, text, term if term in terms else None) for k, t, text, term in facts
    )


def _outcome_text(o: Outcome) -> str:
    if o.kind == "excess_return":
        return (
            "Raw return"
            if o.benchmark == "none"
            else f"Return above {benchmark_words(o.benchmark)}"
        )
    if o.kind == "portfolio_return":
        return f"A book's return against {benchmark_words(o.benchmark)}"
    if o.kind == "hit_target":
        measure = (o.measure or "return").replace("_", " ")
        return f"Hit when the {measure} is {o.direction} {o.target:g}"
    return OUTCOME_WORDS.get(o.kind, o.kind.replace("_", " ").capitalize())


def _picks_text(edge: Edge) -> str:
    head = "Every name that passes" if edge.top_k is None else f"The top {edge.top_k} names"
    if edge.outcome.kind == "portfolio_return" and edge.outcome.weighting != "equal":
        head += f", weighted by {edge.outcome.weighting.replace('_', ' ')}"
    if edge.ensemble:
        head += f", averaged over {len(edge.ensemble)} screens"
    return head


def _names(ids: tuple[str, ...], names: dict[str, str]) -> str:
    return ", ".join(names.get(i) or re.sub(r"_+", " ", i) for i in ids)
