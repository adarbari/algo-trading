"""``classify`` and ``AccessProbe``: what a vendor key may call, from one un-retried answer.

The 402 and 403 bodies are RECORDED (FMP ``Premium Query Parameter``, Finnhub ``You don't have
access``, 2026-10-16); the 200 payloads are recorded rows."""

from collections.abc import Mapping
from typing import ClassVar

import pytest

from algotrade_sources.framework.access import AccessProbe, UnclassifiedError, classify
from algotrade_sources.framework.base import Access, FetchRequest, ProbeSource
from algotrade_sources.framework.http import Answer, HttpError, RetryPolicy
from tests.conftest import REPO_ROOT
from tests.helpers.ingest_fakes import CountingLimiter, http_for

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "sources"
ROWS = (FIXTURES / "fmp" / "price_target_consensus_aapl.json").read_bytes()
FMP_402 = (FIXTURES / "fmp" / "premium_402.txt").read_bytes()
FINNHUB_403 = (FIXTURES / "finnhub" / "price_target_403.json").read_bytes()


def test_a_200_with_rows_is_allowed() -> None:
    verdict = classify(Answer(200, ROWS))
    assert (verdict.access, verdict.http_code, verdict.rows) == (Access.ALLOWED, 200, 1)


@pytest.mark.parametrize(
    ("status", "body"), [(402, FMP_402), (403, FINNHUB_403), (401, b""), (402, b"")]
)
def test_401_402_403_are_denied(status: int, body: bytes) -> None:
    verdict = classify(Answer(status, body))
    assert (verdict.access, verdict.http_code) == (Access.DENIED, status)


def test_a_429_is_limited() -> None:
    verdict = classify(Answer(429, b'{"error": "API limit reached"}'))
    assert (verdict.access, verdict.http_code) == (Access.LIMITED, 429)


@pytest.mark.parametrize("body", [b"[]", b"{}", b"", b"  \n"])
def test_an_empty_200_for_a_covered_name_is_limited(body: bytes) -> None:
    verdict = classify(Answer(200, body))
    assert (verdict.access, verdict.http_code, verdict.rows) == (Access.LIMITED, 200, 0)


@pytest.mark.parametrize(
    "body",
    [
        FMP_402,
        b'{"Error Message": "Restricted Endpoint: this is a premium feature"}',
        b'{"error": "Please upgrade your plan"}',
    ],
)
def test_a_200_whose_body_is_an_upgrade_or_restricted_message_is_denied(body: bytes) -> None:
    assert classify(Answer(200, body)).access is Access.DENIED


def test_a_200_whose_body_says_the_quota_is_used_is_limited() -> None:
    body = b'{"Error Message": "Limit Reach . Please upgrade your plan"}'
    assert classify(Answer(200, body)).access is Access.LIMITED  # quota wins over "upgrade"


@pytest.mark.parametrize("status", [400, 404, 500, 503])
def test_other_statuses_are_no_verdict(status: int) -> None:
    with pytest.raises(UnclassifiedError, match=str(status)):
        classify(Answer(status, b""))


def test_a_200_with_an_unknown_message_is_no_verdict() -> None:
    with pytest.raises(UnclassifiedError):
        classify(Answer(200, b'{"message": "maintenance"}'))


def test_the_note_is_fixed_words_never_the_vendor_body() -> None:
    body = b"Premium Query Parameter: secret-looking-text-123"
    assert "secret-looking" not in classify(Answer(402, body)).note
    assert "secret-looking" not in classify(Answer(200, body)).note


class Probe(AccessProbe):
    name = "vendor"
    endpoints: ClassVar[Mapping[str, str]] = {
        "ok": "https://v.example/ok",
        "no": "https://v.example/no",
    }


def test_a_probe_asks_once_and_never_retries_a_refusal_waiting_on_the_limiter() -> None:
    calls: list[str] = []

    def transport(url: str) -> bytes:
        calls.append(url)
        if url.endswith("/no"):
            raise HttpError(402, body=FMP_402)
        return ROWS

    limiter = CountingLimiter()
    probe = Probe(http_for(transport, RetryPolicy(tries=7), limiter))
    assert probe.probe("ok").access is Access.ALLOWED
    assert probe.probe("no").access is Access.DENIED
    assert calls == ["https://v.example/ok", "https://v.example/no"]  # one request each
    assert limiter.waits == 2 and limiter.outcomes == ["ok", "error"]


def test_a_probe_answers_a_429_without_holding_the_vendor() -> None:
    def transport(url: str) -> bytes:
        raise HttpError(429, retry_after=60.0)

    limiter = CountingLimiter()
    assert Probe(http_for(transport, limiter=limiter)).probe("ok").access is Access.LIMITED
    assert limiter.held == 0.0  # the probe reports; it does not back off or retry


def test_a_probe_is_a_probe_source_for_the_task() -> None:
    assert isinstance(Probe(http_for(lambda url: ROWS)), ProbeSource)


def test_a_probe_source_fetches_by_endpoint_and_normalizes_to_nothing_stored() -> None:
    probe = Probe(http_for(lambda url: ROWS))
    payload = probe.fetch(FetchRequest("ok"))
    normalized = probe.normalize(FetchRequest("ok"), payload or b"")
    assert normalized is not None and normalized.tables == {} and normalized.notes == {"rows": 1}
