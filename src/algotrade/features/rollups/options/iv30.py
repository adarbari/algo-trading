"""``iv30@v1``: our own 30-calendar-day at-the-money implied volatility (ADR 0021, IV30).

Inputs: the session's ``chains/option_quotes`` and ``chains/underlying_quotes``, the Treasury
curve the session sees (``rates/treasury``) and ``div_yield@v1`` (the expression feature
``div_yield``, materialised; a missing yield prices with ``q = 0``). One row per underlying
with a chain or an underlying quote.

Method, per underlying (all thresholds are ``Iv30Params``, ``rollups.toml ["iv30@v1"]``):

1. Expiries: among those ``min_days..max_days`` calendar days out, the latest at or before
   ``target_days`` and the earliest at or after it, from the standard monthlies when they
   bracket the target, else from every listed expiry; else the single expiry nearest the
   target (flat vol, ``SINGLE_EXPIRY``).
2. Per expiry, ``t = days / 365``, ``r`` from the curve at ``t``, ``F = S e^{(r - q) t}``
   (``S``: the underlying quote's price), and the two listed strikes around ``F`` (the
   highest at or below, the lowest above).
3. Each call and put at those strikes passes the quality filters (bid > 0, ask > bid,
   (ask - bid) / mid <= ``max_spread_pct``, open interest >= ``min_open_interest`` or volume
   >= ``min_volume``) and its mid is inverted with ``quant.implied_vol``.
4. Per strike, the call and put vols are averaged; the two strikes are interpolated linearly
   to ``F``; the result is the expiry's ATM vol.
5. The two expiries are interpolated linearly in total variance ``sigma^2 t`` to
   ``target_days`` (``quant.implied_vol.interpolate_total_variance``). One usable expiry
   gives its vol unchanged (``SINGLE_EXPIRY``).

Columns: ``iv30`` (ours, decimal), ``iv30_cboe`` (the feed's ``iv30``, a percentage, as a
decimal), ``iv30_status``, ``near_expiry``, ``far_expiry``, ``atm_strike_near``, ``spot``,
``rate`` (continuous, at ``target_days``), ``div_yield`` (as read; null when unknown),
``n_quotes_used`` (vols averaged across both expiries). ``iv30`` is non-null exactly when
the status is ``OK`` or ``SINGLE_EXPIRY``. Statuses, first failing step wins:

    NO_SPOT       no positive underlying price
    NO_CHAIN      no option quotes for the underlying
    NO_EXPIRY     no expiry within min_days..max_days
    NO_QUOTES     no two-sided quote (bid > 0, ask > bid) at the strikes around F
    WIDE_SPREADS  two-sided, but every spread is wider than max_spread_pct of mid
    ILLIQUID      tight enough, but below both the open interest and volume minimums
    IV_FAILED     every inversion failed (``quant.implied_vol`` status, e.g. BELOW_INTRINSIC)
"""

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from algotrade.core.model.options import standard_monthly_expiries
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.quant.implied_vol import IVStatus, implied_vol, interpolate_total_variance
from algotrade.quant.rates import DAYS_PER_YEAR, YieldCurve

NAME = "iv30"
VERSION = 1
OPTIONS = "chains/option_quotes"
UNDERLYINGS = "chains/underlying_quotes"
RATES = "rates/treasury"
DIVIDENDS = "rollups/instrument/div_yield@v1"  # the materialised expression feature
# Expiry-level failures, most informative last: an underlying reports the worst it reached.
FAILURES = ("NO_QUOTES", "WIDE_SPREADS", "ILLIQUID", "IV_FAILED")
# Statuses where the chain is too thin to price (ADR 0041): the read says ILLIQUID for a null
# ``iv30`` with one of these; the other statuses (NO_CHAIN, NO_SPOT, IV_FAILED...) stay NULL.
ILLIQUID_STATUSES = frozenset({"NO_QUOTES", "WIDE_SPREADS", "ILLIQUID"})

_STATUSES = (
    "OK", "SINGLE_EXPIRY", "NO_SPOT", "NO_CHAIN", "NO_EXPIRY", "NO_QUOTES", "WIDE_SPREADS",
    "ILLIQUID", "IV_FAILED",
)  # fmt: skip
_QUOTES = tuple(f"{OPTIONS}.{c}" for c in ("bid", "ask", "strike", "expiry", "open_interest"))
_SPOT = f"{UNDERLYINGS}.price"
_NO_EXPIRY = "no expiry was selected (NO_SPOT, NO_CHAIN or NO_EXPIRY)"

FEATURES = (
    Feature(
        "iv30", "float", "decimal",
        "Our 30-calendar-day at-the-money implied volatility: forward ATM vols of the two "
        "expiries around 30 days, interpolated in total variance (ADR 0021)",
        "iv30_status is neither OK nor SINGLE_EXPIRY (the status says why)", "chain",
        valid_range=(0, 5), null_status="iv30_status",
        illiquid_statuses=tuple(sorted(ILLIQUID_STATUSES)),
        inputs=(*_QUOTES, _SPOT, f"{RATES}.rate_cont", "div_yield@v1"),
    ),
    Feature(
        "iv30_cboe", "float", "decimal", "The feed's 30-day implied volatility, as a decimal",
        "no underlying quote for it, or the feed gives no IV30", "chain", valid_range=(0, 5),
        inputs=(f"{UNDERLYINGS}.iv30",),
    ),
    Feature(
        "iv30_status", "str", "category",
        "Why iv30 has a value or not; the first failing step wins (SINGLE_EXPIRY: one usable "
        "expiry, flat vol, still a value)",
        "never", "label", categories=_STATUSES, inputs=(*_QUOTES, _SPOT),
    ),
    Feature(
        "near_expiry", "date", "date",
        "The selected expiry at or before 30 days out (standard monthlies first, 7..90 days)",
        f"no expiry in 7..90 days at or before the target, or {_NO_EXPIRY}", "chain",
        inputs=(f"{OPTIONS}.expiry",),
    ),
    Feature(
        "far_expiry", "date", "date",
        "The selected expiry at or after 30 days out (standard monthlies first, 7..90 days)",
        f"no expiry in 7..90 days at or after the target, or {_NO_EXPIRY}", "chain",
        inputs=(f"{OPTIONS}.expiry",),
    ),
    Feature(
        "atm_strike_near", "float", "usd_per_share",
        "The listed strike nearest the forward in the near expiry (the far one without a near)",
        _NO_EXPIRY, "chain", valid_range=(0, None), inputs=(f"{OPTIONS}.strike", _SPOT),
    ),
    Feature(
        "spot", "float", "usd_per_share", "The underlying's price captured with the chain",
        "no positive underlying price (NO_SPOT)", "chain", valid_range=(0, None),
        inputs=(_SPOT,),
    ),
    Feature(
        "rate", "float", "decimal",
        "Continuous risk-free rate at 30 days, from the Treasury curve the session sees",
        "never (the curve is a required input)", "chain",
        valid_range=(-0.05, 0.25), inputs=(f"{RATES}.rate_cont",),
    ),
    Feature(
        "div_yield", "float", "decimal",
        "The dividend yield q used for the forward, as read from div_yield@v1",
        "div_yield@v1 has no yield for it (UNKNOWN; priced with q = 0)", "expression",
        valid_range=(0, 1), inputs=("div_yield@v1",),
    ),
    Feature(
        "n_quotes_used", "int", "count",
        "Option quotes whose implied vols were averaged, across both expiries",
        "never (0 when none)", "chain", valid_range=(0, None), inputs=_QUOTES,
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


@dataclass(frozen=True)
class Iv30Params:
    target_days: int = 30
    min_days: int = 7  # nearer expiries are left out (pin risk, noisy vols)
    max_days: int = 90
    max_spread_pct: float = 0.35  # (ask - bid) / mid
    min_open_interest: int = 10  # a quote passes with this open interest ...
    min_volume: int = 1  # ... or this volume

    def __post_init__(self) -> None:
        if not 1 <= self.min_days <= self.target_days <= self.max_days:
            raise ValueError("need 1 <= min_days <= target_days <= max_days")
        if self.max_spread_pct <= 0:
            raise ValueError("max_spread_pct must be > 0")


def choose_expiries(
    expiries: list[date], session: date, p: Iv30Params, monthly: set[date]
) -> tuple[date | None, date | None]:
    """``(near, far)`` bracketing the target (equal when one expiry is exactly on it), or
    the single expiry nearest the target in the near or far slot, or ``(None, None)``."""
    days = {e: (e - session).days for e in expiries}
    listed = sorted(e for e in set(expiries) if p.min_days <= days[e] <= p.max_days)

    def bracket(candidates: list[date]) -> tuple[date | None, date | None]:
        near = [e for e in candidates if days[e] <= p.target_days]
        far = [e for e in candidates if days[e] >= p.target_days]
        return (near[-1] if near else None, far[0] if far else None)

    for candidates in ([e for e in listed if e in monthly], listed):
        near, far = bracket(candidates)
        if near is not None and far is not None:
            return near, far
    if not listed:
        return None, None
    single = min(listed, key=lambda e: (abs(days[e] - p.target_days), e))
    return (single, None) if days[single] <= p.target_days else (None, single)


def _selected(options: pd.DataFrame, session: date, p: Iv30Params) -> pd.DataFrame:
    """``underlying_id``, ``expiry``, ``role`` (near / far) for every chain."""
    pairs = options[["underlying_id", "expiry"]].drop_duplicates()
    monthly = standard_monthly_expiries(pairs["expiry"].unique())
    rows = []
    for uid, group in pairs.groupby("underlying_id", sort=True):
        near, far = choose_expiries(list(group["expiry"]), session, p, monthly)
        rows += [(uid, e, role) for e, role in ((near, "near"), (far, "far")) if e is not None]
    return pd.DataFrame(rows, columns=["underlying_id", "expiry", "role"])


def _around_forward(quotes: pd.DataFrame) -> pd.DataFrame:
    """The rows at the highest strike at or below ``forward`` and the lowest above it."""
    key = ["underlying_id", "expiry"]
    below = quotes[quotes["strike"] <= quotes["forward"]].groupby(key)["strike"].max()
    above = quotes[quotes["strike"] > quotes["forward"]].groupby(key)["strike"].min()
    bounds = pd.DataFrame({"k_lo": below, "k_hi": above}).reset_index()
    out = quotes.merge(bounds, on=key, how="left")
    return out[(out["strike"] == out["k_lo"]) | (out["strike"] == out["k_hi"])]


def _vols(quotes: pd.DataFrame, p: Iv30Params) -> pd.DataFrame:
    """Quality flags and the implied vol of each quote's mid (NaN when filtered / failed)."""
    bid = quotes["bid"].fillna(0).to_numpy(dtype=float)
    ask = quotes["ask"].fillna(0).to_numpy(dtype=float)
    mid = (bid + ask) / 2
    two_sided = (bid > 0) & (ask > bid)
    with np.errstate(divide="ignore", invalid="ignore"):
        tight = two_sided & ((ask - bid) / mid <= p.max_spread_pct)
    active = (quotes["open_interest"].fillna(0).to_numpy() >= p.min_open_interest) | (
        quotes["volume"].fillna(0).to_numpy() >= p.min_volume
    )
    usable = tight & active
    solved = implied_vol(
        mid[usable],
        quotes["spot"].to_numpy(dtype=float)[usable],
        quotes["strike"].to_numpy(dtype=float)[usable],
        quotes["t"].to_numpy(dtype=float)[usable],
        quotes["r"].to_numpy(dtype=float)[usable],
        quotes["q"].to_numpy(dtype=float)[usable],
        (quotes["right"].astype(str) == "C").to_numpy()[usable],
    )
    iv = np.full(len(quotes), np.nan)
    iv[usable] = np.where(solved.status == IVStatus.OK, solved.iv, np.nan)
    return quotes.assign(two_sided=two_sided, tight=tight, usable=usable, iv=iv)


def expiry_vols(quotes: pd.DataFrame, p: Iv30Params) -> pd.DataFrame:
    """Per (underlying, expiry): ``atm_iv``, ``status``, ``atm_strike``, ``n_used``.

    ``quotes`` carry ``spot``, ``t``, ``r``, ``q`` and ``forward`` per row (``iv30.compute``)."""
    rows = _vols(_around_forward(quotes), p)
    key = ["underlying_id", "expiry"]
    per_strike = rows.groupby([*key, "strike"], as_index=False).agg(
        iv=("iv", "mean"), forward=("forward", "first"), n_used=("iv", "count")
    )
    ok = per_strike.dropna(subset=["iv"])
    distance = (ok["strike"] - ok["forward"]).abs()
    weight = 1.0 / np.maximum(distance.to_numpy(), 1e-9)  # two strikes: linear in strike
    ok = ok.assign(w=weight, wiv=weight * ok["iv"])
    atm = ok.groupby(key).agg(w=("w", "sum"), wiv=("wiv", "sum"), n_used=("n_used", "sum"))
    atm["atm_iv"] = atm["wiv"] / atm["w"]
    nearest = per_strike.assign(d=(per_strike["strike"] - per_strike["forward"]).abs())
    nearest = nearest.sort_values([*key, "d", "strike"]).drop_duplicates(key)
    flags = rows.groupby(key).agg(
        two_sided=("two_sided", "any"), tight=("tight", "any"), usable=("usable", "any")
    )
    out = nearest.set_index(key)[["strike"]].rename(columns={"strike": "atm_strike"})
    out = out.join(flags).join(atm[["atm_iv", "n_used"]])
    out["status"] = np.select(
        [
            out["atm_iv"].notna(),
            ~out["two_sided"].astype(bool),
            ~out["tight"].astype(bool),
            ~out["usable"].astype(bool),
        ],
        ["OK", "NO_QUOTES", "WIDE_SPREADS", "ILLIQUID"],
        "IV_FAILED",
    )
    out["n_used"] = out["n_used"].fillna(0).astype(int)
    return out.reset_index()[[*key, "atm_iv", "status", "atm_strike", "n_used"]]


def _as_dates(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values).dt.date


def _by_id(underlyings: pd.DataFrame, values: pd.Series) -> pd.Series:
    """``values`` (one per row) by instrument id (str): for an id quoted twice, the row with
    the latest ``ts`` (ties: the later row), so the result does not depend on staging order."""
    frame = pd.DataFrame(
        {"id": underlyings["instrument_id"].astype(str).to_numpy(), "value": values.to_numpy()}
    )
    if "ts" in underlyings.columns:
        frame = frame.iloc[pd.to_datetime(underlyings["ts"]).argsort(kind="stable").to_numpy()]
    out = frame.drop_duplicates("id", keep="last").set_index("id")["value"]
    out.index.name = None
    return out


def spot_prices(underlyings: pd.DataFrame | None) -> pd.Series:
    """The spot captured with the chain (``chains/underlying_quotes.price``) by underlying id,
    NaN unless positive; an id quoted twice keeps its latest row. The shared spot reader of
    ``put_wing@v1`` and ``oi_walls@v1`` (via ``positive_spots``); ``option_liquidity@v1`` still
    reads ``price`` on its own."""
    if underlyings is None or underlyings.empty:
        return pd.Series(dtype=float)
    price = pd.to_numeric(underlyings["price"], errors="coerce")
    return _by_id(underlyings, price.where(price > 0).astype(float))


def positive_spots(underlyings: pd.DataFrame | None) -> pd.Series:
    """``spot_prices`` of the underlyings with a positive price only."""
    return spot_prices(underlyings).dropna()


def _spots(underlyings: pd.DataFrame | None) -> pd.DataFrame:
    """``instrument_id``, ``spot`` (``spot_prices``), ``iv30_cboe`` (decimal)."""
    if underlyings is None or underlyings.empty:
        return pd.DataFrame({"instrument_id": [], "spot": [], "iv30_cboe": []}, dtype=float)
    spot = spot_prices(underlyings)
    cboe = _by_id(underlyings, pd.to_numeric(underlyings["iv30"], errors="coerce") / 100.0)
    return pd.DataFrame(
        {
            "instrument_id": spot.index.to_numpy(),
            "spot": spot.to_numpy(),
            "iv30_cboe": cboe.to_numpy(),
        }
    )


def _yields(dividends: pd.DataFrame | None, session: date) -> pd.Series:
    if dividends is None:
        return pd.Series(dtype=float)
    today = dividends[dividends["session_date"] == session]
    return today.set_index(today["instrument_id"].astype(str))["div_yield"].astype(float)


def term_vol(
    near: tuple[float, float] | None, far: tuple[float, float] | None, t_target: float
) -> tuple[float, str]:
    """iv30 and its status from the usable ``(t, atm_iv)`` of the near / far expiry."""
    if near is not None and far is not None:
        iv = float(interpolate_total_variance(near[0], near[1], far[0], far[1], t_target))
        return (iv, "OK") if np.isfinite(iv) else (np.nan, "IV_FAILED")
    if near is not None or far is not None:
        return float((near or far)[1]), "SINGLE_EXPIRY"  # type: ignore[index]
    return np.nan, "NO_EXPIRY"


def _row(chain: pd.DataFrame | None, session: date, t_target: float) -> dict[str, object]:
    """The term columns for one underlying from its selected expiries' vols."""
    if chain is None or chain.empty:
        return {"iv30_status": "NO_EXPIRY", "n_quotes_used": 0}
    by_role = {r["role"]: r for r in chain.to_dict("records")}
    usable = {
        role: ((r["expiry"] - session).days / DAYS_PER_YEAR, float(r["atm_iv"]))
        for role, r in by_role.items()
        if r["status"] == "OK"
    }
    iv, status = term_vol(usable.get("near"), usable.get("far"), t_target)
    if not usable:  # every selected expiry failed: report the furthest step reached
        status = max((str(r["status"]) for r in by_role.values()), key=FAILURES.index)
    first = by_role.get("near", by_role.get("far"))
    assert first is not None
    return {
        "iv30": iv,
        "iv30_status": status,
        "near_expiry": by_role["near"]["expiry"] if "near" in by_role else None,
        "far_expiry": by_role["far"]["expiry"] if "far" in by_role else None,
        "atm_strike_near": first["atm_strike"],
        "n_quotes_used": int(
            sum({r["expiry"]: int(r["n_used"]) for r in by_role.values()}.values())
        ),
    }


def compute(inputs: Inputs, session: date, p: Iv30Params) -> pd.DataFrame:
    options, curve_rows = inputs[OPTIONS], inputs[RATES]
    assert options is not None and curve_rows is not None  # required inputs
    curve = YieldCurve.from_days(curve_rows["tenor_days"], curve_rows["rate_cont"])
    t_target = p.target_days / DAYS_PER_YEAR
    spots = _spots(inputs.get(UNDERLYINGS)).set_index("instrument_id")
    options = options.assign(
        underlying_id=options["underlying_id"].astype(str), expiry=_as_dates(options["expiry"])
    )
    ids = sorted(set(spots.index) | set(options["underlying_id"]))
    out = spots.reindex(ids)
    out["div_yield"] = _yields(inputs.get(DIVIDENDS), session).reindex(ids)
    out["rate"] = float(curve.rate(t_target))
    priced = options[options["underlying_id"].isin(out.index[out["spot"].notna()])]
    chosen = _selected(priced, session, p)
    quotes = priced.merge(chosen[["underlying_id", "expiry"]].drop_duplicates())
    t = np.array([(e - session).days for e in quotes["expiry"]], dtype=float) / DAYS_PER_YEAR
    spot = out["spot"].reindex(quotes["underlying_id"]).to_numpy(dtype=float)
    q = out["div_yield"].reindex(quotes["underlying_id"]).fillna(0.0).to_numpy(dtype=float)
    r = curve.rate(t)
    quotes = quotes.assign(spot=spot, t=t, r=r, q=q, forward=spot * np.exp((r - q) * t))
    vols = chosen.merge(expiry_vols(quotes, p), on=["underlying_id", "expiry"], how="left")
    vols = vols.fillna({"status": "NO_QUOTES", "n_used": 0})
    chains = dict(tuple(vols.groupby("underlying_id"))) if len(vols) else {}
    with_chain = set(options["underlying_id"])
    no_spot = set(out.index[out["spot"].isna()])
    rows = []
    for iid in ids:
        if iid in no_spot:
            rows.append({"iv30_status": "NO_SPOT", "n_quotes_used": 0})
        elif iid not in with_chain:
            rows.append({"iv30_status": "NO_CHAIN", "n_quotes_used": 0})
        else:
            rows.append(_row(chains.get(iid), session, t_target))
    terms = pd.DataFrame(rows, index=pd.Index(ids, name="instrument_id"))
    return out.join(terms).reset_index().reindex(columns=["instrument_id", *COLUMNS])


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "Our 30-day ATM implied vol (forward ATM, put/call mid IVs, total-variance term "
    "interpolation) beside Cboe's, with a status code",
    (
        Input(OPTIONS),
        Input(RATES),
        Input(UNDERLYINGS, required=False),
        Input(DIVIDENDS, required=False),
    ),
    FEATURES,
    compute,
    Iv30Params(),
    applies_to="optionable",
)
