"""A config document as TOML text (``toml_text``): the one serialiser of the config store, used by
the writer (``writer.py``) and by the read model's published edge document. Fails closed: a
value TOML cannot hold, a document over ``MAX_DOCUMENT_BYTES`` or one that does not read back
identical is a ``ConfigurationError``, never a file with something else in it."""

import json
import math
import re
import tomllib
from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

from algotrade.core.model.errors import ConfigurationError

MAX_DOCUMENT_BYTES = 64 * 1024  # a config is a few KiB; refuse anything far larger


_BARE_KEY = re.compile(r"[A-Za-z0-9_-]+")


def _key(key: Any) -> str:
    if not isinstance(key, str):
        raise ConfigurationError(f"config keys are strings, not {key!r}")
    return key if _BARE_KEY.fullmatch(key) else json.dumps(key)


def _float(value: float) -> str:
    if math.isnan(value):
        return "nan"
    if math.isinf(value):
        return "inf" if value > 0 else "-inf"
    return repr(value)


def _scalar(value: Any) -> str | None:
    """TOML text of a scalar; ``None`` when ``value`` is not one."""
    text: str | None = None
    if isinstance(value, bool):
        text = "true" if value else "false"
    elif isinstance(value, int):
        text = str(value)
    elif isinstance(value, float):
        text = _float(value)
    elif isinstance(value, str):
        text = json.dumps(value)  # a JSON string is a valid TOML basic string
    elif isinstance(value, (datetime, date)):
        text = value.isoformat()
    return text


def _value(value: Any, path: str) -> str:
    scalar = _scalar(value)
    if scalar is not None:
        return scalar
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_value(v, f"{path}[]") for v in value) + "]"
    if isinstance(value, Mapping):
        items = (f"{_key(k)} = {_value(v, f'{path}.{k}')}" for k, v in value.items())
        return "{ " + ", ".join(items) + " }" if value else "{}"
    raise ConfigurationError(f"{path}: {type(value).__name__} is not a config value")


def _table(document: Mapping[str, Any], prefix: str, out: list[str]) -> None:
    scalars = [(k, v) for k, v in document.items() if not isinstance(v, Mapping)]
    tables = [(k, v) for k, v in document.items() if isinstance(v, Mapping)]
    if prefix and (scalars or not tables):
        out.append(f"[{prefix}]")
    for key, value in scalars:
        if value is None:
            raise ConfigurationError(f"{prefix or 'document'}.{key}: TOML has no null")
        out.append(f"{_key(key)} = {_value(value, f'{prefix}.{key}')}")
    if scalars:
        out.append("")
    for key, value in tables:
        _table(value, f"{prefix}.{_key(key)}" if prefix else _key(key), out)


def toml_text(document: Mapping[str, Any]) -> str:
    """``document`` as TOML; fails closed unless it reads back identical (and is small)."""
    out: list[str] = []
    _table(document, "", out)
    text = "\n".join(out).rstrip("\n") + "\n"
    if len(text.encode()) > MAX_DOCUMENT_BYTES:
        raise ConfigurationError(f"config document larger than {MAX_DOCUMENT_BYTES} bytes")
    if _normalised(tomllib.loads(text)) != _normalised(document):
        raise ConfigurationError("config document does not round-trip through TOML")
    return text


def _normalised(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {k: _normalised(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalised(v) for v in value]
    if isinstance(value, float) and math.isnan(value):
        return "nan"
    return value
