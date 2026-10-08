"""``PUT /evaluation/split``: save the user's own train / test split (their
``evaluation.toml``, never the site's). Reading it is GraphQL (``Query.evaluationSplit``); a run
under it is the owner's ``algotrade-backtest evaluate-edges`` and is labelled exploratory."""

from fastapi import APIRouter

from algotrade.services.authoring import evaluation
from algotrade_api.deps import Context, User, Writer
from algotrade_api.schemas.authoring.evaluation import EvaluationSplitBody, EvaluationSplitSaved

router = APIRouter(prefix="/evaluation", tags=["edges"])


@router.put("/split")
def save_split(
    writer: Writer, user: User, ctx: Context, body: EvaluationSplitBody
) -> EvaluationSplitSaved:
    saved = evaluation.save_split(writer, user, body.split_from, ctx.session.date)
    return EvaluationSplitSaved(split_from=saved.split_from)
