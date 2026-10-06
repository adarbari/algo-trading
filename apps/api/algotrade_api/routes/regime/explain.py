"""``POST /regime/explain``: the session's regime in plain words (the question "what is
happening?", or one card). A neither-or-both body or an UNKNOWN regime: 400; an unknown card:
404; more than 6 model calls a minute by one user: 429; the model off or not answering: 503."""

from fastapi import APIRouter

from algotrade.services.explaining.regime import explain_regime
from algotrade_api.deps import Caller, Context, ExplainCache, ExplainLimiter, TextModelDep
from algotrade_api.schemas.regime.explain import ExplainBody, RegimeExplanation

router = APIRouter(prefix="/regime", tags=["regime"])


@router.post("/explain")
def explain(
    ctx: Context,
    caller: Caller,
    model: TextModelDep,
    cache: ExplainCache,
    limiter: ExplainLimiter,
    body: ExplainBody,
) -> RegimeExplanation:
    result = explain_regime(ctx, model, cache, limiter, caller.user_id, body.question, body.card)
    return RegimeExplanation.model_validate({**vars(result.explanation), "cached": result.cached})
