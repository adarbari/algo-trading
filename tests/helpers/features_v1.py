"""Reference copies of the v1 definitions that moved to expression features (ADR 0023 step 3):
the ``liquidity_class@v1`` rule as it was computed, and the v1 formulas of the moved numeric
columns. Equivalence tests compare the site's expression features with these."""

from datetime import date

import numpy as np
import pandas as pd

HIGH = {"adv": 100e6, "price": 10.0, "tiers": ("A",), "oi": 50_000, "volume": 5_000}
MEDIUM = {"adv": 10e6, "price": 5.0, "tiers": ("A", "B"), "oi": 5_000, "volume": 0}
KNOWN_CHAIN = frozenset({"OK", "NO_CHAIN", "NO_STANDARD_SERIES", "NO_TARGET_EXPIRY"})
TIER_ORDER = "ABCD"


def _and(*terms: np.ndarray) -> np.ndarray:
    stacked = np.vstack(terms)
    false = (stacked == 0).any(axis=0)
    unknown = np.isnan(stacked).any(axis=0)
    return np.where(false, 0.0, np.where(unknown, np.nan, 1.0))


def _at_least(values: np.ndarray, minimum: float) -> np.ndarray:
    if minimum <= 0:
        return np.ones(len(values))
    return np.where(np.isnan(values), np.nan, (values >= minimum).astype(float))


def options_v1(rows: pd.DataFrame | None, session: date, ids: list[str]) -> pd.DataFrame:
    """``option_tier``, ``chain_oi``, ``chain_volume`` per instrument, as v1 derived them."""
    unknown = pd.DataFrame(
        {"option_tier": None, "chain_oi": np.nan, "chain_volume": np.nan}, index=ids
    )
    if rows is None:
        return unknown
    today = rows[rows["session_date"] == session].set_index("instrument_id")
    known = today[today["liq_status"].astype(str).isin(KNOWN_CHAIN)]
    worse = [
        max(str(a) if pd.notna(a) else "D", str(b) if pd.notna(b) else "D", key=TIER_ORDER.index)
        for a, b in zip(known["put_tier"], known["call_tier"], strict=True)
    ]
    out = pd.DataFrame(
        {
            "option_tier": worse,
            "chain_oi": known["chain_oi"].astype(float).fillna(0.0).to_numpy(),
            "chain_volume": known["chain_volume"].astype(float).fillna(0.0).to_numpy(),
        },
        index=known.index.astype(str),
    )
    unlisted = [i for i in ids if i not in today.index]
    none = pd.DataFrame({"option_tier": "D", "chain_oi": 0.0, "chain_volume": 0.0}, index=unlisted)
    return pd.concat([out, none]).reindex(ids)


def liquidity_class_v1(
    stats: pd.DataFrame, options: pd.DataFrame | None, session: date
) -> pd.Series:
    """``liquidity_class`` by instrument for one session's ``price_stats`` rows."""
    today = stats[stats["session_date"] == session]
    ids = list(today["instrument_id"].astype(str))
    frame = today.set_index(today["instrument_id"].astype(str))[["adv_usd_20d", "close"]]
    frame = frame.join(options_v1(options, session, ids))
    tier = frame["option_tier"]
    met = {}
    for name, p in (("high", HIGH), ("medium", MEDIUM)):
        tier_ok = np.where(tier.notna().to_numpy(), tier.isin(p["tiers"]).to_numpy(), np.nan)
        met[name] = _and(
            _at_least(frame["adv_usd_20d"].to_numpy(dtype=float), p["adv"]),
            _at_least(frame["close"].to_numpy(dtype=float), p["price"]),
            tier_ok.astype(float),
            _at_least(frame["chain_oi"].to_numpy(dtype=float), p["oi"]),
            _at_least(frame["chain_volume"].to_numpy(dtype=float), p["volume"]),
        )
    high, medium = met["high"], met["medium"]
    classes = np.select(
        [high == 1, np.isnan(high), medium == 1, np.isnan(medium)],
        ["HIGH", "UNKNOWN", "MEDIUM", "UNKNOWN"],
        "LOW",
    )
    return pd.Series(classes, index=frame.index, name="liquidity_class")


def moved_numbers_v1(frame: pd.DataFrame) -> pd.DataFrame:
    """The v1 formulas of the moved numeric columns over float64 inputs (``close``,
    ``high_52w``, ``low_52w``, ``hv30``, ``iv30``, ``div_ttm``, ``shares_outstanding``,
    ``market_cap_status``)."""
    close = frame["close"].to_numpy(dtype=float)
    hv = frame["hv30"].to_numpy(dtype=float)
    iv = frame["iv30"].to_numpy(dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return pd.DataFrame(
            {
                "pct_from_high_52w": close / frame["high_52w"].to_numpy(dtype=float) - 1.0,
                "pct_from_low_52w": close / frame["low_52w"].to_numpy(dtype=float) - 1.0,
                "iv_hv_spread": iv - hv,
                "iv_hv_ratio": np.where(hv > 0, iv / hv, np.nan),
                "div_yield": np.where(
                    close > 0, frame["div_ttm"].to_numpy(dtype=float) / close, np.nan
                ),
                "market_cap": np.where(
                    frame["market_cap_status"] == "OK",
                    frame["shares_outstanding"].to_numpy(dtype=float) * close,
                    np.nan,
                ),
            },
            index=frame.index,
        )
