"""``MarketRegime`` (ADR 0047): the session's regime as market weather, its scores, every
indicator card with its value, the sizing rule in force and, on request, the label's history as
bands over a window. UNKNOWN (with its reason) while the regime is not stored for the session."""

import datetime as dt
from typing import Self

import strawberry
from strawberry.types import Info

from algotrade.services.read.context import ReadContext
from algotrade.services.read.regime import episodes as episodes_read
from algotrade.services.read.regime import history, regime
from algotrade_api.graphql.offload import off_loop
from algotrade_api.graphql.types.instruments.feature import Unknown
from algotrade_api.graphql.types.market.indicator import RegimeIndicator

strawberry.enum(regime.RegimeLabel, description="The regime; UNKNOWN when it is not stored")


@strawberry.type(
    description="A 0-100 score; `value` is null exactly when `unknown` says why. `feature`: its "
    "catalogue field; `coverageFeature`: the field of the share of its weight known (null: "
    "fragility has none); `threshold`: at or above it the score is high for the label (null: "
    "context only)"
)
class RegimeScore:
    value: float | None
    unknown: Unknown | None
    feature: str
    coverage_feature: str | None
    threshold: float | None

    @classmethod
    def of(cls, d: regime.RegimeScore) -> Self:
        return cls(
            value=d.value,
            unknown=Unknown.of(d.unknown) if d.unknown is not None else None,
            feature=d.feature,
            coverage_feature=d.coverage_feature,
            threshold=d.threshold,
        )


@strawberry.type(
    description="`macroRisk` (slow, weekly), `marketStress` (fast, daily) and `fragility` "
    "(context only: it never changes the label); `macroEarly` and `macroConfirming`, the macro "
    "score's two tiers (`macroRisk` is the higher; either at or above its threshold makes "
    "macro risk high)"
)
class RegimeScores:
    macro_risk: RegimeScore
    market_stress: RegimeScore
    fragility: RegimeScore
    macro_early: RegimeScore
    macro_confirming: RegimeScore

    @classmethod
    def of(cls, d: regime.RegimeScores) -> Self:
        return cls(
            macro_risk=RegimeScore.of(d.macro_risk),
            market_stress=RegimeScore.of(d.market_stress),
            fragility=RegimeScore.of(d.fragility),
            macro_early=RegimeScore.of(d.macro_early),
            macro_confirming=RegimeScore.of(d.macro_confirming),
        )


@strawberry.type(
    description="New positions are sized at `multiplier` of the normal size in `label`"
)
class LabelSize:
    label: regime.RegimeLabel
    multiplier: float

    @classmethod
    def of(cls, d: regime.LabelSize) -> Self:
        return cls(label=d.label, multiplier=d.multiplier)


@strawberry.type(
    description="One of the caller's screeners and the labels its picks are PAUSED in, calmest "
    "first, as the config layers resolve it for them; `enabled`: its `[regime]` gate is on "
    "(off, nothing is paused)"
)
class ScreenerGate:
    screener_id: str
    name: str
    enabled: bool
    pause_in: list[regime.RegimeLabel]

    @classmethod
    def of(cls, d: regime.ScreenerGate) -> Self:
        return cls(
            screener_id=d.screener_id, name=d.name, enabled=d.enabled, pause_in=list(d.pause_in)
        )


@strawberry.type(
    description="The sizing rule in force for the caller: new positions are sized at "
    "`multiplier` of the normal size while the regime is `label` (null: the regime is UNKNOWN). "
    "`enabled`: the gate is on (off: sizes are 100% and nothing pauses); `multipliers` per "
    "label (the site's `[regime]`), `unknownMultiplier` for a label not stored, and "
    "`screeners`: each of the caller's screeners with the labels it pauses in"
)
class RegimeSizing:
    label: regime.RegimeLabel
    multiplier: float | None
    enabled: bool
    multipliers: list[LabelSize]
    unknown_multiplier: float
    screeners: list[ScreenerGate]

    @classmethod
    def of(cls, d: regime.RegimeSizing) -> Self:
        return cls(
            label=d.label,
            multiplier=d.multiplier,
            enabled=d.enabled,
            multipliers=[LabelSize.of(m) for m in d.multipliers],
            unknown_multiplier=d.unknown_multiplier,
            screeners=[ScreenerGate.of(g) for g in d.screeners],
        )


@strawberry.type(
    description="Consecutive sessions `start..end` (the first and last of the run) with the "
    "same regime label; UNKNOWN where none is stored"
)
class RegimeBand:
    start: dt.date
    end: dt.date
    label: regime.RegimeLabel

    @classmethod
    def of(cls, d: history.RegimeBand) -> Self:
        return cls(start=d.start, end=d.end, label=d.label)


@strawberry.type(
    description="One reference market drawdown, with its plain `name`. `recovered`: the "
    "session the S&P 500 regained its peak, null while the session did not know it yet; "
    "`recession` / `nberStart` / `nberEnd`: the NBER recession months (first days) it "
    "overlapped, shown only once NBER had announced them (`kind` reads `shock` until the "
    "peak is announced; `nberEnd` is null until the trough is). Listed from `knownFrom` "
    "(its trough)"
)
class Episode:
    key: str
    name: str
    kind: str
    peak: dt.date
    trough: dt.date
    recovered: dt.date | None
    spx_drawdown: float
    nasdaq_drawdown: float
    recession: bool
    nber_start: dt.date | None
    nber_end: dt.date | None
    cause: str
    notes: str
    known_from: dt.date

    @classmethod
    def of(cls, d: episodes_read.Episode) -> Self:
        return cls(
            key=d.key,
            name=d.name,
            kind=d.kind,
            peak=d.peak,
            trough=d.trough,
            recovered=d.recovered,
            spx_drawdown=d.spx_drawdown,
            nasdaq_drawdown=d.nasdaq_drawdown,
            recession=d.recession,
            nber_start=d.nber_start,
            nber_end=d.nber_end,
            cause=d.cause,
            notes=d.notes,
            known_from=d.known_from,
        )


@strawberry.type(
    description="One NBER recession as the session knew it: `start` / `end` are the first "
    "days of its peak and trough months; `end` is null while the committee had not yet "
    "dated its end, and the announcement dates are null where none was published or it is "
    "not past"
)
class Recession:
    start: dt.date
    end: dt.date | None
    announced_start: dt.date | None
    announced_end: dt.date | None

    @classmethod
    def of(cls, d: episodes_read.Recession) -> Self:
        return cls(
            start=d.start,
            end=d.end,
            announced_start=d.announced_start,
            announced_end=d.announced_end,
        )


@strawberry.type(
    description="The market regime for the session, as market weather (`plainLabel`: Clear, "
    "Clouds building, Storm, Severe storm). `label` is UNKNOWN exactly when `unknownReason` "
    "says why (the regime is not computed for the session); `headline` is the sentence under "
    "the weather"
)
class MarketRegime:
    session: dt.date
    label: regime.RegimeLabel
    plain_label: str
    headline: str
    scores: RegimeScores
    indicators: list[RegimeIndicator]
    sizing: RegimeSizing
    unknown_reason: Unknown | None
    ctx: strawberry.Private[ReadContext]

    @classmethod
    def of(cls, d: regime.MarketRegime, ctx: ReadContext) -> Self:
        return cls(
            session=d.session,
            label=d.label,
            plain_label=d.plain_label,
            headline=d.headline,
            scores=RegimeScores.of(d.scores),
            indicators=[RegimeIndicator.of(i) for i in d.indicators],
            sizing=RegimeSizing.of(d.sizing),
            unknown_reason=Unknown.of(d.unknown_reason) if d.unknown_reason else None,
            ctx=ctx,
        )

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The regime label of every exchange session of `start..end` (`end` on or "
        "before the session's date), consecutive equal labels merged into bands, oldest "
        "first; a session with no stored label is an UNKNOWN band"
    )
    async def bands(self, info: Info, start: dt.date, end: dt.date) -> list[RegimeBand]:
        # Off the event loop: one range read of the label table.
        found = await off_loop(history.load_regime_bands, self.ctx, start, end)
        return [RegimeBand.of(b) for b in found]

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The reference drawdowns the session knows (those whose trough has come), "
        "oldest first"
    )
    async def episodes(self, info: Info) -> list[Episode]:
        found = await off_loop(episodes_read.load_regime_episodes, self.ctx)
        return [Episode.of(e) for e in found.episodes]

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The NBER recessions since 1969 the session knows (listed from the day "
        "the committee dated the peak), oldest first"
    )
    async def recessions(self, info: Info) -> list[Recession]:
        found = await off_loop(episodes_read.load_regime_episodes, self.ctx)
        return [Recession.of(r) for r in found.recessions]
