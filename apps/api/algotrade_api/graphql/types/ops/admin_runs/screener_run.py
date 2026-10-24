"""``ScreenerRunEntry`` (one screener run for the Admin tab: whose, when, what version ran, what
it decided and left out) and its frozen comparison with the run before it (``changes``)."""

import datetime as dt
from typing import Self

import strawberry
from strawberry.types import Info

from algotrade.services.read.context import Stores
from algotrade.services.read.ops.admin_runs import screener_runs
from algotrade.services.read.screens import runs
from algotrade_api.graphql.offload import off_loop
from algotrade_api.graphql.types.availability import Unavailable
from algotrade_api.graphql.types.screens.screener import DecisionCount


@strawberry.type(
    description="What a run froze when it wrote: the whole run's `picked` and `paused` counts, "
    "the run it was compared with (`previousRunId`, `previousSession`, `previousVersion`; null: "
    "there was none) and the tickers `newPicks` / `dropped` against it (null: no previous run, "
    "never 0)"
)
class ScreenerRunChanges:
    picked: int
    paused: int
    previous_run_id: str | None
    previous_session: dt.date | None
    previous_version: int | None
    new_picks: int | None
    dropped: int | None

    @classmethod
    def of(cls, d: runs.FrozenRun) -> Self:
        return cls(
            picked=d.picked,
            paused=d.paused,
            previous_run_id=d.previous_run_id,
            previous_session=d.previous_session,
            previous_version=d.previous_version,
            new_picks=d.new_picks,
            dropped=d.dropped,
        )


@strawberry.type(
    description="One screener run of any status: `owner` whose run (`site`: the shared one), "
    "`session` it screened, the run record's `status`, `knowledgeTs` (its start while it has "
    "not finished), the `configVersion` and `configHash` that ran, every decision with its "
    "count over the whole run (`decisions`, `picked`, `paused`: null for a run that never "
    "finished, never 0), the `regime` label it stamped, its `coverage` and the tables it ran "
    "without (`missingTables`, `missingOptionalTables`; `unavailable`: what they leave out)"
)
class ScreenerRunEntry:
    run_id: str
    config_id: str
    owner: str
    session: dt.date
    status: str
    started_at: dt.datetime
    finished_at: dt.datetime | None
    knowledge_ts: dt.datetime
    config_version: int | None
    config_hash: str | None
    decisions: list[DecisionCount] | None
    picked: int | None
    paused: int | None
    regime: str | None
    coverage: str | None
    missing_tables: list[str]
    missing_optional_tables: list[str]
    unavailable: list[Unavailable]
    ctx: strawberry.Private[Stores]

    @classmethod
    def of(cls, d: screener_runs.ScreenerRunEntry, ctx: Stores) -> Self:
        return cls(
            run_id=d.run_id,
            config_id=d.config_id,
            owner=d.owner,
            session=d.session,
            status=d.status,
            started_at=d.started_at,
            finished_at=d.finished_at,
            knowledge_ts=d.knowledge_ts,
            config_version=d.config_version,
            config_hash=d.config_hash,
            decisions=None if d.decisions is None else [DecisionCount.of(c) for c in d.decisions],
            picked=d.picked,
            paused=d.paused,
            regime=d.regime,
            coverage=d.coverage,
            missing_tables=list(d.missing_tables),
            missing_optional_tables=list(d.missing_optional_tables),
            unavailable=[Unavailable.of(u) for u in d.unavailable],
            ctx=ctx,
        )

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="What the run froze against the run before it; null: it has no "
        "`screen_runs` row (a run before the table, or one that never wrote). For the detail "
        "only: it reads one row per run, so asking it in a list is one read per entry"
    )
    async def changes(self, info: Info) -> ScreenerRunChanges | None:
        found = await off_loop(screener_runs.load_screener_run_changes, self.ctx, self.run_id)
        return ScreenerRunChanges.of(found) if found is not None else None
