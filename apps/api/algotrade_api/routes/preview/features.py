"""``POST /features/check``: type check a formula and sample it (an invalid one: 400 with
the position)."""

from fastapi import APIRouter

from algotrade.services.explore.preview import expressions
from algotrade_api.deps import Store
from algotrade_api.schemas.preview.features import CheckBody, ExpressionCheck

router = APIRouter(prefix="/features", tags=["features"])


@router.post("/check")
def check(store: Store, body: CheckBody) -> ExpressionCheck:
    result = expressions.check_expression(store, body.expr, body.user, body.sample)
    return ExpressionCheck.model_validate(result)
