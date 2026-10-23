"""Yahoo's shared pieces: the host, the URL builder, the refusal test and the transport.

Yahoo's ``quoteSummary`` needs a cookie and a crumb that the ``yfinance`` package fetches and
refreshes (``yfinance.data.YfData``: one shared session). So the transport here is the vendor's
own, built by the registry (``SourceSpec.transport``): it turns the source's GET URL into a
``YfData.get`` with the URL's query as ``params`` and returns the body, so retry, pacing and the
breaker stay the framework's (``framework/http.py``). ``yfinance`` is imported on the first
request only, never at import: the API imports this package and must not load ``curl_cffi``.

YfData makes hidden requests of its own (the crumb dance: three requests for an unknown symbol)
that bypass the limiter, which is why ``[yahoo] min_interval_s`` is a floor of one second. Its
cookie and timezone caches go to ``[yahoo] cache_dir`` (``var/cache/yahoo``), never the user's
library cache. Errors: a non-200 answer is an ``HttpError`` (404 = an unknown symbol or one with no
fundamentals, ``refused``; 401 a crumb that did not take: an error, retried), a connection or
timeout error is an ``OSError`` (curl_cffi's are), which ``get_with_retry`` retries.
"""

import importlib
import threading
from collections.abc import Callable
from typing import Any, Protocol
from urllib.parse import parse_qsl, quote, urlencode, urlsplit

from algotrade_sources.framework.http import HttpError, Transport, parse_retry_after

SOURCE = "yahoo"
HOST = "https://query2.finance.yahoo.com/v10/finance/quoteSummary"
MODULES = "financialData,earningsTrend,recommendationTrend,calendarEvents,upgradeDowngradeHistory"
TIMEOUT_S = 30


class Session(Protocol):
    """What the transport needs of ``yfinance.data.YfData`` (tests pass a fake)."""

    def get(self, url: str, params: dict[str, str] | None = None, timeout: float = 30) -> Any: ...


def vendor_symbol(symbol: str) -> str:
    """Our (ACT-style) symbol -> Yahoo's: a share class is written with a hyphen (``BRK.B`` ->
    ``BRK-B``)."""
    return symbol.strip().upper().replace(".", "-")


def url(symbol: str) -> str:
    """The one ``quoteSummary`` request of a name (targets, estimates, recommendation counts)."""
    query = urlencode({"modules": MODULES, "formatted": "false"}, quote_via=quote)
    return f"{HOST}/{quote(vendor_symbol(symbol), safe='')}?{query}"


def refused(exc: HttpError) -> bool:
    """404: Yahoo does not know the symbol or holds no fundamentals for it (an ETF): retrying
    cannot help, so it is raised at once (``RetryPolicy.rejected``) and the task reads it as
    ``NOT_COVERED``."""
    return exc.status == 404


def load_session(cache_dir: str) -> Session:
    """The shared ``YfData`` session with its caches under ``cache_dir`` (imports yfinance)."""
    yfinance = importlib.import_module("yfinance")
    yfinance.set_tz_cache_location(cache_dir)  # also moves the cookie cache
    session: Session = importlib.import_module("yfinance.data").YfData()
    return session


def yahoo_transport(
    headers: dict[str, str],  # no credential: the registry hands every transport its headers
    cache_dir: str = "var/cache/yahoo",
    session: Callable[[str], Session] = load_session,
) -> Transport:
    """A GET transport over ``YfData``, created on the first request (see the module docstring)."""
    held: list[Session] = []
    lock = threading.Lock()

    def get(url_: str) -> bytes:
        with lock:
            if not held:
                held.append(session(cache_dir))
        parts = urlsplit(url_)
        base = f"{parts.scheme}://{parts.netloc}{parts.path}"
        try:
            response = held[0].get(base, params=dict(parse_qsl(parts.query)), timeout=TIMEOUT_S)
        except OSError:
            raise  # curl_cffi's connection and timeout errors: retried by get_with_retry
        except Exception as exc:
            if type(exc).__name__ == "YFRateLimitError":  # YfData's own 429 after its retries
                raise HttpError(429) from None
            raise OSError(f"yahoo: {type(exc).__name__}: {exc}") from exc
        if response.status_code != 200:
            retry_after = parse_retry_after(response.headers.get("Retry-After"))
            raise HttpError(response.status_code, retry_after, bytes(response.content[:1024]))
        body: bytes = response.content
        return body

    return get
