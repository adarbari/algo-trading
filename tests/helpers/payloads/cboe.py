"""Synthetic payloads in the Cboe delayed-quotes JSON format (no vendor data in the repo).

Field names match the real feed as observed on 2026-10-02.
"""

import json
import math
from collections.abc import Sequence
from datetime import UTC, date, datetime

SESSION = date(2026, 10, 2)
# Oct-16 (monthly, 14 DTE), Oct-23 weekly, Nov-20 (monthly, 49 DTE), Nov-06 weekly (35 DTE)
EXPIRIES = (date(2026, 10, 16), date(2026, 10, 23), date(2026, 11, 6), date(2026, 11, 20))


def osi(root: str, expiry: date, right: str, strike: float) -> str:
    return f"{root}{expiry:%y%m%d}{right}{round(strike * 1000):08d}"


def _delta(right: str, spot: float, strike: float, dte: int) -> float:
    z = math.log(spot / strike) / (0.35 * math.sqrt(max(dte, 1) / 365))
    call = 0.5 * (1 + math.erf(z / math.sqrt(2)))
    return round(call if right == "C" else call - 1, 4)


def contract(
    root: str,
    expiry: date,
    right: str,
    strike: float,
    *,
    spot: float = 100.0,
    spread: float = 0.10,
    oi: float = 1000,
    delta: float | str | None = "auto",
    session: date = SESSION,
) -> dict[str, object]:
    dte = (expiry - session).days
    d = _delta(right, spot, strike, dte) if delta == "auto" else delta
    intrinsic = max(0.0, (spot - strike) if right == "C" else (strike - spot))
    mid = round(intrinsic + 2.0 * math.exp(-abs(spot - strike) / 15), 2)
    return {
        "option": osi(root, expiry, right, strike),
        "bid": max(mid - spread / 2, 0.0),
        "ask": mid + spread / 2,
        "bid_size": 10.0,
        "ask_size": 10.0,
        "iv": 0.35,
        "open_interest": oi,
        "volume": oi / 10,
        "delta": d,
        "gamma": 0.01,
        "vega": 0.1,
        "theta": -0.05,
        "rho": 0.01,
        "theo": mid,
        "change": 0.0,
        "open": 0.0,
        "high": 0.0,
        "low": 0.0,
        "tick": "no_change",
        "last_trade_price": mid,
        "last_trade_time": None,
        "percent_change": 0.0,
        "prev_day_close": mid,
    }


def chain(
    symbol: str = "TEST",
    session: date = SESSION,
    expiries: Sequence[date] = EXPIRIES,
    spot: float = 100.0,
    spread: float = 0.10,
    oi: float = 1000,
    extra: Sequence[dict[str, object]] = (),
) -> list[dict[str, object]]:
    root = symbol.lstrip("_")
    out = [
        contract(root, e, right, k, spot=spot, spread=spread, oi=oi, session=session)
        for e in expiries
        for right in ("C", "P")
        for k in range(70, 135, 5)
    ]
    return out + list(extra)


def payload(
    symbol: str = "TEST",
    session: date = SESSION,
    options: list[dict[str, object]] | None = None,
    spot: float = 100.0,
    iv30: float = 42.0,
) -> bytes:
    snapshot = datetime(session.year, session.month, session.day, 21, 15, 0)  # noqa: DTZ001 - feed sends naive UTC
    doc = {
        "timestamp": snapshot.strftime("%Y-%m-%d %H:%M:%S"),
        "symbol": symbol,
        "data": {
            "symbol": symbol,
            "security_type": "stock",
            "exchange_id": 3,
            "current_price": spot,
            "price_change": 0.5,
            "price_change_percent": 0.5,
            "bid": spot - 0.01,
            "ask": spot + 0.01,
            "bid_size": 1,
            "ask_size": 1,
            "open": spot - 1,
            "high": spot + 1,
            "low": spot - 2,
            "close": spot,
            "prev_day_close": spot - 0.5,
            "volume": 1_000_000,
            "iv30": iv30,
            "iv30_change": 0.0,
            "iv30_change_percent": 0.0,
            "seqno": 1,
            "last_trade_time": f"{session.isoformat()}T16:00:00",
            "tick": "up",
            "options": chain(symbol, session, spot=spot) if options is None else options,
        },
    }
    return json.dumps(doc).encode()


CLOCK_TS = datetime(2026, 10, 2, 22, 0, tzinfo=UTC)
