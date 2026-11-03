"""Change the event-study scope list as an admin (EV8; ADR 0050, ADR 0029 amendment 2026-11-03,
decision log 2026-11-03 "How an admin changes the event-study scope list").

The site list ``config/site/events/scope.toml`` changes only by PR; the admin's changes are the
document ``config/admin/events/scope.toml`` (scope ``admin``, git-ignored): an ``[[added]]`` or
``[[removed]]`` entry per symbol with who (``by``) and when (``at``, UTC). ``effective_list``
(``config.site.events.scope``) layers it over the site list. Nothing else happens here: a change
is recorded, no data is fetched or deleted, and the next nightly's budgeted fill picks an added
name up; a removal drops only the ``list`` reason (a name still in a put tier stays in scope).

``add_scope_name`` / ``remove_scope_name`` are idempotent (``ScopeChange.changed`` False when the
list already was as asked) and admin only (``PermissionDeniedError``). An added symbol must be
spelled as the site file's loader does and be known to ``SymbolResolver`` of the session's
reference snapshot (ADR 0018), else ``ConfigurationError`` names why; a removal needs only the
spelling (a delisted name must still be removable). The read-modify-write of the one document runs
under a lock, so two admins never lose each other's change."""

import threading
from dataclasses import dataclass
from datetime import UTC, datetime

from algotrade.config.site.events.scope import (
    AdminChange,
    AdminScope,
    effective_list,
    load_admin_scope,
    load_event_scope,
    valid_symbol,
)
from algotrade.config.site.settings import load_users
from algotrade.config.site.users import Role
from algotrade.core.model.errors import ConfigurationError, PermissionDeniedError
from algotrade.data.reference import resolver
from algotrade.services.authoring.scope import ConfigWriter
from algotrade.services.read.context import ReadContext

FOLDER, NAME = "events", "scope"
MAX_NOTE = 200
_LOCK = threading.Lock()


@dataclass(frozen=True)
class ScopeChange:
    """What a write did: ``listed`` the symbol is on the effective list now, ``changed`` the
    document was written (False: it already was as asked)."""

    symbol: str
    listed: bool
    changed: bool


def _admin(writer: ConfigWriter, user_id: str) -> None:
    caller = load_users(writer).get(user_id)
    if caller is None or caller.role is not Role.ADMIN:
        raise PermissionDeniedError("only an admin changes the event scope list")


def _symbol(value: str) -> str:
    symbol = value.strip().upper()
    if not valid_symbol(symbol):
        raise ConfigurationError(
            f"symbol: expected a listed ticker (AAPL, BRK.B), got {value.strip()!r}"
        )
    return symbol


def _note(value: str) -> str:
    note = " ".join(value.split())
    if len(note) > MAX_NOTE or not note.isprintable():
        raise ConfigurationError(f"note: at most {MAX_NOTE} printable characters")
    return note


def _save(writer: ConfigWriter, scope: AdminScope) -> None:
    writer.save_admin_document(FOLDER, NAME, scope.to_document())


def _without(changes: tuple[AdminChange, ...], symbol: str) -> tuple[AdminChange, ...]:
    return tuple(c for c in changes if c.symbol != symbol)


def add_scope_name(
    writer: ConfigWriter, ctx: ReadContext, admin: str, symbol: str, note: str = ""
) -> ScopeChange:
    """Put ``symbol`` on the effective list: a site name the admin removed is restored (its
    removal dropped), any other becomes an ``[[added]]`` entry by ``admin`` now."""
    wanted, why = _symbol(symbol), _note(note)
    _admin(writer, admin)
    if not resolver(ctx.reader, ctx.session.date).knows(wanted):
        raise ConfigurationError(
            f"symbol: {wanted} is not in the reference snapshot the session "
            f"{ctx.session.date.isoformat()} sees: nothing to resolve it to"
        )
    with _LOCK:
        if wanted in effective_list(writer).symbols:
            return ScopeChange(wanted, True, False)
        current = load_admin_scope(writer)
        if wanted in load_event_scope(writer).symbols:  # on the site list: undo the removal
            changed = AdminScope(current.added, _without(current.removed, wanted))
        else:
            entry = AdminChange(wanted, admin, datetime.now(UTC).replace(microsecond=0), why)
            changed = AdminScope((*_without(current.added, wanted), entry), current.removed)
        _save(writer, changed)
    return ScopeChange(wanted, True, True)


def remove_scope_name(writer: ConfigWriter, admin: str, symbol: str, note: str = "") -> ScopeChange:
    """Take ``symbol`` off the effective list: an admin addition is dropped, a site name becomes
    a ``[[removed]]`` entry by ``admin`` now (the site file is untouched)."""
    wanted, why = _symbol(symbol), _note(note)
    _admin(writer, admin)
    with _LOCK:
        if wanted not in effective_list(writer).symbols:
            return ScopeChange(wanted, False, False)
        current = load_admin_scope(writer)
        removed = current.removed
        if wanted in load_event_scope(writer).symbols:
            entry = AdminChange(wanted, admin, datetime.now(UTC).replace(microsecond=0), why)
            removed = (*removed, entry)
        _save(writer, AdminScope(_without(current.added, wanted), removed))
    return ScopeChange(wanted, False, True)
