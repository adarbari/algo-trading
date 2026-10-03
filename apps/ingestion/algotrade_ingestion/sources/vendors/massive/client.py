"""Massive (formerly Polygon) REST: the shared client for every Massive source.

The API key travels in an ``Authorization`` header (set on the transport), never in URLs, so it
cannot leak into logs or the raw store. Free tier: 5 requests/minute, so every request waits on
the shared ``massive`` limiter (``[massive] min_interval_s``, 12.5 s). Rows carry the vendor
``symbol`` (ACT style); the jobs resolve ``instrument_id`` through the reference (ADR 0018).
``_Massive`` holds the transport and ``next_url`` paging; ``act_symbol`` maps tickers.
"""

import json
import re
from datetime import UTC, date, datetime
from typing import Any

import pandas as pd

from algotrade_ingestion.sources.framework.http import Http

SOURCE = "massive"
HOST = "https://api.massive.com"
_PREFERRED = re.compile(r"^([A-Z]+)p([A-Z]*)$")  # Massive "KIMpL" == ACT "KIM$L"


def act_symbol(ticker: str) -> str:
    """Massive ticker -> the ACT-style symbol used by the universe (``KIMpL`` -> ``KIM$L``)."""
    match = _PREFERRED.match(ticker)
    return f"{match.group(1)}${match.group(2)}" if match else ticker.upper()


def _ts(value: str) -> pd.Timestamp:
    return pd.Timestamp(date.fromisoformat(value), tz="UTC")


class _Massive:
    name = SOURCE
    dataset = "massive"

    def __init__(self, http: Http) -> None:
        self._http = http

    def _get(self, url: str) -> bytes | None:
        return self._http.get(url)

    def _paged(self, url: str) -> bytes | None:
        """Follow ``next_url`` and return one JSON document holding every page's results."""
        results: list[Any] = []
        next_url: str | None = url
        while next_url:
            body = self._get(next_url)
            if body is None:
                return None
            doc = json.loads(body)
            results.extend(doc.get("results") or [])
            next_url = doc.get("next_url")
        return json.dumps(
            {"results": results, "fetched_at": datetime.now(UTC).isoformat()}
        ).encode()
