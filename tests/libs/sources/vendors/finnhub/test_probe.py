"""Finnhub's probe endpoints, header auth and refusal handling (``stock/price-target`` is premium:
RECORDED 403, 2026-10-16)."""

import tomllib
from collections.abc import Callable
from pathlib import Path

import pytest

from algotrade.config.site.settings import SourcesSettings
from algotrade_sources.framework import registry
from algotrade_sources.framework.base import Access, FetchRequest
from algotrade_sources.framework.http import HttpError, RetryPolicy
from algotrade_sources.framework.registry import build_sources
from algotrade_sources.vendors.finnhub.client import refused
from algotrade_sources.vendors.finnhub.probe import (
    BROAD_SYMBOL,
    ENDPOINTS,
    PROBE_SYMBOL,
    FinnhubProbe,
)
from algotrade_sources.vendors.finnhub.recommendations import FinnhubRecommendations
from tests.conftest import REPO_ROOT
from tests.helpers.ingest_fakes import http_for

KEY = "fh-k3y-d0-n0t-l34k-77aa"
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "sources" / "finnhub"
RECOMMENDATION = (FIXTURES / "recommendation_aapl.json").read_bytes()
DENIED = (FIXTURES / "price_target_403.json").read_bytes()
SITE = tomllib.loads((REPO_ROOT / "config" / "site" / "sources.toml").read_text())


def test_the_probe_names_the_free_recommendation_and_the_premium_price_target() -> None:
    assert set(ENDPOINTS) == {
        "recommendation",
        "price_target",
        "recommendation@broad",
        "price_target@broad",
    }
    for name, url in ENDPOINTS.items():
        symbol = BROAD_SYMBOL if name.endswith("@broad") else PROBE_SYMBOL
        assert f"symbol={symbol}" in url


def test_the_key_travels_in_the_x_finnhub_token_header_never_the_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[dict[str, str] | None] = []
    urls: list[str] = []

    def transport(headers: dict[str, str] | None = None) -> Callable[[str], bytes]:
        sent.append(headers)
        return lambda url: urls.append(url) or RECOMMENDATION

    monkeypatch.setattr(registry, "urllib_transport", transport)
    settings = SourcesSettings.from_document(SITE)
    built = build_sources(
        settings, {"ALGOTRADE_FINNHUB_API_KEY": KEY}.get, ["finnhub_recommendations"], tmp_path
    )
    source = built.sources["finnhub_recommendations"]
    assert source.fetch(FetchRequest("AAPL")) == RECOMMENDATION
    assert sent[0] == {"X-Finnhub-Token": KEY}
    assert urls == ["https://finnhub.io/api/v1/stock/recommendation?symbol=AAPL"]
    assert not any(KEY in u for u in urls)
    assert built.limiters["finnhub"].min_interval_s == SITE["finnhub"]["min_interval_s"] == 1.0
    assert settings.finnhub_licence == "personal"


def test_without_its_key_the_finnhub_sources_are_skipped_with_the_reason(tmp_path: Path) -> None:
    built = build_sources(SourcesSettings.from_document(SITE), lambda n: None, None, tmp_path)
    assert built.skipped["finnhub_probe"].startswith("ALGOTRADE_FINNHUB_API_KEY is not set")
    assert "finnhub_recommendations" not in built.sources


def test_the_premium_endpoint_is_denied_and_a_refusal_is_not_retried() -> None:
    calls: list[str] = []

    def transport(url: str) -> bytes:
        calls.append(url)
        raise HttpError(403, body=DENIED)

    http = http_for(transport, RetryPolicy(tries=7, rejected=refused))
    with pytest.raises(HttpError):
        FinnhubRecommendations(http).fetch(FetchRequest("AAPL"))
    assert len(calls) == 1
    assert FinnhubProbe(http_for(transport)).probe("price_target").access is Access.DENIED
