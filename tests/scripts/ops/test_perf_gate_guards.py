"""The nightly perf gate wrapper's writer, pause, copy and delete guards (the second half of
``test_perf_gate_nightly.py``, split for the 1000-line cap; the rig and helpers are shared)."""

import contextlib
import json
import os
import shutil
import signal
import subprocess
import time
from pathlib import Path

import pytest

from tests.scripts.ops.test_perf_gate_nightly import (
    QUIET_PS,
    SCRIPT,
    Rig,
    _evidence,
    _script,
    _wait_gone,
)


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    return Rig(tmp_path)


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


def test_only_tables_is_copied_per_dataset_runs_and_serving_whole(rig: Rig) -> None:
    """Hand run 5: a cp per child of runs/ (29k files) ran at 100 files/s: one cp per entry."""
    store = rig.tmp / "var" / "data"
    for i in range(17):
        (store / "tables" / f"d{i}").mkdir(parents=True)
        (store / "tables" / f"d{i}" / "f").write_text("x")
    for i in range(50):
        (store / "runs").mkdir(exist_ok=True)
        (store / "runs" / f"r{i}.json").write_text("x")
    (store / "serving").mkdir()
    for i in range(3):
        (store / "serving" / f"s{i}").write_text("x")
    calls = rig.tmp / "cp.calls"
    counting = _script(rig, "countcp.sh", f'echo "$1" >> {calls}\ncp -R "$1" "$2"\n')
    assert rig.run(PERF_COPY_CMD=counting).returncode == 1
    assert len(calls.read_text().splitlines()) == 17 + 2  # 17 datasets + runs + serving
    snap = json.loads((_evidence(rig) / "snapshot.json").read_text())  # still valid JSON
    assert set(snap["entry_s"]) == {f"tables/d{i}" for i in range(17)} | {"runs", "serving"}


AUTO_DEPLOY = (
    "  9 /x/.venv/bin/python /x/.venv/bin/algotrade-ingest deploy-hold --deploy-only -- "
    "bash /x/scripts/ops/deploy.sh --slot blue --apply auto 3f2b3ae00 sync web restart\n"
)
INGEST_SYNC = (
    "  9 /x/.venv/bin/algotrade-ingest deploy-hold -- "
    "bash /x/scripts/ops/deploy.sh --slot blue --ingest-apply auto 3f2b3ae00\n"
)
FAST_WAIT = {"PERF_DEPLOY_WAIT_S": "2", "PERF_DEPLOY_POLL_S": "1"}


def _during_copy(
    rig: Rig, line: str, seconds: str = "4", gone_after: float | None = None, **env: str
):
    """Copy takes ``seconds``; ``line`` shows in ps after 2 s and goes after ``gone_after``."""
    (rig.tmp / "var" / "data" / "tables").mkdir(exist_ok=True)
    slow = _script(rig, "slowcp7.sh", f"sleep {seconds}\n")
    proc = subprocess.Popen(
        ["bash", str(SCRIPT)],
        env=rig.env(PERF_COPY_CMD=slow, PERF_POLL_S="1", **env),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    time.sleep(2)
    rig.ps.write_text(QUIET_PS + line)
    if gone_after is not None:
        time.sleep(gone_after)
        rig.ps.write_text(QUIET_PS)
    _, err = proc.communicate(timeout=60)
    return proc.returncode, err


@pytest.mark.parametrize("line", [AUTO_DEPLOY, INGEST_SYNC])
def test_a_deploy_during_the_copy_does_not_stop_it_and_the_bench_waits_for_it(
    rig: Rig, line: str
) -> None:
    code, err = _during_copy(rig, line, gone_after=3.5, PERF_DEPLOY_WAIT_S="20")
    assert code == 1 and "copy stopped" not in err  # the bench ran, after the deploy was gone
    assert "waiting" in err and "ignored deploy: pid 9 " in (_evidence(rig) / "run.log").read_text()


@pytest.mark.parametrize("line", [AUTO_DEPLOY, INGEST_SYNC])
def test_a_deploy_still_running_after_the_copy_is_busy_for_the_bench_and_the_clone_goes(
    rig: Rig, line: str
) -> None:
    code, err = _during_copy(rig, line, **FAST_WAIT)
    assert code == 3 and "a deploy is still running" in err
    assert not rig.status.exists() and not (rig.root / "data").exists()


@pytest.mark.parametrize("line", [AUTO_DEPLOY, INGEST_SYNC])
def test_a_deploy_at_the_start_is_waited_for_then_busy(rig: Rig, line: str) -> None:
    rig.ps.write_text(QUIET_PS + line)
    res = rig.run(**FAST_WAIT)
    assert res.returncode == 3 and "a deploy is still running" in res.stderr
    assert not (rig.root / "data").exists()


@pytest.mark.parametrize(
    "line",
    [
        # junk before the command (the `^` anchor)
        "  9 /bin/sh -c rollups; algotrade-ingest deploy-hold --deploy-only -- "
        "bash /x/scripts/ops/deploy.sh --slot b --apply\n",
        # no --slot / --apply, a script that is not the tree's deploy.sh, no mode flag
        "  9 algotrade-ingest deploy-hold --deploy-only -- bash /x/scripts/ops/deploy.sh\n",
        "  9 algotrade-ingest deploy-hold --deploy-only -- bash /x/deploy.sh --slot b --apply\n",
        "  9 algotrade-ingest deploy-hold -- bash /x/scripts/ops/deploy.sh --slot b --apply\n",
        "  9 algotrade-ingest deploy-hold --deploy-only -- bash /x/ops/other.sh --slot b --apply\n",
        "  9 algotrade-ingest rollups --from 2013-01-01\n",
    ],
)
def test_only_the_two_exact_deploy_command_lines_are_exempt_in_the_copy(
    rig: Rig, line: str
) -> None:
    code, err = _during_copy(rig, line, seconds="20")
    assert code == 3 and "a writer started during the copy (copy stopped)" in err


def test_the_release_trees_head_moving_during_the_bench_is_not_recorded(rig: Rig) -> None:
    tree = rig.tmp / "tree"
    tree.mkdir()
    git = ["git", "-C", str(tree), "-c", "user.email=a@b", "-c", "user.name=n"]
    for args in (["init", "-q"], ["commit", "-q", "--allow-empty", "-m", "one"]):
        subprocess.run([*git, *args], check=True, capture_output=True)
    hist = rig.tmp / "logs" / "perf_gate" / "history.jsonl"
    hist.parent.mkdir(parents=True, exist_ok=True)
    hist.write_text('{"old": 1}\n')
    rig.bench_body = (
        f"echo '{{\"new\": 2}}' >> {hist}\n"
        f"{' '.join(git)} commit -q --allow-empty -m two\n"
        f"echo '{rig.bench_out}'\nexit 1\n"
    )
    res = rig.run(PERF_TREE=str(tree))
    assert "code changed during the bench" in res.stderr
    assert "outcome=code-changed" in rig.status.read_text()
    assert hist.read_text() == '{"old": 1}\n'
    assert "NOT recorded" in (rig.tmp / "notified").read_text()
