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
#     `cp -cR` of tables/ runs/ serving/ only (APFS clonefile at low I/O priority; PERF_COPY_CMD
#     overrides, for tests; raw/ and staging/ are not copied; the copy is killed at 10 min), and re-checks that no ingest started during the copy (if one
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
# PERF_TOTAL_LIMIT_S, PERF_COPY_CMD, PERF_PORT_BASE, PERF_SNAPSHOT_LIMIT_S, PERF_LOWPRI.
set -uo pipefail

repo=$(cd "$(dirname "$0")/../.." && pwd)
src=${PERF_SRC:-$repo/var/data}
clone=${PERF_CLONE_ROOT-/Users/adarbari/perf-clone/data}  # set but empty is an error, not a default
status=${PERF_STATUS:-$repo/var/logs/perf_gate.status}
today=${PERF_NOW_DATE:-$(date +%Y-%m-%d)}
hm=${PERF_NOW_HM:-$(date +%H%M)}
min_disk_gb=12
max_load=4
markers='algotrade-ingest|algotrade-backtest|var/logs/'
# a real writer: an ingest or backtest command (rollups, nightly and compaction run through them). Any
# other marker match is a driver script (var/logs/...): a writer only while it has a live child that is not `sleep`
real_writer='algotrade-ingest|algotrade-backtest|rollups|nightly|compaction'

# the bench starts an API on a spare port of ALGOTRADE_PORT_BASE + 8..19: a fixed block outside the
# worktrees' (10000-14990) and the live API's 8000, so the nightly never collides with either
export ALGOTRADE_PORT_BASE=${PERF_PORT_BASE:-15990}
t_start=$(date +%s)
bench_limit=${PERF_BENCH_LIMIT_S:-300}
total_limit=${PERF_TOTAL_LIMIT_S:-720}
snapshot_limit=${PERF_SNAPSHOT_LIMIT_S:-600}
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
# low I/O priority for the copy and the delete (the live site shares the disk); macOS has no ionice
if [ -z "${PERF_LOWPRI+x}" ]; then
  if command -v taskpolicy >/dev/null 2>&1; then PERF_LOWPRI="taskpolicy -b"; else PERF_LOWPRI="nice -n 19"; fi
fi
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
delete_trash() {  # detached, low priority, guarded; logs trash_delete_s when it finishes
  trash_ok "$1" || return 0
  (
    trap - EXIT TERM INT
    t0=$(date +%s)
    $PERF_LOWPRI rm -rf "$1"
    took=$(( $(date +%s) - t0 ))
    day=${1##*.trash.}; day=${day%%.*}  # the day of the run that made this trash, not today
    dayrun=$logs/perf_gate/$day
    [ -d "$dayrun" ] || exit 0
    echo "$took" >"$dayrun/trash_delete_s.txt"
    TOOK=$took RUNDIR=$dayrun python3 - <<'PY'
import json, os
from pathlib import Path
f = Path(os.environ["RUNDIR"]) / "status.json"
if f.is_file():
    d = json.loads(f.read_text())
    d["trash_delete_s"] = int(os.environ["TOOK"])
    f.write_text(json.dumps(d, indent=1) + "\n")
PY
  ) </dev/null >/dev/null 2>&1 &
  disown 2>/dev/null
  return 0
}
discard_clone() { rename_clone; [ -n "$trash_dir" ] && delete_trash "$trash_dir"; return 0; }

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
    set -- $cargs; cmd=${1##*/}
    [ "$cmd" = sleep ] || return 0
  done
  return 1
}
busy_writer() {
  local pid args
  ps_lines | grep -E "$markers" | grep -vE "grep|perf_gate_nightly|fast_bench" | {
    while read -r pid args; do
      if printf '%s' "$args" | grep -qE "$real_writer" || driver_busy "$pid"; then
        echo "$pid $args"; return 0
      fi
      [ "$rundir_made" = 1 ] && echo "perf_gate: ignored parked driver (no child but sleep): pid $pid $args" >>"$rundir/run.log"
    done
    return 0
  }
}
if w=$(busy_writer) && [ -n "$w" ]; then busy "a writer runs: $w"; fi

# a leftover clone or trash of an earlier run is deleted first, in the background (never blocking)
leftover=0
for t in "$clone".trash.*; do [ -e "$t" ] && { delete_trash "$t"; leftover=1; }; done
[ -d "$clone" ] && { discard_clone; leftover=1; }
free_gb=${PERF_FREE_GB:-$(free_now)}
if [ "${free_gb:-0}" -lt "$min_disk_gb" ]; then
  busy "${free_gb:-?} GB free, need $min_disk_gb$([ "$leftover" = 1 ] && echo ' (an earlier run'"'"'s trash is still being deleted)')"
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
free_before=$free_gb
clone_made=1
mkdir -p "$clone"
# the real nightly copies with cp -c (APFS clonefile: shared blocks); PERF_COPY_CMD replaces it
# where cp has no -c (the tests, Linux). One watchdog caps the whole copy.
SRC=$src CLONE=$clone ENTRIES=$copy_entries COPY="$PERF_LOWPRI ${PERF_COPY_CMD:-cp -cR}" \
  watchdog "$snapshot_limit" sh -c 'set -e; for e in $ENTRIES; do [ -e "$SRC/$e" ] || continue; $COPY "$SRC/$e" "$CLONE/$e"; done; mkdir -p "$CLONE/locks"' &
wd_pid=$!
wait "$wd_pid"
copy_code=$?
wd_pid=
if [ "$copy_code" -eq 124 ]; then
  discard_clone
  t_now=$(date +%s); snapshot_s=$((t_now - t_ready)); wait_s=$((t_ready - t_start)); total_s=$((t_now - t_start))
  sha=$(git -C "$repo" rev-parse --short=9 HEAD 2>/dev/null || echo unknown)
  say "snapshot over-time: the copy was killed at ${snapshot_limit}s"
  echo "date=$today sha=$sha views_over=? seconds_above=? exit=4 finished=yes outcome=snapshot-over-time over_time=yes wait_s=$wait_s snapshot_s=$snapshot_s bench_s=0 cleanup_s=0 total_s=$total_s" >>"$status"
  code=4; bench_s=0; cleanup_s=0; finish_evidence snapshot-over-time
  msg="1 s page gate: the snapshot copy was killed at ${snapshot_limit}s (no result); evidence in var/logs/perf_gate/$today/"
  if [ -n "${PERF_NOTIFY:-}" ]; then "$PERF_NOTIFY" "$msg" || true
  else osascript -e "display notification \"${msg//[\"\\]/}\" with title \"algotrade perf gate\"" || true; fi
  exit 4
fi
if [ "$copy_code" -ne 0 ]; then discard_clone; busy "the copy failed"; fi
t_copied=$(date +%s)
snapshot_s=$((t_copied - t_ready)); wait_s=$((t_ready - t_start))
ingest_during=false
if w=$(busy_writer) && [ -n "$w" ]; then ingest_during=true; fi
files="skipped: counting every file is slower than the copy's value (PERF_COUNT_FILES=1 counts)"
[ "${PERF_COUNT_FILES:-0}" = 1 ] && files=$(find "$clone" -type f | wc -l | tr -d ' ')
printf '{"copy_s": %s, "file_count": "%s", "free_gb_before": %s, "free_gb_after": %s, "ingest_started_during_copy": %s}\n' \
  "$snapshot_s" "$files" "${free_before:-null}" "$(free_now)" "$ingest_during" >"$rundir/snapshot.json"
if [ "$ingest_during" = true ]; then discard_clone; busy "a writer started during the copy: $w"; fi

sha=$(git -C "$repo" rev-parse --short=9 HEAD 2>/dev/null || echo unknown)
out=$(mktemp)
py=${PERF_PY:-$repo/.venv/bin/python}
cmd=${PERF_BENCH_CMD:-"$py $repo/scripts/perf/fast_bench.py --data-url file://$clone --record --machine nightly-clone --timings wait_s=$wait_s,snapshot_s=$snapshot_s --out $rundir --history-file $logs/perf_gate/history.jsonl"}

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
elif [ "$code" -eq 1 ] && grep -q '^INTEGRITY ' "$out"; then outcome=integrity
elif [ "$code" -eq 1 ] && [ -n "${over:-}" ]; then outcome=over-the-bar
elif [ "$code" -ne 0 ]; then outcome=crashed; code=1
fi
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
finish_evidence "$reason"

if [ "$code" -ne 0 ] || [ "$bench_s" -gt "$bench_limit" ] || [ "$total_s" -gt "$total_limit" ] || [ "$overtime" = yes ]; then
  msg="1 s page gate: ${views_over:-?} views over the bar (${above:-?} s above); bench ${bench_s}s, total ${total_s}s; evidence in var/logs/perf_gate/$today/"
  if [ "$outcome" = integrity ]; then
    why=$(grep '^INTEGRITY ' "$out_copy" | cut -c11-160 | head -3 | tr '\n' ';')
    msg="1 s page gate INTEGRITY FAILURE (not a timing result): $why evidence in var/logs/perf_gate/$today/"
  fi
  [ "$outcome" = crashed ] && msg="1 s page gate CRASHED (no result): $msg"
  [ "$outcome" = refused ] && msg="1 s page gate REFUSED by the bench (no result): $msg"
  [ "$overtime" = yes ] && msg="1 s page gate OVER-TIME: bench killed at ${bench_limit}s (not recorded); $msg"
  if [ -n "${PERF_NOTIFY:-}" ]; then "$PERF_NOTIFY" "$msg" || true
  else osascript -e "display notification \"${msg//[\"\\]/}\" with title \"algotrade perf gate\"" || true; fi
fi
[ -n "$trash_dir" ] && delete_trash "$trash_dir"
exit "$code"
