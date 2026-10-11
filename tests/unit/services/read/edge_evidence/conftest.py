"""A store for the edge evidence read objects: the site edge ``drift`` with its canonical run
(basis ``momo`` at 20 sessions) and a ledger for it (see ``LEDGER``), and two users: ``owner``
holds the personal licence, ``me`` does not."""

from datetime import date, datetime, timedelta
from typing import Any

import pytest

from algotrade.config.user import UserContext
from algotrade.data import StoreReader
from algotrade.services.read.context import ReadContext, open_stores
from algotrade.services.read.session import Session
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from tests.unit.services.read.evaluation.conftest import DOCS, END, FROZEN, START, write_run

USERS = {"user": [{"id": "owner", "role": "admin", "licences": ["personal"]},
                  {"id": "me", "role": "trader"}]}  # fmt: skip
SESSION = date(2026, 10, 5)


def pick(day: date, iid: str, rank: int, before: bool, **changes: Any) -> dict[str, Any]:
    """One stored ledger row of ``drift`` (the ``results/edge_trades`` columns)."""
    row = {
        "edge_id": "drift", "user_id": "site", "edge_variant": None, "variant": "momo",
        "role": "screener", "horizon_sessions": 20, "range_from": START, "range_to": END,
        "split_from": FROZEN, "decision_session": day, "instrument_id": iid, "rank": rank,
        "entry_session": day + timedelta(days=1), "exit_session": day + timedelta(days=29),
        "status": "won", "hit": True, "value": 0.02 * rank, "gross_value": 0.021,
        "score": 3.0 * rank, "adv_usd_20d": 1e7, "max_drawdown": 0.01, "before_split": before,
        "delisted": False, "licence": "open", "value_licence": "open", "score_licence": "open",
        "adv_licence": "open",
    }  # fmt: skip
    return {**row, **changes}


LEDGER = [
    pick(date(2026, 2, 2), "EQ:B", 2, True),
    pick(date(2026, 2, 2), "EQ:A", 1, True, score_licence="personal", licence="personal"),
    pick(date(2026, 7, 1), "EQ:C", 1, False, status="excluded", hit=None, value=None,
         excluded_reason="NO_ENTRY_BAR"),
    pick(date(2026, 7, 2), "EQ:D", 1, False, status="lost", hit=False, value=-0.01),
    pick(date(2026, 7, 2), "EQ:X", 1, False, variant="other"),  # not the basis
]  # fmt: skip


def context(
    backend: MemoryBackend,
    user: str = "me",
    extra: dict[tuple[str, str, str], Any] | None = None,
    cutoff: datetime | None = None,
) -> ReadContext:
    docs = {**DOCS, ("site", "settings", "users"): USERS, **(extra or {})}
    stores = open_stores(StoreReader(backend), MemoryConfigStore(docs), UserContext(user))
    session = Session(SESSION, None, True, None, None, False, (), (), cutoff=cutoff)
    return ReadContext(
        stores.reader, stores.configs, stores.user, session, stores.features, stores.cache
    )


@pytest.fixture
def backend() -> MemoryBackend:
    b = MemoryBackend()
    write_run(b, "site1", FROZEN, 0.6, trades=LEDGER)
    return b
