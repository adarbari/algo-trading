"""The user's split read: their own ``split_from`` (none until saved), the frozen periods of the
edges they see and the request's session as the latest a split may name."""

from datetime import date

from algotrade.services.read.evaluation.split import load_evaluation_split
from algotrade.storage.backends.memory import MemoryBackend
from tests.unit.services.read.evaluation.conftest import FROZEN, session_ctx, stores


def test_no_split_until_the_user_saves_one(backend: MemoryBackend) -> None:
    read = load_evaluation_split(session_ctx(stores(backend), date(2026, 9, 30)))
    assert read.split_from is None
    assert [(p.edge_id, p.frozen_from) for p in read.frozen_periods] == [("drift", FROZEN)]
    assert read.latest_session == date(2026, 9, 30)
