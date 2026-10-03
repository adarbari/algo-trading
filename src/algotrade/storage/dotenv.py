"""Load a local ``.env`` file so every app sees the same settings (e.g. ALGOTRADE_DATA_URL)."""

import os
from pathlib import Path


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
