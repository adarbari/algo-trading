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
#     `cp -cR` of tables/ runs/ serving/ only (APFS clonefile at nice -n 10, CPU only: `taskpolicy -b` throttles I/O and was 4x slower; PERF_COPY_CMD
#     overrides, for tests; raw/ and staging/ are not copied; the copy is killed at 900 s WALL CLOCK), and re-checks every 10 s while it runs that no writer
#     started (if one did: the copy stops, the clone is discarded, exit 3). A RUNNING delete of a
#     data.trash.* (rm/find, the clone's own sibling) is itself a guard: exit 3 busy, never copy while it runs;
#   - runs scripts/perf/fast_bench.py --data-url file://<clone> --record with the default guards
#     (never lowered), appends a line to var/logs/perf_gate.status, deletes the clone, and
#     notifies the owner (osascript, as deploy.sh) when a view is over the bar.
#   - EVIDENCE: var/logs/perf_gate/YYYY-MM-DD/ (the last 14 kept; nothing is written outside
#     var/logs; README.txt in it says which file answers which question; the FLIGHT RECORDER
#     (scripts/perf/flight_recorder.py) adds timeline.csv every 10 s, ops-stream.jsonl, bench-progress.json,
#     prekill/ at 70% of a cap, kill-report.json on every stop, api.log, bench-head.txt): status.json, run.log, ops.json, views.json, samples-partial.json (per op per
#     pass), run-meta.json, load.csv (epoch before the commands, load, free disk, how late the tick was, how long the sample took; every 10 s), procs-start.txt /
#     procs-end.txt (top 10 by CPU), snapshot.json, profiles.md (page_profile.py on the 3 slowest
#     ops over the bar, 60 s at most); one line per run in var/logs/perf_gate/summary.csv. The bench stops
#     itself within 5 minutes (--budget-s 270); with the snapshot the night's run is ~10 minutes.
#     A noisy or low-confidence bench run is not recorded (it is still a finished day).
#
# The benchmark phase is hard-capped at 300 s (PERF_BENCH_LIMIT_S): a watchdog kills the whole
# process group (the bench and its API child), marks the run over-time (not recorded, a finished
# day, so no retry loop) and the clone is deleted. Phase timings (wait_s, snapshot_s, bench_s,
# cleanup_s, total_s) go to the status line; the owner is notified when bench_s > 300, total_s >
# 720 or a view is over the bar. The 5-minute cap is the benchmark phase; the snapshot is separate.
#
# Exit codes: 0 done (clean) or nothing to do today; 1 finished with a view over the bar without
# a named exception, or an operation that failed; 2 refused (a path guard, or the bench refused);
# 3 busy, retry (also: another instance holds the lock); 4 over-time (the bench hit its wall cap).
# After the copy every outcome is a finished day (one notification, no re-copy at the next retry):
# a bench refusal (2) and a crash (reported as outcome=crashed, exit 1) included. The nightly's own
# history is var/logs/perf_gate/history.jsonl; the repo's benchmarks/critical_path_history.jsonl
# is only ever changed by a PR (docs/perf/page-latency-bar.md). Env (tests): PERF_CLONE_ROOT, PERF_SRC, PERF_STATUS, PERF_NOW_DATE, PERF_NOW_HM,
# PERF_PS_FILE, PERF_FREE_GB, PERF_LOAD, PERF_BENCH_CMD, PERF_NOTIFY, PERF_BENCH_LIMIT_S,
# PERF_TOTAL_LIMIT_S, PERF_COPY_CMD, PERF_TREE, PERF_DEPLOY_WAIT_S, PERF_DEPLOY_POLL_S, PERF_PORT_BASE, PERF_SNAPSHOT_LIMIT_S, PERF_LOWPRI, PERF_POLL_S.
set -uo pipefail

repo=$(cd "$(dirname "$0")/../.." && pwd)
src=${PERF_SRC:-$repo/var/data}
clone=${PERF_CLONE_ROOT-/Users/adarbari/perf-clone/data}  # set but empty is an error, not a default
status=${PERF_STATUS:-$repo/var/logs/perf_gate.status}
today=${PERF_NOW_DATE:-$(date +%Y-%m-%d)}
hm=${PERF_NOW_HM:-$(date +%H%M)}
min_disk_gb=12
max_load=4
max_pause_aborts=3  # a day with this many copies stopped by a paused machine finishes (repeated-pauses)
markers='algotrade-ingest|algotrade_ingestion|algotrade-backtest|var/logs/'
# a real writer: an ingest or backtest command (rollups, nightly and compaction run through them). Any
# other marker match is a driver script (var/logs/...): a writer only while it has a live child that is not `sleep`
# An auto-deploy (`algotrade-ingest deploy-hold --deploy-only -- bash <tree>/scripts/ops/deploy.sh --slot S
# --apply ...`, and its follow-up `deploy-hold -- bash <tree>/scripts/ops/deploy.sh --slot S --ingest-apply
# ...`) writes no store table: it takes the store's `deploy` lock (a file under locks/, not copied) and does a
# git checkout in the release tree, uv sync, the web build, an API restart and verify
# (scripts/ops/deploy.sh, apps/ingestion/.../ops/hold.py: "writes nothing to the store"). So it does NOT stop
# the COPY (hand run 5 lost its copy to one at 223 s). But it changes the CODE the bench runs (checkout, uv sync
# in the same tree and venv): the bench never starts while one runs (a bounded wait, then busy), and a run whose
# release tree HEAD moved during the bench is not recorded. Exactly these two command lines; every other
# algotrade-ingest command (deploy-hold with neither flag included) stays a writer.
deploy_apply_re='^([^ ]*python[^ ]* +)?([^ ]*/)?algotrade-ingest deploy-hold --deploy-only -- bash [^ ]*/scripts/ops/deploy\.sh --slot [^ ]+ --apply( |$)'
deploy_ingest_re='^([^ ]*python[^ ]* +)?([^ ]*/)?algotrade-ingest deploy-hold -- bash [^ ]*/scripts/ops/deploy\.sh --slot [^ ]+ --ingest-apply( |$)'
deploy_re="$deploy_apply_re|$deploy_ingest_re"
real_writer='algotrade-ingest|algotrade_ingestion|algotrade-backtest|rollups|nightly|compaction'

# the bench starts an API on a spare port of ALGOTRADE_PORT_BASE + 8..19: a fixed block outside the
# worktrees' (10000-14990) and the live API's 8000, so the nightly never collides with either
export ALGOTRADE_PORT_BASE=${PERF_PORT_BASE:-15990}
t_start=$(date +%s)
bench_limit=${PERF_BENCH_LIMIT_S:-300}
total_limit=${PERF_TOTAL_LIMIT_S:-720}
snapshot_limit=${PERF_SNAPSHOT_LIMIT_S:-900}  # a safety net: the copy is expected at 3-4 min
# what the API and the bench read: tables, runs and serving (locks are created empty). raw/ (vendor
# payloads the API never opens) and staging/ (transient) are NOT copied: ~245k files and 7 GB less
copy_entries="tables runs serving"
logs=$(dirname "$status")
rundir=$logs/perf_gate/$today
keep_runs=14
rundir_made=0

say() { echo "perf_gate: $*" >&2; if [ "$rundir_made" = 1 ]; then echo "perf_gate: $*" >>"$rundir/run.log"; fi; }

if [ "$((10#$hm))" -lt 300 ]; then exit 0; fi  # before 03:00 local
if [ -f "$status" ] && grep -q "^date=$today .*finished=yes" "$status"; then exit 0; fi

# hold the Mac awake for the whole run (idle sleep only; a lid close on battery cannot be prevented: the
# pause rule in the copy's poll loop detects it). Harmless where caffeinate is missing.
if command -v caffeinate >/dev/null 2>&1; then caffeinate -i -w $$ >/dev/null 2>&1 & fi

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
lockdir=$logs/perf_gate/lock   # a symlink whose target is the holder's pid: created atomically
guard=$lockdir.takeover
mkdir -p "$logs/perf_gate"
lock_held=0
# lstart is locale and TZ dependent: always read it as C / UTC, whoever started the run
start_of() { LC_ALL=C TZ=UTC ps -o lstart= -p "$1" 2>/dev/null | tr -s ' ' '_' | sed 's/^_//; s/_$//'; }
mytag="$$:$(start_of $$)"  # pid and process start time: a reused pid has another start time
alive() {  # a holder tag is pid or pid:start; a dead pid, a garbage tag or another start = stale
  local pid=${1%%:*} start=
  case "$1" in *:*) start=${1#*:} ;; esac
  case "$pid" in ''|*[!0-9]*) return 1 ;; esac
  kill -0 "$pid" 2>/dev/null || return 1
  [ -z "$start" ] || [ "$(start_of "$pid")" = "$start" ]
}
holder_of() { readlink "$1" 2>/dev/null || true; }  # empty or garbage = no live holder
take_lock() {
  # (never `ln -s` onto a real directory: it would link inside it; a leftover directory is stale)
  if { [ ! -d "$lockdir" ] || [ -L "$lockdir" ]; } && ln -s "$mytag" "$lockdir" 2>/dev/null; then
    lock_held=1; return 0
  fi
  alive "$(holder_of "$lockdir")" && return 1
  # stale (a dead pid, an empty or garbage target, or a leftover directory). Takeovers are
  # serialised by a guard that is itself a pid symlink (a dead one is cleaned), and the holder is
  # read again under it, so two instances never both take over, nor take a live lock.
  if ! ln -s "$mytag" "$guard" 2>/dev/null; then
    alive "$(holder_of "$guard")" && return 1
    rm -rf "$guard"; ln -s "$mytag" "$guard" 2>/dev/null || return 1
  fi
  if alive "$(holder_of "$lockdir")"; then rm -f "$guard"; return 1; fi
  rm -rf "$lockdir"
  if ln -s "$mytag" "$lockdir" 2>/dev/null; then lock_held=1; fi
  rm -f "$guard"
  [ "$lock_held" = 1 ]
}
if ! take_lock; then say "busy, retry: another perf gate run holds $lockdir"; exit 3; fi
wd_pid=
clone_made=0
cleanup() {
  [ -n "${sampler_pid:-}" ] && kill "$sampler_pid" 2>/dev/null
  [ -n "${timeline_pid:-}" ] && kill "$timeline_pid" 2>/dev/null
  [ -n "${prekill_pid:-}" ] && kill "$prekill_pid" 2>/dev/null
  [ "$lock_held" = 1 ] && [ "$(holder_of "$lockdir")" = "$mytag" ] && rm -f "$lockdir"
  return 0
}
abort() {  # TERM / INT: stop the bench's whole process group, drop the clone, release the lock
  [ -n "$wd_pid" ] && kill -TERM "$wd_pid" 2>/dev/null
  [ -n "$wd_pid" ] && wait "$wd_pid" 2>/dev/null
  [ "$clone_made" = 1 ] && discard_clone
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

top_procs() { ps -Ao pid,pcpu,pmem,etime,command 2>/dev/null | sed 1d | sort -k2 -nr | head -10 | cut -c1-200; }

# status.json (and the summary line) from the shell variables; $1 = the stop reason
finish_evidence() {
  STOP_REASON=$1 RUNDIR=$rundir SUMMARY=$logs/perf_gate/summary.csv TODAY=$today SHA=${sha:-unknown} \
    CODE=${code:-3} WAIT_S=${wait_s:-0} SNAPSHOT_S=${snapshot_s:-0} BENCH_S=${bench_s:-0} \
    CLEANUP_S=${cleanup_s:-0} TOTAL_S=$(( $(date +%s) - t_start )) VIEWS_OVER=${views_over:-} \
    ABOVE=${above:-} KEEP=$keep_runs NOTE=${kr_note:-} python3 - <<'PY'
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
                status["seconds_above"], status["noisy"],
                reason + (f" | {e['NOTE']}" if e.get("NOTE") else "")])
days = sorted(d for d in run.parent.iterdir() if d.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", d.name))
for old in days[: max(0, len(days) - int(e["KEEP"]))]:
    shutil.rmtree(old, ignore_errors=True)
PY
  [ -f "$fr" ] && python3 "$fr" finish --rundir "$rundir" >/dev/null 2>&1
  return 0
}

busy() {  # a guard: record why, exit 3
  say "busy, retry: $1"
  stop_prekill; kill_report "$phase" 0 "guard: $1"
  code=3; finish_evidence guard
  exit 3
}

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
# load.csv sampler: never blocks on `df` / `uptime` (a sleep or an I/O stall used to leave gaps of 900 s). Each tick
# stamps the epoch BEFORE the commands, runs the sample as its own capped job (5 s each) that writes its
# row when done, and never starts a second one while the last still runs (a row marked `skipped`).
# Columns: epoch (before), load1, free_gb, late_s (this tick vs the interval: the machine paused or the
# loop was not scheduled), took_s (the sample's duration).
echo "epoch,load1,free_gb,late_s,took_s" >"$rundir/load.csv"
sample_row() {  # $1 = epoch before, $2 = late_s
  local t1 l f
  l=$( (watchdog 5 uptime) 2>/dev/null | sed 's/.*load averages*: *//' | awk '{gsub(",", "", $1); print $1}')
  f=$( (watchdog 5 df -k "$(dirname "$clone")") 2>/dev/null | awk 'NR==2 {printf "%d", $4/1048576}')
  t1=$(date +%s)
  echo "$1,$l,$f,$2,$((t1 - $1))" >>"$rundir/load.csv"
}
(
  every=${PERF_SAMPLE_S:-10}; last=$(date +%s); prev=
  while true; do
    now=$(date +%s); late=$((now - last - every)); [ "$late" -lt 0 ] && late=0; last=$now
    if [ -n "$prev" ] && kill -0 "$prev" 2>/dev/null; then echo "$now,,,$late,skipped" >>"$rundir/load.csv"
    else sample_row "$now" "$late" & prev=$!; fi
    sleep "$every"
  done
) >/dev/null 2>&1 &
sampler_pid=$!

# the FLIGHT RECORDER (scripts/perf/flight_recorder.py): a timeline every 10 s across all phases, a
# pre-kill sample at 70% of a phase's cap, a kill report on every stop; all inside $rundir
fr=$repo/scripts/perf/flight_recorder.py
phase=wait; timeline_pid=; prekill_pid=; kr_msg=; kr_note=
set_phase() { phase=$1; echo "$1" >"$rundir/phase.txt"; echo "$1 $(date +%s)" >>"$rundir/phases.txt"; }
set_phase wait
if [ -f "$fr" ]; then
  python3 "$fr" timeline --rundir "$rundir" --root $$ --every "${PERF_SAMPLE_S:-10}" --store "$logs" >/dev/null 2>&1 &
  timeline_pid=$!
fi
start_prekill() {  # $1 = phase, $2 = seconds into it: a sample then, if it still runs
  [ -f "$fr" ] || return 0
  python3 "$fr" prekill --rundir "$rundir" --root $$ --phase "$1" --after "$2" >/dev/null 2>&1 &
  prekill_pid=$!
}
stop_prekill() { [ -n "$prekill_pid" ] && kill "$prekill_pid" 2>/dev/null; prekill_pid=; return 0; }
kill_report() {  # $1 = phase, $2 = cap in seconds, $3 = why: kill-report.json; kr_msg for the notice
  kr_msg=; kr_note=
  [ -f "$fr" ] || return 0
  kr_note=$(python3 "$fr" report --rundir "$rundir" --phase "$1" --cap "$2" --reason "$3" 2>/dev/null) || return 0
  kr_msg=" ($kr_note)"
}
# CPU priority only for the copy and the delete. NOT `taskpolicy -b`: it throttles disk I/O and made the
# CoW copy 4.0x slower (measured 2026-10-23: 42 s normal, 170 s under -b, 42 s under nice -n 10).
: "${PERF_LOWPRI=nice -n 10}"
trash_dir=
trash_ok() {  # only a sibling data.trash.* of the clone is ever deleted
  case "$1" in */perf-clone/data.trash.*) [ "$(dirname "$1")" = "$(dirname "$clone")" ] ;; *) return 1 ;; esac
}
rename_clone() {  # an instant rename on the same volume: the clone leaves the critical path
  [ -d "$clone" ] || return 0
  n=0; trash_dir=$clone.trash.$today
  while [ -e "$trash_dir" ]; do n=$((n + 1)); trash_dir=$clone.trash.$today.$n; done
  mv "$clone" "$trash_dir"
}
# The delete runs in its OWN session and process group (python's start_new_session; macOS has no setsid):
# under launchd (no AbandonProcessGroup in older plists) the wrapper's whole group is killed when it exits,
# and a delete in it died at once, leaving the trash: with a leftover meaning "busy" the gate would never
# copy again. nice (PERF_LOWPRI) and the trash_ok guard are kept; `trash-delete.pid` holds
# "pid trash start_epoch" while it runs (evidence; the busy check reads `ps`).
delete_trash() {  # detached in its own session, low priority, guarded; logs trash_delete_s when it finishes
  trash_ok "$1" || return 0
  mkdir -p "$logs/perf_gate"
  TRASH=$1 LOGS=$logs LOWPRI=$PERF_LOWPRI python3 - <<'PY'
import os, subprocess
body = r"""
t0=$(date +%s)
echo "$$ $TRASH $t0" >"$LOGS/perf_gate/trash-delete.pid"
$LOWPRI find "$TRASH" -delete   # measured 6-7 s vs rm -rf 10 s per 100k CoW files, parallel rm 8 s
took=$(( $(date +%s) - t0 ))
rm -f "$LOGS/perf_gate/trash-delete.pid"
t=${TRASH##*.trash.}; day=${t%%.*}  # the day of the run that made this trash, not today
dayrun=$LOGS/perf_gate/$day
[ -d "$dayrun" ] || exit 0
echo "$took" >"$dayrun/trash_delete_s.txt"
TOOK=$took RUNDIR=$dayrun python3 -c '
import json, os
from pathlib import Path
f = Path(os.environ["RUNDIR"]) / "status.json"
if f.is_file():
    d = json.loads(f.read_text())
    d["trash_delete_s"] = int(os.environ["TOOK"])
    f.write_text(json.dumps(d, indent=1) + "\n")
'
"""
subprocess.Popen(
    ["sh", "-c", body],
    start_new_session=True,
    stdin=subprocess.DEVNULL,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    env=os.environ,
)
PY
  return 0
}
discard_clone() { rename_clone; [ -n "$trash_dir" ] && delete_trash "$trash_dir"; return 0; }

# a delete of an earlier run's clone is running (rm -rf or find on a sibling data.trash.*): never copy while it runs
trash_delete_running() {
  ps_lines | grep -F "$(dirname "$clone")/data.trash." | grep -E '^ *[0-9]+ +([^ ]*/)?(rm|find) ' |
    grep -vE "perf_gate_nightly" | head -1
}
ps_lines() { if [ -n "${PERF_PS_FILE:-}" ]; then cat "$PERF_PS_FILE"; else ps -eo pid,args; fi; }
# a driver script parked in a sleep loop writes nothing: it is not a writer. Fail closed: a driver whose
# children cannot be listed or read, or that has any child other than `sleep`, is a writer.
driver_busy() {  # $1 = pid; returns 0 (busy) unless it has no child or only sleep children
  local kids rc c cargs cmd
  case "$1" in ''|*[!0-9]*) return 0 ;; esac
  kids=$(pgrep -P "$1" 2>/dev/null); rc=$?
  [ "$rc" -le 1 ] || return 0                 # pgrep failed or is missing: cannot tell
  for c in $kids; do
    cargs=$(ps -o args= -p "$c" 2>/dev/null)
    [ -n "$cargs" ] || return 0               # the child vanished or is unreadable: cannot tell
    cmd=${cargs%%[[:space:]]*}; cmd=${cmd##*/}   # no word splitting: a glob in the args must not expand
    [ "$cmd" = sleep ] || return 0
  done
  return 1
}
# a running deploy (one of the two exact command lines): "pid args", empty when none
deploy_running() { ps_lines | sed 's/^ *[0-9]* *//' | grep -E "$deploy_re" | head -1; }
# wait up to PERF_DEPLOY_WAIT_S (600) for a running deploy to finish, polling every PERF_DEPLOY_POLL_S (10)
wait_deploy_done() {
  local waited=0 limit=${PERF_DEPLOY_WAIT_S:-600} every=${PERF_DEPLOY_POLL_S:-10}
  while [ -n "$(deploy_running)" ]; do
    [ "$waited" -ge "$limit" ] && return 1
    [ "$waited" = 0 ] && say "a deploy runs: waiting up to ${limit}s for it before going on"
    sleep "$every"; waited=$((waited + every))
  done
  return 0
}
busy_writer() {  # $1 = copy: a deploy is no writer while the copy runs (it is for everything else)
  local pid args
  ps_lines | grep -E "$markers" | grep -vE "grep|perf_gate_nightly|fast_bench" | {
    while read -r pid args; do
      if [ "${1:-}" = copy ] && printf '%s' "$args" | grep -qE "$deploy_re"; then  # no store table (see above)
        [ "$rundir_made" = 1 ] && ! grep -q "ignored deploy: pid $pid " "$rundir/run.log" 2>/dev/null &&
          echo "perf_gate: ignored deploy: pid $pid $args" >>"$rundir/run.log"
        continue
      fi
      if printf '%s' "$args" | grep -qE "$real_writer" || driver_busy "$pid"; then
        echo "$pid $args"; return 0
      fi
      [ "$rundir_made" = 1 ] && ! grep -q "ignored parked driver (no child but sleep): pid $pid " "$rundir/run.log" 2>/dev/null &&
        echo "perf_gate: ignored parked driver (no child but sleep): pid $pid $args" >>"$rundir/run.log"
    done
    return 0
  }
}
if d=$(trash_delete_running) && [ -n "$d" ]; then busy "trash delete running (pid $(printf '%s' "$d" | awk '{print $1}')): $d"; fi
wait_deploy_done || busy "a deploy is still running after ${PERF_DEPLOY_WAIT_S:-600}s: $(deploy_running)"
if w=$(busy_writer) && [ -n "$w" ]; then busy "a writer runs: $w"; fi

# a leftover clone or trash of an earlier run (no delete runs, checked above): start its delete in the
# background and be busy this tick; the copy never overlaps a delete (they contend on the one volume:
# 2k files/s instead of 6k, the first complete run took 2561 s). The next tick sees the delete running.
leftover=0
for t in "$clone".trash.*; do [ -e "$t" ] && { delete_trash "$t"; leftover=1; }; done
[ -d "$clone" ] && { discard_clone; leftover=1; }
if [ "$leftover" = 1 ]; then busy "a leftover clone or trash of an earlier run: its delete is started, retry once it is gone"; fi
free_gb=${PERF_FREE_GB:-$(free_now)}
if [ "${free_gb:-0}" -lt "$min_disk_gb" ]; then
  busy "${free_gb:-?} GB free, need $min_disk_gb"
fi
load=${PERF_LOAD:-$(load_now)}
if awk "BEGIN {exit !($load > $max_load)}"; then busy "load $load over $max_load"; fi

t_ready=$(date +%s)
case "$clone" in */perf-clone/data) ;; *) exit 2 ;; esac
mkdir -p "$(dirname "$clone")"
dev_of() { if [ -n "${PERF_DEV_CMD:-}" ]; then $PERF_DEV_CMD "$1"; else stat -c %d "$1" 2>/dev/null || stat -f %d "$1"; fi; }
# cp -c silently falls back to a full copy across volumes: the clone must be on the store's volume
if [ "$(dev_of "$src")" != "$(dev_of "$(dirname "$clone")")" ]; then
  say "refusing: $clone is not on the same volume as $src (cp -c would copy every byte)"; exit 2
fi
top_procs >"$rundir/procs-start.txt"
set_phase copy; start_prekill copy "$(( snapshot_limit * 7 / 10 ))"
free_before=$free_gb
clone_made=1
mkdir -p "$clone"
# the real nightly copies with cp -c (APFS clonefile: shared blocks); PERF_COPY_CMD replaces it
# where cp has no -c (the tests, Linux). One watchdog caps the whole copy.
progress_file=$rundir/copy-entry.txt; timings_file=$rundir/copy-timings.txt; : >"$timings_file"
# One cp per child of each entry (tables/<dataset>...), each timed, so a slow one shows in snapshot.json;
# an entry with no child is copied whole. The cap below is WALL CLOCK (date +%s), not the watchdog's
# monotonic timeout, which does not advance while the Mac sleeps: the watchdog gets a day, the poll loop
# enforces snapshot_limit.
SRC=$src CLONE=$clone ENTRIES=$copy_entries PROG=$progress_file TIMINGS=$timings_file COPY="$PERF_LOWPRI ${PERF_COPY_CMD:-cp -cR}" \
  watchdog 86400 sh -c '
set -e
copy_one() { t=$(date +%s); $COPY "$1" "$2"; echo "$3 $(( $(date +%s) - t ))" >>"$TIMINGS"; }
for e in $ENTRIES; do
  [ -e "$SRC/$e" ] || continue
  echo "$e" >"$PROG"
  kids=
  # one timed cp per dataset only for tables/ (about 17); runs/ (29k files) and serving/ go whole: a cp
  # per child of runs/ took about 100 files/s (hand run 5, 2026-10-23)
  if [ "$e" = tables ] && [ -d "$SRC/$e" ]; then
    for c in "$SRC/$e"/* "$SRC/$e"/.[!.]*; do [ -e "$c" ] && kids=1; done
  fi
  if [ -z "$kids" ]; then copy_one "$SRC/$e" "$CLONE/$e" "$e"; continue; fi
  mkdir -p "$CLONE/$e"
  for c in "$SRC/$e"/* "$SRC/$e"/.[!.]*; do
    [ -e "$c" ] || continue
    echo "$e/${c##*/}" >"$PROG"
    copy_one "$c" "$CLONE/$e/${c##*/}" "$e/${c##*/}"
  done
done
echo done >"$PROG"; mkdir -p "$CLONE/locks"' &
wd_pid=$!
# how far the copy got, written when it is stopped (the files and kB counts are capped at 5 s each);
# $snapshot_s must be set before the call so the counts are not added to the copy time
capped() { ( watchdog 5 sh -c "$1" _ "$clone" 2>/dev/null ); }
timings_json() {  # seconds per copied entry: {"tables/x": 12, ...}
  python3 - "$timings_file" <<'PY'
import json, sys
out = {}
for line in open(sys.argv[1]):
    name, _, sec = line.rpartition(" ")
    if name:
        out[name] = int(sec)
print(json.dumps(out))
PY
}
write_progress() {  # $1 = why the copy stopped
  local n kb entry
  n=$(capped 'find "$1" -type f | wc -l' | tr -d ' '); kb=$(capped 'du -sk "$1" | cut -f1' | tr -d ' ')
  entry=$(cat "$progress_file" 2>/dev/null)
  printf '{"copy_stopped": "%s", "copy_s": %s, "limit_s": %s, "entry": "%s", "files_so_far": "%s", "kb_so_far": "%s", "entry_s": %s, "free_gb_before": %s, "free_gb_after": %s}\n' \
    "$1" "$snapshot_s" "$snapshot_limit" "${entry:-none}" "${n:-unknown}" "${kb:-unknown}" "$(timings_json)" "${free_before:-null}" "$(free_now)" >"$rundir/snapshot.json"
}
# poll once a second on the WALL clock: the cap, a writer that appears (every PERF_POLL_S s: the copy would
# be torn: stop it, discard, retry later), and a pause: a gap over 60 s between ticks is logged
poll=${PERF_POLL_S:-10}; tick=0; writer_mid=; paused_s=; cap_hit=0; last_t=$(date +%s)
while kill -0 "$wd_pid" 2>/dev/null; do
  sleep 1; tick=$((tick + 1)); now=$(date +%s)
  if [ $((now - last_t)) -gt 60 ]; then
    paused_s=$((now - last_t))
    say "machine paused or stalled for $paused_s s (during the copy, tick $tick)"
    kill -TERM "$wd_pid" 2>/dev/null; break  # a copy across a sleep is not a result: retry, not a finished day
  fi
  last_t=$now
  if [ $((now - t_ready)) -ge "$snapshot_limit" ]; then cap_hit=1; kill -TERM "$wd_pid" 2>/dev/null; break; fi
  if [ $((tick % poll)) -eq 0 ] && w=$(busy_writer copy) && [ -n "$w" ]; then
    writer_mid=$w; kill -TERM "$wd_pid" 2>/dev/null; break
  fi
done
wait "$wd_pid"
copy_code=$?
wd_pid=
if [ -n "$paused_s" ]; then
  snapshot_s=$(( $(date +%s) - t_ready )); wait_s=$((t_ready - t_start))
  write_progress machine-paused
  stop_prekill; kill_report copy "$snapshot_limit" "machine paused $paused_s s"
  discard_clone
  aborts=$(( $(grep -c "^date=$today pause_abort=" "$status" 2>/dev/null || true) + 1 ))
  echo "date=$today pause_abort=$aborts finished=no" >>"$status"
  if [ "$aborts" -ge "$max_pause_aborts" ]; then  # the retry budget: the day finishes, one notification
    sha=$(git -C "$repo" rev-parse --short=9 HEAD 2>/dev/null || echo unknown)
    total_s=$(( $(date +%s) - t_start ))
    echo "date=$today sha=$sha views_over=? seconds_above=? exit=4 finished=yes outcome=repeated-pauses over_time=no wait_s=$wait_s snapshot_s=$snapshot_s bench_s=0 cleanup_s=0 total_s=$total_s" >>"$status"
    say "repeated pauses: $aborts copies stopped by a paused machine today"
    code=4; bench_s=0; cleanup_s=0; finish_evidence repeated-pauses
    msg="1 s page gate: the machine paused during the copy $aborts times today; no result tonight$kr_msg; evidence in var/logs/perf_gate/$today/"
    if [ -n "${PERF_NOTIFY:-}" ]; then "$PERF_NOTIFY" "$msg" || true
    else osascript -e "display notification \"${msg//[\"\\]/}\" with title \"algotrade perf gate\"" || true; fi
    exit 4
  fi
  busy "machine paused $paused_s s during the copy (copy stopped, retry $aborts of $((max_pause_aborts - 1)))"
fi
if [ -n "$writer_mid" ]; then
  snapshot_s=$(( $(date +%s) - t_ready )); wait_s=$((t_ready - t_start))
  write_progress writer-during-copy
  discard_clone; busy "a writer started during the copy (copy stopped): $writer_mid"
fi
if [ "$cap_hit" = 1 ]; then
  t_now=$(date +%s); snapshot_s=$((t_now - t_ready)); wait_s=$((t_ready - t_start))
  write_progress over-time
  stop_prekill; kill_report copy "$snapshot_limit" "snapshot cap"
  discard_clone
  total_s=$(( $(date +%s) - t_start ))
  sha=$(git -C "$repo" rev-parse --short=9 HEAD 2>/dev/null || echo unknown)
  say "snapshot over-time: the copy was killed at ${snapshot_limit}s"
  echo "date=$today sha=$sha views_over=? seconds_above=? exit=4 finished=yes outcome=snapshot-over-time over_time=yes wait_s=$wait_s snapshot_s=$snapshot_s bench_s=0 cleanup_s=0 total_s=$total_s" >>"$status"
  code=4; bench_s=0; cleanup_s=0; finish_evidence snapshot-over-time
  msg="1 s page gate: the snapshot copy was killed at ${snapshot_limit}s (no result)$kr_msg; evidence in var/logs/perf_gate/$today/"
  if [ -n "${PERF_NOTIFY:-}" ]; then "$PERF_NOTIFY" "$msg" || true
  else osascript -e "display notification \"${msg//[\"\\]/}\" with title \"algotrade perf gate\"" || true; fi
  exit 4
fi
stop_prekill
if [ "$copy_code" -ne 0 ]; then discard_clone; busy "the copy failed"; fi
t_copied=$(date +%s)
snapshot_s=$((t_copied - t_ready)); wait_s=$((t_ready - t_start))
ingest_during=false
# the bench never starts beside a deploy (it changes the code the bench runs); the wait is not copy time
if ! wait_deploy_done; then
  write_progress deploy-running-after-copy; discard_clone
  busy "a deploy is still running after ${PERF_DEPLOY_WAIT_S:-600}s (the clone is discarded): $(deploy_running)"
fi
if w=$(busy_writer) && [ -n "$w" ]; then ingest_during=true; fi
files="skipped: counting every file is slower than the copy's value (PERF_COUNT_FILES=1 counts)"
[ "${PERF_COUNT_FILES:-0}" = 1 ] && files=$(find "$clone" -type f | wc -l | tr -d ' ')
printf '{"copy_s": %s, "file_count": "%s", "entry_s": %s, "free_gb_before": %s, "free_gb_after": %s, "ingest_started_during_copy": %s}\n' \
  "$snapshot_s" "$files" "$(timings_json)" "${free_before:-null}" "$(free_now)" "$ingest_during" >"$rundir/snapshot.json"
if [ "$ingest_during" = true ]; then discard_clone; busy "a writer started during the copy: $w"; fi

sha=$(git -C "$repo" rev-parse --short=9 HEAD 2>/dev/null || echo unknown)
out=$(mktemp)
py=${PERF_PY:-$repo/.venv/bin/python}
cmd=${PERF_BENCH_CMD:-"$py $repo/scripts/perf/fast_bench.py --data-url file://$clone --record --machine nightly-clone --timings wait_s=$wait_s,snapshot_s=$snapshot_s --out $rundir --history-file $logs/perf_gate/history.jsonl"}

rm -f "$rundir/sample-window-bench.json"
set_phase bench; start_prekill bench "${PERF_BENCH_PREKILL_AFTER_S:-$(( bench_limit > 9 ? bench_limit - 8 : 1 ))}"
head_before=$(git -C "${PERF_TREE:-$repo}" rev-parse HEAD 2>/dev/null || echo unknown)
t_bench=$(date +%s)
hist=$logs/perf_gate/history.jsonl; hist_size=$({ wc -c <"$hist"; } 2>/dev/null | tr -d ' '); hist_size=${hist_size:-0}
# shellcheck disable=SC2086
watchdog "$bench_limit" $cmd >"$out" 2>&1 &
wd_pid=$!
wait "$wd_pid"
code=$?
wd_pid=
stop_prekill
t_benched=$(date +%s)
set_phase cleanup
head -200 "$out" >"$rundir/bench-head.txt"
bench_s=$((t_benched - t_bench))
top_procs >"$rundir/procs-end.txt"
over=$(sed -n 's/^\([0-9]*\) views over.*(\([0-9.]*\) s above the bar).*/\1 \2/p' "$out" | tail -1)
views_over=${over%% *}; above=${over##* }
# every outcome after the copy is a finished day (no endless re-copy of the store at every retry)
finished=yes; overtime=no; outcome=ok
if [ "$code" -eq 124 ]; then overtime=yes; code=4; outcome=over-time
elif [ "$code" -eq 2 ]; then outcome=refused
elif [ "$code" -eq 1 ] && grep -q '^INTEGRITY ' "$out"; then outcome=integrity
elif [ "$code" -eq 1 ] && [ -n "${over:-}" ]; then outcome=over-the-bar
elif [ "$code" -ne 0 ]; then outcome=crashed; code=1
fi
# a sleep or stall DURING the bench (the sampler's late_s over 60 s, from the bench's start) makes its
# times worthless: the run is `paused` (noisy), not recorded in the history, and the notice says so
paused_bench=$(awk -F, -v t="$t_bench" 'NR > 1 && $1 >= t - 10 && $4 + 0 > 60 {n++} END {print n + 0}' "$rundir/load.csv" 2>/dev/null)
if [ "${paused_bench:-0}" -gt 0 ] && [ "$outcome" != crashed ] && [ "$outcome" != refused ] \
   && [ "$outcome" != integrity ]; then  # an integrity failure stays one: not a no-verdict pause
  outcome=paused
  [ -f "$hist" ] && [ "$(wc -c <"$hist" | tr -d ' ')" -gt "$hist_size" ] && { head -c "$hist_size" "$hist" >"$hist.tmp" && mv "$hist.tmp" "$hist"; }
  say "the machine paused or stalled during the bench ($paused_bench late samples): not recorded"
fi
# a pre-kill `sample` suspended the bench or its API for 3 s (armed 8 s before the cap, so only a bench about to
# be killed gets one; an over-time run keeps its over-time cause):
# its times are worthless; the window is in sample-window-bench.json, the run is not recorded
if [ -f "$rundir/sample-window-bench.json" ] && [ "$outcome" != crashed ] && [ "$outcome" != refused ] \
   && [ "$outcome" != integrity ] && [ "$outcome" != paused ] && [ "$outcome" != over-time ]; then
  outcome=sampled
  [ -f "$hist" ] && [ "$(wc -c <"$hist" | tr -d ' ')" -gt "$hist_size" ] && { head -c "$hist_size" "$hist" >"$hist.tmp" && mv "$hist.tmp" "$hist"; }
  say "a pre-kill stack sample paused the bench ($(cat "$rundir/sample-window-bench.json")): not recorded"
fi
# the release tree's HEAD moved during the bench (a deploy checked out other code): not recorded
head_after=$(git -C "${PERF_TREE:-$repo}" rev-parse HEAD 2>/dev/null || echo unknown)
if [ "$head_after" != "$head_before" ] && [ "$outcome" != crashed ] && [ "$outcome" != refused ] \
   && [ "$outcome" != integrity ] && [ "$outcome" != paused ] && [ "$outcome" != sampled ]; then
  outcome=code-changed
  [ -f "$hist" ] && [ "$(wc -c <"$hist" | tr -d ' ')" -gt "$hist_size" ] && { head -c "$hist_size" "$hist" >"$hist.tmp" && mv "$hist.tmp" "$hist"; }
  say "code changed during the bench (${head_before:0:9} -> ${head_after:0:9}): not recorded"
fi
[ "$outcome" = over-time ] && [ -f "$rundir/sample-window-bench.json" ] && say "a pre-kill stack sample was taken in the last seconds of the bench (sample-window-bench.json)"
case "$outcome" in over-time|paused|code-changed|crashed|sampled)
  kill_report bench "$bench_limit" "$outcome" ;;
esac
cat "$out" >>"$rundir/run.log"
out_copy=$rundir/run.log
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

rename_clone  # instant; the delete starts after the notification
t_end=$(date +%s)
cleanup_s=$((t_end - t_benched)); total_s=$((t_end - t_start))
echo "date=$today sha=$sha views_over=${views_over:-?} seconds_above=${above:-?} exit=$code finished=$finished outcome=$outcome over_time=$overtime wait_s=$wait_s snapshot_s=$snapshot_s bench_s=$bench_s cleanup_s=$cleanup_s total_s=$total_s" >>"$status"
reason=""; [ "$overtime" = yes ] && reason=over-time
[ "$outcome" = integrity ] && reason=integrity
[ "$outcome" = refused ] && reason=refused; [ "$outcome" = crashed ] && reason=crashed
[ "$outcome" = paused ] && reason=paused; [ "$outcome" = code-changed ] && reason=code-changed; [ "$outcome" = sampled ] && reason=sampled
finish_evidence "$reason"

if [ "$code" -ne 0 ] || [ "$outcome" = paused ] || [ "$outcome" = code-changed ] || [ "$outcome" = sampled ] || [ "$bench_s" -gt "$bench_limit" ] || [ "$total_s" -gt "$total_limit" ] || [ "$overtime" = yes ]; then
  msg="1 s page gate: ${views_over:-?} views over the bar (${above:-?} s above); snapshot ${snapshot_s}s, bench ${bench_s}s, total ${total_s}s; evidence in var/logs/perf_gate/$today/"
  if [ "$outcome" = integrity ]; then
    why=$(grep '^INTEGRITY ' "$out_copy" | cut -c11-160 | head -3 | tr '\n' ';')
    msg="1 s page gate INTEGRITY FAILURE (not a timing result): $why evidence in var/logs/perf_gate/$today/"
  fi
  [ "$outcome" = sampled ] && msg="1 s page gate: a pre-kill stack sample paused the bench (NOT recorded, no verdict): $msg"
  [ "$outcome" = code-changed ] && msg="1 s page gate: the code changed during the bench (a deploy; NOT recorded, no verdict): $msg"
  [ "$outcome" = paused ] && msg="1 s page gate: the machine paused or stalled during the bench (noisy, NOT recorded, no verdict): $msg"
  [ -n "$kr_msg" ] && msg="$msg$kr_msg"
  [ "$outcome" = crashed ] && msg="1 s page gate CRASHED (no result): $msg"
  [ "$outcome" = refused ] && msg="1 s page gate REFUSED by the bench (no result): $msg"
  [ "$overtime" = yes ] && msg="1 s page gate OVER-TIME: bench killed at ${bench_limit}s (not recorded); $msg"
  if [ -n "${PERF_NOTIFY:-}" ]; then "$PERF_NOTIFY" "$msg" || true
  else osascript -e "display notification \"${msg//[\"\\]/}\" with title \"algotrade perf gate\"" || true; fi
fi
[ -n "$trash_dir" ] && delete_trash "$trash_dir"
exit "$code"
