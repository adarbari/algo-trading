"""``GuideEdgeEntry`` and ``GuideEdgeRow``: one site edge's Guide page and the row that lists it
(ADR 0051), read from the edge document alone: no harness result, no live number."""

from typing import Self

import strawberry

from algotrade.services.read.guide import prose
from algotrade.services.read.guide.edges import edge
from algotrade_api.graphql.types.guide.prose import GuideProse


@strawberry.type(description="A mechanism page by its id and title")
class GuideMechanismRef:
    id: str
    title: str

    @classmethod
    def of(cls, d: edge.GuideMechanismRef) -> Self:
        return cls(id=d.id, title=d.title)


@strawberry.type(
    description="An edge in a list: `asset` (stocks, etfs or options) with `assetText`, `side` "
    "(long, short or long_short) with its glossary term, `holdingSessions` with `holdingText` "
    "and `holdingBand` (short, medium or long), `status` and `mechanism` (the mechanism "
    "page's id; null: not set)"
)
class GuideEdgeRow:
    id: str
    name: str
    thesis: str
    mechanism: str | None
    asset: str
    asset_text: str
    side: str
    side_term: str
    holding_sessions: list[int]
    holding_text: str
    holding_band: str
    status: str

    @classmethod
    def of(cls, d: edge.GuideEdgeRow) -> Self:
        return cls(
            id=d.id,
            name=d.name,
            thesis=d.thesis,
            mechanism=d.mechanism,
            asset=d.asset,
            asset_text=d.asset_text,
            side=d.side,
            side_term=d.side_term,
            holding_sessions=list(d.holding_sessions),
            holding_text=d.holding_text,
            holding_band=d.holding_band,
            status=d.status,
        )


@strawberry.type(
    description="What the paper behind an edge reports: `measure` in words, the published "
    "`figure`, what to `expect` once the `haircut` is taken off (a planning haircut by the "
    "paper's `leg`), the horizon, the sample in years (null: not stated) and the `source`; "
    "display only, never a verdict. `terms`: glossary terms for its help buttons"
)
class GuideEdgeResearch:
    measure: str
    figure: str
    expect: str
    haircut: str
    horizon_text: str
    leg: str
    sample: str | None
    source: str
    terms: list[str]

    @classmethod
    def of(cls, d: edge.GuideEdgeResearch) -> Self:
        return cls(
            measure=d.measure,
            figure=d.figure,
            expect=d.expect,
            haircut=d.haircut,
            horizon_text=d.horizon_text,
            leg=d.leg,
            sample=d.sample,
            source=d.source,
            terms=list(d.terms),
        )


@strawberry.type(
    description="One line of how an edge is tested: `key` (outcome, horizon, trigger, entry, "
    "universe, picks, cost, baselines or frozen), its `title`, the `text` and the glossary "
    "`term` that explains it (null: none)"
)
class GuideEdgeFact:
    key: str
    title: str
    text: str
    term: str | None

    @classmethod
    def of(cls, d: edge.GuideEdgeFact) -> Self:
        return cls(key=d.key, title=d.title, text=d.text, term=d.term)


@strawberry.type(description="A site playbook among an edge's screeners: id, name and family")
class GuideEdgePlaybook:
    id: str
    name: str
    family: str | None

    @classmethod
    def of(cls, d: edge.GuideEdgePlaybook) -> Self:
        return cls(id=d.id, name=d.name, family=d.family)


@strawberry.type(
    description="A source of the edge document: `title`, `url` (null: none) and its `form` "
    "(Paper, Working paper, Filing or Source)"
)
class GuideEdgeSource:
    title: str
    url: str | None
    form: str

    @classmethod
    def of(cls, d: edge.GuideEdgeSource) -> Self:
        return cls(title=d.title, url=d.url, form=d.form)


@strawberry.type(
    description="A site edge's Guide page (ADR 0051), from its document alone: `summary` (the "
    "row), the mechanism page, the thesis, who is on `otherSide`, why it `lasts`, the `research` "
    "figure with its planning haircut (null: the document has none), how it is tested "
    "(`tests`), how it is built (the site `playbooks` among its screeners and the catalogue "
    "`fields` their criteria read), what fools it (`failureModes`, `decoys`, `rejection`: why a "
    "rejected or blocked edge is), what it costs to trade (`capacity`), `sources`, `related` "
    "edges and the mechanism's glossary terms (`seeAlso`). Null text: not written"
)
class GuideEdgeEntry:
    summary: GuideEdgeRow
    mechanism: GuideMechanismRef | None
    thesis: GuideProse
    other_side: GuideProse
    lasts: GuideProse
    research: GuideEdgeResearch | None
    tests: list[GuideEdgeFact]
    playbooks: list[GuideEdgePlaybook]
    fields: list[str]
    failure_modes: GuideProse | None
    decoys: GuideProse | None
    rejection: GuideProse | None
    capacity: GuideProse | None
    sources: list[GuideEdgeSource]
    related: list[GuideEdgeRow]
    see_also: list[str]

    @classmethod
    def of(cls, d: edge.GuideEdgeEntry) -> Self:
        return cls(
            summary=GuideEdgeRow.of(d.summary),
            mechanism=GuideMechanismRef.of(d.mechanism) if d.mechanism is not None else None,
            thesis=GuideProse.of(d.thesis),
            other_side=GuideProse.of(d.other_side),
            lasts=GuideProse.of(d.lasts),
            research=GuideEdgeResearch.of(d.research) if d.research is not None else None,
            tests=[GuideEdgeFact.of(f) for f in d.tests],
            playbooks=[GuideEdgePlaybook.of(p) for p in d.playbooks],
            fields=list(d.fields),
            failure_modes=_prose(d.failure_modes),
            decoys=_prose(d.decoys),
            rejection=_prose(d.rejection),
            capacity=_prose(d.capacity),
            sources=[GuideEdgeSource.of(s) for s in d.sources],
            related=[GuideEdgeRow.of(r) for r in d.related],
            see_also=list(d.see_also),
        )


def _prose(d: prose.LinkedProse | None) -> GuideProse | None:
    return GuideProse.of(d) if d is not None else None
