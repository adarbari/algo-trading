"""The nightly perf gate's flight recorder: what the machine and the run were doing, kept so a
killed or slow run can be understood afterwards (``scripts/ops/perf_gate_nightly.sh`` calls it).

Subcommands (stdlib only; nothing outside the run folder ``var/logs/perf_gate/<date>/`` is written):

``timeline``  every 10 s, across all phases, a row of ``timeline.csv`` (load, free disk, CPU by
              family, the top 5 processes, memory, swap, disk busy). Every probe has a hard 3 s
              timeout: a stuck probe is a ``probe-timeout`` note, never a stall.
``prekill``   at 70% of a phase's cap, if the phase still runs: a 3 s ``sample`` of the busiest
              python processes of the gate's tree and a ``ps`` top 15 into ``prekill/`` (5 MB).
``report``    ``kill-report.json``: what was in flight, the last requests and timeline rows, the CPU
              families over the phase, what else ran, a likely cause; prints the cause and the top 3
              consumers on one line for the notification.
``finish``    ``README.txt``, ``top_cpu`` and ``phases`` in ``status.json``, the ``api.log`` tail.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import threading
import time
from collections import defaultdict
from pathlib import Path

PROBE_TIMEOUT_S = 3.0
PREKILL_BYTES = 5 * 1024 * 1024
API_LOG_CAP = 2 * 1024 * 1024
INDEXING = re.compile(r"^(mds|mds_stores|mdworker.*|fseventsd|FSEvents.*|corespotlightd)$")
COLUMNS = [
    *("epoch", "phase", "load1", "free_gb", "cpu_indexing", "cpu_gate", "cpu_other", "top5"),
    *("mem_free_pct", "swap_used_mb", "disk_kb_per_t", "disk_tps", "late_s", "notes"),
]
TIMEOUT = "probe-timeout"

README = """Evidence of one perf gate run (var/logs/perf_gate/<date>/): file: the question
status.json       how did the run end, how long did each phase take (phases), who used the CPU?
run.log           what did the wrapper do and say, in order (guards, ignored drivers, pauses)?
timeline.csv      the machine every 10 s: load, free disk, CPU by family (indexing, the gate's
                  own tree, other), the top 5 processes, memory, swap, disk busy, late_s
load.csv          the older load / free disk sampler (late_s: the loop was not scheduled)
ops.json, views.json  how long did every operation and view take?
ops-stream.jsonl  every bench request as it completed (op, pass, ms, bytes, status, load)
bench-progress.json  the pass and op in flight when the bench stopped
samples-partial.json  every operation's time per pass
api.log           the bench API process's output (last 2 MB)
bench-head.txt    the first 200 lines of the bench's own output
snapshot.json     how far did the copy get, what did each entry take?
copy-timings.txt  seconds per copied entry
kill-report.json  why was the run stopped: likely cause, what was in flight, the last requests
prekill/          stack samples and a ps top 15 taken at 70% of a phase's cap, while it still ran
procs-start.txt, procs-end.txt  the top processes at the start of the copy and the end of the bench
profiles.md       where the time of the slowest operations went (only when something is over)
"""


def probe(fn, timeout: float | None = None):
    """``fn()`` in a daemon thread, ``TIMEOUT`` when it does not finish in ``timeout`` s."""
    box: list = []

    def run() -> None:
        try:
            box.append(fn())
        except Exception as exc:  # a failed probe is a missing value, never a crash
            box.append(f"probe-error:{type(exc).__name__}")

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(PROBE_TIMEOUT_S if timeout is None else timeout)
    return box[0] if box else TIMEOUT


def run_cmd(args: list[str], timeout: float | None = None) -> str:
    """Stdout of a command, the child killed (and not waited for) after ``timeout`` s."""
    p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    try:
        out, _ = p.communicate(timeout=PROBE_TIMEOUT_S if timeout is None else timeout)
    except subprocess.TimeoutExpired:
        p.kill()
        raise
    return out


def process_table() -> list[tuple[int, int, float, str]]:
    """(pid, ppid, cpu%, name) for every process; the name is the basename of the command."""
    rows = []
    for line in run_cmd(["ps", "-Ao", "pid,ppid,pcpu,comm"]).splitlines()[1:]:
        parts = line.split(None, 3)
        if len(parts) == 4:
            try:
                rows.append((int(parts[0]), int(parts[1]), float(parts[2]), Path(parts[3]).name))
            except ValueError:
                continue
    return rows


def families(table: list[tuple[int, int, float, str]], root: int) -> tuple[float, float, float]:
    """CPU% summed for (indexing, the gate's own tree under ``root``, everything else)."""
    kids: dict[int, list[int]] = defaultdict(list)
    for pid, ppid, _, _ in table:
        kids[ppid].append(pid)
    tree, todo = set(), [root]
    while todo:
        pid = todo.pop()
        if pid not in tree:
            tree.add(pid)
            todo.extend(kids[pid])
    idx = gate = other = 0.0
    for pid, _, cpu, name in table:
        if INDEXING.match(name):
            idx += cpu
        elif pid in tree:
            gate += cpu
        else:
            other += cpu
    return round(idx, 1), round(gate, 1), round(other, 1)


def top5(table: list[tuple[int, int, float, str]]) -> str:
    best = sorted(table, key=lambda r: r[2], reverse=True)[:5]
    return ";".join(f"{name}:{cpu:g}" for _, _, cpu, name in best)


def mem_free_pct() -> str:
    out = run_cmd(["memory_pressure", "-Q"])
    m = re.search(r"free percentage:\s*(\d+)", out)
    return m.group(1) if m else ""


def swap_used_mb() -> str:
    m = re.search(r"used = ([\d.]+)M", run_cmd(["sysctl", "-n", "vm.swapusage"]))
    return m.group(1) if m else ""


def disk_busy() -> tuple[str, str]:
    """(KB/t, tps) of the first disk, from the second (live) iostat sample."""
    lines = [x for x in run_cmd(["iostat", "-d", "-c", "2"]).splitlines() if x.strip()]
    nums = lines[-1].split() if lines else []
    return (nums[0], nums[1]) if len(nums) >= 2 else ("", "")


def free_gb(path: str) -> str:
    st = os.statvfs(path)
    return str(int(st.f_bavail * st.f_frsize / 1024**3))


def sample_row(rundir: Path, root: int, late: int, store: str) -> list:
    """One row of timeline.csv; every probe is bounded, a stuck one is noted."""
    notes: list[str] = []

    def get(name: str, fn, default=""):
        v = probe(fn)
        if isinstance(v, str) and v.startswith(("probe-timeout", "probe-error")):
            notes.append(f"{name}={v}")
            return default
        return v

    phase = (
        (rundir / "phase.txt").read_text().strip() if (rundir / "phase.txt").is_file() else "wait"
    )
    table = get("ps", process_table, [])
    idx, gate, other = families(table, root) if table else ("", "", "")
    disk = get("iostat", disk_busy, ("", ""))
    return [
        int(time.time()), phase, get("load", lambda: round(os.getloadavg()[0], 2)),
        get("df", lambda: free_gb(store)), idx, gate, other, top5(table) if table else "",
        get("mem", mem_free_pct), get("swap", swap_used_mb), disk[0], disk[1], late,
        "|".join(notes),
    ]  # fmt: skip


def timeline(
    rundir: Path, root: int, every: float, store: str, stop_file: Path | None = None
) -> None:
    path = rundir / "timeline.csv"
    if not path.exists():
        path.write_text(",".join(COLUMNS) + "\n")
    prev_start, prev_dur = None, 0.0
    # leave when the wrapper died without its EXIT trap (kill -9): the parent is not the root
    while (stop_file is None or not stop_file.exists()) and os.getppid() == root:
        start = time.time()
        # late: tick start vs the last, less the interval and the last probes' own time
        late = 0
        if prev_start is not None:
            late = max(0, int(start - prev_start - max(every, prev_dur)))
        prev_start = start
        row = sample_row(rundir, root, late, store)
        with path.open("a", newline="") as f:
            csv.writer(f).writerow(row)
        prev_dur = time.time() - start
        time.sleep(max(0.0, every - prev_dur))


def read_rows(rundir: Path) -> list[dict]:
    path = rundir / "timeline.csv"
    if not path.is_file():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def phase_starts(rundir: Path) -> dict[str, list[int]]:
    """phase -> [start, end] epochs from ``phases.txt`` (``<phase> <epoch>``; next line ends it)."""
    marks = []
    f = rundir / "phases.txt"
    if f.is_file():
        for line in f.read_text().splitlines():
            name, _, ts = line.partition(" ")
            if ts.isdigit():
                marks.append((name, int(ts)))
    out: dict[str, list[int]] = {}
    for i, (name, ts) in enumerate(marks):
        end = marks[i + 1][1] if i + 1 < len(marks) else int(time.time())
        out[name] = [ts, end]
    return out


def top_consumers(rows: list[dict], n: int = 3) -> list[tuple[str, float]]:
    """Mean CPU% per process name over ``rows`` (absent from a row's top 5 counts as 0)."""
    totals: dict[str, float] = defaultdict(float)
    for r in rows:
        for pair in filter(None, (r.get("top5") or "").split(";")):
            name, _, pct = pair.rpartition(":")
            try:
                totals[name] += float(pct)
            except ValueError:
                continue
    count = max(len(rows), 1)
    best = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:n]
    return [(name, round(v / count, 1)) for name, v in best]


_KNOWN_CAUSES = {
    "paused": "machine paused",
    "code-changed": "code changed during the bench (a deploy)",
    "crashed": "the bench crashed",
    "integrity": "an integrity failure (not a timing cause)",
    "sampled": "a pre-kill stack sample paused the bench",
}


def named_cause(reason: str) -> str | None:
    """The cause a KNOWN stop reason names (None for over-time and unknown reasons)."""
    if reason in _KNOWN_CAUSES:
        return _KNOWN_CAUSES[reason]
    if reason.startswith("machine paused"):
        return "machine paused"
    if reason.startswith("guard:"):
        return "stopped by a guard (" + reason[len("guard:") :].strip()[:80] + ")"
    return None


def likely_cause(
    rows: list[dict], cpus: int, copy_files_per_s: float | None = None, reason: str = ""
) -> str:
    """One line. A KNOWN stop reason names the cause; the CPU and load rules run only for an
    over-time or unknown stop, and read the median of the phase's rows (a spike is no cause)."""
    if (named := named_cause(reason)) is not None:
        return named

    def col(name: str) -> list[float]:
        out = []
        for r in rows:
            try:
                out.append(float(r[name]))
            except (KeyError, ValueError):
                continue
        return out

    if any(v > 60 for v in col("late_s")):
        return "machine paused"
    idx, load = col("cpu_indexing"), col("load1")
    if idx and statistics.median(idx) > 150:
        return "Spotlight/FSEvents indexing contended"
    if load and statistics.median(load) > 2 * cpus:
        return "machine overloaded"
    if copy_files_per_s is not None and copy_files_per_s < 1000:
        return "slow filesystem"
    return "unknown"


RUNNING = re.compile(r"algotrade-ingest|algotrade_ingestion|deploy-hold|deploy\.sh|data\.trash\.")


def running_names() -> list[str]:
    """Names of deploys, ingests and trash deletes running now (never an argument list)."""
    names = set()
    try:
        out = run_cmd(["ps", "-Ao", "pid,args"])
    except Exception:
        return []
    for line in out.splitlines()[1:]:
        if (
            RUNNING.search(line)
            and "flight_recorder" not in line
            and "perf_gate_nightly" not in line
        ):
            words = line.split(None, 2)
            names.add(" ".join(words[1:3])[:60] if len(words) > 2 else words[-1][:60])
    return sorted(names)[:10]


def tail_lines(path: Path, n: int) -> list:
    if not path.is_file():
        return []
    out = []
    for line in path.read_text().splitlines()[-n:]:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def report(rundir: Path, phase: str, cap: int, reason: str, cpus: int | None = None) -> dict:
    """Write kill-report.json; returns it."""
    spans = phase_starts(rundir)
    start, end = spans.get(phase, [int(time.time())] * 2)
    # only this attempt's rows: the folder holds every attempt of the day
    rows = [r for r in read_rows(rundir) if str(r["epoch"]).isdigit() and int(r["epoch"]) >= start]
    in_phase = [r for r in rows if r["phase"] == phase]
    snap = (
        json.loads((rundir / "snapshot.json").read_text())
        if (rundir / "snapshot.json").is_file()
        else {}
    )
    rate = None
    if phase == "copy" and snap.get("copy_s") and str(snap.get("files_so_far", "")).isdigit():
        rate = int(snap["files_so_far"]) / max(int(snap["copy_s"]), 1)
    cause = likely_cause(in_phase, cpus or os.cpu_count() or 1, rate, reason)
    top = top_consumers(in_phase)
    progress = rundir / "bench-progress.json"
    entry = rundir / "copy-entry.txt"
    data = {
        "phase": phase, "reason": reason, "elapsed_s": end - start, "cap_s": cap,
        "in_flight": {
            "bench": json.loads(progress.read_text()) if progress.is_file() else None,
            "copy_entry": entry.read_text().strip() if entry.is_file() else None,
        },
        "last_requests": tail_lines(rundir / "ops-stream.jsonl", 20),
        "timeline_tail": rows[-6:],
        "top_cpu": [{"name": n, "cpu_pct": v} for n, v in top],
        "running": running_names(),
        "likely_cause": cause,
    }  # fmt: skip
    (rundir / "kill-report.json").write_text(json.dumps(data, indent=1) + "\n")
    return data


def prekill(rundir: Path, root: int, phase: str, after: float) -> None:
    """At ``after`` s of ``phase`` (its start is now), if it still runs: samples and a ps top 15."""
    end = time.time() + after
    while time.time() < end:
        if os.getppid() != root:  # the wrapper died without its trap
            return
        time.sleep(min(1.0, max(0.0, end - time.time())))
    pf = rundir / "phase.txt"
    if not pf.is_file() or pf.read_text().strip() != phase:
        return
    folder = rundir / "prekill"
    folder.mkdir(exist_ok=True)
    try:
        lines = run_cmd(["ps", "-Ao", "pid,pcpu,etime,comm"]).splitlines()
        body = sorted(lines[1:], key=_cpu_of, reverse=True)[:15]
        (folder / f"ps-top15-{phase}.txt").write_text("\n".join([lines[0], *body]) + "\n")
    except Exception:
        pass
    sampler = shutil.which("sample")
    if sampler is None:
        return  # skipped silently
    try:
        table = process_table()
    except Exception:
        return
    mine = [r for r in table if "python" in r[3].lower() and _descends(table, r[0], root)]
    window = rundir / f"sample-window-{phase}.json"
    if mine:  # `sample` suspends the process for its 3 s: say when, the run is then not recorded
        window.write_text(json.dumps({"start": int(time.time()), "pids": [r[0] for r in mine[:2]]}))
    for pid, _, _, _ in sorted(mine, key=lambda r: r[2], reverse=True)[:2]:
        target = folder / f"sample-{phase}-{pid}.txt"
        with contextlib.suppress(Exception):
            subprocess.run(
                [sampler, str(pid), "3", "-file", str(target)],
                timeout=10, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )  # fmt: skip
    if mine:
        window.write_text(json.dumps({**json.loads(window.read_text()), "end": int(time.time())}))
    cap_folder(folder, PREKILL_BYTES)


def _cpu_of(line: str) -> float:
    parts = line.split()
    try:
        return float(parts[1])
    except (IndexError, ValueError):
        return 0.0


def _descends(table: list[tuple[int, int, float, str]], pid: int, root: int) -> bool:
    parent = {p: pp for p, pp, _, _ in table}
    for _ in range(50):
        pid = parent.get(pid, 0)
        if pid == root:
            return True
        if pid in (0, 1):
            return False
    return False


def cap_folder(folder: Path, cap: int) -> None:
    """Keep the folder under ``cap`` bytes: truncate the biggest files, drop the empty ones."""
    files = sorted(
        (f for f in folder.iterdir() if f.is_file()), key=lambda f: f.stat().st_size, reverse=True
    )
    total = sum(f.stat().st_size for f in files)
    for f in files:
        if total <= cap:
            break
        keep = max(0, f.stat().st_size - (total - cap))
        data = f.read_bytes()[:keep]
        total -= f.stat().st_size - len(data)
        f.write_bytes(data)


def finish(rundir: Path) -> None:
    """README.txt, ``top_cpu`` and ``phases`` into status.json, the api.log tail."""
    (rundir / "README.txt").write_text(README)
    status = rundir / "status.json"
    if status.is_file():
        d = json.loads(status.read_text())
        d["phases"] = phase_starts(rundir)
        d["top_cpu"] = [{"name": n, "cpu_pct": v} for n, v in top_consumers(read_rows(rundir))]
        status.write_text(json.dumps(d, indent=1) + "\n")
    log = rundir / "api.log"
    if log.is_file() and log.stat().st_size > API_LOG_CAP:
        log.write_bytes(log.read_bytes()[-API_LOG_CAP:])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("timeline", "prekill", "report", "finish"):
        p = sub.add_parser(name)
        p.add_argument("--rundir", required=True, type=Path)
        if name in ("timeline", "prekill"):
            p.add_argument("--root", type=int, default=os.getppid())
        if name == "timeline":
            p.add_argument("--every", type=float, default=10.0)
            p.add_argument("--store", default=".")
            p.add_argument("--stop-file", type=Path)
        if name in ("prekill", "report"):
            p.add_argument("--phase", required=True)
        if name == "prekill":
            p.add_argument("--after", type=float, required=True)
        if name == "report":
            p.add_argument("--cap", type=int, default=0)
            p.add_argument("--reason", default="")
    a = ap.parse_args(argv)
    if a.cmd == "timeline":
        timeline(a.rundir, a.root, a.every, a.store, a.stop_file)
    elif a.cmd == "prekill":
        prekill(a.rundir, a.root, a.phase, a.after)
    elif a.cmd == "report":
        d = report(a.rundir, a.phase, a.cap, a.reason)
        top = ", ".join(f"{x['name']} {x['cpu_pct']:g}%" for x in d["top_cpu"]) or "none"
        print(f"likely cause: {d['likely_cause']}; top CPU: {top}")
    else:
        finish(a.rundir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
