"""The listed operations are answered from the current serving release (ADR 0077 decision 23):
once warm, commits, a same-session restatement, a saved run record, an old-date commit and a
publish of an unrelated table cost them nothing: no loader recomputes, no response is
recomputed, the bodies are byte-equal. An operation that is not listed does recompute (which
proves the counters work). A release that cannot be trusted is today's live path, uncached."""

import dataclasses
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from algotrade.config.site.users import Role, UserRecord
from algotrade.core.model.errors import ConfigurationError
from algotrade.data import StoreReader
from algotrade.services.read.context import Held, ResultCache
from algotrade.services.serving.build import build_release
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.backends.release.memory import MemoryReleaseStore
from algotrade.storage.backends.run_selection import StaleSnapshotError
from algotrade.storage.runs import RunRecord, RunStatus
from algotrade_api.deps import ApiSettings
from algotrade_api.graphql.context import RequestContext
from algotrade_api.graphql.response_cache import RELEASE_SHARED_OPERATIONS, ResponseCache
from algotrade_api.main import create_app
from algotrade_sources.framework.base import FixtureSource
from tests.conftest import REPO_ROOT  # noqa: F401
from tests.helpers.api_store import END, api_store, as_user, web_documents
from tests.helpers.stored_frames import stamped

START = "2022-01-03"

VARIABLES: dict[str, dict[str, Any]] = {
    "InstrumentPrices": {"key": "AAA", "start": START},
    "MarketHistory": {
        "names": ["market.regime_indicators@v1.curve_10y3m"],
        "start": START,
        "end": END.isoformat(),
        "points": 50,
    },
    "InstrumentEvents": {"key": "AAA"},
    "EtfHoldings": {"key": "BULL", "top": 5},
    "RegimeBands": {"start": START, "end": END.isoformat()},
    "RegimeEpisodes": {},
    "RegimeSignals": {},
}
# The web's own documents of the listed operations (gql.ts), with variables that answer from the
# API store (an ETF for the holdings, one name for the instrument reads).
OPERATIONS: dict[str, tuple[str, dict[str, Any]]] = {
    name: (web_documents()[name], variables) for name, variables in VARIABLES.items()
}
NOT_LISTED = "query Day { session { date } }"  # a USER_OPERATIONS name: keyed on the sequence


class Counts:
    """What the caches stored since ``reset``: a store is a miss that was computed."""

    def __init__(self) -> None:
        self.results = 0
        self.responses = 0

    def reset(self) -> None:
        self.results = self.responses = 0


@pytest.fixture
def counts(monkeypatch: pytest.MonkeyPatch) -> Counts:
    seen = Counts()
    real_result, real_response = ResultCache.put, ResponseCache.put
    real_held = Held.get_or_read

    def result_put(self: ResultCache, key: Any, value: Any) -> None:
        seen.results += 1
        real_result(self, key, value)

    def response_put(self: ResponseCache, key: str, body: bytes) -> None:
        seen.responses += 1
        real_response(self, key, body)

    def held_read(self: Held[Any], key: Any, read: Any) -> Any:
        item, read_now = real_held(self, key, read)
        seen.results += bool(read_now)  # a container's item read from the store is a recompute
        return item, read_now

    monkeypatch.setattr(Held, "get_or_read", held_read)
    monkeypatch.setattr(ResultCache, "put", result_put)
    monkeypatch.setattr(ResponseCache, "put", response_put)
    return seen


class World:
    """A fresh API store with a promoted release, the app over it, and the store's backend."""

    def __init__(self, source: FixtureSource) -> None:
        self.store, _ = api_store(source)
        self.backend: MemoryBackend = self.store.reader._backend  # type: ignore[attr-defined,assignment]
        self.releases = MemoryReleaseStore(self.backend.tables)
        manifest = build_release(self.store.reader, self.releases, "test")
        self.releases.promote(manifest.release_id)
        self.release_id = manifest.release_id
        self.session = manifest.session
        self.app: FastAPI = create_app(
            ApiSettings("memory://", "config"),
            self.store,
            authenticator=as_user(),
            releases=self.releases,
        )
        self.client = TestClient(self.app)

    def post(self, document: str, variables: dict[str, Any]) -> Any:
        return self.client.post("/graphql", json={"query": document, "variables": variables})

    def commit(self, run: str, table: str, day: Any, rows: list[dict[str, Any]], **kw: Any) -> None:
        frame = stamped(rows, day, run)
        self.backend.tables.write(table, day, run, frame, pending=True, **kw)
        self.backend.tables.commit_run(run, datetime.now(UTC))


@pytest.fixture
def world(golden_source: FixtureSource) -> Iterator[World]:
    yield World(golden_source)


def bar_rows(day: Any) -> list[dict[str, Any]]:
    bar = {"open": 9.0, "high": 9.0, "low": 9.0, "close": 9.0, "volume": 9.0}
    return [{"instrument_id": "EQ:AAA", "ts": pd.Timestamp(day, tz="UTC"), **bar}]


def six_commits(w: World) -> None:
    """What the nightly, the post-session, a backfill and the owner do after a release is live,
    on tables the listed operations read."""
    day = END
    w.commit("next-session", "bars/1d", day + timedelta(days=1), bar_rows(day + timedelta(days=1)))
    first_run = w.backend.tables.partition_runs("bars/1d", day)[0]
    w.commit(first_run, "bars/1d", day, bar_rows(day))  # a same-run restatement of S
    started = datetime(day.year, day.month, day.day, 23, tzinfo=UTC)
    w.backend.runs.save(RunRecord("job:screen-1", "job:screen", day, started, RunStatus.RUNNING))
    before = day - timedelta(days=1)
    old_run = w.backend.tables.partition_runs("bars/1d", before)[0]
    w.commit(old_run, "bars/1d", before, bar_rows(before))  # an old-date restatement
    market = [{"instrument_id": "MKT:US", "curve_10y3m": 0.5}]
    w.commit("market-next", "rollups/market/regime_indicators@v1", day + timedelta(days=1), market)
    quote = {"instrument_id": "EQ:AAA", "ts": pd.Timestamp(day, tz="UTC"), "right": "C"}
    w.commit("unrelated", "live/option_quotes", day, [quote | {"strike": 100.0, "bid": 1.0}])


five_commits = six_commits  # the name the equivalence test and the brief use


def test_every_listed_operation_answers_without_errors_over_the_store(world: World) -> None:
    assert set(OPERATIONS) == RELEASE_SHARED_OPERATIONS
    for name, (document, variables) in OPERATIONS.items():
        body = world.post(document, variables).json()
        assert "errors" not in body, (name, body.get("errors"))


def test_once_warm_six_commits_recompute_nothing_and_change_no_byte(
    world: World, counts: Counts
) -> None:
    before = {n: world.post(*OPERATIONS[n]).content for n in OPERATIONS}
    world.post(NOT_LISTED, {})
    counts.reset()
    five_commits(world)
    after = {n: world.post(*OPERATIONS[n]).content for n in OPERATIONS}
    assert (counts.results, counts.responses) == (0, 0)  # no loader ran, no response was missed
    assert after == before  # byte-equal
    world.post(NOT_LISTED, {})  # a listed-nowhere operation is keyed on the sequence: it recomputes
    assert counts.responses > 0


def test_with_the_response_cache_empty_no_loader_recomputes_either(
    world: World, counts: Counts
) -> None:
    """The loaders' own keys survive the commits too (a restart of the response cache, or an
    entry aged out, still costs no read)."""
    before = {n: world.post(*OPERATIONS[n]).content for n in OPERATIONS}
    five_commits(world)
    router = world.app.state.graphql
    router._cache._items.clear()
    router._cache._held = 0
    counts.reset()
    after = {n: world.post(*OPERATIONS[n]).content for n in OPERATIONS}
    assert counts.results == 0
    assert counts.responses == len(OPERATIONS)  # the bodies were rebuilt, from the same rows
    assert after == before


def test_without_a_current_release_every_read_is_live_and_not_kept(
    world: World, counts: Counts
) -> None:
    world.releases.state.current = None
    document, variables = OPERATIONS["InstrumentPrices"]
    counts.reset()
    assert world.post(document, variables).status_code == 200
    assert counts.responses == 0 and world.app.state.graphql._cache.held == 0


def test_a_destructive_operation_since_the_build_makes_the_release_untrusted(
    world: World, counts: Counts
) -> None:
    world.backend.tables.drop("rollups/instrument/other@v1")
    document, variables = OPERATIONS["RegimeBands"]
    counts.reset()
    assert world.post(document, variables).status_code == 200
    assert counts.responses == 0


def test_the_kill_switch_turns_every_read_live_and_uncached(world: World, counts: Counts) -> None:
    router = world.app.state.graphql
    router._releases = dataclasses.replace(router._releases, enabled=lambda: False)
    counts.reset()
    document, variables = OPERATIONS["InstrumentPrices"]
    assert world.post(document, variables).status_code == 200
    assert counts.responses == 0


def test_a_pin_the_store_no_longer_holds_answers_live_and_is_not_kept(
    world: World, counts: Counts, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = StoreReader.table_range

    def lost(self: StoreReader, *args: Any, **kwargs: Any) -> Any:
        if self.pin is not None:
            raise StaleSnapshotError("the release's version was discarded")
        return real(self, *args, **kwargs)

    monkeypatch.setattr(StoreReader, "table_range", lost)
    document, variables = OPERATIONS["InstrumentPrices"]
    counts.reset()
    answer = world.post(document, variables)
    assert answer.status_code == 200 and "errors" not in answer.json()
    assert answer.json()["data"]["instrument"]["prices"]["bars"]
    assert counts.responses == 0  # the live answer after a lost pin is not cached


def test_a_document_named_like_a_listed_operation_that_selects_more_goes_live_and_uncached(
    world: World, counts: Counts
) -> None:
    """The name alone is not trusted: a role-wide key must hold nothing of the caller."""
    document, variables = OPERATIONS["InstrumentPrices"]
    sneaky = document.replace("instrument(key: $key) {", "viewer { id } instrument(key: $key) {")
    assert sneaky != document
    counts.reset()
    answer = world.post(sneaky, variables)
    assert answer.status_code == 200 and answer.json()["data"]["viewer"]["id"]
    assert counts.responses == 0 and world.app.state.graphql._cache.held == 0
    deeper = document.replace("bars {", "bars { open ").replace(
        "prices(start: $start)", "prices(start: $start)"
    )
    assert world.post(deeper, variables).status_code == 200  # a deeper field of the listed one


def test_a_malformed_kill_switch_config_is_the_live_path_not_a_500(
    world: World, counts: Counts
) -> None:
    router = world.app.state.graphql

    def boom() -> bool:
        raise ConfigurationError("nightly.toml: [serving] is malformed")

    router._releases = dataclasses.replace(router._releases, enabled=boom)
    document, variables = OPERATIONS["InstrumentPrices"]
    counts.reset()
    assert world.post(document, variables).status_code == 200
    assert counts.responses == 0


def test_a_release_request_explains_causes_from_the_pinned_reader(world: World) -> None:
    router = world.app.state.graphql
    release = router._releases.resolve()
    assert release is not None
    viewer = UserRecord("ana", Role.ADMIN)
    pinned = RequestContext(
        router._opener, viewer, router._stores_opener, release, router._releases.pinned
    )
    live = RequestContext(router._opener, viewer, router._stores_opener)
    assert pinned.stores().reader.pin == release.seq  # type: ignore[union-attr]
    assert live.stores().reader.pin is None  # type: ignore[union-attr]


NESTED = (
    "query EtfHoldings($key: String!, $top: Int!) { instrument(key: $key) { instrumentId isEtf "
    "holdings(top: $top) { asOf source total items { rank name symbol weight assetClass "
    'instrument { symbol features(names: ["hv20_pct"]) { name value } } } } } }'
)


def test_a_caller_dependent_field_deep_in_a_listed_document_goes_live_and_uncached(
    world: World, counts: Counts
) -> None:
    """``features(names: [<a user's expression feature>])`` below the checked depth: the role-wide
    key would hold one user's answer for every user of the role. The whole tree is checked."""
    variables = OPERATIONS["EtfHoldings"][1]
    counts.reset()
    answer = world.post(NESTED, variables)
    assert answer.status_code == 200
    assert counts.responses == 0 and world.app.state.graphql._cache.held == 0
    again = world.post(NESTED, variables)
    assert again.status_code == 200 and counts.responses == 0  # never kept, for anyone


@pytest.mark.parametrize(
    "tricky",
    [
        "query EtfHoldings($key: String!, $top: Int!) { instrument(key: $key) { ...F } } "
        "fragment F on Instrument { instrumentId }",
        "query EtfHoldings($key: String!, $top: Int!) "
        "{ instrument(key: $key) { id: instrumentId } }",
        "query EtfHoldings($key: String!, $top: Int!) { instrument(key: $key) "
        "{ instrumentId @include(if: true) } }",
        "query EtfHoldings($key: String!, $top: Int!) { instrument(key: $key) { instrumentId } "
        "viewer { id } }",
    ],
)
def test_a_fragment_an_alias_a_directive_or_an_extra_root_goes_live_and_uncached(
    world: World, counts: Counts, tricky: str
) -> None:
    counts.reset()
    assert world.post(tricky, OPERATIONS["EtfHoldings"][1]).status_code == 200
    assert counts.responses == 0 and world.app.state.graphql._cache.held == 0
