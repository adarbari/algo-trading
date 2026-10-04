#!/usr/bin/env bash
# Create or remove a git worktree for one work item, ready to run the repo's tooling.
#
#   scripts/worktree.sh [--dry-run] <branch> [base]    new worktree off origin/<base|main>
#   scripts/worktree.sh [--dry-run] --remove <branch>  remove it (refuses if dirty / unpushed)
#
# The worktree is ../algo-trading-<branch-slug> (slash -> dash) next to the main checkout.
# Create: symlinks .venv to the main checkout's (so pre-commit hooks work; never --no-verify
# or SKIP=), writes worktree.env (git-ignored) with the absolute PYTHONPATH of THIS worktree
# (so layout / import-linter resolve it, not main), and runs `npm ci` in apps/web (only links
# node_modules when the lockfiles are identical). Then: `source <worktree>/worktree.env`.
set -euo pipefail

dry=0 remove=0 args=()
for a in "$@"; do
  case "$a" in
    --dry-run) dry=1 ;;
    --remove) remove=1 ;;
    -h | --help) sed -n '2,11p' "$0"; exit 0 ;;
    *) args+=("$a") ;;
  esac
done
if [ "${#args[@]}" -lt 1 ] || [ "${#args[@]}" -gt 2 ]; then
  echo "usage: scripts/worktree.sh [--dry-run] [--remove] <branch> [base]" >&2
  exit 2
fi
branch=${args[0]}
base=${args[1]:-main}

main=$(cd "$(git rev-parse --git-common-dir)/.." && pwd)
slug=${branch//\//-}
wt="$(dirname "$main")/algo-trading-$slug"

run() {
  if [ "$dry" = 1 ]; then echo "[dry-run] $*"; else "$@"; fi
}

if [ "$remove" = 1 ]; then
  [ -d "$wt" ] || { echo "no worktree at $wt" >&2; exit 1; }
  if [ -n "$(git -C "$wt" status --porcelain --ignore-submodules)" ]; then
    echo "refusing: $wt has uncommitted changes" >&2; exit 1
  fi
  if git -C "$wt" rev-parse --verify -q "origin/$branch" >/dev/null; then
    ahead=$(git -C "$wt" rev-list --count "origin/$branch..HEAD")
  else
    ahead=$(git -C "$wt" rev-list --count "origin/$base..HEAD" 2>/dev/null || echo 1)
  fi
  if [ "$ahead" != 0 ]; then
    echo "refusing: $wt has $ahead unpushed commit(s)" >&2; exit 1
  fi
  [ -L "$wt/.venv" ] && run rm "$wt/.venv"
  [ -L "$wt/apps/web/node_modules" ] && run rm "$wt/apps/web/node_modules"
  run rm -f "$wt/worktree.env"
  run git -C "$main" worktree remove "$wt"
  exit 0
fi

[ ! -e "$wt" ] || { echo "already exists: $wt" >&2; exit 1; }
run git -C "$main" fetch -q origin "$base"
run git -C "$main" worktree add -b "$branch" "$wt" "origin/$base"
run ln -s "$main/.venv" "$wt/.venv"

pp="$wt/src:$wt/libs/sources:$wt/apps/ingestion:$wt/apps/api:$wt/apps/backtest"
if [ "$dry" = 1 ]; then
  echo "[dry-run] write $wt/worktree.env: export PYTHONPATH=$pp"
else
  printf 'export PYTHONPATH=%s\n' "$pp" >"$wt/worktree.env"
fi

if [ "$dry" = 1 ] || ! cmp -s "$main/apps/web/package-lock.json" "$wt/apps/web/package-lock.json"; then
  run npm ci --prefix "$wt/apps/web"
elif [ -d "$main/apps/web/node_modules" ]; then
  run ln -s "$main/apps/web/node_modules" "$wt/apps/web/node_modules"
fi

echo "ready: source $wt/worktree.env && cd $wt"
