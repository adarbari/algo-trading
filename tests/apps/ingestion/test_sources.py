import io
import urllib.error
from datetime import date
from email.message import Message
from unittest import mock

import pytest

from algotrade_ingestion.sources.cboe import URL, CboeOptionsSource, parse_chain
from algotrade_ingestion.sources.http import (
    HttpError,
    RetryPolicy,
    get_with_retry,
    urllib_transport,
)
from tests import cboe_fixture as fx

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
    source = CboeOptionsSource(lambda url: seen.append(url) or b"{}", lambda s: None)
    assert source.fetch("_SPX") == b"{}"
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
