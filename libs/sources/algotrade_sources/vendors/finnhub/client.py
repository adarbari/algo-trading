"""Finnhub's shared pieces: the host, the URL builder and the JSON reader of every Finnhub source.

The key travels in an ``X-Finnhub-Token`` header set on the transport (registry), never in a URL.
Free tier: 60 calls a minute (``[finnhub] min_interval_s`` = 1 s on the shared ``finnhub``
limiter); some endpoints are premium and answer 403 ``You don't have access to this resource``
(``stock/price-target``, verified 2026-10-16).
"""

import json
from typing import Any
from urllib.parse import quote, urlencode

from algotrade_sources.framework.http import HttpError

SOURCE = "finnhub"
HOST = "https://finnhub.io/api/v1"


def vendor_symbol(symbol: str) -> str:
    """Our (ACT-style) symbol -> Finnhub's: a share class is written with a dot (``BRK.B``)."""
    return symbol.strip().upper()


def url(path: str, **params: str | int) -> str:
    """``HOST/path?...`` with ``params`` in the given order."""
    return f"{HOST}/{path}?{urlencode(params, quote_via=quote)}"


def refused(exc: HttpError) -> bool:
    """A refusal of this key or plan (401 bad key, 403 premium endpoint): raised at once, never
    retried (``RetryPolicy.rejected``)."""
    return exc.status in (401, 403)


def rows(payload: bytes) -> list[dict[str, Any]]:
    """The JSON list of records an endpoint answers; anything else is a ``ValueError``."""
    data = json.loads(payload)
    if not isinstance(data, list):
        raise ValueError(f"expected a JSON list, got {str(data)[:120]!r}")
    return [r for r in data if isinstance(r, dict)]
