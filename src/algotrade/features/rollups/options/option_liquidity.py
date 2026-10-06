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

Inputs: the session's ``chains/status`` (required: one row per underlying fetched),
``chains/option_quotes`` and ``chains/underlying_quotes``. Parameters: the scalar fields of
``LiquidityParams`` in ``config/site/rollups.toml ["option_liquidity@v1"]``; the tier table is
part of the v1 definition.
"""

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, cast

import pandas as pd

from algotrade.core.model.options import OptionRight, standard_monthly_expiries
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature

NAME = "option_liquidity"
VERSION = 1

_Q = "chains/option_quotes"
_U = "chains/underlying_quotes"
_STATUS = "chains/status.status"
_CONTRACTS = tuple(f"{_Q}.{c}" for c in ("expiry", "strike", "right", "open_interest", "volume"))
_PICK = tuple(f"{_Q}.{c}" for c in ("bid", "ask", "delta", "strike", "open_interest"))
_NO_CHAIN = "no standard-series contracts (NO_STANDARD_SERIES), or the chain fetch failed"
_NO_TARGET = "no target expiry (NO_TARGET_EXPIRY), no standard series, or the fetch failed"
_NO_QUOTE = "no underlying quote captured with the session's chain"
_TIERS = ("A", "B", "C", "D")


def _side(side: str) -> tuple[Feature, ...]:
    """The per-side features (puts and calls are scored separately)."""
    no_pick = f"no two-sided {side} quote with a delta at the target expiry; or {_NO_TARGET}"
    delta = (-1.0, 0.0) if side == "put" else (0.0, 1.0)
    return (
        Feature(
            f"{side}_tier", "str", "category",
            f"Short-{side} tier: the first of A..C whose spread, zone OI, chain OI and bid "
            "limits the short strike meets, else D (not tradeable)",
            "never", "label", categories=_TIERS, inputs=(*_PICK, f"{_Q}.volume"),
        ),
        Feature(
            f"{side}_strike", "float", "usd_per_share",
            f"The short {side} strike: tightest relative spread with 0.20 <= |delta| <= 0.40 "
            "(ties: higher OI), else the two-sided quote nearest |delta| 0.30",
            no_pick, "chain", valid_range=(0, None), inputs=_PICK,
        ),
        Feature(
            f"{side}_delta", "float", "ratio", "The short strike's delta (the feed's, 3 places)",
            no_pick, "chain", valid_range=delta, inputs=(f"{_Q}.delta",),
        ),
        Feature(
            f"{side}_bid", "float", "usd_per_share", "The short strike's bid",
            no_pick, "chain", valid_range=(0, None), inputs=(f"{_Q}.bid",),
        ),
        Feature(
            f"{side}_ask", "float", "usd_per_share", "The short strike's ask",
            no_pick, "chain", valid_range=(0, None), inputs=(f"{_Q}.ask",),
        ),
        Feature(
            f"{side}_spread_abs", "float", "usd_per_share", "ask - bid at the short strike",
            no_pick, "chain", valid_range=(0, None), inputs=(f"{_Q}.bid", f"{_Q}.ask"),
        ),
        Feature(
            f"{side}_spread_pct", "float", "decimal", "(ask - bid) / mid at the short strike",
            no_pick, "chain", valid_range=(0, 2), inputs=(f"{_Q}.bid", f"{_Q}.ask"),
        ),
        Feature(
            f"{side}_strike_oi", "int", "count", "Open interest at the short strike",
            no_pick, "chain", valid_range=(0, None), inputs=(f"{_Q}.open_interest",),
        ),
        Feature(
            f"{side}_zone_oi", "int", "count",
            f"Open interest of the target expiry's {side}s with 0.15 <= |delta| <= 0.40",
            _NO_TARGET, "chain", valid_range=(0, None), inputs=_CONTRACTS,
        ),
        Feature(
            f"{side}_zone_vol", "int", "count",
            f"Volume of the target expiry's {side}s with 0.15 <= |delta| <= 0.40",
            _NO_TARGET, "chain", valid_range=(0, None), inputs=_CONTRACTS,
        ),
        Feature(
            f"{side}_missing_delta", "int", "count",
            f"The target expiry's {side}s without a delta (counted, not dropped)",
            _NO_TARGET, "chain", valid_range=(0, None), inputs=(f"{_Q}.delta",),
        ),
    )  # fmt: skip


FEATURES = (
    Feature(
        "liq_status", "str", "category",
        "OK, NO_STANDARD_SERIES, NO_TARGET_EXPIRY, or the chain fetch status when it failed "
        "(NO_CHAIN, STALE_DATA: ..., FETCH_ERROR, NOT_ATTEMPTED)",
        "never", "label", inputs=(_STATUS, *_CONTRACTS),
    ),
    Feature(
        "chain_oi", "int", "count", "Open interest across every standard-series contract",
        _NO_CHAIN, "chain", valid_range=(0, None), inputs=(f"{_Q}.open_interest",),
    ),
    Feature(
        "chain_volume", "int", "count", "Volume across every standard-series contract",
        _NO_CHAIN, "chain", valid_range=(0, None), inputs=(f"{_Q}.volume",),
    ),
    Feature(
        "expiries_within_60d", "int", "count", "Listed expiries 0..60 calendar days out",
        _NO_CHAIN, "chain", valid_range=(0, None), inputs=(f"{_Q}.expiry",),
    ),
    Feature(
        "target_expiry", "date", "date",
        "The standard monthly closest to 35 days within 21..60 days, else any expiry in that "
        "window, else any at least 14 days out",
        _NO_TARGET, "chain", inputs=(f"{_Q}.expiry",),
    ),
    Feature(
        "target_dte", "int", "days", "Calendar days from the session to the target expiry",
        _NO_TARGET, "chain", valid_range=(0, None), inputs=(f"{_Q}.expiry",),
    ),
    Feature(
        "short_put_ok", "bool", "flag", "put_tier is one of the OK tiers (A, B)",
        _NO_TARGET, "expression", inputs=("option_liquidity.put_tier@v1",),
    ),
    Feature(
        "short_call_ok", "bool", "flag", "call_tier is one of the OK tiers (A, B)",
        _NO_TARGET, "expression", inputs=("option_liquidity.call_tier@v1",),
    ),
    Feature(
        "underlying_price", "float", "usd_per_share",
        "The underlying's price captured with the chain", _NO_QUOTE, "chain",
        valid_range=(0, None), inputs=(f"{_U}.price",),
    ),
    Feature(
        "iv30", "float", "pct_points",
        "The feed's 30-day implied volatility as quoted (a percentage: 25.3 is 25.3%)",
        _NO_QUOTE, "chain", valid_range=(0, 500), inputs=(f"{_U}.iv30",),
    ),
    Feature(
        "stock_volume", "float", "shares", "The underlying's share volume, from the feed",
        _NO_QUOTE, "chain", valid_range=(0, None), inputs=(f"{_U}.volume",),
    ),
    Feature(
        "chain_asof", "date", "date", "When the feed's chain snapshot was taken",
        _NO_QUOTE, "chain", inputs=(f"{_U}.ts",),
    ),
    *_side("put"),
    *_side("call"),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


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


def liquidity_rows(
    status: pd.DataFrame,
    options: pd.DataFrame | None,
    underlyings: pd.DataFrame | None,
    session: date,
    params: LiquidityParams,
) -> pd.DataFrame:
    """One row per underlying in ``status``; failed fetches keep their status as ``liq_status``."""
    chains = dict(tuple(options.groupby("underlying_id"))) if options is not None else {}
    quotes = underlyings.set_index("instrument_id") if underlyings is not None else pd.DataFrame()
    rows = []
    for record in status.to_dict("records"):
        iid, fetch_status = record["instrument_id"], str(record["status"])
        if fetch_status not in ("OK", "NO_STANDARD_SERIES"):
            row = {"liq_status": fetch_status, "put_tier": "D", "call_tier": "D"}
        else:
            frame = chains.get(iid)
            contracts = (
                contracts_from_rows(cast(list[Mapping[str, Any]], frame.to_dict("records")))
                if frame is not None
                else []
            )
            row = assess(contracts, session, params)
        if iid in quotes.index:
            q = quotes.loc[iid]
            row.update(
                underlying_price=q["price"],
                iv30=q["iv30"],
                chain_asof=q["ts"],
                stock_volume=q["volume"],
            )
        rows.append({"instrument_id": iid, **row})
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["instrument_id"])


def compute(inputs: Inputs, session: date, params: LiquidityParams) -> pd.DataFrame:
    status = inputs["chains/status"]
    assert status is not None  # required input
    return liquidity_rows(
        status,
        inputs.get("chains/option_quotes"),
        inputs.get("chains/underlying_quotes"),
        session,
        params,
    )


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "Short-premium tradeability tiers (A-D) for puts and calls at the target expiry",
    (
        Input("chains/status"),
        Input("chains/option_quotes", required=False),
        Input("chains/underlying_quotes", required=False),
    ),
    FEATURES,
    compute,
    LiquidityParams(),
    applies_to="optionable",
)
