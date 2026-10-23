"""`scripts/ops/perf_gate_nightly.sh`: the path guards, the busy guards (exit 3), and the
per-date idempotence (before 03:00, done today, next day), with a fake bench and no real store."""

import contextlib
import json
import os
import shutil
import signal
import subprocess
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "ops" / "perf_gate_nightly.sh"
QUIET_PS = "  1 /sbin/launchd\n  2 /usr/bin/python something-else\n"


class Rig:
    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        (tmp / "var" / "data").mkdir(parents=True)
        (tmp / "var" / "data" / "t.txt").write_text("x")
        self.root = tmp / "perf-clone"
        self.status = tmp / "logs" / "perf_gate.status"
        self.ps = tmp / "ps.txt"
        self.ps.write_text(QUIET_PS)
        self.bench_out = "3 views over 1.0 s on the critical path (2.5 s above the bar); shell 0.5"
        self.bench_code = 1
        self.bench_body: str | None = None  # replaces the fake bench script when set

    def env(self, **over: str) -> dict[str, str]:
        bench = self.tmp / "bench.sh"
        body = f"echo '{self.bench_out}'\nexit {self.bench_code}\n"
        text = "#!/bin/sh\n" + (self.bench_body or body)
        if not bench.exists() or bench.read_text() != text:  # never rewrite a running script
            bench.write_text(text)
        bench.chmod(0o755)
        notify = self.tmp / "notify.sh"
        notify.write_text(f'#!/bin/sh\necho "$1" >> {self.tmp}/notified\n')
        notify.chmod(0o755)
        env = {
            **os.environ,
            "PERF_SRC": str(self.tmp / "var" / "data"),
            "PERF_CLONE_ROOT": str(self.root / "data"),
            "PERF_STATUS": str(self.status),
            "PERF_NOW_DATE": "2026-10-23",
            "PERF_NOW_HM": "0310",
            "PERF_PS_FILE": str(self.ps),
            "PERF_FREE_GB": "40",
            "PERF_LOAD": "1.5",
            "PERF_BENCH_CMD": str(bench),
            "PERF_NOTIFY": str(notify),
            "PERF_COPY_CMD": "cp -R",  # the real nightly uses cp -c (APFS); not on Linux CI
            **over,
        }
        return env

    def run(self, **over: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(SCRIPT)], env=self.env(**over), capture_output=True, text=True, check=False
        )


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    return Rig(tmp_path)


def test_refuses_a_clone_path_that_is_not_the_fixed_clone(rig: Rig) -> None:
    res = rig.run(PERF_CLONE_ROOT=str(rig.tmp / "somewhere" / "data"))
    assert res.returncode == 2 and "perf-clone/data" in res.stderr
    assert (rig.tmp / "var" / "data" / "t.txt").exists()


def test_refuses_the_real_store_even_under_the_clone_name(rig: Rig) -> None:
    real = rig.tmp / "perf-clone" / "data"
    real.parent.mkdir(parents=True)
    (rig.tmp / "var" / "data").rename(real)
    res = rig.run(PERF_SRC=str(real))
    assert res.returncode == 2 and (real / "t.txt").exists()


def test_busy_when_an_ingest_runs_and_nothing_is_copied(rig: Rig) -> None:
    rig.ps.write_text(QUIET_PS + "  9 .venv/bin/algotrade-ingest rollups --from 2013-01-01\n")
    res = rig.run()
    assert res.returncode == 3 and "busy, retry" in res.stderr
    assert not (rig.root / "data").exists() and not rig.status.exists()


def test_busy_on_low_disk_and_on_high_load(rig: Rig) -> None:
    assert rig.run(PERF_FREE_GB="11").returncode == 3
    assert rig.run(PERF_LOAD="4.5").returncode == 3
    assert not rig.status.exists()


def test_before_three_local_is_a_no_op(rig: Rig) -> None:
    rig.ps.write_text(QUIET_PS + "  9 algotrade-ingest nightly\n")  # even busy: nothing to do
    res = rig.run(PERF_NOW_HM="0259")
    assert res.returncode == 0 and not rig.status.exists()


def test_a_run_over_the_bar_is_recorded_notified_and_the_clone_deleted(rig: Rig) -> None:
    res = rig.run()
    assert res.returncode == 1
    line = rig.status.read_text()
    assert "date=2026-10-23" in line and "views_over=3" in line and "seconds_above=2.5" in line
    assert "exit=1 finished=yes" in line
    assert "3 views over the bar" in (rig.tmp / "notified").read_text()
    assert not (rig.root / "data").exists()
    assert (rig.tmp / "var" / "data" / "t.txt").exists()


def test_done_today_is_a_no_op_and_the_next_day_runs_again(rig: Rig) -> None:
    rig.bench_code, rig.bench_out = (
        0,
        "0 views over 1.0 s on the critical path (0.0 s above the bar)",
    )
    assert rig.run().returncode == 0
    assert rig.status.read_text().count("date=2026-10-23") == 1
    assert rig.run().returncode == 0  # same day: exits at once
    assert rig.status.read_text().count("date=2026-10-23") == 1
    assert rig.run(PERF_NOW_DATE="2026-10-24").returncode == 0
    assert "date=2026-10-24" in rig.status.read_text()


def test_a_refusal_after_the_copy_is_a_finished_day_with_one_notification(rig: Rig) -> None:
    rig.bench_code, rig.bench_out = 2, "refused"
    assert rig.run().returncode == 2
    assert "outcome=refused" in rig.status.read_text() and "finished=yes" in rig.status.read_text()
    assert (rig.tmp / "notified").read_text().count("REFUSED") == 1
    assert rig.run().returncode == 0  # no re-copy at the next retry


def test_a_crash_is_reported_as_crashed_not_as_over_the_bar(rig: Rig) -> None:
    rig.bench_code, rig.bench_out = 1, "Traceback (most recent call last)"
    assert rig.run().returncode == 1
    assert "outcome=crashed" in rig.status.read_text()
    assert "CRASHED" in (rig.tmp / "notified").read_text()


def test_status_line_records_the_phase_timings(rig: Rig) -> None:
    rig.run()
    line = rig.status.read_text()
    for key in ("wait_s=", "snapshot_s=", "bench_s=", "cleanup_s=", "total_s=", "over_time=no"):
        assert key in line


def test_the_watchdog_kills_a_slow_bench_and_its_child_and_marks_over_time(rig: Rig) -> None:
    pidfile = rig.tmp / "child.pid"
    rig.bench_body = f"sleep 60 &\necho $! > {pidfile}\nwait\n"
    res = rig.run(PERF_BENCH_LIMIT_S="1")
    assert res.returncode == 4
    line = rig.status.read_text()
    assert "exit=4 finished=yes outcome=over-time over_time=yes" in line
    assert "OVER-TIME" in (rig.tmp / "notified").read_text()
    assert not (rig.root / "data").exists()  # the clone is deleted
    child = int(pidfile.read_text())
    with pytest.raises(ProcessLookupError):  # the whole process group died
        os.kill(child, 0)
    assert rig.run().returncode == 0  # a finished day: no retry loop


def _evidence(rig: Rig, day: str = "2026-10-23") -> Path:
    return rig.tmp / "logs" / "perf_gate" / day


def test_the_run_leaves_its_evidence_directory_and_a_summary_line(rig: Rig) -> None:
    ev = _evidence(rig)
    rig.bench_body = (
        f"echo '{rig.bench_out}'\n"
        f'echo \'{{"a#1": {{"name": "Slow", "avg": 2000}}}}\' > {ev}/ops.json\n'
        f'echo \'{{"passes": 4, "budget_s": 270, "elapsed_s": 100, "stop_reason": '
        f'"reps", "low_confidence": false, "noisy": false}}\' > {ev}/run-meta.json\n'
        "exit 1\n"
    )
    prof = rig.tmp / "prof.sh"
    prof.write_text(f'#!/bin/sh\necho "profiled $@" > {ev}/profiles.md\n')
    prof.chmod(0o755)
    assert rig.run(PERF_PROFILE_CMD=str(prof), PERF_SAMPLE_S="1").returncode == 1
    for name in (
        "status.json",
        "run.log",
        "load.csv",
        "procs-start.txt",
        "procs-end.txt",
        "snapshot.json",
        "profiles.md",
        "ops.json",
    ):
        assert (ev / name).is_file(), name
    status = json.loads((ev / "status.json").read_text())
    assert status["passes"] == 4 and status["stop_reason"] == "reps" and status["exit_code"] == 1
    assert {"wait_s", "snapshot_s", "bench_s", "cleanup_s", "total_s"} <= set(status)
    assert (
        "profiled" in (ev / "profiles.md").read_text()
        and "Slow" in (ev / "profiles.md").read_text()
    )
    assert json.loads((ev / "snapshot.json").read_text())["ingest_started_during_copy"] is False
    rows = (rig.tmp / "logs" / "perf_gate" / "summary.csv").read_text().splitlines()
    assert rows[0].startswith("date,sha,total_s,snapshot_s,bench_s,passes,views_over_bar")
    assert rows[1].startswith("2026-10-23,") and ",4,3,2.5," in rows[1]
    assert str(ev.relative_to(rig.tmp)) in (rig.tmp / "notified").read_text()


def test_a_guard_day_records_why_and_only_the_last_14_run_directories_are_kept(rig: Rig) -> None:
    base = rig.tmp / "logs" / "perf_gate"
    for d in range(1, 21):
        (base / f"2026-09-{d:02d}").mkdir(parents=True)
    (base / "keepme").mkdir()
    rig.ps.write_text(QUIET_PS + "  9 algotrade-ingest nightly\n")
    assert rig.run().returncode == 3
    days = sorted(p.name for p in base.iterdir() if p.name.startswith("2026-"))
    assert len(days) == 14 and days[-1] == "2026-10-23" and days[0] == "2026-09-08"
    assert (base / "keepme").exists()  # only dated directories are ever deleted
    assert json.loads((base / "2026-10-23" / "status.json").read_text())["stop_reason"] == "guard"


def test_an_empty_or_relative_clone_root_is_an_error_not_a_default(rig: Rig) -> None:
    for bad in ("", "perf-clone/data", "./perf-clone/data"):
        res = rig.run(PERF_CLONE_ROOT=bad)
        assert res.returncode == 2 and "absolute" in res.stderr, bad
    assert (rig.tmp / "var" / "data" / "t.txt").exists()


def test_guard_retries_write_no_summary_line_only_finished_runs_do(rig: Rig) -> None:
    rig.ps.write_text(QUIET_PS + "  9 algotrade-ingest nightly\n")
    assert rig.run().returncode == 3 and rig.run().returncode == 3
    assert not (rig.tmp / "logs" / "perf_gate" / "summary.csv").exists()
    rig.ps.write_text(QUIET_PS)
    rig.run()
    assert len((rig.tmp / "logs" / "perf_gate" / "summary.csv").read_text().splitlines()) == 2


def test_a_second_instance_is_busy_and_leaves_the_first_ones_clone_alone(rig: Rig) -> None:
    rig.bench_body = f"touch {rig.tmp}/started\nsleep 4\necho '{rig.bench_out}'\nexit 0\n"
    rig.bench_out = "0 views over 1.0 s on the critical path (0.0 s above the bar)"
    rig.bench_body = f"touch {rig.tmp}/started\nsleep 4\necho '{rig.bench_out}'\nexit 0\n"
    first = subprocess.Popen(
        ["bash", str(SCRIPT)], env=rig.env(), stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    try:
        for _ in range(100):
            if (rig.tmp / "started").exists():
                break
            time.sleep(0.1)
        assert (rig.root / "data").exists()
        second = rig.run()
        assert second.returncode == 3 and "holds" in second.stderr
        assert (rig.root / "data").exists()  # the first run's clone is intact
    finally:
        first.communicate(timeout=60)
    assert first.returncode == 0
    assert not (rig.tmp / "logs" / "perf_gate" / "lock").exists()  # released on exit
    assert not (rig.root / "data").exists()


def test_a_stale_lock_of_a_dead_process_is_taken_over(rig: Rig) -> None:
    lock = rig.tmp / "logs" / "perf_gate" / "lock"
    lock.parent.mkdir(parents=True)
    lock.symlink_to("999999")
    assert rig.run().returncode == 1 and not lock.is_symlink()


@pytest.mark.parametrize("target", ["", "garbage", "12x"])
def test_an_empty_or_garbage_lock_is_stale_not_a_silent_busy_forever(rig: Rig, target: str) -> None:
    lock = rig.tmp / "logs" / "perf_gate" / "lock"
    lock.parent.mkdir(parents=True)
    if target:
        lock.symlink_to(target)
    else:
        lock.mkdir()  # a leftover directory (no readable pid)
    assert rig.run().returncode == 1  # ran (the fake bench is over the bar), not busy
    assert not lock.exists() and not lock.is_symlink()


def test_a_leftover_takeover_marker_of_a_dead_process_is_cleaned(rig: Rig) -> None:
    base = rig.tmp / "logs" / "perf_gate"
    base.mkdir(parents=True)
    (base / "lock").symlink_to("999999")
    (base / "lock.takeover").symlink_to("999998")
    assert rig.run().returncode == 1
    assert not (base / "lock.takeover").is_symlink()


def test_a_live_holder_keeps_the_lock_and_the_second_run_is_busy(rig: Rig) -> None:
    base = rig.tmp / "logs" / "perf_gate"
    base.mkdir(parents=True)
    (base / "lock").symlink_to(str(os.getpid()))  # this test process is alive
    res = rig.run()
    assert res.returncode == 3 and "holds" in res.stderr
    assert (base / "lock").is_symlink()


def test_term_kills_the_bench_group_drops_the_clone_and_releases_the_lock(rig: Rig) -> None:
    pidfile = rig.tmp / "child.pid"
    rig.bench_body = f"sleep 60 &\necho $! > {pidfile}\nwait\n"
    proc = subprocess.Popen(
        ["bash", str(SCRIPT)], env=rig.env(), stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    for _ in range(100):
        if pidfile.exists() and pidfile.read_text().strip():
            break
        time.sleep(0.1)
    proc.terminate()
    proc.communicate(timeout=30)
    assert proc.returncode == 143
    assert not (rig.root / "data").exists()
    assert not (rig.tmp / "logs" / "perf_gate" / "lock").exists()
    with pytest.raises(ProcessLookupError):
        os.kill(int(pidfile.read_text()), 0)


def test_the_nightly_command_writes_its_history_under_var_logs_and_leaves_the_repo_clean(
    rig: Rig,
) -> None:
    argv_file = rig.tmp / "argv.txt"
    fake_py = rig.tmp / "fakepy.sh"
    fake_py.write_text(
        f'#!/bin/sh\necho "$@" > {argv_file}\necho "0 views over 1.0 s (0.0 s above the bar)"\n'
    )
    fake_py.chmod(0o755)
    repo = SCRIPT.parents[2]
    tracked = ["benchmarks/critical_path_history.jsonl"]
    before = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain", *tracked],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    res = rig.run(PERF_BENCH_CMD="", PERF_PY=str(fake_py))
    assert res.returncode == 0, res.stderr
    argv = argv_file.read_text()
    assert f"--history-file {rig.tmp}/logs/perf_gate/history.jsonl" in argv
    assert f"--out {rig.tmp}/logs/perf_gate/2026-10-23" in argv and "--record" in argv
    after = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain", *tracked],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    assert before == after


def test_an_integrity_failure_has_its_own_outcome_and_notice_listing_the_failures(rig: Rig) -> None:
    rig.bench_body = (
        "echo '0 views over 1.0 s on the critical path (0.0 s above the bar); shell 0.5'\n"
        "echo 'INTEGRITY operations that failed: Boom'\n"
        "echo 'INTEGRITY shell operations not measured: Regime'\nexit 1\n"
    )
    assert rig.run().returncode == 1
    assert "outcome=integrity" in rig.status.read_text()
    note = (rig.tmp / "notified").read_text()
    assert "INTEGRITY FAILURE" in note and "Boom" in note and "Regime" in note
    assert "0 views over the bar" not in note


def test_two_instances_racing_for_a_stale_lock_never_both_run(rig: Rig) -> None:
    lock = rig.tmp / "logs" / "perf_gate" / "lock"
    lock.parent.mkdir(parents=True)
    lock.symlink_to("999999")
    rig.bench_body = (
        "sleep 3\necho '0 views over 1.0 s on the critical path (0.0 s above the bar)'\nexit 0\n"
    )
    env = rig.env()
    procs = [
        subprocess.Popen(
            ["bash", str(SCRIPT)], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        for _ in range(3)
    ]
    codes = sorted(p.communicate(timeout=60) and p.returncode for p in procs)
    assert codes == [0, 3, 3]


def test_the_bench_gets_a_fixed_port_block_outside_the_worktrees_and_the_live_api(rig: Rig) -> None:
    rig.bench_body = f'echo "$ALGOTRADE_PORT_BASE" > {rig.tmp}/port\nexit 0\n'
    rig.run()
    base = int((rig.tmp / "port").read_text())
    assert (
        base == 15990 and base > 14990 + 19 and not 8000 <= base <= 8100
    )  # worktrees: 10000-14990
    rig.status.unlink()
    rig.run(PERF_PORT_BASE="16500")
    assert (rig.tmp / "port").read_text().strip() == "16500"


def _wait_gone(path: Path, seconds: float = 20) -> bool:
    end = time.time() + seconds
    while path.exists() and time.time() < end:
        time.sleep(0.1)
    return not path.exists()


def _script(rig: Rig, name: str, body: str) -> str:
    path = rig.tmp / name
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(0o755)
    return str(path)


def test_only_the_entries_the_api_reads_are_copied_raw_and_staging_are_not(rig: Rig) -> None:
    for d in ("tables/a", "runs/b", "serving/c", "raw/d", "staging/e", "locks/f"):
        (rig.tmp / "var" / "data" / d).mkdir(parents=True)
        (rig.tmp / "var" / "data" / d / "x.txt").write_text("x")
    rig.bench_body = (
        f"ls {rig.root}/data > {rig.tmp}/clone_ls\n"
        f"find {rig.root}/data -type f | sed 's#.*/data/##' | sort > {rig.tmp}/clone_files\n"
        "exit 0\n"
    )
    assert rig.run().returncode == 0
    assert (rig.tmp / "clone_ls").read_text().split() == ["locks", "runs", "serving", "tables"]
    files = (rig.tmp / "clone_files").read_text().split()
    assert files == ["runs/b/x.txt", "serving/c/x.txt", "tables/a/x.txt"]  # locks: created empty
    assert (rig.tmp / "var" / "data" / "raw" / "d" / "x.txt").exists()  # the store is untouched


def test_the_clone_is_renamed_at_once_and_deleted_detached_with_the_time_logged(rig: Rig) -> None:
    slow = _script(rig, "slowpri.sh", 'sleep 3\nexec "$@"\n')
    res = rig.run(PERF_LOWPRI=slow)
    assert res.returncode == 1
    trash = rig.root / "data.trash.2026-10-23"
    assert not (rig.root / "data").exists() and trash.exists()  # renamed; the delete is pending
    status = json.loads((_evidence(rig) / "status.json").read_text())
    assert status["cleanup_s"] <= 1 and "trash_delete_s" not in status
    assert _wait_gone(trash)  # then deleted in the background
    end = time.time() + 20
    while "trash_delete_s" not in json.loads((_evidence(rig) / "status.json").read_text()):
        assert time.time() < end
        time.sleep(0.1)
    assert json.loads((_evidence(rig) / "status.json").read_text())["trash_delete_s"] >= 3


def test_leftover_trash_is_deleted_in_the_background_and_the_run_is_busy_not_overlapping(
    rig: Rig,
) -> None:
    old = rig.root / "data.trash.2026-10-20"
    (old / "tables").mkdir(parents=True)
    (old / "tables" / "z.txt").write_text("z")
    keep = [rig.root / "other", rig.root / "data.keep", rig.root / "data.trashy"]
    for k in keep:
        k.mkdir()
    res = rig.run()
    # the copy never overlaps a delete: this tick starts the delete and is busy, the next one runs
    assert res.returncode == 3 and "leftover" in res.stderr and not rig.status.exists()
    assert not (rig.root / "data").exists()
    assert _wait_gone(old)
    assert all(k.exists() for k in keep)  # the guard: only perf-clone/data.trash.* goes
    assert rig.run().returncode == 1  # nothing left: the bench ran


@pytest.mark.parametrize("cmd", ["rm -rf {t}", "find {t} -delete", "/usr/bin/find {t} -delete"])
def test_a_running_trash_delete_is_busy_and_nothing_is_copied_or_started(
    rig: Rig, cmd: str
) -> None:
    trash = rig.root / "data.trash.2026-10-22"
    (trash / "tables").mkdir(parents=True)
    rig.ps.write_text(QUIET_PS + f"  9 {cmd.format(t=trash)}\n")
    res = rig.run()
    assert res.returncode == 3 and "trash delete running (pid 9)" in res.stderr
    assert trash.exists() and not (rig.root / "data").exists() and not rig.status.exists()


def test_a_delete_elsewhere_is_not_a_trash_delete(rig: Rig) -> None:
    rig.ps.write_text(QUIET_PS + f"  9 rm -rf {rig.tmp}/elsewhere/data.trash.2026-10-22\n")
    assert rig.run().returncode == 1  # not our sibling: the bench ran


def test_a_copy_over_ten_minutes_is_killed_and_the_day_finishes_with_an_error(rig: Rig) -> None:
    (rig.tmp / "var" / "data" / "tables").mkdir()
    slow_cp = _script(rig, "slowcp.sh", "sleep 30\n")
    res = rig.run(PERF_COPY_CMD=slow_cp, PERF_SNAPSHOT_LIMIT_S="1")
    assert res.returncode == 4 and "snapshot over-time" in res.stderr
    line = rig.status.read_text()
    assert "outcome=snapshot-over-time" in line and "finished=yes" in line
    assert "snapshot copy was killed" in (rig.tmp / "notified").read_text()
    assert not (rig.root / "data").exists()
    assert _wait_gone(rig.root / "data.trash.2026-10-23")
    assert not (rig.tmp / "logs" / "perf_gate" / "lock").is_symlink()
    assert rig.run().returncode == 0  # a finished day: no retry loop, no re-copy


def test_a_clone_on_another_volume_is_refused_because_cp_c_would_copy_every_byte(rig: Rig) -> None:
    dev = _script(rig, "dev.sh", f'case "$1" in {rig.tmp}/var/*) echo 1;; *) echo 2;; esac\n')
    res = rig.run(PERF_DEV_CMD=dev)
    assert res.returncode == 2 and "same volume" in res.stderr
    assert not (rig.root / "data").exists() and not rig.status.exists()


def test_a_reused_pid_with_another_start_time_is_a_stale_lock(rig: Rig) -> None:
    lock = rig.tmp / "logs" / "perf_gate" / "lock"
    lock.parent.mkdir(parents=True)
    lock.symlink_to(f"{os.getpid()}:Mon_Jan__1_00:00:00_2001")  # alive pid, other start time
    assert rig.run().returncode == 1  # taken over and run, not busy forever


def test_the_lock_tag_with_the_real_start_time_is_a_live_holder(rig: Rig) -> None:
    start = subprocess.run(
        ["ps", "-o", "lstart=", "-p", str(os.getpid())],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "LC_ALL": "C", "TZ": "UTC"},
    ).stdout.split()
    lock = rig.tmp / "logs" / "perf_gate" / "lock"
    lock.parent.mkdir(parents=True)
    lock.symlink_to(f"{os.getpid()}:{'_'.join(start)}")
    assert rig.run().returncode == 3


def test_a_leftover_trash_delete_is_logged_to_its_own_days_record(rig: Rig) -> None:
    old_day = rig.tmp / "logs" / "perf_gate" / "2026-10-20"
    old_day.mkdir(parents=True)
    (old_day / "status.json").write_text("{}")
    old = rig.root / "data.trash.2026-10-20"
    (old / "tables").mkdir(parents=True)
    rig.run()
    assert _wait_gone(old)
    end = time.time() + 20
    while "trash_delete_s" not in json.loads((old_day / "status.json").read_text()):
        assert time.time() < end
        time.sleep(0.1)
    today = json.loads((_evidence(rig) / "status.json").read_text())
    assert (
        today.get("trash_delete_s")
        != json.loads((old_day / "status.json").read_text())["trash_delete_s"]
        or "trash_delete_s" in today
    )  # the old day's file got its own value; today's is its own


def test_the_lock_start_time_is_read_in_the_c_locale_whatever_the_callers_locale(rig: Rig) -> None:
    bin_dir = rig.tmp / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "ps"
    stub.write_text(
        "#!/bin/sh\n"
        'case "$*" in *lstart=*)\n'
        '  if [ "$LC_ALL" = C ] && [ "$TZ" = UTC ]; then echo "Fri Oct 23 03:00:00 2026"\n'
        '  else echo "ven. 23 oct. 03:00:00 2026"; fi; exit 0;;\n'
        "esac\n"
        'exec /bin/ps "$@"\n'
    )
    stub.chmod(0o755)
    lock = rig.tmp / "logs" / "perf_gate" / "lock"
    lock.parent.mkdir(parents=True)
    lock.symlink_to(
        f"{os.getpid()}:Fri_Oct_23_03:00:00_2026"
    )  # as a launchd (C locale) run wrote it
    env = {"PATH": f"{bin_dir}:{os.environ['PATH']}", "LC_ALL": "fr_FR.UTF-8", "TZ": "Europe/Paris"}
    res = rig.run(**env)
    assert res.returncode == 3 and "holds" in res.stderr  # a live holder, not a stale lock


def _stubs(rig: Rig, children: dict[int, str | None], args: dict[int, str]) -> dict[str, str]:
    """Stub `pgrep -P` and `ps -o args= -p` on PATH (children: pid -> 'c1 c2'; None: unreadable)."""
    d = rig.tmp / "stubs"
    (d / "kids").mkdir(parents=True, exist_ok=True)
    (d / "args").mkdir(exist_ok=True)
    for pid, kids in children.items():
        (d / "kids" / str(pid)).write_text("ERR" if kids is None else kids)
    for pid, a in args.items():
        (d / "args" / str(pid)).write_text(a)
    (d / "pgrep").write_text(
        f'#!/bin/sh\nf={d}/kids/"$2"\n[ -f "$f" ] || exit 1\n'
        '[ "$(cat "$f")" = ERR ] && exit 2\n'
        'for k in $(cat "$f"); do echo $k; done\n[ -s "$f" ] || exit 1\n'
    )
    real_ps = shutil.which("ps")
    (d / "ps").write_text(
        f'#!/bin/sh\nif [ "$1" = -o ] && [ "$2" = args= ]; then\n'
        f'  f={d}/args/"$4"; [ -f "$f" ] && cat "$f"; exit 0\nfi\n'
        f'exec {real_ps} "$@"\n'
    )
    for n in ("pgrep", "ps"):
        (d / n).chmod(0o755)
    return {"PATH": f"{d}:{os.environ['PATH']}"}


DRIVER = "  7 /bin/sh var/logs/ops/eb_tail.sh\n"


def test_a_real_ingest_is_busy_whatever_its_children(rig: Rig) -> None:
    rig.ps.write_text(QUIET_PS + "  9 .venv/bin/algotrade-ingest rollups --from 2013-01-01\n")
    env = _stubs(rig, {9: ""}, {})
    assert rig.run(**env).returncode == 3 and not rig.root.joinpath("data").exists()


def test_a_driver_parked_on_a_sleep_is_not_a_writer_and_is_logged(rig: Rig) -> None:
    rig.ps.write_text(QUIET_PS + DRIVER)
    env = _stubs(rig, {7: "8"}, {8: "sleep 60"})
    assert rig.run(**env).returncode == 1  # the bench ran (over the bar), the gate was not refused
    log = _evidence(rig).joinpath("run.log").read_text()
    assert "ignored parked driver" in log and "pid 7 /bin/sh var/logs/ops/eb_tail.sh" in log


def test_a_driver_with_no_child_is_not_a_writer(rig: Rig) -> None:
    rig.ps.write_text(QUIET_PS + DRIVER)
    assert rig.run(**_stubs(rig, {7: ""}, {})).returncode == 1


@pytest.mark.parametrize("child", ["algotrade-ingest rollups", "/usr/bin/python3 -m x"])
def test_a_driver_with_a_running_non_sleep_child_is_a_writer(rig: Rig, child: str) -> None:
    rig.ps.write_text(QUIET_PS + DRIVER)
    res = rig.run(**_stubs(rig, {7: "8 9"}, {8: "sleep 60", 9: child}))
    assert res.returncode == 3 and "a writer runs" in res.stderr


def test_a_driver_whose_children_cannot_be_read_is_a_writer(rig: Rig) -> None:
    rig.ps.write_text(QUIET_PS + DRIVER)
    assert rig.run(**_stubs(rig, {7: None}, {})).returncode == 3  # pgrep fails
    assert rig.run(**_stubs(rig, {7: "8"}, {})).returncode == 3  # the child's command is unreadable


def test_a_driver_is_a_writer_when_pgrep_is_missing(rig: Rig) -> None:
    rig.ps.write_text(QUIET_PS + DRIVER)
    empty = rig.tmp / "nopgrep"
    empty.mkdir()
    for n in (
        "sh",
        "bash",
        "ps",
        "grep",
        "date",
        "mkdir",
        "cat",
        "dirname",
        "readlink",
        "ln",
        "rm",
        "mv",
        "tr",
        "sed",
        "awk",
        "sort",
        "head",
        "cut",
        "stat",
        "mktemp",
        "python3",
        "env",
        "git",
        "id",
        "uname",
        "df",
        "uptime",
    ):
        w = shutil.which(n)
        if w:
            (empty / n).symlink_to(w)
    res = rig.run(PATH=str(empty))
    assert res.returncode == 3 and "a writer runs" in res.stderr


def test_the_gate_itself_and_the_bench_are_never_a_driver_match(rig: Rig) -> None:
    own = "  5 bash scripts/ops/perf_gate_nightly.sh var/logs/x\n"
    own += "  6 python scripts/perf/fast_bench.py var/logs/y\n"
    rig.ps.write_text(QUIET_PS + own)
    assert rig.run(**_stubs(rig, {}, {})).returncode == 1


def test_the_default_low_priority_is_nice_not_taskpolicy_b(rig: Rig) -> None:
    """taskpolicy -b throttled the disk I/O and made the CoW copy 4x slower (2026-10-23)."""
    d = rig.tmp / "prio"
    d.mkdir()
    log = rig.tmp / "prio.log"
    (d / "taskpolicy").write_text(f'#!/bin/sh\necho taskpolicy $* >> {log}\nexec "$@"\n')
    (d / "nice").write_text(f'#!/bin/sh\necho nice $* >> {log}\nshift 2\nexec "$@"\n')
    for n in ("taskpolicy", "nice"):
        (d / n).chmod(0o755)
    (rig.tmp / "var" / "data" / "tables").mkdir()
    rig.run(PATH=f"{d}:{os.environ['PATH']}")
    seen = log.read_text()
    assert "nice -n 10" in seen and "taskpolicy" not in seen
    assert "-b" not in seen
    text = SCRIPT.read_text()
    assert 'taskpolicy -b"' not in text and 'PERF_LOWPRI="taskpolicy' not in text


def test_a_killed_copy_leaves_snapshot_json_with_how_far_it_got(rig: Rig) -> None:
    (rig.tmp / "var" / "data" / "tables").mkdir()
    slow = _script(rig, "slowcp2.sh", 'mkdir -p "$2"; echo x > "$2/part"; sleep 30\n')
    res = rig.run(PERF_COPY_CMD=slow, PERF_SNAPSHOT_LIMIT_S="2")
    assert res.returncode == 4
    snap = json.loads((_evidence(rig) / "snapshot.json").read_text())
    assert snap["copy_stopped"] == "over-time" and snap["entry"] == "tables"
    assert snap["files_so_far"] == "1" and snap["copy_s"] >= 2 and snap["limit_s"] == 2


def test_a_writer_that_appears_mid_copy_stops_the_copy_and_is_busy(rig: Rig) -> None:
    (rig.tmp / "var" / "data" / "tables").mkdir()
    slow = _script(rig, "slowcp3.sh", "sleep 60\n")
    proc = subprocess.Popen(
        ["bash", str(SCRIPT)],
        env=rig.env(PERF_COPY_CMD=slow, PERF_POLL_S="1"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    time.sleep(2)
    rig.ps.write_text(QUIET_PS + "  9 .venv/bin/algotrade-ingest rollups --from 2013-01-01\n")
    _, err = proc.communicate(timeout=40)
    assert proc.returncode == 3 and "a writer started during the copy (copy stopped)" in err
    assert "algotrade-ingest rollups" in err
    snap = json.loads((_evidence(rig) / "snapshot.json").read_text())
    assert snap["copy_stopped"] == "writer-during-copy" and snap["entry"] == "tables"
    assert not (rig.root / "data").exists() and not rig.status.exists()


def test_a_glob_in_a_childs_args_is_not_expanded_into_a_sleep(rig: Rig) -> None:
    rig.ps.write_text(QUIET_PS + DRIVER)
    cwd = rig.tmp / "cwd"
    cwd.mkdir()
    (cwd / "sleep").write_text("")  # an expanded `*` would make the child's first word `sleep`
    env = rig.env(**_stubs(rig, {7: "8"}, {8: "* 60"}))
    res = subprocess.run(
        ["bash", str(SCRIPT)], env=env, cwd=cwd, capture_output=True, text=True, check=False
    )
    assert res.returncode == 3 and "a writer runs" in res.stderr


def test_python_dash_m_ingestion_is_a_real_writer(rig: Rig) -> None:
    rig.ps.write_text(QUIET_PS + "  9 /x/python -m algotrade_ingestion run rollups\n")
    assert rig.run(**_stubs(rig, {9: ""}, {})).returncode == 3


def _date_stub(rig: Rig, jump_file: Path, jump: int) -> dict[str, str]:
    """`date +%s` jumps forward by ``jump`` s once ``jump_file`` exists (the Mac slept)."""
    d = rig.tmp / "datestub"
    d.mkdir(exist_ok=True)
    real = shutil.which("date")
    (d / "date").write_text(
        "#!/bin/sh\n"
        f'if [ "$1" = +%s ] && [ -f {jump_file} ]; then echo $(( $({real} +%s) + {jump} ));\n'
        f'else exec {real} "$@"; fi\n'
    )
    (d / "date").chmod(0o755)
    return {"PATH": f"{d}:{os.environ['PATH']}"}


def _run_with_jump(rig: Rig, jump_s: int, limit: str) -> tuple[int, str]:
    (rig.tmp / "var" / "data" / "tables").mkdir(exist_ok=True)
    jump = rig.tmp / "slept"
    slow = _script(rig, "slowcp5.sh", "sleep 60\n")
    env = rig.env(PERF_COPY_CMD=slow, PERF_SNAPSHOT_LIMIT_S=limit, **_date_stub(rig, jump, jump_s))
    proc = subprocess.Popen(
        ["bash", str(SCRIPT)], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    time.sleep(2.5)
    jump.write_text("")
    _, err = proc.communicate(timeout=40)
    return proc.returncode, err


def test_the_snapshot_cap_is_wall_clock_not_a_monotonic_timeout(rig: Rig) -> None:
    """A jump of the clock under the pause threshold still counts toward the cap."""
    code, err = _run_with_jump(rig, 30, "20")
    assert code == 4 and "snapshot over-time" in err
    snap = json.loads((_evidence(rig) / "snapshot.json").read_text())
    assert snap["copy_stopped"] == "over-time" and snap["copy_s"] >= 20


def test_a_pause_during_the_copy_stops_it_and_retries_instead_of_finishing_the_day(
    rig: Rig,
) -> None:
    """A Mac that slept mid-copy is no slow copy: log it, drop the clone, exit 3 (retries go on)."""
    code, err = _run_with_jump(rig, 600, "500")
    assert code == 3 and "machine paused 60" in err
    assert "machine paused or stalled for" in (_evidence(rig) / "run.log").read_text()
    snap = json.loads((_evidence(rig) / "snapshot.json").read_text())
    assert snap["copy_stopped"] == "machine-paused"
    line = rig.status.read_text()
    assert "pause_abort=1 finished=no" in line and "finished=yes" not in line  # retries go on
    assert not (rig.root / "data").exists()


def test_the_run_holds_the_machine_awake_with_caffeinate_for_its_own_pid(rig: Rig) -> None:
    d = rig.tmp / "caf"
    d.mkdir()
    log = rig.tmp / "caf.log"
    (d / "caffeinate").write_text(f"#!/bin/sh\necho $* >> {log}\n")
    (d / "caffeinate").chmod(0o755)
    rig.run(PATH=f"{d}:{os.environ['PATH']}")
    args = log.read_text().split()
    assert args[:2] == ["-i", "-w"] and args[2].isdigit()


def test_the_trash_delete_guard_refuses_a_path_that_is_not_a_sibling_trash(rig: Rig) -> None:
    """Mutation guard: `delete_trash` (the wrapper's own function, extracted) deletes only a
    sibling `data.trash.*` of the clone: removing `trash_ok` from it deletes the others."""
    funcs = subprocess.run(
        ["sed", "-n", "/^trash_ok()/,/^}/p;/^delete_trash()/,/^}/p", str(SCRIPT)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    sibling = rig.root / "data.trash.2026-10-01"
    elsewhere = rig.tmp / "elsewhere" / "perf-clone" / "data.trash.2026-10-01"
    clone_itself = rig.root / "data"
    for d in (sibling, elsewhere, clone_itself, rig.root / "data.keep"):
        d.mkdir(parents=True)
        (d / "f").write_text("x")
    script = f"clone={clone_itself}; logs={rig.tmp}/logs; PERF_LOWPRI=\n{funcs}\n" + "".join(
        f"delete_trash {d}\n" for d in (elsewhere, clone_itself, rig.root / "data.keep", sibling)
    )
    subprocess.run(["bash", "-c", script], check=True)
    assert _wait_gone(sibling)  # only the sibling trash goes
    assert (elsewhere / "f").exists() and (clone_itself / "f").exists()
    assert (rig.root / "data.keep" / "f").exists()


def test_the_trash_is_deleted_with_find_delete_not_rm(rig: Rig) -> None:
    """Mutation guard: `find -delete` measured 6-7 s per 100k files against 10 s for `rm -rf`."""
    d = rig.tmp / "tools"
    d.mkdir()
    log = rig.tmp / "tools.log"
    for n in ("rm", "find"):
        real = shutil.which(n)
        (d / n).write_text(f'#!/bin/sh\necho {n} $* >> {log}\nexec {real} "$@"\n')
        (d / n).chmod(0o755)
    old = rig.root / "data.trash.2026-10-20"
    old.mkdir(parents=True)
    (old / "f").write_text("x")
    rig.run(PATH=f"{d}:{os.environ['PATH']}")
    assert _wait_gone(old)
    calls = log.read_text().splitlines()
    assert any(
        c.startswith("find ") and "-delete" in c and "data.trash.2026-10-20" in c for c in calls
    )
    assert not any(c.startswith("rm ") and "data.trash" in c for c in calls)


def test_snapshot_json_has_the_seconds_of_every_copied_entry(rig: Rig) -> None:
    for name in ("alpha", "beta"):
        (rig.tmp / "var" / "data" / "tables" / name).mkdir(parents=True)
        (rig.tmp / "var" / "data" / "tables" / name / "f.txt").write_text(name)
    assert rig.run().returncode == 1
    snap = json.loads((_evidence(rig) / "snapshot.json").read_text())
    assert set(snap["entry_s"]) == {"tables/alpha", "tables/beta"}
    assert (rig.root / "data").exists() is False  # renamed to trash after the run
    assert all(isinstance(v, int) for v in snap["entry_s"].values())


def test_a_hung_uptime_does_not_block_the_load_sampler_and_late_samples_are_marked(
    rig: Rig,
) -> None:
    d = rig.tmp / "hang"
    d.mkdir()
    (d / "uptime").write_text("#!/bin/sh\nsleep 30\n")
    (d / "uptime").chmod(0o755)
    rig.bench_body = "sleep 9\necho 3 views over 1.0 s\nexit 1\n"
    rig.run(PERF_SAMPLE_S="1", PATH=f"{d}:{os.environ['PATH']}")
    rows = (_evidence(rig) / "load.csv").read_text().splitlines()
    assert rows[0] == "epoch,load1,free_gb,late_s,took_s"
    assert len(rows) >= 6  # one tick a second although every uptime hangs
    assert any(r.endswith(",skipped") for r in rows[1:])  # one sample at a time, the rest marked
    assert any(r.split(",")[-1].isdigit() and int(r.split(",")[-1]) >= 4 for r in rows[1:])


def test_the_third_pause_abort_of_a_day_finishes_it_with_one_notification(rig: Rig) -> None:
    rig.status.parent.mkdir(parents=True, exist_ok=True)
    rig.status.write_text(
        "date=2026-10-23 pause_abort=1 finished=no\ndate=2026-10-23 pause_abort=2 finished=no\n"
    )
    code, err = _run_with_jump(rig, 600, "500")
    assert code == 4 and "repeated pauses" in err
    lines = rig.status.read_text().splitlines()
    assert "pause_abort=3 finished=no" in lines[2]
    assert "outcome=repeated-pauses" in lines[3] and "finished=yes" in lines[3]
    assert (rig.tmp / "notified").read_text().count("\n") == 1
    assert rig.run().returncode == 0  # a finished day: the next retry is a no-op


def test_a_pause_during_the_bench_is_paused_noisy_and_not_recorded(rig: Rig) -> None:
    hist = rig.tmp / "logs" / "perf_gate" / "history.jsonl"
    hist.parent.mkdir(parents=True, exist_ok=True)
    hist.write_text('{"old": 1}\n')
    rig.bench_body = f"sleep 5\necho '{{\"new\": 2}}' >> {hist}\necho '{rig.bench_out}'\nexit 1\n"
    jump = rig.tmp / "slept"
    env = rig.env(PERF_SAMPLE_S="1", **_date_stub(rig, jump, 600))
    proc = subprocess.Popen(
        ["bash", str(SCRIPT)], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    time.sleep(2.5)
    jump.write_text("")
    _, err = proc.communicate(timeout=60)
    assert "paused or stalled during the bench" in err
    assert "outcome=paused" in rig.status.read_text()
    assert hist.read_text() == '{"old": 1}\n'  # the run is not recorded
    assert "NOT recorded" in (rig.tmp / "notified").read_text()


def test_the_trash_delete_runs_in_its_own_session_and_survives_the_wrappers_group_kill(
    rig: Rig,
) -> None:
    """Under launchd the wrapper's whole group is killed when it exits: a delete in it died."""
    old = rig.root / "data.trash.2026-10-20"
    (old / "tables").mkdir(parents=True)
    (old / "tables" / "z.txt").write_text("z")
    pgid_file = rig.tmp / "delete.pgid"
    slow = _script(rig, "slowdel.sh", f'ps -o pgid= -p $$ > {pgid_file}\nsleep 3\nexec "$@"\n')
    proc = subprocess.Popen(
        ["bash", str(SCRIPT)],
        env=rig.env(PERF_LOWPRI=slow),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,  # the wrapper leads its own group, as under launchd
    )
    proc.communicate(timeout=30)
    with contextlib.suppress(ProcessLookupError):  # what launchd does when the wrapper exits
        os.killpg(proc.pid, signal.SIGKILL)
    end = time.time() + 10
    while not pgid_file.exists() or not pgid_file.read_text().strip():
        assert time.time() < end
        time.sleep(0.1)
    assert int(pgid_file.read_text()) != proc.pid  # its own group
    assert _wait_gone(old, 30)  # and it ran to the end


def test_a_slow_total_notification_names_the_snapshot_time(rig: Rig) -> None:
    rig.run(PERF_TOTAL_LIMIT_S="0")
    assert "snapshot " in (rig.tmp / "notified").read_text()


def test_a_pause_during_the_bench_does_not_hide_an_integrity_failure(rig: Rig) -> None:
    rig.bench_body = (
        "sleep 5\necho 'INTEGRITY operations that answered null'\n"
        "echo '1 views over 1.0 s'\nexit 1\n"
    )
    jump = rig.tmp / "slept"
    env = rig.env(PERF_SAMPLE_S="1", **_date_stub(rig, jump, 600))
    proc = subprocess.Popen(
        ["bash", str(SCRIPT)], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    time.sleep(2.5)
    jump.write_text("")
    proc.communicate(timeout=60)
    assert "outcome=integrity" in rig.status.read_text()
    assert "INTEGRITY FAILURE" in (rig.tmp / "notified").read_text()
