"""Replicate Cboe's PUT index from stored option quotes and compare it with the published level
(ADR 0084 decision 6): the trust check on the data and the engine before any evidence from the
bought history is believed. Pure: quotes, rates and levels in, a series and a gap report out.

The strategy (Cboe's published method): on each monthly expiry (the roll) sell the SPX put,
standard (AM-settled, root ``SPX``) series, expiring on the next monthly expiry, whose strike is
the nearest to the index; hold it to expiry; keep the collateral (the strike) and the premium in
T-bills.
Per unit of capital the portfolio at session t is ``((K + P0) * accrual_t - P_t) / K`` against its
value ``K`` at the sale, where ``accrual`` compounds the 3-month rate of the roll day, actual / 360;
at expiry ``P`` is the put's intrinsic value at the index level.

What a close-based file cannot match, and the first pass says so: Cboe sells on a roll-time average
(about 11:30 to 12:00 New York), the stand-in is the 16:00 mid (or bid); an SPX put settles
on the AM opening settlement price (SOQ), the stand-in is the index level at the 16:00 snapshot of
the expiry session; the expiry of a month whose third Friday was a holiday falls on the Thursday,
and before 2015 a monthly contract is dated the Saturday after the roll session. The rate is the
3-month par yield, simple, actual / 360 (Cboe accrues the 3-month auction rate).
"""

import itertools
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

ROOT = "SPX"  # the AM-settled standard series; SPXW (PM-settled) is a different contract
DAY_COUNT = 360.0  # T-bill accrual, actual / 360
EXPIRY_SLACK = 2  # days a contract may be dated after its expiry session (Saturday expiries)


@dataclass(frozen=True)
class Period:
    """One sold put: the roll it was sold on, its expiry and the contract."""

    roll: date
    expiry: date
    contract: str
    strike: float
    premium: float
    spot: float


def put_price(rows: pd.DataFrame, price: str) -> pd.Series:
    """The put's price per row: the two-sided mid (nothing for a one-sided or crossed quote) or
    the bid. The sold put is valued at what it would cost to buy back only for ``ask``; the
    replication stands in for Cboe's roll price, so mid is the default and bid the cautious one."""
    bid, ask = rows["bid"], rows["ask"]
    if price == "bid":
        return bid.where(bid > 0)
    if price == "mid":
        return ((bid + ask) / 2).where((bid > 0) & (ask >= bid))
    raise ValueError(f"price must be 'mid' or 'bid', not {price!r}")


def sell_put(rows: pd.DataFrame, roll: date, expiry: date, price: str) -> Period | None:
    """The put sold on ``roll`` (``rows``: that session's SPX quotes): root SPX, expiring
    ``expiry``, strike nearest the index (the lower strike on a tie), priced as ``price``;
    ``None`` when no put of that expiry has a price. A contract dated up to two days after the
    expiry session is that expiry's: the monthly series expired on the Saturday after the third
    Friday before 2015, and a Good Friday expiry's contract is dated the Friday."""
    window = (rows["expiry"] >= expiry) & (rows["expiry"] <= expiry + timedelta(days=EXPIRY_SLACK))
    puts = rows[(rows["root"] == ROOT) & (rows["right"] == "P") & window].copy()
    if not puts.empty:  # the earliest date in the window: the Saturday, never the next month's
        puts = puts[puts["expiry"] == puts["expiry"].min()]
    puts["price"] = put_price(puts, price)
    puts = puts.dropna(subset=["price"])
    if puts.empty:
        return None
    spot = float(puts["underlying_price"].median())
    gap = (puts["strike"] - spot).abs()
    chosen = puts.loc[gap[gap == gap.min()].index].sort_values("strike").iloc[0]
    return Period(
        roll, expiry, str(chosen["instrument_id"]), float(chosen["strike"]),
        float(chosen["price"]), spot,
    )  # fmt: skip


def replicate(
    quotes: Mapping[date, pd.DataFrame],
    rolls: Sequence[date],
    rate: Mapping[date, float],
    price: str = "mid",
) -> pd.Series:
    """The strategy's level per session from ``rolls[0]`` to ``rolls[-1]``, 1.0 at the first roll.

    ``quotes``: each session's SPX quote rows; ``rolls``: the monthly expiry sessions in order
    (each is the previous put's expiry and the next one's sale); ``rate``: the simple 3-month
    rate of each roll day (a fraction). A session with no price for the held contract carries
    ``NaN`` (never the last price). Raises ``ValueError`` when a roll has no quotes or no put."""
    level: dict[date, float] = {}
    base = 1.0
    for roll, expiry in itertools.pairwise(rolls):
        if roll not in quotes:
            raise ValueError(f"no quotes on the roll {roll}")
        sold = sell_put(quotes[roll], roll, expiry, price)
        if sold is None:
            raise ValueError(f"no priced SPX put expiring {expiry} on the roll {roll}")
        level[roll] = base
        for day in sorted(d for d in quotes if roll < d <= expiry):
            accrual = 1 + rate[roll] * (day - roll).days / DAY_COUNT
            if day == expiry:
                spot = float(quotes[day]["underlying_price"].median())
                value = max(sold.strike - spot, 0.0)
            else:
                held = quotes[day]
                match = held.loc[held["instrument_id"] == sold.contract]
                value = float(put_price(match, price).iloc[0]) if len(match) else np.nan
            level[day] = base * ((sold.strike + sold.premium) * accrual - value) / sold.strike
        base = level.get(expiry, np.nan)
    return pd.Series(level).sort_index()


def compare(simulated: pd.Series, published: pd.Series) -> dict[str, Any]:
    """The gap between the replication and the published level over their common sessions,
    both rebased to 1 at the first: the cumulative return of each and their difference (basis
    points), the RMS and the largest of the daily return differences (basis points) and their
    correlation. A simulated session where either has no level is left out and counted."""
    both = pd.concat({"sim": simulated, "pub": published}, axis=1).dropna()
    skipped = int(len(simulated) - len(both))  # a simulated session with no level on either side
    both = both / both.iloc[0]
    daily = both.pct_change().dropna()
    diff = (daily["sim"] - daily["pub"]) * 1e4
    return {
        "sessions": len(both),
        "start": both.index[0],
        "end": both.index[-1],
        "simulated_return_bp": float((both["sim"].iloc[-1] - 1) * 1e4),
        "published_return_bp": float((both["pub"].iloc[-1] - 1) * 1e4),
        "gap_bp": float((both["sim"].iloc[-1] - both["pub"].iloc[-1]) * 1e4),
        "rms_daily_diff_bp": float(np.sqrt((diff**2).mean())) if len(diff) else float("nan"),
        "max_daily_diff_bp": float(diff.abs().max()) if len(diff) else float("nan"),
        "correlation": float(daily["sim"].corr(daily["pub"])) if len(daily) > 2 else float("nan"),
        "skipped_sessions": skipped,
    }
