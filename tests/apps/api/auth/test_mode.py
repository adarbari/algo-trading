"""Choosing the authenticator: off serves a declared user; supabase needs the project URL,
fetches its keys once at startup and still starts when the fetch fails."""

import pytest
from jwt.exceptions import PyJWKClientConnectionError

from algotrade.config.site.users import UsersSettings
from algotrade.core.model.errors import ConfigurationError
from algotrade_api.auth.local import LocalAuthenticator
from algotrade_api.auth.mode import AuthConfig, AuthMode, open_authenticator
from algotrade_api.auth.supabase import SupabaseAuthenticator
from tests.apps.api.conftest import SUPABASE_URL, Tokens


def test_config_from_the_environments_values() -> None:
    assert AuthConfig.of("off", None, None).mode is AuthMode.OFF
    config = AuthConfig.of("supabase", SUPABASE_URL, "s3cret")
    assert (config.mode, config.supabase_url) == (AuthMode.SUPABASE, SUPABASE_URL)
    assert "s3cret" not in repr(config)
    with pytest.raises(ConfigurationError, match="ALGOTRADE_AUTH='maybe'"):
        AuthConfig.of("maybe", None, None)


def test_off_serves_a_declared_user(users: UsersSettings) -> None:
    auth = open_authenticator(AuthConfig(AuthMode.OFF), users, "ana")
    assert isinstance(auth, LocalAuthenticator)
    with pytest.raises(ConfigurationError, match="not declared"):
        open_authenticator(AuthConfig(AuthMode.OFF), users, "nobody")


def test_supabase_needs_the_project_url(users: UsersSettings) -> None:
    with pytest.raises(ConfigurationError, match="SUPABASE_URL"):
        open_authenticator(AuthConfig(), users, "local")


def test_supabase_fetches_the_keys_once_at_startup(users: UsersSettings, tokens: Tokens) -> None:
    fetch = tokens.fetch()
    auth = open_authenticator(AuthConfig(AuthMode.SUPABASE, SUPABASE_URL), users, "x", fetch)
    assert isinstance(auth, SupabaseAuthenticator) and fetch.calls == 1


def test_a_provider_outage_does_not_stop_the_api_starting(
    users: UsersSettings, tokens: Tokens
) -> None:
    fetch = tokens.fetch()
    fetch.failure = PyJWKClientConnectionError("down")
    auth = open_authenticator(AuthConfig(AuthMode.SUPABASE, SUPABASE_URL), users, "x", fetch)
    assert isinstance(auth, SupabaseAuthenticator) and fetch.calls == 1
