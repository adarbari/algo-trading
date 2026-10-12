"""``redraft_part``: re-draft one part of a Describe-it draft (ADR 0041, amended 2026-10-12). The
request is already checked (``request.check_request``); the model is asked about the new words
alone with the scoped prompt (``prompt``; the call is tagged ``cap.USE_CASE`` with the draft's
``PROMPT_VERSION``, so the usage log, the cost and the budget count it as they count a draft) and
the answer is merged into the draft the browser holds (``merge``): the new part's items replace
the old part's, every other part stays. The result is the whole merged draft, the id of the part
replaced and the part's own missing-feature requests (what the request log records: the other
parts' were recorded when they were asked). Reads the catalogue, the configs and, for the dry run
of a formula, the session; writes nothing."""

from collections.abc import Callable
from dataclasses import dataclass

from algotrade.config.site.drafting.backlog import open_keys
from algotrade.config.site.settings import (
    load_feature_backlog,
    load_field_guide,
    load_phrasebook,
)
from algotrade.core.model.completion import CallTag
from algotrade.services.drafting.gaps import MissingFeature
from algotrade.services.drafting.prompt import PROMPT_VERSION
from algotrade.services.drafting.redraft.cap import USE_CASE
from algotrade.services.drafting.redraft.merge import merge_part
from algotrade.services.drafting.redraft.prompt import scoped_prompts
from algotrade.services.drafting.redraft.request import PartRequest
from algotrade.services.drafting.screens import ScreenDraft, draft_words
from algotrade.services.read.context import ReadContext
from algotrade.services.read.instruments.catalogue import feature_infos
from algotrade.services.text_model.model import TextModel


@dataclass(frozen=True)
class Redrafted:
    """A part re-drafted: the whole merged ``draft`` (its ``sentence`` has the new words in
    place), the id of the part it replaced, the words before and after, and the missing-feature
    requests of the new words."""

    draft: ScreenDraft
    replaced_part_id: str
    old_words: str
    new_words: str
    missing: tuple[MissingFeature, ...]


def redraft_part(
    ctx: ReadContext,
    model: TextModel,
    req: PartRequest,
    asked: Callable[[str | None], None] = lambda _: None,
) -> Redrafted:
    """``req.part`` re-drafted as ``req.new_words`` for ``ctx``'s user, merged into
    ``req.prior``. ``asked`` is told the call's id as soon as the model has answered (the daily
    cap counts a call whose merge then fails); ``ModelUnavailableError`` when it cannot answer,
    ``ConfigurationError`` for an answer or a document the merge cannot use."""
    infos = feature_infos(ctx.features)
    phrasebook = load_phrasebook(ctx.configs).phrases
    guide = load_field_guide(ctx.configs)
    backlog = load_feature_backlog(ctx.configs)
    others = {cid: c for cid, c in req.criteria.items() if cid not in req.part.criteria}
    system, user = scoped_prompts(
        infos.values(), req.screener_id, req.new_words, others, phrasebook, guide,
        open_keys(backlog, limit=len(backlog.items)),
    )  # fmt: skip
    tag = CallTag(USE_CASE, ctx.user.user_id, PROMPT_VERSION)
    sub = draft_words(
        ctx, model, req.screener_id, req.new_words, system, user, tag, infos, phrasebook
    )
    asked(sub.call_id)
    merged = merge_part(ctx, req, sub)
    return Redrafted(merged, req.part.id, req.old_words, req.new_words, sub.missing)
