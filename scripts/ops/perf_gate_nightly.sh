#!/usr/bin/env bash
# The 1 s page-latency gate, once a night, on a copy-on-write CLONE of the store (never the live
# data or the live API): `make api-latency-fast` in nightly form (docs/perf/page-latency-bar.md).
#
#   scripts/ops/perf_gate_nightly.sh        (launchd: 03:00 America/Los_Angeles, retry every 900 s;
#                                            the owner installs the entry, nothing here does)
#
# Idempotent per local date: exits 0 at once before 03:00 local and when var/logs/perf_gate.status
# already holds a FINISHED run (clean or over the bar) for today. Otherwise:
#   - busy: an ingest or other writer runs (ps, the markers `make status` uses), free disk under
#     12 GB, or 1-minute load over 4 -> exit 3 "busy, retry" (a start refused by a guard is not
#     a finished run, so launchd's retries continue);
#   - removes the old clone (only a path ending in /perf-clone/data that is not the real store),
#     `cp -cR var/data` into it, and re-checks that no ingest started during the copy (if one
#     did: the clone is discarded, exit 3);
#   - runs scripts/perf/fast_bench.py --data-url file://<clone> --record with the default guards
#     (never lowered), appends a line to var/logs/perf_gate.status, deletes the clone, and
#     notifies the owner (osascript, as deploy.sh) when a view is over the bar.
#   - EVIDENCE: var/logs/perf_gate/YYYY-MM-DD/ (the last 14 kept; nothing is written outside
#     var/logs): status.json, run.log, ops.json, views.json, samples-partial.json (per op per
#     pass), run-meta.json, load.csv (load and free disk every 10 s), procs-start.txt /
#     procs-end.txt (top 10 by CPU), snapshot.json, profiles.md (page_profile.py on the 3 slowest
#     ops over the bar, 60 s at most); one line per run in var/logs/perf_gate/summary.csv. The bench stops
#     itself within 5 minutes (--budget-s 270); with the snapshot the night's run is ~10 minutes.
#     A noisy or low-confidence bench run is not recorded (it is still a finished day).
#
# The benchmark phase is hard-capped at 300 s (PERF_BENCH_LIMIT_S): a watchdog kills the whole
# process group (the bench and its API child), marks the run over-time (not recorded, a finished
# day, so no retry loop) and the clone is deleted. Phase timings (wait_s, snapshot_s, bench_s,
# cleanup_s, total_s) go to the status line; the owner is notified when bench_s > 300, total_s >
# 900 or a view is over the bar. The 5-minute cap is the benchmark phase; the snapshot is separate.
#
# Exit codes: 0 done (clean) or nothing to do today; 1 finished with a view over the bar without
# a named exception, or an operation that failed; 2 refused (a path guard, or the bench refused);
# 3 busy, retry (also: another instance holds the lock); 4 over-time (the bench hit its wall cap).
# After the copy every outcome is a finished day (one notification, no re-copy at the next retry):
# a bench refusal (2) and a crash (reported as outcome=crashed, exit 1) included. The nightly's own
# history is var/logs/perf_gate/history.jsonl; the repo's benchmarks/critical_path_history.jsonl
# is only ever changed by a PR (docs/perf/page-latency-bar.md). Env (tests): PERF_CLONE_ROOT, PERF_SRC, PERF_STATUS, PERF_NOW_DATE, PERF_NOW_HM,
# PERF_PS_FILE, PERF_FREE_GB, PERF_LOAD, PERF_BENCH_CMD, PERF_NOTIFY, PERF_BENCH_LIMIT_S,
# PERF_TOTAL_LIMIT_S.
set -uo pipefail

repo=$(cd "$(dirname "$0")/../.." && pwd)
src=${PERF_SRC:-$repo/var/data}
clone=${PERF_CLONE_ROOT-/Users/adarbari/perf-clone/data}  # set but empty is an error, not a default
status=${PERF_STATUS:-$repo/var/logs/perf_gate.status}
today=${PERF_NOW_DATE:-$(date +%Y-%m-%d)}
hm=${PERF_NOW_HM:-$(date +%H%M)}
min_disk_gb=12
max_load=4
markers='algotrade-ingest|var/logs/'

t_start=$(date +%s)
bench_limit=${PERF_BENCH_LIMIT_S:-300}
total_limit=${PERF_TOTAL_LIMIT_S:-900}
logs=$(dirname "$status")
rundir=$logs/perf_gate/$today
keep_runs=14
rundir_made=0

say() { echo "perf_gate: $*" >&2; if [ "$rundir_made" = 1 ]; then echo "perf_gate: $*" >>"$rundir/run.log"; fi; }

if [ "$((10#$hm))" -lt 300 ]; then exit 0; fi  # before 03:00 local
if [ -f "$status" ] && grep -q "^date=$today .*finished=yes" "$status"; then exit 0; fi

# the clone is removed and rewritten: only the fixed clone path, never the real store
case "$clone" in /*) ;; *) say "refusing: PERF_CLONE_ROOT must be an absolute path (got '$clone')"; exit 2 ;; esac
case "$clone" in */perf-clone/data) ;; *) say "refusing: $clone does not end in /perf-clone/data"; exit 2 ;; esac
real_src=$(cd "$src" 2>/dev/null && pwd -P || echo "$src")
real_clone=$(cd "$(dirname "$clone")" 2>/dev/null && pwd -P || dirname "$clone")/data
case "$real_clone/" in "$real_src"/*) say "refusing: the clone is the real store"; exit 2 ;; esac
case "$real_src/" in "$real_clone"/*) say "refusing: the real store is inside the clone"; exit 2 ;; esac
[ "$real_clone" != "$real_src" ] || { say "refusing: the clone is the real store"; exit 2; }
[ -d "$src" ] || { say "refusing: no store at $src"; exit 2; }

# one instance at a time: an atomic mkdir lock with a pid file; a lock whose pid is dead is stale
lockdir=$logs/perf_gate/lock.d
mkdir -p "$logs/perf_gate"
lock_held=0
take_lock() {
  if mkdir "$lockdir" 2>/dev/null; then echo $$ >"$lockdir/pid"; lock_held=1; return 0; fi
  holder=$(cat "$lockdir/pid" 2>/dev/null || true)
  if [ -n "$holder" ] && kill -0 "$holder" 2>/dev/null; then return 1; fi
  rm -rf "$lockdir"  # stale: its owner is gone
  mkdir "$lockdir" 2>/dev/null || return 1
  echo $$ >"$lockdir/pid"; lock_held=1
}
if ! take_lock; then say "busy, retry: another perf gate run holds $lockdir"; exit 3; fi
wd_pid=
clone_made=0
cleanup() {
  [ -n "${sampler_pid:-}" ] && kill "$sampler_pid" 2>/dev/null
  [ "$lock_held" = 1 ] && rm -rf "$lockdir"
  return 0
}
abort() {  # TERM / INT: stop the bench's whole process group, drop the clone, release the lock
  [ -n "$wd_pid" ] && kill -TERM "$wd_pid" 2>/dev/null
  [ -n "$wd_pid" ] && wait "$wd_pid" 2>/dev/null
  [ "$clone_made" = 1 ] && [ -d "$clone" ] && rm -rf "$clone"
  say "aborted by a signal"
  cleanup
  exit 143
}
trap cleanup EXIT
trap abort TERM INT

mkdir -p "$rundir"; rundir_made=1
sampler_pid=
free_now() { df -k "$(dirname "$clone")" 2>/dev/null | awk 'NR==2 {printf "%d", $4/1048576}'; }
load_now() { uptime | sed 's/.*load averages*: *//' | awk '{gsub(",", "", $1); print $1}'; }
echo "epoch,load1,free_gb" >"$rundir/load.csv"
( while true; do echo "$(date +%s),$(load_now),$(free_now)" >>"$rundir/load.csv"; sleep "${PERF_SAMPLE_S:-10}"; done ) >/dev/null 2>&1 &
sampler_pid=$!

top_procs() { ps -Ao pid,pcpu,pmem,etime,command 2>/dev/null | sed 1d | sort -k2 -nr | head -10 | cut -c1-200; }

# status.json (and the summary line) from the shell variables; $1 = the stop reason
finish_evidence() {
  STOP_REASON=$1 RUNDIR=$rundir SUMMARY=$logs/perf_gate/summary.csv TODAY=$today SHA=${sha:-unknown} \
    CODE=${code:-3} WAIT_S=${wait_s:-0} SNAPSHOT_S=${snapshot_s:-0} BENCH_S=${bench_s:-0} \
    CLEANUP_S=${cleanup_s:-0} TOTAL_S=$(( $(date +%s) - t_start )) VIEWS_OVER=${views_over:-} \
    ABOVE=${above:-} KEEP=$keep_runs python3 - <<'PY'
import csv, json, os, re, shutil
from pathlib import Path
e = os.environ
run = Path(e["RUNDIR"])
meta = {}
if (run / "run-meta.json").is_file():
    meta = json.loads((run / "run-meta.json").read_text())
reason = e["STOP_REASON"] or meta.get("stop_reason", "")
if e["STOP_REASON"] == "" and meta.get("low_confidence"):
    reason = "low-confidence"
status = {
    "date": e["TODAY"], "sha": e["SHA"], "exit_code": int(e["CODE"]), "stop_reason": reason,
    "wait_s": int(e["WAIT_S"]), "snapshot_s": int(e["SNAPSHOT_S"]), "bench_s": int(e["BENCH_S"]),
    "cleanup_s": int(e["CLEANUP_S"]), "total_s": int(e["TOTAL_S"]),
    "passes": meta.get("passes"), "budget_s": meta.get("budget_s"),
    "bench_elapsed_s": meta.get("elapsed_s"), "noisy": meta.get("noisy"),
    "views_over_bar": e["VIEWS_OVER"], "seconds_above": e["ABOVE"],
}
(run / "status.json").write_text(json.dumps(status, indent=1) + "\n")
summary = Path(e["SUMMARY"])
new = not summary.exists()
with (summary.open("a", newline="") if e["STOP_REASON"] != "guard" else open(os.devnull, "w")) as f:
    w = csv.writer(f)
    if new:
        w.writerow("date sha total_s snapshot_s bench_s passes views_over_bar seconds_above noisy notes".split())
    w.writerow([status["date"], status["sha"], status["total_s"], status["snapshot_s"],
                status["bench_s"], status["passes"], status["views_over_bar"],
                status["seconds_above"], status["noisy"], reason])
days = sorted(d for d in run.parent.iterdir() if d.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", d.name))
for old in days[: max(0, len(days) - int(e["KEEP"]))]:
    shutil.rmtree(old, ignore_errors=True)
PY
}

busy() {  # a guard: record why, exit 3
  say "busy, retry: $1"
  code=3; finish_evidence guard
  exit 3
}

ps_lines() { if [ -n "${PERF_PS_FILE:-}" ]; then cat "$PERF_PS_FILE"; else ps -eo pid,args; fi; }
busy_writer() {
  ps_lines | grep -E "$markers" | grep -vE "grep|perf_gate_nightly|fast_bench" | head -1
}
if w=$(busy_writer) && [ -n "$w" ]; then busy "a writer runs: $w"; fi

free_gb=${PERF_FREE_GB:-$(free_now)}
if [ "${free_gb:-0}" -lt "$min_disk_gb" ]; then busy "${free_gb:-?} GB free, need $min_disk_gb"; fi
load=${PERF_LOAD:-$(load_now)}
if awk "BEGIN {exit !($load > $max_load)}"; then busy "load $load over $max_load"; fi

t_ready=$(date +%s)
drop_clone() { [ -d "$clone" ] && rm -rf "$clone"; return 0; }
case "$clone" in */perf-clone/data) ;; *) exit 2 ;; esac
drop_clone
mkdir -p "$(dirname "$clone")"
top_procs >"$rundir/procs-start.txt"
free_before=$free_gb
clone_made=1
if ! cp -cR "$src" "$clone"; then drop_clone; busy "the copy failed"; fi
t_copied=$(date +%s)
snapshot_s=$((t_copied - t_ready)); wait_s=$((t_ready - t_start))
ingest_during=false
if w=$(busy_writer) && [ -n "$w" ]; then ingest_during=true; fi
files="skipped: counting every file is slower than the copy's value (PERF_COUNT_FILES=1 counts)"
[ "${PERF_COUNT_FILES:-0}" = 1 ] && files=$(find "$clone" -type f | wc -l | tr -d ' ')
printf '{"copy_s": %s, "file_count": "%s", "free_gb_before": %s, "free_gb_after": %s, "ingest_started_during_copy": %s}\n' \
  "$snapshot_s" "$files" "${free_before:-null}" "$(free_now)" "$ingest_during" >"$rundir/snapshot.json"
if [ "$ingest_during" = true ]; then drop_clone; busy "a writer started during the copy: $w"; fi

sha=$(git -C "$repo" rev-parse --short=9 HEAD 2>/dev/null || echo unknown)
out=$(mktemp)
py=${PERF_PY:-$repo/.venv/bin/python}
cmd=${PERF_BENCH_CMD:-"$py $repo/scripts/perf/fast_bench.py --data-url file://$clone --record --machine nightly-clone --timings wait_s=$wait_s,snapshot_s=$snapshot_s --out $rundir --history-file $logs/perf_gate/history.jsonl"}

# the watchdog: run a command in its own process group; at the limit kill the whole group (the
# bench and its API child) and exit 124. macOS has no `timeout`. $1 = seconds. It `exec`s, so
# call it only in a subshell or the background.
watchdog() {
  exec python3 - "$@" <<'PY'
import os, signal, subprocess, sys
limit, cmd = float(sys.argv[1]), sys.argv[2:]
p = subprocess.Popen(cmd, start_new_session=True)
def stop(*_):
    os.killpg(p.pid, signal.SIGKILL)
    p.wait()
    sys.exit(143)
signal.signal(signal.SIGTERM, stop)
try:
    sys.exit(p.wait(timeout=limit))
except subprocess.TimeoutExpired:
    os.killpg(p.pid, signal.SIGKILL)
    p.wait()
    sys.exit(124)
PY
}
t_bench=$(date +%s)
# shellcheck disable=SC2086
watchdog "$bench_limit" $cmd >"$out" 2>&1 &
wd_pid=$!
wait "$wd_pid"
code=$?
wd_pid=
t_benched=$(date +%s)
bench_s=$((t_benched - t_bench))
top_procs >"$rundir/procs-end.txt"
over=$(sed -n 's/^\([0-9]*\) views over.*(\([0-9.]*\) s above the bar).*/\1 \2/p' "$out" | tail -1)
views_over=${over%% *}; above=${over##* }
# every outcome after the copy is a finished day (no endless re-copy of the store at every retry)
finished=yes; overtime=no; outcome=ok
if [ "$code" -eq 124 ]; then overtime=yes; code=4; outcome=over-time
elif [ "$code" -eq 2 ]; then outcome=refused
elif [ "$code" -eq 1 ] && [ -n "${over:-}" ]; then outcome=over-the-bar
elif [ "$code" -ne 0 ]; then outcome=crashed; code=1
fi
cat "$out" >>"$rundir/run.log"
cp "$out" "$logs/perf_gate.last.log"
rm -f "$out"

# the profiles: the slowest 3 operations over the bar, 60 s at most, before the clone goes
if [ "$outcome" = over-the-bar ] && [ -f "$rundir/ops.json" ]; then
  names=$(python3 - "$rundir/ops.json" <<'PY'
import json, sys
ops = json.load(open(sys.argv[1]))
slow = sorted({(o["avg"], o["name"]) for o in ops.values() if o["avg"] > 1000}, reverse=True)
print(" ".join(list(dict.fromkeys(n for _, n in slow))[:3]))
PY
)
  pcmd=${PERF_PROFILE_CMD:-"$py $repo/scripts/perf/api_latency.py --profile --data-url file://$clone --profile-limit 20 --profile-out $rundir/profiles.md --ops"}
  # shellcheck disable=SC2086
  [ -n "$names" ] && { (watchdog 60 $pcmd $names) >>"$rundir/run.log" 2>&1 || say "profiles cut or failed"; }
fi

drop_clone
t_end=$(date +%s)
cleanup_s=$((t_end - t_benched)); total_s=$((t_end - t_start))
echo "date=$today sha=$sha views_over=${views_over:-?} seconds_above=${above:-?} exit=$code finished=$finished outcome=$outcome over_time=$overtime wait_s=$wait_s snapshot_s=$snapshot_s bench_s=$bench_s cleanup_s=$cleanup_s total_s=$total_s" >>"$status"
reason=""; [ "$overtime" = yes ] && reason=over-time
[ "$outcome" = refused ] && reason=refused; [ "$outcome" = crashed ] && reason=crashed
finish_evidence "$reason"

if [ "$code" -ne 0 ] || [ "$bench_s" -gt "$bench_limit" ] || [ "$total_s" -gt "$total_limit" ] || [ "$overtime" = yes ]; then
  msg="1 s page gate: ${views_over:-?} views over the bar (${above:-?} s above); bench ${bench_s}s, total ${total_s}s; evidence in var/logs/perf_gate/$today/"
  [ "$outcome" = crashed ] && msg="1 s page gate CRASHED (no result): $msg"
  [ "$outcome" = refused ] && msg="1 s page gate REFUSED by the bench (no result): $msg"
  [ "$overtime" = yes ] && msg="1 s page gate OVER-TIME: bench killed at ${bench_limit}s (not recorded); $msg"
  if [ -n "${PERF_NOTIFY:-}" ]; then "$PERF_NOTIFY" "$msg" || true
  else osascript -e "display notification \"${msg//[\"\\]/}\" with title \"algotrade perf gate\"" || true; fi
fi
exit "$code"
