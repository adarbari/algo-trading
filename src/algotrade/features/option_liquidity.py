"""``option_liquidity@v1``: how tradeable an underlying's options are for short premium.

Ported from the original ``liquidity_screen.py`` with the same selection rules and tier
thresholds (all configurable through ``LiquidityParams``), plus these fixes:

- DTE is measured from the chain's session date, not the wall-clock date (point-in-time).
- Standard monthly expiries use the exact third-Friday rule (Thursday when Friday is a
  holiday) instead of a day-of-month heuristic.
- Contracts with a missing delta are counted (``<side>_missing_delta``), not silently dropped.
- Exact ties are broken by the lower strike instead of the feed's row order.

Per side (puts and calls scored separately):
  target expiry = standard monthly closest to ``dte_target`` within [dte_min, dte_max];
                  fallback any expiry in that window, then any expiry >= dte_fallback
  short strike  = tightest relative spread with pick_lo <= |delta| <= pick_hi (ties: higher OI);
                  fallback the two-sided quote closest to ``delta_target``
  zone          = all strikes in the target expiry with zone_lo <= |delta| <= zone_hi
"""

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, cast

from algotrade.core.model.options import OptionRight, standard_monthly_expiries

NAME = "option_liquidity"
VERSION = 1

_SIDE_COLUMNS = {
    "tier": "str",
    "strike": "float",
    "delta": "float",
    "bid": "float",
    "ask": "float",
    "spread_abs": "float",
    "spread_pct": "float",
    "strike_oi": "int",
    "zone_oi": "int",
    "zone_vol": "int",
    "missing_delta": "int",
}
COLUMNS: dict[str, str] = {
    "liq_status": "str",
    "chain_oi": "int",
    "chain_volume": "int",
    "expiries_within_60d": "int",
    "target_expiry": "date",
    "target_dte": "int",
    "short_put_ok": "bool",
    "short_call_ok": "bool",
    "underlying_price": "float",
    "iv30": "float",
    "stock_volume": "float",
    "chain_asof": "date",
    **{f"{side}_{col}": kind for side in ("put", "call") for col, kind in _SIDE_COLUMNS.items()},
}


@dataclass(frozen=True)
class TierRule:
    tier: str
    max_spread_pct: float
    max_spread_abs: float
    min_zone_oi: int
    min_chain_oi: int
    min_bid: float


DEFAULT_TIERS = (
    TierRule("A", 0.05, 0.03, 2000, 20000, 0.25),
    TierRule("B", 0.10, 0.05, 500, 5000, 0.15),
    TierRule("C", 0.20, 0.10, 100, 1000, 0.05),
)


@dataclass(frozen=True)
class LiquidityParams:
    dte_target: int = 35
    dte_min: int = 21
    dte_max: int = 60
    dte_fallback: int = 14
    delta_target: float = 0.30
    pick_lo: float = 0.20
    pick_hi: float = 0.40
    zone_lo: float = 0.15
    zone_hi: float = 0.40
    tiers: tuple[TierRule, ...] = DEFAULT_TIERS
    ok_tiers: frozenset[str] = field(default_factory=lambda: frozenset({"A", "B"}))


@dataclass(frozen=True)
class Contract:
    expiry: date
    right: OptionRight
    strike: float
    bid: float
    ask: float
    open_interest: float
    volume: float
    delta: float | None


def _num(value: Any) -> float:
    return (
        0.0 if value is None or (isinstance(value, float) and math.isnan(value)) else float(value)
    )


def _as_date(value: Any) -> date:
    """Parquet may hand back dates as datetime/Timestamp; features always work in ``date``."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def contracts_from_rows(rows: Iterable[Mapping[str, Any]]) -> list[Contract]:
    """Build contracts from stored ``chains/option_quotes`` rows (standard series only)."""
    out = []
    for r in rows:
        delta = r.get("delta")
        missing = delta is None or (isinstance(delta, float) and math.isnan(delta))
        out.append(
            Contract(
                expiry=_as_date(r["expiry"]),
                right=OptionRight(r["right"]),
                strike=float(r["strike"]),
                bid=_num(r.get("bid")),
                ask=_num(r.get("ask")),
                open_interest=_num(r.get("open_interest")),
                volume=_num(r.get("volume")),
                delta=None if missing else float(cast(float, delta)),
            )
        )
    return out


def choose_target_expiry(
    expiries: Iterable[date], session: date, p: LiquidityParams
) -> date | None:
    listed = sorted(set(expiries))
    dte = {e: (e - session).days for e in listed}
    monthly = standard_monthly_expiries(listed)
    in_window = [e for e in listed if p.dte_min <= dte[e] <= p.dte_max]
    candidates = (
        [e for e in in_window if e in monthly]
        or in_window
        or [e for e in listed if dte[e] >= p.dte_fallback]
    )
    if not candidates:
        return None
    return min(candidates, key=lambda e: (abs(dte[e] - p.dte_target), e))


def _spread_pct(c: Contract) -> float:
    return (c.ask - c.bid) / ((c.ask + c.bid) / 2)


def assess_side(contracts: list[Contract], p: LiquidityParams) -> dict[str, Any]:
    """Metrics for one side of the target expiry (contracts already filtered to it)."""
    with_delta = [c for c in contracts if c.delta is not None and c.delta != 0]
    out: dict[str, Any] = {"missing_delta": sum(1 for c in contracts if c.delta is None)}
    zone = [c for c in with_delta if p.zone_lo <= abs(c.delta or 0) <= p.zone_hi]
    out["zone_oi"] = int(sum(c.open_interest for c in zone))
    out["zone_vol"] = int(sum(c.volume for c in zone))
    quoted = [c for c in with_delta if c.bid > 0 and c.ask > c.bid]
    band = [c for c in quoted if p.pick_lo <= abs(c.delta or 0) <= p.pick_hi]
    if band:
        pick = min(band, key=lambda c: (_spread_pct(c), -c.open_interest, c.strike))
    elif quoted:
        pick = min(quoted, key=lambda c: (abs(abs(c.delta or 0) - p.delta_target), c.strike))
    else:
        return out
    out.update(
        strike=pick.strike,
        delta=round(pick.delta or 0, 3),
        bid=pick.bid,
        ask=pick.ask,
        spread_abs=round(pick.ask - pick.bid, 2),
        spread_pct=round(_spread_pct(pick), 4),
        strike_oi=int(pick.open_interest),
    )
    return out


def tier_for(side: Mapping[str, Any], chain_oi: int, p: LiquidityParams) -> str:
    if "bid" not in side:
        return "D"
    for rule in p.tiers:
        tight = (
            side["spread_pct"] <= rule.max_spread_pct or side["spread_abs"] <= rule.max_spread_abs
        )
        if (
            tight
            and side["zone_oi"] >= rule.min_zone_oi
            and chain_oi >= rule.min_chain_oi
            and side["bid"] >= rule.min_bid
        ):
            return rule.tier
    return "D"


def assess(contracts: list[Contract], session: date, p: LiquidityParams) -> dict[str, Any]:
    """The full feature row for one underlying. ``contracts`` are standard series only."""
    if not contracts:
        return {"liq_status": "NO_STANDARD_SERIES", "put_tier": "D", "call_tier": "D"}
    expiries = {c.expiry for c in contracts}
    row: dict[str, Any] = {
        "liq_status": "OK",
        "chain_oi": int(sum(c.open_interest for c in contracts)),
        "chain_volume": int(sum(c.volume for c in contracts)),
        "expiries_within_60d": sum(1 for e in expiries if 0 <= (e - session).days <= 60),
    }
    target = choose_target_expiry(expiries, session, p)
    if target is None:
        return {**row, "liq_status": "NO_TARGET_EXPIRY", "put_tier": "D", "call_tier": "D"}
    row.update(target_expiry=target, target_dte=(target - session).days)
    for right, name in ((OptionRight.PUT, "put"), (OptionRight.CALL, "call")):
        side = assess_side([c for c in contracts if c.expiry == target and c.right is right], p)
        row[f"{name}_tier"] = tier_for(side, row["chain_oi"], p)
        row.update({f"{name}_{k}": v for k, v in side.items()})
    row["short_put_ok"] = row["put_tier"] in p.ok_tiers
    row["short_call_ok"] = row["call_tier"] in p.ok_tiers
    return row
