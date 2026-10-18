"""Outcome table schema (ADR 0053): the one schema of ``outcomes/instrument/<name>@v<N>`` and its
row checks.
"""

import pandas as pd

from algotrade.storage.tables.spec import (
    TableSpec,
    fixed,
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
