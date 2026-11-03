"""``PUT`` / ``DELETE /admin/events/scope/{symbol}``: add or remove a name of the event-study scope
list (EV8; ADR 0050, ADR 0029 amendment 2026-11-03). Admin only (403 for a trader). One
``services.authoring`` write of ``config/admin/events/scope.toml``: the change is only recorded, the
next nightly's budgeted fill picks an added name up and a removal deletes no stored data. Both are
idempotent; an added symbol the session's reference snapshot does not know is a 400. The effective
list is read back by ``Query.eventScope``."""

import logging
from typing import Annotated

from fastapi import APIRouter, Query

from algotrade.config.site.users import Role
from algotrade.core.model.errors import PermissionDeniedError
from algotrade.services.authoring import event_scope
from algotrade_api.deps import Caller, Context, Writer
from algotrade_api.schemas.authoring.event_scope import ScopeChange, ScopeNameBody

router = APIRouter(prefix="/admin/events/scope", tags=["admin"])
log = logging.getLogger(__name__)


def _require_admin(caller: Caller) -> None:
    if caller.role is not Role.ADMIN:
        raise PermissionDeniedError("only an admin changes the event scope list")


@router.put("/{symbol}")
def add_name(
    writer: Writer, caller: Caller, ctx: Context, symbol: str, body: ScopeNameBody | None = None
) -> ScopeChange:
    _require_admin(caller)
    done = event_scope.add_scope_name(
        writer, ctx, caller.user_id, symbol, body.note if body else ""
    )
    log.info(
        "event-scope add symbol=%s changed=%s by=%s", done.symbol, done.changed, caller.user_id
    )
    return ScopeChange.model_validate(done)


@router.delete("/{symbol}")
def remove_name(
    writer: Writer,
    caller: Caller,
    symbol: str,
    note: Annotated[str, Query(description="why it is removed (optional)")] = "",
) -> ScopeChange:
    _require_admin(caller)
    done = event_scope.remove_scope_name(writer, caller.user_id, symbol, note)
    log.info(
        "event-scope remove symbol=%s changed=%s by=%s", done.symbol, done.changed, caller.user_id
    )
    return ScopeChange.model_validate(done)
