import io
import urllib.error
from datetime import date
from email.message import Message
from unittest import mock

import pytest

from algotrade_ingestion.sources.base import FetchRequest
from algotrade_ingestion.sources.cboe import URL, CboeOptionsSource, parse_chain
from algotrade_ingestion.sources.http import (
    CircuitBreaker,
    CircuitOpenError,
    Http,
    HttpError,
    RetryPolicy,
    get_with_retry,
    urllib_transport,
)
from tests import cboe_fixture as fx
from tests.ingest_helpers import CountingLimiter, http_for

FAST = RetryPolicy(tries=3, base_delay=0, max_delay=0)


def scripted(*outcomes: object):  # type: ignore[no-untyped-def]
    calls = iter(outcomes)

    def transport(url: str) -> bytes:
        outcome = next(calls)
        if isinstance(outcome, Exception):
            raise outcome
        assert isinstance(outcome, bytes)
        return outcome

    return transport


def test_retry_honours_retry_after_then_succeeds() -> None:
    sleeps: list[float] = []
    body = get_with_retry(
        scripted(HttpError(429, 7.0), OSError("reset"), b"ok"), "u", FAST, sleeps.append
    )
    assert body == b"ok"
    assert sleeps[0] == 7.0


def test_404_means_no_chain_but_403_is_an_error() -> None:
    assert get_with_retry(scripted(HttpError(404)), "u", FAST, lambda s: None) is None
    with pytest.raises(RuntimeError, match="giving up"):
        get_with_retry(
            scripted(HttpError(403), HttpError(403), HttpError(403)), "u", FAST, lambda s: None
        )


def test_urllib_transport_maps_http_errors() -> None:
    headers = Message()
    headers["Retry-After"] = "3"
    err = urllib.error.HTTPError("u", 429, "slow down", headers, io.BytesIO())
    with mock.patch("urllib.request.urlopen", side_effect=err), pytest.raises(HttpError) as exc:
        urllib_transport()("https://example.com")
    assert (exc.value.status, exc.value.retry_after) == (429, 3.0)
    response = mock.MagicMock()
    response.__enter__.return_value.read.return_value = b"body"
    with mock.patch("urllib.request.urlopen", return_value=response):
        assert urllib_transport()("https://example.com") == b"body"


def test_source_builds_url() -> None:
    seen: list[str] = []
    source = CboeOptionsSource(http_for(lambda url: seen.append(url) or b"{}"))
    assert source.fetch(FetchRequest("_SPX")) == b"{}"
    assert seen == [URL.format(symbol="_SPX")]


def test_parse_chain_normalises_and_filters_nonstandard() -> None:
    adjusted = fx.contract("TEST1", fx.EXPIRIES[0], "C", 100)
    junk = {**fx.contract("TEST", fx.EXPIRIES[0], "C", 100), "option": "garbage"}
    parsed = parse_chain("TEST", "EQ:TEST", fx.payload(options=fx.chain(extra=[adjusted, junk])))
    assert parsed is not None
    assert parsed.session_date == fx.SESSION
    assert parsed.nonstandard_series == 2
    assert len(parsed.options) == len(fx.EXPIRIES) * 2 * 13
    first = parsed.options.iloc[0]
    assert first["underlying_id"] == "EQ:TEST"
    assert first["instrument_id"].startswith("OPT:TEST")
    assert first["expiry"] == fx.EXPIRIES[0]
    assert parsed.underlying.iloc[0]["iv30"] == 42.0
    assert parsed.snapshot_ts.tzinfo is not None


def test_parse_chain_without_options() -> None:
    assert parse_chain("TEST", "EQ:TEST", fx.payload(options=[])) is None
    assert (
        parse_chain("TEST", "EQ:TEST", b'{"timestamp": "2026-10-02 21:00:00", "data": {}}') is None
    )


def test_session_falls_back_to_snapshot_date() -> None:
    doc = fx.payload().replace(
        b'"last_trade_time": "2026-10-02T16:00:00"', b'"last_trade_time": null'
    )
    parsed = parse_chain("TEST", "EQ:TEST", doc)
    assert parsed is not None
    assert parsed.session_date == date(2026, 10, 2)


def test_every_attempt_waits_on_the_limiter_and_the_retry_time_is_capped() -> None:
    limiter = CountingLimiter()
    body = get_with_retry(
        scripted(OSError("reset"), b"ok"), "u", FAST, lambda s: None, limiter=limiter
    )
    assert (body, limiter.waits) == (b"ok", 2)
    ticks = iter([0.0, 0.0, 100.0, 100.0])
    capped = RetryPolicy(tries=5, base_delay=10, max_delay=10, max_total_s=15)
    with pytest.raises(RuntimeError, match="giving up on u after"):
        get_with_retry(
            scripted(HttpError(500), HttpError(500)),
            "u",
            capped,
            lambda s: None,
            clock=lambda: next(ticks),
        )


def test_circuit_breaker_fails_the_rest_fast_after_consecutive_blocks() -> None:
    breaker = CircuitBreaker("cboe", threshold=3)
    blocked = Http(scripted(*[HttpError(403)] * 3), FAST, breaker=breaker, sleep=lambda s: None)
    with pytest.raises(RuntimeError, match="giving up"):
        blocked.get("u1")  # three 403s in a row: the breaker opens
    assert breaker.open
    with pytest.raises(CircuitOpenError, match="circuit open after 3 consecutive"):
        blocked.get("u2")  # no request sent
    healthy = CircuitBreaker("x", threshold=2)
    http = Http(
        scripted(HttpError(503), b"a", HttpError(503), HttpError(404)),
        FAST,
        breaker=healthy,
        sleep=lambda s: None,
    )
    assert http.get("a") == b"a" and http.get("b") is None  # successes and 404s reset it
    assert not healthy.open
    assert not CircuitBreaker("off", threshold=0).open


def test_cool_down_holds_the_shared_limiter() -> None:
    limiter = CountingLimiter()
    source = CboeOptionsSource(http_for(lambda url: b"{}", limiter=limiter))
    source.cool_down(30.0)
    assert limiter.held == 30.0
    Http(lambda url: b"").cool_down(5.0)  # no limiter: nothing to hold
