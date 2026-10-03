"""Typed reads of one TOML table for ``config/settings.py``: defaults, types, ranges, and an
error that names the file, section and key (``sources.toml [http] max_retry_s: ...``)."""

from collections.abc import Iterable, Mapping
from typing import Any, overload

from algotrade.core.errors import ConfigurationError


class Table:
    """A TOML table (``None``: missing, so every read returns its default) and where it is."""

    def __init__(self, doc: Mapping[str, Any] | None, where: str) -> None:
        self._doc: Mapping[str, Any] = doc or {}
        self.where = where

    def names(self) -> list[str]:
        return list(self._doc)

    def raw(self, key: str) -> Any:
        return self._doc.get(key)

    def only(self, allowed: Iterable[str]) -> None:
        unknown = sorted(set(self._doc) - set(allowed))
        if unknown:
            raise ConfigurationError(f"{self.where}: unknown keys {unknown}")

    def _fail(self, key: str, expected: str) -> ConfigurationError:
        return ConfigurationError(
            f"{self.where} {key}: expected {expected}, got {self._doc[key]!r}"
        )

    def table(self, key: str, allowed: Iterable[str]) -> "Table":
        """A sub-table (``[section]``); missing -> empty. Unknown keys inside it fail."""
        value = self._doc.get(key)
        if value is not None and not isinstance(value, Mapping):
            raise self._fail(key, "a table")
        inner = self.where.removesuffix("]")
        sub = Table(value, f"{inner}.{key}]" if inner != self.where else f"{self.where} [{key}]")
        sub.only(allowed)
        return sub

    @overload
    def number(self, key: str, default: float, minimum: float | None = None) -> float: ...

    @overload
    def number(self, key: str, default: None, minimum: float | None = None) -> float | None: ...

    def number(self, key: str, default: float | None, minimum: float | None = None) -> float | None:
        if key not in self._doc:
            return default
        value = self._doc[key]
        bound = "" if minimum is None else f" >= {minimum:g}"
        if not _is_number(value) or (minimum is not None and value < minimum):
            raise self._fail(key, f"a number{bound}")
        return float(value)

    def fraction(self, key: str, default: float) -> float:
        value = self.number(key, default, 0)
        if value > 1:
            raise self._fail(key, "a fraction between 0 and 1")
        return value

    def integer(self, key: str, default: int, minimum: int | None = None) -> int:
        if key not in self._doc:
            return default
        value = self._doc[key]
        bound = "" if minimum is None else f" >= {minimum}"
        if not _is_int(value) or (minimum is not None and value < minimum):
            raise self._fail(key, f"an integer{bound}")
        return int(value)

    def integers(self, key: str, default: tuple[int, ...], length: int) -> tuple[int, ...]:
        if key not in self._doc:
            return default
        value = self._doc[key]
        if not isinstance(value, list) or len(value) != length or not all(map(_is_int, value)):
            raise self._fail(key, f"a list of {length} integers")
        return tuple(int(v) for v in value)

    def boolean(self, key: str, default: bool) -> bool:
        if key not in self._doc:
            return default
        if not isinstance(self._doc[key], bool):
            raise self._fail(key, "true or false")
        return bool(self._doc[key])

    def text(self, key: str, default: str) -> str:
        if key not in self._doc:
            return default
        if not isinstance(self._doc[key], str) or not self._doc[key]:
            raise self._fail(key, "a non-empty string")
        return str(self._doc[key])

    def choice(self, key: str, default: str, choices: Iterable[str]) -> str:
        options = tuple(choices)
        value = self.text(key, default)
        if value not in options:
            raise self._fail(key, f"one of {list(options)}")
        return value

    def strings(self, key: str, default: tuple[str, ...]) -> tuple[str, ...]:
        if key not in self._doc:
            return default
        value = self._doc[key]
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise self._fail(key, "a list of strings")
        return tuple(value)


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
