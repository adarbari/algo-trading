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
ON at the window's first stored session starts there (``first_known_day`` says when that was).
``cleared_day`` is ``None`` while the signal is still ON at the window's end (the session or
``trough + clear_horizon``).

``state``: ``NEVER_FIRED`` when verdicts are stored up to the trough, every one in the window is
false and they cover at least ``min_coverage`` of the sessions up to the trough; ``UNKNOWN``
(a reason: field not in the catalogue, no verdict stored up to the trough, or too few to tell)
is never ``NEVER_FIRED``; ``LATE`` is a first ON only after the trough.
Windows, labels and the episode come from ``episodes.toml``; the cards from ``cards.toml``."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import date
from enum import StrEnum

from algotrade.config.site.regime.cards import load_cards
from algotrade.config.site.regime.episodes import load_episodes
from algotrade.core.model.instruments import market_id
from algotrade.core.time.calendar import (
    next_session,
    session_offset,
    sessions_between,
    sessions_ending,
)
from algotrade.core.views.feature_view import FeatureValue as Scalar
from algotrade.services.read.availability.cause import feature_cause
from algotrade.services.read.context import ReadContext
from algotrade.services.read.instruments.series import load_series
from algotrade.services.read.market.features import US
from algotrade.services.read.regime.fields import LABEL, ON
from algotrade.services.read.regime.regime import RegimeLabel
from algotrade.services.read.values import Unknown, UnknownCode

GATE = "gate"  # the ``indicator`` of the screener gate's timing


class SignalState(StrEnum):
    """How a signal did: ``LED`` (ON in the window up to the trough), ``LATE`` (first ON only
    after the trough), ``NEVER_FIRED`` (every stored verdict false) or ``UNKNOWN`` (none stored
    up to the trough)."""

    LED = "LED"
    LATE = "LATE"
    NEVER_FIRED = "NEVER_FIRED"
    UNKNOWN = "UNKNOWN"


class SignalKind(StrEnum):
    """A fast (market) or slow (macro) indicator, or the screener gate."""

    FAST = "FAST"
    SLOW = "SLOW"
    GATE = "GATE"


@dataclass(frozen=True)
class SignalTiming:
    """One signal around one episode. ``flagged_day`` / ``cleared_day``: sessions from the
    peak (negative: before it); ``flagged_day_from_trough``: from the trough (positive for
    ``LATE``);
    ``first_known_day``: the first stored verdict's session from the peak, set only when it is
    after the window's start (``flagged_day`` is then not the true start); ``unknown_reason``
    exactly when ``state`` is ``UNKNOWN``; ``verdict_sessions`` of ``window_sessions`` (the
    sessions from the window's start to the trough) have a stored verdict."""

    indicator: str
    kind: SignalKind
    state: SignalState
    flagged_day: int | None
    cleared_day: int | None
    first_known_day: int | None
    never_fired: bool
    unknown_reason: Unknown | None
    flagged_day_from_trough: int | None
    verdict_sessions: int
    window_sessions: int


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
    window: tuple[date, date, date],
    min_coverage: float,
    unknown: Callable[[str | None], Unknown],
) -> SignalTiming:
    start, peak, trough = window
    ordered = [(d, v) for d, v in sorted(verdicts.items()) if v is not None]
    known = [(d, v) for d, v in ordered if d <= trough]
    after = [(d, v) for d, v in ordered if d > trough]
    total = len(sessions_between(start, trough))
    base = SignalTiming(indicator, kind, SignalState.UNKNOWN, None, None, None, False, None, None,
                        len(known), total)  # fmt: skip
    if not known:  # nothing stored up to the trough: a later verdict says nothing about it
        return replace(base, unknown_reason=unknown(None))
    first_known = None if known[0][0] <= start else session_offset(peak, known[0][0])
    state, flagged = SignalState.LED, next((d for d, v in known if v), None)
    if flagged is None:
        flagged = next((d for d, v in after if v), None)
        state = SignalState.NEVER_FIRED if flagged is None else SignalState.LATE
    if flagged is None:
        if len(known) < min_coverage * total:  # too thin to say it never fired
            why = f"verdicts stored for {len(known)} of {total} sessions before the trough"
            return replace(base, first_known_day=first_known, unknown_reason=unknown(why))
        return replace(base, state=state, first_known_day=first_known, never_fired=True)
    cleared = next((d for d, v in [*known, *after] if d > flagged and not v), None)
    return replace(
        base,
        state=state,
        flagged_day=session_offset(peak, flagged),
        cleared_day=None if cleared is None else session_offset(peak, cleared),
        first_known_day=first_known,
        flagged_day_from_trough=session_offset(trough, flagged),
    )


def _gap(ctx: ReadContext, feature: str, code: UnknownCode, why: str) -> Unknown:
    return Unknown(code, feature_cause(feature, why, code.value, ctx.session.date))


def _gate_verdict(label: object, gate: Sequence[str]) -> bool | None:
    if not isinstance(label, str) or label not in {x.value for x in RegimeLabel} - {"UNKNOWN"}:
        return None
    return label in gate


def load_episode_signals(ctx: ReadContext, episode_key: str) -> EpisodeSignals | None:
    """The signal timing of episode ``episode_key`` as ``ctx.session`` knew it; ``None`` for a
    key the site has not declared, an episode the session does not know yet (its trough has
    not come). The same for every caller (site episodes and cards, stored market fields) until
    the next publish (in the key, read first, ADR 0022; the catalogue is not in it: the card
    features and the label are site-only stored fields, the same for every user): kept in
    ``ctx.cache`` (the regime page's History asks for every episode at once, 1.2 s)."""
    key = ("episode-signals", episode_key, ctx.session.date, ctx.reader.visible_seq())
    cached: tuple[EpisodeSignals | None] = ctx.cache.get_or_compute(
        key, lambda: (_signals(ctx, episode_key),)
    )
    return cached[0]


def _signals(ctx: ReadContext, episode_key: str) -> EpisodeSignals | None:
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

    def unknown(name: str) -> Callable[[str | None], Unknown]:
        def gap(why: str | None) -> Unknown:
            if name not in catalogue:
                return _gap(
                    ctx, name, UnknownCode.NOT_IN_CATALOGUE, f"{name} is not in the catalogue"
                )
            detail = why or "no verdict stored before the trough"
            return _gap(ctx, name, UnknownCode.NO_ROW, f"{name}: {detail}")

        return gap

    labels = read(LABEL)
    gate = {d: _gate_verdict(v, window.gate_labels) for d, v in labels.items()}
    peak, trough, cover = found.peak, found.trough, window.min_coverage
    return EpisodeSignals(
        _timing(GATE, SignalKind.GATE, gate, (start, peak, trough), cover, unknown(LABEL)),
        tuple(
            _timing(
                c.key,
                SignalKind(c.pace.upper()),
                {d: v if isinstance(v, bool) else None for d, v in read(c.feature + ON).items()},
                (start, peak, trough),
                cover,
                unknown(c.feature + ON),
            )
            for c in cards
        ),
    )
