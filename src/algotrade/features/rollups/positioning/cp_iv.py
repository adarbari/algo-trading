"""``cp_iv@v1``: the call-put IV spread, the individual-option smirk and the ATM call and put
vols at one expiry (edge ideas c01, c02 and c03, ``docs/edge-ideas/options-volatility.md``).

Inputs: the session's ``chains/option_quotes`` and ``rates/treasury`` (required),
``chains/underlying_quotes`` and ``div_yield@v1`` (optional; a missing yield prices with
``q = 0``). One row per underlying with a chain or an underlying quote. Parameters:
``CpIvParams`` (``rollups.toml ["cp_iv@v1"]``). Spot is the shared rule (``closing_spots``).

One expiry per underlying: the listed expiry ``min_days..max_days`` (10..60) calendar days out
nearest ``target_days`` (30), the earlier on a tie. Over that expiry's **smile quotes**
(two-sided, ``(ask - bid) / mid <= max_spread_pct``) each contract's mid is inverted to its own
IV (``wing_search.our_deltas``, ADR 0021). With ``m = strike / spot``:

- ``cp_iv_spread`` (c01, Cremers-Weinbaum): the open-interest-weighted mean of
  ``IV_call - IV_put`` over the matched pairs (a call and a put of the same strike with both
  smile quotes) whose ``|m - 1| <= pair_band`` (0.10); the weight of a pair is the mean of the
  two open interests, so a pair with no open interest has none and a name whose pairs all have
  none is null;
- ``atm_call_iv`` / ``atm_put_iv`` (c03, An-Ang-Bali-Cakici's inputs): the call (put) IV at the
  strike nearest the spot among ``|m - 1| <= atm_band`` (0.05), the lower strike on a tie;
- ``iv_smirk`` (c02, Xing-Zhang-Zhao): the IV of the put with ``m`` in ``otm_lo..otm_hi``
  (0.80..0.95) nearest ``otm_hi``, minus ``atm_call_iv``.

``cp_iv_status``, first failing step wins:

    NO_SPOT    no positive underlying close or price
    NO_CHAIN   no option quotes for the underlying
    NO_EXPIRY  no expiry ``min_days..max_days`` days out
    NO_PAIRS   an expiry, but no weighted matched pair (``cp_iv_spread`` null; the ATM vols
               and the smirk may still have values)
    OK         a spread

Chains are stored nightly from 2026-10-02 only, with no earlier source, so every column has
history from that date; the changes over a window are ``cp_iv_history@v1``'s.
"""

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.options.iv30 import DIVIDENDS, RATES, div_yields
from algotrade.features.rollups.options.wing_search import our_deltas
from algotrade.features.rollups.positioning.chain_inputs import (
    OPTIONS,
    UNDERLYINGS,
    read_chain,
    relative_spread,
    two_sided_mid,
)
from algotrade.quant.rates import YieldCurve

NAME = "cp_iv"
VERSION = 1
STATUSES = ("OK", "NO_SPOT", "NO_CHAIN", "NO_EXPIRY", "NO_PAIRS")

_QUOTE = tuple(f"{OPTIONS}.{c}" for c in ("bid", "ask", "strike", "expiry", "right"))
_INPUTS = (
    *_QUOTE,
    f"{OPTIONS}.open_interest",
    f"{UNDERLYINGS}.close",
    f"{UNDERLYINGS}.price",
    f"{RATES}.rate_cont",
    "div_yield@v1",
)
_FROM = "chains are stored nightly from 2026-10-02 only, so there is no history before that date"
_NO_EXPIRY = "no chain or spot, or no expiry 10..60 days out (cp_iv_status says which)"

FEATURES = (
    Feature(
        "cp_iv_status", "str", "category",
        "OK, or the first failing step: NO_SPOT, NO_CHAIN, NO_EXPIRY (none 10..60 days out), "
        "NO_PAIRS (an expiry but no call-put pair of the same strike with a quote and open "
        "interest on both sides)",
        "never", "label", categories=STATUSES, inputs=_INPUTS,
    ),
    Feature(
        "cp_iv_spread", "float32", "decimal",
        "Call-put IV spread at the expiry nearest 30 days (10..60): the open-interest-weighted "
        "mean of call IV minus put IV over same-strike pairs within 10% of the spot; positive: "
        "calls richer than puts (0.02 is two vol points), the Cremers-Weinbaum signal. "
        f"Chain-derived, so {_FROM}",
        "cp_iv_status is not OK (the status says why)", "chain", valid_range=(-2, 2),
        inputs=_INPUTS,
    ),
    Feature(
        "atm_call_iv", "float32", "decimal",
        "The call IV at the strike nearest the spot (within 5%) at the expiry nearest 30 days "
        f"(10..60); chain-derived, so {_FROM}",
        _NO_EXPIRY + ", or no call within 5% of the spot with a smile quote", "chain",
        valid_range=(0, 5), inputs=_INPUTS,
    ),
    Feature(
        "atm_put_iv", "float32", "decimal",
        "The put IV at the strike nearest the spot (within 5%) at the expiry nearest 30 days "
        f"(10..60); chain-derived, so {_FROM}",
        _NO_EXPIRY + ", or no put within 5% of the spot with a smile quote", "chain",
        valid_range=(0, 5), inputs=_INPUTS,
    ),
    Feature(
        "iv_smirk", "float32", "decimal",
        "The individual-option smirk: the IV of the OTM put with strike 0.80..0.95 of the spot "
        "nearest 0.95, minus the ATM call IV (atm_call_iv), at the expiry nearest 30 days "
        "(10..60); positive: the put wing is richer than the ATM call, the Xing-Zhang-Zhao "
        f"SKEW (a steep smirk predicts lower returns). Chain-derived, so {_FROM}",
        _NO_EXPIRY + ", or no OTM put in the band, or atm_call_iv is null", "chain",
        valid_range=(-2, 5), inputs=_INPUTS,
    ),
    Feature(
        "cp_iv_dte", "int", "days",
        "Calendar days from the session to the expiry the cp_iv columns read",
        _NO_EXPIRY, "chain", valid_range=(1, None), inputs=(f"{OPTIONS}.expiry",),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


@dataclass(frozen=True)
class CpIvParams:
    target_days: int = 30  # the expiry nearest this many days out
    min_days: int = 10  # among expiries min_days..max_days out
    max_days: int = 60
    max_spread_pct: float = 0.35  # a smile quote's (ask - bid) / mid, as iv30@v1
    pair_band: float = 0.10  # cp_iv_spread pairs: |strike / spot - 1| <= this
    atm_band: float = 0.05  # the ATM vols: |strike / spot - 1| <= this
    otm_lo: float = 0.80  # the smirk's put: strike / spot in otm_lo..otm_hi
    otm_hi: float = 0.95

    def __post_init__(self) -> None:
        if not 1 <= self.min_days <= self.target_days <= self.max_days:
            raise ValueError("need 1 <= min_days <= target_days <= max_days")
        if self.max_spread_pct <= 0 or not 0 < self.atm_band <= self.pair_band < 1:
            raise ValueError("need max_spread_pct > 0 and 0 < atm_band <= pair_band < 1")
        if not 0 < self.otm_lo < self.otm_hi <= 1:
            raise ValueError("need 0 < otm_lo < otm_hi <= 1")


def target_expiries(options: pd.DataFrame, session: date, p: CpIvParams) -> pd.Series:
    """The expiry per underlying: ``min_days..max_days`` out, nearest ``target_days``, the
    earlier on a tie. Indexed by ``underlying_id``; empty when none."""
    pairs = options[["underlying_id", "expiry"]].drop_duplicates()
    dte = np.array([(e - session).days for e in pairs["expiry"]], dtype=int)
    pairs = pairs.assign(dte=dte, gap=np.abs(dte - p.target_days))
    pairs = pairs[(pairs["dte"] >= p.min_days) & (pairs["dte"] <= p.max_days)]
    best = pairs.sort_values(["underlying_id", "gap", "expiry"]).drop_duplicates("underlying_id")
    return best.set_index("underlying_id")["expiry"]


def _nearest(side: pd.DataFrame, target: float, lo: float, hi: float) -> pd.Series:
    """The IV of the contract per underlying with ``m`` in ``lo..hi`` nearest ``target``
    (the lower strike on a tie)."""
    band = side[(side["m"] >= lo) & (side["m"] <= hi)]
    band = band.assign(gap=(band["m"] - target).abs())
    best = band.sort_values(["underlying_id", "gap", "strike"]).drop_duplicates("underlying_id")
    return best.set_index("underlying_id")["iv"]


def spread_by_underlying(calls: pd.DataFrame, puts: pd.DataFrame, p: CpIvParams) -> pd.Series:
    """The open-interest-weighted mean of ``iv_call - iv_put`` over matched same-strike pairs
    within ``pair_band``; NaN for an underlying whose pairs carry no open interest."""
    pairs = calls.merge(puts, on=["underlying_id", "strike"], suffixes=("_c", "_p"))
    pairs = pairs[(pairs["m_c"] - 1).abs() <= p.pair_band]
    weight = (pairs["oi_c"] + pairs["oi_p"]) / 2
    frame = pairs.assign(diff=pairs["iv_c"] - pairs["iv_p"], weight=weight)
    frame = frame[frame["weight"] > 0]
    frame = frame.assign(weighted=frame["diff"] * frame["weight"])
    sums = frame.groupby("underlying_id")[["weighted", "weight"]].sum()
    return sums["weighted"] / sums["weight"]


def _priced(
    contracts: pd.DataFrame, curve: YieldCurve, p: CpIvParams
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The smile quotes of the calls and the puts with ``iv``, ``m`` and ``oi``."""
    mid = two_sided_mid(contracts["bid"], contracts["ask"])
    smile = contracts[relative_spread(contracts["bid"], contracts["ask"], mid) <= p.max_spread_pct]
    out = []
    for right, is_call in (("C", True), ("P", False)):
        side = our_deltas(smile[smile["right"] == right], curve, is_call)
        side = side[np.isfinite(side["iv"])]
        out.append(
            side.assign(
                m=side["strike"].astype(float) / side["spot"].astype(float),
                oi=pd.to_numeric(side["open_interest"], errors="coerce").fillna(0.0),
            )
        )
    return out[0], out[1]


def compute(inputs: Inputs, session: date, p: CpIvParams) -> pd.DataFrame:
    curve, spots, options, ids = read_chain(inputs)
    priced = options[options["underlying_id"].isin(spots.dropna().index)]
    chosen = target_expiries(priced, session, p)
    contracts = priced.merge(chosen.rename("expiry").reset_index(), on=["underlying_id", "expiry"])
    q = div_yields(inputs.get(DIVIDENDS), session)
    contracts = contracts.assign(
        dte=[(e - session).days for e in contracts["expiry"]],
        spot=spots.reindex(contracts["underlying_id"]).to_numpy(dtype=float),
        q=q.reindex(contracts["underlying_id"]).fillna(0.0).to_numpy(dtype=float),
    )
    if len(contracts):
        calls, puts = _priced(contracts, curve, p)
    else:
        calls = puts = contracts.assign(iv=np.nan, m=np.nan, oi=np.nan)
    spread = spread_by_underlying(calls, puts, p)
    atm_c = _nearest(calls, 1.0, 1 - p.atm_band, 1 + p.atm_band)
    atm_p = _nearest(puts, 1.0, 1 - p.atm_band, 1 + p.atm_band)
    wing = _nearest(puts, p.otm_hi, p.otm_lo, p.otm_hi)
    with_chain = set(options["underlying_id"])
    rows = []
    for iid in ids:
        if np.isnan(spots.get(iid, np.nan)):
            rows.append({"instrument_id": iid, "cp_iv_status": "NO_SPOT"})
            continue
        if iid not in with_chain:
            rows.append({"instrument_id": iid, "cp_iv_status": "NO_CHAIN"})
            continue
        if iid not in chosen.index:
            rows.append({"instrument_id": iid, "cp_iv_status": "NO_EXPIRY"})
            continue
        call = atm_c.get(iid, np.nan)
        rows.append(
            {
                "instrument_id": iid,
                "cp_iv_status": "OK" if np.isfinite(spread.get(iid, np.nan)) else "NO_PAIRS",
                "cp_iv_spread": spread.get(iid, np.nan),
                "atm_call_iv": call,
                "atm_put_iv": atm_p.get(iid, np.nan),
                "iv_smirk": wing.get(iid, np.nan) - call,
                "cp_iv_dte": (chosen[iid] - session).days,
            }
        )
    return pd.DataFrame(rows).reindex(columns=["instrument_id", *COLUMNS])


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "The call-put IV spread, the OTM-put smirk and the ATM call and put IV at the expiry "
    "nearest 30 days, from our own IV per contract",
    (
        Input(OPTIONS),
        Input(RATES),
        Input(UNDERLYINGS, required=False),
        Input(DIVIDENDS, required=False),
    ),
    FEATURES,
    compute,
    CpIvParams(),
    applies_to="optionable",
)
