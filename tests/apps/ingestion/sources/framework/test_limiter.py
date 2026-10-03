"""The shared vendor limiter (``sources/framework/limiter.py``): one adaptive pace per key,
across processes (Retry-After holds, back-off, error-rate slowdown, recovery, run stats)."""

import subprocess
import sys
from dataclasses import replace
from itertools import pairwise
from pathlib import Path

import pytest

from algotrade_ingestion.sources.framework.limiter import IDLE_RESET_S, Limiter, Pacing


class FakeTime:
    def __init__(self, start: float = 1000.0) -> None:
        self.now, self.slept = start, []  # type: ignore[var-annotated]

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def test_requests_are_spaced_and_the_pace_is_shared_through_the_file(tmp_path: Path) -> None:
    t = FakeTime()
    first = Limiter("massive", 12.5, tmp_path, t.sleep, t.clock)
    second = Limiter("massive", 12.5, tmp_path, t.sleep, t.clock)  # e.g. another process
    first.wait()
    t.now += 2.5
    second.wait()  # sees the first one's request through the lock file
    assert t.slept == [10.0]
    t.now += 20
    first.wait()
    assert t.slept == [10.0]  # long enough ago: no wait
    other = Limiter("sec", 12.5, tmp_path, t.sleep, t.clock)
    other.wait()
    assert t.slept == [10.0]  # keys are independent
    assert sorted(p.name for p in tmp_path.iterdir()) == ["massive.lock", "sec.lock"]


def test_hold_pauses_the_next_request_even_unpaced(tmp_path: Path) -> None:
    t = FakeTime()
    cboe = Limiter("cboe", 0.0, tmp_path, t.sleep, t.clock)
    cboe.wait()
    assert t.slept == []
    Limiter("cboe", 0.0, tmp_path, t.sleep, t.clock).hold(30.0)
    cboe.wait()
    assert t.slept == [30.0]


def test_bad_keys_and_unreadable_state(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="invalid limiter key"):
        Limiter("../x", 1.0, tmp_path)
    (tmp_path / "sec.lock").write_text("garbage")
    t = FakeTime()
    Limiter("sec", 1.0, tmp_path, t.sleep, t.clock).wait()  # starts afresh
    assert t.slept == []


CBOE = Pacing(1.0, max_interval_s=5.0, speedup_after=4, error_window=10, max_error_rate=0.1)


def test_429_holds_every_process_for_retry_after_then_backs_off_once(tmp_path: Path) -> None:
    t = FakeTime()
    first = Limiter("cboe", CBOE, tmp_path, t.sleep, t.clock)
    second = Limiter("cboe", CBOE, tmp_path, t.sleep, t.clock)  # another process
    stats = first.track()
    first.wait()
    first.throttled(47.0)  # Retry-After: 47
    assert first.interval == 1.5  # x backoff_factor
    second.throttled(47.0)  # the other worker's 429 from the same burst: no second back-off
    assert second.interval == 1.5
    second.wait()
    assert t.slept == [47.0]  # the hold is shared through the file
    for _ in range(5):
        first.throttled(60.0)  # a long ban: backs off each fresh hold, up to the ceiling
        first.wait()
    assert first.interval == 5.0
    assert (stats.throttled_429, stats.backoffs_429) == (6, 6)  # second tracks its own
    assert stats.retry_after_wait_s == 47.0 + 5 * 60.0


def test_error_rate_above_the_limit_slows_down_once_per_window(tmp_path: Path) -> None:
    t = FakeTime()
    limiter = Limiter("cboe", replace(CBOE, speedup_after=100), tmp_path, t.sleep, t.clock)
    stats = limiter.track()
    for outcome in ["ok"] * 8 + ["error"] * 2:  # 20% errors over a full window of 10
        limiter.record(outcome)  # type: ignore[arg-type]
    assert limiter.interval == 1.5 and stats.error_rate_slowdowns == 1
    for outcome in ["error"] * 2 + ["ok"] * 7:  # the window starts again: not full yet
        limiter.record(outcome)  # type: ignore[arg-type]
    assert limiter.interval == 1.5
    limiter.record("error")  # full again, 30% errors
    assert limiter.interval == 2.25 and stats.error_rate_slowdowns == 2 and stats.errors == 5


def test_missing_objects_are_not_errors(tmp_path: Path) -> None:
    t = FakeTime()
    limiter = Limiter("cboe", replace(CBOE, speedup_after=100), tmp_path, t.sleep, t.clock)
    stats = limiter.track()
    for _ in range(30):
        limiter.record("missing")  # e.g. Cboe's 403 AccessDenied for a symbol with no chain
    assert limiter.interval == 1.0 and stats.errors == 0 and stats.error_rate_slowdowns == 0


def test_speeds_up_after_a_success_streak_but_never_below_the_floor(tmp_path: Path) -> None:
    t = FakeTime()
    pacing = replace(CBOE, start_interval_s=1.2, speedup_factor=1.1)
    limiter = Limiter("cboe", pacing, tmp_path, t.sleep, t.clock)
    stats = limiter.track()
    for _ in range(3):
        limiter.record("ok")
    limiter.record("error")  # breaks the streak
    for _ in range(3):
        limiter.record("ok")
    assert limiter.interval == 1.2
    limiter.record("ok")  # 4 in a row
    assert limiter.interval == pytest.approx(1.2 / 1.1)
    for _ in range(40):
        limiter.record("ok")
    assert limiter.interval == 1.0 and stats.speedups >= 2
    assert stats.interval_min_s == 1.0 and stats.interval_max_s == 1.2


def test_state_resets_to_the_start_after_an_idle_spell(tmp_path: Path) -> None:
    t = FakeTime()
    limiter = Limiter("cboe", CBOE, tmp_path, t.sleep, t.clock)
    limiter.wait()
    limiter.throttled(10.0)
    t.now += 11
    limiter.wait()
    assert limiter.interval == 1.5
    t.now += IDLE_RESET_S + 1  # e.g. the next night
    assert Limiter("cboe", CBOE, tmp_path, t.sleep, t.clock).interval == 1.0


def test_stats_cover_what_happened_while_tracked(tmp_path: Path) -> None:
    t = FakeTime()
    limiter = Limiter("cboe", CBOE, tmp_path, t.sleep, t.clock)
    limiter.wait()  # before tracking: not counted
    stats = limiter.track()
    limiter.wait()
    limiter.record("ok")
    limiter.untrack(stats)
    limiter.wait()
    out = stats.as_dict()
    assert out["requests"] == 1 and out["limiter_wait_s"] == 1.0
    assert out["interval_start_s"] == out["interval_final_s"] == 1.0
    assert set(out) == {
        "requests",
        "errors",
        "throttled_429",
        "retry_after_wait_s",
        "limiter_wait_s",
        "backoffs_429",
        "error_rate_slowdowns",
        "speedups",
        "interval_start_s",
        "interval_final_s",
        "interval_min_s",
        "interval_max_s",
    }


def test_previous_state_format_and_pacing_validation(tmp_path: Path) -> None:
    (tmp_path / "cboe.lock").write_text("1000.0")  # the old format: the last request time
    t = FakeTime(1000.5)
    Limiter("cboe", CBOE, tmp_path, t.sleep, t.clock).wait()
    assert t.slept == [0.5]
    (tmp_path / "cboe.lock").write_text('{"interval": "x"}')
    Limiter("cboe", CBOE, tmp_path, t.sleep, t.clock).wait()  # starts afresh
    with pytest.raises(ValueError, match="below min_interval_s"):
        Pacing(2.0, max_interval_s=1.0)
    with pytest.raises(ValueError, match="start_interval_s"):
        Pacing(1.0, max_interval_s=2.0, start_interval_s=3.0)
    with pytest.raises(ValueError, match="factor"):
        Pacing(1.0, backoff_factor=0.5)
    with pytest.raises(ValueError, match="error_window"):
        Pacing(1.0, error_window=0)
    with pytest.raises(ValueError, match="max_error_rate"):
        Pacing(1.0, max_error_rate=2)
    with pytest.raises(ValueError, match="min_interval_s"):
        Pacing(-1.0)


SCRIPT = """
import sys, time
from pathlib import Path
from algotrade_ingestion.sources.framework.limiter import IDLE_RESET_S, Limiter, Pacing
limiter = Limiter("vendor", 0.3, Path(sys.argv[1]))
for _ in range(3):
    limiter.wait()
    print(time.time(), flush=True)
"""


def test_two_processes_share_one_pace(tmp_path: Path) -> None:
    procs = [
        subprocess.Popen([sys.executable, "-c", SCRIPT, str(tmp_path)], stdout=subprocess.PIPE)
        for _ in range(2)
    ]
    stamps = sorted(float(x) for p in procs for x in p.communicate(timeout=30)[0].split())
    assert len(stamps) == 6
    gaps = [b - a for a, b in pairwise(stamps)]
    assert min(gaps) >= 0.2  # six requests, never closer than the interval (minus jitter)
