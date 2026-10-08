"""The environment: the ONE place that reads environment variables (ADR 0019, ``secrets-env``).

Credentials, the data and config locations and the default user only ever come from the
process environment, optionally seeded from a local ``.env`` file (``load_dotenv``; entry
points call it once). Everything else receives values from here as parameters: the storage
factory gets the data URL, the source registry gets ``credential``.
"""

import os
from pathlib import Path

DATA_URL = "ALGOTRADE_DATA_URL"
DEFAULT_DATA_URL = "file://./var/data"
CONFIG_DIR = "ALGOTRADE_CONFIG_DIR"
DEFAULT_CONFIG_DIR = "config"
USER = "ALGOTRADE_USER"
API_DEBUG = "ALGOTRADE_API_DEBUG"  # "1": the API serves the GraphiQL IDE (local development)
PORT_BASE = "ALGOTRADE_PORT_BASE"  # first of a worktree's ports: the API serves on it
CORS_ORIGINS = "ALGOTRADE_CORS_ORIGINS"  # comma-separated web origins the API allows (hosting)
# The built web app the API serves on its own origin (ADR 0044): `var/web` after
# `make web-build`; unset: the API serves no files (development runs the Vite dev server).
WEB_DIST = "ALGOTRADE_WEB_DIST"
# Who may call the API (ADR 0040): "supabase" (default) verifies a Supabase access token per
# request; "off" serves ALGOTRADE_USER without one, and only on a loopback address.
AUTH = "ALGOTRADE_AUTH"
DEFAULT_AUTH = "supabase"
SUPABASE_URL = "SUPABASE_URL"  # the project URL: https://<ref>.supabase.co (its JWKS, its iss)
SUPABASE_JWT_SECRET = "SUPABASE_JWT_SECRET"  # the legacy HS256 secret; unset: JWKS keys only
# The nightly summary email (workflows/nightly/notify.py): personal data stays out of the repo.
NOTIFY_EMAIL_TO = "ALGOTRADE_NOTIFY_EMAIL_TO"  # comma-separated recipients
NOTIFY_EMAIL_FROM = "ALGOTRADE_NOTIFY_EMAIL_FROM"  # default: the first recipient
SMTP_USER = "ALGOTRADE_SMTP_USER"
SMTP_PASSWORD = "ALGOTRADE_SMTP_PASSWORD"  # Gmail: an app password, never the account password
# IB Gateway (read-only market data for the verify task): where it listens, which API client id.
IBKR_HOST = "ALGOTRADE_IBKR_HOST"
IBKR_PORT = "ALGOTRADE_IBKR_PORT"
IBKR_CLIENT_ID = "ALGOTRADE_IBKR_CLIENT_ID"
# The API's live option quotes (ADR 0028) connect with their own client id, never ingestion's.
IBKR_API_CLIENT_ID = "ALGOTRADE_IBKR_API_CLIENT_ID"  # default: ALGOTRADE_IBKR_CLIENT_ID + 1

# Keys a working checkout needs in .env (values never leave this module): the vendor key and the
# SEC fair-access contact. Everything else is optional or defaulted. `make doctor` lists them.
MASSIVE_API_KEY = "ALGOTRADE_MASSIVE_API_KEY"
SEC_CONTACT = "ALGOTRADE_SEC_CONTACT"
# Tiingo daily prices (the event-study history from 2018, ADR 0050): optional, free key; no key:
# the source is skipped and `bars-history` with it.
TIINGO_API_KEY = "ALGOTRADE_TIINGO_API_KEY"
# The text model behind natural-language screener drafts (ADR 0041): optional (a local server
# needs none); the provider is `config/site/llm.toml`, never the environment.
LLM_API_KEY = "ALGOTRADE_LLM_API_KEY"  # the single-provider (legacy) form of llm.toml only
LLM_KEY_PREFIX = "ALGOTRADE_LLM_API_KEY_"  # + the provider id upper-cased: see `llm_key`
REQUIRED_KEYS = (MASSIVE_API_KEY, SEC_CONTACT)

__all__ = [
    "REQUIRED_KEYS",
    "api_credential",
    "api_debug",
    "auth_mode",
    "config_dir",
    "credential",
    "data_url",
    "dotenv_keys",
    "llm_key",
    "load_dotenv",
    "supabase_jwt_secret",
    "supabase_url",
    "user_id",
    "web_dist",
]


def dotenv_keys(path: Path = Path(".env")) -> set[str]:
    """The NAMES of the keys that have a non-empty value in the .env file or the environment
    (never the values: for `make doctor`)."""
    found = {k for k in REQUIRED_KEYS if credential(k)}
    if path.exists():
        for raw in path.read_text().splitlines():
            key, sep, value = raw.strip().partition("=")
            if sep and not key.startswith("#") and value.strip().strip("\"'"):
                found.add(key.strip())
    return found


def load_dotenv(path: Path = Path(".env")) -> None:
    """Load ``KEY=VALUE`` lines into the environment without overriding variables already set."""
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def port_base(default: int) -> int:
    """``$ALGOTRADE_PORT_BASE`` (a worktree's ports, ``scripts/worktree.sh``), else ``default``."""
    raw = credential(PORT_BASE) or ""
    return int(raw) if raw.isdigit() else default


def llm_key(provider_id: str) -> str:
    """The environment variable holding the key of the ``[[provider]]`` with this id in
    ``llm.toml``: ``ALGOTRADE_LLM_API_KEY_<ID upper>`` (``claude`` -> ``..._CLAUDE``). The
    name, never the value: read it with ``credential``."""
    return LLM_KEY_PREFIX + provider_id.upper()


def credential(name: str) -> str | None:
    """The variable's value; ``None`` when unset or empty. Never logged or stored."""
    return os.environ.get(name) or None


def api_credential(name: str) -> str | None:
    """``credential`` as the API sees it: the IBKR client id is the API's own
    (``$ALGOTRADE_IBKR_API_CLIENT_ID``, else ``$ALGOTRADE_IBKR_CLIENT_ID`` + 1), so the API's
    live quotes and an ingestion run never share an IB Gateway session id."""
    if name != IBKR_CLIENT_ID:
        return credential(name)
    own, shared = credential(IBKR_API_CLIENT_ID), credential(IBKR_CLIENT_ID)
    if own is not None or shared is None:
        return own
    return str(int(shared) + 1) if shared.isdigit() else None


def data_url(explicit: str | None = None) -> str:
    """The storage URL: ``explicit`` (a CLI flag), else ``$ALGOTRADE_DATA_URL``, else ./var/data."""
    return explicit or credential(DATA_URL) or DEFAULT_DATA_URL


def config_dir(explicit: str | Path | None = None) -> Path:
    """The config root: ``explicit``, else ``$ALGOTRADE_CONFIG_DIR``, else ./config."""
    return Path(explicit or credential(CONFIG_DIR) or DEFAULT_CONFIG_DIR)


def api_debug() -> bool:
    """``$ALGOTRADE_API_DEBUG`` is ``1`` / ``true``: the API serves its development tools."""
    return (credential(API_DEBUG) or "").strip().lower() in ("1", "true")


def cors_origins(default: tuple[str, ...]) -> tuple[str, ...]:
    """``$ALGOTRADE_CORS_ORIGINS`` (comma-separated origins, blanks and trailing slashes
    dropped), else ``default`` (the local web dev server)."""
    raw = credential(CORS_ORIGINS)
    found = tuple(o.strip().rstrip("/") for o in (raw or "").split(",") if o.strip())
    return found or default


def web_dist() -> Path | None:
    """``$ALGOTRADE_WEB_DIST``: the built web app's directory the API serves; ``None`` when
    unset (the API serves no files)."""
    raw = credential(WEB_DIST)
    return Path(raw.strip()) if raw and raw.strip() else None


def auth_mode() -> str:
    """``$ALGOTRADE_AUTH`` lowercased (the API checks the value), else ``supabase``."""
    return (credential(AUTH) or DEFAULT_AUTH).strip().lower()


def supabase_url() -> str | None:
    """``$SUPABASE_URL`` without a trailing slash; ``None`` when unset."""
    url = credential(SUPABASE_URL)
    return url.strip().rstrip("/") if url else None


def supabase_jwt_secret() -> str | None:
    """``$SUPABASE_JWT_SECRET`` (the legacy HS256 signing secret); ``None`` when unset."""
    return credential(SUPABASE_JWT_SECRET)


def user_id(fallback: str) -> str:
    """``$ALGOTRADE_USER`` if set, else ``fallback`` (CLIs: ``local``; site screens: ``site``)."""
    return credential(USER) or fallback
