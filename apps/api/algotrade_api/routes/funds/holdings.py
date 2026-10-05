"""``/instruments/{id}/holdings``: an ETF's largest holdings (``id``: an instrument id or a
ticker). A non-ETF, or an ETF with nothing stored, answers 200 with an empty list."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from algotrade.services.explore.funds.holdings import etf_top_holdings
from algotrade_api.deps import Store
from algotrade_api.schemas.funds.holdings import EtfHoldings

router = APIRouter(prefix="/instruments", tags=["funds"])


@router.get("/{instrument_id}/holdings")
def holdings(
    store: Store,
    instrument_id: str,
    top: Annotated[int, Query(ge=1, le=1000, description="holdings to return")] = 10,
    on: Annotated[date | None, Query(alias="date")] = None,
) -> EtfHoldings:
    return EtfHoldings.model_validate(etf_top_holdings(store, instrument_id, top, on))
