"""What an ETF holds (ADR 0037 ``Holdings``, ADR 0035): its largest holdings with their weights,
as of the issuer's date the session sees.

Issuer-dated grain (docs/api/read-model.md "Session resolution"): the fund's rows of its
latest ``as_of`` on or before ``ctx.session.date`` whose ``filed`` date (an N-PORT report) is
on or before it too (``data.funds.holdings.etf_holdings``); ``as_of`` is disclosed. A holding
links to the universe through ``instrument_id`` when the issuer's line resolved to one; cash,
futures, bonds and foreign lines keep their name only. Not an ETF: no holdings (``None``); an
ETF with nothing stored (no issuer file or filing yet): empty ``items`` and ``as_of`` None."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from algotrade.core.model.errors import ConfigurationError
from algotrade.data.funds.holdings import etf_holdings
from algotrade.services.read.context import ReadContext
from algotrade.services.read.instruments.identity import load_instruments
from algotrade.services.read.values import to_scalar


@dataclass(frozen=True)
class Holding:
    """One line of the fund. ``symbol``: the issuer's ticker for the line (None: none
    printed); ``instrument_id``: the universe instrument it resolved to (None: not in the
    universe); ``weight``: a fraction of the fund (0.0844 = 8.44%), negative for shorts."""

    rank: int
    name: str
    symbol: str | None
    instrument_id: str | None
    weight: float
    asset_class: str | None


@dataclass(frozen=True)
class Holdings:
    """The ``top`` largest lines of one fund. ``source``: the reader of the issuer's file
    (ssga_holdings, ishares_holdings, sec_nport); ``total``: positions in that file."""

    fund_id: str
    as_of: date | None
    source: str | None
    total: int
    items: tuple[Holding, ...]


def _text(value: object) -> str | None:
    found = to_scalar(value)
    return str(found) if found is not None else None


def _holdings(ctx: ReadContext, fund_id: str, top: int) -> Holdings:
    frame = etf_holdings(ctx.reader, fund_id, ctx.session.date)
    if frame.empty:
        return Holdings(fund_id, None, None, 0, ())
    first = frame.iloc[0]
    items = tuple(
        Holding(
            rank=int(r["rank"]),
            name=str(r["holding_name"]),
            symbol=_text(r["holding_symbol"]),
            instrument_id=_text(r["holding_id"]),
            weight=float(r["weight"]),
            asset_class=_text(r["asset_class"]),
        )
        for r in frame.head(top).to_dict("records")
    )
    return Holdings(
        fund_id, first["as_of"], _text(first["source"]), int(first["holdings_count"]), items
    )


def load_holdings(
    ctx: ReadContext, fund_ids: Sequence[str], top: int
) -> dict[str, Holdings | None]:
    """The ``top`` largest holdings of each of ``fund_ids`` for ``ctx.session`` (None: not
    an ETF in the session's reference snapshot, or no such instrument). ``ConfigurationError``
    for a ``top`` under 1. One ``etf_holdings`` read per fund (the pane asks for one)."""
    if top < 1:
        raise ConfigurationError(f"top: at least 1, got {top}")
    funds = load_instruments(ctx, fund_ids)
    return {
        iid: _holdings(ctx, iid, top) if (f := funds.get(iid)) is not None and f.is_etf else None
        for iid in fund_ids
    }
