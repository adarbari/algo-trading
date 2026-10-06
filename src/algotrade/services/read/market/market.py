"""``Market`` (ADR 0047): the market the regime and the market-entity features describe, for
``ctx.session``. It carries only identity (``market_id``, the entity key of its feature rows);
its values are catalogue features read by name (``services.read.market.features``)."""

from dataclasses import dataclass
from datetime import date

from algotrade.core.model.instruments import market_id
from algotrade.services.read.context import ReadContext
from algotrade.services.read.market.features import US


@dataclass(frozen=True)
class Market:
    """A market for ``session``: ``market_id`` is its ``MKT:`` entity id."""

    session: date
    market_id: str


def load_market(ctx: ReadContext, market: str = US) -> Market:
    """``market`` (the US market by default) for ``ctx.session``."""
    return Market(ctx.session.date, market_id(market))
