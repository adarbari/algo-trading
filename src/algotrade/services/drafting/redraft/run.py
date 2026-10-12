"""``redraft_part``: re-draft one part of a Describe-it draft (ADR 0041, amended 2026-10-12). The
request is already checked (``request.check_request``); the model is asked about the new words
alone with the scoped prompt (``prompt``; the call is tagged ``cap.USE_CASE`` with the draft's
``PROMPT_VERSION``, so the usage log, the cost and the budget count it as they count a draft) and
the answer is merged into the draft the browser holds (``merge``): the new part's items replace
the old part's, every other part stays. The result is the whole merged draft, the id of the part
replaced and the part's own missing-feature requests (what the request log records: the other
parts' were recorded when they were asked). Reads the catalogue, the configs and, for the dry run
of a formula, the session; writes nothing."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from algotrade.config.site.drafting.backlog import open_keys
from algotrade.config.site.settings import (
    load_feature_backlog,
    load_field_guide,
    load_phrasebook,
)
from algotrade.core.model.completion import CallTag
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.drafting.contract.gaps import MissingFeature
from algotrade.services.drafting.prompt import PROMPT_VERSION
from algotrade.services.drafting.redraft.cap import USE_CASE
from algotrade.services.drafting.redraft.merge import merge_part
from algotrade.services.drafting.redraft.prompt import scoped_prompts
from algotrade.services.drafting.redraft.request import PartRequest, missing_ref
from algotrade.services.drafting.screens import ScreenDraft, draft_words, validated
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
    _check_own(ctx, req, others)  # before anything is asked: the trader's own rows must be valid
    system, user = scoped_prompts(
        infos.values(), req.screener_id, req.new_words, others, phrasebook, guide,
        open_keys(backlog, limit=len(backlog.items)),
    )  # fmt: skip
    tag = CallTag(USE_CASE, ctx.user.user_id, PROMPT_VERSION)
    answered: list[ScreenDraft] = []  # the draft of the new words alone, before the merge

    def finish(sub: ScreenDraft) -> ScreenDraft:
        answered.append(sub)
        asked(sub.call_id)
        return merge_part(ctx, req, sub)  # a ConfigurationError here rejects the answer in the log

    merged = draft_words(
        ctx, model, req.screener_id, req.new_words, system, user, tag, infos, phrasebook, finish
    )
    sub = answered[0]
    known = {missing_ref(m) for m in req.prior.missing}  # recorded when they were asked
    fresh = tuple(m for m in sub.missing if missing_ref(m) not in known)
    return Redrafted(merged, req.part.id, req.old_words, req.new_words, fresh)


def _check_own(ctx: ReadContext, req: PartRequest, others: Mapping[str, Any]) -> None:
    """The criteria of the other parts and the tie-break the part does not own are valid as
    finalise sees them, or ``ConfigurationError`` (a 400) naming the first that is not: the merge
    never drops what the trader has, and the model is not asked about a screen that cannot be
    saved."""
    document = {k: v for k, v in req.prior.document.items() if k not in ("criteria", "rank")}
    document["criteria"] = dict(others)
    rank = req.prior.document.get("rank")
    if rank is not None and not req.part.rank:
        document["rank"] = rank
    checked, refused = validated(ctx, req.screener_id, document, ())
    if refused:
        raise ConfigurationError(
            f"{req.screener_id}: the criterion {refused[0].id!r} of your screen is not valid: "
            f"{refused[0].reason}; fix it before retyping a part"
        )
    if "rank" in document and "rank" not in checked:
        raise ConfigurationError(
            f"{req.screener_id}: the tie-break of your screen is not valid; fix it before "
            "retyping a part"
        )
