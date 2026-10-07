"""The wing search ``put_wing@v1`` and ``call_wing@v1`` share: one implementation, two rights.

A wing is the one option to sell at the 30-60 day expiry, found by our own delta. Per
underlying and session (the parameters are ``WingParams``; each group sets its own bands):

- **Target expiry**: the expiry closest to ``dte_target`` (45) calendar days among those
  ``dte_min..dte_max`` (30..60) days out (ties: the earlier), the standard monthlies first when
  ``prefer_monthly`` (open interest concentrates there; a weekly nearer 45 days is usually
  thin), else any listed expiry.
- **Candidates**: its contracts whose OUR |delta| is in ``search_lo..search_hi``.
- **Best contract**: the candidate closest to the target band ``delta_lo..delta_hi`` (edges
  included), i.e. the smallest ``delta_band_distance`` (0 inside the band, else the distance to
  the nearer edge), then the highest premium yield (the side's ``per``: a put's mid / strike,
  a call's mid / spot), then the higher open interest, then the strike the side prefers.
  A chain without a strike in the band still has a best contract (distance > 0), and a screen
  scores the distance instead of rejecting it.
- **Band totals**: strikes, open interest and volume of the contracts inside the band, and
  their median relative spread.

Our delta (ADR 0021; the feed's ``delta`` column is a cross-check only): each two-sided
contract (bid > 0, ask > bid) at the target expiry has its mid inverted with
``quant.implied_vol`` (``t = days / 365``, ``r`` from the Treasury curve the session sees at
``t``, ``q`` from ``div_yield@v1``, 0 when unknown, ``S`` the underlying quote's price), and its
delta is the Black-Scholes-Merton delta of the side's right at that vol
(``quant.black_scholes.greeks``). A contract without a two-sided quote or whose inversion
fails has no delta: it is never a candidate and is counted in ``n_unpriced``. Spreads are the
stored (end-of-day, possibly after-hours) quote's.

Inputs: the session's ``chains/option_quotes`` (required), ``rates/treasury`` (required),
``chains/underlying_quotes`` and ``div_yield@v1``. One row per underlying with a chain or an
underlying quote. ``wing_status``, first failing step wins: NO_SPOT (no positive underlying
price), NO_CHAIN (no quotes of the side's right), NO_EXPIRY (none ``dte_min..dte_max`` days
out), NO_STRIKE (none with our |delta| in ``search_lo..search_hi``), OUTSIDE_BAND (a best
contract, but none in the band), OK (the best contract is in the band).

Also here, so both groups declare the same columns the same way: ``wing_features`` (the
documented columns with their ranges and null meanings, worded from the side and the
parameters' bands) and ``Side`` (what differs between a put and a call).
"""

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from algotrade.core.model.options import standard_monthly_expiries
from algotrade.features.framework.declaration import Inputs
from algotrade.features.framework.feature import Feature, Range
from algotrade.features.rollups.options.iv30 import (  # the same input tables, read the same way
    DIVIDENDS,
    OPTIONS,
    RATES,
    UNDERLYINGS,
    positive_spots,
)
from algotrade.quant.black_scholes import greeks
from algotrade.quant.implied_vol import IVStatus, implied_vol
from algotrade.quant.rates import DAYS_PER_YEAR, YieldCurve

STATUSES = ("OK", "OUTSIDE_BAND", "NO_SPOT", "NO_CHAIN", "NO_EXPIRY", "NO_STRIKE")

_Q = tuple(f"{OPTIONS}.{c}" for c in ("bid", "ask", "strike", "expiry", "right"))
_PRICING = (*_Q, f"{UNDERLYINGS}.price", f"{RATES}.rate_cont", "div_yield@v1")
_OI, _VOL = f"{OPTIONS}.open_interest", f"{OPTIONS}.volume"
_NO_TARGET = "no target expiry (wing_status NO_SPOT, NO_CHAIN or NO_EXPIRY)"


@dataclass(frozen=True, kw_only=True)
class WingParams:
    """The expiry window and delta bands of a wing (a group's subclass sets the bands)."""

    dte_target: int = 45
    dte_min: int = 30
    dte_max: int = 60
    delta_lo: float  # the target |delta| band, both edges included
    delta_hi: float
    search_lo: float  # candidates: search_lo <= |delta| <= search_hi
    search_hi: float
    prefer_monthly: bool = True  # standard monthlies in the window first, else any expiry

    def __post_init__(self) -> None:
        if not 1 <= self.dte_min <= self.dte_target <= self.dte_max:
            raise ValueError("need 1 <= dte_min <= dte_target <= dte_max")
        if not 0 < self.search_lo <= self.delta_lo <= self.delta_hi <= self.search_hi < 1:
            raise ValueError("need 0 < search_lo <= delta_lo <= delta_hi <= search_hi < 1")


@dataclass(frozen=True)
class Side:
    """What differs between the put wing and the call wing."""

    right: str  # the chain's ``right`` value: "P" or "C"
    name: str  # "put" / "call": the columns are ``best_<name>_...``
    yield_name: str  # the best contract's premium-yield column: ``best_<name>_<yield_name>``
    per: str  # the premium's denominator among the contract columns: strike (put), spot (call)
    yield_rank: str  # how the yield reads in the strike's description
    yield_text: str  # the yield column's description
    lower_strike: bool  # an exact tie goes to the lower strike (put) or the higher (call)
    sign: int  # the sign of the contract's delta: -1 put, +1 call

    @property
    def is_call(self) -> bool:
        return self.right == "C"


def _pct(x: float) -> str:
    return f"{x:.2f}"


def wing_features(side: Side, p: WingParams) -> tuple[Feature, ...]:
    """The group's documented columns; the numbers in the descriptions are ``p``'s defaults
    (part of the version: changing a band or window is a new version)."""
    n, band = side.name, f"{_pct(p.delta_lo)}..{_pct(p.delta_hi)}"
    search, window = f"{_pct(p.search_lo)}..{_pct(p.search_hi)}", f"{p.dte_min}..{p.dte_max}"
    no_best = f"no {n} at the target expiry with our |delta| in {search} (NO_STRIKE), or "
    no_best += _NO_TARGET
    no_band = f"no {n} with our |delta| in {band} at the target expiry, or " + _NO_TARGET
    reach = round(max(p.search_hi - p.delta_hi, p.delta_lo - p.search_lo), 6)
    example = p.delta_hi + 0.05

    def best(name: str, dtype: str, unit: str, text: str, rng: Range, *inputs: str) -> Feature:
        return Feature(
            f"best_{n}_{name}", dtype, unit, f"The best {n}'s {text}", no_best, "chain",
            valid_range=rng, inputs=inputs or _PRICING,
        )  # fmt: skip

    ties = "lower" if side.lower_strike else "higher"
    delta_range: Range = (
        (-p.search_hi, -p.search_lo) if side.sign < 0 else (p.search_lo, p.search_hi)
    )
    return (
        Feature(
            "wing_status", "str", "category",
            f"OK (best {n} in {band} |delta|), OUTSIDE_BAND (best {n} in {search} but not the "
            f"band), or the first failing step: NO_SPOT, NO_CHAIN (no {n}s), NO_EXPIRY (none "
            f"{window} days out), NO_STRIKE (no {n} with our |delta| in {search})",
            "never", "label", categories=STATUSES, inputs=_PRICING,
        ),
        Feature(
            "target_expiry", "date", "date",
            f"The {n} expiry closest to {p.dte_target} calendar days among those {window} "
            f"days out, standard monthlies first (ties: the earlier); the best {n}'s expiry",
            _NO_TARGET, "chain", inputs=(f"{OPTIONS}.expiry",),
        ),
        Feature(
            "target_dte", "int", "days",
            f"Calendar days from the session to the target expiry (the best {n}'s DTE)",
            _NO_TARGET, "chain", valid_range=(p.dte_min, p.dte_max), inputs=(f"{OPTIONS}.expiry",),
        ),
        Feature(
            "n_unpriced", "int", "count",
            f"{n.capitalize()}s at the target expiry without our delta (no two-sided quote, or "
            "the implied-vol inversion failed): never candidates",
            _NO_TARGET, "chain", valid_range=(0, None), inputs=_PRICING,
        ),
        Feature(
            "n_strikes", "int", "count",
            f"Strikes at the target expiry whose {n} has our |delta| in {band} (edges "
            "included); 0 when none",
            _NO_TARGET, "chain", valid_range=(0, None), inputs=_PRICING,
        ),
        Feature(
            "wing_oi", "int", "count",
            f"Open interest across the {n}s in the {band} band; 0 when none",
            _NO_TARGET, "chain", valid_range=(0, None), inputs=(*_PRICING, _OI),
        ),
        Feature(
            "wing_volume", "int", "count",
            f"Volume across the {n}s in the {band} band; 0 when none",
            _NO_TARGET, "chain", valid_range=(0, None), inputs=(*_PRICING, _VOL),
        ),
        Feature(
            "wing_spread_pct", "float32", "decimal",
            f"Median (ask - bid) / mid across the {n}s in the {band} band (stored quote)",
            no_band, "chain", valid_range=(0, 2), inputs=_PRICING,
        ),
        Feature(
            "delta_band_distance", "float32", "ratio",
            f"How far the best {n}'s |delta| is from the {band} band: 0 inside, else the "
            f"distance to the nearer edge ({_pct(example)} delta: 0.05)",
            no_best, "chain", valid_range=(0, reach), inputs=_PRICING,
        ),
        best("strike", "float32", "usd_per_share",
             f"strike: the candidate nearest the band, then the highest {side.yield_rank} "
             f"(ties: higher OI, then {ties} strike)", (0, None)),
        best("delta", "float32", "ratio",
             "delta (ours, negative)" if side.sign < 0 else "delta (ours)", delta_range),
        best("iv", "float32", "decimal", "implied vol (ours, from the mid)", (0, 5)),
        best("mid", "float32", "usd_per_share", "mid, (bid + ask) / 2: the premium per share",
             (0, None), f"{OPTIONS}.bid", f"{OPTIONS}.ask"),
        best("oi", "int", "count", "open interest", (0, None), _OI),
        best("volume", "int", "count", "volume", (0, None), _VOL),
        best("spread_pct", "float32", "decimal",
             "(ask - bid) / mid on the stored quote (judge the trade on a live one)", (0, 2),
             f"{OPTIONS}.bid", f"{OPTIONS}.ask"),
        best(side.yield_name, "float32", "decimal", side.yield_text, (0, 1)),
    )  # fmt: skip


def target_expiries(contracts: pd.DataFrame, p: WingParams) -> pd.Series:
    """The target expiry per ``underlying_id`` (only underlyings with one): closest to
    ``dte_target`` within ``dte_min..dte_max`` days (standard monthlies first when
    ``prefer_monthly``), ties to the earlier."""
    pairs = contracts[["underlying_id", "expiry", "dte"]].drop_duplicates()
    window = pairs[pairs["dte"].between(p.dte_min, p.dte_max)]
    monthly = standard_monthly_expiries(pairs["expiry"].unique()) if p.prefer_monthly else set()
    window = window.assign(
        other=~window["expiry"].isin(monthly), off=(window["dte"] - p.dte_target).abs()
    )
    order = ["underlying_id", "other", "off", "expiry"]
    best = window.sort_values(order).drop_duplicates("underlying_id")
    return best.set_index("underlying_id")["expiry"]


def our_deltas(contracts: pd.DataFrame, curve: YieldCurve, is_call: bool) -> pd.DataFrame:
    """``contracts`` (with ``spot``, ``q``, ``dte``) plus ``mid``, ``iv`` and ``delta``: NaN
    for a contract without a two-sided quote or whose inversion fails."""
    bid = contracts["bid"].fillna(0).to_numpy(dtype=float)
    ask = contracts["ask"].fillna(0).to_numpy(dtype=float)
    two_sided = (bid > 0) & (ask > bid)
    mid = np.where(two_sided, (bid + ask) / 2, np.nan)
    t = contracts["dte"].to_numpy(dtype=float) / DAYS_PER_YEAR
    spot = contracts["spot"].to_numpy(dtype=float)
    strike = contracts["strike"].to_numpy(dtype=float)
    r, q = curve.rate(t), contracts["q"].to_numpy(dtype=float)
    iv = np.full(len(contracts), np.nan)
    if two_sided.any():
        k = two_sided
        solved = implied_vol(mid[k], spot[k], strike[k], t[k], r[k], q[k], is_call)
        iv[k] = np.where(solved.status == IVStatus.OK, solved.iv, np.nan)
    priced = np.isfinite(iv)
    delta = np.full(len(contracts), np.nan)
    if priced.any():
        g = greeks(
            spot[priced], strike[priced], t[priced], r[priced], q[priced], iv[priced], is_call
        )
        delta[priced] = g.delta
    return contracts.assign(mid=mid, iv=iv, delta=delta)


def band_distance(size: pd.Series, p: WingParams) -> pd.Series:
    """0 for an |delta| inside ``delta_lo..delta_hi``, else the distance to the nearer edge."""
    return (p.delta_lo - size).clip(lower=0) + (size - p.delta_hi).clip(lower=0)


def wing_row(contracts: pd.DataFrame, p: WingParams, side: Side) -> dict[str, object]:
    """The columns for one underlying from its target expiry's priced contracts (``strike``,
    ``bid``, ``ask``, ``mid``, ``iv``, ``delta``, ``open_interest``, ``volume``, and the
    side's ``per`` column)."""
    size = contracts["delta"].abs()
    oi, volume = contracts["open_interest"].fillna(0), contracts["volume"].fillna(0)
    spread = (contracts["ask"] - contracts["bid"]) / contracts["mid"]
    band = (size >= p.delta_lo) & (size <= p.delta_hi)
    row: dict[str, object] = {
        "n_unpriced": int(contracts["delta"].isna().sum()),
        "n_strikes": int(contracts.loc[band, "strike"].nunique()),
        "wing_oi": int(oi[band].sum()),
        "wing_volume": int(volume[band].sum()),
        "wing_spread_pct": float(spread[band].median()) if band.any() else None,
    }
    found = (size >= p.search_lo) & (size <= p.search_hi)
    if not found.any():
        return {**row, "wing_status": "NO_STRIKE"}
    candidates = contracts[found].assign(
        distance=band_distance(size[found], p),
        premium_yield=contracts["mid"] / contracts[side.per],
        oi=oi,
        volume=volume,
        spread=spread,
    )
    best = candidates.sort_values(
        ["distance", "premium_yield", "oi", "strike"],
        ascending=[True, False, False, side.lower_strike],
    ).iloc[0]
    n = f"best_{side.name}"
    return {
        **row,
        "wing_status": "OK" if best["distance"] == 0 else "OUTSIDE_BAND",
        "delta_band_distance": float(best["distance"]),
        f"{n}_strike": float(best["strike"]),
        f"{n}_delta": float(best["delta"]),
        f"{n}_iv": float(best["iv"]),
        f"{n}_mid": float(best["mid"]),
        f"{n}_oi": int(best["oi"]),
        f"{n}_volume": int(best["volume"]),
        f"{n}_spread_pct": float(best["spread"]),
        f"{n}_{side.yield_name}": float(best["premium_yield"]),
    }


def _div_yields(rows: pd.DataFrame | None, session: date) -> pd.Series:
    if rows is None:
        return pd.Series(dtype=float)
    today = rows[rows["session_date"] == session]
    return pd.Series(
        today["div_yield"].to_numpy(dtype=float), index=today["instrument_id"].astype(str)
    )


def compute(
    inputs: Inputs, session: date, p: WingParams, side: Side, columns: list[str]
) -> pd.DataFrame:
    """The wing of ``side`` per underlying (``columns``: the group's ``instrument_id`` first)."""
    options, curve_rows = inputs[OPTIONS], inputs[RATES]
    assert options is not None and curve_rows is not None  # required inputs
    curve = YieldCurve.from_days(curve_rows["tenor_days"], curve_rows["rate_cont"])
    underlyings = inputs.get(UNDERLYINGS)
    spots = positive_spots(underlyings)
    quoted = set() if underlyings is None else set(underlyings["instrument_id"].astype(str))
    options = options.assign(underlying_id=options["underlying_id"].astype(str))
    contracts = options[options["right"].astype(str) == side.right]
    expiry = pd.to_datetime(contracts["expiry"]).dt.date
    contracts = contracts.assign(expiry=expiry, dte=[(e - session).days for e in expiry])
    targets = target_expiries(contracts[contracts["underlying_id"].isin(spots.index)], p)
    chosen = contracts[
        contracts["expiry"].to_numpy() == targets.reindex(contracts["underlying_id"]).to_numpy()
    ]
    yields = _div_yields(inputs.get(DIVIDENDS), session)
    chosen = chosen.assign(
        spot=spots.reindex(chosen["underlying_id"]).to_numpy(),
        q=yields.reindex(chosen["underlying_id"]).fillna(0.0).to_numpy(),
    )
    priced = dict(tuple(our_deltas(chosen, curve, side.is_call).groupby("underlying_id")))
    with_contracts = set(contracts["underlying_id"])
    rows = []
    for iid in sorted(quoted | set(options["underlying_id"])):
        if iid not in spots.index:
            row: dict[str, object] = {"wing_status": "NO_SPOT"}
        elif iid not in with_contracts:
            row = {"wing_status": "NO_CHAIN"}
        elif iid not in targets.index:
            row = {"wing_status": "NO_EXPIRY"}
        else:
            target = targets[iid]
            row = {"target_expiry": target, "target_dte": (target - session).days}
            row |= wing_row(priced[iid], p, side)
        rows.append({"instrument_id": iid, **row})
    return pd.DataFrame(rows).reindex(columns=columns)
