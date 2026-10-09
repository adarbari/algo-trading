"""``GuideIndicatorDetail``: one regime indicator's Guide page (ADR 0051): its card's
explanation without a session value, linked, with how it is computed, the field it reads and
its reading list."""

from typing import Self

import strawberry

from algotrade.services.read.guide import regime as indicator
from algotrade_api.graphql.types.guide.prose import GuideProse
from algotrade_api.graphql.types.market.indicator import IndicatorLink, TextPart


@strawberry.type(
    description="What an indicator did before one reference fall: `label` as the card writes "
    'it ("2008"), `episode` the slug of the episode it means (null: none)'
)
class GuideIndicatorBefore:
    label: str
    line: GuideProse
    episode: str | None

    @classmethod
    def of(cls, d: indicator.GuideIndicatorBefore) -> Self:
        return cls(label=d.label, line=GuideProse.of(d.line), episode=d.episode)


@strawberry.type(
    description="A regime indicator's Guide page (no session value): `summary` (the "
    "one-liner), why it matters, when it is on, lead time and `trackRecord` (its false "
    "alarms), what it did before each reference fall, all linked; `how` it is computed (terms "
    "linked), the catalogue `feature` it reads and its reading list (`sources`); `pace`: slow "
    "(macro) or fast (market)"
)
class GuideIndicatorDetail:
    key: str
    plain_name: str
    technical_name: str
    pace: str
    summary: GuideProse
    why_it_matters: GuideProse
    what_on_means: GuideProse
    lead_time: GuideProse
    track_record: GuideProse
    before: list[GuideIndicatorBefore]
    how: list[TextPart]
    feature: str
    sources: list[IndicatorLink]

    @classmethod
    def of(cls, d: indicator.GuideIndicatorDetail) -> Self:
        return cls(
            key=d.key,
            plain_name=d.plain_name,
            technical_name=d.technical_name,
            pace=d.pace,
            summary=GuideProse.of(d.summary),
            why_it_matters=GuideProse.of(d.why_it_matters),
            what_on_means=GuideProse.of(d.what_on_means),
            lead_time=GuideProse.of(d.lead_time),
            track_record=GuideProse.of(d.track_record),
            before=[GuideIndicatorBefore.of(b) for b in d.before],
            how=[TextPart.of(p) for p in d.how],
            feature=d.feature,
            sources=[IndicatorLink.of(s) for s in d.sources],
        )
