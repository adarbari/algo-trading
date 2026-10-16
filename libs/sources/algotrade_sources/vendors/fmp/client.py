"""FMP's shared pieces: the host, the URL builder and the JSON list reader of every FMP source.

The API key is NOT here: FMP takes it only as the ``apikey`` query parameter, which the
registry's transport appends (``framework.http.with_query_param``) to every URL, so the URLs
built here, the retry and error messages that quote them and the raw-store paths never hold it.
Free tier: about 250 calls a day (``[fmp] daily_budget`` keeps the nightly under it), so every
request waits on the shared ``fmp`` limiter (``[fmp] min_interval_s``).
"""

import json
from typing import Any
from urllib.parse import quote, urlencode

from algotrade_sources.framework.http import HttpError

SOURCE = "fmp"
HOST = "https://financialmodelingprep.com/stable"


def vendor_symbol(symbol: str) -> str:
    """Our (ACT-style) symbol -> FMP's: a share class is written with a hyphen (``BRK.B`` ->
    ``BRK-B``)."""
    return symbol.strip().upper().replace(".", "-")


def url(path: str, **params: str | int) -> str:
    """``HOST/path?...`` with ``params`` in the given order and NO key (the transport adds it)."""
    query = urlencode(params, quote_via=quote)
    return f"{HOST}/{path}?{query}"


def refused(exc: HttpError) -> bool:
    """A refusal of this key or plan (401 bad key, 402 premium parameter or symbol): retrying
    the same URL cannot help and spends a call of the day's budget, so it is raised at once
    (``RetryPolicy.rejected``)."""
    return exc.status in (401, 402)


def rows(payload: bytes) -> list[dict[str, Any]]:
    """The JSON list of records an FMP endpoint answers; anything else is a ``ValueError``."""
    data = json.loads(payload)
    if not isinstance(data, list):
        raise ValueError(f"expected a JSON list, got {str(data)[:120]!r}")
    return [r for r in data if isinstance(r, dict)]
