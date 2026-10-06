"""The JWKS key cache: one fetch serves until stale, an unknown ``kid`` refetches once (not
more often than the cooldown), a failed fetch keeps the keys, an empty set is no keys."""

import logging

import pytest
from jwt.exceptions import PyJWKClientConnectionError

from algotrade_api.auth.keys import JWKS_PATH, KeySet, jwks_fetch, parse_keys
from tests.apps.api.conftest import KID, SUPABASE_URL, Fetch, Tokens


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_one_fetch_serves_known_kids_until_stale(tokens: Tokens) -> None:
    fetch, clock = tokens.fetch(), Clock()
    keys = KeySet(fetch, max_age=600, cooldown=30, clock=clock)
    assert keys.refresh() and fetch.calls == 1
    assert keys.key_for(KID) is not None and keys.key_for(KID) is not None
    assert fetch.calls == 1
    clock.now += 600
    assert keys.key_for(KID) is not None and fetch.calls == 2  # stale: refetched once


def test_an_unknown_kid_refetches_once_within_the_cooldown(tokens: Tokens) -> None:
    fetch, clock = tokens.fetch(), Clock()
    keys = KeySet(fetch, cooldown=30, clock=clock)
    keys.refresh()
    clock.now += 31
    assert keys.key_for("forged") is None and fetch.calls == 2
    assert keys.key_for("forged") is None and fetch.calls == 2  # cooldown: no fetch storm
    clock.now += 31
    fetch.document = tokens.jwks(KID, "k2")  # the project rotated its key
    found = keys.key_for("k2")
    assert found is not None and found.key_id == "k2" and fetch.calls == 3


def test_the_first_call_fetches_when_startup_did_not(tokens: Tokens) -> None:
    fetch = tokens.fetch()
    keys = KeySet(fetch, clock=Clock())
    assert keys.key_for(KID) is not None and fetch.calls == 1


def test_a_failed_fetch_keeps_the_keys_and_never_raises(
    tokens: Tokens, caplog: pytest.LogCaptureFixture
) -> None:
    fetch, clock = tokens.fetch(), Clock()
    keys = KeySet(fetch, max_age=600, cooldown=30, clock=clock)
    keys.refresh()
    fetch.failure = PyJWKClientConnectionError("down")
    clock.now += 601
    with caplog.at_level(logging.WARNING):
        assert keys.key_for(KID) is not None  # stale, refetch failed: the old key still serves
    assert fetch.calls == 2 and "JWKS fetch failed" in caplog.text
    assert keys.key_for(KID) is not None and fetch.calls == 2  # no retry inside the cooldown
    assert not keys.refresh()


def test_an_empty_or_unusable_set_is_no_keys(tokens: Tokens) -> None:
    assert parse_keys({"keys": []}) == {}
    assert parse_keys({}) == {}
    assert parse_keys({"keys": [{"kty": "nope"}]}) == {}
    assert list(parse_keys({"keys": [{**tokens.jwk(), "kid": ""}]})) == []  # unnamed: unusable
    keys = KeySet(Fetch({"keys": []}), clock=Clock())
    assert keys.refresh() and keys.key_for(KID) is None


def test_a_malformed_document_is_a_failed_fetch() -> None:
    keys = KeySet(Fetch(["not", "an", "object"]), clock=Clock())  # type: ignore[arg-type]
    assert not keys.refresh()


def test_the_default_fetch_reads_the_projects_jwks_url() -> None:
    fetch = jwks_fetch(SUPABASE_URL)
    assert fetch.__self__.uri == f"{SUPABASE_URL}{JWKS_PATH}"  # type: ignore[attr-defined]
