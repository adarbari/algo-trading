"""Supabase access tokens: what verifies (ES256 from the JWKS, HS256 with the secret) and
everything that must not (401), and verified callers the registry does not know (403)."""

import base64
import hashlib
import hmac
import json
import time
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from starlette.requests import Request

from algotrade.config.site.users import Identity, Role, UsersSettings
from algotrade_api.auth.keys import KeySet
from algotrade_api.auth.protocol import ForbiddenError, UnauthenticatedError
from algotrade_api.auth.supabase import SupabaseAuthenticator, bearer_token
from tests.apps.api.conftest import SUPABASE_URL, Fetch, Tokens


def request(authorization: str | None) -> Request:
    headers = [] if authorization is None else [(b"authorization", authorization.encode())]
    return Request({"type": "http", "headers": headers, "server": ("10.0.0.1", 443)})


def bearer(token: str) -> Request:
    return request(f"Bearer {token}")


@pytest.fixture
def fetch(tokens: Tokens) -> Fetch:
    return tokens.fetch()


@pytest.fixture
def auth(users: UsersSettings, fetch: Fetch, tokens: Tokens) -> SupabaseAuthenticator:
    keys = KeySet(fetch)
    keys.refresh()
    return SupabaseAuthenticator(SUPABASE_URL, users, keys, tokens.secret)


def test_an_es256_token_from_the_jwks_is_the_registry_user(
    auth: SupabaseAuthenticator, tokens: Tokens
) -> None:
    user = auth.authenticate(bearer(tokens.mint()))
    assert (user.user_id, user.role) == ("ana", Role.ADMIN)


def test_an_hs256_token_verifies_with_the_legacy_secret(
    auth: SupabaseAuthenticator, tokens: Tokens
) -> None:
    user = auth.authenticate(bearer(tokens.mint("HS256", kid=None, email="tom@example.com")))
    assert (user.user_id, user.role) == ("tom", Role.TRADER)


def test_roles_come_from_the_registry_not_the_token(
    auth: SupabaseAuthenticator, tokens: Tokens
) -> None:
    token = tokens.mint(email="tom@example.com", role="service_role", app_metadata={"r": "admin"})
    assert auth.authenticate(bearer(token)).role is Role.TRADER


def test_email_case_is_ignored(auth: SupabaseAuthenticator, tokens: Tokens) -> None:
    assert auth.authenticate(bearer(tokens.mint(email="ANA@Example.com"))).user_id == "ana"


def _unsigned(header: dict[str, Any], claims: dict[str, Any], key: bytes) -> str:
    """A token HMAC-signed by hand (PyJWT refuses a public key as an HMAC secret)."""

    def part(value: dict[str, Any]) -> bytes:
        return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=")

    signing = part(header) + b"." + part(claims)
    mac = hmac.new(key, signing, hashlib.sha256).digest()
    return (signing + b"." + base64.urlsafe_b64encode(mac).rstrip(b"=")).decode()


def _bad_tokens(tokens: Tokens) -> dict[str, str]:
    now = int(time.time())
    other = Tokens()  # a key pair the project never published
    public_pem = tokens.private.public_key().public_bytes(
        Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
    )
    return {
        "alg none": jwt.encode(tokens.claims(), "", algorithm="none"),
        "foreign key, known kid": other.mint(),
        "unknown kid": tokens.mint(kid="k9"),
        "no kid": tokens.mint(kid=None),
        "hs256 with another secret": tokens.mint("HS256", kid=None, key="x" * 32),
        "alg confusion: hs256 keyed with the public key": _unsigned(
            {"alg": "HS256", "typ": "JWT", "kid": "k1"}, tokens.claims(), public_pem
        ),
        "header alg differs from the key's": _unsigned(
            {"alg": "RS256", "typ": "JWT", "kid": "k1"}, tokens.claims(), b"k"
        ),
        "expired beyond the leeway": tokens.mint(exp=now - 31, iat=now - 3600),
        "issued in the future": tokens.mint(iat=now + 120, exp=now + 3600),
        "wrong issuer": tokens.mint(iss="https://other.supabase.co/auth/v1"),
        "wrong audience": tokens.mint(aud="anon"),
        "no sub": tokens.mint(sub=None),
        "no exp": tokens.mint(exp=None),
        "garbage": "not.a.token",
        # The project's API keys are HS256 JWTs signed with the same secret: no aud, iss
        # "supabase", no email. They are not a user's session and must never pass.
        "anon key": tokens.mint(
            "HS256", kid=None, iss="supabase", role="anon", aud=None, sub=None, email=None
        ),
        "service_role key": tokens.mint(
            "HS256", kid=None, iss="supabase", role="service_role", aud=None, sub=None, email=None
        ),
    }


BAD = (
    "alg none", "foreign key, known kid", "unknown kid", "no kid", "hs256 with another secret",
    "alg confusion: hs256 keyed with the public key", "header alg differs from the key's",
    "expired beyond the leeway", "issued in the future", "wrong issuer", "wrong audience",
    "no sub", "no exp", "garbage", "anon key", "service_role key",
)  # fmt: skip


@pytest.mark.parametrize("case", BAD)
def test_tokens_that_must_not_verify_are_401(
    auth: SupabaseAuthenticator, tokens: Tokens, case: str
) -> None:
    bad = _bad_tokens(tokens)
    assert set(bad) == set(BAD)
    with pytest.raises(UnauthenticatedError):
        auth.authenticate(bearer(bad[case]))


def test_expiry_inside_the_leeway_still_verifies(
    auth: SupabaseAuthenticator, tokens: Tokens
) -> None:
    now = int(time.time())
    assert auth.authenticate(bearer(tokens.mint(exp=now - 20, iat=now - 3600))).user_id == "ana"


def test_hs256_is_refused_without_a_secret(
    users: UsersSettings, fetch: Fetch, tokens: Tokens
) -> None:
    auth = SupabaseAuthenticator(SUPABASE_URL, users, KeySet(fetch), secret=None)
    with pytest.raises(UnauthenticatedError):
        auth.authenticate(bearer(tokens.mint("HS256", kid=None)))
    assert auth.authenticate(bearer(tokens.mint())).user_id == "ana"


@pytest.mark.parametrize(
    "header", [None, "", "Bearer", "Bearer ", "Basic YW5hOnB3", "Token abc", "Bearer a b"]
)
def test_no_bearer_header_is_401(auth: SupabaseAuthenticator, header: str | None) -> None:
    with pytest.raises(UnauthenticatedError):
        auth.authenticate(request(header))


def test_the_bearer_scheme_is_case_insensitive() -> None:
    assert bearer_token("bearer abc") == "abc" and bearer_token(" Bearer  abc ") == "abc"


@pytest.mark.parametrize(
    "claims",
    [
        {"email": "nobody@example.com"},  # signed up, but not in the registry
        {"email": None},
        {"email": ""},
        {"is_anonymous": True},  # an anonymous sign-in, even with a registered email
    ],
)
def test_verified_callers_outside_the_registry_are_403(
    auth: SupabaseAuthenticator, tokens: Tokens, claims: dict[str, Any]
) -> None:
    with pytest.raises(ForbiddenError) as raised:
        auth.authenticate(bearer(tokens.mint(**claims)))
    assert "@" not in str(raised.value)  # never echoes the email


def test_a_rotated_key_takes_one_fetch(users: UsersSettings, tokens: Tokens, fetch: Fetch) -> None:
    keys = KeySet(fetch, cooldown=0)  # (the 30 s cooldown is test_keys')
    auth = SupabaseAuthenticator(SUPABASE_URL, users, keys)
    assert auth.authenticate(bearer(tokens.mint())).user_id == "ana"
    assert fetch.calls == 1
    fetch.document = tokens.jwks("k1", "k2")
    for _ in range(3):
        assert auth.authenticate(bearer(tokens.mint(kid="k2"))).user_id == "ana"
    assert fetch.calls == 2


def test_errors_never_carry_the_token(auth: SupabaseAuthenticator, tokens: Tokens) -> None:
    token = tokens.mint(iss="https://other.supabase.co/auth/v1")
    with pytest.raises(UnauthenticatedError) as raised:
        auth.authenticate(bearer(token))
    assert token not in str(raised.value) and "other.supabase" not in str(raised.value)


def test_a_symmetric_key_in_the_jwks_is_never_used(users: UsersSettings, tokens: Tokens) -> None:
    secret = "an-oct-key-published-in-the-jwks-32b"
    oct_key = {"kty": "oct", "k": base64.urlsafe_b64encode(secret.encode()).decode().rstrip("=")}
    keys = KeySet(Fetch({"keys": [{**oct_key, "kid": "k1", "alg": "HS256"}]}))
    for configured in (None, tokens.secret):
        auth = SupabaseAuthenticator(SUPABASE_URL, users, keys, configured)
        with pytest.raises(UnauthenticatedError):
            auth.authenticate(bearer(tokens.mint("HS256", kid="k1", key=secret)))


PINNED = "7b1c1d2e-0000-4000-8000-0000000000aa"


@pytest.fixture
def pinned(users: UsersSettings, fetch: Fetch) -> SupabaseAuthenticator:
    """ana's subject is pinned in her identity.toml; tom's is not."""
    pins = {
        u.user_id: Identity(u.email, PINNED if u.user_id == "ana" else None) for u in users.users
    }
    return SupabaseAuthenticator(SUPABASE_URL, users.with_identities(pins), KeySet(fetch))


def test_a_pinned_subject_must_match(pinned: SupabaseAuthenticator, tokens: Tokens) -> None:
    assert pinned.authenticate(bearer(tokens.mint(sub=PINNED.upper()))).user_id == "ana"
    with pytest.raises(ForbiddenError) as raised:  # her email, someone else's account
        pinned.authenticate(bearer(tokens.mint()))
    assert PINNED not in str(raised.value) and "@" not in str(raised.value)


def test_without_a_pinned_subject_the_email_decides(
    pinned: SupabaseAuthenticator, tokens: Tokens
) -> None:
    assert pinned.authenticate(bearer(tokens.mint(email="tom@example.com"))).user_id == "tom"
