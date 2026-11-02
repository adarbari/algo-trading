"""The option cost levels of an option trade's rows (ADR 0088, design 2.4 and 2.6): ``mid`` pays no
spread and no commission, ``effective`` the share of both half-spreads that
``[option_costs] effective_share_by_legs`` names for the structure's option-leg count, and
``full`` all of them; the commission per contract is paid on each side, none at the exit of a
trade that expired (no closing trade). ``full`` with commission is the stored main value of an
``option_pnl`` outcome (``hit._chain_pnl`` reads the ``commission`` column this module writes).

Pure over the option trade grain's rows (``outcomes/option/structure_pnl@v2``): ``at_level`` is a
copy with the half-spreads scaled and the commission set, so ``hit.apply_outcome`` and
``shapes.trade_frame`` run on it unchanged and no formula is duplicated. A figure that cannot be
known (no leg list, no quantity) is NaN at every level, never 0, so one session counts the same
names at each level."""

from collections.abc import Sequence

import numpy as np
import pandas as pd

from algotrade.config.edges.verdict import OPTION_LEVELS, OptionCosts

COMMISSION = "commission"  # the column: dollars per unit (per share of the underlying), both sides
CONTRACT_MULTIPLIER = 100  # shares per option contract; ``structure_pnl@v2`` stores no multiplier
INTRINSIC = "INTRINSIC"  # the exit_basis of a trade settled at expiry: no closing trade, no fee
OPTION = "option"  # a leg_kinds entry (a share leg is the other kind)
_SPREADS = ("entry_half_spread", "exit_half_spread")


def share_by_legs(costs: OptionCosts, n_option_legs: int) -> float:
    """The share of the half-spread ``effective`` pays for a structure of ``n_option_legs`` option
    legs: that of the largest declared leg count at or below it (a count below the first key
    cannot be: the first key is 1)."""
    found = costs.effective_share_by_legs[0][1]
    for legs, share in costs.effective_share_by_legs:
        if legs <= n_option_legs:
            found = share
    return found


def _legs(rows: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """``(option-leg counts, sum of |quantity| of the option legs)`` per row, NaN where a row has
    no leg lists (never 0)."""
    n = len(rows)
    count, size = np.full(n, np.nan), np.full(n, np.nan)
    if "leg_kinds" not in rows.columns or "leg_qty" not in rows.columns:
        return count, size
    for at, (kinds, qty) in enumerate(zip(rows["leg_kinds"], rows["leg_qty"], strict=True)):
        if kinds is None or qty is None or len(kinds) != len(qty):
            continue
        mine = [abs(float(q)) for k, q in zip(kinds, qty, strict=True) if k == OPTION]
        if mine and all(np.isfinite(mine)):
            count[at], size[at] = len(mine), sum(mine)
    return count, size


def commission_per_unit(rows: pd.DataFrame, costs: OptionCosts) -> np.ndarray:
    """The commission of each row per unit: ``commission_usd`` per contract on the entry and,
    unless the trade expired (``exit_basis`` ``INTRINSIC``), on the exit, over
    ``CONTRACT_MULTIPLIER`` shares. NaN where the option legs are not known."""
    _, size = _legs(rows)
    if "exit_basis" in rows.columns:
        closing = (rows["exit_basis"].astype(str) != INTRINSIC).to_numpy()
    else:
        closing = np.ones(len(rows), dtype=bool)
    return costs.commission_usd * size / CONTRACT_MULTIPLIER * (1 + closing)


def at_level(rows: pd.DataFrame, level: str, costs: OptionCosts) -> pd.DataFrame:
    """A copy of option trade ``rows`` at cost ``level``: both half-spreads scaled by k (``mid``
    0, ``effective`` ``share_by_legs`` of the row's option-leg count, ``full`` 1) and the
    commission set (0 at ``mid``, NaN where the legs are unknown)."""
    if level not in OPTION_LEVELS:
        raise ValueError(f"option cost level: expected one of {list(OPTION_LEVELS)}, got {level!r}")
    out = rows.copy()
    count, _ = _legs(rows)
    if level == "mid":
        scale = np.zeros(len(rows))
    elif level == "full":
        scale = np.ones(len(rows))
    else:
        scale = np.array(
            [share_by_legs(costs, int(n)) if np.isfinite(n) else np.nan for n in count]
        )
    fee = commission_per_unit(rows, costs)
    out[COMMISSION] = np.where(np.isfinite(fee), 0.0, np.nan) if level == "mid" else fee
    for column in _SPREADS:
        if column in out.columns:
            with np.errstate(invalid="ignore"):
                out[column] = pd.to_numeric(out[column], errors="coerce") * scale
    return out


def levels(rows: pd.DataFrame, names: Sequence[str], costs: OptionCosts) -> list[pd.DataFrame]:
    """``at_level`` for each of ``names`` in order."""
    return [at_level(rows, name, costs) for name in names]


def commission_of(rows: pd.DataFrame, costs: OptionCosts | None) -> np.ndarray:
    """The per-unit commission ``hit`` and ``shapes`` subtract: the frame's own column (a leveled
    frame), else ``costs``' (the main level), else none: 0 for a caller with no costs."""
    if COMMISSION in rows.columns:
        return pd.to_numeric(rows[COMMISSION], errors="coerce").to_numpy(dtype=np.float64)
    if costs is None:
        return np.zeros(len(rows))
    return commission_per_unit(rows, costs)
