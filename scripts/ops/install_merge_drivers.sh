#!/usr/bin/env bash
# Register the repo's git merge drivers (declared in .gitattributes) in this clone's git config.
#
#   scripts/ops/install_merge_drivers.sh [--check]
#
# `git config merge.<name>.driver` is local config, so a fresh clone has none. The config is the
# clone's common one (.git/config), shared by the main checkout and every worktree, so one run
# covers them all. Run by scripts/worktree.sh and scripts/merge_main.sh; `make doctor` checks it
# (--check: exit 1 when a driver is missing or differs). Drivers: scripts/ops/merge_budgets.py,
# and `keepours` (`true`: our side, no conflict) for generated files merge_main.sh regenerates.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

want_budgets='python3 scripts/ops/merge_budgets.py budgets %O %A %B %P'
want_views='python3 scripts/ops/merge_budgets.py views %O %A %B %P'
bad=0
set_driver() { # name command [description]
  [ "$(git config --get "merge.$1.driver" || true)" = "$2" ] && return 0
  if [ "${CHECK:-0}" = 1 ]; then bad=1; echo "merge driver '$1' not installed"; return 0; fi
  git config "merge.$1.name" "$1 (${3:-scripts/ops/merge_budgets.py})"
  git config "merge.$1.driver" "$2"
  echo "installed merge driver '$1'"
}
CHECK=0
[ "${1:-}" = "--check" ] && CHECK=1
set_driver perfbudgets "$want_budgets"
set_driver latencyviews "$want_views"
set_driver keepours true "generated file: ours, then scripts/merge_main.sh regenerates"
exit "$bad"
