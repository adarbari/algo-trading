"""Supabase access tokens, verified offline (ADR 0040 decision 3).

``Authorization: Bearer <token>`` is the only credential. The token's header picks the key:
an asymmetric token (ES256 / RS256) names a ``kid`` the project's JWKS holds, and its ``alg``
must be that key's; an HS256 token is checked against the legacy secret, and only when one is
configured. Anything else (``none``, another algorithm, an unknown key) is refused before the
signature is looked at, so a token can never choose how it is verified. The claims must carry
``exp``, ``iat``, ``iss`` (the project's ``/auth/v1``), ``aud`` (``authenticated``) and ``sub``,
with 30 s of clock leeway. A verified token maps to the registry user whose identity email it
carries, and when that user has a pinned ``subject`` the token's ``sub`` must equal it;
anonymous sign-ins, tokens without an email (the project's anon and service-role keys fail
``aud`` before that), unknown emails and a subject that is not the user's are 403. Nothing
here logs a token, a claim or an email."""

import uuid
from collections.abc import Mapping
from typing import Any

import jwt
from jwt.exceptions import PyJWTError
from starlette.requests import Request

from algotrade.config.site.users import UserRecord, UsersSettings
from algotrade_api.auth.keys import KeySet
from algotrade_api.auth.protocol import ForbiddenError, UnauthenticatedError

AUDIENCE = "authenticated"
SYMMETRIC = "HS256"
ASYMMETRIC = ("ES256", "RS256")
REQUIRED = ["exp", "iat", "iss", "aud", "sub"]
LEEWAY_S = 30.0


def bearer_token(header: str | None) -> str:
    """The token of an ``Authorization: Bearer <token>`` header (401 for anything else)."""
    scheme, _, token = (header or "").strip().partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not token or " " in token:
        raise UnauthenticatedError("a bearer token is required")
    return token


class SupabaseAuthenticator:
    """Resolves a request's caller from its Supabase access token and the user registry."""

    def __init__(
        self,
        url: str,
        users: UsersSettings,
        keys: KeySet,
        secret: str | None = None,
        leeway: float = LEEWAY_S,
    ) -> None:
        self._issuer = f"{url.rstrip('/')}/auth/v1"
        self._users = users
        self._keys = keys
        self._secret = secret
        self._leeway = leeway

    def authenticate(self, request: Request) -> UserRecord:
        token = bearer_token(request.headers.get("authorization"))
        return self.user_of(self.verify(token))

    def verify(self, token: str) -> Mapping[str, Any]:
        """The token's claims once its signature, issuer, audience and times check out."""
        key, algorithm = self._key(token)
        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                key,
                algorithms=[algorithm],
                audience=AUDIENCE,
                issuer=self._issuer,
                leeway=self._leeway,
                options={"require": REQUIRED},
            )
        except PyJWTError as exc:
            raise UnauthenticatedError("the token does not verify") from exc
        return claims

    def _key(self, token: str) -> tuple[Any, str]:
        """The key and the one algorithm the token may be verified with."""
        try:
            header = jwt.get_unverified_header(token)
        except PyJWTError as exc:
            raise UnauthenticatedError("the token is malformed") from exc
        algorithm = header.get("alg")
        if algorithm == SYMMETRIC and self._secret:
            return self._secret, SYMMETRIC
        kid = header.get("kid")
        if algorithm in ASYMMETRIC and isinstance(kid, str):
            jwk = self._keys.key_for(kid)
            if jwk is not None and jwk.algorithm_name == algorithm:
                return jwk.key, algorithm
        raise UnauthenticatedError("the token's key or algorithm is not accepted")

    def user_of(self, claims: Mapping[str, Any]) -> UserRecord:
        """The registry user of verified ``claims`` (403 when there is none)."""
        if claims.get("is_anonymous") is True:
            raise ForbiddenError("anonymous sign-ins have no access")
        email = claims.get("email")
        if not isinstance(email, str) or not email.strip():
            raise ForbiddenError("the token carries no email")
        user = self._users.by_email(email)
        if user is None:
            raise ForbiddenError("no registered user has this email")
        if user.subject is not None and _subject(claims.get("sub")) != user.subject:
            raise ForbiddenError("the token's subject is not this user's")
        return user


def _subject(sub: object) -> str | None:
    """A token's ``sub`` as the registry stores a subject (a normalised UUID), else None."""
    try:
        return str(uuid.UUID(sub)) if isinstance(sub, str) else None
    except ValueError:
        return None
