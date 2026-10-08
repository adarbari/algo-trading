"""The shape checks every Guide source shares (ADR 0051): a required one-line string (its
whitespace collapsed), a non-empty list of such strings, a list of tables (``[[key]]``) and a
value listed only once; each failure names the file, the table and the key."""

from collections import Counter
from collections.abc import Iterable, Mapping

from algotrade.config.site.fields import Table
from algotrade.core.model.errors import ConfigurationError


def line(t: Table, key: str) -> str:
    """``key`` with its whitespace collapsed; required and non-empty."""
    value = " ".join(t.text(key, "").split())
    if not value:
        raise ConfigurationError(f"{t.where} {key}: expected a non-empty string")
    return value


def lines(t: Table, key: str, required: bool = True) -> tuple[str, ...]:
    """``key``'s strings, each collapsed; ``required``: at least one."""
    values = tuple(" ".join(v.split()) for v in t.strings(key, ()))
    if (required and not values) or not all(values):
        raise ConfigurationError(f"{t.where} {key}: expected one or more non-empty strings")
    return values


def tables(root: Table, key: str) -> list[Table]:
    """``[[key]]``: a list of tables (missing: none), each named by its position."""
    raw = root.raw(key) or []
    if not isinstance(raw, list) or not all(isinstance(e, Mapping) for e in raw):
        raise ConfigurationError(f"{root.where} {key}: expected a list of tables ([[{key}]])")
    return [Table(e, f"{root.where} [[{key}]][{i}]") for i, e in enumerate(raw)]


def once(where: str, what: str, values: Iterable[str]) -> None:
    """Fails naming every value of ``values`` listed more than once."""
    repeated = sorted(k for k, n in Counter(values).items() if n > 1)
    if repeated:
        raise ConfigurationError(f"{where}: {what} listed more than once: {repeated}")
