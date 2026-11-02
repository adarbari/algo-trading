"""``SetupIdeas``: a tab's Ideas from the picks of setups with a good stored verdict (ADR 0083
decision 2 and its amendment of 2026-11-01): the setups with what each picked, the ranked ideas
under the cap, and the left-out counts by kind. Decided on the server (services/read/ideas)."""

import datetime as dt
from typing import Self

import strawberry
from strawberry.types import Info

from algotrade.services.read.context import ReadContext
from algotrade.services.read.evaluation import edges as edge_reads
from algotrade.services.read.evaluation.positions import state
from algotrade.services.read.ideas import picks
from algotrade.services.read.ideas.setups import Tab
from algotrade_api.graphql.offload import off_loop
from algotrade_api.graphql.types.evaluation.verdict import SetupState
from algotrade_api.graphql.types.instruments.feature import Unknown
from algotrade_api.graphql.types.instruments.instrument import Instrument
from algotrade_api.graphql.types.screens.ideas import IdeaMetric
from algotrade_api.graphql.types.screens.result import ScreenResult

strawberry.enum(
    Tab,
    name="IdeaTab",
    description="An Ideas tab: Stocks (share setups) or Premium (option setups)",
)
IdeaTab = Tab


@strawberry.type(description="Setups (or, for `licence`, picks) left out of the list for `kind`")
class LeftOut:
    kind: str
    count: int

    @classmethod
    def of(cls, d: picks.LeftOut) -> Self:
        return cls(kind=d.kind, count=d.count)


@strawberry.type(description="Another setup that picked the ticker, at its `place` there")
class AlsoIn:
    edge_id: str
    edge_name: str
    place: int

    @classmethod
    def of(cls, d: picks.AlsoIn) -> Self:
        return cls(edge_id=d.edge_id, edge_name=d.edge_name, place=d.place)


@strawberry.type(
    description="A ticker at its best pick: the setup it ranks under (`setupId`), its `place` "
    "there, the other setups that picked it, the stored `result` of that pick (null: its row "
    "could not be read) and its display `metrics` and `watchOut` ids"
)
class SetupIdea:
    rank: int
    instrument_id: str
    instrument: Instrument | None
    setup_id: str
    place: int
    also_in: list[AlsoIn]
    result: ScreenResult | None
    metrics: list[IdeaMetric]
    watch_out: list[str]

    @classmethod
    def of(cls, d: picks.SetupIdea, ctx: ReadContext) -> Self:
        result = d.result
        return cls(
            rank=d.rank,
            instrument_id=d.instrument_id,
            instrument=Instrument.of(d.instrument, ctx) if d.instrument is not None else None,
            setup_id=d.setup_id,
            place=d.place,
            also_in=[AlsoIn.of(a) for a in d.also_in],
            result=ScreenResult.of(result, ctx) if result is not None else None,
            metrics=[IdeaMetric.of(m) for m in d.metrics],
            watch_out=list(d.watch_out),
        )


@strawberry.type(
    description="A setup of the tab with what it picked tonight. `state`: picked, "
    "nothing_picked, not_a_decision_day or unknown (`unknown` says why: the night was not "
    "stored, never read as no picks); `picked`: its picks on the viewer's list before the cap, "
    "`shown`: the ideas under the cap that rank under it. `level` is the stored verdict "
    "(works or promising); the figures are labelled backtested (hypothetical) on the page"
)
class SetupGroup:
    edge_id: str
    name: str
    level: str
    lift_pts: float | None
    oos_trades: int | None
    basis_screener: str
    basis_horizon: int | None
    state: str
    unknown: Unknown | None
    picked: int
    shown: int

    @classmethod
    def of(cls, d: picks.SetupGroup) -> Self:
        return cls(
            edge_id=d.edge_id,
            name=d.name,
            level=d.level,
            lift_pts=d.lift_pts,
            oos_trades=d.oos_trades,
            basis_screener=d.basis_screener,
            basis_horizon=d.basis_horizon,
            state=d.state,
            unknown=Unknown.of(d.unknown) if d.unknown is not None else None,
            picked=d.picked,
            shown=d.shown,
        )

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The setup's state at the served session (ON, OFF, PAUSED or UNKNOWN with "
        "its reason; ADR 0088 decision 16): a group is a setup with a good stored verdict, so "
        "ON or PAUSED; null: no session is served or the setup is not readable"
    )
    async def setup_state(self, info: Info) -> SetupState | None:
        read = await info.context.aread(None)
        found = edge_reads.load_edge(read, self.edge_id) if read is not None else None
        if found is None:
            return None
        decided = await off_loop(state.load_setup_state, read, found)
        return SetupState.of(decided) if decided is not None else None


@strawberry.type(
    description="The Ideas of one tab for the session. `state`: listed (a setup qualifies; a "
    "night that picks nothing is an empty list, never a fall back) or unproven (none does: the "
    "page shows `Query.ideas(tab)` as Unproven). `groups` the qualifying setups, strongest "
    "evidence first; `ideas` at most 15, best first; `total` the ideas before the cap; "
    "`leftOut` counts by kind; `ruleVersion` the ranking rule's; `watchlist`: the ideas under "
    "the cap before the viewer's watchlist kept the watched ones (only those are in `ideas`; "
    "`total`, `picked` and the ranks are the whole list's, `shown` and the licence left-out "
    "count only watched names), null: no "
    "watchlist, no filter"
)
class SetupIdeas:
    session: dt.date
    tab: IdeaTab
    state: str
    rule_version: int
    groups: list[SetupGroup]
    ideas: list[SetupIdea]
    total: int
    left_out: list[LeftOut]
    watchlist: int | None

    @classmethod
    def of(cls, d: picks.SetupPicks, ctx: ReadContext) -> Self:
        return cls(
            session=d.session,
            tab=IdeaTab(d.tab),
            state=d.state,
            rule_version=d.rule_version,
            groups=[SetupGroup.of(g) for g in d.groups],
            ideas=[SetupIdea.of(i, ctx) for i in d.ideas],
            total=d.total,
            left_out=[LeftOut.of(c) for c in d.left_out],
            watchlist=d.watchlist,
        )
