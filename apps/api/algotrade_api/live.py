"""The API's live option quotes (ADR 0028): the IB Gateway session behind ``/chains/{id}/live``.

Built once per app (``open_live``) from the site settings and the environment through the
source registry, so the API gets exactly the ingestion's read-only facade and its shared,
cross-process limiters, but with the API's own client id (``config.env.api_credential``). One
``SessionThread`` owns the session: nothing connects until the first request, a stopped
gateway makes requests fall back at once for ``live_retry_s``, and a slow one after
``live_timeout_s``. ``[ibkr]`` disabled or not configured: a ``DisabledFeed`` (the stored chain
with status DISABLED). Answers are recorded in the background (``services.live.recorder``).
"""

from collections.abc import Sequence
from datetime import date
from typing import Any, cast

from algotrade.config.env import api_credential
from algotrade.config.site.settings import IbkrSettings, SiteDocuments, load_sources
from algotrade.services.live.quotes import (
    UNAVAILABLE,
    DisabledFeed,
    FeedUnavailableError,
    LiveQuotes,
    QuoteFeed,
)
from algotrade.services.live.recorder import open_recorder
from algotrade_sources.framework.base import FetchRequest, SessionSource, SessionUnavailableError
from algotrade_sources.framework.registry import build_sources
from algotrade_sources.framework.session_thread import SessionThread

SOURCE = "ibkr"
OFF = "live quotes are off in this app (tests, the OpenAPI export)"


def quotes_key(symbol: str, expiry: date, strikes: Sequence[float]) -> str:
    """The IBKR source's request key for an expiry's quotes at ``strikes``."""
    return "__".join(
        ("quotes", symbol, expiry.isoformat(), "+".join(str(float(k)) for k in strikes))
    )


class SessionQuoteFeed:
    """``QuoteFeed`` over a session source run by a ``SessionThread``."""

    def __init__(self, thread: SessionThread[SessionSource], options: IbkrSettings) -> None:
        self._thread, self._timeout_s = thread, options.live_timeout_s
        self.market_data_type = options.market_data_type

    def quotes(self, symbol: str, expiry: date, strikes: Sequence[float]) -> Any:
        request = FetchRequest(quotes_key(symbol, expiry, strikes))

        def read(source: SessionSource) -> Any:
            payload = source.fetch(request)
            normalized = source.normalize(request, payload) if payload else None
            if normalized is None:
                raise FeedUnavailableError(UNAVAILABLE, f"{SOURCE}: no answer for {request.key}")
            return normalized.parsed["quotes"]

        try:
            return self._thread.call(read, self._timeout_s)
        except SessionUnavailableError as exc:
            raise FeedUnavailableError(UNAVAILABLE, str(exc)) from exc

    def close(self) -> None:
        self._thread.close()


def live_feed(configs: SiteDocuments) -> tuple[QuoteFeed, IbkrSettings]:
    """The IBKR feed the site settings and the environment allow (else a disabled one)."""
    settings = load_sources(configs)
    built = build_sources(settings, api_credential, [SOURCE])
    source = built.sources.get(SOURCE)
    if source is None:
        return DisabledFeed(built.skipped.get(SOURCE, f"{SOURCE} unavailable")), settings.ibkr
    thread = SessionThread(cast(SessionSource, source), settings.ibkr.live_retry_s)
    return SessionQuoteFeed(thread, settings.ibkr), settings.ibkr


def open_live(data_url: str, configs: SiteDocuments) -> LiveQuotes:
    """Live quotes for the app serving ``data_url`` (recorded there when the feed is real)."""
    feed, options = live_feed(configs)
    recorder = None if isinstance(feed, DisabledFeed) else open_recorder(data_url)
    return LiveQuotes(feed, recorder, options)


def no_live(reason: str = OFF) -> LiveQuotes:
    """Live quotes switched off: every request gets the stored chain (status DISABLED)."""
    return LiveQuotes(DisabledFeed(reason), None, IbkrSettings())
