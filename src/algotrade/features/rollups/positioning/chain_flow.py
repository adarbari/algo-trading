"""``chain_flow@v1``: option volume and open interest by right, and the unusual-activity
columns (``docs/data/positioning.md`` OP2, ADR 0031).

Input: the session's ``chains/option_quotes`` (required) and ``chains/underlying_quotes``
(optional: an underlying quoted without a chain reads NO_CHAIN). One row per underlying with a
chain or an underlying quote. No spot, no pricing: sums over the stored contracts, with
``dte = expiry - session`` in calendar days.

- **Volume** counts every stored contract, ``dte = 0`` included (it traded that day).
- **Open interest** counts ``dte >= 1`` only: a ``dte = 0`` contract expired at the snapshot
  (the feed still lists it) and is no longer a position.
- **Next expiry**: the first listed expiry with ``dte >= 1``, weeklies and dailies included;
  its call and put volume are ``next_exp_call_volume`` / ``next_exp_put_volume``.
- **Unusual activity** (``dte >= 1``: it compares volume with open interest, so it follows
  the open-interest rule): a contract is unusual when its volume is above its open interest
  and at least ``min_unusual_volume``. ``unusual_contracts`` counts them,
  ``unusual_premium_usd`` is the premium they changed hands for (``volume x mid x 100``,
  two-sided quotes only), ``max_vol_oi_ratio`` the largest ``volume / open_interest`` among
  contracts with ``open_interest >= 1`` and ``volume >= min_unusual_volume``.

A null ``open_interest`` or ``volume`` counts as 0. ``flow_status``: ``NO_CHAIN`` (no quotes
for the underlying on the session) or ``OK``. The put / call ratios over these columns are
expression features (``config/site/features/positioning.toml``).
"""

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.positioning.chain_inputs import (
    OPTIONS,
    UNDERLYINGS,
    days_to,
    expiry_days,
    two_sided_mid,
)

NAME = "chain_flow"
VERSION = 1
STATUSES = ("OK", "NO_CHAIN")
CONTRACT_SIZE = 100  # shares per standard contract (non-standard series are dropped at ingest)

_VOLUME, _OI = f"{OPTIONS}.volume", f"{OPTIONS}.open_interest"
_RIGHT, _EXPIRY = f"{OPTIONS}.right", f"{OPTIONS}.expiry"
_QUOTE = (f"{OPTIONS}.bid", f"{OPTIONS}.ask")
_NO_CHAIN = "flow_status is NO_CHAIN (no option quotes for the underlying on the session)"
_NO_NEXT = f"{_NO_CHAIN}, or no listed expiry with dte >= 1"
_UNUSUAL = "volume above open interest and at least 500 contracts (min_unusual_volume), dte >= 1"

FEATURES = (
    Feature(
        "flow_status", "str", "category",
        "OK, or NO_CHAIN when the underlying has no option quotes on the session",
        "never", "label", categories=STATUSES, inputs=(_VOLUME,),
    ),
    Feature(
        "call_volume", "int", "count",
        "Total call volume on the session across every stored expiry, 0-DTE included",
        _NO_CHAIN, "chain", valid_range=(0, None), inputs=(_VOLUME, _RIGHT),
    ),
    Feature(
        "put_volume", "int", "count",
        "Total put volume on the session across every stored expiry, 0-DTE included",
        _NO_CHAIN, "chain", valid_range=(0, None), inputs=(_VOLUME, _RIGHT),
    ),
    Feature(
        "call_oi", "int", "count",
        "Total call open interest across the expiries 1 or more days out (end-of-day OCC "
        "figure; a 0-DTE contract expired at the snapshot and is left out)",
        _NO_CHAIN, "chain", valid_range=(0, None), inputs=(_OI, _RIGHT, _EXPIRY),
    ),
    Feature(
        "put_oi", "int", "count",
        "Total put open interest across the expiries 1 or more days out (end-of-day OCC "
        "figure; a 0-DTE contract expired at the snapshot and is left out)",
        _NO_CHAIN, "chain", valid_range=(0, None), inputs=(_OI, _RIGHT, _EXPIRY),
    ),
    Feature(
        "next_exp_call_volume", "int", "count",
        "Call volume at the next expiry: the first listed expiry 1 or more days out, weeklies "
        "included",
        _NO_NEXT, "chain", valid_range=(0, None), inputs=(_VOLUME, _RIGHT, _EXPIRY),
    ),
    Feature(
        "next_exp_put_volume", "int", "count",
        "Put volume at the next expiry: the first listed expiry 1 or more days out, weeklies "
        "included",
        _NO_NEXT, "chain", valid_range=(0, None), inputs=(_VOLUME, _RIGHT, _EXPIRY),
    ),
    Feature(
        "unusual_contracts", "int", "count",
        f"Contracts with {_UNUSUAL}: how many traded far above their open interest",
        _NO_CHAIN + " (0 when the chain has none)", "chain", valid_range=(0, None),
        inputs=(_VOLUME, _OI, _EXPIRY),
    ),
    Feature(
        "max_vol_oi_ratio", "float32", "ratio",
        "The largest volume / open interest among contracts 1 or more days out with open "
        "interest of at least 1 and volume of at least 500 (min_unusual_volume)",
        _NO_CHAIN + ", or no contract has open interest of at least 1 and volume of at least "
        "500", "chain", valid_range=(0, None), inputs=(_VOLUME, _OI, _EXPIRY),
    ),
    Feature(
        "unusual_premium_usd", "float32", "usd",
        "Premium paid across the unusual contracts: the sum of volume x mid x 100 over those "
        "with a two-sided quote (bid > 0, ask > bid)",
        _NO_CHAIN + ", or no unusual contract has a two-sided quote", "chain",
        valid_range=(0, None), inputs=(_VOLUME, _OI, _EXPIRY, *_QUOTE),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


@dataclass(frozen=True)
class ChainFlowParams:
    min_unusual_volume: int = 500  # contracts traded: a smaller print is never unusual

    def __post_init__(self) -> None:
        if self.min_unusual_volume < 1:
            raise ValueError("min_unusual_volume must be >= 1")


def flow_columns(options: pd.DataFrame, session: date, p: ChainFlowParams) -> pd.DataFrame:
    """The flow columns by ``underlying_id`` for every underlying in ``options``."""
    right = options["right"].astype(str).to_numpy()
    call, put = right == "C", right == "P"
    volume = pd.to_numeric(options["volume"], errors="coerce").fillna(0).to_numpy(dtype=float)
    oi = pd.to_numeric(options["open_interest"], errors="coerce").fillna(0).to_numpy(dtype=float)
    dte = days_to(expiry_days(options["expiry"]), session)
    ahead = dte >= 1
    uid = options["underlying_id"].astype(str).to_numpy()
    next_dte = pd.Series(np.where(ahead, dte, np.iinfo("int64").max)).groupby(uid).min()
    at_next = ahead & (dte == pd.Series(uid).map(next_dte).to_numpy())
    big = ahead & (volume >= p.min_unusual_volume)
    unusual = big & (volume > oi)
    mid = two_sided_mid(options["bid"], options["ask"])
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = np.where(big & (oi >= 1), volume / oi, np.nan)
    premium = np.where(unusual & np.isfinite(mid), volume * mid * CONTRACT_SIZE, np.nan)
    sums = pd.DataFrame(
        {
            "call_volume": volume * call,
            "put_volume": volume * put,
            "call_oi": oi * (call & ahead),
            "put_oi": oi * (put & ahead),
            "next_exp_call_volume": volume * (call & at_next),
            "next_exp_put_volume": volume * (put & at_next),
            "unusual_contracts": unusual.astype(int),
        }
    )
    out = sums.groupby(uid).sum()
    has_next = (next_dte < np.iinfo("int64").max).reindex(out.index)
    for column in ("next_exp_call_volume", "next_exp_put_volume"):
        out[column] = out[column].where(has_next)
    out["max_vol_oi_ratio"] = pd.Series(ratio).groupby(uid).max()
    out["unusual_premium_usd"] = pd.Series(premium).groupby(uid).sum(min_count=1)
    return out


def compute(inputs: Inputs, session: date, p: ChainFlowParams) -> pd.DataFrame:
    options = inputs[OPTIONS]
    assert options is not None  # required input
    underlyings = inputs.get(UNDERLYINGS)
    quoted = set() if underlyings is None else set(underlyings["instrument_id"].astype(str))
    found = flow_columns(options, session, p) if len(options) else pd.DataFrame()
    ids = sorted(quoted | set(found.index))
    out = found.reindex(ids)
    out["flow_status"] = np.where(pd.Index(ids).isin(found.index), "OK", "NO_CHAIN")
    out.index.name = "instrument_id"
    return out.reset_index().reindex(columns=["instrument_id", *COLUMNS])


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "Option volume and open interest by right (all expiries, and the next expiry), and the "
    "unusual-activity columns: contracts, premium and the largest volume / open interest",
    (Input(OPTIONS), Input(UNDERLYINGS, required=False)),
    FEATURES,
    compute,
    ChainFlowParams(),
    applies_to="optionable",
)
