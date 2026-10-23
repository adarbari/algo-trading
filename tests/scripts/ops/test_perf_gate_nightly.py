"""`scripts/ops/perf_gate_nightly.sh`: the path guards, the busy guards (exit 3), and the
per-date idempotence (before 03:00, done today, next day), with a fake bench and no real store."""

import json
import os
import subprocess
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

    def run(self, **over: str) -> subprocess.CompletedProcess[str]:
        bench = self.tmp / "bench.sh"
        body = f"echo '{self.bench_out}'\nexit {self.bench_code}\n"
        bench.write_text("#!/bin/sh\n" + (self.bench_body or body))
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
            **over,
        }
        return subprocess.run(
            ["bash", str(SCRIPT)], env=env, capture_output=True, text=True, check=False
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


def test_a_refused_bench_is_not_a_finished_day(rig: Rig) -> None:
    rig.bench_code, rig.bench_out = 2, "refused"
    assert rig.run().returncode == 2
    assert "finished=no" in rig.status.read_text()
    rig.bench_code, rig.bench_out = (
        0,
        "0 views over 1.0 s on the critical path (0.0 s above the bar)",
    )
    assert rig.run().returncode == 0  # retried the same day


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
    assert "exit=4 finished=yes over_time=yes" in line
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
