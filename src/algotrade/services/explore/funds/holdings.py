"""What an ETF holds: its largest holdings with their weights (``GET /instruments/{id}/holdings``).

``key`` is an instrument id or a ticker, like every instrument query. A non-ETF, or an ETF with
no stored holdings (no issuer file or N-PORT filing for it yet), is an empty answer, not an
error: only an unknown instrument is ``NotFoundError``. A holding links to Explore through
``instrument_id`` when its ticker is in the universe; cash, futures, bonds and foreign lines
keep their name only.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any

from algotrade.data.funds.holdings import etf_holdings
from algotrade.data.reference import instruments
from algotrade.services.explore.instruments import resolve_key
from algotrade.services.explore.store import ReadStore, latest_session, records

ETF = "ETF"


@dataclass(frozen=True)
class Holding:
    rank: int
    name: str
    symbol: str | None  # the issuer's ticker for the line, when it prints one
    instrument_id: str | None  # the universe instrument it resolves to (the Explore link)
    weight: float  # fraction of the fund (0.0844 = 8.44%); negative for shorts
    asset_class: str | None


@dataclass(frozen=True)
class EtfHoldings:
    instrument_id: str
    is_etf: bool
    as_of: date | None  # the issuer's holdings date
    source: str | None  # the source that read it (ssga_holdings, ishares_holdings, sec_edgar)
    total: int  # lines in the issuer's file (not only those stored)
    items: list[Holding]  # largest weight first


def _is_etf(store: ReadStore, instrument_id: str, snapshot: date) -> bool:
    row = instruments(store.reader, snapshot, [instrument_id])
    kind = row["security_type"].iloc[0] if len(row) and "security_type" in row.columns else None
    return str(kind).upper() == ETF


def etf_top_holdings(
    store: ReadStore, key: str, top: int = 10, on: date | None = None
) -> EtfHoldings:
    """The ``top`` largest holdings of an ETF on its latest stored date on or before ``on``
    (the latest session by default)."""
    iid, snapshot = resolve_key(store, key, on)
    etf = _is_etf(store, iid, snapshot)
    day = on or latest_session(store.reader)
    frame = etf_holdings(store.reader, iid, day) if etf and day is not None else None
    if frame is None or frame.empty:
        return EtfHoldings(iid, etf, None, None, 0, [])
    rows: list[dict[str, Any]] = records(frame.head(top))
    items = [
        Holding(
            rank=int(r["rank"]),
            name=str(r["holding_name"]),
            symbol=r["holding_symbol"],
            instrument_id=r["holding_id"],
            weight=float(r["weight"]),
            asset_class=r["asset_class"],
        )
        for r in rows
    ]
    return EtfHoldings(
        iid, True, frame["as_of"].iloc[0], str(frame["source"].iloc[0]),
        int(frame["holdings_count"].iloc[0]), items,
    )  # fmt: skip
