"""``MassiveNews``: the window in the request, the headline facts kept, empty titles dropped."""

import pandas as pd

from algotrade_sources.framework.series import NewsRequest
from algotrade_sources.vendors.massive.news import MassiveNews, parse_news
from tests.conftest import REPO_ROOT
from tests.helpers.ingest_fakes import http_for

PAYLOAD = (REPO_ROOT / "tests/fixtures/sources/massive/news_AAA.json").read_bytes()


def test_the_request_names_the_ticker_the_window_and_the_limit() -> None:
    urls: list[str] = []

    def transport(url: str) -> bytes:
        urls.append(url)
        return PAYLOAD

    request = NewsRequest(
        key="AAA", start="2026-10-02T20:00:00Z", end="2026-10-05T20:00:00Z", limit=8
    )
    assert MassiveNews(http_for(transport)).fetch(request) == PAYLOAD
    url = urls[0]
    assert "ticker=AAA" in url and "published_utc.gte=2026-10-02T20%3A00%3A00Z" in url
    assert "published_utc.lte=2026-10-05T20%3A00%3A00Z" in url and "limit=8" in url


def test_headlines_keep_the_title_publisher_time_and_url_newest_first() -> None:
    frame = parse_news(PAYLOAD)
    assert list(frame["title"]) == [
        "AAA cuts full-year guidance on weak demand",
        "Analyst downgrades AAA to sell",
    ]  # the empty title is dropped
    assert frame.loc[0, "published_utc"] == pd.Timestamp("2026-10-05T12:15:00Z")
    assert frame.loc[0, "publisher"] == "Newswire" and frame.loc[1, "article_url"].endswith("a2")
