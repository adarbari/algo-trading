"""``ScreenerHit``: a screener of the user's that picked an instrument in the session, with
what its run stored for it (``Instrument.screenerHits``)."""

from typing import Self

import strawberry

from algotrade.services.read.context import ReadContext
from algotrade.services.read.screens import hits
from algotrade_api.graphql.types.screens.result import ScreenResult
from algotrade_api.graphql.types.screens.screener import Screener


@strawberry.type(
    description="A screener that picked the instrument in the session (its run for exactly "
    "the session), and its result for it"
)
class ScreenerHit:
    screener: Screener
    result: ScreenResult

    @classmethod
    def of(cls, d: hits.ScreenerHit, ctx: ReadContext) -> Self:
        return cls(screener=Screener.of(d.screener, ctx), result=ScreenResult.of(d.result, ctx))
