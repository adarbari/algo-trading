"""Cboe delayed-quotes feed: a whole option chain plus the underlying in one request.

Endpoint (undocumented, public, delayed, not a licensed data product, so it may change
or disappear; see docs/data/vendors.md):
    https://cdn-api.cboe.com/api/global/delayed_quotes/options/<SYMBOL>.json
Index options use a leading underscore (``_SPX``).

Notes for point-in-time correctness:
- ``timestamp`` is UTC; the session is taken from the underlying's ``last_trade_time``
  (exchange local time).
- ``open_interest`` is OCC's figure as of the previous session's close.
- Greeks and IV are Cboe's model values; ``quant/`` will compute our own as a cross-check.
"""

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import pandas as pd

from algotrade.core.instruments import AssetClass, instrument_id
from algotrade.core.options import is_standard_root, parse_osi
from algotrade_ingestion.sources.framework.base import FetchRequest, Normalized
from algotrade_ingestion.sources.framework.http import Http

SOURCE = "cboe_delayed"
DATASET = "option_chain"
URL = "https://cdn-api.cboe.com/api/global/delayed_quotes/options/{symbol}.json"
UNDERLYINGS_TABLE = "chains/underlying_quotes"
OPTIONS_TABLE = "chains/option_quotes"
_QUOTE_FIELDS = (
    "bid",
    "ask",
    "bid_size",
    "ask_size",
    "volume",
    "open_interest",
    "iv",
    "delta",
    "gamma",
    "vega",
    "theta",
    "rho",
    "theo",
)


@dataclass(frozen=True)
class ParsedChain:
    session_date: date
    snapshot_ts: datetime
    underlying: pd.DataFrame  # one row, chains/underlying_quotes columns (minus common)
    options: pd.DataFrame  # chains/option_quotes columns (minus common)
    nonstandard_series: int


class CboeOptionsSource:
    """Implements ``sources.base.Source``. Request key = Cboe symbol (``_SPX`` for indexes)."""

    name = SOURCE
    dataset = DATASET

    def __init__(self, http: Http) -> None:
        self._http = http

    def fetch(self, request: FetchRequest) -> bytes | None:
        return self._http.get(URL.format(symbol=request.key))

    def cool_down(self, seconds: float) -> None:
        """Pause new Cboe requests (every process) before a gentler retry pass."""
        self._http.cool_down(seconds)

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        if request.instrument_id is None:
            raise ValueError("Cboe requests need the underlying's instrument_id")
        parsed = parse_chain(request.key, request.instrument_id, payload)
        if parsed is None:
            return None
        return Normalized(
            session_date=parsed.session_date,
            tables={UNDERLYINGS_TABLE: parsed.underlying, OPTIONS_TABLE: parsed.options},
            notes={"nonstandard_series": parsed.nonstandard_series},
        )


def _float(value: Any) -> float | None:
    return None if value is None else float(value)


def parse_chain(symbol: str, underlying_id: str, payload: bytes) -> ParsedChain | None:
    """Normalise one response. ``None`` when the payload has no options at all.

    ``underlying_id`` comes from the universe, so chains join to it without re-deriving ids.
    """
    doc = json.loads(payload)
    data = doc.get("data") or {}
    if not data.get("options"):
        return None
    snapshot = datetime.fromisoformat(doc["timestamp"]).replace(tzinfo=UTC)
    last_trade = data.get("last_trade_time")
    session = datetime.fromisoformat(last_trade).date() if last_trade else snapshot.date()
    underlying = pd.DataFrame(
        [
            {
                "instrument_id": underlying_id,
                "symbol": symbol,
                "ts": snapshot,
                "price": _float(data.get("current_price")),
                "open": _float(data.get("open")),
                "high": _float(data.get("high")),
                "low": _float(data.get("low")),
                "close": _float(data.get("close")),
                "prev_close": _float(data.get("prev_day_close")),
                "volume": _float(data.get("volume")),
                "iv30": _float(data.get("iv30")),
                "security_type": data.get("security_type"),
            }
        ]
    )
    rows, nonstandard = [], 0
    for quote in data["options"]:
        osi = parse_osi(quote["option"])
        if osi is None or not is_standard_root(osi.root, symbol.lstrip("_")):
            nonstandard += 1
            continue
        row: dict[str, Any] = {
            "instrument_id": instrument_id(AssetClass.OPTION, quote["option"]),
            "underlying_id": underlying_id,
            "ts": snapshot,
            "root": osi.root,
            "expiry": osi.expiry,
            "right": osi.right.value,
            "strike": osi.strike,
            "last": _float(quote.get("last_trade_price")),
        }
        row.update({f: _float(quote.get(f)) for f in _QUOTE_FIELDS})
        rows.append(row)
    return ParsedChain(session, snapshot, underlying, pd.DataFrame(rows), nonstandard)
