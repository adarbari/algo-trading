"""``FeatureTable``: one page of instruments x catalogue features for the session, columnar
(ADR 0038): ``rows[i][j]`` is ``columns[j]``'s value for ``instruments[i]``, null exactly when
``unknown[i][j]`` says why. The client formats a column with ``columns[j].format``."""

import datetime as dt
from typing import Self

import strawberry
from strawberry.scalars import JSON

from algotrade.services.read import values
from algotrade.services.read.availability.cause import UnavailableKind, kind_texts
from algotrade.services.read.context import ReadContext
from algotrade.services.read.instruments import table
from algotrade_api.graphql.types.availability import KindText, Unavailable
from algotrade_api.graphql.types.instruments.feature import FeatureInfo
from algotrade_api.graphql.types.instruments.instrument import Instrument
from algotrade_api.graphql.types.session import Session


@strawberry.type(
    description="Instruments x catalogue features for one session, one page of the rows "
    "matching the filters in the sort order (`total`: every page). `rows[i][j]` is the value "
    "of `columns[j]` for `instruments[i]`, null exactly when `unknown[i][j]` says why "
    "(`reasons[i][j]`: its NullReason when EXPLAINED; `kinds[i][j]`: its public kind, "
    "how a cell is drawn). "
    "`unavailable`: what the tables the filters and sort read have nothing for the session "
    "leave out (no row passes a filter on them)"
)
class FeatureTable:
    session: Session
    universe_snapshot: dt.date | None
    pre_snapshot: bool
    columns: list[FeatureInfo]
    instruments: list[Instrument]
    rows: list[list[JSON | None]]
    unknown: list[list[values.UnknownCode | None]]
    reasons: list[list[values.NullReason | None]]
    kinds: list[list[UnavailableKind | None]]
    sort: str | None
    total: int
    page: int
    size: int
    unavailable: list[Unavailable]

    @classmethod
    def of(cls, d: table.FeatureTable, ctx: ReadContext) -> Self:
        return cls(
            session=Session.of(d.session),
            universe_snapshot=d.universe_snapshot,
            pre_snapshot=d.pre_snapshot,
            columns=[FeatureInfo.of(c) for c in d.columns],
            instruments=[Instrument.of(i, ctx) for i in d.instruments],
            rows=[[JSON(v) for v in row] for row in d.rows],
            unknown=[list(row) for row in d.unknown],
            reasons=[list(row) for row in d.reasons],
            kinds=[list(row) for row in d.kinds],
            sort=d.sort,
            total=d.total,
            page=d.page,
            size=d.size,
            unavailable=[Unavailable.of(u) for u in d.unavailable],
        )

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The words of each kind `kinds` uses: how a cell's kind reads"
    )
    def kind_texts(self) -> list[KindText]:
        return [KindText.of(t) for t in kind_texts(self.kinds)]
