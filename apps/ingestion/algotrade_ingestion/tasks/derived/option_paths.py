"""The stored rows of one option trade window (ADR 0088, design 2.5): row shaping only. The
engine (``engines/structures/trades``) chooses the contracts, marks the window, scans the exit
rules and values each trade; this module turns its ``Trade`` list into ``structure_pnl@v2`` rows
(the table's own columns, stamps added by the writer): the aligned leg lists, the entry, exit and
P&L columns, an UNMEASURED trade with its reason and no exit or P&L, and the columns declared for a
later slice (``regt_margin``, ``leg_entry_iv``, ``quoted_otm_prob``, ``dividend_forgone``) null.

A row's ``knowledge_ts`` is the latest stamp among the chain and field partitions read up to its
own exit, never the window's end: a trade that exits early is known as soon as its exit close was.
``stamps[t]`` is the latest ``knowledge_ts`` of the chain and the fields read at close ``t``
(``S`` = 0), None where none had one."""

from collections.abc import Sequence
from datetime import date, datetime
from typing import cast

import numpy as np
import pandas as pd

from algotrade.engines.structures.trades import Trade

COLUMNS = (
    "instrument_id", "ts", "position_key", "price_source", "licence", "window_end", "hold_sessions",
    "leg_kinds", "leg_contract_ids", "leg_rights", "leg_strikes", "leg_expiries", "leg_qty",
    "leg_entry_mid", "leg_entry_half_spread", "leg_entry_delta", "leg_entry_iv", "entry_spot",
    "entry_net_mid", "entry_half_spread", "position_delta", "position_gamma", "position_vega",
    "position_theta", "quoted_otm_prob", "collateral", "notional", "regt_margin", "entry_oi_min",
    "entry_spread_share", "mark_mid", "spot_path", "exit_session", "exit_kind", "exit_basis",
    "exit_net_mid", "exit_half_spread", "dividend_forgone", "expired_otm", "exit_unknown_closes",
    "pnl_mid", "option_pnl", "stock_pnl", "pnl_hedged_mid", "path_min", "max_adverse",
    "realised_vol_window", "outcome_status", "outcome_reason", "knowledge_ts",
)  # fmt: skip


def _known(stamps: Sequence[datetime | None], through: int) -> pd.Timestamp:
    """The latest stamp of closes ``0..through`` (NaT when none)."""
    found = [pd.Timestamp(s) for s in stamps[: through + 1] if s is not None]
    return max(found) if found else cast(pd.Timestamp, pd.NaT)


def _list[T](values: list[T]) -> list[T] | None:
    return values if values else None  # a trade with no legs chosen: a null list, never []


def position_rows(
    trades: Sequence[Trade], stamps: Sequence[datetime | None], *, key: str, hold: int,
    window_end: date, price_source: str, licence: str, ts: datetime,
) -> pd.DataFrame:  # fmt: skip
    """One row per ``Trade``: the table's columns in ``COLUMNS`` order (``knowledge_ts`` last,
    popped by the one publisher)."""
    rows = []
    for t in trades:
        measured = t.reason is None
        rows.append(
            {
                "instrument_id": t.name, "ts": ts, "position_key": key,
                "price_source": price_source, "licence": licence, "window_end": window_end,
                "hold_sessions": hold, "leg_kinds": _list(t.kinds),
                "leg_contract_ids": _list(t.contract_ids), "leg_rights": _list(t.rights),
                "leg_strikes": _list(t.strikes), "leg_expiries": _list(t.expiries),
                "leg_qty": _list(t.qty), "leg_entry_mid": _list(t.leg_mid),
                "leg_entry_half_spread": _list(t.leg_half_spread),
                "leg_entry_delta": _list(t.leg_delta), "leg_entry_iv": None,
                "entry_spot": t.entry_spot, "entry_net_mid": t.entry_net_mid,
                "entry_half_spread": t.entry_half_spread, "position_delta": t.delta,
                "position_gamma": t.gamma, "position_vega": t.vega, "position_theta": t.theta,
                "quoted_otm_prob": np.nan, "collateral": t.collateral, "notional": t.notional,
                "regt_margin": np.nan, "entry_oi_min": t.entry_oi_min,
                "entry_spread_share": t.entry_spread_share, "mark_mid": t.mark_mid,
                "spot_path": t.spot_path, "exit_session": t.exit_session,
                "exit_kind": t.exit_kind, "exit_basis": t.exit_basis,
                "exit_net_mid": t.exit_net_mid, "exit_half_spread": t.exit_half_spread,
                "dividend_forgone": np.nan, "expired_otm": t.expired_otm,
                "exit_unknown_closes": t.unknown_closes, "pnl_mid": t.pnl_mid,
                "option_pnl": t.option_pnl, "stock_pnl": t.stock_pnl,
                "pnl_hedged_mid": t.pnl_hedged_mid, "path_min": t.path_min,
                "max_adverse": t.max_adverse, "realised_vol_window": t.realised_vol,
                "outcome_status": "COMPLETE" if measured else "UNMEASURED",
                "outcome_reason": t.reason, "knowledge_ts": _known(stamps, t.exit_index),
            }
        )  # fmt: skip
    return pd.DataFrame(rows, columns=list(COLUMNS))
