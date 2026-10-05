"""One underlying's option chain for a session: expiries, strikes, quotes, Cboe IV and Greeks,
the underlying quote and fetch status, and our own IV30 when the ``iv30`` rollup has it."""

from dataclasses import dataclass
from datetime import date
from typing import Any

from algotrade.data.chains import OPTION_QUOTES, chain_status, option_quotes, underlying_quotes
from algotrade.data.rollups import rollup_row
from algotrade.features.rollups.options import iv30
from algotrade.services.explore.instruments import resolve_key
from algotrade.services.explore.store import (
    NotFoundError,
    ReadStore,
    partition_for,
    record,
    records,
)

QUOTE_COLUMNS = (
    "instrument_id",
    "expiry",
    "right",
    "strike",
    "bid",
    "ask",
    "last",
    "volume",
    "open_interest",
    "iv",
    "delta",
    "gamma",
    "theta",
    "vega",
    "rho",
)


@dataclass(frozen=True)
class OptionChain:
    underlying_id: str
    session: date
    status: str | None  # the chain fetch status (OK, NO_CHAIN, STALE_DATA: ...)
    underlying: dict[str, Any] | None  # price, close, volume, iv30 (Cboe, percent)
    our_iv: dict[str, Any] | None  # the iv30 rollup row for the session (ours, decimal)
    expiries: list[date]
    strikes: list[float]
    quotes: list[dict[str, Any]]  # sorted by expiry, strike, right


def option_chain(
    store: ReadStore, key: str, on: date | None = None, expiry: date | None = None
) -> OptionChain:
    """The chain stored for the latest session on or before ``on`` (only ``expiry`` when
    given). ``NotFoundError`` when the underlying has no chain that session."""
    session = partition_for(store.reader, OPTION_QUOTES, on)
    iid, _ = resolve_key(store, key, session)
    frame = option_quotes(store.reader, session, [iid])
    if frame is None or frame.empty:
        raise NotFoundError(f"no option chain for {iid} on {session}")
    expiries = sorted(set(frame["expiry"]))
    strikes = sorted({float(s) for s in frame["strike"]})
    if expiry is not None:
        frame = frame[frame["expiry"] == expiry]
    frame = frame.sort_values(["expiry", "strike", "right"], kind="stable")
    status = chain_status(store.reader, session, [iid])
    quote = underlying_quotes(store.reader, session, [iid])
    ours = rollup_row(store.reader, iv30.GROUP.table, iid, session)
    return OptionChain(
        underlying_id=iid,
        session=session,
        status=str(status["status"].iloc[0]) if status is not None and len(status) else None,
        underlying=record(quote.iloc[0], ["instrument_id"])
        if quote is not None and len(quote)
        else None,
        our_iv=record(ours[1], ["instrument_id"]) if ours and ours[0] == session else None,
        expiries=expiries,
        strikes=strikes,
        quotes=records(frame.reindex(columns=list(QUOTE_COLUMNS))),
    )
