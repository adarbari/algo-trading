import gzip
import io
import urllib.error
from dataclasses import replace
from datetime import date
from email.message import Message
from pathlib import Path
from unittest import mock

import pytest

from algotrade_sources.framework.base import FetchRequest
from algotrade_sources.framework.http import (
    CircuitBreaker,
    CircuitOpenError,
    Http,
    HttpError,
    RetryPolicy,
    get_with_retry,
    json_post_transport,
    urllib_transport,
)
from algotrade_sources.framework.limiter import Limiter, Pacing
from algotrade_sources.vendors.cboe.option_chains import (
    URL,
    CboeOptionsSource,
    missing_chain,
    parse_chain,
)
from tests.helpers.ingest_fakes import CountingLimiter, http_for
from tests.helpers.payloads import cboe as fx

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


def test_urllib_transport_asks_for_gzip_and_decompresses() -> None:
    response = mock.MagicMock()
    inner = response.__enter__.return_value
    inner.read.return_value = gzip.compress(b'{"cik": 1}')
    inner.headers = {"Content-Encoding": "gzip"}
    with mock.patch("urllib.request.urlopen", return_value=response) as opened:
        assert urllib_transport()("https://example.com") == b'{"cik": 1}'
    assert opened.call_args.args[0].get_header("Accept-encoding") == "gzip"


def test_json_post_transport_posts_json_with_the_headers_given() -> None:
    response = mock.MagicMock()
    response.__enter__.return_value.read.return_value = b'{"choices": []}'
    with mock.patch("urllib.request.urlopen", return_value=response) as opened:
        post = json_post_transport(timeout=5.0, headers={"Authorization": "Bearer k"})
        assert post("https://example.com/v1/chat/completions", b'{"a": 1}') == b'{"choices": []}'
    request = opened.call_args.args[0]
    assert request.get_method() == "POST" and request.data == b'{"a": 1}'
    assert request.get_header("Content-type") == "application/json"
    assert request.get_header("Authorization") == "Bearer k"
    assert opened.call_args.kwargs["timeout"] == 5.0
    err = urllib.error.HTTPError("u", 401, "no", Message(), io.BytesIO(b'{"error": "bad key"}'))
    with mock.patch("urllib.request.urlopen", side_effect=err), pytest.raises(HttpError) as exc:
        json_post_transport()("https://example.com", b"{}")
    assert exc.value.status == 401 and b"bad key" in exc.value.body


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


S3_MISSING = b'<?xml version="1.0" encoding="UTF-8"?>\n<Error><Code>AccessDenied</Code></Error>'


def test_vendor_not_found_errors_return_none_and_do_not_trip_the_breaker() -> None:
    policy = replace(FAST, not_found=missing_chain)
    breaker = CircuitBreaker("cboe", 2)
    missing = [HttpError(403, body=S3_MISSING)] * 5
    http = Http(scripted(*missing, b"chain"), policy, breaker=breaker, sleep=lambda s: None)
    assert [http.get("u") for _ in range(5)] == [None] * 5  # five missing chains in a row
    assert not breaker.open
    assert http.get("u") == b"chain"


def test_a_block_is_still_an_error_even_with_a_not_found_rule() -> None:
    policy = replace(FAST, tries=1, not_found=missing_chain)
    breaker = CircuitBreaker("cboe", 2)
    block = HttpError(403, body=b"<html>Attention Required! | Cloudflare</html>")
    http = Http(scripted(block, block, b"never"), policy, breaker=breaker, sleep=lambda s: None)
    for _ in range(2):
        with pytest.raises(RuntimeError):
            http.get("u")
    assert breaker.open


class Clock:
    def __init__(self) -> None:
        self.now, self.slept = 1000.0, []  # type: ignore[var-annotated]

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def test_429_holds_the_shared_limiter_for_retry_after_and_backs_off(tmp_path: Path) -> None:
    clock = Clock()
    pacing = Pacing(1.0, max_interval_s=5.0)
    limiter = Limiter("cboe", pacing, tmp_path, clock.sleep, clock)
    stats = limiter.track()
    in_thread: list[float] = []
    body = get_with_retry(
        scripted(HttpError(429, 47.0), b"ok"), "u", FAST, in_thread.append, limiter=limiter
    )
    assert body == b"ok"
    assert in_thread == []  # the limiter waits it out, for every thread and process
    assert clock.slept == [47.0] and limiter.interval == 1.5
    assert (stats.requests, stats.throttled_429, stats.retry_after_wait_s) == (2, 1, 47.0)
    assert stats.errors == 1 and stats.limiter_wait_s == 47.0


def test_outcomes_reported_to_the_limiter() -> None:
    limiter = CountingLimiter()
    policy = replace(FAST, not_found=missing_chain)
    denied = HttpError(403, body=b"<Error><Code>AccessDenied</Code></Error>")
    assert get_with_retry(scripted(denied), "u", policy, lambda s: None, limiter=limiter) is None
    flaky = scripted(OSError("timeout"), HttpError(503), b"x")
    get_with_retry(flaky, "u", policy, lambda s: None, limiter=limiter)
    assert limiter.outcomes == ["missing", "error", "error", "ok"]
    no_header = RetryPolicy(tries=2, max_delay=9.0)
    get_with_retry(scripted(HttpError(429), b"x"), "u", no_header, lambda s: None, limiter=limiter)
    assert limiter.outcomes[-2:] == ["429", "ok"] and limiter.held == 5.0  # exponential default
