"""What one site edge took at one session, by the harness's own rule (ADR 0081).

For each screener an edge lists, one ``EdgePicks`` per session: ``picked`` when the edge decides
there (``pick_ids``: a long outcome's picks are the screener's qualified names inside the edge's
universe, and an event schedule's event names, best first, the first ``top_k``:
``picks.long_picks``, the rule the harness and the paper record use; a ``short`` or ``long_short``
outcome's are ``picks.side_picks``, the harness's own legs ranked by the edge's score, with
``pick_sides`` the side of each, ADR 0088 decision 9), ``gate_closed`` when the setup gate is closed
at the session (read as ``paused``, with the gate's reason), ``not_decision_day`` when its schedule
does not fire, ``unjudged`` when its outcome holds a book (a portfolio outcome's weights are
replayed from the book, not ranked here) and ``skipped`` with the reason when the data to decide was
missing or the gate's state unknown. Reads only what was known at the session (``screen_variant``
and ``eligible`` are point in time) and no outcome. A screener's run is made once per session
whatever the number of edges that list it (``Night``)."""

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from functools import cached_property

from algotrade.config.edges.document import Edge
from algotrade.config.edges.portfolio import PORTFOLIO_KIND
from algotrade.config.site.settings import load_verdict
from algotrade.config.user import UserContext
from algotrade.core.model.errors import ConfigurationError, MissingDataError
from algotrade.core.model.predicates import Group
from algotrade.core.time.calendar import sessions_between
from algotrade.data import StoreReader
from algotrade.engines.screening.gate import UNDECIDED, UNKNOWN
from algotrade.services.configs import field_catalog, resolve_config
from algotrade.services.evaluation.cross_section.events import EventDayMissingError
from algotrade.services.evaluation.cross_section.harness import edge_universe
from algotrade.services.evaluation.cross_section.measuring import (
    MEASURED_COVERAGE,
    Names,
    names_for,
)
from algotrade.services.evaluation.cross_section.picks import (
    MIN_SCORE_COVERAGE,
    Eligible,
    RankedRun,
    SelectionReads,
    long_picks,
    screen_variant,
    side_picks,
)
from algotrade.services.evaluation.cross_section.reads.session import ADV_FIELD, numbers_at
from algotrade.services.evaluation.cross_section.sessions import decision_sessions
from algotrade.services.evaluation.forward.signals import legs_between
from algotrade.services.screening.regime import edge_gate
from algotrade.storage.configs.store import ConfigStore

PICKED, NOT_DECISION_DAY, UNJUDGED, SKIPPED = "picked", "not_decision_day", "unjudged", "skipped"
GATE_CLOSED = "gate_closed"  # the setup gate closed at the session (ADR 0088 decision 7)
STATUSES = (PICKED, GATE_CLOSED, NOT_DECISION_DAY, UNJUDGED, SKIPPED)
EVERY_SESSION = "every_session"
LONG = "long"
AROUND_DAYS = 45  # the calendar days either side of D a month-end or window schedule is read over


@dataclass(frozen=True)
class EdgePicks:
    """One (edge, screener) at one session: ``status`` (``STATUSES``), ``pick_ids`` best first
    (empty unless ``picked``; a ``long_short`` outcome's long leg, then its short leg) with
    ``pick_sides`` the side of each (``long`` or ``short``), ``pick_weights`` a book's weight of
    each (empty: not a book), ``reason`` for ``gate_closed``, ``unjudged`` and ``skipped``,
    ``config_hash`` of the screener's resolved config (None before it was resolved)."""

    edge_id: str
    screener: str
    status: str
    pick_ids: tuple[str, ...] = ()
    reason: str = ""
    top_k: int | None = None
    config_hash: str | None = None
    pick_sides: tuple[str, ...] = ()
    pick_weights: tuple[float, ...] = ()


def _unjudged(edge: Edge) -> str | None:
    """Why the edge's pick is not ranked from the screener's run (None: it is)."""
    if edge.outcome.kind == PORTFOLIO_KIND:
        return "a portfolio outcome holds a book, not the screener's picks"
    return None


def fires(edge: Edge, session: date) -> bool:
    """Whether a plain (non-event) schedule decides at ``session``: every session does (the
    harness spaces its decisions a horizon apart for an independent statistic; the stored picks
    are what the edge would take that session), a month end or a calendar window on its own days
    (``sessions.decision_sessions`` over the sessions around ``session``)."""
    if edge.schedule == EVERY_SESSION:
        return True
    around = sessions_between(
        session - timedelta(days=AROUND_DAYS), session + timedelta(days=AROUND_DAYS)
    )
    # A month end is a decision day whatever the spacing (no earlier month end is read); a window
    # needs its own horizon.
    horizon = 1 if edge.schedule == "month_end" else edge.outcome.horizon_sessions[0]
    return session in decision_sessions(edge.schedule, around, horizon)


@dataclass
class Night:
    """The reads one session's decisions share: a screener's run by config hash (None: its data
    was missing), the universes by selection."""

    reader: StoreReader
    configs: ConfigStore
    user: UserContext
    session: date
    runs: dict[str, RankedRun | str] = field(default_factory=dict)
    selections: SelectionReads = field(init=False)

    def __post_init__(self) -> None:
        self.selections = SelectionReads(self.reader)

    @cached_property
    def adv_floor(self) -> float:
        """The least 20-day dollar volume of a name a short leg may hold (the harness's
        ``capacity_adv_floor_usd``, ``verdict.toml``), read once."""
        return load_verdict(self.configs).capacity_adv_floor_usd

    def run(self, screener: str) -> tuple[str, RankedRun | str]:
        """``(config hash, the screener's run)``; a string for the run is why it has none."""
        config = resolve_config(self.configs, screener, self.user)
        if config.hash not in self.runs:
            try:
                self.runs[config.hash] = screen_variant(self.reader, config, self.session)
            except MissingDataError as missing:
                self.runs[config.hash] = f"no {missing.dataset} for {self.session.isoformat()}"
        return config.hash, self.runs[config.hash]


def _decide(night: Night, edge: Edge, screener: str, names: frozenset[str] | None) -> EdgePicks:
    """``edge``'s picks of ``screener`` at the session; ``names``: an event schedule's names."""
    day = night.session
    try:
        digest, run = night.run(screener)
    except ConfigurationError as error:
        return EdgePicks(edge.id, screener, SKIPPED, reason=str(error), top_k=edge.top_k)
    made = EdgePicks(edge.id, screener, SKIPPED, top_k=edge.top_k, config_hash=digest)
    if isinstance(run, str):
        return replace(made, reason=run)
    if run.coverage not in MEASURED_COVERAGE:
        reason = f"the screen read incomplete data ({run.coverage.value})"
        return replace(made, reason=reason)
    try:
        universe: Eligible = night.selections.eligible(
            edge_universe(night.configs, night.user, edge), day
        )
    except MissingDataError as missing:
        reason = f"no {missing.dataset} for {day.isoformat()}"
        return replace(made, reason=reason)
    found = names_for(edge, universe.ids, names)
    if edge.outcome.side == LONG:
        picks = long_picks(edge, run.qualified, found.pickable)
        return replace(made, status=PICKED, pick_ids=tuple(picks), pick_sides=(LONG,) * len(picks))
    return _sided(night, edge, run, universe, found, made)


def _sided(
    night: Night, edge: Edge, run: RankedRun, universe: Eligible, found: Names, made: EdgePicks
) -> EdgePicks:
    """A ``short`` or ``long_short`` outcome's picks, ranked by score as the harness ranks them:
    too few scores and there is no honest bottom, so the session is skipped as the harness leaves
    it unmeasured. A session with no stored dollar volume for any scored name is skipped too, never
    stored as an empty short leg."""
    if len([i for i in run.scores if i in found.ids]) < MIN_SCORE_COVERAGE * len(found.ids):
        return replace(made, reason="too few names carry the edge's score to rank a short leg")
    day = night.session
    try:
        adv = numbers_at(night.reader, ADV_FIELD, universe.ids, day)
    except MissingDataError as missing:
        return replace(made, reason=f"no {missing.dataset} for {day.isoformat()}")
    if not any(adv.get(i) is not None for i in found.pickable if i in run.scores):
        return replace(made, reason=f"no {ADV_FIELD} for {day.isoformat()}")
    legs, _ = side_picks(edge, run.scores, found.pickable, adv, night.adv_floor)
    ids = tuple(i for _, leg in legs for i in leg)
    sides = tuple(side for side, leg in legs for _ in leg)
    return replace(made, status=PICKED, pick_ids=ids, pick_sides=sides)


def _gate_shut(night: Night, gate: Group) -> tuple[str, str] | None:
    """``(status, reason)`` when the setup gate holds the session's picks back (None: it is open),
    whatever ``[regime].enabled`` says: closed is ``gate_closed`` with the gate's reason, unknown
    is ``skipped`` (fail closed: neither picks)."""
    domains = field_catalog(night.configs).domains
    decision = edge_gate(night.reader, gate, night.session, domains)
    if decision.open:
        return None
    if decision.state == UNDECIDED:
        return SKIPPED, UNKNOWN
    return GATE_CLOSED, decision.reason or "gate closed"


def edge_night(
    night: Night, edge: Edge, wanted: Callable[[str], bool] = lambda _: True
) -> list[EdgePicks]:
    """The rows of ``edge`` at the session, one per listed screener ``wanted`` says to make (a
    resumed run skips what is stored). An edge with no screener has none."""
    screeners = [s for s in edge.screeners if wanted(s)]
    if not screeners:
        return []
    top_k = edge.top_k
    if (why := _unjudged(edge)) is not None:
        return [EdgePicks(edge.id, s, UNJUDGED, reason=why, top_k=top_k) for s in screeners]
    names: frozenset[str] | None = None
    try:
        if edge.event_class is not None:
            legs, events = legs_between(
                night.reader, night.configs, night.user, edge, night.session, night.session,
                night.session,
            )  # fmt: skip
            fired = bool(legs) and events is not None
            names = events.names[night.session] if fired and events is not None else None
        else:
            fired = fires(edge, night.session)
    except (MissingDataError, ConfigurationError) as error:
        day = error.day if isinstance(error, EventDayMissingError) else night.session
        why = (
            f"no {error.dataset} for {day.isoformat()}"
            if isinstance(error, MissingDataError)
            else str(error)
        )
        return [EdgePicks(edge.id, s, SKIPPED, reason=why, top_k=top_k) for s in screeners]
    if not fired:
        return [EdgePicks(edge.id, s, NOT_DECISION_DAY, top_k=top_k) for s in screeners]
    if edge.gate is not None and (shut := _gate_shut(night, edge.gate)) is not None:
        status, why = shut
        return [EdgePicks(edge.id, s, status, reason=why, top_k=top_k) for s in screeners]
    return [_decide(night, edge, s, names) for s in screeners]
