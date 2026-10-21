"""``lower_priority``: the background priority every ingest process and its workers run at."""

import ctypes
import os
import subprocess
import sys
from pathlib import Path

import pytest

from algotrade.services.jobs.priority import lower_priority


def test_lower_priority_never_raises_and_asks_for_the_cpu_nice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    niced: list[int] = []
    monkeypatch.setattr(os, "nice", lambda n: niced.append(n) or 0)
    monkeypatch.setattr(sys, "platform", "linux")
    lower_priority(10)
    assert niced[-1] == 10  # the total, whatever the current value is
    monkeypatch.setattr(os, "nice", lambda n: (_ for _ in ()).throw(OSError("no")))
    lower_priority(10)  # swallowed
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(ctypes, "CDLL", lambda *a, **k: (_ for _ in ()).throw(OSError("no libc")))
    lower_priority(0)  # the disk policy failing is swallowed too


def test_spawned_workers_inherit_the_niceness_of_the_parent() -> None:
    """Why the CLI lowers its own priority once: the filing-text and edge-evaluation pools
    spawn workers that never call ``lower_priority`` themselves (2026-10-21: a backfill's
    workers ran at nice 0 and starved the API). Run in a child interpreter so the test
    process itself keeps its priority."""
    code = (
        "import multiprocessing, os\n"
        "from concurrent.futures import ProcessPoolExecutor\n"
        "from algotrade.services.jobs.priority import lower_priority\n"
        "if __name__ == '__main__':\n"
        "    lower_priority(7)\n"
        "    ctx = multiprocessing.get_context('spawn')\n"
        "    with ProcessPoolExecutor(1, mp_context=ctx) as pool:\n"
        "        print(os.nice(0), pool.submit(os.nice, 0).result())\n"
    )
    done = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)},
    )
    parent, child = (int(n) for n in done.stdout.split())
    assert parent >= 7 and child == parent


@pytest.mark.skipif(sys.platform != "darwin", reason="the disk policy is darwin's")
def test_the_disk_policy_really_changes_in_the_process_and_in_a_spawned_worker(
    tmp_path: Path,
) -> None:
    """The first version used type 1 (EINVAL, silently swallowed): the policy stayed 0."""
    code = (
        "import ctypes, multiprocessing\n"
        "from concurrent.futures import ProcessPoolExecutor\n"
        "from algotrade.services.jobs.priority import lower_priority\n"
        "def policy():\n"
        "    return ctypes.CDLL(None).getiopolicy_np(0, 0)\n"
        "if __name__ == '__main__':\n"
        "    lower_priority(5)\n"
        "    ctx = multiprocessing.get_context('spawn')\n"
        "    with ProcessPoolExecutor(1, mp_context=ctx) as pool:\n"
        "        print(policy(), pool.submit(policy).result())\n"
    )
    script = tmp_path / "policy.py"  # a file: spawn re-imports the main module by path
    script.write_text(code)
    done = subprocess.run(
        [sys.executable, str(script)],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)},
    )
    assert done.stdout.split() == ["2", "2"]
