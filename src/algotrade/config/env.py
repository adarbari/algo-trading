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

__all__ = ["api_credential", "config_dir", "credential", "data_url", "load_dotenv", "user_id"]


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


def user_id(fallback: str) -> str:
    """``$ALGOTRADE_USER`` if set, else ``fallback`` (CLIs: ``local``; site screens: ``site``)."""
    return credential(USER) or fallback
