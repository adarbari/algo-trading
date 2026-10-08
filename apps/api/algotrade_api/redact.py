"""``redact``: the one place a REST response is made role-scoped (ADR 0056).

A field that carries why a fact is not available (a table list, an error text, a cause chain)
declares it with ``ADMIN_CAUSE`` in its schema (pydantic ``json_schema_extra``) or dataclass
``metadata``; the value of the key is what anyone but an admin gets instead (``None``, ``[]``
or ``GENERIC``: the generic words; ``AUDIT``: a stored audit without its table keys). A route
returns ``redact(model, caller.role)``; the server withholds the cause, the browser never
filters it. ``unavailable_for`` builds the public ``Unavailable`` list of a set of tables, with
the cause chain expanded for an admin only."""

from collections.abc import Iterable, Mapping
from dataclasses import fields, is_dataclass, replace
from datetime import date
from typing import Any

from pydantic import BaseModel

from algotrade.config.site.users import Role
from algotrade.services.read.availability.cause import (
    ADMIN_CAUSE,
    AUDIT,
    GENERIC,
    GENERIC_REASONS,
    Cause,
    Unavailable,
    UnavailableKind,
    public_audit,
)
from algotrade.services.read.availability.explain import explain
from algotrade.services.read.availability.unavailable import unavailable_tables
from algotrade.services.read.context import Stores
from algotrade_api.schemas.availability import Unavailable as UnavailableOut
from algotrade_api.schemas.availability import unavailable_of

__all__ = ["redact", "unavailable_for"]


def _instead(fallback: Any, value: Any) -> Any:
    """What anyone but an admin gets in place of ``value``."""
    if fallback == AUDIT:
        return public_audit(value)
    if fallback == GENERIC:
        return None if value is None else GENERIC_REASONS[UnavailableKind.SYSTEM]
    return fallback


def _scrub(value: Any) -> Any:
    """``value`` with every cause field under it replaced (models, dataclasses, lists)."""
    if isinstance(value, BaseModel):
        marks: Mapping[str, Any] = {
            name: extra[ADMIN_CAUSE]
            for name, f in type(value).model_fields.items()
            if isinstance(extra := f.json_schema_extra, dict) and ADMIN_CAUSE in extra
        }
        changes = {
            name: _instead(marks[name], getattr(value, name))
            if name in marks
            else _scrub(getattr(value, name))
            for name in type(value).model_fields
        }
        return value.model_copy(update=changes)
    if is_dataclass(value) and not isinstance(value, type):
        updates = {
            f.name: _instead(f.metadata[ADMIN_CAUSE], getattr(value, f.name))
            if ADMIN_CAUSE in f.metadata
            else _scrub(getattr(value, f.name))
            for f in fields(value)
        }
        return replace(value, **updates)
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    return value


def redact[T](model: T, role: Role) -> T:
    """``model`` as ``role`` may read it: unchanged for an admin; for anyone else every field
    that declares ``ADMIN_CAUSE`` is replaced by its fallback, wherever it is nested."""
    return model if role is Role.ADMIN else _scrub(model)


def unavailable_for(
    ctx: Stores, tables: Iterable[str], session: date, role: Role
) -> list[UnavailableOut]:
    """The ``Unavailable`` of each table with nothing for ``session``; an admin's carry the
    chain ``explain`` finds, anyone else's are stripped by ``redact`` and never explained."""
    out: list[UnavailableOut] = []
    for found in unavailable_tables(tables, session):
        cause = explain(ctx, found.cause) if role is Role.ADMIN else Cause(())
        out.append(unavailable_of(Unavailable(found.kind, found.features, cause)))
    return out
