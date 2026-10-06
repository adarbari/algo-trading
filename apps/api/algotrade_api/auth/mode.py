"""Which authenticator the app runs (ADR 0040): ``AuthConfig`` from the environment
(``ALGOTRADE_AUTH``, ``SUPABASE_URL``, ``SUPABASE_JWT_SECRET``) and ``open_authenticator``.
Supabase mode needs the project URL; its keys are fetched once here, and a failed fetch is
logged, not fatal (an outage of the provider must not stop the API from starting: the next
request with an unknown key fetches again). Off mode serves a declared user only."""

from dataclasses import dataclass, field
from enum import StrEnum
from urllib.parse import urlparse

from algotrade.config.site.users import UsersSettings
from algotrade.core.model.errors import ConfigurationError
from algotrade_api.auth.keys import Fetch, KeySet, jwks_fetch
from algotrade_api.auth.local import LocalAuthenticator, is_loopback
from algotrade_api.auth.protocol import Authenticator
from algotrade_api.auth.supabase import SupabaseAuthenticator


class AuthMode(StrEnum):
    SUPABASE = "supabase"  # a Supabase access token on every request
    OFF = "off"  # the API's user without a token, loopback only


@dataclass(frozen=True)
class AuthConfig:
    mode: AuthMode = AuthMode.SUPABASE
    supabase_url: str | None = None
    jwt_secret: str | None = field(default=None, repr=False)

    @classmethod
    def of(cls, mode: str, supabase_url: str | None, jwt_secret: str | None) -> "AuthConfig":
        """From the environment's values (``algotrade.config.env``); an unknown mode is refused."""
        if mode not in tuple(AuthMode):
            choices = ", ".join(m.value for m in AuthMode)
            raise ConfigurationError(f"ALGOTRADE_AUTH={mode!r}: expected one of {choices}")
        return cls(AuthMode(mode), supabase_url, jwt_secret)


def open_authenticator(
    config: AuthConfig, users: UsersSettings, user_id: str, fetch: Fetch | None = None
) -> Authenticator:
    """The app's authenticator: ``off`` serves ``user_id`` (a declared user); ``supabase``
    verifies tokens with the project's keys (``fetch``: the JWKS, default over HTTPS)."""
    if config.mode is AuthMode.OFF:
        user = users.get(user_id)
        if user is None:
            raise ConfigurationError(f"ALGOTRADE_USER {user_id!r} is not declared in users.toml")
        return LocalAuthenticator(user)
    if not config.supabase_url:
        raise ConfigurationError(
            "ALGOTRADE_AUTH=supabase needs SUPABASE_URL (ALGOTRADE_AUTH=off: a local-only API)"
        )
    url = config.supabase_url.rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme != "https" and not (
        parsed.scheme == "http" and is_loopback(parsed.hostname or "")
    ):
        raise ConfigurationError("SUPABASE_URL: expected https:// (http:// only on loopback)")
    keys = KeySet(fetch if fetch is not None else jwks_fetch(url))
    keys.refresh()
    return SupabaseAuthenticator(url, users, keys, config.jwt_secret)
