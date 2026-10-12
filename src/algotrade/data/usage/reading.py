"""Read the text-model usage log (``usage/llm_calls``, written by the API's usage recorder) for
a range of exchange calendar dates: every attempt, and the money spent per day. A day with no
partition has nothing recorded; a null ``cost_usd`` (a call whose cost is unknown) adds nothing
to a sum and is never read as $0 anywhere else (ADR 0058). ``calls_of`` counts a user's calls of
one use case on one day (the per-user daily cap of part re-drafts, ADR 0041 amended 2026-10-12)."""

from datetime import date, datetime
from typing import cast

import pandas as pd

from algotrade.storage.tables.readers import StoreReader

LLM_CALLS = "usage/llm_calls"
SKIPPED_BUDGET = "skipped_budget"  # an attempt the ledger did not make (the budget was spent)
SPENDING = ("price", "reported", "bound")  # cost_basis values that count against a budget


def read_llm_calls(
    reader: StoreReader, start: date, end: date, as_of: datetime | None = None
) -> pd.DataFrame | None:
    """The attempts of ``start``..``end`` (inclusive), ``None`` when nothing was recorded."""
    return reader.table_range(LLM_CALLS, start, end, as_of)


def spent_by_day(
    reader: StoreReader, start: date, end: date, as_of: datetime | None = None
) -> dict[date, float]:
    """USD spent per day (``cost_basis`` ``price``, ``reported`` or ``bound``, known costs only);
    a day with none is absent."""
    frame = read_llm_calls(reader, start, end, as_of)
    if frame is None:
        return {}
    spent = frame[frame["cost_basis"].isin(SPENDING) & frame["cost_usd"].notna()]
    days = pd.to_datetime(spent["session_date"]).dt.date
    totals = spent.groupby(days)["cost_usd"].sum()
    return {cast(date, d): float(v) for d, v in totals.items()}


def calls_of(reader: StoreReader, day: date, use_case: str, user: str) -> set[str]:
    """The calls ``user`` made for ``use_case`` on exchange date ``day``, one id per call: its
    ``call_id`` (every attempt of a call shares it), else a key of the attempt (a row from before
    call ids). An attempt never asked (``skipped_budget``) is no call; a failed one is (the
    provider was asked and may have billed)."""
    frame = read_llm_calls(reader, day, day)
    if frame is None:
        return set()
    asked = frame[
        (frame["use_case"] == use_case)
        & (frame["user"] == user)
        & (frame["outcome"] != SKIPPED_BUDGET)
    ]
    out: set[str] = set()
    for row in asked.to_dict("records"):
        call_id = row.get("call_id")  # a store written before call ids has no such column
        out.add(str(call_id) if pd.notna(call_id) else f"{row['provider']}@{row['ts'].isoformat()}")
    return out
