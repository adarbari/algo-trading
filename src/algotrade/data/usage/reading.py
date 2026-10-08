"""Read the text-model usage log (``usage/llm_calls``, written by the API's usage recorder) for
a range of exchange calendar dates: every attempt, and the money spent per day. A day with no
partition has nothing recorded; a null ``cost_usd`` (a call whose cost is unknown) adds nothing
to a sum and is never read as $0 anywhere else (ADR 0057)."""

from datetime import date, datetime
from typing import cast

import pandas as pd

from algotrade.storage.tables.readers import StoreReader

LLM_CALLS = "usage/llm_calls"
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
