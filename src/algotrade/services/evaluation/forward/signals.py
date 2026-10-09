"""Tonight's paper picks of one followed edge (ADR 0053 amendment 2026-10-09).

An edge the user follows (``following``) or tries as a new version (``trial``) signals at a
session when its schedule fires there, counted from the session its state began (``since``):
the same decision sessions the backtest uses (``cross_section/sessions.decision_sessions``,
spaced a horizon apart), and the picks are the harness's own (``cross_section/picks``: the
screener's qualified names among the edge's eligible names, best first, the first ``top_k``),
read only at the signal session. The buy session is the entry session S (the decision session
plus the document's start offset) and the sell session the close of the window h sessions
later, both from the trading calendar. An edge the first cut cannot paper trade (an event
schedule, an outcome that needs the implied vol, no screener) or whose screen could not be read
returns no signals and says why: never an empty record that reads as "nothing to buy"."""

from dataclasses import dataclass
from datetime import date

from algotrade.config.edges.document import Edge
from algotrade.config.user import UserContext
from algotrade.core.model.errors import MissingDataError
from algotrade.core.time.calendar import next_session, sessions_between
from algotrade.data import StoreReader
from algotrade.services.configs import resolve_config
from algotrade.services.evaluation.cross_section.harness import MEASURED_COVERAGE, edge_universe
from algotrade.services.evaluation.cross_section.hit import needs_implied_vol
from algotrade.services.evaluation.cross_section.picks import eligible, screen_variant
from algotrade.services.evaluation.cross_section.sessions import decision_sessions, entry_session
from algotrade.storage.configs.store import ConfigStore

PAPER_STATES = ("following", "trial")


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


def due(edge: Edge, session: date) -> bool:
    """Whether the edge's schedule fires at ``session``, counted from the session its state began
    (the session itself when the state has no date)."""
    since = edge.follow.since or session
    if since > session:
        return False
    sessions = sessions_between(since, session)
    fired = decision_sessions(edge.schedule, sessions, edge.outcome.horizon_sessions[0])
    return bool(fired) and fired[-1] == session


def _not_possible(edge: Edge) -> str | None:
    """Why the first cut cannot paper trade ``edge`` (None: it can)."""
    if edge.event_class is not None:
        return "an event schedule is not paper traded yet"
    if needs_implied_vol(edge):
        return "the outcome needs the implied vol, which a paper trade does not read yet"
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
    if not due(edge, session):
        return EdgeSignals(edge.id, session, None, None, horizon)
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
    chosen = [i for i in run.qualified if i in universe.ids]
    picks = chosen if edge.top_k is None else chosen[: edge.top_k]
    buy = entry_session(session, max(edge.outcome.start_offset_sessions, 1))
    sell = advance(buy, horizon)
    return made(tuple(Signal(i, rank, buy, sell) for rank, i in enumerate(picks, start=1)))
