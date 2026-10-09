"""A store for the paper-record read objects: the site edge ``drift`` (canonical run at its
frozen period with a 60% win rate for ``momo``), a user ``me`` who follows it from FOLLOWED, and
helpers that store paper trades the way the nightly job does (partition = signal session)."""

from datetime import UTC, date, datetime
from typing import Any

import pandas as pd
import pytest

from algotrade.config.user import UserContext
from algotrade.data import StoreReader
from algotrade.services.read.context import ReadContext, open_stores
from algotrade.services.read.session import Session
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped
from tests.unit.services.read.evaluation.conftest import DOCS, FROZEN, write_run

FOLLOWED = date(2026, 9, 1)
SESSION = date(2026, 10, 5)  # a Monday; the next session is Oct 6
NEXT = date(2026, 10, 6)
KNOWN = datetime(2026, 10, 3, tzinfo=UTC)
FOLLOW = {"state": "following", "since": FOLLOWED}


def trade(
    iid: str, signal: date, status: str = "open", sell: date = NEXT, rank: int = 1,
    edge: str = "drift", user: str = "me", **changes: Any,
) -> dict[str, Any]:  # fmt: skip
    """One stored paper trade row (the ``results/edge_paper`` columns)."""
    return {
        "user_id": user, "edge_id": edge, "signal_session": signal, "instrument_id": iid,
        "config_hash": "h", "outcome_hash": "o", "screener": "momo", "status": status,
        "reason": "", "buy_session": signal, "sell_session": sell, "horizon_sessions": 20,
        "rank": rank, "delisted": False,
        "excess_return": 0.02 if status == "won" else float("nan"),
    } | changes  # fmt: skip


def store(backend: MemoryBackend, rows: list[dict[str, Any]], known: datetime = KNOWN) -> None:
    """Store ``rows`` in the partition of each one's signal session."""
    frame = pd.DataFrame(rows)
    writer = StoreWriter(backend)
    for day in sorted(set(frame["signal_session"])):
        part = frame[frame["signal_session"] == day].reset_index(drop=True)
        run = f"p-{day}-{known:%H%M}"
        writer.write_table(
            "results/edge_paper",
            day,
            run,
            stamped(part.to_dict("records"), day, run, known, "edge-signals"),
        )


def closed_trades(
    wins: int, losses: int, start: date = date(2026, 9, 2), sell: date = date(2026, 10, 2)
) -> list[dict[str, Any]]:
    """``wins`` won and ``losses`` lost trades, one name each on consecutive days, all settled."""
    days = pd.bdate_range(start, periods=wins + losses).date
    status = ["won"] * wins + ["lost"] * losses
    return [
        trade(f"EQ:T{i}", d, s, sell=sell)
        for i, (d, s) in enumerate(zip(days, status, strict=True))
    ]


def context(
    backend: MemoryBackend,
    day: date = SESSION,
    follow: dict[str, Any] | None = FOLLOW,
    extra: dict[tuple[str, str, str], dict[str, Any]] | None = None,
) -> ReadContext:
    docs = dict(DOCS) | (extra or {})
    if follow is not None:
        docs[("me", "edges", "drift")] = {"follow": follow}
    stores = open_stores(StoreReader(backend), MemoryConfigStore(docs), UserContext("me"))
    session = Session(day, None, True, None, None, False, (), ())
    return ReadContext(
        stores.reader, stores.configs, stores.user, session, stores.features, stores.cache
    )


@pytest.fixture
def backend() -> MemoryBackend:
    b = MemoryBackend()
    write_run(b, "site1", FROZEN, 0.6)  # the canonical run: win rate 60% out of sample
    return b
