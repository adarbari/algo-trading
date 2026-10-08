"""Whether an edge's outcome held for one row: the one place an edge document's ``[outcome]``
meets the stored fields of ``outcomes/instrument/forward_returns@v1`` (ADR 0053).

- ``excess_return``: ``value = fwd_excess_return - cost_bps / 1e4`` (a round trip, charged
  once); a hit is ``value > 0``.
- ``hit_target``: ``value`` is the ``measure`` (the net excess return, or ``fwd_realised_vol``
  over the implied vol at S, ``IMPLIED_VOL_FIELD``); a hit is ``value < target`` for
  ``below`` and ``value > target`` for ``above`` (equal is a miss).
- ``expires_otm``: the short option(s) are not assigned at the horizon's close. The strike is
  set at the entry session S from the entry close ``P`` (the price ``fwd_return`` is measured
  from) and the implied vol read at D: ``K / P = strike_from_delta(1, iv, T, delta)`` (or
  ``1 -+ otm_pct``), ``T = horizon / 252`` years (r = q = 0, ``quant/black_scholes``). The hit
  is ``fwd_return > K_put / P - 1`` (put), ``fwd_return < K_call / P - 1`` (call), both
  (strangle); ``value`` is the cushion to the nearest strike (higher = better). ``reference``
  is the risk-neutral chance (N(d2); joint for a strangle) of that hit, ``touch`` whether the
  window's intraday low / high reached a strike (``fwd_max_drawdown`` / ``fwd_max_return``):
  both reported beside the hit rate, never inside it. No premium and no P&L: a win rate
  overstates expectancy.
- ``max_drawdown`` set: a hit also needs ``fwd_max_drawdown <= max_drawdown``.

A row whose value cannot be computed is *excluded with a reason*, never a miss and never a
zero (a window not closed has no stored row: the harness counts it unclosed). DELISTED
rows count: they are measured to the last bar. ``oriented`` is the value with higher =
better, so a ``below`` edge's ranks and effect sizes point the same way as an ``above`` one's.
"""

from collections.abc import Mapping

import numpy as np
import pandas as pd

from algotrade.config.edges.document import Edge
from algotrade.core.model.errors import ConfigurationError
from algotrade.quant.black_scholes import prob_between, prob_otm, strike_from_delta

IMPLIED_VOL_FIELD = (
    "rollup.iv30@v1.iv30"  # our IV30 (decimal, like fwd_realised_vol); chains from 2026-10-02
)
MEASURE_FIELDS: Mapping[str, tuple[str, ...]] = {
    "excess_return": ("fwd_excess_return",),
    "realised_to_implied_vol": ("fwd_realised_vol", IMPLIED_VOL_FIELD),
}
EXPIRES_OTM_FIELDS = ("fwd_return", "fwd_max_return", "fwd_max_drawdown")
MISSING_VALUE = "missing_value"  # a row, but the measure is null (no benchmark bar, no vol)
NO_IMPLIED_VOL = "no_implied_vol"  # the implied vol at S is missing or not positive
MISSING_DRAWDOWN = "missing_drawdown"
TRADING_DAYS = 252  # sessions per year: T of an expires_otm strike
RESULT_COLUMNS = (
    "instrument_id", "value", "oriented", "hit", "excluded", "delisted", "reference", "touch",
)  # fmt: skip


def needs_implied_vol(edge: Edge) -> bool:
    return edge.outcome.kind == "expires_otm" or edge.outcome.measure == "realised_to_implied_vol"


def _implied_array(outcomes: pd.DataFrame, implied: Mapping[str, float | None]) -> np.ndarray:
    return np.array(
        [np.nan if implied.get(i) is None else implied[i] for i in outcomes["instrument_id"]],
        dtype=np.float64,
    )


def _expires_otm(
    edge: Edge, outcomes: pd.DataFrame, implied: Mapping[str, float | None]
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """``(cushion, hit, reference, touch, usable_iv)`` per row of an expires_otm outcome.
    Strikes are relative to the entry close (price 1)."""
    o = edge.outcome
    assert o.structure is not None
    iv = _implied_array(outcomes, implied)
    usable = np.isfinite(iv) & (iv > 0)
    iv = np.where(usable, iv, np.nan)
    years = _numbers(outcomes, "horizon_sessions") / TRADING_DAYS
    ret = _numbers(outcomes, "fwd_return")
    legs = ("put", "call") if o.structure == "strangle" else (o.structure,)
    rel: dict[str, np.ndarray] = {}
    for leg in legs:
        if o.strike_delta is not None:
            rel[leg] = strike_from_delta(1.0, iv, years, o.strike_delta, leg)
        else:
            assert o.otm_pct is not None
            rel[leg] = np.full(len(outcomes), 1.0 - o.otm_pct if leg == "put" else 1.0 + o.otm_pct)
    cushions = []
    if "put" in rel:
        cushions.append(ret - (rel["put"] - 1.0))
    if "call" in rel:
        cushions.append((rel["call"] - 1.0) - ret)
    cushion = np.minimum.reduce(cushions)
    if len(legs) == 2:
        reference = prob_between(1.0, rel["put"], rel["call"], iv, years)
    else:
        reference = prob_otm(1.0, rel[legs[0]], iv, years, legs[0])
    down = _numbers(outcomes, "fwd_max_drawdown") >= 1.0 - rel.get("put", np.nan)
    up = _numbers(outcomes, "fwd_max_return") >= rel.get("call", np.nan) - 1.0
    touch = (down if "put" in rel else False) | (up if "call" in rel else False)
    with np.errstate(invalid="ignore"):
        hit = cushion > 0
    return cushion, hit, np.asarray(reference), np.asarray(touch), usable


def _numbers(frame: pd.DataFrame, column: str) -> np.ndarray:
    return pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype=np.float64, na_value=np.nan)


def apply_outcome(
    edge: Edge, outcomes: pd.DataFrame, implied: Mapping[str, float | None] | None = None
) -> pd.DataFrame:
    """``outcomes`` (the rows of one horizon at one session) as ``RESULT_COLUMNS``: the value,
    its higher-is-better orientation, whether it hit, why it was excluded (``""`` when counted)
    and whether the name was delisted. ``implied``: the IV at S by instrument id (needed when
    ``needs_implied_vol``)."""
    o = edge.outcome
    n = len(outcomes)
    excluded = np.full(n, "", dtype=object)
    reference = np.full(n, np.nan)
    touch = np.full(n, np.nan)
    otm_hit: np.ndarray | None = None
    if o.kind == "expires_otm":
        if implied is None:
            raise ConfigurationError(f"{edge.id}: expires_otm needs the implied vol")
        value, otm_hit, reference, touched, usable_iv = _expires_otm(edge, outcomes, implied)
        touch = touched.astype(np.float64)
        excluded[~np.isfinite(_numbers(outcomes, "fwd_return"))] = MISSING_VALUE
        excluded[(excluded == "") & ~usable_iv] = NO_IMPLIED_VOL
    elif o.kind == "excess_return" or o.measure == "excess_return":
        value = _numbers(outcomes, "fwd_excess_return") - (o.cost_bps or 0.0) / 1e4
        excluded[~np.isfinite(value)] = MISSING_VALUE
    elif o.measure == "realised_to_implied_vol":
        if implied is None:
            raise ConfigurationError(f"{edge.id}: realised_to_implied_vol needs the implied vol")
        vol = _numbers(outcomes, "fwd_realised_vol")
        iv = _implied_array(outcomes, implied)
        usable_iv = np.isfinite(iv) & (iv > 0)
        value = np.full(n, np.nan)
        np.divide(vol, iv, out=value, where=usable_iv)
        excluded[~np.isfinite(vol)] = MISSING_VALUE
        excluded[(excluded == "") & ~usable_iv] = NO_IMPLIED_VOL
    else:
        raise ConfigurationError(f"{edge.id}: no measure {o.measure!r}")
    counted = excluded == ""
    if otm_hit is not None:
        hit = otm_hit
    elif o.kind == "hit_target":
        assert o.target is not None
        below = o.direction == "below"
        with np.errstate(invalid="ignore"):
            hit = (value < o.target) if below else (value > o.target)
    else:
        with np.errstate(invalid="ignore"):
            hit = value > 0
    if o.max_drawdown is not None:
        drawdown = _numbers(outcomes, "fwd_max_drawdown")
        excluded[counted & ~np.isfinite(drawdown)] = MISSING_DRAWDOWN
        counted = excluded == ""
        with np.errstate(invalid="ignore"):
            hit = hit & (drawdown <= o.max_drawdown)
    hit = hit & counted
    sign = -1.0 if o.direction == "below" else 1.0
    return pd.DataFrame(
        {
            "instrument_id": outcomes["instrument_id"].to_numpy(),
            "value": np.where(counted, value, np.nan),
            "oriented": np.where(counted, sign * value, np.nan),
            "hit": hit,
            "excluded": excluded,
            "delisted": (outcomes["outcome_status"] == "DELISTED").to_numpy() & counted,
            "reference": np.where(counted, reference, np.nan),
            "touch": np.where(counted, touch, np.nan),
        },
        columns=list(RESULT_COLUMNS),
    )
