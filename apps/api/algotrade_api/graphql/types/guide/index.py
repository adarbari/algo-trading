"""``GuideIndex``: what the Guide holds, in the order the spec fixes (ADR 0051), with the
counts the server computes."""

from typing import Self

import strawberry

from algotrade.services.read.guide import index


@strawberry.type(
    description="A Guide section in order: `entries`, how many entries it has (0: none yet)"
)
class GuideSection:
    id: str
    title: str
    purpose: str
    entries: int

    @classmethod
    def of(cls, d: index.GuideSection) -> Self:
        return cls(id=d.id, title=d.title, purpose=d.purpose, entries=d.entries)


@strawberry.type(description="A field-guide theme and the number of fields it guides")
class GuideTheme:
    theme: str
    fields: int

    @classmethod
    def of(cls, d: index.GuideTheme) -> Self:
        return cls(theme=d.theme, fields=d.fields)


@strawberry.type(description="Field themes grouped in the order a screen uses them")
class GuideThemeGroup:
    id: str
    title: str
    themes: list[GuideTheme]

    @classmethod
    def of(cls, d: index.GuideThemeGroup) -> Self:
        return cls(id=d.id, title=d.title, themes=[GuideTheme.of(t) for t in d.themes])


@strawberry.type(
    description="An intent a trader has and the number of fields with a criterion for it"
)
class GuideIntent:
    intent: str
    fields: int

    @classmethod
    def of(cls, d: index.GuideIntent) -> Self:
        return cls(intent=d.intent, fields=d.fields)


@strawberry.type(
    description="A situation, the number of fields it fools and `slug`, its page's key"
)
class GuideSituationEntry:
    name: str
    fields: int
    slug: str

    @classmethod
    def of(cls, d: index.GuideSituationEntry) -> Self:
        return cls(name=d.name, fields=d.fields, slug=d.slug)


@strawberry.type(description="A playbook: a site rule-screen preset's id and name")
class GuidePlaybook:
    id: str
    name: str

    @classmethod
    def of(cls, d: index.GuidePlaybook) -> Self:
        return cls(id=d.id, name=d.name)


@strawberry.type(description="A family of playbooks, in reading order")
class GuideFamily:
    id: str
    title: str
    playbooks: list[GuidePlaybook]

    @classmethod
    def of(cls, d: index.GuideFamily) -> Self:
        return cls(id=d.id, title=d.title, playbooks=[GuidePlaybook.of(p) for p in d.playbooks])


@strawberry.type(
    description="A regime indicator card: its key (`Query.guideIndicator(key)`) and "
    "plain-language name"
)
class GuideIndicator:
    key: str
    plain_name: str

    @classmethod
    def of(cls, d: index.GuideIndicator) -> Self:
        return cls(key=d.key, plain_name=d.plain_name)


@strawberry.type(
    description="A reference market fall: its key (its page's slug, `Query.guideEpisode(slug)`) "
    "and name"
)
class GuideEpisode:
    key: str
    name: str

    @classmethod
    def of(cls, d: index.GuideEpisode) -> Self:
        return cls(key=d.key, name=d.name)


@strawberry.type(
    description="A Start here page: its id (`Query.guideStartPage(id)`), number, title and "
    "one-line summary"
)
class GuideStartEntry:
    id: str
    order: int
    title: str
    summary: str

    @classmethod
    def of(cls, d: index.GuideStartEntry) -> Self:
        return cls(id=d.id, order=d.order, title=d.title, summary=d.summary)


@strawberry.type(
    description="A glossary term: its id (`Query.guideTerm(id)`), the term as the app writes "
    "it and `short`, one sentence (the help button's hover)"
)
class GuideTermEntry:
    id: str
    term: str
    short: str

    @classmethod
    def of(cls, d: index.GuideTermEntry) -> Self:
        return cls(id=d.id, term=d.term, short=d.short)


@strawberry.type(
    description="What the Guide holds (ADR 0051): the sections in order with entry counts, the "
    "field theme groups, the intents (most fields first), the situations, the playbooks by "
    "family, the regime indicators, the reference episodes, the Start here pages in order and "
    "the glossary terms"
)
class GuideIndex:
    sections: list[GuideSection]
    theme_groups: list[GuideThemeGroup]
    intents: list[GuideIntent]
    situations: list[GuideSituationEntry]
    families: list[GuideFamily]
    indicators: list[GuideIndicator]
    episodes: list[GuideEpisode]
    start_pages: list[GuideStartEntry]
    terms: list[GuideTermEntry]

    @classmethod
    def of(cls, d: index.GuideIndex) -> Self:
        return cls(
            sections=[GuideSection.of(s) for s in d.sections],
            theme_groups=[GuideThemeGroup.of(g) for g in d.theme_groups],
            intents=[GuideIntent.of(i) for i in d.intents],
            situations=[GuideSituationEntry.of(s) for s in d.situations],
            families=[GuideFamily.of(f) for f in d.families],
            indicators=[GuideIndicator.of(i) for i in d.indicators],
            episodes=[GuideEpisode.of(e) for e in d.episodes],
            start_pages=[GuideStartEntry.of(p) for p in d.start_pages],
            terms=[GuideTermEntry.of(t) for t in d.terms],
        )
