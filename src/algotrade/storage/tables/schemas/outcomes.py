"""Outcome table schemas (ADR 0053): the one schema of ``outcomes/instrument/<name>@v<N>`` and its
row checks, and the option trade grain ``outcomes/option/structure_pnl@v2`` (ADR 0053 amendment,
EB H13; ADR 0088, design 2.5).
"""

import pandas as pd

from algotrade.storage.tables.spec import (
    TableSpec,
    fixed,
    floats,
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
# The residual-returns grain (ADR 0053 amendment, EB H11): the return left after the ETF factor
# betas known before S, beside (never inside) forward_returns, so no stored leg is invalidated.
RESIDUAL_RETURNS = f"{OUTCOMES_PREFIX}residual_returns@v1"  # the residual-returns task's table

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


_RESIDUAL_TYPES = (
    "instrument_id string!",
    "ts timestamp_utc!",  # the close of S
    "horizon_sessions int64!",
    "window_end date!",  # T: the h-th exchange session after S
    "beta_session date",  # the session the betas were read at (before S); null: none was found
    "fwd_residual_return float64",  # fwd_return - fwd_factor_return; null: UNMEASURED
    "fwd_factor_return float64",  # sum of beta_k x factor_k return over S..end; null: UNMEASURED
    "outcome_status string!",  # OUTCOME_STATUSES; DELISTED: measured to the last bar
    "outcome_reason string",  # UNMEASURED only: BAD_BAR, NO_FACTOR_HISTORY, NO_BETAS, ...
)
_MEASURED = (
    "fwd_return", "fwd_max_return", "fwd_max_drawdown", "fwd_residual_return",
    "fwd_factor_return",
)  # fmt: skip


def outcomes_spec(table: str) -> TableSpec:
    """The spec of one ``outcomes/instrument/`` table (the forward tables share one schema; the
    residual-returns table has its own, with no benchmark)."""
    if table == RESIDUAL_RETURNS:
        return fixed(
            table, "outcome", ("instrument_id", "ts", "horizon_sessions", "window_end"),
            *_RESIDUAL_TYPES, runs="merge", key=("instrument_id", "horizon_sessions"),
        )  # fmt: skip
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
    for column in (c for c in _MEASURED if c in frame.columns):
        values = frame[column]
        if values[unmeasured].notna().any():
            problems.append(f"{column} must be null when UNMEASURED")
        if values[measured].isna().any():
            problems.append(f"{column} is null on a measured outcome")
    return problems


# Option trades (ADR 0088, design 2.5; v2 replaces the structure grain of ADR 0053 amendment, EB
# H13, v1 was never written): what one position with an option leg, bought at the close of a start
# session S and closed by its exit rules or at its hold cap, earned from the stored chains
# (quotes, never a model price). One row per (underlying, ``position_key``); the partition is S;
# each night writes the windows it closes, so runs merge (the latest wins). ``position_key`` is
# built from the resolved legs and parameters, never the template id
# (``config/edges/positions/key.py``), so two exit rules, or two holds, are two keys.
# ``knowledge_ts`` is the latest ``knowledge_ts`` among the chain and field partitions read up to
# the row's own exit (not the window's close, not the write time). UNMEASURED: a reason and no P&L
# (the entry or exit chain missing or STALE_DATA, ADR 0054, or no exit quote; never a zero, never
# an older chain in its place). Columns declared for a later slice (``regt_margin``,
# ``leg_entry_iv``, ``quoted_otm_prob``, ``dividend_forgone``, the collateral of a ``regt``
# template) are stored null, never read as zero.
STRUCTURE_PNL = "outcomes/option/structure_pnl@v2"  # the grain is its own family, not instrument/
STRUCTURE_PNL_STATUSES = frozenset({"COMPLETE", "UNMEASURED"})
# Why a trade is UNMEASURED: the code before the colon of ``outcome_reason`` (a session follows
# NO_CHAIN and STALE_CHAIN); each has its Guide entry (``chain_outcome_unmeasured``).
STRUCTURE_PNL_REASONS = (
    "NO_CHAIN", "STALE_CHAIN", "NO_EXIT_QUOTE", "NO_EXPIRY", "NO_ENTRY_QUOTE", "NO_PNL",
)  # fmt: skip
EXIT_KINDS = frozenset(
    {
        "EXPIRED", "ASSIGNED", "EARLY_ASSIGNED_DIVIDEND", "TAKE_PROFIT", "STOP_LOSS", "EXIT_DTE",
        "CONDITION", "HORIZON", "DELISTED",
    }
)  # fmt: skip
EXIT_BASES = frozenset({"QUOTE", "INTRINSIC", "INTRINSIC_FALLBACK"})
PRICE_SOURCES = frozenset({"cboe", "option_history"})
LEG_COLUMNS = (
    "leg_kinds", "leg_contract_ids", "leg_rights", "leg_strikes", "leg_expiries", "leg_qty",
    "leg_entry_mid", "leg_entry_half_spread", "leg_entry_delta", "leg_entry_iv",
)  # fmt: skip

_STRUCTURE_PNL_TYPES = (
    "instrument_id string!",  # the underlying (EQ:<FIGI>)
    "ts timestamp_utc!",  # the close of S
    "position_key string!",  # canonical, round-trips to the spec (positions/key.py)
    "price_source string!",  # PRICE_SOURCES
    "licence string!",  # the strictest of the price source and the exit rules' fields (G9)
    "window_end date!",  # T: the hold cap's session (the h-th exchange session after S)
    "hold_sessions int64!",  # the hold cap h (the reader's ``horizon_sessions``)
    "leg_kinds string[]",  # option / shares, aligned lists, the share leg included
    "leg_contract_ids string[]",  # null for a share leg
    "leg_rights string[]",
    "leg_strikes float64[]",
    "leg_expiries date[]",
    "leg_qty float64[]",
    "leg_entry_mid float64[]",
    "leg_entry_half_spread float64[]",
    "leg_entry_delta float64[]",
    "leg_entry_iv float64[]",  # null in this slice
    *floats(
        "entry_spot",
        "entry_net_mid",
        "entry_half_spread",
        "position_delta",
        "position_gamma",
        "position_vega",
        "position_theta",
        "quoted_otm_prob",
        "collateral",
        "notional",
        "regt_margin",
        "entry_oi_min",
        "entry_spread_share",
    ),
    "mark_mid float64[]",  # the position's mid at each close from S (book = true only)
    "spot_path float64[]",
    "exit_session date",
    "exit_kind string",  # EXIT_KINDS
    "exit_basis string",  # EXIT_BASES
    *floats("exit_net_mid", "exit_half_spread", "dividend_forgone"),
    "expired_otm bool",
    "exit_unknown_closes int64!",  # closes up to the exit on which an exit rule was UNKNOWN
    *floats(
        "pnl_mid",
        "option_pnl",
        "stock_pnl",
        "pnl_hedged_mid",
        "path_min",
        "max_adverse",
        "realised_vol_window",
    ),
    "outcome_status string!",  # STRUCTURE_PNL_STATUSES
    "outcome_reason string",  # UNMEASURED only
)
# pnl_mid: the position's mid P&L per unit (a share leg's quantity is shares / 100), option_pnl and
# stock_pnl its option and share parts; pnl_hedged_mid: pnl_mid less a daily delta hedge with our
# own delta (null where a hedge session lacked a chain or delta); path_min: the lowest mark P&L;
# max_adverse: the worst mark loss over collateral (null without collateral).

STRUCTURE_PNL_SPEC = fixed(
    STRUCTURE_PNL, "option_outcome", ("instrument_id", "ts", "position_key", "window_end"),
    *_STRUCTURE_PNL_TYPES, runs="merge", key=("instrument_id", "position_key"),
)  # fmt: skip

_MEASURED_TRADE = (
    "entry_spot", "entry_net_mid", "exit_session", "exit_kind", "exit_basis", "exit_net_mid",
    "pnl_mid",
)  # fmt: skip


def structure_pnl_problems(frame: pd.DataFrame) -> list[str]:
    """A COMPLETE trade has its entry, exit and P&L and known kinds, bases and source; an
    UNMEASURED one has a reason and no P&L (never a zero); the leg lists of a row are as long as
    each other."""
    status = frame["outcome_status"].astype(str)
    problems = []
    bad = sorted(set(status) - STRUCTURE_PNL_STATUSES)
    if bad:
        problems.append(f"outcome_status must be one of {sorted(STRUCTURE_PNL_STATUSES)}: {bad}")
    unmeasured = (status == UNMEASURED).to_numpy()
    reason = frame["outcome_reason"] if "outcome_reason" in frame.columns else None
    if unmeasured.any() and (reason is None or reason[unmeasured].isna().any()):
        problems.append("an UNMEASURED outcome needs an outcome_reason")
    for column in ("pnl_mid", "option_pnl", "stock_pnl", "pnl_hedged_mid"):
        if column in frame.columns and frame[column][unmeasured].notna().any():
            problems.append(f"{column} must be null when UNMEASURED")
    for column in (c for c in _MEASURED_TRADE if c in frame.columns):
        if frame[column][~unmeasured].isna().any():
            problems.append(f"{column} is null on a COMPLETE outcome")
    for column, allowed in (("exit_kind", EXIT_KINDS), ("exit_basis", EXIT_BASES)):
        found = set(frame.loc[~unmeasured, column].dropna().astype(str)) - allowed
        if found:
            problems.append(f"{column} must be one of {sorted(allowed)}: {sorted(found)}")
    source = set(frame["price_source"].astype(str)) - PRICE_SOURCES
    if source:
        problems.append(f"price_source must be one of {sorted(PRICE_SOURCES)}: {sorted(source)}")
    lengths = pd.DataFrame(
        {c: frame[c].map(lambda v: -1 if v is None else len(v)) for c in LEG_COLUMNS
         if c in frame.columns and c != "leg_entry_iv"}
    )  # fmt: skip
    known = lengths.where(lengths >= 0)
    if (known.nunique(axis=1) > 1).any():
        problems.append("the leg_* lists of a row must be as long as each other")
    return problems
