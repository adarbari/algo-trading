"""``historical_reference``: the reference rows a session BEFORE the first reference snapshot
reads, so the harness measures the delisted too (edges ED6, ADR 0053 amendment 2026-10-09).

``data.reference`` falls back to the earliest snapshot for such a session: today's names only,
a delisted one has no row and the rest carry today's ``status`` (survivorship). Here the names
are ``universe_asof(session)``'s (alive on that session, survivors and the delisted alike) and
their identity fields come by one of two paths, the owner's rule (disclosed, never hidden):

* ``today_flag``: a name alive in today's snapshot keeps its row (today's ``optionable`` and
  ``security_type``, which favour names that later grew into optionable ones: a lookahead tilt);
* ``proxy``: a name absent from it (delisted) keeps the ``security_type`` the listing history
  stored for it (Massive's, point in time, ADR 0087: a warrant stays a warrant), and only a null
  type falls back to a common stock (Tiingo ``Stock``; an ETF stays an ETF), the name then in
  ``type_proxy_ids`` and counted (``type_paths``); its ``optionable`` is taken as True, to be
  decided by the liquidity rule the universe itself declares (close and ``adv_usd_20d``
  thresholds, no number of our own: ``services/evaluation/cross_section/historical.py`` checks
  the universe has them).

``status`` is ACTIVE for every name (it was listed on the session). Without a stored listing
history the read raises ``MissingDataError`` (no silent fallback to today's names)."""

import threading
from collections import OrderedDict
from collections.abc import Callable, Hashable
from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd

from algotrade.data.listings.universe import ETF, universe_asof
from algotrade.storage.tables.readers import StoreReader

TODAY_FLAG = "today_flag"
PROXY = "proxy"
STORED_TYPE = "stored_type"
TYPE_PROXY = "type_proxy"
RULE = (
    "before the first reference snapshot the universe is the listing history's names alive on "
    "the session; a name alive in today's snapshot uses today's optionable flag and security "
    "type (lookahead: it favours names that later became optionable), a delisted name keeps the "
    "security type the listing history stored (a null one counts as a common stock) and its "
    "optionable is replaced by the universe's own price and dollar-volume rule"
)


@dataclass(frozen=True)
class HistoricalIdentity:
    session: date
    frame: pd.DataFrame  # the reference rows of the names alive on ``session``
    proxy_ids: frozenset[str]  # the names on the ``proxy`` path (the rest: ``today_flag``)
    # The ``proxy`` names whose security type is the proxy too (stored null, not an ETF): the
    # rest of ``proxy_ids`` carry the type the listing history stored.
    type_proxy_ids: frozenset[str] = frozenset()

    def paths(self, ids: frozenset[str] | set[str] | tuple[str, ...]) -> dict[str, int]:
        """How many of ``ids`` took each path."""
        chosen = set(ids)
        proxy = len(chosen & self.proxy_ids)
        return {TODAY_FLAG: len(chosen) - proxy, PROXY: proxy}

    def type_paths(self, ids: frozenset[str] | set[str] | tuple[str, ...]) -> dict[str, int]:
        """How many of ``ids`` took each way to a security type: today's snapshot, the type the
        listing history stored (its ``security_type``, or its ETF ``asset_type`` when that is null),
        or the null-type proxy (a common stock)."""
        chosen = set(ids)
        proxied = len(chosen & self.type_proxy_ids)
        stored = len(chosen & self.proxy_ids) - proxied
        return {
            TODAY_FLAG: len(chosen) - stored - proxied,
            STORED_TYPE: stored,
            TYPE_PROXY: proxied,
        }


_MEMO_SIZE = 8
_lock = threading.Lock()  # the API's threads share the memo
_memo: OrderedDict[
    tuple[int, str | None, Hashable, date, datetime | None],
    tuple[StoreReader, HistoricalIdentity | None],
] = OrderedDict()


def memoised_identity(
    reader: StoreReader,
    session: date,
    as_of: datetime | None,
    compute: Callable[[], HistoricalIdentity | None],
) -> HistoricalIdentity | None:
    """``compute()`` once per (reader, ``visible_seq``, session, ``as_of``), a small LRU: the
    harness asks for the same session's identity once per field read (16 times). ``visible_seq``
    changes exactly when a commit publishes, so a publish makes every earlier entry unreachable.
    The reader is kept in the entry so its ``id`` is never reused while the entry lives; a
    reader with pending writes (``own_run``) is never memoised."""
    if reader.own_run is not None:  # a run's pending writes do not move ``visible_seq``
        return compute()
    key = (id(reader), reader.own_run, reader.version(), session, as_of)  # read before
    with _lock:
        if key in _memo:
            _memo.move_to_end(key)
            return _memo[key][1]
    found = compute()
    with _lock:
        _memo[key] = (reader, found)
        while len(_memo) > _MEMO_SIZE:
            _memo.popitem(last=False)
    return found


def historical_reference(
    reader: StoreReader, session: date, today: pd.DataFrame
) -> HistoricalIdentity:
    """The reference rows for ``session`` from ``universe_asof`` and ``today`` (the earliest
    reference snapshot's rows); ``MissingDataError`` when no listing history (or S&P 500
    membership) is stored: the harness never falls back to today's names without saying so."""
    listed = universe_asof(reader, session).instruments
    ids = listed["instrument_id"].astype(str)
    known = today.assign(instrument_id=today["instrument_id"].astype(str))
    known = known[known["instrument_id"].isin(set(ids))].assign(status="ACTIVE")
    absent = listed[~ids.isin(set(known["instrument_id"]))]
    # A delisted name's type is the one stored (Massive's, ADR 0087); only a null type falls back
    # to the proxy (an ETF asset type stays an ETF, anything else a common stock: counted).
    stored = absent["security_type"].mask(absent["security_type"].fillna("") == "")
    is_etf_asset = absent["asset_type"].astype(str).str.upper().eq(ETF)
    fallback = is_etf_asset.map({True: "ETF", False: "COMMON_STOCK"})
    security = stored.where(stored.notna(), fallback)
    added = pd.DataFrame(
        {
            "instrument_id": absent["instrument_id"].astype(str),
            "symbol": absent["ticker"].astype(str),
            "asset_class": "EQ",
            "security_type": security,
            "multiplier": 1.0,
            "status": "ACTIVE",
            "exchange": absent["exchange"].astype(str),
            "optionable": True,
            "is_etf": security.eq(ETF),
        }
    ).drop_duplicates("instrument_id")
    frame = pd.concat([known, added], ignore_index=True)
    frame = frame.sort_values("instrument_id", kind="stable").reset_index(drop=True)
    proxied = absent.loc[stored.isna() & ~is_etf_asset, "instrument_id"].astype(str)
    return HistoricalIdentity(
        session,
        frame,
        frozenset(added["instrument_id"]),
        frozenset(proxied) & set(added["instrument_id"]),
    )
