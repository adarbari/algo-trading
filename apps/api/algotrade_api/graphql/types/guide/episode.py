"""``GuideEpisodeDetail``: one reference market fall's Guide page (ADR 0051): the episode as
its config holds it, its cause and notes linked, and the indicators whose before-line is about
it."""

import datetime as dt
from typing import Self

import strawberry

from algotrade.services.read.guide import episode
from algotrade_api.graphql.types.guide.prose import GuideProse


@strawberry.type(
    description='A regime indicator whose before-line (`label`: "2008") is about the episode'
)
class GuideEpisodeIndicator:
    key: str
    plain_name: str
    label: str
    line: GuideProse

    @classmethod
    def of(cls, d: episode.GuideEpisodeIndicator) -> Self:
        return cls(key=d.key, plain_name=d.plain_name, label=d.label, line=GuideProse.of(d.line))


@strawberry.type(
    description="A reference market fall's Guide page, as the config holds it (no session "
    "gating): `spxDrawdown` / `nasdaqDrawdown` peak-to-trough fractions (zero or negative), "
    "`nberStart` / `nberEnd` the recession's first and last months (null: none), `recovered` "
    "null while the S&P 500 has not regained its peak; `cause` and `notes` linked; the "
    "indicators whose before-line is about it, in card order"
)
class GuideEpisodeDetail:
    slug: str
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
    known_from: dt.date
    cause: GuideProse
    notes: GuideProse
    indicators: list[GuideEpisodeIndicator]

    @classmethod
    def of(cls, d: episode.GuideEpisodeDetail) -> Self:
        return cls(
            slug=d.slug,
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
            known_from=d.known_from,
            cause=GuideProse.of(d.cause),
            notes=GuideProse.of(d.notes),
            indicators=[GuideEpisodeIndicator.of(i) for i in d.indicators],
        )
