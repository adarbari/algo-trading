"""The edge document (ADR 0053 decision 1; the quality bar is docs/edges-plan.md): one
``config/site/edges/<id>/edge.toml`` typed into a frozen ``Edge``, fail closed: an unknown key, a
wrong type, an unknown status, schedule or event class, or a missing answer fails with the file
and the key.

    id, name          the file's stem (an id), the name on screen
    thesis            one sentence: what is mispriced, and which way
    mechanism         quality bar 1: who is forced, constrained or systematically wrong
    persistence       quality bar 2: why it survives being known
    [outcome]         kind (``excess_return`` | ``hit_target``), horizon_sessions (one or more),
                      benchmark (``SPY`` | ``none``), start_offset_sessions (the entry session S:
                      D + this for every_session / month_end, D the decision session, so at
                      least 1; for an event schedule the event's anchor session + this, D = S - 1;
                      <= 0 only for an event announced ahead), optional target, max_drawdown (a
                      fraction), cost_bps; a hit_target also names its measure (MEASURES) and
                      direction (``below`` | ``above``); an excess_return's measure may be
                      ``residual_return`` (factor-neutral); an ``expires_otm`` outcome (the short
                      option is not assigned at the horizon's close: put | call | strangle) names
                      its ``structure``, exactly one of ``strike_delta`` (a delta in (0, 1)) and
                      ``otm_pct`` (a fraction in (0, 1)) and the ``iv_field`` it reads at D;
                      ``iv_field`` is allowed on a ratio measure too (default: the run's); an
                      ``option_model_pnl`` outcome (a model P&L, basis ``model``) names its
                      ``structure`` (MODEL_STRUCTURES), ``iv_field``, ``benchmark = "none"``, no
                      strike; ``option_pnl``: ``chain.py``; ``pair_spread``: ``pair_field``;
                      ``side`` (SIDES; ADR 0053 amendment, outcome sides): ``long`` (default),
                      ``short`` (the picks are the bottom ``top_k`` of the ranked, liquid names;
                      the value is minus the excess return, less cost and borrow) or
                      ``long_short`` (the top ``top_k`` minus the bottom: a spread, diagnostic
                      only); a side other than long needs an ``excess_return`` outcome, no
                      ``max_drawdown``, an integer ``top_k``; optional ``borrow_bps_annual``
                      (default from ``verdict.toml``) is the short leg's assumed borrow cost;
                      optional ``hold_rank`` (buy/hold band, ADR 0053 amendment 2026-10-18): held
                      while rank <= this (>= ``top_k``, an integer); cost on entries and exits
                      only; see ``_hold_rank`` for where it is allowed
    schedule          ``every_session`` | ``month_end`` | ``calendar:<window>`` (WINDOW_NAMES: a
                      stretch the calendar fixes, whose length is the one horizon) |
                      ``on_event:<class>[:<subtype>]`` (EVENT_CLASSES; EVENT_SUBTYPES)
    base              what the picks are compared with: ``event`` (the names with the event at
                      D, of the schedule's own class and subtype; default for an event
                      schedule) | ``universe`` (every eligible name) | ``out_of_window`` (a
                      time-series edge: ADR 0073)
    picks             where an event schedule's picks come from: ``event`` (the qualified names
                      within the event names; default) | ``universe`` (the qualified names of
                      every eligible name on the event sessions; a decoy). Plain schedules
                      ignore it
    [[variants]]      id, optional [variants.outcome], universe, base and picks overriding the
                      edge's: each
                      is another evaluation of the same edge, one trial in the deflated Sharpe
                      ratio (ADR 0053 amendment 2026-10-08; the id ``main`` is the edge itself)
    universe          a selection preset name, or an inline selection (``[universe] where``)
    top_k             an integer >= 1, or ``"all"`` (every qualified name)
    screeners         the screener presets that implement it (empty while a candidate waits)
    baselines         screener presets run on the same sessions (quality bar 9); the one entry
                      ``"@standard"`` stands for ``verdict.toml [decoys] standard`` (the decoy
                      battery, ADR 0053 amendment 2026-10-18), expanded where the edge loads
    status            researching | candidate | evidenced | live | retired | rejected | blocked
    family            optional "A".."I": the idea catalogue's family (docs/edge-ideas/); the
                      edges page groups by it
    frozen_from       optional date: the harness reports sessions from it on their own as the
                      frozen period (fixed once chosen, never rolling; none: no frozen slice)
    [evidence]        run_id and split_from of the run an evidenced or live edge rests on; its
                      split_from must equal frozen_from (ADR 0053 amendment, ED5a)
    rejection_reason  required when rejected or blocked, allowed when retired, else an error
    [published]       optional: the number the literature reports, to set beside the harness's:
                      ``measure`` (PUBLISHED_MEASURES; ``mean_excess`` and ``decile_spread`` in
                      return as a fraction, ``lift_pts`` in points), ``value``,
                      ``horizon_sessions`` (one of the outcome's), ``source`` (the index of its
                      ``[[sources]]`` entry) and optional ``sample`` (years it covers; ADR 0064
                      decision 6), and optional ``leg`` (LEGS: ``long_short``, ``short`` or
                      ``long``:
                      what the figure is of; by default ``long_short`` for a ``decile_spread``,
                      ``short`` for another measure of a short outcome, else ``long``; picks the
                      ``verdict.toml``
                      ``[published_haircut]`` shown beside it, display only). A copy inherits it
    [[sources]]       title, optional https url (a paper without one: author, title, year)
    [quality_bar]     the other seven answers (QUALITY_BAR); required unless rejected / blocked
    notes             optional: a proxy, an open decision
    [implementation]  optional: ``horizon``, the one of the main outcome's horizon_sessions the
                      verdict rests on (ADR 0065: declared only where the thesis fixes one; else
                      the basis is the best candidate in-sample); ``promoted``, the one of
                      ``screeners`` that implements the edge
                      for use (ED7c) and the verdict's screen, and ``[[implementation.compared]]``
                      (only beside ``promoted``): the frozen-slice
                      numbers of the cited run it rests on (``horizon``, ``screener``, ``lift``,
                      ``decile_spread``, ``sessions``, ``decile_sessions``; the model and every
                      rule screener at every horizon). A reader honours ``promoted`` only when
                      the cited run's stored rows show the model ahead
                      (``services/read/evaluation/promotion.py``); a fitness test checks the
                      committed numbers the same way (``test_edge_promotion.py``)
    extends           a user's copy: the id of the edge (a site edge, or the user's own) whose
                      document it is layered over (``loading.py``); the copy's own keys win
    [follow]          a user's bookmark of a site edge (``follow.py``)
    [audit]           the server's bookkeeping of a user's own edge (``follow.py``)
    [scorer]          optional: ``features``, the selection fields (``rollup.<group>@v<n>.<column>``
                      or ``feature.<name>``) a learned scorer is fitted on (ED7)

Whether the named presets exist is checked by ``loading.py``, which sees the store.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, NoReturn

from algotrade.config.edges import chain, named
from algotrade.config.edges.follow import Audit, Follow, parse_audit, parse_follow
from algotrade.config.edges.identity import (
    LONG,
    LONG_SHORT,
    SHORT,
    SIDES,
    check_side,
    hold_rank_of,
    pair_field_of,
)
from algotrade.config.edges.portfolio import (
    BENCHMARK_BASE,
    PORTFOLIO_KIND,
    Canary,
    benchmark_of,
    canary_of,
    check_base,
    check_portfolio,
    ensemble_of,
    oos_class_of,
    vol_target_of,
    weighting_of,
)
from algotrade.config.edges.verdict import LEGS
from algotrade.config.site.fields import Table, reject_secrets
from algotrade.config.strategy.schema import Selection, parse_selection
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.ids import validate_id
from algotrade.core.time.windows import (
    CALENDAR,
    WINDOW_NAMES,
    window_length,
    window_name,
)

MIN_INDEPENDENT_SESSIONS = 40  # the quality bar's count: a fit and a promotion need this many
FAMILIES = tuple("ABCDEFGHI")  # the idea catalogue's families (docs/edge-ideas/)
STATUSES = ("researching", "candidate", "evidenced", "live", "retired", "rejected", "blocked")
CLOSED = ("rejected", "blocked")  # kept on file with the reason; the bar is not required
OUTCOME_KINDS = (
    "excess_return", "hit_target", "expires_otm", "option_model_pnl", PORTFOLIO_KIND,
    chain.CHAIN_KIND, "pair_spread",
)  # fmt: skip
MODEL_KIND, PAIR_KIND = "option_model_pnl", "pair_spread"  # pair: cheap return less sibling's
MODEL_BASIS = "model"  # what a price from a model, not a quote, is labelled (results and UI)
BENCHMARKS = ("SPY", "none")
SCHEDULES = ("every_session", "month_end")
BASES = ("event", "universe", named.OUT_OF_WINDOW, BENCHMARK_BASE)
PICKS = ("event", "universe")  # where an event schedule's picks may come from
MAIN = "main"  # the edge itself, as the key of a results row (a variant has its own id)
ON_EVENT = "on_event:"
# The event classes a schedule may trigger on, and its ANCHOR session. The entry session is
# S = anchor + start_offset_sessions, the decision session D = S - 1, the outcome's horizons
# count from S's close, and the event must be known by D (``known_from <= D``, ADR 0050): the
# harness skips an event that is not, never reads it early (``cross_section/events.py`` names
# the stored field each class is read from).
EVENT_CLASSES: Mapping[str, str] = {
    "earnings_reaction": "a reported result's two-session reaction (earnings_reaction@v1); "
    "anchor: the reaction's last session, E+1 (E: the report date)",
    "earnings_expected": "a next report expected, scheduled or from the year-ago report "
    "(earnings_expected@v1); anchor: the expected report date's session",
    "index_change": "an S&P 500 membership change (index_changes@v1); anchor: the session it is "
    "first stored (never the announcement)",
    "filing_8k": "an 8-K carrying one Item (filing_events@v1); needs the item as its subtype; "
    "anchor: the session the filing became known, the first whose close is after SEC accepted it",
    "nt_late_filing": "an NT 10-K or NT 10-Q late-filing notice (filing_events@v1); anchor: the "
    "session it became known",
    "tender_offer": "an SC TO-I issuer or SC TO-T third-party tender offer (filing_events@v1); "
    "anchor: the session it became known",
    "earnings_date_shift": "a next report date a week or more away from last year's "
    "(earnings_date_shift@v1); anchor: the session the shifted date was first stored",
}
# A class may be split by a subtype: ``on_event:<class>:<subtype>``. The subtype is one of the
# class's own values (fail closed on any other, and on a subtype for a class that has none); the
# base of an edge on it is the same class and subtype (``base = "event"``) or the universe. A
# class in ``SUBTYPE_REQUIRED`` has no field of its own to read without one. The stored field of
# each is declared in ``cross_section/events.py`` (kept equal by a fitness test).
EVENT_SUBTYPES: Mapping[str, Mapping[str, str]] = {
    "index_change": {
        "addition": "joined the S&P 500 (sp500_added)",
        "deletion": "left the S&P 500 (sp500_removed)",
    },
    "filing_8k": {
        "1.02": "Item 1.02, termination of a material agreement",
        "2.05": "Item 2.05, exit or disposal costs (a restructuring)",
        "3.01": "Item 3.01, a delisting or listing-standard notice",
        "4.01": "Item 4.01, a change of the auditor",
        "4.02": "Item 4.02, non-reliance on previously issued financial statements",
        "5.02": "Item 5.02, the departure or appointment of a director or an officer",
    },
    "earnings_date_shift": {
        "later": "the next report date is a week or more later than last year's",
        "earlier": "the next report date is a week or more earlier than last year's",
    },
}
SUBTYPE_REQUIRED = ("filing_8k",)
# ex_dividend, macro_release and lockup_expiry have no field to read yet (EB H4 follow-ups).
ANNOUNCED_AHEAD = ("earnings_expected",)  # an entry may precede these
# Quality bar answers 3 to 9 (1 and 2 are the document's mechanism and persistence).
# What a hit_target compares with its target over the window (ED2 stores each as a field).
MEASURES = ("excess_return", "realised_to_implied_vol")
EXCESS_MEASURES = ("residual_return",)  # what an excess_return outcome may name (factor-neutral)
DIRECTIONS = ("below", "above")
QUALITY_BAR = (
    "outcome",
    "trigger_timing",
    "replication",
    "expected_size",
    "capacity_costs",
    "failure_modes",
    "decoys",
)
PUBLISHED_MEASURES = ("mean_excess", "decile_spread", "lift_pts")
PUBLISHED_KEYS = ("measure", "value", "horizon_sessions", "sample", "source", "leg")
STANDARD = "@standard"  # in ``baselines``: the site's standard decoys (``expand_baselines``)
KEYS = (
    "id", "name", "thesis", "mechanism", "persistence", "outcome", "schedule", "universe",
    "top_k", "screeners", "baselines", "status", "rejection_reason", "sources", "quality_bar",
    "notes", "frozen_from", "base", "picks", "variants", "evidence", "scorer", "implementation",
    "extends", "follow", "audit", "published", "family", "ensemble", "oos_class",
)  # fmt: skip
OUTCOME_KEYS = (
    "kind", "horizon_sessions", "benchmark", "start_offset_sessions", "target", "max_drawdown",
    "cost_bps", "measure", "direction", "structure", "strike_delta", "otm_pct", "iv_field",
    "side", "borrow_bps_annual", "tenor_days", "hold_rank", "weighting", "vol_field", "pair_field",
    "vol_target", "vol_window", "vol_return_field", "canary",
)  # fmt: skip
SHARED_KEYS = ("horizon_sessions", "benchmark", "start_offset_sessions", "iv_field")
VARIANT_KEYS = ("id", "outcome", "universe", "base", "picks")
EVIDENCE_KEYS = ("run_id", "split_from")
IMPLEMENTATION_KEYS = ("promoted", "horizon", "compared")
COMPARED_KEYS = ("horizon", "screener", "lift", "decile_spread", "sessions", "decile_sessions")
EVIDENCE_STATUSES = ("evidenced", "live", "retired")
_SENTENCE_BREAK = re.compile(r"[.!?]\s+[A-Z]")


@dataclass(frozen=True)
class Outcome:
    """What counts as the edge working for one (instrument, entry session S): returns from S's
    close to the close ``h`` sessions later, for each horizon ``h``; a hit_target holds when
    ``measure`` is ``direction`` the ``target`` (and the path stays within ``max_drawdown``).
    ``start_offset_sessions``: S = D + it (D: the decision session), or for an event schedule
    the event's anchor + it."""

    kind: str
    horizon_sessions: tuple[int, ...]
    benchmark: str
    start_offset_sessions: int = 0
    target: float | None = None
    max_drawdown: float | None = None
    cost_bps: float | None = None
    measure: str | None = None
    direction: str | None = None
    structure: str | None = None
    strike_delta: float | None = None
    otm_pct: float | None = None
    iv_field: str | None = None
    side: str = LONG  # SIDES; a short leg pays ``borrow_bps_annual`` (None: the site's default)
    borrow_bps_annual: float | None = None
    tenor_days: int | None = None  # an option_pnl's tenor rule (chain.py)
    pair_field: str | None = None  # a pair_spread's sibling-id feature, read at D
    hold_rank: int | None = None  # buy/hold band: held while rank <= this (None: no band)
    # A portfolio_return book (ADR 0074): how the picks are weighted, and for ``inverse_vol`` the
    # declared feature whose value at D is each name's volatility.
    weighting: str = "equal"
    vol_field: str | None = None
    # Volatility targeting of the book (ADR 0074 amendment): None, or the annualised volatility
    # the book is scaled down to (never up), measured over ``vol_window`` sessions of
    # ``vol_return_field``; the rest is cash.
    vol_target: float | None = None
    vol_window: int = 60
    vol_return_field: str = "rollup.trend_stats@v2.ret_1d"
    canary: Canary | None = None  # a risk-off gate on the book (ADR 0074 amendment)

    @property
    def result_side(self) -> str:
        """The side results are judged under: ``long_short`` (diagnostic only) for a pair spread."""
        return LONG_SHORT if self.kind == PAIR_KIND else self.side

    @property
    def is_return(self) -> bool:
        """The value is the net excess return (a round-trip cost applies to it)."""
        return self.kind in ("excess_return", PORTFOLIO_KIND) or self.measure == "excess_return"

    @property
    def basis(self) -> str | None:
        return {MODEL_KIND: MODEL_BASIS, chain.CHAIN_KIND: chain.CHAIN_BASIS}.get(self.kind)

    @property
    def sign(self) -> float:
        """The orientation of the value: higher is better, so ``-1`` for direction ``below``."""
        return -1.0 if self.direction == "below" else 1.0


@dataclass(frozen=True)
class EdgeVariant:
    """One more evaluation of an edge (ADR 0053 amendment 2026-10-08): the edge's outcome and
    universe with this variant's overrides applied. Each is a trial of the deflated Sharpe ratio."""

    id: str
    outcome: Outcome
    universe: str | Selection
    base: str | None = None  # None: the edge's own
    picks: str | None = None  # None: the edge's own


@dataclass(frozen=True)
class Evidence:
    """The harness run an evidenced or live edge cites (ADR 0053 amendment, ED5a): its record id
    and the split it was measured at, which must be the document's ``frozen_from``."""

    run_id: str
    split_from: date


@dataclass(frozen=True)
class Compared:
    """One screener's frozen-slice numbers at one horizon, as committed beside a promotion."""

    horizon: int
    screener: str
    lift: float
    decile_spread: float
    sessions: int
    decile_sessions: int


@dataclass(frozen=True)
class Published:
    """The figure a paper reports for the edge's own statistic: ``measure`` (what it measures,
    comparable with the harness's ``mean_excess_picks``, ``decile_spread`` or the lift in points)
    equal to ``value`` over ``horizon_sessions``, from ``sources[source]``, over ``sample`` years
    (None: not stated)."""

    measure: str
    value: float
    horizon_sessions: int
    source: int
    sample: int | None = None
    leg: str = "long"  # what the paper's figure is of: the long side | a long-short spread


@dataclass(frozen=True)
class Source:
    title: str
    url: str = ""


@dataclass(frozen=True)
class Edge:
    id: str
    name: str
    thesis: str
    mechanism: str
    persistence: str
    outcome: Outcome
    schedule: str
    universe: str | Selection
    top_k: int | None  # None: every qualified name
    screeners: tuple[str, ...]
    baselines: tuple[str, ...]
    status: str
    sources: tuple[Source, ...]
    quality_bar: Mapping[str, str]  # QUALITY_BAR -> answer ("" only when CLOSED)
    rejection_reason: str = ""
    notes: str = ""
    family: str = ""  # the catalogue family "A".."I" the idea came from ("" none)
    frozen_from: date | None = None
    base: str = "universe"  # what the picks are compared with: the event's names | the universe
    picks: str = "event"  # an event schedule's pick set: within the event names | the universe
    variants: tuple[EdgeVariant, ...] = ()
    scorer_features: tuple[str, ...] = ()  # the fields a learned scorer reads (ADR 0053, ED7)
    evidence: Evidence | None = None
    published: Published | None = None  # the literature's figure, for the decay read (ADR 0064)
    promoted: str | None = None  # the screener that implements the edge for use (ED7c)
    compared: tuple[Compared, ...] = ()  # the numbers the promotion rests on
    basis_horizon: int | None = None  # the horizon the verdict rests on (ADR 0065)
    extends: str | None = None  # a user's copy: the edge it is layered over
    follow: Follow = field(default_factory=Follow)  # the user's bookmark of a site edge
    audit: Audit = field(default_factory=Audit)  # the server's bookkeeping of an own edge
    # ADR 0074: the screeners a book averages into ONE variant; the class of its haircut
    ensemble: tuple[str, ...] = ()
    oos_class: str | None = None
    # The frozen_from of the site edge this one is a copy of (its own for a site edge): a copy
    # whose frozen_from differs is exploratory (its split is the user's, ADR 0053 amendment).
    site_frozen_from: date | None = None
    # Whose edge it is: ``site`` or a user id, set by the loader from where the document lives
    # (``loading.py``), never a key of the document (a document cannot claim an owner).
    owner: str = "site"

    @property
    def followed(self) -> bool:
        """The user bookmarked this (site) edge."""
        return self.follow.since is not None

    @property
    def event_class(self) -> str | None:
        """The class an ``on_event:`` schedule triggers on, else None."""
        return event_class(self.schedule)

    @property
    def event_subtype(self) -> str | None:
        """The subtype of an ``on_event:<class>:<subtype>`` schedule, else None."""
        return event_subtype(self.schedule)

    @property
    def answers(self) -> tuple[tuple[str, str], ...]:
        """The nine quality-bar answers in the plan's order."""
        return (
            ("mechanism", self.mechanism),
            ("persistence", self.persistence),
            *((key, self.quality_bar[key]) for key in QUALITY_BAR),
        )


# Owners an evaluation run was once recorded under for what are now site edges: the backtest CLI
# fell back to the user ``local`` before an edge's owner came from its document. Their records
# are read as the site's (disclosed as ``legacy_owner``), never rewritten.
# ``local`` is a real user too, so a record counts as the site's only if it finished before the
# cutoff (the day owner-from-document landed); later ``local`` runs are the user's own.
LEGACY_SITE_OWNERS = ("local",)
LEGACY_SITE_CUTOFF = datetime(2026, 10, 11, tzinfo=UTC)


def job_name(edge_id: str, user_id: str) -> str:
    """The run-record ``job`` whose records hold one owner's trial log of an edge (ADR 0015):
    written by the harness, read by the read model."""
    return f"edge-eval:{edge_id}:{user_id}"


def event_class(schedule: str) -> str | None:
    """The event class of an ``on_event:<class>[:<subtype>]`` schedule, else None."""
    if not schedule.startswith(ON_EVENT):
        return None
    return schedule.removeprefix(ON_EVENT).partition(":")[0]


def event_subtype(schedule: str) -> str | None:
    """The subtype of an ``on_event:<class>:<subtype>`` schedule, else None."""
    if not schedule.startswith(ON_EVENT):
        return None
    return schedule.removeprefix(ON_EVENT).partition(":")[2] or None


def _event_schedule_ok(t: Table, schedule: str) -> bool:
    """Whether an ``on_event:`` schedule names a known class and, fail closed, one of its
    subtypes (required for ``SUBTYPE_REQUIRED``, refused for a class that has none)."""
    cls, sub = event_class(schedule), event_subtype(schedule)
    if cls is None or cls not in EVENT_CLASSES:
        return False
    allowed = EVENT_SUBTYPES.get(cls, {})
    if sub is None:
        if cls in SUBTYPE_REQUIRED:
            raise ConfigurationError(
                f"{t.where} schedule: {schedule!r} needs a subtype, one of {sorted(allowed)}"
            )
        return True
    if sub not in allowed:
        raise ConfigurationError(
            f"{t.where} schedule: {sub!r} is not a subtype of {cls!r} "
            f"(known: {sorted(allowed) or 'none'})"
        )
    return True


def parse_edge(doc: Mapping[str, Any], name: str, where: str) -> Edge:
    """``doc`` (the layered document of ``<name>.toml``) as an ``Edge``; ``where`` names it."""
    reject_secrets(doc, where)
    t = Table(doc, where)
    t.only(KEYS)
    edge_id = validate_id("edge", _required(t, "id"))
    if edge_id != name:
        raise ConfigurationError(f"{where} id: {edge_id!r} must equal the file name {name!r}")
    status = t.choice("status", "", STATUSES) if "status" in doc else _missing(t, "status")
    closed = status in CLOSED
    schedule = _schedule(t)
    base = _base(t, schedule, BENCHMARK_BASE if _kind_of(t) == PORTFOLIO_KIND else None)
    outcome = _outcome(t, schedule, base)
    universe = _universe(t, edge_id)
    named.check_time_series(base, window_name(schedule) in WINDOW_NAMES, universe, where)
    picks = _picks(t, schedule, base)
    sources = _sources(t)
    screeners = _ids(t, "screeners")
    top_k = _top_k(t)
    variants = _variants(t, schedule, edge_id, universe, base, picks)
    chain.check_kinds(where, {outcome.kind, *(v.outcome.kind for v in variants)})
    for held, held_base in ((outcome, base), *((v.outcome, v.base or base) for v in variants)):
        check_base(held.kind, held_base, where)
        if held.side != LONG and top_k is None:
            raise ConfigurationError(
                f"{where} top_k: a {held.side!r} outcome ranks the names, so it needs an "
                f"integer top_k, not 'all'"
            )
        if held.hold_rank is not None and (top_k is None or held.hold_rank < top_k):
            raise ConfigurationError(
                f"{where} hold_rank: {held.hold_rank} must be an integer >= top_k "
                f"({'all' if top_k is None else top_k}); a name is held down to that rank, "
                f"entered at top_k"
            )
    edge = Edge(
        id=edge_id,
        name=_required(t, "name"),
        thesis=_thesis(t),
        mechanism=_answer(t, "mechanism", closed),
        persistence=_answer(t, "persistence", closed),
        outcome=outcome,
        schedule=schedule,
        universe=universe,
        top_k=top_k,
        screeners=screeners,
        baselines=_ids(t, "baselines", (STANDARD,)),
        status=status,
        sources=sources,
        quality_bar=_quality_bar(t, closed),
        rejection_reason=_prose(t, "rejection_reason"),
        notes=_prose(t, "notes"),
        family=t.choice("family", "", FAMILIES) if "family" in doc else "",
        frozen_from=_frozen_from(t),
        base=base,
        picks=picks,
        variants=variants,
        ensemble=ensemble_of(t, screeners, outcome.kind),
        oos_class=oos_class_of(t),
        scorer_features=_scorer_features(t),
        evidence=_evidence(t),
        published=_published(t, outcome, len(sources)),
        promoted=_promoted(t),
        compared=_compared(t),
        basis_horizon=_basis_horizon(t, outcome),
        extends=_extends(t, edge_id),
        follow=parse_follow(doc, where),
        audit=parse_audit(doc, where),
        site_frozen_from=_frozen_from(t),
    )
    if edge.promoted is not None and edge.promoted not in edge.screeners:
        raise ConfigurationError(
            f"{where} implementation.promoted: {edge.promoted!r} is not one of the screeners "
            f"{list(edge.screeners)}"
        )
    if edge.evidence is not None and status not in EVIDENCE_STATUSES:
        raise ConfigurationError(
            f"{where} evidence: only an evidenced, live or retired edge cites a run"
        )
    if closed and not edge.rejection_reason:
        raise ConfigurationError(f"{where} rejection_reason: required when status is {status!r}")
    if edge.rejection_reason and status not in (*CLOSED, "retired"):
        raise ConfigurationError(
            f"{where} rejection_reason: only a rejected, blocked or retired edge has one"
        )
    return edge


def _missing(t: Table, key: str) -> NoReturn:
    raise ConfigurationError(f"{t.where} {key}: required")


def _prose(t: Table, key: str) -> str:
    """Optional text with its whitespace collapsed (TOML multi-line strings read as one line)."""
    return " ".join(t.text(key, "").split()) if t.raw(key) is not None else ""


def _required(t: Table, key: str) -> str:
    return _prose(t, key) or _missing(t, key)


def _answer(t: Table, key: str, closed: bool) -> str:
    return _prose(t, key) if closed else _required(t, key)


def _thesis(t: Table) -> str:
    thesis = _required(t, "thesis")
    if _SENTENCE_BREAK.search(thesis) or thesis[-1] not in ".!?":
        raise ConfigurationError(f"{t.where} thesis: expected one sentence, got {thesis!r}")
    return thesis


def _evidence(t: Table) -> Evidence | None:
    if t.raw("evidence") is None:
        return None
    sub = t.table("evidence", EVIDENCE_KEYS)
    run_id, split = sub.text("run_id", ""), sub.raw("split_from")
    if not run_id or split is None:
        raise ConfigurationError(f"{sub.where}: run_id and split_from are both required")
    return Evidence(run_id, _date(sub, "split_from", split))


def _default_leg(measure: str, outcome: Outcome) -> str:
    """What a published figure is of when the document does not say: a decile spread is a
    long-short spread; any other measure is of the outcome's own leg (``short`` for a short)."""
    if measure == "decile_spread":
        return LONG_SHORT
    return SHORT if outcome.side == SHORT else LONG


def _published(t: Table, outcome: Outcome, sources: int) -> Published | None:
    if t.raw("published") is None:
        return None
    sub = t.table("published", PUBLISHED_KEYS)
    for key in ("measure", "value", "horizon_sessions", "source"):
        if key not in sub.names():
            _missing(sub, key)
    horizon = sub.integer("horizon_sessions", 0, 1)
    if horizon not in outcome.horizon_sessions:
        raise ConfigurationError(
            f"{sub.where} horizon_sessions: {horizon} is not one of the outcome's "
            f"{list(outcome.horizon_sessions)}"
        )
    source = sub.integer("source", 0, 0)
    if source >= sources:
        raise ConfigurationError(
            f"{sub.where} source: {source} is not an index of the {sources} [[sources]]"
        )
    measure = sub.choice("measure", "", PUBLISHED_MEASURES)
    return Published(
        measure=measure,
        value=sub.number("value", 0.0),
        horizon_sessions=horizon,
        source=source,
        sample=sub.integer("sample", 0, 1) if "sample" in sub.names() else None,
        leg=sub.choice("leg", _default_leg(measure, outcome), LEGS),
    )


def _extends(t: Table, edge_id: str) -> str | None:
    raw = t.text("extends", "")
    if not raw:
        return None
    if validate_id("edge", raw) == edge_id:
        raise ConfigurationError(f"{t.where} extends: an edge cannot extend itself")
    return raw


def _frozen_from(t: Table) -> date | None:
    raw = t.raw("frozen_from")
    return None if raw is None else _date(t, "frozen_from", raw)


def _date(t: Table, key: str, raw: Any) -> date:
    if type(raw) is date:
        return raw
    try:
        if isinstance(raw, str):
            return date.fromisoformat(raw)
    except ValueError:
        pass
    raise ConfigurationError(f"{t.where} {key}: expected a date (2026-04-01), got {raw!r}")


def _schedule(t: Table) -> str:
    schedule = _required(t, "schedule")
    if (
        schedule in SCHEDULES
        or _event_schedule_ok(t, schedule)
        or window_name(schedule) in WINDOW_NAMES
    ):
        return schedule
    options = [
        *SCHEDULES,
        *(f"{CALENDAR}{w}" for w in WINDOW_NAMES),
        *(f"{ON_EVENT}{c}" for c in EVENT_CLASSES),
    ]
    raise ConfigurationError(f"{t.where} schedule: expected one of {options}, got {schedule!r}")


def _base(t: Table, schedule: str, default: str | None = None) -> str:
    event = event_class(schedule) is not None
    base = (
        t.choice("base", "", BASES)
        if "base" in t.names()
        else default or ("event" if event else "universe")
    )
    if base == "event" and not event:
        raise ConfigurationError(f"{t.where} base: 'event' needs an on_event schedule")
    return base


def _picks(t: Table, schedule: str, base: str, default: str = "event") -> str:
    """The table's ``picks`` (else ``default``): only an event schedule has picks to widen, and
    picks outside the event names need the universe as the base rate (else they are dropped)."""
    picks = t.choice("picks", default, PICKS)
    if "picks" in t.names() and event_class(schedule) is None:
        raise ConfigurationError(f"{t.where} picks: needs an on_event schedule")
    if picks == "universe" and base != "universe":
        raise ConfigurationError(f"{t.where} picks: 'universe' needs base = \"universe\"")
    return picks


def _outcome(t: Table, schedule: str, base: str = "universe") -> Outcome:
    if t.raw("outcome") is None:
        _missing(t, "outcome")
    return _outcome_of(t.table("outcome", OUTCOME_KEYS), schedule, base)


def _kind_of(t: Table) -> object:
    """The outcome's ``kind`` as written (None: none), to default the base before the outcome."""
    raw = t.raw("outcome")
    return raw.get("kind") if isinstance(raw, Mapping) else None


def _benchmark(o: Table, kind: str) -> str:
    if kind == PORTFOLIO_KIND:
        return benchmark_of(o, BENCHMARKS)
    if "benchmark" not in o.names():
        _missing(o, "benchmark")
    return o.choice("benchmark", "", BENCHMARKS)


def _hit_fields(o: Table, kind: str) -> tuple[float | None, str | None, str | None]:
    allowed = EXCESS_MEASURES if kind == "excess_return" else MEASURES  # but its optional one
    measure = o.choice("measure", "", allowed) if "measure" in o.names() else None
    direction = o.choice("direction", "", DIRECTIONS) if "direction" in o.names() else None
    target, own = o.number("target", None), None if kind == "excess_return" else measure
    for key, value in {"target": target, "measure": own, "direction": direction}.items():
        if kind == "hit_target" and value is None:
            raise ConfigurationError(f"{o.where} {key}: required for a hit_target outcome")
        if kind != "hit_target" and value is not None:
            raise ConfigurationError(f"{o.where} {key}: only a hit_target outcome has one")
    return target, measure, direction


def _outcome_of(o: Table, schedule: str, base: str = "universe") -> Outcome:
    kind = o.choice("kind", "", OUTCOME_KINDS) if "kind" in o.names() else _missing(o, "kind")
    benchmark = _benchmark(o, kind)
    named.check_raw_returns(o.where, kind, benchmark, base == named.OUT_OF_WINDOW)
    if kind in (MODEL_KIND, chain.CHAIN_KIND) and benchmark != "none":
        raise ConfigurationError(
            f"{o.where} benchmark: an {kind} is a P&L on the underlying, "
            f"it has no benchmark: use 'none'"
        )
    horizons = _horizons(o)
    offset = o.integer("start_offset_sessions", 0)
    event = event_class(schedule)
    window = window_name(schedule)
    if window is not None:
        if offset != 1:
            raise ConfigurationError(
                f"{o.where} start_offset_sessions: a calendar window starts at the session after "
                f"the decision session (D = S - 1), so 1, got {offset}"
            )
        if horizons != (window_length(window),):
            raise ConfigurationError(
                f"{o.where} horizon_sessions: calendar:{window} is {window_length(window)} "
                f"sessions long, so its one horizon is [{window_length(window)}], "
                f"got {list(horizons)}"
            )
    if event is None and offset < 1:
        raise ConfigurationError(
            f"{o.where} start_offset_sessions: the screen runs after the decision session's "
            f"close, so the entry session is at least 1 session later (>= 1), got {offset}"
        )
    if event is not None and offset < 1 and event not in ANNOUNCED_AHEAD:
        raise ConfigurationError(
            f"{o.where} start_offset_sessions: an entry before the event needs it announced "
            f"ahead ({list(ANNOUNCED_AHEAD)}); {event!r} is known when it happens, so the "
            f"offset from its anchor is >= 1, got {offset}"
        )
    target, measure, direction = _hit_fields(o, kind)
    drawdown = o.number("max_drawdown", None, 0)
    if drawdown is not None and not 0 < drawdown <= 1:
        raise ConfigurationError(f"{o.where} max_drawdown: expected a fraction in (0, 1]")
    structure, strike_delta, otm_pct, iv_field = chain.option_fields(o, kind)
    if kind == MODEL_KIND:
        chain.check_tenor(o, horizons, iv_field)
    side = o.choice("side", LONG, SIDES)
    borrow = o.number("borrow_bps_annual", None, 0)
    check_side(o, side, borrow, kind, drawdown)
    hold_rank = hold_rank_of(o, side, kind, schedule, SCHEDULES, horizons)
    weighting, vol_field = weighting_of(o, kind)
    vol_target, vol_window, vol_return_field = vol_target_of(o, kind)
    check_portfolio(o, kind, side, drawdown, hold_rank is not None, schedule, SCHEDULES, horizons)
    return Outcome(
        kind=kind,
        horizon_sessions=horizons,
        benchmark=benchmark,
        start_offset_sessions=offset,
        target=target,
        max_drawdown=drawdown,
        cost_bps=o.number("cost_bps", None, 0),
        measure=measure,
        direction=direction,
        structure=structure,
        strike_delta=strike_delta,
        otm_pct=otm_pct,
        iv_field=iv_field,
        side=side,
        borrow_bps_annual=borrow,
        tenor_days=chain.chain_tenor(o, kind),
        pair_field=pair_field_of(o, kind == PAIR_KIND, benchmark, side, drawdown),
        hold_rank=hold_rank,
        weighting=weighting,
        vol_field=vol_field,
        vol_target=vol_target,
        vol_window=vol_window,
        vol_return_field=vol_return_field,
        canary=canary_of(o, kind),
    )


def _horizons(o: Table) -> tuple[int, ...]:
    raw = o.raw("horizon_sessions")
    numbers = isinstance(raw, list) and all(type(h) is int and h >= 1 for h in raw)
    if not numbers or not raw or raw != sorted(set(raw)):
        raise ConfigurationError(
            f"{o.where} horizon_sessions: expected one or more ascending, distinct integers "
            f">= 1, got {raw!r}"
        )
    return tuple(raw)


def _universe(t: Table, edge_id: str) -> str | Selection:
    raw = t.raw("universe")
    if isinstance(raw, str):
        return validate_id("selection", raw)
    if isinstance(raw, Mapping):
        return parse_selection({"name": edge_id, **raw}, f"{t.where} universe")
    raise ConfigurationError(
        f"{t.where} universe: expected a selection preset name or an inline selection "
        f"([universe] where = ...), got {raw!r}"
    )


def _variants(
    t: Table,
    schedule: str,
    edge_id: str,
    universe: str | Selection,
    edge_base: str,
    edge_picks: str,
) -> tuple[EdgeVariant, ...]:
    raw = t.raw("variants")
    if raw is None:
        return ()
    if not isinstance(raw, list) or not all(isinstance(v, Mapping) for v in raw):
        raise ConfigurationError(f"{t.where} variants: expected [[variants]] tables")
    base = t.raw("outcome") or {}
    found: list[EdgeVariant] = []
    for i, item in enumerate(raw):
        v = Table(item, f"{t.where} [[variants]][{i}]")
        v.only(VARIANT_KEYS)
        vid = validate_id("variant", _required(v, "id"))
        if vid == MAIN or vid in {x.id for x in found}:
            raise ConfigurationError(f"{v.where} id: {vid!r} is reserved or listed twice")
        over = v.table("outcome", OUTCOME_KEYS)
        kept = (
            base
            if "kind" not in over.names() or over.raw("kind") == base.get("kind")
            else {k: x for k, x in base.items() if k in SHARED_KEYS}
        )  # a variant of another kind drops the base's kind-specific keys
        merged = Table({**kept, **{k: over.raw(k) for k in over.names()}}, f"{v.where} outcome")
        v_base = _base(v, schedule) if "base" in v.names() else None
        named.check_variants(v.where, v_base, edge_base)
        _picks(v, schedule, v_base or edge_base, edge_picks)  # the effective pair is checked
        found.append(
            EdgeVariant(
                id=vid,
                outcome=_outcome_of(merged, schedule),
                universe=_universe(v, f"{edge_id}-{vid}") if "universe" in v.names() else universe,
                base=v_base,
                picks=v.choice("picks", "event", PICKS) if "picks" in v.names() else None,
            )
        )
    return tuple(found)


def _top_k(t: Table) -> int | None:
    raw = t.raw("top_k")
    if raw == "all":
        return None
    if type(raw) is int and raw >= 1:
        return raw
    raise ConfigurationError(f"{t.where} top_k: expected an integer >= 1 or 'all', got {raw!r}")


def _scorer_features(t: Table) -> tuple[str, ...]:
    if t.raw("scorer") is None:
        return ()
    found = t.table("scorer", ("features",)).strings("features", ())
    if not found or len(set(found)) != len(found):
        raise ConfigurationError(f"{t.where} scorer.features: one or more distinct fields")
    return found


def _compared(t: Table) -> tuple[Compared, ...]:
    if t.raw("implementation") is None:
        return ()
    found = []
    for c in t.table("implementation", IMPLEMENTATION_KEYS).tables("compared"):
        c.only(COMPARED_KEYS)
        for key in COMPARED_KEYS:
            if key not in c.names():
                _missing(c, key)
        found.append(
            Compared(
                horizon=c.integer("horizon", 0, 1),
                screener=validate_id("screener", c.text("screener", "")),
                lift=c.number("lift", 0.0),
                decile_spread=c.number("decile_spread", 0.0),
                sessions=c.integer("sessions", 0, 0),
                decile_sessions=c.integer("decile_sessions", 0, 0),
            )
        )
    return tuple(found)


def _promoted(t: Table) -> str | None:
    """The promoted screener; required beside ``compared`` and in a table that declares no
    ``horizon`` (an empty ``[implementation]`` declares nothing)."""
    if t.raw("implementation") is None:
        return None
    sub = t.table("implementation", IMPLEMENTATION_KEYS)
    text = sub.text("promoted", "")
    if not text and "horizon" in sub.names() and "compared" not in sub.names():
        return None
    return validate_id("screener", text or _missing(sub, "promoted"))


def _basis_horizon(t: Table, outcome: Outcome) -> int | None:
    """``[implementation] horizon``: one of the outcome's horizons (ADR 0065), else None."""
    if t.raw("implementation") is None:
        return None
    sub = t.table("implementation", IMPLEMENTATION_KEYS)
    if "horizon" not in sub.names():
        return None
    horizon = sub.integer("horizon", 0, 1)
    if horizon not in outcome.horizon_sessions:
        raise ConfigurationError(
            f"{sub.where} horizon: {horizon} is not one of the outcome's horizon_sessions "
            f"{list(outcome.horizon_sessions)}"
        )
    return horizon


def expand_baselines(
    baselines: tuple[str, ...], standard: tuple[str, ...], screeners: tuple[str, ...]
) -> tuple[str, ...]:
    """``baselines`` with ``STANDARD`` replaced, in place, by the site's standard decoys: those
    not already listed and not the edge's own screeners (a screener is never its own baseline)."""
    if STANDARD not in baselines:
        return baselines
    listed = {*baselines, *screeners}
    out: list[str] = []
    for b in baselines:
        out += [d for d in standard if d not in listed and d not in out] if b == STANDARD else [b]
    return tuple(out)


def _ids(t: Table, key: str, tokens: tuple[str, ...] = ()) -> tuple[str, ...]:
    found = tuple(s if s in tokens else validate_id("screener", s) for s in t.strings(key, ()))
    if len(set(found)) != len(found):
        raise ConfigurationError(f"{t.where} {key}: a screener is listed twice: {list(found)}")
    return found


def _sources(t: Table) -> tuple[Source, ...]:
    raw = t.raw("sources")
    if not isinstance(raw, list) or not raw or not all(isinstance(s, Mapping) for s in raw):
        raise ConfigurationError(f"{t.where} sources: expected one or more [[sources]] tables")
    found = []
    for i, item in enumerate(raw):
        s = Table(item, f"{t.where} [[sources]][{i}]")
        s.only(("title", "url"))
        url = _prose(s, "url")
        if url and not url.startswith("https://"):
            raise ConfigurationError(f"{s.where} url: expected an https:// address, got {url!r}")
        found.append(Source(title=_required(s, "title"), url=url))
    return tuple(found)


def _quality_bar(t: Table, closed: bool) -> dict[str, str]:
    if t.raw("quality_bar") is None and not closed:
        _missing(t, "quality_bar")
    bar = t.table("quality_bar", QUALITY_BAR)
    return {key: _answer(bar, key, closed) for key in QUALITY_BAR}
