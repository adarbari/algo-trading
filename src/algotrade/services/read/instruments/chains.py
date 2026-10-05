"""An underlying's option chain for the session (ADR 0037 ``OptionChain``): its listed
expiries (with the calendar days to each), strikes, the fetch status, and the quotes of one
expiry (Cboe bid / ask / IV / Greeks as stored).

Session grain (ADR 0036): ``chains/*`` are read for exactly ``ctx.session.date`` through
``partition``; no partition, or no rows for the underlying, is no chain (``None``), never an
older one. Per-instrument facts about the chain are catalogue features read through
``Instrument.features``, never fields of it: our implied volatility
(``rollup.iv30@v1.iv30``), the underlying's price captured with the chain
(``rollup.option_liquidity@v1.underlying_price``), the target expiry. A listed expiry's ``days`` is
the chain's structure (one per expiry); the nearest expiry's DTE as a per-instrument fact is
``rollup.nearest_expiry@v1.dte``."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd

from algotrade.data.chains import CHAIN_STATUS, OPTION_QUOTES
from algotrade.services.read.context import ReadContext, partition
from algotrade.services.read.values import to_scalar

GREEKS = ("iv", "delta", "gamma", "theta", "vega", "rho")
PRICES = ("bid", "ask", "last", "volume", "open_interest")


@dataclass(frozen=True)
class OptionExpiry:
    """A listed expiry and its calendar days from the session (0: expires on the session)."""

    date: date
    days: int


@dataclass(frozen=True)
class OptionQuote:
    """One contract's stored quote. ``iv`` and the Greeks as the feed computes them (IV a
    decimal); None when not stored."""

    instrument_id: str
    expiry: date
    right: str
    strike: float
    bid: float | None
    ask: float | None
    last: float | None
    volume: float | None
    open_interest: float | None
    iv: float | None
    delta: float | None
    gamma: float | None
    theta: float | None
    vega: float | None
    rho: float | None


@dataclass(frozen=True)
class OptionChain:
    """An underlying's stored chain for the session. ``status``: the chain run's (OK,
    NO_CHAIN, STALE_DATA: ...; None: not recorded)."""

    underlying_id: str
    session: date
    status: str | None
    expiries: tuple[OptionExpiry, ...]
    strikes: tuple[float, ...]


def _number(value: object) -> float | None:
    found = to_scalar(value)
    return float(found) if isinstance(found, int | float) and not isinstance(found, bool) else None


def _text(value: object) -> str | None:
    found = to_scalar(value)
    return str(found) if found is not None else None


def _rows(ctx: ReadContext, underlying_ids: Sequence[str]) -> pd.DataFrame:
    """The session's stored quotes of the chains of ``underlying_ids`` (empty: none). Kept in
    the result cache until the next publish, so the chain and its quotes read it once."""
    wanted = tuple(sorted(set(underlying_ids)))
    key = ("chain-rows", ctx.session.date, wanted, ctx.reader.visible_seq())  # ADR 0022
    found = ctx.cache.get(key)
    if found is None:
        frame = partition(ctx, OPTION_QUOTES)
        if isinstance(frame, pd.DataFrame):
            frame = frame[frame["underlying_id"].astype(str).isin(wanted)]
            frame = frame.assign(expiry=pd.to_datetime(frame["expiry"]).dt.date)
        else:
            frame = pd.DataFrame(columns=["underlying_id", "expiry", "strike", "right"])
        found = frame.reset_index(drop=True)
        ctx.cache.put(key, found)
    return found


def _by_id(ctx: ReadContext, table: str, ids: Sequence[str]) -> dict[str, Mapping[Any, Any]]:
    frame = partition(ctx, table)
    if not isinstance(frame, pd.DataFrame):
        return {}
    frame = frame[frame["instrument_id"].astype(str).isin(list(ids))]
    return {str(r["instrument_id"]): r for r in frame.to_dict("records")}


def load_chains(ctx: ReadContext, underlying_ids: Sequence[str]) -> dict[str, OptionChain | None]:
    """Each underlying's chain for ``ctx.session`` (None: none stored for the session): one
    read of each ``chains/*`` table for them all."""
    rows = _rows(ctx, underlying_ids)
    status = _by_id(ctx, CHAIN_STATUS, underlying_ids)
    day = ctx.session.date
    out: dict[str, OptionChain | None] = {}
    for iid in underlying_ids:
        chain = rows[rows["underlying_id"].astype(str) == iid]
        if chain.empty:
            out[iid] = None
            continue
        out[iid] = OptionChain(
            underlying_id=iid,
            session=day,
            status=_text(status.get(iid, {}).get("status")),
            expiries=tuple(OptionExpiry(e, (e - day).days) for e in sorted(set(chain["expiry"]))),
            strikes=tuple(sorted({float(s) for s in chain["strike"]})),
        )
    return out


def _quote(row: Mapping[Any, Any]) -> OptionQuote:
    n = {c: _number(row.get(c)) for c in (*PRICES, *GREEKS)}
    return OptionQuote(
        instrument_id=str(row["instrument_id"]),
        expiry=row["expiry"],
        right=str(row["right"]),
        strike=float(row["strike"]),
        bid=n["bid"],
        ask=n["ask"],
        last=n["last"],
        volume=n["volume"],
        open_interest=n["open_interest"],
        iv=n["iv"],
        delta=n["delta"],
        gamma=n["gamma"],
        theta=n["theta"],
        vega=n["vega"],
        rho=n["rho"],
    )


def load_quotes(
    ctx: ReadContext, underlying_ids: Sequence[str], expiry: date
) -> dict[str, tuple[OptionQuote, ...]]:
    """Each underlying's stored quotes of ``expiry`` for ``ctx.session``, sorted by strike
    then right (empty: no such expiry stored for the session)."""
    rows = _rows(ctx, underlying_ids)
    rows = rows[rows["expiry"] == expiry].sort_values(["strike", "right"], kind="stable")
    return {
        iid: tuple(
            _quote(r) for r in rows[rows["underlying_id"].astype(str) == iid].to_dict("records")
        )
        for iid in underlying_ids
    }
