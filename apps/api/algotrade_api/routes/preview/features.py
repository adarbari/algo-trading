"""``POST /features/check``: type check a formula and sample it (an invalid one: 400 with
the position)."""

from fastapi import APIRouter

from algotrade.services.preview import expressions
from algotrade_api.deps import Caller, Reads, Users, acting_user
from algotrade_api.schemas.preview.features import CheckBody, ExpressionCheck

router = APIRouter(prefix="/features", tags=["features"])


@router.post("/check")
def check(ctx: Reads, caller: Caller, users: Users, body: CheckBody) -> ExpressionCheck:
    who = acting_user(caller, users, body.user)
    result = expressions.check_expression(ctx, body.expr, who, body.sample)
    return ExpressionCheck.model_validate(result)
