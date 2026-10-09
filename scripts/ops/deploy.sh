#!/usr/bin/env bash
# Update the running site from the main checkout (docs/hosting.md, ADR 0057).
#
#   scripts/ops/deploy.sh [--dry-run]   manual: pull main and do everything (sync, web, restart)
#   scripts/ops/deploy.sh --auto        the launchd agent com.algotrade.deploy (every 5 minutes):
#                                       deploy only what origin/main changed since the last deploy
#   scripts/ops/deploy.sh --clear       print why auto-deploy is blocked and let it run again
#
# Refuses unless the main checkout is on `main` with a clean tree and no commits origin/main
# lacks (--auto: it then writes var/deploy/blocked, notifies once and stops until --clear).
# The git-ignored overlay (config/site/*.local.toml, .env, var/) never counts as dirty.
# State is var/deploy/ (last_sha, blocked, the web build); the log is var/logs/deploy.log.
# Tests override: ALGOTRADE_DEPLOY_API / _INGEST (the algotrade-api / algotrade-ingest programs), ALGOTRADE_DEPLOY_NOTIFY
# (a command given the message), ALGOTRADE_DEPLOY_AGENTS (the launchd agents directory).
# bash has parsed every function below before the merge can rewrite this file under it.
set -euo pipefail

main() {
  local dry=0 mode=manual clear=0 apply=0
  local script
  script="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
  while [ $# -gt 0 ]; do
    case "$1" in
      --dry-run) dry=1 ;;
      --auto) mode=auto ;;
      --clear) clear=1 ;;
      --apply) apply=1; mode="$2"; shift ;;
      -h | --help) sed -n '2,15p' "$0"; return 0 ;;
      *) break ;;
    esac
    shift
  done
  if [ $# -gt 0 ] && [ "$apply" = 0 ]; then
    echo "usage: scripts/ops/deploy.sh [--dry-run | --auto | --clear]" >&2; return 2
  fi

  local root
  root=$(cd "$(git rev-parse --git-common-dir)/.." && pwd)
  cd "$root"
  local state=var/deploy log=var/logs/deploy.log
  local api="${ALGOTRADE_DEPLOY_API:-$root/.venv/bin/algotrade-api}"
  local ingest="${ALGOTRADE_DEPLOY_INGEST:-$root/.venv/bin/algotrade-ingest}"
  mkdir -p "$state" var/logs

  if [ "$clear" = 1 ]; then
    if [ -f "$state/blocked" ]; then
      cat "$state/blocked"; rm -f "$state/blocked" "$state/fetch_failures"; echo "cleared"
    else
      echo "not blocked"
    fi
    return 0
  fi

  if [ "$apply" = 1 ]; then apply_phase "$mode" "$@"; return $?; fi

  # ---- phase A: guards, fetch, plan (the old code, no lock) -------------------------------
  if [ "$mode" = auto ] && [ -f "$state/blocked" ]; then return 0; fi
  local pid
  if [ "$mode" = auto ] && [ -f "$state/applying" ]; then
    pid=$(cat "$state/applying")
    if kill -0 "$pid" 2> /dev/null; then  # a deploy is mid-merge: its dirty tree is not a fault
      say "skipped: deploy running (pid $pid)"; return 0
    fi
  fi
  local tool
  for tool in uv npm node curl git; do
    command -v "$tool" > /dev/null 2>&1 || { block "$tool not found on PATH"; return 1; }
  done
  local branch
  branch=$(git rev-parse --abbrev-ref HEAD)
  if [ "$branch" != main ]; then
    block "the main checkout $root is on '$branch', not main"; return 1
  fi
  if [ -n "$(git status --porcelain -uno --ignore-submodules)" ]; then
    echo "(a committed file edited here is not fine: move it to config/site/<name>.local.toml)" >&2
    git status --short >&2
    block "the main checkout $root has uncommitted changes"; return 1
  fi
  if ! git fetch -q origin main; then
    if [ "$mode" != auto ]; then echo "refusing: git fetch failed" >&2; return 1; fi
    local n=0
    if [ -f "$state/fetch_failures" ]; then n=$(cat "$state/fetch_failures"); fi
    n=$((n + 1)); echo "$n" > "$state/fetch_failures"
    if [ "$n" -ge 12 ]; then block "git fetch failed $n times in a row"; return 1; fi
    return 0
  fi
  rm -f "$state/fetch_failures"
  # Unpushed local commits on main must never deploy: main has to be an ancestor of origin/main.
  if ! git merge-base --is-ancestor main origin/main; then
    block "main has commits that are not on origin/main (unpushed or diverged)"; return 1
  fi
  local target last acts locks
  target=$(git rev-parse origin/main)
  if [ "$mode" = auto ]; then
    if [ ! -f "$state/last_sha" ] && [ "$dry" = 0 ]; then
      git rev-parse HEAD > "$state/last_sha"
      say "seeded last_sha from HEAD $(cat "$state/last_sha")"
    fi
    if [ -f "$state/last_sha" ]; then last=$(cat "$state/last_sha"); else last=$(git rev-parse HEAD); fi
    if ! git merge-base --is-ancestor "$last" "$target" 2> /dev/null; then
      block "the last deployed commit ${last:0:9} is not an ancestor of origin/main ${target:0:9}"
      return 1
    fi
    if [ "$target" = "$last" ]; then return 0; fi
    acts=$("$api" deploy-plan --since "$last" --to "$target") \
      || { block "deploy-plan failed"; return 1; }
    # the ingest lock only when a running ingest loads what changed (ADR 0057, 2026-10-09)
    locks=$("$api" deploy-plan --locks --since "$last" --to "$target") \
      || { block "deploy-plan failed"; return 1; }
  else
    acts="sync web restart"
    locks=ingest
  fi
  local deploy_only=""
  if [ -z "$locks" ]; then deploy_only=1; fi

  if [ "$dry" = 1 ]; then
    if [ -n "$deploy_only" ]; then echo "locks (dry-run): deploy"; else echo "locks (dry-run): deploy, ingest"; fi
    apply_phase "$mode" "$target" $acts
    return $?
  fi
  local rc=0
  "$ingest" deploy-hold ${deploy_only:+--deploy-only} -- bash "$script" --apply "$mode" "$target" $acts || rc=$?
  case "$rc" in
    0) ;;
    75)
      if [ -n "$deploy_only" ]; then
        say "skipped: deploy running (${target:0:9} waits)"
      else
        say "skipped: ingest/deploy running (${target:0:9} waits)"
      fi
      if [ "$mode" != auto ]; then return 1; fi
      ;;
    *)
      if [ "$mode" = auto ] && [ ! -f "$state/blocked" ]; then block "deploy-hold exited $rc"; fi
      return "$rc"
      ;;
  esac
  return 0
}

stamp() { date -u +%Y-%m-%dT%H:%M:%SZ; }

say() {  # one log line; --auto output is launchd's own file, so only the file there
  echo "$(stamp) $*" >> "$log"
  if [ "$mode" != auto ]; then echo "$*"; fi
}

notify() {
  local msg="${1//[\"\\]/}"
  if [ -n "${ALGOTRADE_DEPLOY_NOTIFY:-}" ]; then
    "$ALGOTRADE_DEPLOY_NOTIFY" "$msg" || true
  else
    osascript -e "display notification \"$msg\" with title \"algotrade deploy\"" || true
  fi
}

block() {  # auto: remember why, tell the owner once, stop; manual: just refuse
  echo "refusing: $1" >&2
  if [ "$mode" = auto ] && [ "$dry" = 0 ]; then
    printf '%s %s\n' "$(stamp)" "$1" > "$state/blocked"
    say "BLOCKED: $1"
    notify "auto-deploy blocked: $1 (scripts/ops/deploy.sh --clear)"
  fi
  return 0
}

run() {
  if [ "$dry" = 1 ]; then echo "[dry-run] $*"; else echo "+ $*"; "$@"; fi
}

# ---- phase B: under the deploy and ingest locks (algotrade-ingest deploy-hold) ---------------
apply_phase() {
  local mode=$1 target=$2
  shift 2
  local acts=" $* " before
  has() { case "$acts" in *" $1 "*) return 0 ;; esac; return 1; }
  before=$(git rev-parse HEAD)
  local verify=("$api" deploy-verify --expect "$target")
  if [ "$dry" = 0 ]; then
    echo "$$" > "$state/applying"
    trap "rm -f '$PWD/$state/applying'" EXIT  # expanded now: main's locals are gone by then
  fi

  run git merge --ff-only "$target" || { block "git merge --ff-only ${target:0:9} failed"; return 1; }
  if has sync; then
    run uv sync --all-packages --locked || { block "uv sync failed"; return 1; }  # main checkout only
  fi
  if has web; then
    # Built beside the live one; a changed package-lock.json is newer than node_modules, so make runs npm ci.
    if [ "$dry" = 0 ]; then rm -rf "$state/web.next"; fi
    run make web-build WEB_DIST="$state/web.next" || { block "the web build failed"; return 1; }
  fi
  if has restart; then
    run launchctl kickstart -k "gui/$(id -u)/com.algotrade.api" \
      || { block "the API restart failed"; return 1; }
    local check=full
    if has web; then check=api; fi  # the served web is still the old build until the swap
    run "${verify[@]}" --check "$check" || { block "the API did not come back at ${target:0:9}"; return 1; }
  fi
  if has web; then
    if [ "$dry" = 1 ]; then
      echo "[dry-run] swap $state/web.next into var/web (old assets/ kept for open tabs)"
    else
      # Hashed asset names: an open tab keeps loading the files of the build it has.
      carry_assets var/web "$state/web.next"
      rm -rf "$state/web.prev"
      if [ -d var/web ]; then mv var/web "$state/web.prev"; fi
      mv "$state/web.next" var/web
    fi
    run "${verify[@]}" --check web || { block "the served web is not at ${target:0:9} after the swap"; return 1; }
  fi
  if has plists; then plists_check "$before" "$target"; fi
  if [ "$dry" = 0 ]; then
    printf '%s\n' "$target" > "$state/last_sha.tmp"
    mv "$state/last_sha.tmp" "$state/last_sha"
    rm -f "$state/blocked"  # a manual deploy that worked is the owner clearing it
    say "deployed ${target:0:9} ($*)"
  fi
  return 0
}

# Only the previous build's own assets (the files its index.html references), not every
# generation: the one an open tab was loaded with keeps loading, and the folder cannot grow.
carry_assets() {
  local from=$1 to=$2 f
  [ -f "$from/index.html" ] || return 0
  mkdir -p "$to/assets"
  for f in $(grep -o 'assets/[^"'"'"' )?]*' "$from/index.html" | sort -u); do
    if [ -f "$from/$f" ] && [ ! -e "$to/$f" ]; then cp "$from/$f" "$to/$f"; fi
  done
}

# A launchd plist writer changed: regenerate into var/deploy/plists and say which installed
# agent differs. Never installs, never blocks (ADR 0044: the owner runs launchctl).
plists_check() {
  local before=$1 target=$2 agents="${ALGOTRADE_DEPLOY_AGENTS:-$HOME/Library/LaunchAgents}"
  local dir=$state/plists differs="" f
  if [ "$dry" = 1 ]; then
    echo "[dry-run] regenerate the launchd plists into $dir and compare"; return 0
  fi
  mkdir -p "$dir"
  "$api" schedule --agent api --out "$dir/com.algotrade.api.plist" > /dev/null || true
  "$api" schedule --agent deploy --out "$dir/com.algotrade.deploy.plist" > /dev/null || true
  for f in "$dir"/*.plist; do
    if [ -f "$f" ] && ! cmp -s "$f" "$agents/$(basename "$f")"; then
      differs="$differs $(basename "$f" .plist)"
    fi
  done
  if git diff --name-only "$before..$target" | grep -q 'apps/ingestion/algotrade_ingestion/ops/schedule.py'; then
    differs="$differs com.algotrade.nightly(algotrade-ingest schedule)"
  fi
  if [ -n "$differs" ]; then
    say "launchd plists differ from the installed agents:$differs"
    notify "reinstall the launchd agents:$differs (docs/hosting.md)"
  fi
}

main "$@"; exit $?
