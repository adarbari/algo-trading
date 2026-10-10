"""Tonight's paper picks of one followed edge (ADR 0053 amendment 2026-10-09).

An edge the user follows (``following``) or tries as a new version (``trial``) signals at a
session when its schedule fires there, counted from the session its state began (``since``):
the same decision sessions the backtest uses (``cross_section/sessions.decision_sessions``,
spaced a horizon apart), and the picks are the harness's own (``cross_section/picks``: the
screener's qualified names among the edge's eligible names, best first, the first ``top_k``),
read only at the signal session. The buy session is the entry session S (the decision session
plus the document's start offset) and the sell session the close of the window h sessions
later, both from the trading calendar. An event schedule (``on_event:``) fires on the harness's
own legs (``sessions.leg_blocks``: the event names read at D, S = D + 1), and its picks are the
qualified names among the event's. An edge the paper record cannot trade (no screener, a
mixed-source implied vol) or whose screen could not be read returns no signals and says why:
never an empty record that reads as "nothing to buy"."""

from dataclasses import dataclass
from datetime import date

from algotrade.config.edges.document import Edge
from algotrade.config.user import UserContext
from algotrade.core.model.errors import MissingDataError
from algotrade.core.time.calendar import (
    next_session,
    sessions_between,
    sessions_ending,
    sessions_to,
)
from algotrade.data import StoreReader
from algotrade.services.configs import resolve_config
from algotrade.services.evaluation.cross_section.events import (
    DEDUPE_SESSIONS,
    EventDayMissingError,
    EventSchedule,
    read_events,
)
from algotrade.services.evaluation.cross_section.harness import (
    MEASURED_COVERAGE,
    MIXED_SOURCE_IV,
    edge_universe,
    iv_field_of,
    names_for,
)
from algotrade.services.evaluation.cross_section.hit import needs_implied_vol
from algotrade.services.evaluation.cross_section.picks import eligible, screen_variant
from algotrade.services.evaluation.cross_section.sessions import Leg, leg_blocks
from algotrade.storage.configs.store import ConfigStore

PAPER_STATES = ("following", "trial")
# Sessions an event schedule reads back to dedupe names. The dedupe is a chain (a name counted
# at X blocks the next DEDUPE_SESSIONS), so the bound is exact unless one name matches three or
# more times within this many sessions (a moved report date): then the first match may lie
# before the window and tonight's count can differ from the backtest's.
EVENT_LOOKBACK = 2 * DEDUPE_SESSIONS


@dataclass(frozen=True)
class Signal:
    """One paper buy: ``rank`` 1 is the screener's best name."""

    instrument_id: str
    rank: int
    buy_session: date
    sell_session: date


@dataclass(frozen=True)
class EdgeSignals:
    """What one edge signalled at one session: ``signals`` (empty when none was due or
    possible), ``skipped`` why a due signal could not be made (None: nothing was wrong)."""

    edge_id: str
    session: date
    screener: str | None
    config_hash: str | None
    horizon: int
    signals: tuple[Signal, ...] = ()
    skipped: str | None = None


def advance(day: date, sessions: int) -> date:
    """``day`` moved ``sessions`` exchange sessions later."""
    for _ in range(sessions):
        day = next_session(day)
    return day


def paper_traded(edge: Edge) -> bool:
    """The user follows the edge (or trials it) from a session on."""
    return edge.follow.state in PAPER_STATES


def legs_between(
    reader: StoreReader,
    configs: ConfigStore,
    user: UserContext,
    edge: Edge,
    first: date,
    last: date,
) -> tuple[list[Leg], EventSchedule | None]:
    """The harness's own legs (``sessions.leg_blocks``) of ``edge`` with a decision session in
    ``first..last``, counted from the session its state began (the session itself when the state
    has no date), and, for an event schedule, the event names by decision session. A plain
    schedule is spaced a horizon apart from ``since``; an event schedule fires on every session
    where a name has the event, read at that session alone (``events.read_events``) with the
    once-per-name dedupe looking ``EVENT_LOOKBACK`` sessions back, so a paper trade is the leg
    the backtest would have taken."""
    since = edge.follow.since or last
    if since > last:
        return [], None
    horizon = edge.outcome.horizon_sessions[0]
    if edge.event_class is None:
        blocks = leg_blocks(edge, None, sessions_between(since, last), horizon)
        return [leg for block in blocks for leg in block if leg.decision >= first], None
    start = max(since, first)
    days = sessions_ending(last, sessions_to(start, last) + 1 + EVENT_LOOKBACK)
    universe = edge_universe(configs, user, edge)
    events = read_events(
        reader,
        edge.event_class,
        edge.outcome.start_offset_sessions,
        days,
        lambda day: eligible(reader, universe, day).ids,
    )
    legs = [leg for block in leg_blocks(edge, events, days, horizon) for leg in block]
    return [leg for leg in legs if leg.decision >= start], events


def _not_possible(edge: Edge) -> str | None:
    """Why the paper record cannot trade ``edge`` (None: it can)."""
    if needs_implied_vol(edge) and iv_field_of(edge) in MIXED_SOURCE_IV:
        return "its implied vol field mixes sources: name one vendor's field"
    if edge.promoted is None and not edge.screeners:
        return "the edge has no screener to take picks from"
    return None


def edge_signals(
    reader: StoreReader, configs: ConfigStore, user: UserContext, edge: Edge, session: date
) -> EdgeSignals:
    """``edge``'s paper picks at ``session`` (none when its schedule does not fire there)."""
    horizon = edge.outcome.horizon_sessions[0]
    if (why := _not_possible(edge)) is not None:
        return EdgeSignals(edge.id, session, None, None, horizon, (), why)
    try:
        legs, events = legs_between(reader, configs, user, edge, session, session)
    except MissingDataError as missing:
        day = missing.day if isinstance(missing, EventDayMissingError) else session
        return EdgeSignals(
            edge.id, session, None, None, horizon, (), f"no {missing.dataset} for {day.isoformat()}"
        )
    if not legs:
        return EdgeSignals(edge.id, session, None, None, horizon)
    (leg,) = legs
    screener = edge.promoted or edge.screeners[0]
    config = resolve_config(configs, screener, user)

    def made(signals: tuple[Signal, ...] = (), skipped: str | None = None) -> EdgeSignals:
        return EdgeSignals(edge.id, session, screener, config.hash, horizon, signals, skipped)

    try:
        run = screen_variant(reader, config, session)
        universe = eligible(reader, edge_universe(configs, user, edge), session)
    except MissingDataError as missing:
        return made(skipped=f"no {missing.dataset} for {session.isoformat()}")
    if run.coverage not in MEASURED_COVERAGE:
        return made(skipped=f"the screen read incomplete data ({run.coverage.value})")
    names = None if events is None else events.names[session]
    pickable = names_for(edge, universe.ids, names).pickable
    chosen = [i for i in run.qualified if i in pickable]
    picks = chosen if edge.top_k is None else chosen[: edge.top_k]
    sell = advance(leg.entry, horizon)
    return made(tuple(Signal(i, rank, leg.entry, sell) for rank, i in enumerate(picks, start=1)))
