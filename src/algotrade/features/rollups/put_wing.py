"""``put_wing@v1``: the 8-15 delta puts of the 30-60 day expiry a short-put seller would sell.

The VRP scanner's option-trade follow-up (``docs/screeners/vrp-scanner.md``): per underlying
and session, the expiry closest to ``dte_target`` (45) calendar days among those
``dte_min..dte_max`` (30..60) days out (ties: the earlier), the standard monthlies first when
``prefer_monthly`` (open interest concentrates there; a weekly nearer 45 days is usually
thin), else any listed expiry; and at that expiry the puts whose
OUR delta has ``delta_lo <= |delta| <= delta_hi`` (0.08..0.15, both edges included): how many
strikes, their open interest, volume and median relative spread, and the best of them by
cash-secured return on capital, ROC = premium / (strike x 100) per contract = mid / strike.

Our delta (ADR 0021; the feed's ``delta`` column is a cross-check only): each two-sided put
(bid > 0, ask > bid) at the target expiry has its mid inverted with ``quant.implied_vol``
(``t = days / 365``, ``r`` from the Treasury curve the session sees at ``t``, ``q`` from
``div_yield@v1``, 0 when unknown, ``S`` the underlying quote's price), and its delta is the
Black-Scholes-Merton put delta at that vol (``quant.black_scholes.greeks``). A put without a
two-sided quote or whose inversion fails has no delta: it never qualifies and is counted in
``n_unpriced``.

Inputs: the session's ``chains/option_quotes`` (required), ``rates/treasury`` (required),
``chains/underlying_quotes`` and ``div_yield@v1``. One row per underlying with a chain or an
underlying quote. ``wing_status``, first failing step wins:

    NO_SPOT       no positive underlying price
    NO_CHAIN      no put quotes for the underlying
    NO_EXPIRY     no put expiry dte_min..dte_max days out
    NO_STRIKE     the target expiry has no put with our |delta| in the band
    OK

Ties for the best put: the higher open interest, then the lower strike. Parameters:
``PutWingParams`` (``config/site/rollups.toml ["put_wing@v1"]``). The windows and the band
(45 in 30..60, 0.08..0.15) are named in the feature descriptions and ``best_put_delta``'s
valid range: changing them is a new version, like a window named in a column.
"""

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from algotrade.core.model.options import standard_monthly_expiries
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.iv30 import (  # the same input tables, read the same way
    DIVIDENDS,
    OPTIONS,
    RATES,
    UNDERLYINGS,
)
from algotrade.quant.black_scholes import greeks
from algotrade.quant.implied_vol import IVStatus, implied_vol
from algotrade.quant.rates import DAYS_PER_YEAR, YieldCurve

NAME = "put_wing"
VERSION = 1
STATUSES = ("OK", "NO_SPOT", "NO_CHAIN", "NO_EXPIRY", "NO_STRIKE")

_Q = tuple(f"{OPTIONS}.{c}" for c in ("bid", "ask", "strike", "expiry", "right"))
_PRICING = (*_Q, f"{UNDERLYINGS}.price", f"{RATES}.rate_cont", "div_yield@v1")
_NO_TARGET = "no target expiry (wing_status NO_SPOT, NO_CHAIN or NO_EXPIRY)"
_NO_STRIKE = (
    f"no put with our |delta| in 0.08..0.15 at the target expiry (NO_STRIKE), or {_NO_TARGET}"
)

FEATURES = (
    Feature(
        "wing_status", "str", "category",
        "OK, or the first failing step: NO_SPOT, NO_CHAIN (no puts), NO_EXPIRY (none 30..60 "
        "days out), NO_STRIKE (no put with our |delta| in 0.08..0.15 at the target expiry)",
        "never", "label", categories=STATUSES, inputs=_PRICING,
    ),
    Feature(
        "target_expiry", "date", "date",
        "The put expiry closest to 45 calendar days among those 30..60 days out, standard "
        "monthlies first (ties: the earlier); the best put's expiry",
        _NO_TARGET, "chain", inputs=(f"{OPTIONS}.expiry",),
    ),
    Feature(
        "target_dte", "int", "days",
        "Calendar days from the session to the target expiry (the best put's DTE)",
        _NO_TARGET, "chain", valid_range=(30, 60), inputs=(f"{OPTIONS}.expiry",),
    ),
    Feature(
        "n_strikes", "int", "count",
        "Strikes at the target expiry whose put has our |delta| in 0.08..0.15 (edges included)",
        _NO_TARGET, "chain", valid_range=(0, None), inputs=_PRICING,
    ),
    Feature(
        "n_unpriced", "int", "count",
        "Puts at the target expiry without our delta (no two-sided quote, or the implied-vol "
        "inversion failed): never counted as qualifying",
        _NO_TARGET, "chain", valid_range=(0, None), inputs=_PRICING,
    ),
    Feature(
        "wing_oi", "int", "count", "Open interest across the qualifying puts",
        _NO_STRIKE, "chain", valid_range=(0, None), inputs=(*_PRICING, f"{OPTIONS}.open_interest"),
    ),
    Feature(
        "wing_volume", "int", "count", "Volume across the qualifying puts",
        _NO_STRIKE, "chain", valid_range=(0, None), inputs=(*_PRICING, f"{OPTIONS}.volume"),
    ),
    Feature(
        "wing_spread_pct", "float32", "decimal",
        "Median (ask - bid) / mid across the qualifying puts",
        _NO_STRIKE, "chain", valid_range=(0, 2), inputs=_PRICING,
    ),
    Feature(
        "best_put_strike", "float32", "usd_per_share",
        "The qualifying put with the highest ROC (ties: higher OI, then lower strike): strike",
        _NO_STRIKE, "chain", valid_range=(0, None), inputs=_PRICING,
    ),
    Feature(
        "best_put_delta", "float32", "ratio", "The best put's delta (ours, negative)",
        _NO_STRIKE, "chain", valid_range=(-0.15, -0.08), inputs=_PRICING,
    ),
    Feature(
        "best_put_iv", "float32", "decimal", "The best put's implied vol (ours, from the mid)",
        _NO_STRIKE, "chain", valid_range=(0, 5), inputs=_PRICING,
    ),
    Feature(
        "best_put_mid", "float32", "usd_per_share", "The best put's mid, (bid + ask) / 2",
        _NO_STRIKE, "chain", valid_range=(0, None), inputs=(f"{OPTIONS}.bid", f"{OPTIONS}.ask"),
    ),
    Feature(
        "best_put_oi", "int", "count", "The best put's open interest",
        _NO_STRIKE, "chain", valid_range=(0, None), inputs=(f"{OPTIONS}.open_interest",),
    ),
    Feature(
        "best_put_roc", "float32", "decimal",
        "The best put's cash-secured return on capital: premium / (strike x 100) = mid / strike",
        _NO_STRIKE, "chain", valid_range=(0, 1), inputs=_PRICING,
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


@dataclass(frozen=True)
class PutWingParams:
    dte_target: int = 45
    dte_min: int = 30
    dte_max: int = 60
    delta_lo: float = 0.08  # |delta| band, both edges included
    delta_hi: float = 0.15
    prefer_monthly: bool = True  # standard monthlies in the window first, else any expiry

    def __post_init__(self) -> None:
        if not 1 <= self.dte_min <= self.dte_target <= self.dte_max:
            raise ValueError("need 1 <= dte_min <= dte_target <= dte_max")
        if not 0 < self.delta_lo <= self.delta_hi < 1:
            raise ValueError("need 0 < delta_lo <= delta_hi < 1")


def target_expiries(puts: pd.DataFrame, p: PutWingParams) -> pd.Series:
    """The target expiry per ``underlying_id`` (only underlyings with one): closest to
    ``dte_target`` within ``dte_min..dte_max`` days (standard monthlies first when
    ``prefer_monthly``), ties to the earlier."""
    pairs = puts[["underlying_id", "expiry", "dte"]].drop_duplicates()
    window = pairs[pairs["dte"].between(p.dte_min, p.dte_max)]
    monthly = standard_monthly_expiries(pairs["expiry"].unique()) if p.prefer_monthly else set()
    window = window.assign(
        other=~window["expiry"].isin(monthly), off=(window["dte"] - p.dte_target).abs()
    )
    order = ["underlying_id", "other", "off", "expiry"]
    best = window.sort_values(order).drop_duplicates("underlying_id")
    return best.set_index("underlying_id")["expiry"]


def our_deltas(puts: pd.DataFrame, curve: YieldCurve) -> pd.DataFrame:
    """``puts`` (with ``spot``, ``q``, ``dte``) plus ``mid``, ``iv`` and ``delta``: NaN for a
    put without a two-sided quote or whose inversion fails."""
    bid = puts["bid"].fillna(0).to_numpy(dtype=float)
    ask = puts["ask"].fillna(0).to_numpy(dtype=float)
    two_sided = (bid > 0) & (ask > bid)
    mid = np.where(two_sided, (bid + ask) / 2, np.nan)
    t = puts["dte"].to_numpy(dtype=float) / DAYS_PER_YEAR
    spot, strike = puts["spot"].to_numpy(dtype=float), puts["strike"].to_numpy(dtype=float)
    r, q = curve.rate(t), puts["q"].to_numpy(dtype=float)
    iv = np.full(len(puts), np.nan)
    if two_sided.any():
        k = two_sided
        solved = implied_vol(mid[k], spot[k], strike[k], t[k], r[k], q[k], False)
        iv[k] = np.where(solved.status == IVStatus.OK, solved.iv, np.nan)
    priced = np.isfinite(iv)
    delta = np.full(len(puts), np.nan)
    if priced.any():
        g = greeks(spot[priced], strike[priced], t[priced], r[priced], q[priced], iv[priced], False)
        delta[priced] = g.delta
    return puts.assign(mid=mid, iv=iv, delta=delta)


def wing_row(puts: pd.DataFrame, p: PutWingParams) -> dict[str, object]:
    """The aggregate columns for one underlying from its target expiry's priced puts
    (``strike``, ``bid``, ``ask``, ``mid``, ``iv``, ``delta``, ``open_interest``, ``volume``)."""
    size = puts["delta"].abs()
    row: dict[str, object] = {"n_unpriced": int(puts["delta"].isna().sum())}
    wing = puts[(size >= p.delta_lo) & (size <= p.delta_hi)]
    row["n_strikes"] = int(wing["strike"].nunique())
    if wing.empty:
        return {**row, "wing_status": "NO_STRIKE"}
    oi = wing["open_interest"].fillna(0)
    roc = wing["mid"] / wing["strike"]
    ranked = wing.assign(roc=roc, oi=oi).sort_values(
        ["roc", "oi", "strike"], ascending=[False, False, True]
    )
    best = ranked.iloc[0]
    return {
        **row,
        "wing_status": "OK",
        "wing_oi": int(oi.sum()),
        "wing_volume": int(wing["volume"].fillna(0).sum()),
        "wing_spread_pct": float(((wing["ask"] - wing["bid"]) / wing["mid"]).median()),
        "best_put_strike": float(best["strike"]),
        "best_put_delta": float(best["delta"]),
        "best_put_iv": float(best["iv"]),
        "best_put_mid": float(best["mid"]),
        "best_put_oi": int(best["oi"]),
        "best_put_roc": float(best["roc"]),
    }


def _spots(underlyings: pd.DataFrame | None) -> pd.Series:
    """Positive underlying prices by instrument id."""
    if underlyings is None or underlyings.empty:
        return pd.Series(dtype=float)
    price = pd.to_numeric(underlyings["price"], errors="coerce")
    ids = underlyings["instrument_id"].astype(str)
    return pd.Series(price.to_numpy(dtype=float), index=ids.to_numpy())[lambda s: s > 0]


def _div_yields(rows: pd.DataFrame | None, session: date) -> pd.Series:
    if rows is None:
        return pd.Series(dtype=float)
    today = rows[rows["session_date"] == session]
    return pd.Series(
        today["div_yield"].to_numpy(dtype=float), index=today["instrument_id"].astype(str)
    )


def compute(inputs: Inputs, session: date, p: PutWingParams) -> pd.DataFrame:
    options, curve_rows = inputs[OPTIONS], inputs[RATES]
    assert options is not None and curve_rows is not None  # required inputs
    curve = YieldCurve.from_days(curve_rows["tenor_days"], curve_rows["rate_cont"])
    underlyings = inputs.get(UNDERLYINGS)
    spots = _spots(underlyings)
    quoted = set() if underlyings is None else set(underlyings["instrument_id"].astype(str))
    options = options.assign(underlying_id=options["underlying_id"].astype(str))
    puts = options[options["right"].astype(str) == "P"]
    expiry = pd.to_datetime(puts["expiry"]).dt.date
    puts = puts.assign(expiry=expiry, dte=[(e - session).days for e in expiry])
    targets = target_expiries(puts[puts["underlying_id"].isin(spots.index)], p)
    chosen = puts[puts["expiry"].to_numpy() == targets.reindex(puts["underlying_id"]).to_numpy()]
    yields = _div_yields(inputs.get(DIVIDENDS), session)
    chosen = chosen.assign(
        spot=spots.reindex(chosen["underlying_id"]).to_numpy(),
        q=yields.reindex(chosen["underlying_id"]).fillna(0.0).to_numpy(),
    )
    priced = dict(tuple(our_deltas(chosen, curve).groupby("underlying_id")))
    with_puts = set(puts["underlying_id"])
    rows = []
    for iid in sorted(quoted | set(options["underlying_id"])):
        if iid not in spots.index:
            row: dict[str, object] = {"wing_status": "NO_SPOT"}
        elif iid not in with_puts:
            row = {"wing_status": "NO_CHAIN"}
        elif iid not in targets.index:
            row = {"wing_status": "NO_EXPIRY"}
        else:
            target = targets[iid]
            row = {"target_expiry": target, "target_dte": (target - session).days}
            row |= wing_row(priced[iid], p)
        rows.append({"instrument_id": iid, **row})
    return pd.DataFrame(rows).reindex(columns=["instrument_id", *COLUMNS])


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "The 8-15 delta puts (our delta) of the expiry nearest 45 days: strikes, OI, volume, "
    "spread and the best put by cash-secured ROC",
    (
        Input(OPTIONS),
        Input(RATES),
        Input(UNDERLYINGS, required=False),
        Input(DIVIDENDS, required=False),
    ),
    FEATURES,
    compute,
    PutWingParams(),
)
