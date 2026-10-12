"""``Query.myFeatureRequests``: the signed-in user's own missing-feature history, whatever their
role; another user's asks never appear (ADR 0066 amendment)."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient

from algotrade.config.site.users import Role
from algotrade.config.user import UserContext
from algotrade.services.feedback.request_recorder import FeatureRequestRecorder
from algotrade.services.feedback.requests import request_row
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.tables.feedback_writer import FeedbackWriter
from algotrade_api.deps import ApiSettings
from algotrade_api.main import create_app
from tests.helpers.api_store import as_user, store_over

NOON = datetime.now(UTC).replace(hour=16, minute=0)
QUERY = """{ myFeatureRequests { ref description status unmapped firstAsked lastAsked
  timesAsked feasibility span promotedTo } }"""


def _ask(user: str, slug: str, days_ago: int, span: str) -> dict[str, Any]:
    item = SimpleNamespace(
        key=None, new_key_slug=slug, span=span, closest=(), feasibility="NEEDS_SOURCE"
    )
    row = request_row(
        user, item, f"a sentence with {span} in it", at=NOON - timedelta(days=days_ago)
    )
    assert row is not None
    return row


def _client(role: Role) -> TestClient:
    backend = MemoryBackend()
    recorder = FeatureRequestRecorder(FeedbackWriter(backend), clock=lambda: NOON)
    for row in (
        _ask("u", "gamma_squeeze", 3, "gamma squeeze"),
        _ask("u", "gamma_squeeze", 1, "squeeze"),
        _ask("other", "other_secret", 1, "secret"),
    ):
        recorder.submit(row)
    recorder.flush()
    recorder.close()
    store = store_over(backend, MemoryConfigStore({}), UserContext("local"))
    return TestClient(
        create_app(ApiSettings("memory://", "config"), store, authenticator=as_user("u", role))
    )


def test_a_user_reads_only_their_own_history_with_the_latest_span_and_feasibility() -> None:
    for role in (Role.TRADER, Role.ADMIN):
        body = _client(role).post("/graphql", json={"query": QUERY}).json()
        assert "errors" not in body
        (mine,) = body["data"]["myFeatureRequests"]  # nothing of "other"
        assert (mine["ref"], mine["unmapped"], mine["timesAsked"]) == ("gamma_squeeze", True, 2)
        assert mine["span"] == "squeeze" and mine["feasibility"] == "NEEDS_SOURCE"
        assert mine["status"] == "UNMAPPED" and mine["firstAsked"] < mine["lastAsked"]
