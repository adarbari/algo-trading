"""``IbkrSource``: IB Gateway market data as a session source (``ctx.sources["ibkr"]``).

A ``SessionSource`` (``sources/framework/base.py``): the registry builds it unconnected,
workflows ``probe`` the gateway port, and the task opens and closes it around its work
(``base.opened``). Requests go through the read-only facade (``gateway.py``); each answer is
serialised to JSON, which ``IngestRun.fetch`` saves as the raw payload like any other source's,
and ``normalize`` turns it back into frames (``Normalized.parsed``; nothing is stored as is).

Request keys (``FetchRequest.session_date`` is the session verified):

    bars__<SYMBOL>           daily TRADES bars (split-adjusted by IB), ``bar_sessions`` of them
    iv__<SYMBOL>             daily OPTION_IMPLIED_VOLATILITY of the underlying
    div__<SYMBOL>            IB dividends (tick 456) + the last close
    option_params__<SYMBOL>  listed expirations and strikes
    option__<SYMBOL>__<YYYY-MM-DD>__<C|P>__<strike>   one option snapshot
"""

import json
from datetime import UTC, date, datetime
from typing import Any

import pandas as pd

from algotrade_ingestion.sources.framework.base import FetchRequest, Normalized
from algotrade_ingestion.sources.vendors.ibkr.gateway import IbkrMarketData

SOURCE = "ibkr"
KINDS = ("bars", "iv", "div", "option_params", "option")
# Request keys double as raw storage keys, which may not contain "/" (storage/backends).
SEP = "__"
DEFAULT_SESSIONS = 260


def parse_key(key: str) -> tuple[str, list[str]]:
    kind, _, rest = key.partition(SEP)
    parts = rest.split(SEP) if rest else []
    if kind not in KINDS or not parts or (kind == "option") != (len(parts) == 4):
        raise ValueError(f"unknown IBKR request key {key!r}; kinds: {', '.join(KINDS)}")
    return kind, parts


def option_key(symbol: str, expiry: date, right: str, strike: float) -> str:
    return SEP.join(("option", symbol, expiry.isoformat(), right, f"{strike:g}"))


def _frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
    frame["date"] = pd.to_datetime(frame["date"]).dt.date
    return frame


def _iso(yyyymmdd: str) -> str:
    """IB's ``20261120`` -> ``2026-11-20``."""
    return f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:8]}"


class IbkrSource:
    """Market data from IB Gateway, read-only. ``sessions``: daily bars per ``bars`` request."""

    name = SOURCE
    dataset = "market_data"

    def __init__(self, gateway: IbkrMarketData, sessions: int = DEFAULT_SESSIONS) -> None:
        self.gateway, self.sessions = gateway, sessions

    # ------------------------------------------------------------------ session

    def probe(self) -> str | None:
        return self.gateway.reachable()

    def open(self) -> None:
        self.gateway.connect()

    def close(self) -> None:
        self.gateway.close()

    # ------------------------------------------------------------------ source

    def fetch(self, request: FetchRequest) -> bytes | None:
        kind, parts = parse_key(request.key)
        symbol = parts[0]
        end = request.session_date or datetime.now(UTC).date()
        answer: Any
        if kind == "bars":
            answer = self.gateway.historical_bars(symbol, end, self.sessions)
        elif kind == "iv":
            answer = self.gateway.implied_volatility(symbol, end)
        elif kind == "div":
            answer = self.gateway.dividends(symbol)
        elif kind == "option_params":
            answer = self.gateway.option_params(symbol)
        else:
            expiry, right, strike = date.fromisoformat(parts[1]), parts[2], float(parts[3])
            answer = self.gateway.option_quote(symbol, expiry, strike, right)
        doc = {"key": request.key, "session": end.isoformat(), "data": answer}
        return json.dumps(doc, sort_keys=True).encode()

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        kind, _ = parse_key(request.key)
        data = json.loads(payload)["data"]
        if kind == "option_params":
            listed = {_iso(e) for c in data for e in c["expirations"]}
            expirations = sorted(date.fromisoformat(e) for e in listed)
            strikes = sorted({float(s) for c in data for s in c["strikes"]})
            parsed = {
                "expirations": pd.DataFrame({"expiration": expirations}),
                "strikes": pd.DataFrame({"strike": strikes}),
            }
        elif kind in ("bars", "iv"):
            parsed = {kind: _frame(data)}
        else:
            parsed = {kind: pd.DataFrame([data])}
        return Normalized(request.session_date, tables={}, parsed=parsed)
