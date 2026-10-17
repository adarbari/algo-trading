import asyncio
import json
import threading
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, cast

import pytest

from algotrade_api.graphql import warm
from algotrade_api.graphql.warm import CacheWarmer
from algotrade_api.main import _start_warming


@dataclass
class _Reader:
    seq: int = 1

    def visible_seq(self) -> int:
        return self.seq


@dataclass
class _Session:
    date: date
    newer: object = None


@dataclass
class _Ctx:
    session: _Session
    reader: _Reader


def _once(warmer: CacheWarmer) -> bool:
    pending = warmer.begin()
    if pending is None:
        return False
    warmer.finish(pending)
    return True


def test_it_warms_at_start_and_after_each_publish_or_new_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    warmed: list[tuple[date, int]] = []
    monkeypatch.setattr(
        warm, "warm", lambda c, _f, home: warmed.append((c.session.date, c.reader.seq))
    )
    reader, session = _Reader(), _Session(date(2026, 10, 8))
    warmer = CacheWarmer(lambda: _Ctx(session, reader))  # type: ignore[arg-type, return-value]
    assert _once(warmer) and not _once(warmer)  # nothing new: nothing read
    reader.seq = 2  # a publish
    assert _once(warmer)
    session.date = date(2026, 10, 9)  # the next session
    assert _once(warmer)
    assert warmed == [(date(2026, 10, 8), 1), (date(2026, 10, 8), 2), (date(2026, 10, 9), 2)]


def test_the_served_operations_are_replayed_between_the_home_steps_and_the_rest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []
    monkeypatch.setattr(warm, "home_steps", lambda c: [("home", lambda: order.append("home"))])
    monkeypatch.setattr(warm, "warm", lambda c, _f, home: order.append("rest"))

    async def replay() -> int:
        order.append("replay")
        return 3

    warmer = CacheWarmer(
        lambda: _Ctx(_Session(date(2026, 10, 8)), _Reader()),  # type: ignore[arg-type, return-value]
        every_s=0.01,
        replay=replay,
    )

    async def go() -> None:
        task = asyncio.create_task(warmer.run())
        await asyncio.sleep(0.2)
        task.cancel()

    asyncio.run(go())
    assert order == ["home", "replay", "rest"]


def test_a_failing_replay_does_not_stop_the_warm() -> None:
    async def boom() -> int:
        raise RuntimeError("no")

    warmer = CacheWarmer(lambda: None, replay=boom)  # type: ignore[arg-type, return-value]
    asyncio.run(warmer.replay_operations())  # logged, not raised


def test_seed_operations_lists_each_page_load_operation_once(tmp_path: Path) -> None:
    pages = {
        "pages": {
            "/a": [{"op": "Viewer", "query": "query Viewer { v }", "variables": {}}],
            "/b": [
                {"op": "Viewer", "query": "query Viewer { v }", "variables": {}},
                {"op": "X", "query": "query X($n: Int) { x }", "variables": {"n": 1}},
            ],
        }
    }
    file = tmp_path / "pages.json"
    file.write_text(json.dumps(pages))
    assert warm.seed_operations(file) == [
        ("query Viewer { v }", {}),
        ("query X($n: Int) { x }", {"n": 1}),
    ]
    assert warm.seed_operations(tmp_path / "missing.json") == []


def test_it_warms_when_a_session_becomes_complete_without_a_publish(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR 0062: the nightly's record flipping the served session saves no table."""
    warmed: list[date] = []
    monkeypatch.setattr(warm, "warm", lambda c, _f, home: warmed.append(c.session.date))
    session = _Session(date(2026, 10, 8), newer="2026-10-09 failing")
    warmer = CacheWarmer(lambda: _Ctx(session, _Reader()))  # type: ignore[arg-type, return-value]
    assert _once(warmer) and not _once(warmer)
    session.date, session.newer = date(2026, 10, 9), None  # the retry completed 10-09
    assert _once(warmer)
    assert warmed == [date(2026, 10, 8), date(2026, 10, 9)]


def test_a_failed_warm_is_logged_and_tried_again(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    calls: list[int] = []

    def flaky(_ctx: Any, _frames: Any, home: bool) -> None:
        calls.append(1)
        if len(calls) == 1:
            raise OSError("a store mid-publish")

    monkeypatch.setattr(warm, "warm", flaky)
    reader = _Reader()
    ctx = _Ctx(_Session(date(2026, 10, 8)), reader)
    warmer = CacheWarmer(lambda: ctx, every_s=0.01)  # type: ignore[arg-type, return-value]

    async def two_polls() -> None:
        task = asyncio.create_task(warmer.run())
        while len(calls) < 2:
            await asyncio.sleep(0.01)
        task.cancel()

    asyncio.run(asyncio.wait_for(two_polls(), 5))
    assert len(calls) == 2 and "warming the read cache failed" in caplog.text


def test_a_failing_step_does_not_stop_the_others(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    ran: list[str] = []

    def boom(_ctx: Any) -> None:
        raise ValueError("no data")

    monkeypatch.setattr(warm, "warm_market_frames", lambda c: ran.append("frames"))
    monkeypatch.setattr(warm, "load_completeness", lambda c, n: ran.append("completeness"))
    monkeypatch.setattr(warm, "load_regime", boom)
    monkeypatch.setattr(
        warm,
        "load_episodes",
        lambda configs: type("E", (), {"episodes": [type("X", (), {"key": "a"})]}),
    )
    monkeypatch.setattr(warm, "load_episode_signals", lambda c, k: ran.append(f"episode {k}"))
    ctx = type("C", (), {"configs": None})()
    warm.warm(ctx)  # type: ignore[arg-type]
    assert (
        ran == ["completeness", "completeness", "frames", "episode a"]
        and "regime failed" in caplog.text
    )


def test_it_runs_the_extra_steps_after_the_screen_rows_and_before_the_market_frames(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The Builder's first preview after a publish reads the saved run and its screen's frame:
    the screen rows first, then a step per screen (one failing does not stop the next), then
    the minutes-long market frames; with no extra steps (a test app) none of it."""
    ran: list[str] = []

    def step(screen: str) -> Any:
        def run() -> None:
            if screen == "b":
                raise ValueError("no data")
            ran.append(f"preview {screen}")

        return run

    monkeypatch.setattr(warm, "screen_rows", lambda c: ran.append("rows"))
    monkeypatch.setattr(warm, "warm_market_frames", lambda c: ran.append("frames"))
    monkeypatch.setattr(warm, "load_completeness", lambda c, n: None)
    monkeypatch.setattr(warm, "load_regime", lambda c: None)
    monkeypatch.setattr(warm, "load_screeners", lambda c: None)
    monkeypatch.setattr(warm, "load_ideas", lambda c, n: None)
    monkeypatch.setattr(warm, "load_edge_desk", lambda c: None)
    monkeypatch.setattr(warm, "load_episodes", lambda configs: type("E", (), {"episodes": []}))
    ctx = type("C", (), {"configs": None})()
    warm.warm(ctx, lambda c: [(f"preview {i}", step(i)) for i in "abc"])  # type: ignore[arg-type]
    assert ran == ["rows", "preview a", "preview c", "frames"] and "preview b failed" in caplog.text
    ran.clear()
    warm.warm(ctx)  # type: ignore[arg-type]
    assert ran == ["rows", "frames"]


def test_it_warms_what_the_ideas_page_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    """The home page (Ideas) asks for the resolved screeners, the ideas table and the edge desk:
    read into the cache before the first visit after a start or a publish, screeners first
    (the regime strip and the status strip need them too)."""
    ran: list[str] = []
    monkeypatch.setattr(warm, "load_screeners", lambda c: ran.append("screeners"))
    monkeypatch.setattr(warm, "screen_rows", lambda c: None)
    monkeypatch.setattr(warm, "warm_market_frames", lambda c: None)
    monkeypatch.setattr(warm, "load_completeness", lambda c, n: None)
    monkeypatch.setattr(warm, "load_regime", lambda c: None)
    monkeypatch.setattr(warm, "load_ideas", lambda c, n: ran.append(f"ideas {n}"))
    monkeypatch.setattr(warm, "load_edge_desk", lambda c: ran.append("edge desk"))
    monkeypatch.setattr(warm, "load_episodes", lambda configs: type("E", (), {"episodes": []}))
    warm.warm(type("C", (), {"configs": None})())  # type: ignore[arg-type]
    assert ran == ["screeners", "ideas 200", "edge desk"]


def test_warm_home_reads_only_the_home_steps(monkeypatch: pytest.MonkeyPatch) -> None:
    """What the app's start waits for: the home page's reads, never the market frames."""
    ran: list[str] = []
    for name in ("load_screeners", "screen_rows", "load_regime", "load_edge_desk"):
        monkeypatch.setattr(warm, name, lambda c, _n=name: ran.append(_n))
    monkeypatch.setattr(warm, "load_completeness", lambda c, n: ran.append("load_completeness"))
    monkeypatch.setattr(warm, "load_ideas", lambda c, n: ran.append("load_ideas"))
    monkeypatch.setattr(warm, "warm_market_frames", lambda c: ran.append("frames"))
    warm.CacheWarmer(lambda: cast(Any, object())).warm_home()
    assert "frames" not in ran and "load_ideas" in ran and "load_regime" in ran


def test_a_slow_home_warm_does_not_hold_the_start_past_its_cap(
    caplog: pytest.LogCaptureFixture,
) -> None:
    release = threading.Event()

    class Slow:
        def warm_home(self) -> None:
            release.wait(5)

        async def run(self) -> None:
            await asyncio.sleep(0)

    async def go() -> None:
        task = await _start_warming(cast(Any, Slow()), home_timeout_s=0.05)
        assert task is not None
        release.set()
        await task

    asyncio.run(go())
    assert "serving anyway" in caplog.text


def test_it_warms_the_admin_ingestion_grid_after_the_home_steps_not_before_serving(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Admin Ingestion page's 10-session grid (3 s of partition reads cold) is warmed by the
    task after the start, never by the home warm-up the start waits for."""
    ran: list[str] = []
    for name in ("load_screeners", "screen_rows", "load_regime", "load_edge_desk"):
        monkeypatch.setattr(warm, name, lambda c, _n=name: ran.append(_n))
    monkeypatch.setattr(warm, "load_ideas", lambda c, n: ran.append("load_ideas"))
    monkeypatch.setattr(warm, "load_completeness", lambda c, n: ran.append(f"grid {n}"))
    monkeypatch.setattr(warm, "warm_market_frames", lambda c: None)
    monkeypatch.setattr(warm, "load_episodes", lambda configs: type("E", (), {"episodes": []}))
    warm.CacheWarmer(lambda: cast(Any, object())).warm_home()
    assert "grid 10" not in ran
    ran.clear()
    warm.warm(cast(Any, type("C", (), {"configs": None})()))
    assert ran.index("grid 1") < ran.index("load_ideas") < ran.index("grid 10")
