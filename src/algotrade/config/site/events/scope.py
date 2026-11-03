"""The event-sensitivity scope list (``config/site/events/scope.toml``, ADR 0050;
docs/event-sensitivity-plan.md section 6): the names the event study runs for on top of the
tier A / B short-put names. Each ``[[name]]`` is a listed ``symbol`` (as the vendors spell it),
the date it was ``added_on`` and an optional ``note``.

The loader checks shape, the symbol spelling and uniqueness. Symbols become instrument ids
through ``SymbolResolver`` on each run (ADR 0018), never here: the reference snapshot decides.

The admin's changes to the list are a second document, ``config/admin/events/scope.toml`` (scope
``admin``, git-ignored; ADR 0029 amendment 2026-11-03): each ``[[added]]`` / ``[[removed]]`` is a
``symbol`` with ``by`` (the admin's user id), ``at`` (a UTC instant) and an optional ``note``.
``load_admin_scope`` types it; ``effective_list`` layers it over the site list (the one place;
``services.events.scope`` and the admin write in ``services.authoring`` both call it: the use-case
packages may not import each other).
"""

import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Protocol

from algotrade.config.site.fields import Table, reject_secrets
from algotrade.core.model.errors import ConfigurationError

FOLDER = "events"
NAME = "scope"
ADMIN_SCOPE = "admin"  # the config scope of the admin's changes (``storage.configs.files.ADMIN``)
KEYS = ("symbol", "added_on", "note")
ADMIN_KEYS = ("symbol", "by", "at", "note")
SITE, ADMIN = "site", "admin"  # where a listed symbol comes from (``ListedName.source``)
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


@dataclass(frozen=True)
class AdminChange:
    """One ``[[added]]`` or ``[[removed]]``: the ticker, who changed the list, when (UTC) and why
    (optional)."""

    symbol: str
    by: str
    at: datetime
    note: str = ""


@dataclass(frozen=True)
class AdminScope:
    """``config/admin/events/scope.toml``: the symbols the admin added to the site list and the
    ones removed from it (no file: none of either). A symbol is in at most one of the two."""

    added: tuple[AdminChange, ...] = ()
    removed: tuple[AdminChange, ...] = ()

    @classmethod
    def from_document(cls, doc: Mapping[str, Any] | None) -> "AdminScope":
        where = f"{ADMIN_SCOPE}/{FOLDER}/{NAME}.toml"
        reject_secrets(doc or {}, where)
        root = Table(doc, where)
        root.only(("added", "removed"))
        added, removed = (_changes(root, key, where) for key in ("added", "removed"))
        both = sorted({c.symbol for c in added} & {c.symbol for c in removed})
        if both:
            raise ConfigurationError(f"{where}: symbols both added and removed: {both}")
        return cls(added, removed)

    def to_document(self) -> dict[str, Any]:
        """The TOML document of this state (what ``from_document`` reads back)."""
        out: dict[str, Any] = {}
        for key, changes in (("added", self.added), ("removed", self.removed)):
            if changes:
                out[key] = [
                    {
                        "symbol": c.symbol,
                        "by": c.by,
                        "at": c.at,
                        **({"note": c.note} if c.note else {}),
                    }
                    for c in changes
                ]
        return out


def load_admin_scope(configs: Documents) -> AdminScope:
    """``config/admin/events/scope.toml``; missing: no changes."""
    return AdminScope.from_document(configs.load(ADMIN_SCOPE, FOLDER, NAME))


def _changes(root: Table, key: str, where: str) -> tuple[AdminChange, ...]:
    raw = root.raw(key) or []
    if not isinstance(raw, list) or not all(isinstance(n, Mapping) for n in raw):
        raise ConfigurationError(f"{where} {key}: expected a list of tables ([[{key}]])")
    found = tuple(_change(Table(n, f"{where} [[{key}]][{i}]")) for i, n in enumerate(raw))
    repeated = sorted(s for s, n in Counter(c.symbol for c in found).items() if n > 1)
    if repeated:
        raise ConfigurationError(f"{where} {key}: symbols declared more than once: {repeated}")
    return found


def _change(t: Table) -> AdminChange:
    t.only(ADMIN_KEYS)
    at = t.raw("at")
    if not isinstance(at, datetime) or at.tzinfo is None:
        raise ConfigurationError(f"{t.where} at: expected a UTC instant, got {at!r}")
    by = t.text("by", "").strip()
    if not by:
        raise ConfigurationError(f"{t.where} by: required (the admin's user id)")
    return AdminChange(_symbol(t), by, at.astimezone(UTC), " ".join(t.text("note", "").split()))


def load_event_scope(configs: Documents) -> EventScope:
    """``config/site/events/scope.toml``; missing: an empty scope."""
    return EventScope.from_document(configs.load("site", FOLDER, NAME))


@dataclass(frozen=True)
class ListedName:
    """A symbol of the effective list: ``source`` ``site`` (the PR-reviewed file) or ``admin``
    (added by ``by`` at ``at``; for a site name ``by`` / ``at`` are None), ``added_on`` the
    site file's date (admin: the day of the change), ``note`` why."""

    symbol: str
    source: str
    added_on: date
    note: str
    by: str | None = None
    at: datetime | None = None


@dataclass(frozen=True)
class EffectiveList:
    """The list the ``list`` reason reads: ``names`` (the site's in file order, then the admin's
    additions) and ``removed``, the site symbols the admin took off it (still in the file)."""

    names: tuple[ListedName, ...]
    removed: tuple[AdminChange, ...]

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(n.symbol for n in self.names)


def effective_list(configs: Documents) -> EffectiveList:
    """The site names minus the admin's removals, then the admin's additions the site does not
    already list (the one place the two documents are layered)."""
    site = load_event_scope(configs).names
    admin = load_admin_scope(configs)
    gone = {c.symbol for c in admin.removed}
    names = [ListedName(n.symbol, SITE, n.added_on, n.note) for n in site if n.symbol not in gone]
    listed = {n.symbol for n in site}
    names += [
        ListedName(c.symbol, ADMIN, c.at.date(), c.note, c.by, c.at)
        for c in admin.added
        if c.symbol not in listed
    ]
    removed = tuple(c for c in admin.removed if c.symbol in listed)
    return EffectiveList(tuple(names), removed)


def valid_symbol(symbol: str) -> bool:
    """A listed ticker spelling (``AAPL``, ``BRK.B``), never a FIGI or an ``EQ:`` id."""
    return _SYMBOL.match(symbol) is not None


def _symbol(t: Table) -> str:
    if t.raw("symbol") is None:
        raise ConfigurationError(f"{t.where} symbol: required")
    symbol = t.text("symbol", "").strip()
    if not valid_symbol(symbol):
        raise ConfigurationError(
            f"{t.where} symbol: expected a listed ticker in upper case (AAPL, BRK.B), "
            f"got {symbol!r}"
        )
    return symbol


def _name(t: Table) -> ScopeName:
    t.only(KEYS)
    symbol = _symbol(t)
    added_on = t.raw("added_on")
    if not isinstance(added_on, date) or isinstance(added_on, datetime):
        raise ConfigurationError(
            f"{t.where} added_on: expected a date (YYYY-MM-DD), got {added_on!r}"
        )
    return ScopeName(symbol=symbol, added_on=added_on, note=" ".join(t.text("note", "").split()))
