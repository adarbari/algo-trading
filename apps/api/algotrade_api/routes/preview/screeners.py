"""``POST /screeners/preview``: evaluate an unsaved rule-screen draft (an invalid one: 400
naming the field path)."""

from fastapi import APIRouter

from algotrade.services.preview import screens
from algotrade.services.read.availability.cause import Cause, Unavailable, UnavailableKind
from algotrade_api.deps import Caller, Context, Store, Users, acting_user
from algotrade_api.redact import redact, unavailable_for
from algotrade_api.schemas.availability import unavailable_of
from algotrade_api.schemas.preview.screeners import PreviewBody, ScreenPreview

router = APIRouter(prefix="/screeners", tags=["screeners"])


@router.post("/preview")
def preview(
    ctx: Context, store: Store, caller: Caller, users: Users, body: PreviewBody
) -> ScreenPreview:
    who = acting_user(caller, users, body.user)
    result = screens.preview_screen(ctx, store.preview_cache, body.spec, who, body.limit)
    out = ScreenPreview.model_validate(result)
    gaps = unavailable_for(ctx, result.coverage.missing_tables, ctx.session.date, caller.role)
    if result.coverage.withheld_fields:  # fields under a data licence the viewer lacks
        withheld = Unavailable(
            UnavailableKind.LICENCE, tuple(result.coverage.withheld_fields), Cause(())
        )
        gaps.append(unavailable_of(withheld))
    coverage = out.coverage.model_copy(update={"unavailable": gaps})
    return redact(out.model_copy(update={"coverage": coverage}), caller.role)
