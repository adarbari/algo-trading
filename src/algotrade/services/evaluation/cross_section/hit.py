"""Whether an edge's outcome held for one row: the one place an edge document's ``[outcome]``
meets the stored fields of ``outcomes/instrument/forward_returns@v2`` (ADR 0053).

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
- ``option_model_pnl`` (basis ``model``, never a quote; ADR 0053 amendment): the model P&L of
  one at-the-money straddle at the entry close, as a fraction of the entry price ``P``, from the
  implied vol read at D and the stored window, ``T = horizon / 252``: ``atm_straddle_long`` is
  ``|fwd_return| - straddle_price(iv, T)`` (held to the horizon's close), ``atm_straddle_short``
  its negative, ``delta_hedged_atm`` the long straddle hedged continuously,
  ``vega * (fwd_realised_vol^2 - iv^2) / (2 iv)`` with the straddle's vega at entry
  (``quant/black_scholes``), ``delta_hedged_atm_short`` its negative. ``cost_bps`` is charged
  once, in bps of ``P`` (the excess return's convention); no hedging cost, spread or fill is
  modelled and the cost grid does not apply (it scales a stored return). A hit is ``value > 0``.
- ``side`` ``short`` or ``long_short`` (an ``excess_return`` outcome only): ``short_value`` is the
  value of being short the name, ``-fwd_excess_return - cost_bps / 1e4 - borrow``, with the
  borrow ``borrow_bps_annual / 1e4 * horizon / 252`` (an assumption: no borrow data is stored);
  ``short_hit`` is ``short_value > 0`` (the name underperformed by more than the costs). The
  long columns are unchanged: the deciles and the base are over them whatever the side.
- ``max_drawdown`` set: a hit also needs ``fwd_max_drawdown <= max_drawdown``.

A row whose value cannot be computed is *excluded with a reason*, never a miss and never a
zero (a window not closed has no stored row: the harness counts it unclosed). DELISTED
rows count: they are measured to the last bar. An ``UNMEASURED`` row (a flagged bar in its
window, ``outcome_reason``) is excluded as ``UNMEASURED`` before anything else: no return was
measured, and the harness counts a pick of it like a screen it could not measure. ``oriented``
is the value with higher = better, so a ``below`` edge's ranks and effect sizes point the same way
as an ``above`` one's.
"""

from collections.abc import Mapping

import numpy as np
import pandas as pd

from algotrade.config.edges.document import Edge
from algotrade.core.model.errors import ConfigurationError
from algotrade.quant.black_scholes import (
    atm_straddle_price,
    atm_straddle_vega,
    delta_hedged_vega_pnl,
    prob_between,
    prob_otm,
    strike_from_delta,
)

IMPLIED_VOL_FIELD = (
    "rollup.iv30@v1.iv30"  # our IV30 (decimal, like fwd_realised_vol); chains from 2026-10-02
)
MEASURE_FIELDS: Mapping[str, tuple[str, ...]] = {
    "excess_return": ("fwd_excess_return",),
    "realised_to_implied_vol": ("fwd_realised_vol", IMPLIED_VOL_FIELD),
}
EXPIRES_OTM_FIELDS = ("fwd_return", "fwd_max_return", "fwd_max_drawdown")
MODEL_PNL_FIELDS: Mapping[str, tuple[str, ...]] = {
    "atm_straddle_long": ("fwd_return",),
    "atm_straddle_short": ("fwd_return",),
    "delta_hedged_atm": ("fwd_realised_vol",),
    "delta_hedged_atm_short": ("fwd_realised_vol",),
}  # the stored fields each option_model_pnl structure reads, beside the implied vol
MISSING_VALUE = "missing_value"  # a row, but the measure is null (no benchmark bar, no vol)
NO_IMPLIED_VOL = "no_implied_vol"  # the implied vol at S is missing or not positive
INVALID_IMPLIED_VOL = "invalid_implied_vol"  # ... or non-finite or above MAX_IMPLIED_VOL: garbage
MAX_IMPLIED_VOL = 5.0  # the catalogue's declared range of an IV field is (0, 5] (decimal)
MISSING_DRAWDOWN = "missing_drawdown"
UNMEASURED = "unmeasured"  # an UNMEASURED outcome row (a flagged bar in its window, ADR 0061)
TRADING_DAYS = 252  # sessions per year: T of an expires_otm strike
RESULT_COLUMNS = (
    "instrument_id", "value", "oriented", "hit", "excluded", "delisted", "reference", "touch",
    "short_value", "short_hit",
)  # fmt: skip


def is_return(edge: Edge) -> bool:
    """Whether the outcome's value is the net excess return (``apply_outcome``'s own test)."""
    return edge.outcome.is_return


def needs_implied_vol(edge: Edge) -> bool:
    return (
        edge.outcome.kind in ("expires_otm", "option_model_pnl")
        or edge.outcome.measure == "realised_to_implied_vol"
    )


def _implied_array(outcomes: pd.DataFrame, implied: Mapping[str, float | None]) -> np.ndarray:
    return np.array(
        [np.nan if implied.get(i) is None else implied[i] for i in outcomes["instrument_id"]],
        dtype=np.float64,
    )


def _implied_reasons(iv: np.ndarray) -> np.ndarray:
    """Per row ``""`` for a usable IV (finite, in ``(0, MAX_IMPLIED_VOL]``), ``NO_IMPLIED_VOL``
    when missing or not positive, ``INVALID_IMPLIED_VOL`` when infinite or out of range."""
    reason = np.full(len(iv), "", dtype=object)
    with np.errstate(invalid="ignore"):
        missing = np.isnan(iv) | (iv <= 0)
        invalid = ~missing & ~(iv <= MAX_IMPLIED_VOL)
    reason[missing] = NO_IMPLIED_VOL
    reason[invalid] = INVALID_IMPLIED_VOL
    return reason


def _expires_otm(
    edge: Edge, outcomes: pd.DataFrame, implied: Mapping[str, float | None]
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """``(cushion, hit, reference, touch, usable_iv)`` per row of an expires_otm outcome.
    Strikes are relative to the entry close (price 1)."""
    o = edge.outcome
    assert o.structure is not None
    iv = _implied_array(outcomes, implied)
    usable = _implied_reasons(iv) == ""
    iv = np.where(usable, iv, np.nan)  # masked before any exp / log: no overflow, no warning
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


def _model_pnl(edge: Edge, outcomes: pd.DataFrame, iv: np.ndarray) -> np.ndarray:
    """The ``option_model_pnl`` value per row (NaN where the stored window or the vol is not
    usable; ``iv`` is NaN where it is not), net of ``cost_bps``."""
    o = edge.outcome
    assert o.structure is not None
    years = _numbers(outcomes, "horizon_sessions") / TRADING_DAYS
    if o.structure.startswith("delta_hedged_atm"):
        gross = atm_straddle_vega(iv, years) * delta_hedged_vega_pnl(
            _numbers(outcomes, "fwd_realised_vol"), iv
        )
        gross = -gross if o.structure.endswith("_short") else gross
    else:
        long = np.abs(_numbers(outcomes, "fwd_return")) - atm_straddle_price(iv, years)
        gross = -long if o.structure == "atm_straddle_short" else long
    return np.asarray(gross - (o.cost_bps or 0.0) / 1e4, dtype=np.float64)


def _model_outcome(
    edge: Edge,
    outcomes: pd.DataFrame,
    implied: Mapping[str, float | None] | None,
    excluded: np.ndarray,
) -> np.ndarray:
    """``_model_pnl`` per row; ``excluded`` gets the reason of each row that has no value."""
    if implied is None:
        raise ConfigurationError(f"{edge.id}: option_model_pnl needs the implied vol")
    iv = _implied_array(outcomes, implied)
    reasons = _implied_reasons(iv)
    value = _model_pnl(edge, outcomes, np.where(reasons == "", iv, np.nan))
    excluded[:] = reasons
    excluded[(excluded == "") & ~np.isfinite(value)] = MISSING_VALUE
    return value


def _numbers(frame: pd.DataFrame, column: str) -> np.ndarray:
    return pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype=np.float64, na_value=np.nan)


def _vol_ratio(
    edge: Edge,
    outcomes: pd.DataFrame,
    implied: Mapping[str, float | None] | None,
    excluded: np.ndarray,
) -> np.ndarray:
    """The realised over the implied vol per row; ``excluded`` gets the reason of each row that
    has none."""
    if implied is None:
        raise ConfigurationError(f"{edge.id}: realised_to_implied_vol needs the implied vol")
    vol = _numbers(outcomes, "fwd_realised_vol")
    iv = _implied_array(outcomes, implied)
    reasons = _implied_reasons(iv)
    value = np.full(len(outcomes), np.nan)
    np.divide(vol, iv, out=value, where=reasons == "")
    excluded[~np.isfinite(vol)] = MISSING_VALUE
    excluded[(excluded == "") & (reasons != "")] = reasons[(excluded == "") & (reasons != "")]
    return value


def borrow_cost(borrow_bps_annual: float | None, horizon_sessions: np.ndarray) -> np.ndarray:
    """The borrow cost (a fraction) of a short held ``horizon_sessions``: the assumed yearly
    rate scaled by the share of a year of sessions; zero without a rate."""
    return (borrow_bps_annual or 0.0) / 1e4 * horizon_sessions / TRADING_DAYS


def _short_value(edge: Edge, outcomes: pd.DataFrame, counted: np.ndarray) -> np.ndarray:
    """The value of being short each counted name (see the module doc); NaN for a long outcome
    (no short leg) and for a name that does not count."""
    o = edge.outcome
    if o.side == "long":
        return np.full(len(outcomes), np.nan)
    horizon = _numbers(outcomes, "horizon_sessions")
    gross = _numbers(outcomes, "fwd_excess_return")
    value = -gross - (o.cost_bps or 0.0) / 1e4 - borrow_cost(o.borrow_bps_annual, horizon)
    return np.where(counted, value, np.nan)


def short_view(res: pd.DataFrame) -> pd.DataFrame:
    """``res`` (``apply_outcome``'s, indexed by instrument) as seen from the short side: the
    value, its orientation and the hit are the short's; everything else is shared."""
    out = res.copy()
    out["value"] = out["oriented"] = out["short_value"]
    out["hit"] = out["short_hit"] & (out["excluded"] == "")
    return out


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
        value, otm_hit, reference, touched, _ = _expires_otm(edge, outcomes, implied)
        touch = touched.astype(np.float64)
        excluded[~np.isfinite(_numbers(outcomes, "fwd_return"))] = MISSING_VALUE
        reasons = _implied_reasons(_implied_array(outcomes, implied))
        excluded[(excluded == "") & (reasons != "")] = reasons[(excluded == "") & (reasons != "")]
        excluded[(excluded == "") & ~np.isfinite(value)] = MISSING_VALUE  # no horizon: no strike
    elif o.kind == "option_model_pnl":
        value = _model_outcome(edge, outcomes, implied, excluded)
    elif is_return(edge):
        value = _numbers(outcomes, "fwd_excess_return") - (o.cost_bps or 0.0) / 1e4
        excluded[~np.isfinite(value)] = MISSING_VALUE
    elif o.measure == "realised_to_implied_vol":
        value = _vol_ratio(edge, outcomes, implied, excluded)
    else:
        raise ConfigurationError(f"{edge.id}: no measure {o.measure!r}")
    unmeasured = (outcomes["outcome_status"] == "UNMEASURED").to_numpy()
    excluded[unmeasured] = UNMEASURED  # before any other reason: there is no row to read
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
    sign = o.sign
    short_value = _short_value(edge, outcomes, counted)
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
            "short_value": short_value,
            "short_hit": np.nan_to_num(short_value, nan=-1.0) > 0,
        },
        columns=list(RESULT_COLUMNS),
    )
