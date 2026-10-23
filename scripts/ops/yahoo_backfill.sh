#!/usr/bin/env bash
# Loop `algotrade-ingest run analyst-backfill` until no name is due (ADR 0080 amendment
# 2026-10-23b): one batch of [yahoo] backfill_batch names a run, the ingest lock released between
# batches so the launchd nightly is never starved, ~60 s between batches. The OWNER starts it
# (README "Long runs"), detached:
#
#   nohup scripts/ops/yahoo_backfill.sh >/dev/null 2>&1 &
#   cat var/logs/yahoo-backfill.status      # state, batches, names still due; tail the .log too
#
# Stops when due_remaining is 0 ("done"), after three batches in a row that answered nothing
# ("stalled": Yahoo is down or the crumb dance fails; look at the log), after three 429s in a row
# ("blocked": Yahoo is throttling us; try again tomorrow) or when the batch fails to run at all
# ("error"). Waits, then retries, when the ingest lock is held (exit 3: the nightly is running),
# when the nightly of the last session is not complete yet (the task asks nothing) and after a 429
# (the batch stopped at once): 60 s, then 5 minutes, then 30 minutes, reset by a batch without one.
# Env: YAHOO_BACKFILL_LOGS (var/logs), YAHOO_BACKFILL_PAUSE (10 s between batches),
# YAHOO_BACKFILL_LOCKED (300 s), YAHOO_BACKFILL_WAIT (900 s: the nightly is incomplete),
# YAHOO_BACKFILL_COOLDOWNS ("60 300 1800": seconds after the first, second, third 429).
set -uo pipefail

cd "$(dirname "$0")/../.." || exit 2
logs=${YAHOO_BACKFILL_LOGS:-var/logs}
mkdir -p "$logs"
log=$logs/yahoo-backfill.log
status=$logs/yahoo-backfill.status
pause=${YAHOO_BACKFILL_PAUSE:-10}
locked=${YAHOO_BACKFILL_LOCKED:-300}
incomplete=${YAHOO_BACKFILL_WAIT:-900}
read -ra cooldowns <<<"${YAHOO_BACKFILL_COOLDOWNS:-60 300 1800}"
ingest=${YAHOO_BACKFILL_CMD:-.venv/bin/algotrade-ingest}

background=()  # like the launchd nightly: background CPU and IO priority, the website stays fast
command -v taskpolicy >/dev/null && background=(taskpolicy -b nice -n 10)
batches=0 stalled=0 limited=0 due=unknown
note() { echo "state=$1 batches=$batches due=$due $(date -u +%FT%TZ)" >"$status"; }
number() { sed -n "s/.*\"$1\": \([0-9][0-9]*\).*/\1/p" <<<"$out" | tail -1; }

while true; do
  note running
  out=$("${background[@]}" "$ingest" run analyst-backfill 2>>"$log")
  code=$?
  echo "$out" >>"$log"
  if [ "$code" -eq 3 ]; then
    note "locked (the nightly or another run holds the ingest lock)"
    sleep "$locked"
    continue
  fi
  if [ "$code" -gt 1 ]; then
    note "error exit=$code"
    exit "$code"
  fi
  if grep -q '"waiting"' <<<"$out"; then
    note "waiting (the nightly of the last session is not complete)"
    sleep "$incomplete"
    continue
  fi
  batches=$((batches + 1))
  due=$(number due_remaining)
  progress=$(number progress)
  [ -n "$due" ] || { note "error (no due_remaining in the output)"; exit 1; }
  if [ "${due}" -eq 0 ]; then
    note done
    exit 0
  fi
  if [ "${progress:-0}" -eq 0 ]; then stalled=$((stalled + 1)); else stalled=0; fi
  if [ "$stalled" -ge 3 ]; then
    note stalled
    exit 1
  fi
  if grep -q '"rate_limited": true' <<<"$out"; then
    limited=$((limited + 1))
    if [ "$limited" -ge "${#cooldowns[@]}" ]; then
      note blocked
      exit 1
    fi
    note "cooling down after a 429 (${cooldowns[$((limited - 1))]} s)"
    sleep "${cooldowns[$((limited - 1))]}"
  else
    limited=0
    sleep "$pause"
  fi
done
