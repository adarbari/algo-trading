"""``load_edge_list``: the Edges list as filtered rows (ADR 0082, surface ``edges``). A row is an
``EdgeRow``: the edge the user sees, its verdict headline (``summary``: the stored one when its
fingerprint matches, else judged live, as ``Edge.summary``) and its ``live`` state for the session
(``edge_desk/states``: the paper record against the backtest's usual range; ``not_recording`` for
an edge that records none). ``q`` searches the edge's id, name and thesis (any case) and narrows
the list before the filters, so the facets count what the search left (``facets.total``); the
``filters`` then narrow it through the one pass. A figure the summary does not hold (no lift, no
trades) is UNKNOWN for its filter, never passing. Not paged: the list is the user's edges and the
site's."""

from collections.abc import Sequence
from dataclasses import dataclass

from algotrade.services.read.context import ReadContext
from algotrade.services.read.edge_desk.paper import load_trades
from algotrade.services.read.edge_desk.states import LiveState, live_edges, load_live_states
from algotrade.services.read.evaluation import versions
from algotrade.services.read.evaluation.edges import Edge, load_edges
from algotrade.services.read.evaluation.verdict.model import EdgeSummary
from algotrade.services.read.filtering.facets import Facets, compute_facets
from algotrade.services.read.filtering.masks import FilterInput
from algotrade.services.read.filtering.rows import frame_of
from algotrade.services.read.filtering.served import load_served_filters

SURFACE = "edges"  # config/site/filters/edges.toml


@dataclass(frozen=True)
class EdgeRow:
    """``edge`` with the facts the list's filters read (the roots of the column sources)."""

    edge: Edge
    summary: EdgeSummary
    live: LiveState | None


@dataclass(frozen=True)
class EdgeList:
    """``items``: the edges that pass the search and the filters, in id order; ``total``: their
    count (``facets.total``: before the filters, after the search)."""

    items: tuple[EdgeRow, ...]
    total: int
    facets: Facets


def _matches(e: Edge, needle: str) -> bool:
    return any(needle in text.lower() for text in (e.id, e.name, e.thesis))


def load_edge_list(
    ctx: ReadContext, filters: Sequence[FilterInput] = (), q: str | None = None
) -> EdgeList:
    """The user's edges for ``ctx.session`` matching ``q`` and ``filters``.
    ``FilterRefusedError`` for a filter the viewer is not offered."""
    served = load_served_filters(ctx, SURFACE, ctx.session.date)
    served.resolved.check(i.id for i in filters)
    needle = (q or "").strip().lower()
    found = [e for e in load_edges(ctx) if not needle or _matches(e, needle)]
    by_id = {e.id: e for e in found}
    recording = live_edges(by_id)
    trades = load_trades(ctx, recording) if recording else ()
    states = {s.edge_id: s for s in load_live_states(ctx, by_id, trades)}
    rows = tuple(EdgeRow(e, versions.load_summary(ctx, e), states.get(e.id)) for e in found)
    frame = frame_of(rows, served.resolved, served.columns)
    facets = compute_facets(frame, len(rows), served.resolved, filters)
    return EdgeList(tuple(rows[i] for i in facets.matched_rows), facets.matched, facets)
