"""``GuideEntries``: the batched Guide read (ADR 0051, ADR 0037): the entries many help
buttons of one page ask for, answered by one operation instead of one request per button."""

from typing import Self

import strawberry

from algotrade.services.read.guide import entries
from algotrade_api.graphql.types.guide.episode import GuideEpisodeDetail
from algotrade_api.graphql.types.guide.indicator import GuideIndicatorDetail
from algotrade_api.graphql.types.guide.written import GuideStartPage, GuideTerm

strawberry.enum(entries.GuideEntryKind, description="The kinds of Guide entry `guideEntries` reads")
strawberry.input(
    entries.GuideRef,
    description="One entry a page asks for: its `kind` and its `id` (an indicator's key, an "
    "episode's slug, a term's or Start here page's id)",
)


@strawberry.type(
    description="The entries found for the refs asked, each list in the order of the refs; a "
    "ref with no entry is left out (the caller matches by key)"
)
class GuideEntries:
    indicators: list[GuideIndicatorDetail]
    episodes: list[GuideEpisodeDetail]
    terms: list[GuideTerm]
    start_pages: list[GuideStartPage]

    @classmethod
    def of(cls, d: entries.GuideEntries) -> Self:
        return cls(
            indicators=[GuideIndicatorDetail.of(i) for i in d.indicators],
            episodes=[GuideEpisodeDetail.of(e) for e in d.episodes],
            terms=[GuideTerm.of(t) for t in d.terms],
            start_pages=[GuideStartPage.of(p) for p in d.start_pages],
        )
