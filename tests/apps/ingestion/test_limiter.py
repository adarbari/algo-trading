"""The shared vendor limiter (``sources/limiter.py``): one pace per key across processes."""

import subprocess
import sys
from itertools import pairwise
from pathlib import Path

import pytest

from algotrade_ingestion.sources.limiter import Limiter


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


SCRIPT = """
import sys, time
from pathlib import Path
from algotrade_ingestion.sources.limiter import Limiter
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
