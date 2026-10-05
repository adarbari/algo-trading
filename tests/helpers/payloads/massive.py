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
