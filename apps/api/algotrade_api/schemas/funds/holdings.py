"""``/instruments/{id}/holdings``: an ETF's largest holdings with their weights."""

from datetime import date

from algotrade_api.schemas.health import Schema


class Holding(Schema):
    rank: int
    name: str
    symbol: str | None
    instrument_id: str | None
    weight: float
    asset_class: str | None


class EtfHoldings(Schema):
    instrument_id: str
    is_etf: bool
    as_of: date | None
    source: str | None
    total: int
    items: list[Holding]
