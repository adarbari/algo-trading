"""When each regime signal flagged and cleared around one reference episode (ADR 0047, ranged
read under ADR 0036): for the indicators of ``config/site/regime/cards.toml`` and for the
screener gate, the first session of the first ON run overlapping ``[peak - lookback, trough]``
and the first session after it where the signal was not ON, counted in exchange sessions from
the episode's peak (negative: before it) and from its trough.

Point in time: the window ends at ``min(ctx.session, trough + clear_horizon)``, so a session
never sees a verdict stored after it. Every session's verdict is that session's own stored
``<card feature>_on`` (the gate: its own stored regime label against ``gate_labels``); a verdict
counts only when it is a bool. A null or absent one is unknown: it neither flags nor clears
(the run goes on across it) and nothing is carried forward from another session. A run already
ON at the window's first stored session starts there (the true start is earlier). ``cleared_day``
is ``None`` while the signal is still ON at the window's end.

``never_fired``: verdicts are stored and every one is false. No stored verdict in the window at
all is never ``never_fired`` but an ``unknown`` saying why (field not in the catalogue, or
nothing stored). ``flagged_day`` ``None`` with neither is a signal that first turned ON only
after the trough. Windows, labels and the episode come from ``episodes.toml``; the cards from
``cards.toml``."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from algotrade.config.site.regime.cards import load_cards
from algotrade.config.site.regime.episodes import load_episodes
from algotrade.core.model.instruments import market_id
from algotrade.core.time.calendar import next_session, session_offset, sessions_ending
from algotrade.core.views.feature_view import FeatureValue as Scalar
from algotrade.services.read.availability.cause import feature_cause
from algotrade.services.read.context import ReadContext
from algotrade.services.read.instruments.series import load_series
from algotrade.services.read.market.features import US
from algotrade.services.read.regime.fields import LABEL, ON
from algotrade.services.read.regime.regime import RegimeLabel
from algotrade.services.read.values import Unknown, UnknownCode

GATE = "gate"  # the ``indicator`` of the screener gate's timing


class SignalKind(StrEnum):
    """A fast (market) or slow (macro) indicator, or the screener gate."""

    FAST = "FAST"
    SLOW = "SLOW"
    GATE = "GATE"


@dataclass(frozen=True)
class SignalTiming:
    """One signal around one episode. ``flagged_day`` / ``cleared_day``: sessions from the
    peak (negative: before it); ``flagged_day_from_trough``: from the trough; ``unknown_reason``
    exactly when no verdict is stored in the window."""

    indicator: str
    kind: SignalKind
    flagged_day: int | None
    cleared_day: int | None
    never_fired: bool
    unknown_reason: Unknown | None
    flagged_day_from_trough: int | None


@dataclass(frozen=True)
class EpisodeSignals:
    """The screener gate and every indicator (cards in file order) around one episode."""

    gate: SignalTiming
    indicators: tuple[SignalTiming, ...]


Verdicts = dict[date, bool | None]


def _after(day: date, n: int) -> date:
    for _ in range(n):
        day = next_session(day)
    return day


def _timing(
    indicator: str,
    kind: SignalKind,
    verdicts: Verdicts,
    peak: date,
    trough: date,
    unknown: Unknown | None,
) -> SignalTiming:
    known = [(d, v) for d, v in sorted(verdicts.items()) if v is not None]
    if not known:
        return SignalTiming(indicator, kind, None, None, False, unknown, None)
    flagged = next((d for d, v in known if v and d <= trough), None)
    if flagged is None:
        return SignalTiming(indicator, kind, None, None, not any(v for _, v in known), None, None)
    cleared = next((d for d, v in known if d > flagged and not v), None)
    return SignalTiming(
        indicator,
        kind,
        session_offset(peak, flagged),
        None if cleared is None else session_offset(peak, cleared),
        False,
        None,
        session_offset(trough, flagged),
    )


def _gap(ctx: ReadContext, feature: str, code: UnknownCode, why: str) -> Unknown:
    return Unknown(code, feature_cause(feature, why, code.value, ctx.session.date))


def _gate_verdict(label: object, gate: Sequence[str]) -> bool | None:
    if not isinstance(label, str) or label not in {x.value for x in RegimeLabel} - {"UNKNOWN"}:
        return None
    return label in gate


def load_episode_signals(ctx: ReadContext | None, episode_key: str) -> EpisodeSignals | None:
    """The signal timing of episode ``episode_key`` as ``ctx.session`` knew it; ``None`` for a
    key the site has not declared, an episode the session does not know yet (its trough has
    not come) or no ``ctx`` (a Guide page has no session)."""
    if ctx is None:
        return None
    config = load_episodes(ctx.configs)
    found = next((e for e in config.episodes if e.key == episode_key), None)
    if found is None or found.known_from > ctx.session.date:
        return None
    window = config.timeline
    start = sessions_ending(found.peak, window.lookback_sessions + 1)[0]
    end = min(ctx.session.date, _after(found.trough, window.clear_horizon_sessions))
    cards = load_cards(ctx.configs).cards
    catalogue = ctx.features.field_types("market")
    names = [n for n in (LABEL, *(c.feature + ON for c in cards)) if n in catalogue]
    mid = market_id(US)
    points = (
        load_series(ctx, [mid], names, start, end, entity="market")[mid].points if names else ()
    )
    index = {n: i for i, n in enumerate(names)}

    def read(name: str) -> dict[date, Scalar]:
        if name not in index:
            return {}
        return {p.session: p.values[index[name]] for p in points}

    def unknown(name: str) -> Unknown:
        if name not in catalogue:
            return _gap(ctx, name, UnknownCode.NOT_IN_CATALOGUE, f"{name} is not in the catalogue")
        return _gap(
            ctx, name, UnknownCode.NO_ROW, f"{name} has no stored verdict in {start}..{end}"
        )

    labels = read(LABEL)
    gate = {d: _gate_verdict(v, window.gate_labels) for d, v in labels.items()}
    peak, trough = found.peak, found.trough
    return EpisodeSignals(
        _timing(GATE, SignalKind.GATE, gate, peak, trough, unknown(LABEL)),
        tuple(
            _timing(
                c.key,
                SignalKind(c.pace.upper()),
                {d: v if isinstance(v, bool) else None for d, v in read(c.feature + ON).items()},
                peak,
                trough,
                unknown(c.feature + ON),
            )
            for c in cards
        ),
    )
