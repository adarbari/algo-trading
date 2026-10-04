"""Safe identifiers. User, config and selection ids end up in file paths and URLs."""

import re

from algotrade.core.model.errors import ConfigurationError

_ID = re.compile(r"^[a-z0-9_-]{1,64}$")


def validate_id(kind: str, value: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ConfigurationError(f"invalid {kind} id {value!r}: use 1-64 of [a-z0-9_-]")
    return value
