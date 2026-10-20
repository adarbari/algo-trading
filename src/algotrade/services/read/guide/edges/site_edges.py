"""The site's edges as the Guide reads them (ADR 0051; spec ``docs/ui/guide.md``, "Edges"):
every edge document of ``config/site/edges/`` through ``config.edges.loading.load_edges`` as the
``site`` user, so a user's draft or copy never appears, each with what the Guide derives from
the document alone: its asset-class tag (``universe.asset_of``), side (the outcome's, ``long``,
``short`` or ``long_short``), holding sessions, band and plain trigger text (``schedule``) and
the links between an edge and the site screeners that implement it (an edge's ``screeners``
that are site screeners, and the other way round). In Guide order: name, then id.

Session-free: this folder reads documents and configs only, never ``ctx.session``, a store, the
evaluation read model or an outcome (a fitness test); the Guide shows no harness result."""

from dataclasses import dataclass

from algotrade.config.edges.document import Edge
from algotrade.config.edges.loading import load_edges
from algotrade.config.user import SITE_USER
from algotrade.services.read.context import Stores
from algotrade.services.read.guide.edges.schedule import holding_band, holding_text, trigger_text
from algotrade.services.read.guide.edges.universe import Universe, asset_of, universe_of
from algotrade.services.read.guide.screeners.site_screeners import SiteScreener, site_screeners


@dataclass(frozen=True)
class SiteEdge:
    """One site edge with the tags the Guide derives: ``mechanism`` (its ``mechanism_kind``;
    ``None``: a document that omits it), ``asset`` (``universe.ASSETS``), ``side``,
    ``holding`` (the outcome's horizons in sessions), ``band`` (``schedule.BANDS``),
    ``holding_text``, ``trigger`` (plain text) and ``screeners`` (the ids of its screeners that
    are site screeners, in the document's order)."""

    edge: Edge
    universe: Universe
    mechanism: str | None
    asset: str
    side: str
    holding: tuple[int, ...]
    band: str
    holding_text: str
    trigger: str
    screeners: tuple[str, ...]


def screeners_of(ctx: Stores) -> tuple[SiteScreener, ...]:
    """The site screeners (``guide.screeners``), shared across requests like ``site_edges``."""
    return site_screeners(ctx)


def site_edges(ctx: Stores) -> tuple[SiteEdge, ...]:
    """Every site edge in Guide order (module docstring); cached like ``screeners_of``."""
    return ctx.cache.get_or_compute(("guide-site-edges",), lambda: _site_edges(ctx))  # type: ignore[no-any-return]


def _site_edges(ctx: Stores) -> tuple[SiteEdge, ...]:
    screeners = {p.id for p in screeners_of(ctx)}
    found = []
    for edge in load_edges(ctx.configs, SITE_USER):
        if edge.owner != "site":
            continue
        universe = universe_of(ctx, edge)
        horizons = edge.outcome.horizon_sessions
        found.append(
            SiteEdge(
                edge=edge,
                universe=universe,
                mechanism=edge.mechanism_kind,
                asset=asset_of(edge, universe),
                side=edge.outcome.result_side,
                holding=horizons,
                band=holding_band(horizons),
                holding_text=holding_text(horizons),
                trigger=trigger_text(edge.schedule),
                screeners=tuple(s for s in edge.screeners if s in screeners),
            )
        )
    return tuple(sorted(found, key=lambda e: (e.edge.name.lower(), e.edge.id)))


def edges_of_screener(ctx: Stores, screener_id: str) -> tuple[SiteEdge, ...]:
    """The site edges whose screeners include the site screener ``screener_id``."""
    return tuple(e for e in site_edges(ctx) if screener_id in e.screeners)
