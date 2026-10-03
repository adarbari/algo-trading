"""Local ``.env`` loading and vendor credentials (they only ever come from the environment)."""

import os
from pathlib import Path

from algotrade.core.errors import ConfigurationError

MASSIVE_KEY = "ALGOTRADE_MASSIVE_API_KEY"
SEC_CONTACT = "ALGOTRADE_SEC_CONTACT"


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


def massive_key(required: bool = True) -> str | None:
    key = os.environ.get(MASSIVE_KEY) or None
    if key is None and required:
        raise ConfigurationError(
            f"{MASSIVE_KEY} is not set: create a free Massive account and add the key to .env"
        )
    return key


def sec_contact(required: bool = True) -> str | None:
    """Contact email for the SEC's required User-Agent. Never logged or stored."""
    contact = os.environ.get(SEC_CONTACT) or None
    if contact is None and required:
        raise ConfigurationError(
            f"{SEC_CONTACT} is not set: SEC EDGAR requires a contact email; add it to .env"
        )
    return contact
