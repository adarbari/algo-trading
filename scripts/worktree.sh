#!/usr/bin/env bash
# Create or remove a git worktree for one work item, ready to run the repo's tooling.
#
#   scripts/worktree.sh [--dry-run] <branch> [base]    new worktree off origin/<base|main>
#   scripts/worktree.sh [--dry-run] --remove <branch>  remove it (refuses if dirty / unpushed)
#   scripts/worktree.sh [--dry-run] --prune-merged     remove the worktrees of merged PRs
#
# --prune-merged covers ../algo-trading-*, ../algo-wt-* and <main>/.claude/worktrees/*. It
# removes a worktree only when it is clean, not locked, not the current one, its branch has no
# open PR and a merged PR (`gh`) whose last commit is the worktree's HEAD (or an ancestor of
# it), then deletes the local branch (`git branch -D`: a squash-merged branch is never an
# ancestor of main, which is why --remove refuses it). It prints "removed" / "kept <reason>"
# per worktree (dry-run: "would remove"), never touches the main checkout, and needs `gh`.
#
# The worktree is ../algo-trading-<branch-slug> (slash -> dash) next to the main checkout.
# Create: symlinks .venv to the main checkout's (so pre-commit hooks work; never --no-verify
# or SKIP=), writes worktree.env (git-ignored) with the absolute PYTHONPATH of THIS worktree
# (so layout / import-linter resolve it, not main), and runs its own `npm ci` in apps/web.
# Never `uv sync` / `make install` in it: through the link that rewrites main's venv (which
# the nightly and API run) to this worktree's code; `make install` refuses, `make doctor`
# flags it. Never symlink node_modules: `make check` runs `npm ci`, which through a link
# empties main's install (breaking its dev server and every linked worktree).
# worktree.env also sets ALGOTRADE_PORT_BASE = 10000 + cksum(<wt path>) % 500 * 10: this
# worktree's own block of ports, read by apps/web (vite.config.ts and the playwright configs):
# API +0, Vite dev +1, real-app api/web pairs +2..+5, Storybook preview +6, vite preview +7.
# Unset (CI, the main checkout) the web keeps its usual 8000 / 5173 / 4173 / 6007 / 88xx / 58xx.
# Then: `source <wt>/worktree.env`.
set -euo pipefail

dry=0 remove=0 prune=0 args=()
for a in "$@"; do
  case "$a" in
    --dry-run) dry=1 ;;
    --remove) remove=1 ;;
    --prune-merged) prune=1 ;;
    -h | --help) sed -n '2,25p' "$0"; exit 0 ;;
    *) args+=("$a") ;;
  esac
done
if [ "$prune" = 1 ]; then
  [ "${#args[@]}" = 0 ] && [ "$remove" = 0 ] || { echo "--prune-merged takes no branch" >&2; exit 2; }
elif [ "${#args[@]}" -lt 1 ] || [ "${#args[@]}" -gt 2 ]; then
  echo "usage: scripts/worktree.sh [--dry-run] [--remove] <branch> [base] | --prune-merged" >&2
  exit 2
fi
branch=${args[0]:-}
base=${args[1]:-main}

main=$(cd "$(git rev-parse --git-common-dir)/.." && pwd)
slug=${branch//\//-}
wt="$(dirname "$main")/algo-trading-$slug"

run() {
  if [ "$dry" = 1 ]; then echo "[dry-run] $*"; else "$@"; fi
}

# Why the worktree at $1 (branch $2, HEAD $3) must stay, or empty when its PR is merged.
keep_reason() {
  local path=$1 br=$2 head=$3 oid
  [ -n "$br" ] || { echo "detached HEAD"; return; }
  [ -n "$(git -C "$path" status --porcelain --ignore-submodules)" ] && { echo "uncommitted changes"; return; }
  grep -Fxq "$br" "$tmp/open" && { echo "open PR"; return; }
  awk -F'\t' -v b="$br" '$1 == b { f = 1 } END { exit !f }' "$tmp/merged" || { echo "no merged PR"; return; }
  while read -r b oid; do
    [ "$b" = "$br" ] || continue
    [ "$oid" = "$head" ] && return
    git cat-file -e "$oid^{commit}" 2>/dev/null && git merge-base --is-ancestor "$head" "$oid" && return
  done <"$tmp/merged"
  echo "commits after the merged PR"
}

prune_merged() {
  command -v gh >/dev/null || { echo "gh not on PATH" >&2; exit 1; }
  tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
  gh pr list --state merged --limit 2000 --json headRefName,headRefOid \
    --jq '.[] | [.headRefName, .headRefOid] | @tsv' >"$tmp/merged"
  gh pr list --state open --limit 500 --json headRefName --jq '.[].headRefName' >"$tmp/open"
  local mainp cur path br head why removed=0 kept=0
  mainp=$(cd "$main" && pwd -P)
  cur=$(git rev-parse --show-toplevel 2>/dev/null || true)
  git worktree list --porcelain >"$tmp/list"
  path="" br="" head="" locked=0
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
      "worktree "*) path=${line#worktree } br="" head="" locked=0 ;;
      "HEAD "*) head=${line#HEAD } ;;
      "branch "*) br=${line#branch refs/heads/} ;;
      locked*) locked=1 ;;
      "") ;;
    esac
    # a record ends at the blank line after it; handle it there
    [ -z "$line" ] || continue
    [ -n "$path" ] && [ "$path" != "$mainp" ] || { path=""; continue; }
    case "$path" in
      "$(dirname "$mainp")"/algo-trading-* | "$(dirname "$mainp")"/algo-wt-* | "$mainp"/.claude/worktrees/*) ;;
      *) path=""; continue ;;
    esac
    if [ "$path" = "$cur" ]; then why="the current worktree"
    elif [ "$locked" = 1 ]; then why="locked"
    else why=$(keep_reason "$path" "$br" "$head"); fi
    if [ -n "$why" ]; then
      echo "kept $path ($br): $why"; kept=$((kept + 1))
    else
      if [ "$dry" = 1 ]; then echo "would remove $path ($br)"; else
        [ -L "$path/.venv" ] && rm "$path/.venv"
        [ -L "$path/apps/web/node_modules" ] && rm "$path/apps/web/node_modules"
        rm -f "$path/worktree.env"
        if git -C "$mainp" worktree remove "$path" && git -C "$mainp" branch -D "$br" >/dev/null; then
          echo "removed $path ($br)"
        else
          echo "kept $path ($br): git refused to remove it"; kept=$((kept + 1)); continue
        fi
      fi
      removed=$((removed + 1))
    fi
    path=""
  done <"$tmp/list"
  echo "$([ "$dry" = 1 ] && echo "would remove" || echo removed) $removed worktree(s), kept $kept"
}

if [ "$prune" = 1 ]; then prune_merged; exit 0; fi

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
  # legacy: older worktrees linked node_modules to main's; drop the link, never main's install
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
port_base=$((10000 + $(printf %s "$wt" | cksum | cut -d' ' -f1) % 500 * 10))
if [ "$dry" = 1 ]; then
  echo "[dry-run] write $wt/worktree.env: export PYTHONPATH=$pp"
  echo "[dry-run] write $wt/worktree.env: export ALGOTRADE_PORT_BASE=$port_base"
else
  printf 'export PYTHONPATH=%s\nexport ALGOTRADE_PORT_BASE=%s\n' "$pp" "$port_base" >"$wt/worktree.env"
fi

run npm ci --prefix "$wt/apps/web"

echo "ready: source $wt/worktree.env && cd $wt"
