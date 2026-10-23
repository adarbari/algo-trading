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
#     notifies the owner (osascript, as deploy.sh) when a view is over the bar. The bench stops
#     itself within 5 minutes (--budget-s 270); with the snapshot the night's run is ~10 minutes.
#     A noisy or low-confidence bench run is not recorded (it is still a finished day).
#
# Exit codes: 0 done (clean) or nothing to do today; 1 finished with a view over the bar without
# a named exception, or an operation that failed; 2 refused (a path guard, or the bench refused);
# 3 busy, retry. Env (tests): PERF_CLONE_ROOT, PERF_SRC, PERF_STATUS, PERF_NOW_DATE, PERF_NOW_HM,
# PERF_PS_FILE, PERF_FREE_GB, PERF_LOAD, PERF_BENCH_CMD, PERF_NOTIFY.
set -uo pipefail

repo=$(cd "$(dirname "$0")/../.." && pwd)
src=${PERF_SRC:-$repo/var/data}
clone=${PERF_CLONE_ROOT:-/Users/adarbari/perf-clone/data}
status=${PERF_STATUS:-$repo/var/logs/perf_gate.status}
today=${PERF_NOW_DATE:-$(date +%Y-%m-%d)}
hm=${PERF_NOW_HM:-$(date +%H%M)}
min_disk_gb=12
max_load=4
markers='algotrade-ingest|var/logs/'

say() { echo "perf_gate: $*" >&2; }

if [ "$((10#$hm))" -lt 300 ]; then exit 0; fi  # before 03:00 local
if [ -f "$status" ] && grep -q "^date=$today .*finished=yes" "$status"; then exit 0; fi

# the clone is removed and rewritten: only the fixed clone path, never the real store
case "$clone" in */perf-clone/data) ;; *) say "refusing: $clone does not end in /perf-clone/data"; exit 2 ;; esac
real_src=$(cd "$src" 2>/dev/null && pwd -P || echo "$src")
real_clone=$(cd "$(dirname "$clone")" 2>/dev/null && pwd -P || dirname "$clone")/data
case "$real_clone/" in "$real_src"/*) say "refusing: the clone is the real store"; exit 2 ;; esac
case "$real_src/" in "$real_clone"/*) say "refusing: the real store is inside the clone"; exit 2 ;; esac
[ "$real_clone" != "$real_src" ] || { say "refusing: the clone is the real store"; exit 2; }
[ -d "$src" ] || { say "refusing: no store at $src"; exit 2; }

ps_lines() { if [ -n "${PERF_PS_FILE:-}" ]; then cat "$PERF_PS_FILE"; else ps -eo pid,args; fi; }
busy_writer() {
  ps_lines | grep -E "$markers" | grep -vE "grep|perf_gate_nightly|fast_bench" | head -1
}
if w=$(busy_writer) && [ -n "$w" ]; then say "busy, retry: a writer runs: $w"; exit 3; fi

free_gb=${PERF_FREE_GB:-$(df -k "$(dirname "$clone")" 2>/dev/null | awk 'NR==2 {printf "%d", $4/1048576}')}
if [ "${free_gb:-0}" -lt "$min_disk_gb" ]; then say "busy, retry: ${free_gb:-?} GB free, need $min_disk_gb"; exit 3; fi
load=${PERF_LOAD:-$(uptime | sed 's/.*load averages*: *//' | awk '{gsub(",", "", $1); print $1}')}
if awk "BEGIN {exit !($load > $max_load)}"; then say "busy, retry: load $load over $max_load"; exit 3; fi

drop_clone() { [ -d "$clone" ] && rm -rf "$clone"; return 0; }
case "$clone" in */perf-clone/data) ;; *) exit 2 ;; esac
drop_clone
mkdir -p "$(dirname "$clone")"
if ! cp -cR "$src" "$clone"; then drop_clone; say "busy, retry: the copy failed"; exit 3; fi
if w=$(busy_writer) && [ -n "$w" ]; then drop_clone; say "busy, retry: a writer started during the copy: $w"; exit 3; fi

sha=$(git -C "$repo" rev-parse --short=9 HEAD 2>/dev/null || echo unknown)
out=$(mktemp)
cmd=${PERF_BENCH_CMD:-"$repo/.venv/bin/python $repo/scripts/perf/fast_bench.py --data-url file://$clone --record --machine nightly-clone"}
$cmd >"$out" 2>&1
code=$?
over=$(sed -n 's/^\([0-9]*\) views over.*(\([0-9.]*\) s above the bar).*/\1 \2/p' "$out" | tail -1)
views_over=${over%% *}; above=${over##* }
finished=no; if [ "$code" -le 1 ]; then finished=yes; fi
mkdir -p "$(dirname "$status")"
echo "date=$today sha=$sha views_over=${views_over:-?} seconds_above=${above:-?} exit=$code finished=$finished" >>"$status"
cp "$out" "$(dirname "$status")/perf_gate.last.log"
rm -f "$out"
drop_clone

if [ "$code" -eq 1 ]; then
  msg="1 s page gate: ${views_over:-?} views over the bar (${above:-?} s above), see var/logs/perf_gate.last.log"
  if [ -n "${PERF_NOTIFY:-}" ]; then "$PERF_NOTIFY" "$msg" || true
  else osascript -e "display notification \"${msg//[\"\\]/}\" with title \"algotrade perf gate\"" || true; fi
fi
exit "$code"
