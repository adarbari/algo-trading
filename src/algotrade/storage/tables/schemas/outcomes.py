"""Outcome table schemas (ADR 0053): the one schema of ``outcomes/instrument/<name>@v<N>`` and its
row checks, and the chain P&L grain ``outcomes/option/structure_pnl@v1`` (ADR 0053 amendment,
EB H13).
"""

import pandas as pd

from algotrade.storage.tables.spec import (
    TableSpec,
    fixed,
    floats,
    strings,
)

# Outcomes (ADR 0053): what happened after a start session S, read only by the harness
# (``algotrade.data.outcomes``). One family of fixed tables ``outcomes/instrument/<name>@v<N>``;
# the partition is S. Each night T writes the windows it closes (S = T - h sessions), so one
# partition receives one run per horizon on different nights: runs merge, the latest run's row
# winning per (instrument, horizon, benchmark). ``knowledge_ts`` is the write time, never before
# the close of ``window_end`` (the writer refuses a window that has not closed).
# v2 (ADR 0061): a window that needs a bar the ``bar-quality`` task flagged is UNMEASURED, a row
# with a reason and no returns, instead of a return computed over a bad price.
OUTCOMES_PREFIX = "outcomes/instrument/"

FORWARD_RETURNS = f"{OUTCOMES_PREFIX}forward_returns@v2"  # the outcomes task's table

OUTCOME_STATUSES = frozenset({"COMPLETE", "DELISTED", "UNMEASURED"})

UNMEASURED = "UNMEASURED"

_OUTCOME_TYPES = (
    "instrument_id string!",
    "ts timestamp_utc!",  # the close of S
    "horizon_sessions int64!",
    "window_end date!",  # T: the h-th exchange session after S
    "benchmark string!",  # the benchmark ticker of fwd_excess_return
    "fwd_return float64",  # close(T) / close(S) - 1, split-adjusted, price return; null: UNMEASURED
    "fwd_excess_return float64",  # fwd_return - the benchmark's (null: no benchmark bar)
    "fwd_max_return float64",  # max high over (S, T] / close(S) - 1 (favourable); null: UNMEASURED
    "fwd_max_drawdown float64",  # 1 - min low over (S, T] / close(S), >= 0; null: UNMEASURED
    "fwd_realised_vol float64",  # annualised stdev of daily log close returns over (S, T]
    "outcome_status string!",  # OUTCOME_STATUSES; DELISTED: measured to the last bar
    "outcome_reason string",  # UNMEASURED only: why (BAD_BAR: a flagged bar in S..T, ADR 0061)
)


def outcomes_spec(table: str) -> TableSpec:
    """The spec of one ``outcomes/instrument/`` table (they share one schema)."""
    return fixed(
        table, "outcome", ("instrument_id", "ts", "horizon_sessions", "window_end", "benchmark"),
        *_OUTCOME_TYPES, runs="merge", key=("instrument_id", "horizon_sessions", "benchmark"),
    )  # fmt: skip


def outcome_problems(frame: pd.DataFrame) -> list[str]:
    """An UNMEASURED outcome has a reason and no return; every other status has its returns."""
    unmeasured = (frame["outcome_status"] == UNMEASURED).to_numpy()
    problems = []
    reason = frame["outcome_reason"] if "outcome_reason" in frame.columns else None
    if unmeasured.any() and (reason is None or reason[unmeasured].isna().any()):
        problems.append("an UNMEASURED outcome needs an outcome_reason")
    measured = ~unmeasured
    for column in ("fwd_return", "fwd_max_return", "fwd_max_drawdown"):
        values = frame[column]
        if values[unmeasured].notna().any():
            problems.append(f"{column} must be null when UNMEASURED")
        if values[measured].isna().any():
            problems.append(f"{column} is null on a measured outcome")
    return problems


# Chain P&L (ADR 0053 amendment, EB H13): what one option structure bought at the close of a start
# session S and sold at the close of S + h sessions earned, from the stored chains (quotes, never a
# model price). One row per (underlying, structure, tenor rule, horizon); the partition is S; each
# night writes the windows it closes, so runs merge (the latest wins). ``structure`` is the
# position held long (``atm_straddle``; ``put_delta_NN``: the put whose own delta is -NN/100); the
# edge document's side and hedging are applied by the harness. ``knowledge_ts`` is the latest
# ``knowledge_ts`` among the chain partitions the row was computed from (the exit's), never the
# write time. UNMEASURED: a reason and no P&L (a chain missing or STALE_DATA on any session of
# the window, ADR 0054; never a zero, never an older chain in its place).
OPTION_PNL = "outcomes/option/structure_pnl@v1"  # the grain is its own family, not instrument/
OPTION_PNL_STATUSES = frozenset({"COMPLETE", "UNMEASURED"})
# Why a window is UNMEASURED: the code before the colon of ``outcome_reason`` (a session follows
# NO_CHAIN, STALE_CHAIN and NO_DELTA); each has its Guide entry (``chain_outcome_unmeasured``).
OPTION_PNL_REASONS = (
    "NO_CHAIN", "STALE_CHAIN", "NO_EXIT_QUOTE", "NO_DELTA", "NO_EXPIRY", "NO_ENTRY_QUOTE", "NO_PNL",
)  # fmt: skip
EXIT_KINDS = frozenset({"QUOTE", "INTRINSIC"})  # exit at the quoted bid, or intrinsic at expiry
PNL_COLUMNS = (
    "pnl_per_premium", "pnl_exec_per_premium", "pnl_per_underlying",
    "hedged_pnl_per_premium", "hedged_pnl_per_underlying",
)  # fmt: skip

_OPTION_PNL_TYPES = (
    "instrument_id string!",  # the underlying (EQ:<FIGI>)
    "ts timestamp_utc!",  # the close of S
    "structure string!",
    "tenor_days int64!",  # the tenor rule: the first expiry at least this many calendar days out
    "horizon_sessions int64!",
    "window_end date!",  # T: the h-th exchange session after S
    *strings("call_id", "put_id"),  # the contracts held (null for the leg a structure lacks)
    "expiry date",
    *floats("strike", "entry_spot", "entry_mid", "entry_ask", "exit_spot", "exit_mid", "exit_bid"),
    "exit_kind string",  # EXIT_KINDS
    *floats(*PNL_COLUMNS),
    "outcome_status string!",  # OPTION_PNL_STATUSES
    "outcome_reason string",  # UNMEASURED only
)
# pnl_per_premium: long, mid in and mid out, over the entry mid; pnl_exec_per_premium: bought at the
# ask, sold at the bid (intrinsic at expiry), over the ask; pnl_per_underlying: the mid P&L over
# the entry spot; hedged_*: the mid P&L less a daily delta hedge of the underlying at each
# session's close with our own delta (``quant/edges/chain_pnl``), per premium and per underlying.

OPTION_PNL_SPEC = fixed(
    OPTION_PNL, "option_outcome", ("instrument_id", "ts", "structure", "tenor_days",
    "horizon_sessions", "window_end"), *_OPTION_PNL_TYPES, runs="merge",
    key=("instrument_id", "structure", "tenor_days", "horizon_sessions"),
)  # fmt: skip


def option_pnl_problems(frame: pd.DataFrame) -> list[str]:
    """A COMPLETE chain outcome has every P&L and its exit kind; an UNMEASURED one has a reason
    and no P&L (never a zero)."""
    status = frame["outcome_status"].astype(str)
    problems = []
    bad = sorted(set(status) - OPTION_PNL_STATUSES)
    if bad:
        problems.append(f"outcome_status must be one of {sorted(OPTION_PNL_STATUSES)}: {bad}")
    unmeasured = (status == UNMEASURED).to_numpy()
    reason = frame["outcome_reason"] if "outcome_reason" in frame.columns else None
    if unmeasured.any() and (reason is None or reason[unmeasured].isna().any()):
        problems.append("an UNMEASURED outcome needs an outcome_reason")
    for column in PNL_COLUMNS:
        values = frame[column]
        if values[unmeasured].notna().any():
            problems.append(f"{column} must be null when UNMEASURED")
        if values[~unmeasured].isna().any():
            problems.append(f"{column} is null on a COMPLETE outcome")
    kinds = frame["exit_kind"]
    if (~unmeasured).any() and not set(kinds[~unmeasured].astype(str)) <= EXIT_KINDS:
        problems.append(f"exit_kind must be one of {sorted(EXIT_KINDS)} on a COMPLETE outcome")
    return problems
