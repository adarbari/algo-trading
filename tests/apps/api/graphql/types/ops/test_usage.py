"""``Query.llmUsage``: the Admin usage page's read over a store holding a usage log; admins are
served, a trader is refused (ADR 0040), an empty log says it recorded nothing."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pandas as pd
from fastapi.testclient import TestClient

from algotrade.config.site.users import Role
from algotrade.config.user import UserContext
from algotrade.core.time.calendar import exchange_date
from algotrade.data import StoreReader
from algotrade.data.usage import LLM_CALLS
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.tables.writers import StoreWriter
from algotrade_api.deps import ApiSettings, ReadStore
from algotrade_api.main import create_app
from tests.helpers.api_store import as_user
from tests.helpers.stored_frames import stamped

QUERY = """{ llmUsage(recent: 5) {
  today recorded budget { dailyUsd error }
  windows { key tally { calls spentUsd reportedUsd inputTokens unknown { code } } cap { kind } }
  breakdowns { by rows { key provider costShare } }
  daily { day tally { calls } }
  reliability { attempts failureRate }
  recent { provider costBasis costUsd inputTokens unknownFields unknown { code } runId }
} }"""


def _graph(role: Role, with_rows: bool) -> Callable[[str], dict[str, Any]]:
    backend = MemoryBackend()
    if with_rows:
        now = datetime.now(UTC)
        day = exchange_date(now)
        rows: list[dict[str, object]] = [
            {"ts": pd.Timestamp(now), "provider": "cli", "model": "haiku", "use_case": "regime",
             "user": "abhi", "input_tokens": None, "output_tokens": None, "latency_s": 2.0,
             "cost_usd": 0.2, "cost_basis": "reported", "outcome": "ok", "fell_back_from": None}
        ]  # fmt: skip
        StoreWriter(backend).write_table(LLM_CALLS, day, "r1", stamped(rows, day, "r1"))
    store = ReadStore(StoreReader(backend), MemoryConfigStore({}), UserContext("local"))
    app = create_app(ApiSettings("memory://", "config"), store, authenticator=as_user("u", role))
    client = TestClient(app)

    def post(query: str) -> dict[str, Any]:
        body: dict[str, Any] = client.post("/graphql", json={"query": query}).json()
        return body

    return post


def test_an_admin_reads_the_usage_with_unknown_tokens_kept_unknown() -> None:
    body = _graph(Role.ADMIN, True)(QUERY)
    assert "errors" not in body, body
    usage = body["data"]["llmUsage"]
    assert usage["recorded"] is True and usage["budget"]["dailyUsd"] is None
    today = next(w for w in usage["windows"] if w["key"] == "today")
    assert today["tally"]["calls"] == 1 and today["tally"]["reportedUsd"] == 0.2
    assert today["tally"]["unknown"]["code"] == "NULL" and today["cap"]["kind"] == "daily"
    [call] = usage["recent"]
    assert call["inputTokens"] is None and "input_tokens" in call["unknownFields"]
    assert call["unknown"]["code"] == "NULL" and call["costBasis"] == "reported"
    assert len(usage["daily"]) == 30


def test_an_empty_log_says_nothing_was_recorded() -> None:
    usage = _graph(Role.ADMIN, False)(QUERY)["data"]["llmUsage"]
    assert usage["recorded"] is False and usage["recent"] == []
    assert usage["reliability"] == {"attempts": 0, "failureRate": None}


def test_a_trader_is_refused() -> None:
    body = _graph(Role.TRADER, True)(QUERY)
    assert body["errors"][0]["extensions"]["code"] == "FORBIDDEN"
