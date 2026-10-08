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


@strawberry.type(
    description="One signal around one episode. `flaggedDay` / `clearedDay`: exchange sessions "
    "from the episode's peak (negative: before it, the signal led); `flaggedDayFromTrough`: from "
    "its trough. `flaggedDay` is the first session of the first ON run overlapping the window "
    "before the trough (a run already ON at the window's start counts from there); `clearedDay` "
    "the first later session it was not ON, null while it is still ON at the session. "
    "`neverFired`: verdicts are stored and every one is false. `unknownReason`: set exactly when "
    "no verdict is stored in the window (never `neverFired` then). All three null with neither "
    "set: it turned ON only after the trough"
)
class SignalTiming:
    indicator: str
    kind: timeline.SignalKind
    flagged_day: int | None
    cleared_day: int | None
    never_fired: bool
    unknown_reason: Unknown | None
    flagged_day_from_trough: int | None

    @classmethod
    def of(cls, d: timeline.SignalTiming) -> Self:
        return cls(
            indicator=d.indicator,
            kind=d.kind,
            flagged_day=d.flagged_day,
            cleared_day=d.cleared_day,
            never_fired=d.never_fired,
            unknown_reason=Unknown.of(d.unknown_reason) if d.unknown_reason else None,
            flagged_day_from_trough=d.flagged_day_from_trough,
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
