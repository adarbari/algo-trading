"""The default session of every operation is the current serving release's (ADR 0077 decision 7,
ADR 0062): while the next session is complete but its release is not promoted, a listed operation
(pinned reads) and the ideas page, the status strip and the session date all show the same day;
the newer one is disclosed as ``PUBLISHING`` once the publishing delay has passed, a flip made by
the server's clock in the cached answer, never by the browser; without a release the ADR 0062
rule is exactly today's."""

import dataclasses
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from algotrade.config.user import UserContext
from algotrade.data import StoreReader
from algotrade.services.ondemand.screens import OnDemandScreens
from algotrade.services.serving.build import build_release
from algotrade.storage.backends.release.memory import MemoryReleaseStore
from algotrade.storage.runs import RunRecord, RunStatus
from algotrade_api.deps import ApiSettings
from algotrade_api.main import create_app
from algotrade_sources.framework.base import FixtureSource
from tests.contract.api.release_reads.test_cache_survives_commits import (
    OPERATIONS,
    World,
    bar_rows,
)
from tests.helpers.api_store import END, as_user, store_over, web_documents
from tests.helpers.ondemand_store import DAY as SESSION
from tests.helpers.ondemand_store import seeded_backend, site_configs
from tests.helpers.stored_frames import stamped

NEXT = END + timedelta(days=1)
NEXT_DAY = SESSION + timedelta(days=1)
DELAY = timedelta(minutes=15)
IDEAS = web_documents()["IdeasPage"]
STRIP = web_documents()["StatusStrip"]
DATE = web_documents()["SessionDate"]
PRICES, PRICES_VARIABLES = OPERATIONS["InstrumentPrices"]


@pytest.fixture
def world(golden_source: FixtureSource) -> Iterator[World]:
    yield World(golden_source)


def complete_next_session(w: World) -> datetime:
    """The nightly of ``NEXT`` finishes (bars committed, then its COMPLETE record): returns when."""
    w.commit("bars-next", "bars/1d", NEXT, bar_rows(NEXT))
    done = datetime(NEXT.year, NEXT.month, NEXT.day, 22, tzinfo=UTC)
    record = RunRecord(
        f"nightly-{NEXT}", "nightly", NEXT, done - timedelta(hours=1), RunStatus.COMPLETE, done
    )
    w.backend.runs.save(record)
    return done


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Any:
    """The API's clock: ``clock(now)`` sets what ``datetime.now`` answers in ``algotrade_api.main``
    (the serving of a request is made there: the release's day, that clock, the delay)."""
    held = [datetime(2030, 1, 1, tzinfo=UTC)]

    class Frozen(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> "Frozen":  # type: ignore[override]
            return cls.fromtimestamp(held[0].timestamp(), tz or UTC)

    monkeypatch.setattr("algotrade_api.main.datetime", Frozen)

    def set_clock(now: datetime) -> None:
        held[0] = now

    return set_clock


def days(w: World) -> dict[str, Any]:
    """The default session each kind of operation shows."""
    ideas = w.post(IDEAS, {"first": 3, "names": []}).json()["data"]["ideas"]["session"]
    strip = w.post(STRIP, {"admin": False}).json()["data"]["session"]
    plain = w.post(DATE, {}).json()["data"]["session"]["date"]
    prices = w.post(PRICES, PRICES_VARIABLES).json()["data"]["instrument"]["prices"]
    return {"ideas": ideas, "strip": strip["date"], "newer": strip["newer"], "date": plain,
            "prices": prices["end"]}  # fmt: skip


def test_every_operation_shows_the_released_session_while_the_next_is_unreleased(
    world: World, clock: Any
) -> None:
    done = complete_next_session(world)
    clock(done + timedelta(minutes=5))
    shown = days(world)
    assert {shown[k] for k in ("ideas", "strip", "date", "prices")} == {END.isoformat()}
    assert shown["newer"] is None  # inside the delay: the release is probably about to be promoted


def test_publishing_is_disclosed_by_the_servers_clock_in_the_cached_answer(
    world: World, clock: Any
) -> None:
    done = complete_next_session(world)
    clock(done + timedelta(minutes=14))
    assert days(world)["newer"] is None
    clock(done + DELAY)  # the same requests, a later clock: the answer flips
    flipped = days(world)
    assert flipped["newer"] == {"date": NEXT.isoformat(), "state": "PUBLISHING"}
    assert {flipped[k] for k in ("ideas", "strip", "date", "prices")} == {END.isoformat()}


def test_a_promoted_release_for_the_next_session_moves_every_operation_together(
    world: World, clock: Any
) -> None:
    done = complete_next_session(world)
    manifest = build_release(world.store.reader, world.releases, "test")
    assert manifest.session == NEXT.isoformat()
    world.releases.promote(manifest.release_id)
    clock(done + timedelta(hours=1))
    shown = days(world)
    assert shown["newer"] is None
    assert {shown[k] for k in ("ideas", "strip", "date")} == {NEXT.isoformat()}


def test_without_a_release_the_default_session_is_the_newest_complete_one_as_today(
    world: World, clock: Any
) -> None:
    done = complete_next_session(world)
    world.releases.state.current = None
    clock(done + timedelta(hours=1))
    shown = days(world)
    assert {shown[k] for k in ("ideas", "strip", "date")} == {NEXT.isoformat()}
    assert shown["newer"] is None  # ADR 0062: nothing newer is processing


def test_the_kill_switch_restores_the_live_default_session(world: World, clock: Any) -> None:
    done = complete_next_session(world)
    router = world.app.state.graphql
    router._releases = dataclasses.replace(router._releases, enabled=lambda: False)
    clock(done + DELAY)
    assert days(world)["date"] == NEXT.isoformat()


def test_a_request_builds_its_serving_once_so_the_key_and_the_body_agree(
    world: World, clock: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One ``Serving`` (one clock reading) per request: the key under which a body is cached and
    the context that computed it must not see different instants."""
    done = complete_next_session(world)
    clock(done + timedelta(minutes=14, seconds=59))
    reads: list[int] = []
    real = datetime
    instant = done + timedelta(minutes=14, seconds=59)

    class Counting(real):  # type: ignore[valid-type, misc]
        @classmethod
        def now(cls, tz: Any = None) -> Any:
            reads.append(1)
            return real.fromtimestamp(instant.timestamp(), tz or UTC)

    monkeypatch.setattr("algotrade_api.main.datetime", Counting)
    assert world.post(DATE, {}).status_code == 200
    assert len(reads) == 1


def test_run_with_no_date_while_a_release_is_pending_writes_the_released_session() -> None:
    """The screener Run, the builder preview and every REST read default to the same session as
    the pages (ADR 0077 decision 7): the web sends no date to Run."""
    backend, configs = seeded_backend(), site_configs()
    for day in (SESSION, NEXT_DAY):
        backend.tables.write(
            "bars/1d", day, f"bars-{day}", stamped(bar_rows(day), day, f"b{day}"), pending=True
        )
        backend.tables.commit_run(f"bars-{day}", datetime.now(UTC))
        done = datetime(day.year, day.month, day.day, 22, tzinfo=UTC)
        backend.runs.save(
            RunRecord(
                f"nightly-{day}",
                "nightly",
                day,
                done - timedelta(hours=1),
                RunStatus.COMPLETE,
                done,
            )
        )
        if day == SESSION:  # the release of SESSION is promoted before NEXT_DAY completes
            releases = MemoryReleaseStore(backend.tables)
            releases.promote(build_release(StoreReader(backend), releases, "test").release_id)
    store = store_over(backend, configs, UserContext("local"))
    app = create_app(
        ApiSettings("memory://", "config"),
        store,
        ondemand=OnDemandScreens(backend, configs),
        authenticator=as_user(),
        releases=releases,
    )
    with TestClient(app) as client:
        started = client.post("/screens/big_liquid/run")
        assert started.json()["session"] == SESSION.isoformat()  # not NEXT_DAY
        releases.state.current = None  # no release: the newest complete session, as before
        live = client.post("/screens/big_liquid/run")
        assert live.json()["session"] == NEXT_DAY.isoformat()
