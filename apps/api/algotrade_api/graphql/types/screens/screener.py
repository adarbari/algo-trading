"""``Screener`` and ``ScreenerRun``: a rule screen the user sees (typed identity and config
bookkeeping) and its run for the session, resolved through the request's
``screener_latest_run`` dataloader (THE latest-run rule; none for the session is ``notRun``:
``NOT_RUN``, ADR 0036)."""

import datetime as dt
from typing import Self

import strawberry
from strawberry.types import Info

from algotrade.services.read.context import ReadContext
from algotrade.services.read.screens import runs, screeners
from algotrade_api.graphql.types.instruments.feature import Unknown


@strawberry.type(description="How many rows of a run got one decision")
class DecisionCount:
    decision: str
    count: int

    @classmethod
    def of(cls, d: runs.DecisionCount) -> Self:
        return cls(decision=d.decision, count=d.count)


@strawberry.type(
    description="A screener's run for the session: whose, which version ran, its run record's "
    "status, and every decision with its count over the whole run (`picked`: the tickers it "
    "picked)"
)
class ScreenerRun:
    run_id: str
    config_id: str
    owner: str
    session: dt.date
    status: str | None
    knowledge_ts: dt.datetime
    config_version: int | None
    decisions: list[DecisionCount]
    picked: int

    @classmethod
    def of(cls, d: runs.ScreenerRun) -> Self:
        return cls(
            run_id=d.run_id,
            config_id=d.config_id,
            owner=d.owner,
            session=d.session,
            status=d.status,
            knowledge_ts=d.knowledge_ts,
            config_version=d.config_version,
            decisions=[DecisionCount.of(c) for c in d.decisions],
            picked=d.picked,
        )


@strawberry.type(
    description="A rule screen as the user sees it (their own config, else the site preset): "
    "`owner` is whose runs are its; `latestRun` its run for the session, else `notRun` says "
    "why (NOT_RUN)"
)
class Screener:
    id: str
    owner: str
    scope: str
    name: str
    version: int | None
    hash: str
    ctx: strawberry.Private[ReadContext]

    @classmethod
    def of(cls, d: screeners.Screener, ctx: ReadContext) -> Self:
        return cls(
            id=d.id,
            owner=d.owner,
            scope=d.scope,
            name=d.name,
            version=d.version,
            hash=d.hash,
            ctx=ctx,
        )

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="Its run for the session; null: not run for it (see `notRun`)"
    )
    async def latest_run(self, info: Info) -> ScreenerRun | None:
        found = await self.ctx.loaders.screener_latest_run.load((self.owner, self.id))
        return ScreenerRun.of(found.run) if found.run is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="Why it has no run for the session (NOT_RUN); null: it has one"
    )
    async def not_run(self, info: Info) -> Unknown | None:
        found = await self.ctx.loaders.screener_latest_run.load((self.owner, self.id))
        return Unknown.of(found.not_run) if found.not_run is not None else None
