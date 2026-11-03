"""``POST /users``: onboard a trader (ID5; ADR 0040, decision log 2026-11-02). Admin only (403
for a trader). One ``services.authoring`` write of the user's ``identity.toml``; the route then
swaps the app's registry for the reloaded one, so the new email signs in at once with no restart.
The identity provider is not called: the response says the one step left to do there."""

import logging

from fastapi import APIRouter, Request

from algotrade.config.site.users import Role, UsersSettings
from algotrade.core.model.errors import PermissionDeniedError
from algotrade.services.authoring import onboarding
from algotrade_api.deps import Caller, Writer
from algotrade_api.schemas.authoring.users import OnboardBody, Onboarded, ProviderStep

router = APIRouter(prefix="/users", tags=["users"])
log = logging.getLogger(__name__)


@router.post("")
def onboard(request: Request, writer: Writer, caller: Caller, body: OnboardBody) -> Onboarded:
    if caller.role is not Role.ADMIN:
        raise PermissionDeniedError("only an admin onboards a user")

    def swap(users: UsersSettings) -> None:
        request.app.state.users = users

    done = onboarding.onboard_user(
        writer, caller.user_id, body.user_id, body.email, body.name, publish=swap
    )
    log.info("onboard user=%s role=%s by=%s", done.user_id, done.role, caller.user_id)
    return Onboarded(
        user_id=done.user_id,
        role=done.role,
        pending_provider=done.pending_provider,
        provider_step=ProviderStep(
            email=done.provider_step.email, instruction=done.provider_step.instruction
        ),
    )
