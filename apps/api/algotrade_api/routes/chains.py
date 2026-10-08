"""``/chains/{id}/live``: live quotes of one expiry of an underlying's option chain (``id``: an
instrument id or a ticker; ADR 0028). The stored chain itself is a page read on GraphQL
(``Instrument.chain``, read-model PR 6); this route stays REST by design (latency-bound,
records to ``live/*``)."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from algotrade_api.deps import Caller, Context, Live
from algotrade_api.redact import redact
from algotrade_api.schemas.chains import LiveOptionChain

router = APIRouter(prefix="/chains", tags=["chains"])


@router.get("/{underlying_id}/live")
def live_chain(
    ctx: Context,
    caller: Caller,
    live: Live,
    underlying_id: str,
    expiry: date,
    strikes: Annotated[
        list[float] | None,
        Query(
            description="strikes to quote (repeat the parameter); default: those nearest "
            "the underlying"
        ),
    ] = None,
) -> LiveOptionChain:
    """Live quotes from IB Gateway (read-only, cached briefly); the stored delayed chain with
    a status when the gateway cannot answer. Each live answer is recorded (``live/*``)."""
    found = LiveOptionChain.model_validate(live.chain(ctx, underlying_id, expiry, strikes))
    return redact(found, caller.role)
