"""Massive news headlines of one ticker in a time window (``MassiveNews``, ADR 0050 EV4b).

``GET /v2/reference/news`` with ``ticker``, ``published_utc.gte`` / ``.lte``, ``order=desc`` and
``limit`` is one request per ticker (the free tier's 5 a minute are the shared ``massive``
limiter's). Only the headline facts are kept: the title, the publisher, the time it was published
and the article URL; no article text. The request is a ``NewsRequest`` (ticker, ISO UTC window,
limit): one payload is one window; the nightly names it (the previous close to the reaction
session's close) and says how many headlines at most.
"""

import json
from urllib.parse import quote

import pandas as pd

from algotrade_sources.framework.base import FetchRequest, Normalized
from algotrade_sources.framework.series import NEWS_FRAME, NewsRequest
from algotrade_sources.vendors.massive.client import HOST, _Massive
from algotrade_sources.vendors.massive.overview import massive_ticker

NEWS = HOST + "/v2/reference/news"
COLUMNS = ["title", "publisher", "published_utc", "article_url"]


def parse_news(payload: bytes) -> pd.DataFrame:
    """The headlines of a news response, newest first (``COLUMNS``); none: an empty frame."""
    rows = []
    for item in json.loads(payload).get("results") or []:
        title = " ".join(str(item.get("title") or "").split())
        published = pd.to_datetime(item.get("published_utc"), utc=True, errors="coerce")
        if not title or pd.isna(published):
            continue
        publisher = item.get("publisher") or {}
        rows.append(
            {
                "title": title,
                "publisher": str(publisher.get("name") or ""),
                "published_utc": published,
                "article_url": str(item.get("article_url") or ""),
            }
        )
    frame = pd.DataFrame(rows, columns=COLUMNS)
    return frame.sort_values("published_utc", ascending=False, kind="stable").reset_index(drop=True)


class MassiveNews(_Massive):
    """One ticker's headlines in a window (a ``NewsRequest``)."""

    dataset = "ticker_news"

    def fetch(self, request: FetchRequest) -> bytes | None:
        assert isinstance(request, NewsRequest)
        query = (
            f"?ticker={quote(massive_ticker(request.key), safe='')}"
            f"&published_utc.gte={quote(request.start, safe='')}"
            f"&published_utc.lte={quote(request.end, safe='')}"
            f"&order=desc&sort=published_utc&limit={request.limit}"
        )
        return self._get(NEWS + query)

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        return Normalized(session_date=None, tables={}, parsed={NEWS_FRAME: parse_news(payload)})
