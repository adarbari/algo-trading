"""``POST /preview/options/{roll,calls}``: the option calculators (plan V11) over figures a
trader types, priced on the request's session. Body only, never a query string, and the answer
is ``Cache-Control: no-store``: what a trader types stays out of request logs (the access log
names the path alone) and out of every cache (``test_options.py`` holds both)."""

from fastapi import APIRouter, Response

from algotrade.services.preview.options import calls, roll
from algotrade_api.deps import Context
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
def preview_roll(ctx: Context, body: RollBody, response: Response) -> RollResult:
    response.headers.update(NO_STORE)
    contract = roll.Contract(body.right, body.strike, body.expiry)
    found = roll.preview_roll(
        ctx, body.key, contract, body.sold_at, body.include_debits, body.same_delta
    )
    return roll_result(found)


@router.post("/calls")
def preview_calls(ctx: Context, body: CallsBody, response: Response) -> CallsResult:
    response.headers.update(NO_STORE)
    return calls_result(calls.preview_calls(ctx, body.key, body.shares, body.price))
