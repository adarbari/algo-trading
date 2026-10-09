"""``GuideEntries``: the batched Guide read (ADR 0051, ADR 0037): the entries many help
buttons of one page ask for, answered by one operation instead of one request per button."""

from enum import Enum
from typing import Self

import strawberry

from algotrade.services.read.context import Stores
from algotrade.services.read.guide import episode as episode_page
from algotrade.services.read.guide import indicator as indicator_page
from algotrade.services.read.guide import written as written_page
from algotrade_api.graphql.types.guide.episode import GuideEpisodeDetail
from algotrade_api.graphql.types.guide.indicator import GuideIndicatorDetail
from algotrade_api.graphql.types.guide.written import GuideStartPage, GuideTerm


@strawberry.enum(description="The kinds of Guide entry `guideEntries` reads in a batch")
class GuideEntryKind(Enum):
    INDICATOR = "indicator"
    EPISODE = "episode"
    TERM = "term"
    START = "start"


@strawberry.input(
    description="One entry a page asks for: its `kind` and its `id` (an indicator's key, an "
    "episode's slug, a term's or Start here page's id)"
)
class GuideRef:
    kind: GuideEntryKind
    id: str


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
    def load(cls, ctx: Stores, refs: list[GuideRef]) -> Self:
        """Each distinct ref once, through the same loaders as the single-entry fields."""
        seen = set[tuple[GuideEntryKind, str]]()
        found = cls(indicators=[], episodes=[], terms=[], start_pages=[])
        for ref in refs:
            if (ref.kind, ref.id) in seen:
                continue
            seen.add((ref.kind, ref.id))
            if ref.kind is GuideEntryKind.INDICATOR:
                if (i := indicator_page.load_guide_indicator(ctx, ref.id)) is not None:
                    found.indicators.append(GuideIndicatorDetail.of(i))
            elif ref.kind is GuideEntryKind.EPISODE:
                if (e := episode_page.load_guide_episode(ctx, ref.id)) is not None:
                    found.episodes.append(GuideEpisodeDetail.of(e))
            elif ref.kind is GuideEntryKind.TERM:
                if (t := written_page.load_guide_term(ctx, ref.id)) is not None:
                    found.terms.append(GuideTerm.of(t))
            elif (s := written_page.load_guide_start_page(ctx, ref.id)) is not None:
                found.start_pages.append(GuideStartPage.of(s))
        return found
