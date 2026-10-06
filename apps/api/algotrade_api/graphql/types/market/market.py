"""``Market``: the market the regime describes (``MKT:US``) for the session, and its values by
catalogue name (``features(names)``, ADR 0047): the market-entity groups'
``market.<group>@vN.<col>`` fields, each a ``FeatureValue`` (the instrument value type) for
exactly the session."""

import datetime as dt
from typing import Self

import strawberry
from strawberry.types import Info

from algotrade.services.read.context import ReadContext
from algotrade.services.read.market import market
from algotrade.services.read.market.features import load_market_feature_values
from algotrade_api.graphql.limits import MAX_NAMES, MaxItems
from algotrade_api.graphql.types.instruments.feature import FeatureValue


@strawberry.type(
    description="A market (`marketId` `MKT:US`) for the session. Per-session values (breadth, "
    "trend, the regime's inputs) are market catalogue features: `features(names)`"
)
class Market:
    session: dt.date
    market_id: str
    ctx: strawberry.Private[ReadContext]

    @classmethod
    def of(cls, d: market.Market, ctx: ReadContext) -> Self:
        return cls(session=d.session, market_id=d.market_id, ctx=ctx)

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The values of `names` (market catalogue fields: "
        "`market.<group>@v<N>.<column>`, or a `feature.<name>` over them; in the order "
        "asked) for the session; a name outside the market's catalogue is an UNKNOWN_FEATURE "
        "error",
        extensions=[MaxItems("names", MAX_NAMES)],
    )
    def features(self, info: Info, names: list[str]) -> list[FeatureValue]:
        return [FeatureValue.of(v) for v in load_market_feature_values(self.ctx, names)]
