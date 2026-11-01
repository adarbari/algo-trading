"""``short_premium@v1``: the short put and short call at 0.20 delta, about 30 days out, as
summary figures a list can filter on (ADR 0038; the option grid of ADR 0083's amendment of
2026-11-01 is the full table, a read over the same chain).

It is the grid's (0.20 delta, 30-day) cell: the same expiry rule (the listed expiry nearest 30
calendar days within 30% of it, ``band_pick.pick_expiry``) and the same pick and figures
(``band_pick.pick_band``: our delta, the nearest two-sided strike within 0.025 of 0.20), so a
list and the grid never disagree (a contract test holds them equal). The grid's 30-day row has
no monthlies-first rule: the nearest expiry is the cell.

One row per underlying with a chain or an underlying quote. ``premium_status``, first failing
step wins (the put side, then the call side):

    OK         both sides found
    NO_SPOT    no positive underlying price
    NO_CHAIN   no option quotes for the underlying
    NO_EXPIRY  no listed expiry within 30% of 30 days
    ILLIQUID   a side has no two-sided quote at the expiry, or none whose vol inverts
    NO_STRIKE  a side's nearest strike is farther than 0.025 delta from 0.20

A side that was found keeps its columns when the other fails (its status says which). Inputs
as ``put_wing@v1``: ``chains/option_quotes`` (required), ``rates/treasury`` (required),
``chains/underlying_quotes`` and ``div_yield@v1`` (q is 0 where unknown). The band, window and
tolerances are part of v1: changing one is v2.
"""

from datetime import date
from typing import cast

import numpy as np
import pandas as pd

from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.options.iv30 import (
    DIVIDENDS,
    OPTIONS,
    RATES,
    UNDERLYINGS,
    positive_spots,
)
from algotrade.features.rollups.options.wing_search import div_yields
from algotrade.features.rollups.premium import band_pick
from algotrade.quant.rates import YieldCurve

NAME = "short_premium"
VERSION = 1
BAND = 0.20  # |delta| of both sides
TARGET_DAYS = 30  # calendar days to the expiry
STATUSES = ("OK", "NO_SPOT", "NO_CHAIN", "NO_EXPIRY", "ILLIQUID", "NO_STRIKE")

_QUOTE = tuple(f"{OPTIONS}.{c}" for c in ("bid", "ask", "strike", "expiry", "right"))
_INPUTS = (*_QUOTE, f"{UNDERLYINGS}.price", f"{RATES}.rate_cont", "div_yield@v1")
_NO_EXPIRY = (
    "no listed expiry within 30% of 30 days (premium_status NO_EXPIRY), or no spot or chain"
)
_UNFOUND = "no two-sided strike within 0.025 of 0.20 |delta| at the expiry (see premium_status)"


def _side(side: str) -> tuple[Feature, ...]:
    def feature(name: str, unit: str, text: str, rng: tuple[float, float | None]) -> Feature:
        return Feature(
            f"{side}_{name}", "float32", unit, text, f"{_UNFOUND}: the {side} side",
            "chain", valid_range=rng, inputs=_INPUTS,
        )  # fmt: skip

    collateral = "strike" if side == "put" else "spot"
    return (
        feature("strike", "usd_per_share", f"The short {side}'s strike: our |delta| nearest 0.20",
                (0, None)),
        feature("breakeven", "usd_per_share",
                f"The {side}'s breakeven: {'strike - mid' if side == 'put' else 'spot - mid'}",
                (0, None)),
        feature("yield_ann", "decimal",
                f"The {side}'s yield a year on its collateral: mid / {collateral} x 365 / days "
                "to the expiry (simple, not compounded)", (0, None)),
    )  # fmt: skip


FEATURES = (
    Feature(
        "premium_status", "str", "category",
        "OK (both the 0.20-delta put and call were found), or the first failing step: NO_SPOT, "
        "NO_CHAIN, NO_EXPIRY (none within 30% of 30 days), ILLIQUID (a side has no two-sided "
        "quote or no vol of ours), NO_STRIKE (no strike within 0.025 of 0.20 delta)",
        "never", "label", categories=STATUSES, inputs=_INPUTS,
    ),
    Feature(
        "target_expiry", "date", "date",
        "The listed expiry nearest 30 calendar days within 30% of it (ties: the earlier)",
        _NO_EXPIRY, "chain", inputs=(f"{OPTIONS}.expiry",),
    ),
    Feature(
        "target_dte", "int", "days",
        "Calendar days from the session to the target expiry",
        _NO_EXPIRY, "chain", valid_range=(21, 39), inputs=(f"{OPTIONS}.expiry",),
    ),
    *_side("put"),
    *_side("call"),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def _row(
    chain: pd.DataFrame, session: date, spot: float, deltas: band_pick.OurDeltas
) -> dict[str, object]:
    listed = cast(list[date], chain["expiry"].tolist())
    expiry = band_pick.pick_expiry(sorted(set(listed)), session, TARGET_DAYS)
    if expiry is None:
        return {"premium_status": "NO_EXPIRY"}
    row: dict[str, object] = {
        "target_expiry": expiry,
        "target_dte": (expiry - session).days,
        "premium_status": "OK",
    }
    for side in (band_pick.PUT, band_pick.CALL):
        cell = band_pick.pick_band(chain, session, expiry, spot, BAND, side, deltas)
        if isinstance(cell, band_pick.BandMiss):
            if row["premium_status"] == "OK":
                row["premium_status"] = cell.reason
            continue
        row |= {
            f"{side}_strike": cell.strike,
            f"{side}_breakeven": cell.breakeven,
            f"{side}_yield_ann": cell.yield_ann,
        }
    return row


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    options, curve_rows = inputs[OPTIONS], inputs[RATES]
    assert options is not None and curve_rows is not None  # required inputs
    if bool(curve_rows["pre_snapshot"].iloc[0]) if "pre_snapshot" in curve_rows else False:
        return pd.DataFrame(columns=["instrument_id", *COLUMNS])  # a later curve is no curve
    curve = YieldCurve.from_days(curve_rows["tenor_days"], curve_rows["rate_cont"])
    underlyings = inputs.get(UNDERLYINGS)
    spots = positive_spots(underlyings)
    quoted = set() if underlyings is None else set(underlyings["instrument_id"].astype(str))
    yields = div_yields(inputs.get(DIVIDENDS), session)
    options = options.assign(
        underlying_id=options["underlying_id"].astype(str),
        expiry=pd.to_datetime(options["expiry"]).dt.date,
    )
    chains = {str(k): g for k, g in options.groupby("underlying_id")}
    rows = []
    for iid in sorted(quoted | set(chains)):
        if iid not in spots.index:
            row: dict[str, object] = {"premium_status": "NO_SPOT"}
        elif iid not in chains:
            row = {"premium_status": "NO_CHAIN"}
        else:
            found = yields.get(iid)  # a missing or null yield prices with 0, like the grid
            q = float(found) if found is not None and np.isfinite(found) else 0.0
            row = _row(chains[iid], session, float(spots[iid]), band_pick.OurDeltas(curve, q))
        rows.append({"instrument_id": iid, **row})
    return pd.DataFrame(rows).reindex(columns=["instrument_id", *COLUMNS])


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "The short put and call at 0.20 delta about 30 days out: strike, breakeven and yield a "
    "year (the option grid's cell)",
    (
        Input(OPTIONS),
        Input(RATES),
        Input(UNDERLYINGS, required=False),
        Input(DIVIDENDS, required=False),
    ),
    FEATURES,
    compute,
    None,
    applies_to="optionable",
)
