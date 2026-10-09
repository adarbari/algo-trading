"""``EpisodeSignals`` (ADR 0047): when each regime indicator and the screener gate flagged and
cleared around one reference episode, as the read model's ``timeline`` computes it. Split from
``regime.py`` (``Episode``)."""

from typing import Self

import strawberry

from algotrade.services.read.regime import timeline
from algotrade_api.graphql.types.instruments.feature import Unknown

strawberry.enum(
    timeline.SignalKind,
    description="A fast (market) or slow (macro) indicator, or the screener gate (GATE)",
)


strawberry.enum(
    timeline.SignalState,
    description="How a signal did: LED (ON up to the trough), LATE (first ON only after it), "
    "NEVER_FIRED (every stored verdict false) or UNKNOWN (no verdict stored up to the trough)",
)


@strawberry.type(
    description="One signal around one episode; `state` says how it did. `flaggedDay` / "
    "`clearedDay`: exchange sessions from the episode's peak (negative: before it, the signal "
    "led); `flaggedDayFromTrough`: from its trough (positive for LATE, where `flaggedDay` is the "
    "first ON session after the trough). `flaggedDay` is the first session of the first ON run "
    "overlapping the window before the trough; `clearedDay` the first later session it was not "
    "ON, null while it is still ON at the session or at the trough plus the clear horizon. "
    "`firstKnownDay`: set when the stored verdicts start after the window's start (sessions "
    "from the peak), so `flaggedDay` is not the true start of a run already ON then. "
    "`unknownReason` is set exactly when `state` is UNKNOWN (never `neverFired` then; also when "
    "too few sessions have a verdict to say it never fired). `verdictSessions` of "
    "`windowSessions` (window start to the trough) have a stored verdict"
)
class SignalTiming:
    indicator: str
    kind: timeline.SignalKind
    state: timeline.SignalState
    flagged_day: int | None
    cleared_day: int | None
    first_known_day: int | None
    never_fired: bool
    unknown_reason: Unknown | None
    flagged_day_from_trough: int | None
    verdict_sessions: int
    window_sessions: int

    @classmethod
    def of(cls, d: timeline.SignalTiming) -> Self:
        return cls(
            indicator=d.indicator,
            kind=d.kind,
            state=d.state,
            flagged_day=d.flagged_day,
            cleared_day=d.cleared_day,
            first_known_day=d.first_known_day,
            never_fired=d.never_fired,
            unknown_reason=Unknown.of(d.unknown_reason) if d.unknown_reason else None,
            flagged_day_from_trough=d.flagged_day_from_trough,
            verdict_sessions=d.verdict_sessions,
            window_sessions=d.window_sessions,
        )


@strawberry.type(
    description="The signal timing around one episode as the session knew it: the screener "
    "`gate` (the regime label in the site's gate labels) and every indicator, cards in file order"
)
class EpisodeSignals:
    gate: SignalTiming
    indicators: list[SignalTiming]

    @classmethod
    def of(cls, d: timeline.EpisodeSignals) -> Self:
        return cls(
            gate=SignalTiming.of(d.gate),
            indicators=[SignalTiming.of(i) for i in d.indicators],
        )
