"""The perf gate's flight recorder (scripts/perf/flight_recorder.py): bounded probes, the CPU
families, the likely-cause rules, the kill report, the pre-kill sample and its size cap."""

import csv
import importlib.util
import json
import os
import signal
import subprocess
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location(
    "flight_recorder", ROOT / "scripts" / "perf" / "flight_recorder.py"
)
assert _spec and _spec.loader
fr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fr)

TABLE = [  # (pid, ppid, cpu, name)
    (1, 0, 0.0, "launchd"),
    (100, 1, 1.0, "bash"),  # the gate: root
    (101, 100, 90.0, "cp"),
    (102, 101, 40.0, "python"),
    (200, 1, 120.0, "mds"),
    (201, 1, 60.0, "mdworker_shared"),
    (202, 1, 30.0, "fseventsd"),
    (300, 1, 25.0, "Safari"),
]


def test_a_stuck_probe_is_a_timeout_not_a_stall(monkeypatch: pytest.MonkeyPatch) -> None:
    t0 = time.time()
    assert fr.probe(lambda: time.sleep(5), 0.2) == fr.TIMEOUT
    assert time.time() - t0 < 2
    assert fr.probe(lambda: 7, 1) == 7
    assert fr.probe(lambda: 1 / 0, 1).startswith("probe-error")


def test_a_row_names_the_probes_that_timed_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(fr, "PROBE_TIMEOUT_S", 0.3)
    monkeypatch.setattr(fr, "process_table", lambda: time.sleep(5))
    monkeypatch.setattr(fr, "disk_busy", lambda: ("1.0", "2"))
    monkeypatch.setattr(fr, "mem_free_pct", lambda: "50")
    monkeypatch.setattr(fr, "swap_used_mb", lambda: "3.5")
    t0 = time.time()
    row = fr.sample_row(tmp_path, os.getpid(), 0, str(tmp_path))
    assert time.time() - t0 < 3
    d = dict(zip(fr.COLUMNS, row, strict=True))
    assert "ps=probe-timeout" in d["notes"] and d["disk_tps"] == "2" and d["mem_free_pct"] == "50"
    assert d["phase"] == "wait" and d["late_s"] == 0


def test_cpu_is_split_into_indexing_the_gates_tree_and_the_rest() -> None:
    assert fr.families(TABLE, 100) == (210.0, 131.0, 25.0)
    assert fr.top5(TABLE).startswith("mds:120;cp:90;mdworker_shared:60;python:40")


def _rows(**cols: list) -> list[dict]:
    n = max(len(v) for v in cols.values())
    keys = {"cpu_indexing": 0, "load1": 0, "late_s": 0}
    return [{k: str(cols.get(k, [keys[k]] * n)[i]) for k in keys} for i in range(n)]


@pytest.mark.parametrize(
    ("rows", "rate", "cause"),
    [
        (_rows(late_s=[0, 700]), None, "machine paused"),
        (_rows(cpu_indexing=[10, 160, 170]), None, "Spotlight/FSEvents indexing contended"),
        (_rows(cpu_indexing=[10, 10, 400]), None, "unknown"),  # one spike is not a cause
        (_rows(load1=[1, 20, 25]), None, "machine overloaded"),
        (_rows(load1=[1, 1, 30]), None, "unknown"),
        (_rows(load1=[1, 2]), 400.0, "slow filesystem"),
        (_rows(load1=[1, 2]), 5000.0, "unknown"),
        (_rows(load1=[1, 2]), None, "unknown"),
        # the first rule that fits wins: a pause beats indexing beats load
        (_rows(late_s=[900], cpu_indexing=[400], load1=[30]), None, "machine paused"),
        (_rows(cpu_indexing=[400], load1=[30]), None, "Spotlight/FSEvents indexing contended"),
    ],
)
def test_the_likely_cause_rules(rows: list[dict], rate: float | None, cause: str) -> None:
    assert fr.likely_cause(rows, cpus=8, copy_files_per_s=rate) == cause


@pytest.mark.parametrize(
    ("reason", "cause"),
    [
        ("code-changed", "code changed during the bench (a deploy)"),
        ("crashed", "the bench crashed"),
        ("integrity", "an integrity failure (not a timing cause)"),
        ("machine paused 601 s", "machine paused"),
        (
            "guard: a writer runs: 9 algotrade-ingest rollups",
            "stopped by a guard (a writer runs: 9 algotrade-ingest rollups)",
        ),
    ],
)
def test_a_known_stop_reason_names_the_cause_whatever_the_cpu_says(reason: str, cause: str) -> None:
    hot = _rows(cpu_indexing=[500, 500, 500], load1=[40, 40, 40])
    assert fr.likely_cause(hot, cpus=8, reason=reason) == cause
    # over-time and unknown reasons still use the rules
    assert fr.likely_cause(hot, cpus=8, reason="over-time").startswith("Spotlight")


def test_top_consumers_are_means_over_the_rows() -> None:
    rows = [{"top5": "mds:100;python:50"}, {"top5": "mds:200"}]
    assert fr.top_consumers(rows, 2) == [("mds", 150.0), ("python", 25.0)]


def _run_folder(tmp_path: Path) -> Path:
    d = tmp_path / "2026-10-23"
    d.mkdir()
    now = int(time.time())
    (d / "phases.txt").write_text(f"wait {now - 400}\ncopy {now - 380}\nbench {now - 300}\n")
    (d / "phase.txt").write_text("bench\n")
    with (d / "timeline.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(fr.COLUMNS)
        for i in range(10):
            row = dict.fromkeys(fr.COLUMNS, "")
            row |= {"epoch": now - 100 + i, "phase": "bench", "load1": "13", "cpu_indexing": "480"}
            row |= {"top5": "mds:173;python:90;mds_stores:144", "late_s": "0"}
            w.writerow([row[c] for c in fr.COLUMNS])
    (d / "ops-stream.jsonl").write_text(
        "".join(json.dumps({"op": f"Op{i}", "ms": i}) + "\n" for i in range(30))
    )
    (d / "bench-progress.json").write_text(json.dumps({"op": "IdeasPage", "pass": 3}))
    return d


def test_the_kill_report_says_what_was_in_flight_and_the_likely_cause(tmp_path: Path) -> None:
    d = _run_folder(tmp_path)
    data = fr.report(d, "bench", 300, "over-time", cpus=8)
    assert data["likely_cause"] == "Spotlight/FSEvents indexing contended"
    assert data["in_flight"]["bench"] == {"op": "IdeasPage", "pass": 3}
    assert [r["op"] for r in data["last_requests"]][-1] == "Op29" and len(
        data["last_requests"]
    ) == 20
    assert len(data["timeline_tail"]) == 6 and data["cap_s"] == 300 and data["phase"] == "bench"
    assert data["top_cpu"][0]["name"] == "mds" and data["elapsed_s"] >= 299
    assert json.loads((d / "kill-report.json").read_text())["reason"] == "over-time"


def test_a_report_reads_only_this_attempts_rows_not_an_earlier_one_of_the_day(
    tmp_path: Path,
) -> None:
    d = _run_folder(tmp_path)
    rows = (d / "timeline.csv").read_text().splitlines()
    old = rows[1].replace(rows[1].split(",")[0], str(int(time.time()) - 5000))
    quiet = rows[1].split(",")
    quiet[fr.COLUMNS.index("cpu_indexing")] = "1"
    quiet[fr.COLUMNS.index("load1")] = "1"
    new = [",".join(quiet).replace(quiet[0], str(int(time.time()) - 10))]
    (d / "timeline.csv").write_text("\n".join([rows[0], *[old] * 5, *new]) + "\n")
    data = fr.report(d, "bench", 300, "over-time", cpus=8)
    assert data["likely_cause"] == "unknown" and len(data["timeline_tail"]) == 1


def test_the_timeline_leaves_when_its_wrapper_dies_without_its_trap(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "perf" / "flight_recorder.py"
    shell = subprocess.Popen(
        ["sh", "-c", f"python3 {script} timeline --rundir {tmp_path} --root $$ --every 0.2 "
         f"--store {tmp_path} & echo $!; sleep 60"],
        stdout=subprocess.PIPE, text=True,
    )  # fmt: skip
    pid = int(shell.stdout.readline())
    end = time.time() + 20
    while not (tmp_path / "timeline.csv").exists() and time.time() < end:
        time.sleep(0.1)
    os.kill(shell.pid, signal.SIGKILL)  # no EXIT trap runs
    shell.wait()
    end = time.time() + 20
    gone = False
    while time.time() < end and not gone:
        try:
            os.kill(pid, 0)
            time.sleep(0.2)
        except ProcessLookupError:
            gone = True
    shell.stdout.close()
    assert gone


def test_late_s_does_not_count_the_probes_own_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lates = []

    def slow_row(rundir: Path, root: int, late: int, store: str) -> list:
        lates.append(late)
        time.sleep(0.5)  # the probes take longer than the interval
        return [""] * len(fr.COLUMNS)

    monkeypatch.setattr(fr, "sample_row", slow_row)
    stop = tmp_path / "stop"
    root = os.getppid()
    threading.Timer(2.2, stop.write_text, args=("x",)).start()
    fr.timeline(tmp_path, root, 0.2, str(tmp_path), stop)
    assert len(lates) >= 3 and set(lates) == {0}


def test_the_report_names_the_slow_copy_from_the_snapshot_rate(tmp_path: Path) -> None:
    d = _run_folder(tmp_path)
    (d / "timeline.csv").write_text(",".join(fr.COLUMNS) + "\n")  # nothing else explains it
    (d / "phases.txt").write_text(f"copy {int(time.time()) - 100}\n")
    (d / "snapshot.json").write_text(json.dumps({"copy_s": 100, "files_so_far": "50000"}))
    assert fr.report(d, "copy", 900, "cap", cpus=8)["likely_cause"] == "slow filesystem"


def _stub_sample(tmp_path: Path, kb: int) -> str:
    d = tmp_path / "bin"
    d.mkdir(exist_ok=True)
    (d / "sample").write_text(
        f'#!/bin/sh\nhead -c {kb * 1024} /dev/zero > "$4"\n'  # sample PID 3 -file PATH
    )
    (d / "sample").chmod(0o755)
    return f"{d}:{os.environ['PATH']}"


def test_the_prekill_sample_is_taken_only_while_the_phase_runs_and_is_size_capped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = _run_folder(tmp_path)
    monkeypatch.setenv("PATH", _stub_sample(tmp_path, 4096))  # 4 MB each, two processes: 8 MB
    me = os.getpid()
    monkeypatch.setattr(
        fr,
        "process_table",
        lambda: [
            (me, 1, 50.0, "python"),
            (me + 1, me, 40.0, "python"),
            (me + 2, me, 30.0, "python"),
        ],
    )
    fr.prekill(d, me, "bench", 0)
    window = json.loads((d / "sample-window-bench.json").read_text())  # the safety net's evidence
    assert window["end"] >= window["start"]
    folder = d / "prekill"
    assert (folder / "ps-top15-bench.txt").is_file()
    assert sum(f.stat().st_size for f in folder.iterdir()) <= fr.PREKILL_BYTES
    assert any(f.name.startswith("sample-bench-") for f in folder.iterdir())
    (d / "phase.txt").write_text("cleanup\n")  # the phase ended: nothing taken
    other = tmp_path / "other"
    other.mkdir()
    (other / "phase.txt").write_text("cleanup\n")
    fr.prekill(other, me, "bench", 0)
    assert not (other / "prekill").exists()


def test_a_missing_sample_tool_is_skipped_silently(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = _run_folder(tmp_path)
    monkeypatch.setattr(fr.shutil, "which", lambda name: None)
    fr.prekill(d, os.getpid(), "bench", 0)
    assert not any(f.name.startswith("sample-") for f in (d / "prekill").iterdir())


def test_cap_folder_truncates_the_biggest_files(tmp_path: Path) -> None:
    (tmp_path / "a").write_bytes(b"x" * 600)
    (tmp_path / "b").write_bytes(b"x" * 300)
    fr.cap_folder(tmp_path, 500)
    assert sum(f.stat().st_size for f in tmp_path.iterdir()) <= 500


def test_finish_writes_the_readme_and_the_phases_and_top_cpu_into_status(tmp_path: Path) -> None:
    d = _run_folder(tmp_path)
    (d / "status.json").write_text(json.dumps({"date": "2026-10-23"}))
    (d / "api.log").write_bytes(b"x" * (fr.API_LOG_CAP + 10))
    fr.finish(d)
    status = json.loads((d / "status.json").read_text())
    assert (
        set(status["phases"]) == {"wait", "copy", "bench"} and status["top_cpu"][0]["name"] == "mds"
    )
    assert "timeline.csv" in (d / "README.txt").read_text()
    assert (d / "api.log").stat().st_size == fr.API_LOG_CAP


def test_trash_watch_samples_until_the_pid_file_is_gone(tmp_path: Path) -> None:
    pid_file = tmp_path / "trash-delete.pid"
    pid_file.write_text(f"{os.getpid()} /x/data.trash.1 0")
    threading.Timer(1.5, pid_file.unlink).start()
    t0 = time.time()
    fr.trash_watch(tmp_path, pid_file, str(tmp_path), 0.3, 30.0)
    assert time.time() - t0 < 10
    rows = (tmp_path / "timeline.csv").read_text().splitlines()
    assert len(rows) >= 2 and all(",trash-delete," in r for r in rows[1:])


def test_trash_watch_gives_up_when_the_pid_file_never_appears_and_stops_at_its_cap(
    tmp_path: Path,
) -> None:
    t0 = time.time()
    fr.trash_watch(tmp_path, tmp_path / "none.pid", str(tmp_path), 0.2, 30.0, appear_s=0.5)
    assert time.time() - t0 < 5
    pid_file = tmp_path / "live.pid"
    pid_file.write_text(f"{os.getpid()} x 0")  # never goes: the max-s cap ends it
    t0 = time.time()
    fr.trash_watch(tmp_path, pid_file, str(tmp_path), 0.2, 1.0)
    assert 1.0 <= time.time() - t0 < 6


def test_trash_watch_stops_for_a_stale_pid_file(tmp_path: Path) -> None:
    pid_file = tmp_path / "stale.pid"
    pid_file.write_text("999999 /x/data.trash.1 0")  # no such process
    t0 = time.time()
    fr.trash_watch(tmp_path, pid_file, str(tmp_path), 0.2, 30.0, appear_s=0.5)
    assert time.time() - t0 < 5
