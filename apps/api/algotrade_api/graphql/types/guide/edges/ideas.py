"""``GuideIdea``: an idea researched but not built (ADR 0051): the catalogue's verdict and
build feasibility with their glossary terms, and one sentence on why it is not built."""

from typing import Self

import strawberry

from algotrade.services.read.guide.edges import ideas


@strawberry.type(
    description="An idea researched but not built: `mechanism` (the mechanism page's id), the "
    "catalogue's `verdict` (strong, promising, weak, decayed, dead or not_graded: the "
    "published evidence, never our test) with `verdictText`, `feasibilityText` (what building "
    "it would take) with its glossary term and `whyNotBuilt`, one plain sentence"
)
class GuideIdea:
    id: str
    title: str
    mechanism: str
    verdict: str
    verdict_text: str
    feasibility_text: str
    feasibility_term: str
    why_not_built: str

    @classmethod
    def of(cls, d: ideas.GuideIdea) -> Self:
        return cls(
            id=d.id,
            title=d.title,
            mechanism=d.mechanism,
            verdict=d.verdict,
            verdict_text=d.verdict_text,
            feasibility_text=d.feasibility_text,
            feasibility_term=d.feasibility_term,
            why_not_built=d.why_not_built,
        )
