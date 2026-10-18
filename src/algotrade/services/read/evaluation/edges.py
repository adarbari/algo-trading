"""The edges a user sees (``Edge``): every edge document, by id, as it resolves for the user
(a site document with the user's layer over it, ADR 0015), with its status, thesis, the
screeners and baselines that implement it, its out-of-sample start (``frozen_from``), the run it
cites as evidence, its sources and how it is defined in words (``EdgeDefinition``).

Configs, not results: an edge is listed whether or not it has been evaluated."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from algotrade.config.edges import document, loading
from algotrade.config.edges.follow import AUDIT
from algotrade.config.edges.follow import KEY as FOLLOW
from algotrade.core.time.windows import window_name
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
class EdgePublished:
    """The figure the literature reports for the edge (``[published]``): ``measure``
    (``mean_excess``, ``decile_spread`` or ``lift_pts``) equal to ``value`` over
    ``horizon_sessions``, from ``source`` (title and link), over ``sample`` years (None: not
    stated); ``leg``: what the figure is of (``long_short`` spread or ``long``)."""

    measure: str
    value: float
    horizon_sessions: int
    source: EdgeSource
    sample: int | None = None
    leg: str = "long"


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
class EdgeAnswer:
    """One quality-bar answer (``key`` of ``document.QUALITY_BAR``) as the document has it."""

    key: str
    text: str


@dataclass(frozen=True)
class EdgeSettings:
    """What the builder edits, as the layered document resolves (the browser reads no TOML):
    ``top_k`` (None: every qualified name), ``universe`` (a preset's name; "" for an inline
    selection), the outcome's ``kind``, ``benchmark``, ``start_offset_sessions`` and ``cost_bps``,
    the ``quality_bar`` answers, and ``own``: the user's own document as JSON (``extends`` and
    what it sets; dates as ISO text; ``{}`` for a site edge). A save sends the whole document, so
    keys the builder does not edit are kept from ``own``."""

    top_k: int | None
    universe: str
    kind: str
    benchmark: str
    start_offset_sessions: int
    cost_bps: float | None
    quality_bar: tuple[EdgeAnswer, ...]
    own: Mapping[str, Any] = field(default_factory=dict)
    cost_applies: bool = True  # the outcome's value is a return, so a round-trip cost applies
    outcome_sign: float = 1.0  # -1 for direction ``below``: the stored values are oriented
    hold_rank: int | None = None  # a buy/hold band: the cost is charged on entries and exits


@dataclass(frozen=True)
class Edge:
    """An edge document. ``frozen_from``: the first session of its frozen period (None: it has
    none, so no run is canonical); ``variants``: the ids of its ``[[variants]]``, ``main``
    first; ``schedule``: ``every_session``, ``month_end``, ``calendar:<window>`` or
    ``on_event:<class>``. The user's
    own state about it (ADR 0053 amendment 2026-10-10): ``status`` is the one status (the user's
    on an own edge, with ``status_since`` and ``status_reason`` from its ``[audit]``); ``followed``
    and ``followed_since``: a site edge the user bookmarked; the permanent ``labels`` the server
    decided (the bookmark's and the audit's), ``oos_revealed``; ``mine``: the document is the
    user's (a copy or a new
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
    published: EdgePublished | None = None
    followed: bool = False
    followed_since: date | None = None
    status_since: date | None = None
    status_reason: str = ""
    labels: tuple[str, ...] = ()
    oos_revealed: bool = False
    mine: bool = False
    extends: str | None = None
    replaces: str | None = None
    oos_hidden: bool = False
    settings: EdgeSettings | None = None
    base: str = "universe"  # the document's ``base`` (``out_of_window``: a time-series edge)
    # The basis the document fixes for the verdict (ADR 0065): ``[implementation]`` promoted
    # and horizon (None: not declared; a user's edge never declares one).
    promoted: str | None = None
    basis_horizon: int | None = None
    # Interim, until the surfaces speak status (ADR 0053 amendment 2026-10-10): the old state
    # words the GraphQL type still serves, derived (``following`` when bookmarked, else
    # ``researching``; ``since`` the bookmark's; ``state_reason`` the status's).
    state: str = "researching"
    since: date | None = None
    state_reason: str = ""

    @property
    def paper_traded(self) -> bool:
        """The edge is on the desk: a bookmarked site edge (its paper trades are the site's, one
        shared record) or the user's own evidenced or live edge (recorded for them)."""
        return self.followed or (self.mine and self.status in loading.RECORDING)

    @property
    def paper_since(self) -> date | None:
        """The session the user's interest began: the bookmark's, else the status's."""
        return self.followed_since if self.followed else self.status_since


def _picks(e: document.Edge) -> str:
    event = document.event_class(e.schedule)
    window = window_name(e.schedule)
    when = (
        f"after each {event.replace('_', ' ')}"
        + (f" ({document.event_subtype(e.schedule)})" if document.event_subtype(e.schedule) else "")
        if event
        else f"every {window.replace('_', ' ')}"
        if window
        else {"every_session": "every session", "month_end": "every month end"}.get(
            e.schedule, e.schedule
        )
    )
    top = "all that qualify" if e.top_k is None else f"top {e.top_k} of the screen"
    return f"{when.capitalize()} · {top}"


def _win(o: document.Outcome) -> str:
    if o.kind == "expires_otm":
        return "the option expires worthless"
    if o.kind == "option_model_pnl":
        return "the modelled straddle P&L is positive (a model, not a quote)"
    if o.kind == "option_pnl":
        return "the chain P&L is positive (quoted prices, net of the spread)"
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


def _json(value: Any) -> Any:
    """``value`` as JSON-safe data (a TOML date as ISO text)."""
    if isinstance(value, Mapping):
        return {str(k): _json(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_json(v) for v in value]
    return value.isoformat() if isinstance(value, date) else value


def _settings(e: document.Edge, own: Mapping[str, Any] | None) -> EdgeSettings:
    return EdgeSettings(
        top_k=e.top_k,
        universe=e.universe if isinstance(e.universe, str) else "",
        kind=e.outcome.kind,
        benchmark=e.outcome.benchmark,
        start_offset_sessions=e.outcome.start_offset_sessions,
        cost_bps=e.outcome.cost_bps,
        cost_applies=e.outcome.is_return,
        outcome_sign=e.outcome.sign,
        hold_rank=e.outcome.hold_rank,
        quality_bar=tuple(EdgeAnswer(k, e.quality_bar.get(k, "")) for k in document.QUALITY_BAR),
        own={k: _json(v) for k, v in (own or {}).items() if k not in (FOLLOW, AUDIT, "status")},
    )


def _edge(e: document.Edge, mine: bool, own: Mapping[str, Any] | None = None) -> Edge:
    return Edge(
        id=e.id,
        name=e.name,
        status=e.status,
        thesis=e.thesis,
        mechanism=e.mechanism,
        persistence=e.persistence,
        schedule=e.schedule,
        base=e.base,
        horizons=e.outcome.horizon_sessions,
        screeners=e.screeners,
        baselines=e.baselines,
        variants=(document.MAIN, *(v.id for v in e.variants)),
        frozen_from=e.frozen_from,
        evidence=EdgeEvidence(e.evidence.run_id, e.evidence.split_from) if e.evidence else None,
        rejection_reason=e.rejection_reason,
        sources=tuple(EdgeSource(x.title, x.url) for x in e.sources),
        definition=EdgeDefinition(_picks(e), _trade(e.outcome), _compare(e), _test(e)),
        published=_published(e),
        state="following" if e.followed else "researching",
        since=e.follow.since,
        state_reason=e.audit.status_reason,
        followed=e.followed,
        followed_since=e.follow.since,
        status_since=e.audit.status_since,
        status_reason=e.audit.status_reason,
        labels=tuple(dict.fromkeys([*e.follow.labels, *e.audit.labels])),
        oos_revealed=e.audit.oos_revealed,
        mine=mine,
        extends=e.extends,
        replaces=e.audit.replaces,
        oos_hidden=mine and not e.audit.oos_revealed,
        settings=_settings(e, own if mine else None),
        promoted=e.promoted,
        basis_horizon=e.basis_horizon,
    )


def _published(e: document.Edge) -> EdgePublished | None:
    p = e.published
    if p is None:
        return None
    src = e.sources[p.source]
    return EdgePublished(
        p.measure, p.value, p.horizon_sessions, EdgeSource(src.title, src.url), p.sample, p.leg
    )


def load_edges(ctx: Stores) -> tuple[Edge, ...]:
    """Every edge ``ctx.user`` sees, by id; none without documents."""
    site = set(ctx.configs.names(loading.SITE, loading.KIND))
    found = loading.load_edges(ctx.configs, ctx.user.user_id)
    user = ctx.user.user_id
    return tuple(
        _edge(
            e,
            mine=e.id not in site,
            own=None if e.id in site else ctx.configs.load(user, loading.KIND, e.id),
        )
        for e in found
    )


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
