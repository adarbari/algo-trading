"""The response cache of ``POST /graphql`` and the admission in front of the read pool: a hit
serves the stored bytes without opening a context, only the classified operations are kept (every
web operation is in exactly one group; one that reads run records is keyed on the runs
generation, and on the closed session when it reads the clock), a role or user never reads
another's entry
(ADR 0056: an admin's answer carries causes), a publish or a write route makes the earlier
entries unreachable (a probe or preview POST does not), an errored answer is not kept, the
bytes are bounded; a request past ``MAX_WAITING`` gets 503 + ``Retry-After`` while ``/health``
and the inline ``viewer`` are never refused."""

import gzip
import json
import re
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from algotrade.config.site.users import Role, UserRecord
from algotrade_api import main
from algotrade_api.deps import ApiSettings, ReadStore
from algotrade_api.graphql.offload import MAX_WAITING, READ_THREADS, Admission
from algotrade_api.graphql.response_cache import (
    CLOSED_SESSION_OPERATIONS,
    NEVER_CACHED,
    RUN_OPERATIONS,
    SHARED_OPERATIONS,
    USER_OPERATIONS,
    ResponseCache,
    WriteEpoch,
    response_key,
)
from algotrade_api.graphql.schema import _accepts_gzip, graphql_router
from algotrade_api.main import create_app
from tests.helpers.api_store import as_user

SESSION = "query Day { session { date } }"  # a cached operation (USER_OPERATIONS)
VIEWER = "query Day { viewer { id role } }"
SHARED = "query MarketHistory { viewer { id role } }"  # a SHARED_OPERATIONS name
RUNS = "query LlmUsage { session { date } }"  # in NEVER_CACHED
RUN_OP = "query NightlyRuns { session { date } viewer { id role } }"  # a RUN_OPERATIONS name
CLOSED_OP = "query IngestionCompleteness { session { date } }"  # also CLOSED_SESSION_OPERATIONS
GQL_TS = Path(__file__).parents[4] / "apps/web/src/shared/api/generated/graphql/gql.ts"


class Harness:
    """Apps over one store sharing a response cache, a published state and an open counter."""

    def __init__(self, store: ReadStore, monkeypatch: pytest.MonkeyPatch) -> None:
        self.store = store
        self.seq = 1
        self.runs = (7, 100)  # the runs generation
        self.closed = date(2026, 10, 8)  # the last closed session
        self.wired: Any = None  # the runs generation main.py passes
        self.opened = 0
        self.cache = ResponseCache()
        self.admission = Admission(2)
        real_reads = main._reads

        def reads(store: ReadStore, cache: Any) -> Callable[..., Any]:
            inner = real_reads(store, cache)

            def counting(*args: Any) -> Any:
                self.opened += 1
                return inner(*args)

            return counting

        def router(
            opener: Any, debug: bool, stores: Any, seq: Any, epoch: WriteEpoch, runs: Any
        ) -> Any:
            self.wired = runs
            return graphql_router(
                opener,
                debug,
                stores,
                lambda: self.seq,
                epoch,
                self.cache,
                self.admission,
                lambda: self.runs,
                lambda: self.closed,
            )

        monkeypatch.setattr(main, "_reads", reads)
        monkeypatch.setattr("algotrade_api.main.graphql_router", router)

    def client(self, user: str = "ana", role: Role = Role.ADMIN) -> TestClient:
        settings = ApiSettings("memory://", "config")
        return TestClient(create_app(settings, self.store, authenticator=as_user(user, role)))


@pytest.fixture
def harness(
    api_golden: tuple[ReadStore, dict[str, str]], monkeypatch: pytest.MonkeyPatch
) -> Harness:
    return Harness(api_golden[0], monkeypatch)


def _post(client: TestClient, query: str) -> Any:
    return client.post("/graphql", json={"query": query})


def test_a_repeat_is_served_from_the_cache_without_opening_a_context(harness: Harness) -> None:
    client = harness.client()
    first = _post(client, SESSION)
    opened = harness.opened
    again = _post(client, SESSION)
    assert first.status_code == again.status_code == 200
    assert opened > 0 and harness.opened == opened  # the second never reached the loaders
    assert again.content == first.content


def test_an_unclassified_or_never_cached_operation_always_runs(harness: Harness) -> None:
    client = harness.client()
    _post(client, RUNS)
    opened = harness.opened
    _post(client, RUNS)
    assert harness.opened > opened and harness.cache.held == 0
    _post(client, "{ session { date } }")  # an anonymous operation: not cached either
    assert harness.cache.held == 0


def test_a_role_and_a_user_never_read_another_entry(harness: Harness) -> None:
    admin = _post(harness.client("ana", Role.ADMIN), VIEWER)
    trader = _post(harness.client("bob", Role.TRADER), VIEWER)
    other = _post(harness.client("alice", Role.TRADER), VIEWER)
    assert admin.json()["data"]["viewer"]["role"] == "admin"
    assert trader.json()["data"]["viewer"]["role"] == "trader"
    assert trader.json()["data"]["viewer"]["id"] == "bob"
    assert other.json()["data"]["viewer"]["id"] == "alice"


def test_a_shared_operation_is_keyed_on_the_role_alone(harness: Harness) -> None:
    admin = _post(harness.client("ana", Role.ADMIN), SHARED)
    bob = _post(harness.client("bob", Role.TRADER), SHARED)
    alice = _post(harness.client("alice", Role.TRADER), SHARED)
    assert admin.json()["data"]["viewer"]["role"] == "admin"  # never a trader's entry
    assert bob.json()["data"]["viewer"]["role"] == "trader"
    assert alice.content == bob.content  # one entry for the role (bob's)


def test_a_publish_makes_the_earlier_entries_unreachable(harness: Harness) -> None:
    client = harness.client()
    _post(client, SESSION)
    harness.seq += 1
    opened = harness.opened
    _post(client, SESSION)
    assert harness.opened > opened


def test_a_write_route_makes_the_earlier_entries_unreachable(harness: Harness) -> None:
    client = harness.client()
    _post(client, SESSION)
    client.delete("/screeners/none/draft")  # a route of routes/authoring
    opened = harness.opened
    _post(client, SESSION)
    assert harness.opened > opened


def test_a_probe_or_a_preview_post_leaves_the_cache_alone(harness: Harness) -> None:
    client = harness.client()
    _post(client, SESSION)
    opened = harness.opened
    client.post("/features/check", json={})  # a preview POST: writes nothing
    client.post("/regime/explain", json={})  # the explain probe the Regime view sends
    _post(client, SESSION)
    assert harness.opened == opened


def test_an_errored_answer_is_not_kept(harness: Harness) -> None:
    client = harness.client()
    bad = _post(client, "query Day { nonsense }")
    assert "errors" in bad.json()
    assert harness.cache.held == 0


def web_operations() -> set[str]:
    """The names of the operations the web sends (the documents of the generated gql.ts)."""
    names = set()
    for m in re.finditer(r'^\s+("(?:[^"\\]|\\.)*"): typeof', GQL_TS.read_text(), re.M):
        head = re.search(r"\b(?:query|mutation)\s+(\w+)", json.loads(m.group(1)))
        if head:
            names.add(head.group(1))
    return names


def test_every_web_operation_is_in_exactly_one_group() -> None:
    groups = [SHARED_OPERATIONS, USER_OPERATIONS, RUN_OPERATIONS, NEVER_CACHED]
    names = web_operations()
    assert len(names) > 40  # the parse found the documents
    for name in sorted(names):
        in_groups = [i for i, group in enumerate(groups) if name in group]
        assert len(in_groups) == 1, f"{name} is in groups {in_groups}: classify it in one"
    for i, group in enumerate(groups):
        assert all(not group & other for other in groups[i + 1 :])
    assert CLOSED_SESSION_OPERATIONS <= RUN_OPERATIONS


def test_a_run_operation_is_kept_until_a_run_record_is_saved(harness: Harness) -> None:
    client = harness.client()
    first = _post(client, RUN_OP)
    opened = harness.opened
    assert _post(client, RUN_OP).content == first.content and harness.opened == opened
    harness.runs = (7, 101)  # a record was saved (a failed job's, an on-request run)
    _post(client, RUN_OP)
    assert harness.opened > opened


def test_a_static_operation_ignores_the_runs_generation(harness: Harness) -> None:
    client = harness.client()
    _post(client, SESSION)
    opened = harness.opened
    harness.runs = (7, 101)
    _post(client, SESSION)
    assert harness.opened == opened


def test_a_run_operation_is_still_keyed_on_publish_and_writes(harness: Harness) -> None:
    client = harness.client()
    _post(client, RUN_OP)
    opened = harness.opened
    harness.seq += 1
    _post(client, RUN_OP)
    assert harness.opened > opened
    opened = harness.opened
    client.delete("/screeners/none/draft")  # a config write: the WriteEpoch
    _post(client, RUN_OP)
    assert harness.opened > opened


def test_a_run_operation_is_per_role_and_user(harness: Harness) -> None:
    admin = _post(harness.client("ana", Role.ADMIN), RUN_OP)
    bob = _post(harness.client("bob", Role.TRADER), RUN_OP)
    alice = _post(harness.client("alice", Role.TRADER), RUN_OP)
    assert admin.json()["data"]["viewer"]["role"] == "admin"
    assert bob.json()["data"]["viewer"]["id"] == "bob"
    assert alice.json()["data"]["viewer"]["id"] == "alice"


def test_the_closed_session_moves_only_the_operations_that_read_the_clock(
    harness: Harness,
) -> None:
    client = harness.client()
    _post(client, RUN_OP)
    _post(client, CLOSED_OP)
    opened = harness.opened
    harness.closed = date(2026, 10, 9)  # the exchange closed another session
    _post(client, RUN_OP)
    assert harness.opened == opened  # NightlyRuns does not read the clock
    _post(client, CLOSED_OP)
    assert harness.opened > opened


def test_an_errored_run_operation_is_not_kept(harness: Harness) -> None:
    bad = _post(harness.client(), "query NightlyRuns { nonsense }")
    assert "errors" in bad.json() and harness.cache.held == 0


def test_the_app_keys_on_the_stores_own_runs_generation(harness: Harness) -> None:
    harness.client()  # builds the app: main.py hands the router the reader's generation
    assert harness.wired == harness.store.reader.runs_generation


def test_the_key_holds_the_variables_and_the_document() -> None:
    who = UserRecord("ana", Role.ADMIN)
    base = response_key(1, 0, who, "{ a }", {"x": 1, "y": 2}, None)
    assert base == response_key(1, 0, who, "{ a }", {"y": 2, "x": 1}, None)  # order of keys
    assert base != response_key(1, 0, who, "{ a }", {"x": 2, "y": 2}, None)
    assert base != response_key(1, 0, who, "{ b }", {"x": 1, "y": 2}, None)
    assert base != response_key(2, 0, who, "{ a }", {"x": 1, "y": 2}, None)
    assert base != response_key(1, 1, who, "{ a }", {"x": 1, "y": 2}, None)
    # the runs generation and the closed session count only for the operations that read them
    assert base == response_key(
        1, 0, who, "{ a }", {"x": 1, "y": 2}, "Day", (1, 2), date(2026, 1, 1)
    )
    run = response_key(1, 0, who, "{ a }", None, "NightlyRuns", (1, 2))
    assert run != response_key(1, 0, who, "{ a }", None, "NightlyRuns", (1, 3))
    assert run == response_key(1, 0, who, "{ a }", None, "NightlyRuns", (1, 2), date(2026, 1, 1))
    closed = response_key(1, 0, who, "{ a }", None, "StatusStrip", (1, 2), date(2026, 1, 1))
    assert closed != response_key(1, 0, who, "{ a }", None, "StatusStrip", (1, 2), date(2026, 1, 2))


def test_the_cache_is_bounded_by_bytes_and_evicts_the_least_recently_used() -> None:
    cache = ResponseCache(max_bytes=10)
    cache.put("a", b"1234")
    cache.put("b", b"1234")
    assert cache.get("a") == b"1234"  # a is now the most recent
    cache.put("c", b"1234")  # 12 bytes: b goes
    assert cache.get("b") is None and cache.get("a") and cache.get("c")
    assert cache.held == 8
    cache.put("big", b"x" * 11)  # larger than the whole bound: never kept
    assert cache.get("big") is None and cache.held == 8


def test_an_entry_expires_after_its_age() -> None:
    now = [0.0]
    cache = ResponseCache(ttl_s=10, clock=lambda: now[0])
    cache.put("a", b"1")
    now[0] = 11
    assert cache.get("a") is None and cache.held == 0


def test_past_the_queue_the_api_answers_503_with_retry_after(harness: Harness) -> None:
    client = harness.client()
    harness.admission.admit()
    harness.admission.admit()  # the pool and its queue are full
    refused = _post(client, RUNS)
    assert refused.status_code == 503 and int(refused.headers["retry-after"]) > 0
    harness.admission.release()
    assert _post(client, RUNS).status_code == 200  # a place is free again


def test_health_and_viewer_are_never_refused(harness: Harness) -> None:
    client = harness.client()
    harness.admission.admit()
    harness.admission.admit()
    assert client.get("/health").status_code == 200
    viewer = _post(client, "{ me: viewer { id } }")  # inline: never refused
    assert viewer.status_code == 200 and viewer.json()["data"]["me"]["id"] == "ana"


def test_a_request_releases_its_place_even_when_it_fails(harness: Harness) -> None:
    client = harness.client()
    for _ in range(5):
        _post(client, "{ nonsense }")
    assert harness.admission.taken == 0


def test_the_queue_is_a_constant_beyond_the_threads() -> None:
    assert Admission().limit == READ_THREADS + MAX_WAITING


def test_a_hit_is_served_as_stored_gzip_without_compressing_again(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = harness.client()
    gz = {"Accept-Encoding": "gzip"}
    first = client.post("/graphql", json={"query": SESSION}, headers=gz)
    assert first.headers["content-encoding"] == "gzip"
    assert "Accept-Encoding" in first.headers["vary"]
    calls: list[int] = []
    real = gzip.compress
    monkeypatch.setattr(gzip, "compress", lambda *a, **k: calls.append(1) or real(*a, **k))
    again = client.post("/graphql", json={"query": SESSION}, headers=gz)
    assert again.headers["content-encoding"] == "gzip"
    assert "Accept-Encoding" in again.headers["vary"]
    assert not calls  # neither the handler nor the middleware compressed the hit
    assert again.json() == first.json()


def test_the_byte_bound_counts_the_stored_gzip_size(harness: Harness) -> None:
    body = _post(harness.client(), SESSION).content
    assert harness.cache.held == len(gzip.compress(body, 5)) > 0
    assert harness.cache.held != len(body)  # the compressed size, not the JSON's


def test_a_client_without_gzip_gets_the_identity_body(harness: Harness) -> None:
    client = harness.client()
    _post(client, SESSION)  # fills the cache
    plain = client.post(
        "/graphql", json={"query": SESSION}, headers={"Accept-Encoding": "identity"}
    )
    assert "content-encoding" not in plain.headers
    assert "Accept-Encoding" in plain.headers["vary"]
    assert plain.json()["data"]["session"]


def test_gzip_with_q0_is_refused() -> None:
    assert _accepts_gzip("br, gzip;q=0.8") and _accepts_gzip("*")
    assert not _accepts_gzip("gzip;q=0") and not _accepts_gzip("identity")
    assert not _accepts_gzip("")
