"""``oi_walls@v1``: the call wall and put wall, the strikes with the most open interest above
and below spot (``docs/data/swing.md``).

Inputs: the session's ``chains/option_quotes`` (required) and ``chains/underlying_quotes``
(the spot captured with the chain). One row per underlying with a chain or an underlying quote.

Open interest is summed per strike across every expiry ``dte_min..dte_max`` (1..60) calendar
days out (an expiry on the session itself is left out: it is gone by the next open). The
**call wall** is the strike at or above spot with the most call OI, the **put wall** the strike
at or below spot with the most put OI; ties go to the strike nearer spot. A missing OI counts
as 0. Cboe OI is an end-of-day figure (OCC updates it once a day, overnight), so the walls
describe positioning at a close, not intraday. ``wall_status``, first failing step wins:

    NO_SPOT    no positive underlying price
    NO_CHAIN   no option quotes for the underlying
    NO_EXPIRY  no expiry 1..60 days out
    NO_OI      no positive OI at or above spot in calls nor at or below spot in puts
    PARTIAL    one wall found (the other side has no positive OI)
    OK         both walls found

The DTE window is named in the feature descriptions: changing it is a new version.
"""

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.options.iv30 import OPTIONS, UNDERLYINGS
from algotrade.features.rollups.options.put_wing import positive_spots

NAME = "oi_walls"
VERSION = 1
STATUSES = ("OK", "PARTIAL", "NO_OI", "NO_SPOT", "NO_CHAIN", "NO_EXPIRY")

_CHAIN = tuple(f"{OPTIONS}.{c}" for c in ("strike", "expiry", "right", "open_interest"))
_INPUTS = (*_CHAIN, f"{UNDERLYINGS}.price")


def _wall(side: str, where: str) -> str:
    return (
        f"no {side} with open interest above 0 at a strike {where} spot 1..60 days out, or "
        "wall_status NO_SPOT, NO_CHAIN or NO_EXPIRY"
    )


FEATURES = (
    Feature(
        "wall_status", "str", "category",
        "OK (both walls), PARTIAL (one wall), NO_OI (no open interest on either side), or the "
        "first failing step: NO_SPOT, NO_CHAIN (no quotes), NO_EXPIRY (none 1..60 days out)",
        "never", "label", categories=STATUSES, inputs=_INPUTS,
    ),
    Feature(
        "call_wall", "float32", "usd_per_share",
        "Call wall: the strike at or above spot with the most call open interest, summed "
        "across expiries 1..60 calendar days out (end-of-day OI; ties: nearer spot)",
        _wall("call", "at or above"), "chain", valid_range=(0, None), inputs=_INPUTS,
    ),
    Feature(
        "call_wall_oi", "int", "count", "Call open interest at the call wall, summed across "
        "expiries 1..60 days out",
        _wall("call", "at or above"), "chain", valid_range=(1, None), inputs=_INPUTS,
    ),
    Feature(
        "put_wall", "float32", "usd_per_share",
        "Put wall: the strike at or below spot with the most put open interest, summed across "
        "expiries 1..60 calendar days out (end-of-day OI; ties: nearer spot)",
        _wall("put", "at or below"), "chain", valid_range=(0, None), inputs=_INPUTS,
    ),
    Feature(
        "put_wall_oi", "int", "count", "Put open interest at the put wall, summed across "
        "expiries 1..60 days out",
        _wall("put", "at or below"), "chain", valid_range=(1, None), inputs=_INPUTS,
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


@dataclass(frozen=True)
class OiWallsParams:
    dte_min: int = 1  # expiries dte_min..dte_max calendar days out are summed
    dte_max: int = 60

    def __post_init__(self) -> None:
        if not 0 <= self.dte_min <= self.dte_max:
            raise ValueError("need 0 <= dte_min <= dte_max")


def walls(options: pd.DataFrame, spots: pd.Series, call: bool) -> dict[str, tuple[float, int]]:
    """Per underlying, the wall strike and its summed OI on one side: calls at or above spot,
    puts at or below; the most OI, ties to the strike nearer spot."""
    side = options[options["right"] == ("C" if call else "P")]
    by_strike = side.groupby(["underlying_id", "strike"], as_index=False)["oi"].sum()
    spot = spots.reindex(by_strike["underlying_id"]).to_numpy(dtype=float)
    strike = by_strike["strike"].to_numpy(dtype=float)
    beyond = strike >= spot if call else strike <= spot
    found = by_strike.assign(away=np.abs(strike - spot))[beyond & (by_strike["oi"] > 0)]
    best = found.sort_values(["underlying_id", "oi", "away"], ascending=[True, False, True])
    best = best.drop_duplicates("underlying_id")
    pairs = zip(best["strike"].to_numpy(dtype=float), best["oi"].to_numpy(dtype=float), strict=True)
    return {iid: (k, int(oi)) for iid, (k, oi) in zip(best["underlying_id"], pairs, strict=True)}


def compute(inputs: Inputs, session: date, p: OiWallsParams) -> pd.DataFrame:
    options = inputs[OPTIONS]
    assert options is not None  # required input
    underlyings = inputs.get(UNDERLYINGS)
    spots = positive_spots(underlyings)
    quoted = set() if underlyings is None else set(underlyings["instrument_id"].astype(str))
    expiry = pd.to_datetime(options["expiry"]).dt.date
    options = options.assign(
        underlying_id=options["underlying_id"].astype(str),
        right=options["right"].astype(str),
        dte=[(e - session).days for e in expiry],
        oi=pd.to_numeric(options["open_interest"], errors="coerce").fillna(0),
    )
    with_chain = set(options["underlying_id"])
    window = options[options["dte"].between(p.dte_min, p.dte_max)]
    window = window[window["underlying_id"].isin(spots.index)]
    calls, puts = walls(window, spots, call=True), walls(window, spots, call=False)
    in_window = set(window["underlying_id"])
    rows = []
    for iid in sorted(quoted | with_chain):
        row: dict[str, object] = {"instrument_id": iid}
        if iid not in spots.index:
            row["wall_status"] = "NO_SPOT"
        elif iid not in with_chain:
            row["wall_status"] = "NO_CHAIN"
        elif iid not in in_window:
            row["wall_status"] = "NO_EXPIRY"
        else:
            found = 0
            for name, side in (("call", calls), ("put", puts)):
                if iid in side:
                    row[f"{name}_wall"], row[f"{name}_wall_oi"] = side[iid]
                    found += 1
            row["wall_status"] = ("NO_OI", "PARTIAL", "OK")[found]
        rows.append(row)
    return pd.DataFrame(rows).reindex(columns=["instrument_id", *COLUMNS])


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "Call and put walls: the strikes with the most open interest at or above / at or below "
    "spot, summed across expiries 1..60 days out (end-of-day OI)",
    (Input(OPTIONS), Input(UNDERLYINGS, required=False)),
    FEATURES,
    compute,
    OiWallsParams(),
)
