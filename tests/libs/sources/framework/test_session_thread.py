"""``SessionThread``: one thread opens a session source lazily, keeps it between calls, fails
fast while the source is down, and reports a call that outlives its timeout."""

import threading
from collections.abc import Callable
from dataclasses import dataclass, field

import pytest

from algotrade_sources.framework.base import SessionUnavailableError
from algotrade_sources.framework.session_thread import SessionThread


@dataclass
class FakeSession:
    name: str = "fake"
    dataset: str = "fake"
    reason: str | None = None  # what probe says
    open_error: Exception | None = None
    events: list[str] = field(default_factory=list)
    threads: set[str] = field(default_factory=set)

    def probe(self) -> str | None:
        self.events.append("probe")
        return self.reason

    def open(self) -> None:
        self.threads.add(threading.current_thread().name)
        self.events.append("open")
        if self.open_error is not None:
            raise self.open_error

    def close(self) -> None:
        self.events.append("close")

    def fetch(self, request: object) -> bytes | None:
        return None

    def normalize(self, request: object, payload: bytes) -> None:
        return None


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def worker_name(session: FakeSession) -> str:
    session.threads.add(threading.current_thread().name)
    return threading.current_thread().name


def test_opens_once_on_its_own_thread_and_keeps_the_session() -> None:
    session = FakeSession()
    thread = SessionThread(session)
    first = thread.call(worker_name, 5)
    second = thread.call(worker_name, 5)
    assert first == second != threading.current_thread().name
    assert first.startswith("session-fake")
    assert session.events == ["probe", "open"] and session.threads == {first}
    assert thread.status() is None and thread.name == "fake"
    thread.close()
    assert session.events[-1] == "close"


def test_a_source_that_cannot_open_is_down_until_the_retry_window_ends() -> None:
    clock = Clock()
    session = FakeSession(reason="IB Gateway not reachable on 127.0.0.1:4002")
    thread = SessionThread(session, retry_after_s=30, clock=clock)
    with pytest.raises(SessionUnavailableError, match="not reachable"):
        thread.call(worker_name, 5)
    assert thread.status() == "IB Gateway not reachable on 127.0.0.1:4002"
    with pytest.raises(SessionUnavailableError, match="not reachable"):
        thread.call(worker_name, 5)  # fails at once: not even probed again
    assert session.events.count("probe") == 1
    clock.now, session.reason = 31.0, None
    assert thread.call(worker_name, 5)  # the window passed: probed, opened
    assert session.events.count("open") == 1
    thread.close()


def test_a_failed_open_marks_it_down() -> None:
    session = FakeSession(open_error=SessionUnavailableError("API not ready"))
    thread = SessionThread(session)
    with pytest.raises(SessionUnavailableError, match="API not ready"):
        thread.call(worker_name, 5)
    assert thread.status() == "API not ready"
    thread.close()


def test_losing_the_session_closes_it_and_other_errors_are_the_callers() -> None:
    session = FakeSession()
    thread = SessionThread(session)

    def lose(_: FakeSession) -> None:
        raise ConnectionError("Not connected")

    def wrong(_: FakeSession) -> None:
        raise LookupError("no such contract")

    with pytest.raises(LookupError):
        thread.call(wrong, 5)
    assert "close" not in session.events and thread.status() is None  # still open
    with pytest.raises(SessionUnavailableError, match="Not connected"):
        thread.call(lose, 5)
    assert session.events[-1] == "close"
    assert thread.status() is not None and "session lost" in str(thread.status())
    thread.close()


def test_a_call_past_its_timeout_fails_and_later_calls_are_busy_until_it_ends() -> None:
    session = FakeSession()
    thread = SessionThread(session)
    release = threading.Event()

    def slow(_: FakeSession) -> str:
        release.wait(5)
        return "late"

    with pytest.raises(SessionUnavailableError, match=r"no answer within 0\.05 s"):
        thread.call(slow, 0.05)
    assert "still running" in str(thread.status())
    with pytest.raises(SessionUnavailableError, match="still running"):
        thread.call(worker_name, 5)
    release.set()
    done: Callable[[FakeSession], str] = lambda _: "ok"  # noqa: E731
    for _ in range(100):  # the slow call finishes on the worker
        if thread.status() is None:
            break
        threading.Event().wait(0.01)
    assert thread.call(done, 5) == "ok"
    thread.close()
