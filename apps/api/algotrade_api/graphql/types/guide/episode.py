"""``GuideEpisodeDetail``: one reference market fall's Guide page (ADR 0051): the episode as
its config holds it, its cause and notes linked, and the indicators whose before-line is about
it."""

from typing import Self

import strawberry

from algotrade.services.read.guide import regime as guide_episode
from algotrade_api.graphql.types.guide.prose import GuideProse
from algotrade_api.graphql.types.market.regime import Episode


@strawberry.type(
    description='A regime indicator whose before-line (`label`: "2008") is about the episode'
)
class GuideEpisodeIndicator:
    key: str
    plain_name: str
    label: str
    line: GuideProse

    @classmethod
    def of(cls, d: guide_episode.GuideEpisodeIndicator) -> Self:
        return cls(key=d.key, plain_name=d.plain_name, label=d.label, line=GuideProse.of(d.line))


@strawberry.type(
    description="A reference market fall's Guide page: `episode` with every date the config "
    "has (no session gating; its key is the page's slug), `cause` and `notes` linked, the "
    "indicators whose before-line is about it, in card order"
)
class GuideEpisodeDetail:
    episode: Episode
    cause: GuideProse
    notes: GuideProse
    indicators: list[GuideEpisodeIndicator]

    @classmethod
    def of(cls, d: guide_episode.GuideEpisodeDetail) -> Self:
        return cls(
            episode=Episode.of(d.episode),
            cause=GuideProse.of(d.cause),
            notes=GuideProse.of(d.notes),
            indicators=[GuideEpisodeIndicator.of(i) for i in d.indicators],
        )
