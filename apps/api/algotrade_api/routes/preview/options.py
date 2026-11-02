"""``POST /preview/options/{roll,calls}``: the option calculators (plan V11) over figures a
trader types, priced on the request's session. Body only, never a query string, and the answer
is ``Cache-Control: no-store``: what a trader types stays out of request logs (the access log
names the path alone) and out of every cache (``test_options.py`` holds both). A gap's cause
is an admin's only (``redact``, ADR 0056)."""

from fastapi import APIRouter, Response

from algotrade.services.preview.options import calls, roll
from algotrade_api.deps import Caller, Context
from algotrade_api.redact import redact
from algotrade_api.schemas.preview.options import (
    CallsBody,
    CallsResult,
    RollBody,
    RollResult,
    calls_result,
    roll_result,
)

router = APIRouter(prefix="/preview/options", tags=["preview"])
NO_STORE = {"Cache-Control": "no-store"}


@router.post("/roll")
def preview_roll(ctx: Context, caller: Caller, body: RollBody, response: Response) -> RollResult:
    response.headers.update(NO_STORE)
    contract = roll.Contract(body.right, body.strike, body.expiry)
    found = roll.preview_roll(
        ctx, body.key, contract, body.sold_at, body.include_debits, body.same_delta
    )
    return redact(roll_result(found), caller.role)


@router.post("/calls")
def preview_calls(ctx: Context, caller: Caller, body: CallsBody, response: Response) -> CallsResult:
    response.headers.update(NO_STORE)
    found = calls.preview_calls(ctx, body.key, body.shares, body.price)
    return redact(calls_result(found), caller.role)
