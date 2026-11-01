"""Synthetic payloads in the Massive (Polygon) response formats."""

import json
from collections.abc import Iterable
from datetime import UTC, date, datetime


def grouped(day: date, rows: Iterable[tuple[str, float, float, float, float, float]]) -> bytes:
    """rows: (ticker, open, high, low, close, volume)."""
    t = int(datetime(day.year, day.month, day.day, 20, tzinfo=UTC).timestamp() * 1000)
    results = [
        {"T": tk, "o": o, "h": h, "l": lo, "c": c, "v": v, "vw": c, "t": t, "n": 10}
        for tk, o, h, lo, c, v in rows
    ]
    return json.dumps(
        {
            "status": "OK",
            "adjusted": False,
            "resultsCount": len(results),
            "results": results or None,
        }
    ).encode()


def page(results: list[dict[str, object]], next_url: str | None = None) -> bytes:
    doc: dict[str, object] = {"status": "OK", "results": results}
    if next_url:
        doc["next_url"] = next_url
    return json.dumps(doc).encode()


def inactive_record(
    ticker: str,
    delisted: str | None,
    mic: str | None = "XNAS",
    kind: str | None = "CS",
    **more: str,
) -> dict[str, object]:
    """One record of the inactive list, in the recorded shape (``tests/fixtures/sources/massive/
    inactive_tickers_slice.json``): the day is ``delisted`` (ISO date, as the last trading day), a
    null ``mic`` or ``kind`` leaves the field out as Massive does, ``more`` adds fields."""
    record: dict[str, object] = {
        "active": False, "currency_name": "usd", "locale": "us", "market": "stocks",
        "name": f"{ticker} Inc", "ticker": ticker, "last_updated_utc": "2025-01-16T17:32:57Z",
    }  # fmt: skip
    if delisted:
        record["delisted_utc"] = f"{delisted}T05:00:00Z"
    if mic:
        record["primary_exchange"] = mic
    if kind:
        record["type"] = kind
    return {**record, **more}


def overview(
    ticker: str,
    description: str | None = None,
    homepage: str | None = None,
    employees: int | None = None,
) -> bytes:
    """A ticker overview: stocks carry a description; ETFs on the free tier do not."""
    results: dict[str, object] = {"ticker": ticker, "name": f"{ticker} Inc", "type": "CS"}
    if description:
        results["description"] = description
    if homepage:
        results["homepage_url"] = homepage
    if employees:
        results["total_employees"] = employees
    return json.dumps({"request_id": "r", "status": "OK", "results": results}).encode()
