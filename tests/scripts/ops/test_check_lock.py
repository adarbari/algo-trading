"""`scripts/ops/check_lock.sh`: one `make check` per worktree; a stale lock is taken over."""

import os
import subprocess
import time
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "ops" / "check_lock.sh"


def _lock(tmp_path: Path, *cmd: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "CHECK_LOCK_DIR": str(tmp_path / "var" / "check.lock.d")}
    return subprocess.run(
        ["bash", str(SCRIPT), *cmd], env=env, capture_output=True, text=True, check=False
    )


def test_runs_the_command_passes_its_status_and_releases(tmp_path: Path) -> None:
    assert _lock(tmp_path, "true").returncode == 0
    assert _lock(tmp_path, "sh", "-c", "exit 3").returncode == 3
    assert not (tmp_path / "var" / "check.lock.d").exists()


def test_a_second_run_is_refused_while_the_first_runs(tmp_path: Path) -> None:
    env = {**os.environ, "CHECK_LOCK_DIR": str(tmp_path / "var" / "check.lock.d")}
    first = subprocess.Popen(["bash", str(SCRIPT), "sleep", "30"], env=env)
    try:
        for _ in range(50):
            if (tmp_path / "var" / "check.lock.d" / "started").exists():
                break
            time.sleep(0.1)
        second = _lock(tmp_path, "true")
        assert second.returncode == 1
        assert f"PID {first.pid}" in second.stderr and "never with pkill" in second.stderr
    finally:
        first.terminate()
        first.wait()
    assert not (tmp_path / "var" / "check.lock.d").exists()  # the trap released it
    assert _lock(tmp_path, "true").returncode == 0


def test_a_lock_of_a_dead_pid_is_stale(tmp_path: Path) -> None:
    lock = tmp_path / "var" / "check.lock.d"
    lock.mkdir(parents=True)
    dead = subprocess.Popen(["true"])
    dead.wait()
    (lock / "pid").write_text(f"{dead.pid}\n")
    assert _lock(tmp_path, "true").returncode == 0


def test_a_live_takeover_guard_refuses_a_second_taker(tmp_path: Path) -> None:
    lock = tmp_path / "var" / "check.lock.d"
    lock.mkdir(parents=True)
    (lock / "pid").write_text("999999\n")  # stale lock
    guard = tmp_path / "var" / "check.lock.d.takeover"
    guard.mkdir()
    holder = subprocess.Popen(["sleep", "30"])  # another run mid-takeover
    try:
        (guard / "pid").write_text(f"{holder.pid}\n")
        out = _lock(tmp_path, "true")
        assert out.returncode == 1 and "taking over" in out.stderr
    finally:
        holder.terminate()
        holder.wait()
    # The guard's PID is dead: a crashed takeover. It is never cleared by another run (two runs
    # clearing it at once would both get inside); the operator is told the command.
    out = _lock(tmp_path, "true")
    assert out.returncode == 1 and "crashed takeover" in out.stderr and "rm -rf" in out.stderr
    (guard / "pid").unlink()
    guard.rmdir()
    assert _lock(tmp_path, "true").returncode == 0


def test_an_empty_leftover_guard_refuses_with_the_command(tmp_path: Path) -> None:
    """A takeover killed before it wrote its PID leaves an empty guard: refuse, never hang."""
    lock = tmp_path / "var" / "check.lock.d"
    lock.mkdir(parents=True)
    (lock / "pid").write_text("999999\n")
    (tmp_path / "var" / "check.lock.d.takeover").mkdir()
    out = _lock(tmp_path, "true")
    assert out.returncode == 1 and "crashed takeover" in out.stderr


def test_a_stale_takeover_moves_the_old_lock_aside(tmp_path: Path) -> None:
    lock = tmp_path / "var" / "check.lock.d"
    lock.mkdir(parents=True)
    (lock / "pid").write_text("999999\n")
    assert _lock(tmp_path, "true").returncode == 0
    assert list((tmp_path / "var").iterdir()) == []  # no check.lock.d, no *.stale.* left
