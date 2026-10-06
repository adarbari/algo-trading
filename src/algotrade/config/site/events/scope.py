"""The event-sensitivity scope list (``config/site/events/scope.toml``, ADR 0050;
docs/event-sensitivity-plan.md section 6): the names the event study runs for on top of the
tier A / B short-put names. Each ``[[name]]`` is a listed ``symbol`` (as the vendors spell it),
the date it was ``added_on`` and an optional ``note``.

The loader checks shape, the symbol spelling and uniqueness. Symbols become instrument ids
through ``SymbolResolver`` on each run (ADR 0018), never here: the reference snapshot decides.
"""

import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol

from algotrade.config.site.fields import Table, reject_secrets
from algotrade.core.model.errors import ConfigurationError

FOLDER = "events"
NAME = "scope"
KEYS = ("symbol", "added_on", "note")
_SYMBOL = re.compile(r"^[A-Z][A-Z0-9]{0,5}(\.[A-Z])?$")  # BRK.B; never a FIGI or an EQ: id


class Documents(Protocol):
    """What the loader needs from a config store (``ConfigStore``)."""

    def load(self, scope: str, kind: str, name: str) -> Mapping[str, Any] | None: ...


@dataclass(frozen=True)
class ScopeName:
    """One ``[[name]]``: the ticker, when it joined the list and why (optional)."""

    symbol: str
    added_on: date
    note: str = ""


@dataclass(frozen=True)
class EventScope:
    """``scope.toml``: the names in file order (none without the file)."""

    names: tuple[ScopeName, ...] = ()

    @classmethod
    def from_document(cls, doc: Mapping[str, Any] | None) -> "EventScope":
        where = f"{FOLDER}/{NAME}.toml"
        reject_secrets(doc or {}, where)
        root = Table(doc, where)
        root.only(("name",))
        raw = root.raw("name") or []
        if not isinstance(raw, list) or not all(isinstance(n, Mapping) for n in raw):
            raise ConfigurationError(f"{where} name: expected a list of tables ([[name]])")
        found = tuple(_name(Table(n, f"{where} [[name]][{i}]")) for i, n in enumerate(raw))
        repeated = sorted(s for s, n in Counter(n.symbol for n in found).items() if n > 1)
        if repeated:
            raise ConfigurationError(f"{where}: symbols declared more than once: {repeated}")
        return cls(found)

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(n.symbol for n in self.names)


def load_event_scope(configs: Documents) -> EventScope:
    """``config/site/events/scope.toml``; missing: an empty scope."""
    return EventScope.from_document(configs.load("site", FOLDER, NAME))


def _name(t: Table) -> ScopeName:
    t.only(KEYS)
    if t.raw("symbol") is None:
        raise ConfigurationError(f"{t.where} symbol: required")
    symbol = t.text("symbol", "").strip()
    if not _SYMBOL.match(symbol):
        raise ConfigurationError(
            f"{t.where} symbol: expected a listed ticker in upper case (AAPL, BRK.B), "
            f"got {symbol!r}"
        )
    added_on = t.raw("added_on")
    if not isinstance(added_on, date) or isinstance(added_on, datetime):
        raise ConfigurationError(
            f"{t.where} added_on: expected a date (YYYY-MM-DD), got {added_on!r}"
        )
    return ScopeName(symbol=symbol, added_on=added_on, note=" ".join(t.text("note", "").split()))
