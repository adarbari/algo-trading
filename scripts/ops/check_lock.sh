#!/usr/bin/env bash
# Run a command under a per-worktree lock: `make check` is `scripts/ops/check_lock.sh $(MAKE)
# check-gates`. Two full checks at once on this machine time out each other (30-40 min each),
# so a second run in the same worktree refuses and names the first run's PID and start time.
#
# Portable (macOS has no flock): the lock is a directory, `var/check.lock.d` (override with
# CHECK_LOCK_DIR), made with `mkdir` (atomic) and holding `pid` and `started`. A lock whose PID
# is dead is stale and is taken over (under a guard directory, `$lock.takeover`, so two runs
# never both take over). The trap releases it when the command ends or is stopped.
set -uo pipefail

[ "$#" -ge 1 ] || { echo "usage: check_lock.sh <command> [args...]" >&2; exit 2; }
lock=${CHECK_LOCK_DIR:-var/check.lock.d}
mkdir -p "$(dirname "$lock")"

take() {
  mkdir "$lock" 2>/dev/null || return 1
  echo $$ >"$lock/pid"
  date '+%Y-%m-%d %H:%M:%S' >"$lock/started"
}

holder_alive() {
  local pid
  pid=$(cat "$lock/pid" 2>/dev/null || true)
  if [ -z "$pid" ]; then sleep 1; pid=$(cat "$lock/pid" 2>/dev/null || true); fi  # being written
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

if ! take; then
  if holder_alive; then
    echo "refusing: another \`make check\` is running here (PID $(cat "$lock/pid"), started" \
      "$(cat "$lock/started" 2>/dev/null || echo unknown)). Wait for it; stop it by its PID," \
      "never with pkill. Lock: $lock" >&2
    exit 1
  fi
  # Stale: its process is gone. Only one run may take over at a time: a guard directory
  # (itself stale when its PID is dead). Inside it the holder is checked again, so a lock that
  # a faster run took meanwhile is never moved aside; then the old lock moves aside atomically.
  guard="$lock.takeover"
  # The guard is never removed by another run: two runs clearing a "dead" guard at once would
  # both get inside it, and a takeover killed before its PID is written would otherwise block
  # for good. A leftover guard can only come from a crashed takeover; the operator removes it.
  if ! mkdir "$guard" 2>/dev/null; then
    gpid=$(cat "$guard/pid" 2>/dev/null || true)
    if [ -n "$gpid" ] && kill -0 "$gpid" 2>/dev/null; then
      echo "refusing: another run (PID $gpid) is taking over $lock; retry in a moment" >&2
    else
      echo "refusing: a crashed takeover left $guard behind; check nothing runs, then: rm -rf $guard" >&2
    fi
    exit 1
  fi
  trap 'rm -rf "$guard"' EXIT
  echo $$ >"$guard/pid"
  if [ -d "$lock" ] && holder_alive; then
    echo "refusing: another \`make check\` took $lock first (PID $(cat "$lock/pid"))" >&2; exit 1
  fi
  if mv "$lock" "$lock.stale.$$" 2>/dev/null; then rm -rf "$lock.stale.$$"; fi
  take || { echo "refusing: lost the race for $lock to another run" >&2; exit 1; }
  rm -rf "$guard"
fi
[ "$(cat "$lock/pid" 2>/dev/null)" = "$$" ] || { echo "refusing: lost $lock" >&2; exit 1; }
trap 'rm -rf "$lock"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

"$@"
