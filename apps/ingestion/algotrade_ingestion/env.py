"""Local ``.env`` loading and vendor credentials (they only ever come from the environment).

The source registry names the variable each source needs (``sources/registry.py``) and reads
it through ``credential``; a missing one leaves the source out, with the reason reported.
"""

import os

from algotrade.storage.dotenv import load_dotenv

__all__ = ["credential", "load_dotenv"]


def credential(name: str) -> str | None:
    """The variable's value; ``None`` when unset or empty. Never logged or stored."""
    return os.environ.get(name) or None
