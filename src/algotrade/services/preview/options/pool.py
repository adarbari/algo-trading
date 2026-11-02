"""The underlying a calculator prices (a ticker or id resolved in the session's reference
snapshot, ``NotFoundError`` when it names none) and one expiry and right of its session chain
priced at the mid (ownership ``option-calculators``): each listed strike with a two-sided
quote, its mid and our delta (the grid's convention, ``band_pick.OurDeltas``: BSM with the
session's rate and dividend yield, NaN where no vol inverts), open interest and the day's
volume. The vendor
bid and ask stop here: nothing downstream sees them.
"""

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from algotrade.data.chains import OPTION_QUOTES
from algotrade.features.rollups.positioning.chain_inputs import two_sided_mid
from algotrade.features.rollups.premium.band_pick import OurDeltas
from algotrade.quant.rates import DAYS_PER_YEAR
from algotrade.services.read.context import ReadContext
from algotrade.services.read.instruments.identity import resolve_id
from algotrade.services.read.options.session_inputs import PricingInputs, gap
from algotrade.services.read.session import NotFoundError
from algotrade.services.read.values import Unknown, UnknownCode

PUT, CALL = "put", "call"
RIGHT_CODE = {PUT: "P", CALL: "C"}  # the chain's ``right`` values
COLUMNS = ["strike", "mid", "delta", "open_interest", "volume"]
_MATCH = 1e-6  # a typed strike matches a listed one within this


@dataclass(frozen=True)
class Contract:
    """An option as the trader typed it: ``right`` put or call, its strike and expiry."""

    right: str
    strike: float
    expiry: date


@dataclass(frozen=True)
class Listed:
    """A typed contract as listed tonight: its mid and our delta (NaN: no vol inverts), the
    open interest and the day's volume (None or NaN when the quote carries none)."""

    mid: float
    delta: float
    open_interest: float | None
    volume: float | None


def underlying(ctx: ReadContext, key: str) -> str:
    """The ``instrument_id`` ``key`` (an id or a ticker) names for ``ctx.session``."""
    found = resolve_id(ctx, key)
    if found is None:
        raise NotFoundError(f"no instrument {key!r} in the session's reference snapshot")
    return found


def listed_expiries(inputs: PricingInputs, right: str, session: date) -> list[date]:
    """The expiries after ``session`` with a ``right`` listed, in order."""
    chain = inputs.chain
    found = chain.loc[chain["right"] == RIGHT_CODE[right], "expiry"]
    return sorted(e for e in set(found) if e > session)


def priced_pool(
    inputs: PricingInputs, deltas: OurDeltas, session: date, expiry: date, right: str
) -> pd.DataFrame:
    """``COLUMNS`` of the two-sided ``right`` contracts at ``expiry``, by strike (empty when
    none is two-sided)."""
    chain = inputs.chain
    pool = chain[(chain["right"] == RIGHT_CODE[right]) & (chain["expiry"] == expiry)]
    mid = two_sided_mid(pool["bid"], pool["ask"])
    keep = np.isfinite(mid)
    if not keep.any():
        return pd.DataFrame(columns=COLUMNS)
    strikes = pool["strike"].to_numpy(dtype=float)[keep]
    mids = mid[keep]
    t = (expiry - session).days / DAYS_PER_YEAR
    delta = deltas(mids, inputs.spot, strikes, t, right == CALL)
    out = pd.DataFrame(
        {
            "strike": strikes,
            "mid": mids,
            "delta": delta,
            "open_interest": pool["open_interest"].to_numpy()[keep],
            "volume": pool["volume"].to_numpy()[keep],
        }
    )
    # Two contracts at one strike (an adjusted deliverable): the one with more open interest.
    ranked = out.sort_values(
        ["strike", "open_interest"], ascending=[True, False], kind="stable", na_position="last"
    )
    return ranked.drop_duplicates("strike").reset_index(drop=True)


def figures(pool: pd.DataFrame) -> list[tuple[float, float, float]]:
    """``(strike, mid, delta)`` of each row of a priced pool, in its order."""
    columns = (pool[c].to_numpy(dtype=float) for c in ("strike", "mid", "delta"))
    return [(float(k), float(m), float(d)) for k, m, d in zip(*columns, strict=True)]


def listed_contract(
    ctx: ReadContext, inputs: PricingInputs, deltas: OurDeltas, contract: Contract
) -> Listed | Unknown:
    """``contract`` priced tonight, or why it cannot be: its expiry is not after the session
    or it is not listed (NOT_APPLICABLE), or its quote is one-sided (ILLIQUID)."""
    session = ctx.session.date
    what = f"{contract.right} {contract.strike:g} expiring {contract.expiry}"
    if contract.expiry <= session:
        why = f"{what}: the expiry is not after {session}"
        return gap(ctx, UnknownCode.NOT_APPLICABLE, "EXPIRED", why, OPTION_QUOTES)
    pool = priced_pool(inputs, deltas, session, contract.expiry, contract.right)
    found = pool[(pool["strike"] - contract.strike).abs() <= _MATCH]
    if not found.empty:
        row = found.iloc[0]
        return Listed(
            float(row["mid"]), float(row["delta"]), _number(row["open_interest"]),
            _number(row["volume"]),
        )  # fmt: skip
    chain = inputs.chain
    listed = chain[
        (chain["right"] == RIGHT_CODE[contract.right])
        & (chain["expiry"] == contract.expiry)
        & ((chain["strike"] - contract.strike).abs() <= _MATCH)
    ]
    code, status = (
        (UnknownCode.ILLIQUID, "ILLIQUID")
        if not listed.empty
        else (UnknownCode.NOT_APPLICABLE, "NOT_LISTED")
    )
    why = f"{what}: {status.lower().replace('_', ' ')} on {session}"
    return gap(ctx, code, status, why, OPTION_QUOTES)


def _number(value: object) -> float | None:
    """A stored count as a float; None where it is missing."""
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return None if pd.isna(number) else float(number)
