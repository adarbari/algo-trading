"""``TraderPreferences``: the user's default Ideas tab and watchlist (ADR 0083, amendment
2026-11-01)."""

from typing import Self

import strawberry

from algotrade.services.read.users import trader


@strawberry.type(description="An instrument on the user's watchlist")
class WatchedInstrument:
    instrument_id: str
    symbol: str | None = strawberry.field(
        description="The ticker in the session's reference snapshot; null when it has none"
    )

    @classmethod
    def of(cls, d: trader.WatchedInstrument) -> Self:
        return cls(instrument_id=d.instrument_id, symbol=d.symbol)


@strawberry.type(
    description="The user's two stored choices: the Ideas tab they open on (`stocks` or "
    "`premium`; null until they answered the sign-up question) and their watchlist "
    "(instrument ids only, at most 50; never a position, size or account)"
)
class TraderPreferences:
    default_tab: str | None
    watchlist: list[WatchedInstrument]

    @classmethod
    def of(cls, d: trader.TraderPreferences) -> Self:
        return cls(
            default_tab=d.default_tab,
            watchlist=[WatchedInstrument.of(w) for w in d.watchlist],
        )
