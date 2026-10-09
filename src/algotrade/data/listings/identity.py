"""``historical_reference``: the reference rows a session BEFORE the first reference snapshot
reads, so the harness measures the delisted too (edges ED6, ADR 0053 amendment 2026-10-09).

``data.reference`` falls back to the earliest snapshot for such a session: today's names only,
a delisted one has no row and the rest carry today's ``status`` (survivorship). Here the names
are ``universe_asof(session)``'s (alive on that session, survivors and the delisted alike) and
their identity fields come by one of two paths, the owner's rule (disclosed, never hidden):

* ``today_flag``: a name alive in today's snapshot keeps its row (today's ``optionable`` and
  ``security_type``, which favour names that later grew into optionable ones: a lookahead tilt);
* ``proxy``: a name absent from it (delisted) counts as a common stock (Tiingo ``Stock``; an
  ETF stays an ETF) and its ``optionable`` is taken as True, to be decided by the liquidity
  rule the universe itself declares (close and ``adv_usd_20d`` thresholds, no number of our own:
  ``services/evaluation/cross_section/historical.py`` checks the universe has them).

``status`` is ACTIVE for every name (it was listed on the session). Without a stored listing
history the earliest snapshot stands in as before and the session stays ``pre_snapshot``."""

from dataclasses import dataclass
from datetime import date

import pandas as pd

from algotrade.core.model.errors import MissingDataError
from algotrade.data.listings.universe import ETF, universe_asof
from algotrade.storage.tables.readers import StoreReader

TODAY_FLAG = "today_flag"
PROXY = "proxy"
RULE = (
    "before the first reference snapshot the universe is the listing history's names alive on "
    "the session; a name alive in today's snapshot uses today's optionable flag and security "
    "type (lookahead: it favours names that later became optionable), a delisted name counts "
    "as a common stock and its optionable is replaced by the universe's own price and "
    "dollar-volume rule"
)


@dataclass(frozen=True)
class HistoricalIdentity:
    session: date
    frame: pd.DataFrame  # the reference rows of the names alive on ``session``
    proxy_ids: frozenset[str]  # the names on the ``proxy`` path (the rest: ``today_flag``)

    def paths(self, ids: frozenset[str] | set[str] | tuple[str, ...]) -> dict[str, int]:
        """How many of ``ids`` took each path."""
        chosen = set(ids)
        proxy = len(chosen & self.proxy_ids)
        return {TODAY_FLAG: len(chosen) - proxy, PROXY: proxy}


def historical_reference(
    reader: StoreReader, session: date, today: pd.DataFrame
) -> HistoricalIdentity | None:
    """The reference rows for ``session`` from ``universe_asof`` and ``today`` (the earliest
    reference snapshot's rows); ``None`` when no listing history is stored."""
    try:
        listed = universe_asof(reader, session).instruments
    except MissingDataError:
        return None
    ids = listed["instrument_id"].astype(str)
    known = today.assign(instrument_id=today["instrument_id"].astype(str))
    known = known[known["instrument_id"].isin(set(ids))].assign(status="ACTIVE")
    absent = listed[~ids.isin(set(known["instrument_id"]))]
    is_etf = absent["asset_type"].astype(str).str.upper().eq(ETF)
    added = pd.DataFrame(
        {
            "instrument_id": absent["instrument_id"].astype(str),
            "symbol": absent["ticker"].astype(str),
            "asset_class": "EQ",
            "security_type": is_etf.map({True: "ETF", False: "COMMON_STOCK"}),
            "multiplier": 1.0,
            "status": "ACTIVE",
            "exchange": absent["exchange"].astype(str),
            "optionable": True,
            "is_etf": is_etf,
        }
    ).drop_duplicates("instrument_id")
    frame = pd.concat([known, added], ignore_index=True)
    frame = frame.sort_values("instrument_id", kind="stable").reset_index(drop=True)
    return HistoricalIdentity(session, frame, frozenset(added["instrument_id"]))
