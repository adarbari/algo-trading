"""Whether an edge's outcome held for one row: the one place an edge document's ``[outcome]``
meets the stored fields of ``outcomes/instrument/forward_returns@v1`` (ADR 0053).

- ``excess_return``: ``value = fwd_excess_return - cost_bps / 1e4`` (a round trip, charged
  once); a hit is ``value > 0``.
- ``hit_target``: ``value`` is the ``measure`` (the net excess return, or ``fwd_realised_vol``
  over the implied vol at S, ``IMPLIED_VOL_FIELD``); a hit is ``value < target`` for
  ``below`` and ``value > target`` for ``above`` (equal is a miss).
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

IMPLIED_VOL_FIELD = (
    "rollup.iv30@v1.iv30"  # our IV30 (decimal, like fwd_realised_vol); chains from 2026-10-02
)
MEASURE_FIELDS: Mapping[str, tuple[str, ...]] = {
    "excess_return": ("fwd_excess_return",),
    "realised_to_implied_vol": ("fwd_realised_vol", IMPLIED_VOL_FIELD),
}
MISSING_VALUE = "missing_value"  # a row, but the measure is null (no benchmark bar, no vol)
NO_IMPLIED_VOL = "no_implied_vol"  # the implied vol at S is missing or not positive
MISSING_DRAWDOWN = "missing_drawdown"
RESULT_COLUMNS = ("instrument_id", "value", "oriented", "hit", "excluded", "delisted")


def needs_implied_vol(edge: Edge) -> bool:
    return edge.outcome.measure == "realised_to_implied_vol"


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
    if o.kind == "excess_return" or o.measure == "excess_return":
        value = _numbers(outcomes, "fwd_excess_return") - (o.cost_bps or 0.0) / 1e4
        excluded[~np.isfinite(value)] = MISSING_VALUE
    elif o.measure == "realised_to_implied_vol":
        if implied is None:
            raise ConfigurationError(f"{edge.id}: realised_to_implied_vol needs the implied vol")
        vol = _numbers(outcomes, "fwd_realised_vol")
        iv = np.array(
            [np.nan if implied.get(i) is None else implied[i] for i in outcomes["instrument_id"]],
            dtype=np.float64,
        )
        usable_iv = np.isfinite(iv) & (iv > 0)
        value = np.full(n, np.nan)
        np.divide(vol, iv, out=value, where=usable_iv)
        excluded[~np.isfinite(vol)] = MISSING_VALUE
        excluded[(excluded == "") & ~usable_iv] = NO_IMPLIED_VOL
    else:
        raise ConfigurationError(f"{edge.id}: no measure {o.measure!r}")
    counted = excluded == ""
    if o.kind == "hit_target":
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
        },
        columns=list(RESULT_COLUMNS),
    )
