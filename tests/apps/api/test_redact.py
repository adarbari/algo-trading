"""``redact`` (ADR 0056): the fields that declare ``ADMIN_CAUSE`` are replaced for anyone but an
admin, wherever they are nested; ``public_audit`` drops the table keys of an audit."""

from typing import Any

from pydantic import BaseModel, Field

from algotrade.config.site.users import Role
from algotrade.services.read.availability.cause import (
    ADMIN_CAUSE,
    AUDIT,
    GENERIC,
    GENERIC_REASONS,
    UnavailableKind,
    public_audit,
)
from algotrade.services.read.context import open_context
from algotrade_api.redact import redact, unavailable_for
from algotrade_api.schemas.availability import Unavailable
from tests.helpers.api_store import END

SYSTEM = GENERIC_REASONS[UnavailableKind.SYSTEM]


class Inner(BaseModel):
    note: str | None = Field(None, json_schema_extra={ADMIN_CAUSE: GENERIC})
    kept: str = "public"


class Outer(BaseModel):
    tables: list[str] = Field(default_factory=list, json_schema_extra={ADMIN_CAUSE: []})
    audit: dict[str, Any] = Field(default_factory=dict, json_schema_extra={ADMIN_CAUSE: AUDIT})
    inner: list[Inner] = Field(default_factory=list)


def _outer() -> Outer:
    audit = {
        "rules": 3,
        "missing_tables": ["rollups/x@v1"],
        "deep": {"missing_optional_tables": []},
    }
    return Outer(tables=["rollups/x@v1"], audit=audit, inner=[Inner(note="boom: rollups/x@v1")])


def test_an_admin_reads_everything() -> None:
    found = _outer()
    assert redact(found, Role.ADMIN) is found


def test_anyone_else_reads_the_fallbacks_wherever_they_are_nested() -> None:
    shown = redact(_outer(), Role.TRADER)
    assert shown.tables == []
    assert shown.audit == {"rules": 3, "deep": {}}
    assert shown.inner[0].note == SYSTEM and shown.inner[0].kept == "public"
    assert redact(Inner(note=None), Role.TRADER).note is None  # nothing to hide


def test_public_audit_drops_the_table_keys_at_any_depth_and_keeps_the_rest() -> None:
    audit = {"a": [{"missing_tables": ["t"], "b": 1}], "missing_optional_tables": ["u"]}
    assert public_audit(audit) == {"a": [{"b": 1}]}


def test_unavailable_for_explains_only_for_an_admin(
    api_golden: tuple[Any, dict[str, str]],
) -> None:
    store = api_golden[0]
    ctx = open_context(store.reader, store.configs, store.user)
    table = "rollups/instrument/ibkr_iv@v1"
    [admin] = unavailable_for(ctx, [table], END, Role.ADMIN)
    [trader] = unavailable_for(ctx, [table], END, Role.TRADER)
    assert [link.level for link in admin.cause or []][:2] == ["SOURCE", "STEP"]
    assert redact(admin, Role.TRADER).cause is None and trader.cause == []
    assert isinstance(admin, Unavailable) and admin.guide_term == "unavailable_system"
