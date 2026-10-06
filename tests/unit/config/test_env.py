"""``config/env.py``: the one reader of environment variables and ``.env``."""

from pathlib import Path

import pytest

from algotrade.config import env


def test_dotenv_never_overrides_and_empty_means_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text('# comment\n\nALGOTRADE_X="from-file"\nnot a pair\nALGOTRADE_Y=\n')
    monkeypatch.delenv("ALGOTRADE_X", raising=False)
    monkeypatch.setenv("ALGOTRADE_Y", "")
    env.load_dotenv(dotenv)
    assert env.credential("ALGOTRADE_X") == "from-file"
    assert env.credential("ALGOTRADE_Y") is None
    env.load_dotenv(tmp_path / "missing")


def test_locations_and_user_resolve_flag_then_environment_then_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (env.DATA_URL, env.CONFIG_DIR, env.USER):
        monkeypatch.delenv(name, raising=False)
    assert env.data_url() == env.DEFAULT_DATA_URL
    assert env.config_dir() == Path("config")
    assert env.user_id("local") == "local"
    monkeypatch.setenv(env.DATA_URL, "memory://")
    monkeypatch.setenv(env.CONFIG_DIR, "/etc/algo")
    monkeypatch.setenv(env.USER, "alice")
    assert env.data_url() == "memory://" and env.data_url("file://x") == "file://x"
    assert env.config_dir() == Path("/etc/algo") and env.config_dir("c") == Path("c")
    assert env.user_id("local") == "alice"


def test_the_api_has_its_own_ibkr_client_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(env.IBKR_API_CLIENT_ID, raising=False)
    monkeypatch.delenv(env.IBKR_CLIENT_ID, raising=False)
    monkeypatch.setenv(env.IBKR_HOST, "127.0.0.1")
    assert env.api_credential(env.IBKR_CLIENT_ID) is None
    assert env.api_credential(env.IBKR_HOST) == "127.0.0.1"
    monkeypatch.setenv(env.IBKR_CLIENT_ID, "17")
    assert env.api_credential(env.IBKR_CLIENT_ID) == "18"  # ingestion's + 1
    monkeypatch.setenv(env.IBKR_CLIENT_ID, "x")
    assert env.api_credential(env.IBKR_CLIENT_ID) is None
    monkeypatch.setenv(env.IBKR_API_CLIENT_ID, "21")
    assert env.api_credential(env.IBKR_CLIENT_ID) == "21"


@pytest.mark.parametrize(
    ("value", "debug"), [("1", True), ("true", True), ("0", False), ("", False)]
)
def test_api_debug(monkeypatch: pytest.MonkeyPatch, value: str, debug: bool) -> None:
    monkeypatch.setenv(env.API_DEBUG, value)
    assert env.api_debug() is debug


def test_auth_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (env.AUTH, env.SUPABASE_URL, env.SUPABASE_JWT_SECRET):
        monkeypatch.delenv(name, raising=False)
    assert (env.auth_mode(), env.supabase_url(), env.supabase_jwt_secret()) == (
        "supabase",
        None,
        None,
    )
    monkeypatch.setenv(env.AUTH, " OFF ")
    monkeypatch.setenv(env.SUPABASE_URL, "https://ref.supabase.co/")
    monkeypatch.setenv(env.SUPABASE_JWT_SECRET, "s3cret")
    assert env.auth_mode() == "off"
    assert env.supabase_url() == "https://ref.supabase.co"
    assert env.supabase_jwt_secret() == "s3cret"


def test_cors_origins_come_from_the_environment_else_the_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    default = ("http://localhost:5173",)
    monkeypatch.delenv(env.CORS_ORIGINS, raising=False)
    assert env.cors_origins(default) == default
    monkeypatch.setenv(env.CORS_ORIGINS, " https://app.example.com/ ,, https://b.example.com")
    assert env.cors_origins(default) == ("https://app.example.com", "https://b.example.com")
    monkeypatch.setenv(env.CORS_ORIGINS, " , ")
    assert env.cors_origins(default) == default


def test_web_dist_comes_from_the_environment_else_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(env.WEB_DIST, raising=False)
    assert env.web_dist() is None
    monkeypatch.setenv(env.WEB_DIST, "  ")
    assert env.web_dist() is None
    monkeypatch.setenv(env.WEB_DIST, " apps/web/dist ")
    assert env.web_dist() == Path("apps/web/dist")
