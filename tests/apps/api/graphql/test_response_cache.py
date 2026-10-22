"""The response cache of ``POST /graphql`` and the admission in front of the read pool: a hit
serves the stored bytes without opening a context, only the classified operations are kept (every
web operation is in exactly one group; one that reads run records is keyed on the runs
generation, and on the closed session when it reads the clock), a role or user never reads
another's entry
(ADR 0056: an admin's answer carries causes), a publish or a write route makes the earlier
entries unreachable (a probe or preview POST does not), an errored answer is not kept, the
bytes are bounded; a request past ``MAX_WAITING`` gets 503 + ``Retry-After`` while ``/health``
and the inline ``viewer`` are never refused."""

import asyncio
import gzip
import json
import re
import time
from collections.abc import Callable
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from algotrade.config.site.users import Role, UserRecord
from algotrade.data import StoreReader
from algotrade.storage.backends.local import LocalBackend
from algotrade_api import main
from algotrade_api.deps import ApiSettings, ReadStore
from algotrade_api.graphql.context import ReleaseReads
from algotrade_api.graphql.offload import MAX_WAITING, READ_THREADS, Admission
from algotrade_api.graphql.response_cache import (
    CLOSED_SESSION_OPERATIONS,
    NEVER_CACHED,
    RUN_OPERATIONS,
    SHARED_OPERATIONS,
    TTL_S,
    USER_OPERATIONS,
    ResponseCache,
    Served,
    operation_name,
    response_key,
    served_token,
)
from algotrade_api.graphql.schema import _accepts_gzip, graphql_router
from algotrade_api.main import create_app
from tests.helpers.api_store import END, as_user
from tests.helpers.stored_frames import T0, stamped

SESSION = "query Regime { session { date } }"  # a cached operation (USER_OPERATIONS)
VIEWER = "query Viewer { viewer { id role } }"
SHARED = "query RegimeBands { viewer { id role } }"  # a SHARED_OPERATIONS name
RUNS = "query AcceptedFormulas { session { date } }"  # in NEVER_CACHED
USAGE = "query LlmUsage { session { date } }"  # USER_OPERATIONS + TODAY_OPERATIONS
RUN_OP = "query NightlyRuns { session { date } viewer { id role } }"  # a RUN_OPERATIONS name
CLOSED_OP = "query IngestionCompleteness { session { date } }"  # also CLOSED_SESSION_OPERATIONS
GQL_TS = Path(__file__).parents[4] / "apps/web/src/shared/api/generated/graphql/gql.ts"


class Harness:
    """Apps over one store sharing a response cache, a published state and an open counter."""

    def __init__(self, store: ReadStore, monkeypatch: pytest.MonkeyPatch) -> None:
        self.store = store
        self.seq = 1
        self.releases: Any = None  # ReleaseReads the router follows (ADR 0077)
        self.generation: int | None = 0  # the caller's config generation (None: a write in flight)
        self.runs = (7, 100)  # the runs generation
        self.closed = date(2026, 10, 8)  # the last closed session
        self.served = "2026-10-08"  # the default session's token (ADR 0062)
        self.wired: Any = None  # the runs generation main.py passes
        self.opened = 0
        self.now = [0.0]
        self.cache = ResponseCache(clock=lambda: self.now[0])
        self.router: Any = None
        self.admission = Admission(2)
        real_reads = main._reads

        def reads(store: ReadStore, cache: Any) -> Callable[..., Any]:
            inner = real_reads(store, cache)

            def counting(*args: Any, **kwargs: Any) -> Any:
                self.opened += 1
                return inner(*args, **kwargs)

            return counting

        def router(
            opener: Any,
            debug: bool,
            stores: Any,
            seq: Any,
            runs: Any,
            served: Any,
            log: Any = None,
            config_generation: Any = None,
            releases: Any = None,
        ) -> Any:
            self.wired, self.wired_served = runs, served
            self.router = graphql_router(
                opener,
                debug,
                stores,
                lambda: self.seq,
                self.cache,
                self.admission,
                lambda: self.runs,
                lambda: self.closed,
                lambda: self.served,
                log,
                lambda user, everyone: self.generation,
                self.releases,
            )
            return self.router

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


def test_a_config_write_makes_the_earlier_entries_unreachable(harness: Harness) -> None:
    client = harness.client()
    _post(client, SESSION)
    harness.generation = 2  # what a write through ConfigWriter does (tests/contract/api)
    opened = harness.opened
    _post(client, SESSION)
    assert harness.opened > opened


def test_a_config_generation_moves_only_the_keys_that_hold_the_user(harness: Harness) -> None:
    """ADR 0077 decision 15: the durable counter, not the process, tells a write happened."""
    client = harness.client()
    _post(client, SESSION)
    _post(client, SHARED)
    harness.generation = 2
    opened = harness.opened
    _post(client, SHARED)
    assert harness.opened == opened  # a shared answer holds no user state
    _post(client, SESSION)
    assert harness.opened > opened  # a user-keyed one is recomputed


def test_nothing_is_cached_while_a_write_of_the_caller_is_in_flight(harness: Harness) -> None:
    client = harness.client()
    harness.generation = None  # odd: a write is in flight, or crashed
    _post(client, SESSION)
    opened = harness.opened
    _post(client, SESSION)
    assert harness.opened > opened and harness.cache.held == 0


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
    bad = _post(client, "query Regime { nonsense }")
    assert "errors" in bad.json()
    assert harness.cache.held == 0


WEB_SRC = Path(__file__).parents[4] / "apps/web/src"
HAND_WRITTEN = re.compile(r"""[`'"]\s*(?:query|mutation)\s+(\w+)""")


def web_operations() -> set[str]:
    """The names of the operations the web sends: the documents of the generated gql.ts, plus
    the hand-written ``query <Name>`` template strings of the app code (tests and stories apart)."""
    names = set()
    for m in re.finditer(r'^\s+("(?:[^"\\]|\\.)*"): typeof', GQL_TS.read_text(), re.M):
        head = re.search(r"\b(?:query|mutation)\s+(\w+)", json.loads(m.group(1)))
        if head:
            names.add(head.group(1))
    for path in WEB_SRC.rglob("*.ts*"):
        if "generated" in path.parts or re.search(r"\.(test|stories)\.", path.name):
            continue
        names.update(HAND_WRITTEN.findall(path.read_text()))
    return names


def test_the_hand_written_operations_are_seen() -> None:
    hand_written = {"EdgeDesk", "EdgePaper", "EdgeBuilder", "EdgeCompare", "PublishedEdge"}
    assert hand_written <= web_operations()


def test_every_web_operation_is_in_exactly_one_group() -> None:
    groups = [SHARED_OPERATIONS, USER_OPERATIONS, RUN_OPERATIONS, NEVER_CACHED]
    names = web_operations()
    assert len(names) > 80  # the parse found the documents (76 in gql.ts + 5 hand-written)
    for name in sorted(names):
        in_groups = [i for i, group in enumerate(groups) if name in group]
        assert len(in_groups) == 1, f"{name} is in groups {in_groups}: classify it in one"
    for i, group in enumerate(groups):
        assert all(not group & other for other in groups[i + 1 :])
    assert CLOSED_SESSION_OPERATIONS <= RUN_OPERATIONS


def test_no_group_keeps_an_operation_the_web_no_longer_sends() -> None:
    sent = web_operations()
    for group in (SHARED_OPERATIONS, USER_OPERATIONS, RUN_OPERATIONS, NEVER_CACHED):
        assert not group - sent, f"classified but sent by no web document: {sorted(group - sent)}"


def test_a_run_operation_is_kept_until_a_run_record_is_saved(harness: Harness) -> None:
    client = harness.client()
    first = _post(client, RUN_OP)
    opened = harness.opened
    assert _post(client, RUN_OP).content == first.content and harness.opened == opened
    harness.runs = (7, 101)  # a record was saved (a failed job's, an on-request run)
    _post(client, RUN_OP)
    assert harness.opened > opened


def test_a_job_record_does_not_evict_a_shared_operation_but_a_session_completing_does(
    harness: Harness,
) -> None:
    """A checkpoint or job record saves no session (the runs generation moves, the served token
    does not): nothing is evicted. A nightly turning a session COMPLETE changes the default
    session's token (ADR 0062): every operation is read again, without a publish."""
    client = harness.client()
    _post(client, SESSION)
    opened = harness.opened
    harness.runs = (7, 101)  # a non-nightly record was saved
    _post(client, SESSION)
    assert harness.opened == opened
    harness.served = "2026-10-09"  # the nightly completed the next session
    _post(client, SESSION)
    assert harness.opened > opened


def test_the_app_wires_the_real_default_session_token(harness: Harness) -> None:
    harness.client()
    assert harness.wired_served() == str(END)  # the golden store has no nightly records


def test_the_served_token_holds_the_newer_session_too() -> None:
    day, newer = date(2026, 10, 8), date(2026, 10, 9)
    plain = served_token(SimpleNamespace(date=day, newer=None))
    failing = served_token(
        SimpleNamespace(
            date=day, newer=SimpleNamespace(date=newer, state="FAILED_RETRYING", kind="SYSTEM")
        )
    )
    going = served_token(
        SimpleNamespace(date=day, newer=SimpleNamespace(date=newer, state="IN_PROGRESS", kind=None))
    )
    assert len({plain, failing, going}) == 3


def test_a_run_operation_is_still_keyed_on_publish_and_writes(harness: Harness) -> None:
    client = harness.client()
    _post(client, RUN_OP)
    opened = harness.opened
    harness.seq += 1
    _post(client, RUN_OP)
    assert harness.opened > opened
    opened = harness.opened
    harness.generation = 2  # a config write: the caller's config generation
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


def test_each_ideas_page_has_its_own_key_by_its_cursor() -> None:
    """``after`` is a variable, so page two never answers with page one's bytes (owner decision
    2026-10-22, "Ideas page size"); the first page asked with and without a null cursor differ
    only as the client sent them."""
    who = UserRecord("ana", Role.TRADER)
    doc = "query IdeasPage($first: Int!, $after: String) { ideas(first: $first, after: $after) { total } }"  # noqa: E501
    one = response_key(1, who, doc, {"first": 50, "after": None}, "IdeasPage", (1, 1))
    two = response_key(1, who, doc, {"first": 50, "after": "YzI6NTA"}, "IdeasPage", (1, 1))
    three = response_key(1, who, doc, {"first": 50, "after": "Yzk6MTAw"}, "IdeasPage", (1, 1))
    assert len({one, two, three}) == 3
    assert (
        "IdeasPage" in RUN_OPERATIONS
    )  # keyed on the runs generation too, so a new run moves them


def test_the_key_holds_the_variables_and_the_document() -> None:
    who = UserRecord("ana", Role.ADMIN)
    base = response_key(1, who, "{ a }", {"x": 1, "y": 2}, None)
    assert base == response_key(1, who, "{ a }", {"y": 2, "x": 1}, None)  # order of keys
    assert base != response_key(1, who, "{ a }", {"x": 2, "y": 2}, None)
    assert base != response_key(1, who, "{ b }", {"x": 1, "y": 2}, None)
    assert base != response_key(2, who, "{ a }", {"x": 1, "y": 2}, None)
    assert base != response_key(1, who, "{ a }", {"x": 1, "y": 2}, None, generation=2)
    # the runs generation counts only for the run operations, the closed session only for the
    # operations that read the clock; every key holds the default session (ADR 0062)
    assert base == response_key(1, who, "{ a }", {"x": 1, "y": 2}, "Day", (1, 2))
    assert base != response_key(1, who, "{ a }", {"x": 1, "y": 2}, None, served="2026-10-09")
    shared = response_key(1, who, "{ a }", None, "RegimeBands", (1, 2))
    assert shared == response_key(1, who, "{ a }", None, "RegimeBands", (1, 3))
    assert base == response_key(1, who, "{ a }", {"x": 1, "y": 2}, None, (0, 0), date(2026, 1, 1))
    run = response_key(1, who, "{ a }", None, "NightlyRuns", (1, 2))
    assert run != response_key(1, who, "{ a }", None, "NightlyRuns", (1, 3))
    assert run == response_key(1, who, "{ a }", None, "NightlyRuns", (1, 2), date(2026, 1, 1))
    closed = response_key(1, who, "{ a }", None, "StatusStrip", (1, 2), date(2026, 1, 1))
    assert closed != response_key(1, who, "{ a }", None, "StatusStrip", (1, 2), date(2026, 1, 2))


def test_the_usage_page_is_kept_per_day_and_moves_with_a_publish(harness: Harness) -> None:
    """A logged call publishes a partition (seq), a new exchange date changes the key: the
    page that took 0.4-1 s every call is a hit until one of them moves."""
    client = harness.client()
    _post(client, USAGE)
    opened = harness.opened
    _post(client, USAGE)
    assert harness.opened == opened  # a hit
    harness.seq = 2  # a call was logged
    _post(client, USAGE)
    assert harness.opened > opened
    viewer = UserRecord("ana", Role.ADMIN)

    def key(day: date) -> str:
        return response_key(1, viewer, USAGE, None, "LlmUsage", today=day)

    assert key(date(2026, 10, 8)) != key(date(2026, 10, 9))


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


def test_an_entry_is_stale_after_ttl_and_dropped_after_the_hard_ttl() -> None:
    now = [0.0]
    cache = ResponseCache(ttl_s=10, hard_ttl_s=100, clock=lambda: now[0])
    cache.put("a", b"1")
    assert cache.get("a") == b"1" and cache.get_stale("a") is None  # fresh: get serves it
    now[0] = 11
    assert cache.get("a") is None and cache.get_stale("a") == b"1"  # stale: kept for the router
    now[0] = 101
    assert cache.get_stale("a") is None and cache.held == 0  # hard TTL: gone


def _wait_until(done: Callable[[], bool]) -> None:
    for _ in range(500):
        if done():
            return
        time.sleep(0.01)
    raise AssertionError("the background recompute did not finish")


def test_a_stale_entry_is_served_at_once_and_recomputed_behind_the_answer(
    harness: Harness,
) -> None:
    """After an idle spell past the TTL the first request is a cache answer, not a recompute."""
    with harness.client() as client:
        first = _post(client, SESSION)
        harness.now[0] += TTL_S + 1
        opened = harness.opened
        stale = _post(client, SESSION)
        assert stale.content == first.content
        _wait_until(lambda: harness.opened > opened)  # the recompute ran after the answer
        opened = harness.opened
        _wait_until(lambda: harness.cache.get(_key(harness)) is not None)  # fresh again
        _post(client, SESSION)
        assert harness.opened == opened  # fresh again: a hit


def _key(harness: Harness) -> str:
    return response_key(
        harness.seq, UserRecord("ana", Role.ADMIN), SESSION, None, "Regime",
        served=harness.served,
    )  # fmt: skip


def test_a_replay_after_a_publish_fills_the_cache_before_any_request(harness: Harness) -> None:
    """The warmer replays the served operations for the new published state."""
    with harness.client() as client:
        _post(client, SESSION)
        harness.seq = 2  # a publish: the cached entry is unreachable
        assert client.portal is not None
        assert client.portal.call(harness.router.replay) >= 1
        opened = harness.opened
        again = _post(client, SESSION)
        assert again.status_code == 200 and harness.opened == opened  # served by the replay's entry
        assert client.portal.call(harness.router.replay) == 0  # nothing stale: nothing recomputed


def test_a_replay_runs_as_the_caller_it_recorded(harness: Harness) -> None:
    """ADR 0056: a trader's operation is replayed as that trader: the entry it fills is the
    trader's, and an admin asking next still computes its own."""
    with harness.client("tia", Role.TRADER) as client:
        trader = _post(client, RUN_OP)
        harness.seq = 2
        assert client.portal is not None
        client.portal.call(harness.router.replay)
        opened = harness.opened
        assert _post(client, RUN_OP).content == trader.content and harness.opened == opened
    with harness.client("ana", Role.ADMIN) as admin:
        assert _post(admin, RUN_OP).status_code == 200
        assert harness.opened > opened  # the trader's entry is not the admin's


def test_a_replay_stops_when_the_pool_is_busy_and_drops_a_failing_operation(
    harness: Harness,
) -> None:
    with harness.client() as client:
        _post(client, SESSION)
        _post(client, "query Regime { nosuchfield }")  # errors: never kept, never replayed again
        harness.seq = 2
        assert client.portal is not None
        router = harness.router
        harness.admission.taken = READ_THREADS  # requests are using the pool
        assert client.portal.call(router.replay) == 0
        harness.admission.taken = 0
        assert client.portal.call(router.replay) >= 1
        assert client.portal.call(router.replay, None, 0.0) == 0  # no budget: nothing recomputed
        documents = [op.document for op in router._log.items()]
        assert "query Regime { nosuchfield }" not in documents and SESSION in documents


def _served(document: str) -> Served:
    return Served(UserRecord("ana", Role.ADMIN), document, {})


def test_a_replay_runs_the_cheap_operations_first_and_the_heavy_ones_last(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Seeded in page order, the heavy InstrumentEvents would run before the cheap reads and
    starve a first request: the cheap ones come first, each kind keeping its order."""
    with harness.client() as client:
        assert client.portal is not None
        ran: list[str | None] = []

        async def refresh(op: Served, only_missing: bool = False) -> bool:
            ran.append(operation_name(op.document))
            return True

        monkeypatch.setattr(harness.router, "refresh", refresh)
        ops = [
            _served("query InstrumentEvents { a }"),
            _served("query Regime { a }"),
            _served("query RegimeBands { a }"),
            _served("query Viewer { a }"),
        ]
        assert client.portal.call(harness.router.replay, ops) == 4
        assert ran == ["Regime", "Viewer", "InstrumentEvents", "RegimeBands"]


def test_a_request_is_served_while_the_replay_is_still_running(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The replay yields the loop between operations (a first request is not queued behind
    the whole pass), and a heavy one is left for the next publish while a request holds the pool."""
    with harness.client() as client:
        assert client.portal is not None
        ran: list[str | None] = []

        async def refresh(op: Served, only_missing: bool = False) -> bool:
            ran.append(operation_name(op.document))
            return True

        monkeypatch.setattr(harness.router, "refresh", refresh)
        ops = [_served(f"query Op{n} {{ a }}") for n in range(20)]

        async def go() -> tuple[int, int]:
            replaying = asyncio.ensure_future(harness.router.replay(ops))
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            served_during = len(ran)  # a request's turn on the loop came between operations
            return served_during, await replaying

        during, done = client.portal.call(go)
        assert 0 < during < 20 and done == 20

        ran.clear()
        harness.admission.taken = 1  # a request is using the pool
        heavy = [_served("query InstrumentEvents { a }"), _served("query Regime { a }")]
        assert client.portal.call(harness.router.replay, heavy) == 1
        assert ran == ["Regime"]  # the heavy one waits for an idle pool
        harness.admission.taken = 0


def test_closing_the_router_cancels_the_background_recomputes(harness: Harness) -> None:
    with harness.client() as client:
        _post(client, SESSION)
        harness.now[0] += TTL_S + 1
        _post(client, SESSION)  # stale: a recompute is started
        assert client.portal is not None
        client.portal.call(harness.router.aclose)
        assert not harness.router._revalidating or all(
            t.done() for t in harness.router._revalidating.values()
        )


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


def test_two_viewers_with_different_licence_sets_never_share_an_entry() -> None:
    """What a viewer may see differs by data licence (ADR 0028, 0068): even a SHARED operation
    (keyed by role) has the licence set in its key, so a holder's answer is never served to
    a viewer without the licence."""
    holder = UserRecord("a", Role.TRADER, licences=("personal",))
    other = UserRecord("b", Role.TRADER)
    args = (1,)
    for name in ("MarketHistory", "FeatureTable"):
        held = response_key(*args, holder, "{ a }", None, name)
        assert held != response_key(*args, other, "{ a }", None, name)
    same = UserRecord("c", Role.TRADER, licences=("personal",))
    assert response_key(*args, holder, "{ a }", None, "MarketHistory") == response_key(
        *args, same, "{ a }", None, "MarketHistory"
    )  # a shared operation is still shared by viewers with the same set


def test_a_run_compaction_leaves_the_cache_key_unchanged(tmp_path: Path) -> None:
    # ADR 0078: compact-runs swaps a partition's index without a commit, so the published state
    # the key holds (visible_seq) does not move and no cached page is evicted or recomputed
    backend = LocalBackend(tmp_path / "data")
    day = date(2026, 10, 2)
    for k in range(1, 5):
        rows = [{"instrument_id": "EQ:A", "ts": pd.Timestamp(day, tz="UTC"), "cash_amount": 1.0}]
        frame = stamped(rows, day, f"r{k}", T0 + pd.Timedelta(hours=k).to_pytimedelta())
        backend.tables.write("events/dividend", day, f"r{k}", frame, pending=True)
        backend.tables.commit_run(f"r{k}", T0 + pd.Timedelta(days=1, hours=k).to_pytimedelta())
    reader, who = StoreReader(backend), UserRecord("ana", Role.ADMIN)

    def key() -> str:
        return response_key(
            reader.visible_seq(), who, SESSION, None, "Regime", reader.runs_generation()
        )

    before = key()
    assert backend.tables.compact_runs("events/dividend", day).runs_dropped == 2
    assert key() == before


# ADR 0077 decision 18: the version an answer was built from, as response headers the web
# client reads (a miss and a hit alike; absent for a shared operation, a write in flight, or
# with no release)
GENERATION, RELEASE = "x-config-generation", "x-release-id"


def _releases(release_id: str = "r1") -> ReleaseReads:
    def pinned(*_: Any) -> Any:
        raise AssertionError("an unlisted operation reads live")

    return ReleaseReads(current=lambda: SimpleNamespace(release_id=release_id), pinned=pinned)


def test_a_hit_and_a_miss_carry_the_same_generation(harness: Harness) -> None:
    harness.generation = 4
    client = harness.client()
    miss = _post(client, SESSION)
    opened = harness.opened
    hit = _post(client, SESSION)
    assert harness.opened == opened  # served from the cache
    assert miss.headers[GENERATION] == hit.headers[GENERATION] == "4"


def test_a_write_moves_the_generation(harness: Harness) -> None:
    client = harness.client()
    before = _post(client, SESSION).headers[GENERATION]
    harness.generation = 2
    assert _post(client, SESSION).headers[GENERATION] == "2" != before


def test_no_generation_while_a_write_is_in_flight(harness: Harness) -> None:
    harness.generation = None
    assert GENERATION not in _post(harness.client(), SESSION).headers


def test_a_shared_operation_carries_no_generation(harness: Harness) -> None:
    assert GENERATION not in _post(harness.client(), SHARED).headers


def test_the_release_id_is_on_a_miss_and_a_hit(harness: Harness) -> None:
    harness.releases = _releases("r7")
    client = harness.client()
    miss, hit = _post(client, SESSION), _post(client, SESSION)
    assert miss.headers[RELEASE] == hit.headers[RELEASE] == "r7"


def test_no_release_id_without_a_serving_release(harness: Harness) -> None:
    assert RELEASE not in _post(harness.client(), SESSION).headers


def test_cors_exposes_both_headers(harness: Harness) -> None:
    reply = harness.client().options(
        "/graphql",
        headers={"origin": "http://localhost:5173", "access-control-request-method": "POST"},
    )
    assert reply.status_code == 200
    response = harness.client().post(
        "/graphql", json={"query": SESSION}, headers={"origin": "http://localhost:5173"}
    )
    exposed = response.headers["access-control-expose-headers"].lower()
    assert GENERATION in exposed and RELEASE in exposed


def test_a_stale_serve_carries_the_generation_and_the_release(harness: Harness) -> None:
    harness.generation, harness.releases = 4, _releases("r7")
    with harness.client() as client:
        _post(client, SESSION)
        harness.now[0] += TTL_S + 1
        stale = _post(client, SESSION)  # served from the stale entry while it recomputes
        assert stale.headers[GENERATION] == "4" and stale.headers[RELEASE] == "r7"
