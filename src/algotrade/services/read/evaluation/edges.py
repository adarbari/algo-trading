"""The edges a user sees (``Edge``): every edge document, by id, as it resolves for the user
(a site document with the user's layer over it, ADR 0015), with its status, thesis, the
screeners and baselines that implement it, its out-of-sample start (``frozen_from``), the run it
cites as evidence, its sources and how it is defined in words (``EdgeDefinition``).

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
class EdgeSource:
    """A source the edge rests on: its title, and a link when the document has one ("")."""

    title: str
    url: str


@dataclass(frozen=True)
class EdgeDefinition:
    """The parts of "how the edge is defined", as sentences (the browser words nothing):
    picks (when it fires, how many), trade (entry, holding periods, costs, what a win is),
    compare (the universe and the baselines) and test (where the out-of-sample period starts)."""

    picks: str
    trade: str
    compare: str
    test: str


@dataclass(frozen=True)
class Edge:
    """An edge document. ``frozen_from``: the first session of its frozen period (None: it has
    none, so no run is canonical); ``variants``: the ids of its ``[[variants]]``, ``main``
    first; ``schedule``: ``every_session``, ``month_end`` or ``on_event:<class>``. The user's
    own state about it (``[follow]``, ADR 0053 amendment 2026-10-09): ``state`` (researching,
    following, rejected, retired, trial), ``since``, ``state_reason``, the permanent ``labels``
    the server decided, ``oos_revealed``; ``mine``: the document is the user's (a copy or a new
    edge, not a site edge), ``extends`` the edge it is a copy of, ``replaces`` the edge a trial
    would replace. ``oos_hidden``: a copy whose out-of-sample result is withheld until shown."""

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
    sources: tuple[EdgeSource, ...]
    definition: EdgeDefinition
    state: str = "researching"
    since: date | None = None
    state_reason: str = ""
    labels: tuple[str, ...] = ()
    oos_revealed: bool = False
    mine: bool = False
    extends: str | None = None
    replaces: str | None = None
    oos_hidden: bool = False


def _picks(e: document.Edge) -> str:
    event = document.event_class(e.schedule)
    when = (
        f"after each {event.replace('_', ' ')}"
        if event
        else {"every_session": "every session", "month_end": "every month end"}.get(
            e.schedule, e.schedule
        )
    )
    top = "all that qualify" if e.top_k is None else f"top {e.top_k} of the screen"
    return f"{when.capitalize()} · {top}"


def _win(o: document.Outcome) -> str:
    if o.kind == "expires_otm":
        return "the option expires worthless"
    if o.kind == "hit_target":
        return f"{(o.measure or 'the measure').replace('_', ' ')} {o.direction} {o.target:g}"
    return f"beats {o.benchmark}" if o.benchmark != "none" else "rises"


def _trade(o: document.Outcome) -> str:
    n = o.start_offset_sessions
    held = " or ".join(str(h) for h in o.horizon_sessions)
    parts = [
        f"Enter {n} session{'' if n == 1 else 's'} after the decision",
        f"hold {held} trading days",
    ]
    if o.cost_bps is not None:
        parts.append(f"{o.cost_bps / 100:g}% costs")
    parts.append(f"win = {_win(o)}")
    return " · ".join(parts)


def _compare(e: document.Edge) -> str:
    universe = e.universe if isinstance(e.universe, str) else "its own selection"
    baselines = ", ".join(e.baselines) or "no baselines"
    return f"Universe: {universe} · against {baselines}"


def _test(e: document.Edge) -> str:
    if e.frozen_from is None:
        return "No out-of-sample period yet"
    return f"Out-of-sample from {e.frozen_from.isoformat()}"


def _edge(e: document.Edge, mine: bool) -> Edge:
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
        sources=tuple(EdgeSource(x.title, x.url) for x in e.sources),
        definition=EdgeDefinition(_picks(e), _trade(e.outcome), _compare(e), _test(e)),
        state=e.follow.state,
        since=e.follow.since,
        state_reason=e.follow.reason,
        labels=e.follow.labels,
        oos_revealed=e.follow.oos_revealed,
        mine=mine,
        extends=e.extends,
        replaces=e.follow.replaces,
        oos_hidden=mine and not e.follow.oos_revealed,
    )


def load_edges(ctx: Stores) -> tuple[Edge, ...]:
    """Every edge ``ctx.user`` sees, by id; none without documents."""
    site = set(ctx.configs.names(loading.SITE, loading.KIND))
    found = loading.load_edges(ctx.configs, ctx.user.user_id)
    return tuple(_edge(e, mine=e.id not in site) for e in found)


def load_edge(ctx: Stores, edge_id: str) -> Edge | None:
    """The edge ``edge_id``; ``None`` when the user has no such edge."""
    return next((e for e in load_edges(ctx) if e.id == edge_id), None)


@dataclass(frozen=True)
class EdgeProblem:
    """One of the user's own edge files that does not (fully) load: ``edge_id`` and the
    ``reason`` in the loader's words."""

    edge_id: str
    reason: str


def load_edge_problems(ctx: Stores) -> tuple[EdgeProblem, ...]:
    """The user's own edge files left out (or only partly read) by ``load_edges``, by id."""
    found = loading.edge_problems(ctx.configs, ctx.user.user_id)
    return tuple(EdgeProblem(i, found[i]) for i in sorted(found))
