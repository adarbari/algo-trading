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

__all__ = ["config_dir", "credential", "data_url", "load_dotenv", "user_id"]


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


def data_url(explicit: str | None = None) -> str:
    """The storage URL: ``explicit`` (a CLI flag), else ``$ALGOTRADE_DATA_URL``, else ./var/data."""
    return explicit or credential(DATA_URL) or DEFAULT_DATA_URL


def config_dir(explicit: str | Path | None = None) -> Path:
    """The config root: ``explicit``, else ``$ALGOTRADE_CONFIG_DIR``, else ./config."""
    return Path(explicit or credential(CONFIG_DIR) or DEFAULT_CONFIG_DIR)


def user_id(fallback: str) -> str:
    """``$ALGOTRADE_USER`` if set, else ``fallback`` (CLIs: ``local``; site screens: ``site``)."""
    return credential(USER) or fallback
