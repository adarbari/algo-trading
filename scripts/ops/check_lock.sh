#!/usr/bin/env bash
# Run a command under a per-worktree lock: `make check` is `scripts/ops/check_lock.sh $(MAKE)
# check-gates`. Two full checks at once on this machine time out each other (30-40 min each),
# so a second run in the same worktree refuses and names the first run's PID and start time.
#
# Portable (macOS has no flock): the lock is a directory, `var/check.lock.d` (override with
# CHECK_LOCK_DIR), made with `mkdir` (atomic) and holding `pid` and `started`. A lock whose PID
# is dead is stale and is taken over. The trap releases it when the command ends or is stopped.
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
  rm -rf "$lock"  # stale: its process is gone
  take || { echo "refusing: lost the race for $lock to another run" >&2; exit 1; }
fi
trap 'rm -rf "$lock"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

"$@"
