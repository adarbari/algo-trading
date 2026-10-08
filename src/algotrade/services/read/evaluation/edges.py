"""The edges a user sees (``Edge``): every edge document, by id, as it resolves for the user
(a site document with the user's layer over it, ADR 0015), with its status, thesis, the
screeners and baselines that implement it, its frozen period and the run it cites as evidence.

Configs, not results: an edge is listed whether or not it has been evaluated."""

from dataclasses import dataclass
from datetime import date

from algotrade.config.edges import document, loading
from algotrade.services.read.context import Stores


@dataclass(frozen=True)
class EdgeEvidence:
    """The run an evidenced or live edge cites and the split it was measured at."""

    run_id: str
    split_from: date


@dataclass(frozen=True)
class Edge:
    """An edge document. ``frozen_from``: the first session of its frozen period (None: it has
    none, so no run is canonical); ``variants``: the ids of its ``[[variants]]``, ``main``
    first; ``schedule``: ``every_session``, ``month_end`` or ``on_event:<class>``."""

    id: str
    name: str
    status: str
    thesis: str
    mechanism: str
    persistence: str
    schedule: str
    horizons: tuple[int, ...]
    screeners: tuple[str, ...]
    baselines: tuple[str, ...]
    variants: tuple[str, ...]
    frozen_from: date | None
    evidence: EdgeEvidence | None
    rejection_reason: str


def _edge(e: document.Edge) -> Edge:
    return Edge(
        id=e.id,
        name=e.name,
        status=e.status,
        thesis=e.thesis,
        mechanism=e.mechanism,
        persistence=e.persistence,
        schedule=e.schedule,
        horizons=e.outcome.horizon_sessions,
        screeners=e.screeners,
        baselines=e.baselines,
        variants=(document.MAIN, *(v.id for v in e.variants)),
        frozen_from=e.frozen_from,
        evidence=EdgeEvidence(e.evidence.run_id, e.evidence.split_from) if e.evidence else None,
        rejection_reason=e.rejection_reason,
    )


def load_edges(ctx: Stores) -> tuple[Edge, ...]:
    """Every edge ``ctx.user`` sees, by id; none without documents."""
    return tuple(_edge(e) for e in loading.load_edges(ctx.configs, ctx.user.user_id))


def load_edge(ctx: Stores, edge_id: str) -> Edge | None:
    """The edge ``edge_id``; ``None`` when the user has no such edge."""
    return next((e for e in load_edges(ctx) if e.id == edge_id), None)
