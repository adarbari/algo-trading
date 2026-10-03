"""Synthetic payloads in the api.nasdaq.com earnings-calendar format."""

import json
from collections.abc import Iterable


def calendar(rows: Iterable[tuple[str, str]], reported: bool = False) -> bytes:
    """rows: (symbol, time code such as ``time-pre-market``)."""
    out = []
    for symbol, time in rows:
        row = {
            "symbol": symbol,
            "name": f"{symbol} Inc.",
            "time": time,
            "fiscalQuarterEnding": "Sep/2026",
            "epsForecast": "$1.20",
            "noOfEsts": "5",
            "marketCap": "$1,000,000",
        }
        if reported:
            row.update(eps="($0.30)", surprise="-12.5")
        out.append(row)
    return json.dumps(
        {"data": {"asOf": "x", "headers": {}, "rows": out or None}, "status": {"rCode": 200}}
    ).encode()
