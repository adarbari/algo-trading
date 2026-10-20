#!/usr/bin/env bash
# Update the running site from its release tree (docs/hosting.md, ADRs 0057 and 0079).
#
#   var/release/current/scripts/ops/deploy.sh [--dry-run]   manual (the entry point; the main checkout's copy lags): fetch main and do everything (sync, web, restart)
#   scripts/ops/deploy.sh --auto        the launchd agent com.algotrade.deploy (every 5 minutes):
#                                       deploy only what origin/main changed since the last deploy
#   scripts/ops/deploy.sh --clear       print why auto-deploy is blocked and let it run again
#   scripts/ops/deploy.sh --init-release [--slot NAME]
#                                       owner-run once: create the release tree (var/release/<slot>)
#                                       and print the launchd commands; installs nothing itself
#
# Two roots: the STATE root is the main checkout (var/deploy, deploy-hold, --clear; found through
# git's common dir, so it works from the main checkout and from any release tree), the TREE is
# var/release/<slot> (default slot `blue`; `var/release/current` links the active one). The tree
# is a detached worktree the deployer alone moves: serving never touches the main checkout or its
# venv, so a deploy takes only the `deploy` lock and never waits on an ingest (ADR 0079).
# main is fetched into the private ref refs/deploy/main (never refs/remotes/origin/main, which
# other sessions fetch too). The git-ignored overlay (var, .env, config/users,
# config/site/*.local.toml) is symlinked into the tree from the main checkout.
# State is var/deploy/ (last_sha, blocked); the web build is var/release/<slot>.web; the log is
# var/logs/deploy.log.
# Tests override: ALGOTRADE_DEPLOY_API / _INGEST (the algotrade-api / algotrade-ingest programs), ALGOTRADE_DEPLOY_NOTIFY
# (a command given the message), ALGOTRADE_DEPLOY_AGENTS (the launchd agents directory),
# ALGOTRADE_DEPLOY_FREE_KB (free disk space, kB), ALGOTRADE_DEPLOY_SLOT (the slot).
# bash has parsed every function below before a checkout can rewrite this file under it.
set -euo pipefail

PRIVATE_REF=refs/deploy/main
# The git-ignored env files Vite bakes into the web build (apps/web/.gitignore, the root .env);
# linked into the tree beside the other overlay files (a test keeps this list in step).
WEB_ENV_OVERLAY=".env .env.local .env.*.local"
MIN_FREE_KB=5242880  # 5 GB: the floor of the free-space check (else 3x the tree)

main() {
  local dry=0 mode=manual clear=0 apply=0 iapply=0 init=0 slot="${ALGOTRADE_DEPLOY_SLOT:-}"
  local script
  script="$(cd "$(dirname "$0")" && pwd -P)/$(basename "$0")"  # physical: a flip of `current` never moves it
  while [ $# -gt 0 ]; do
    case "$1" in
      --dry-run) dry=1 ;;
      --auto) mode=auto ;;
      --clear) clear=1 ;;
      --init-release) init=1 ;;
      --slot) slot="$2"; shift ;;
      --apply) apply=1; mode="$2"; shift ;;
      --ingest-apply) iapply=1; mode="$2"; shift ;;
      -h | --help) sed -n '2,22p' "$0"; return 0 ;;
      *) break ;;
    esac
    shift
  done
  if [ $# -gt 0 ] && [ "$apply" = 0 ] && [ "$iapply" = 0 ]; then
    echo "usage: var/release/current/scripts/ops/deploy.sh [--dry-run | --auto | --clear | --init-release] [--slot NAME]" >&2
    return 2
  fi

  local root
  root=$(cd "$(git rev-parse --git-common-dir)/.." && pwd)
  cd "$root"
  if [ -z "$slot" ]; then  # the active slot, else the first one
    if [ -L var/release/current ]; then slot=$(basename "$(readlink var/release/current)"); else slot=blue; fi
  fi
  local state=var/deploy log=var/logs/deploy.log
  local tree="$root/var/release/$slot" webdir="$root/var/release/$slot.web"
  local api="${ALGOTRADE_DEPLOY_API:-$tree/.venv/bin/algotrade-api}"
  # deploy-hold runs from the tree's venv: the ingest sync below may `uv sync` the main venv
  local ingest="${ALGOTRADE_DEPLOY_INGEST:-$tree/.venv/bin/algotrade-ingest}"
  mkdir -p "$state" var/logs

  if [ "$clear" = 1 ]; then
    if [ -f "$state/blocked" ]; then
      cat "$state/blocked"; rm -f "$state/blocked" "$state/fetch_failures"; echo "cleared"
    else
      echo "not blocked"
    fi
    return 0
  fi

  if [ "$init" = 1 ]; then init_release "$script" "$slot"; return $?; fi
  if [ "$apply" = 1 ]; then apply_phase "$mode" "$@"; return $?; fi
  if [ "$iapply" = 1 ]; then ingest_apply "$1"; return $?; fi

  # ---- phase A: guards, fetch, plan (no lock) ----------------------------------------------
  if [ "$mode" = auto ] && [ -f "$state/blocked" ]; then
    # a serving block must not stall the ingest checkout, but it only moves to the last commit
    # served successfully (last_sha): never to the target whose deploy just failed
    if [ -f "$state/last_sha" ]; then ingest_sync "$script" "$slot" "$(cat "$state/last_sha")"; fi
    return 0
  fi
  need_tools || return 1
  if [ ! -e "$tree/.git" ]; then
    block "no release tree at $tree (the owner runs scripts/ops/deploy.sh --init-release once)"
    return 1
  fi
  if ! fetch_private; then
    if [ "$mode" != auto ]; then echo "refusing: git fetch failed" >&2; return 1; fi
    local n=0
    if [ -f "$state/fetch_failures" ]; then n=$(cat "$state/fetch_failures"); fi
    n=$((n + 1)); echo "$n" > "$state/fetch_failures"
    if [ "$n" -ge 12 ]; then block "git fetch failed $n times in a row"; return 1; fi
    return 0
  fi
  rm -f "$state/fetch_failures"
  local target last acts
  target=$(git rev-parse "$PRIVATE_REF")
  if [ "$mode" = auto ]; then
    if [ ! -f "$state/last_sha" ] && [ "$dry" = 0 ]; then
      git -C "$tree" rev-parse HEAD > "$state/last_sha"
      say "seeded last_sha from the release tree $(cat "$state/last_sha")"
    fi
    if [ -f "$state/last_sha" ]; then last=$(cat "$state/last_sha"); else last=$(git -C "$tree" rev-parse HEAD); fi
    if ! git merge-base --is-ancestor "$last" "$target" 2> /dev/null; then
      block "the last deployed commit ${last:0:9} is not an ancestor of origin/main ${target:0:9}"
      return 1
    fi
    if [ "$target" = "$last" ]; then ingest_sync "$script" "$slot" "$target"; return 0; fi
    acts=$("$api" deploy-plan --since "$last" --to "$target") \
      || { block "deploy-plan failed"; return 1; }
  else
    acts="sync web restart"
  fi

  # A serving deploy takes the deploy lock alone: nothing it touches is loaded by an ingest.
  if [ "$dry" = 1 ]; then
    echo "locks (dry-run): deploy"
    local drc=0
    apply_phase "$mode" "$target" $acts || drc=$?
    ingest_sync "$script" "$slot" "$target"
    return "$drc"
  fi
  local rc=0
  "$ingest" deploy-hold --deploy-only -- bash "$script" --slot "$slot" --apply "$mode" "$target" $acts || rc=$?
  case "$rc" in
    0) ;;
    75)
      say "skipped: deploy running (${target:0:9} waits)"
      if [ "$mode" != auto ]; then return 1; fi
      ;;
    *)
      if [ "$mode" = auto ] && [ ! -f "$state/blocked" ]; then block "deploy-hold exited $rc"; fi
      return "$rc"
      ;;
  esac
  if [ "$rc" = 0 ]; then ingest_sync "$script" "$slot" "$target"; fi
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

run_in() {  # run a command inside a directory
  local dir=$1
  shift
  if [ "$dry" = 1 ]; then echo "[dry-run] $*"; else echo "+ $*"; (cd "$dir" && "$@"); fi
}

has() { case "$acts" in *" $1 "*) return 0 ;; esac; return 1; }

need_tools() {
  local tool
  for tool in uv npm node curl git; do
    command -v "$tool" > /dev/null 2>&1 || { block "$tool not found on PATH"; return 1; }
  done
}

# main goes into a private ref: --refmap= stops the explicit refspec from also updating
# refs/remotes/origin/main, which every session sharing this object store fetches (a lock race).
fetch_private() {
  git -c gc.auto=0 fetch --refmap= -q origin "+main:$PRIVATE_REF"
}

# ---- the release tree: slot functions ----------------------------------------------------------
# slot_prepare / slot_update / slot_activate act on $tree (var/release/<slot>); `current` follows
# the active slot, and activate restarts it in place (ADR 0077's flip replaces that).

link_one() {  # link_one <source> <link>: create once, check every cycle
  local src=$1 dst=$2
  if [ -L "$dst" ]; then
    if [ "$(readlink "$dst")" != "$src" ]; then
      block "the release tree's $dst points at $(readlink "$dst"), not $src"; return 1
    fi
    return 0
  fi
  if [ -e "$dst" ]; then block "the release tree has its own $dst where a link to $src belongs"; return 1; fi
  mkdir -p "$(dirname "$dst")"
  ln -s "$src" "$dst"
}

slot_links() {
  local root_dir=$root f pat
  if [ "$dry" = 1 ]; then echo "[dry-run] link var, .env, config/users, config/site/*.local.toml, apps/web/{$WEB_ENV_OVERLAY} into $tree"; return 0; fi
  link_one "$root_dir/var" "$tree/var" || return 1
  if [ -e "$root_dir/.env" ]; then link_one "$root_dir/.env" "$tree/.env" || return 1; fi
  mkdir -p "$root_dir/config/users"  # always linked: a first user-config write must not make a real dir in the tree
  link_one "$root_dir/config/users" "$tree/config/users" || return 1
  for f in "$root_dir"/config/site/*.local.toml; do
    if [ -e "$f" ]; then link_one "$f" "$tree/config/site/$(basename "$f")" || return 1; fi
  done
  for pat in $WEB_ENV_OVERLAY; do  # the web build's own env: without it VITE_SUPABASE_* is baked out
    for f in "$root_dir"/apps/web/$pat; do
      if [ -e "$f" ]; then link_one "$f" "$tree/apps/web/$(basename "$f")" || return 1; fi
    done
  done
  for f in "$tree"/config/site/*.local.toml "$tree"/apps/web/.env*; do  # a local file removed from main
    if [ -L "$f" ] && [ ! -e "$f" ]; then rm -f "$f"; fi
  done
}

# Fail closed: a build made without the Supabase URL the main checkout's apps/web/.env.local
# holds would swap in a sign-in page that says "not set up". Checked on the finished build.
web_env_check() {
  local dist=$1 url
  [ "$dry" = 0 ] || return 0
  [ -f "$root/apps/web/.env.local" ] || return 0
  url=$(grep -E '^VITE_SUPABASE_URL=' "$root/apps/web/.env.local" | tail -1 | cut -d= -f2- | tr -d "\"' ")
  if [ -n "$url" ] && ! grep -rqF -- "$url" "$dist"; then
    block "the web build lacks VITE_SUPABASE_URL from apps/web/.env.local (is it linked into the release tree?)"
    return 1
  fi
}

slot_space() {  # refuse under max(5 GB, 3x the tree): the volume runs near full (ADR 0079)
  local free_kb size_kb floor_kb=$MIN_FREE_KB
  free_kb=${ALGOTRADE_DEPLOY_FREE_KB:-$(df -Pk "$root" | awk 'NR==2 {print $4}')}
  size_kb=0
  if [ -d "$tree" ]; then size_kb=$(du -sk "$tree" | awk '{print $1}'); fi
  if [ $((size_kb * 3)) -gt "$floor_kb" ]; then floor_kb=$((size_kb * 3)); fi
  if [ "$free_kb" -lt "$floor_kb" ]; then
    block "only $((free_kb / 1024)) MB free; a release deploy needs $((floor_kb / 1024)) MB (the larger of 5 GB and 3x the tree)"
    return 1
  fi
}

slot_prepare() {
  slot_links || return 1
  slot_space || return 1
}

slot_update() {  # move the tree to the target, then sync and build what the plan says
  local target=$1
  run git -C "$tree" checkout -q --force --detach "$target" || { block "checkout of ${target:0:9} in the release tree failed"; return 1; }
  run git -C "$tree" reset -q --hard "$target" || { block "reset of the release tree to ${target:0:9} failed"; return 1; }
  if [ "$dry" = 0 ] && [ -n "$(git -C "$tree" status --porcelain -uno --ignore-submodules)" ]; then
    block "the release tree is not clean at ${target:0:9}"; return 1
  fi
  if has sync; then
    run_in "$tree" uv sync --all-packages --locked || { block "uv sync failed"; return 1; }  # the tree's own venv
  fi
  if has web; then
    # Built beside the live one, outside every git path; a changed package-lock.json is newer than node_modules, so make runs npm ci.
    if [ "$dry" = 0 ]; then rm -rf "$webdir.next"; fi
    run make -C "$tree" web-build WEB_DIST="$webdir.next" || { block "the web build failed"; return 1; }
    web_env_check "$webdir.next" || return 1
  fi
}

slot_activate() {  # restart the API in place, verify, swap the web build in
  local target=$1
  local verify=("$api" deploy-verify --expect "$target")
  if has restart; then
    run launchctl kickstart -k "gui/$(id -u)/com.algotrade.api" \
      || { block "the API restart failed"; return 1; }
    local check=full
    if has web; then check=api; fi  # the served web is still the old build until the swap
    run "${verify[@]}" --check "$check" || { block "the API did not come back at ${target:0:9}"; return 1; }
  fi
  if has web; then
    if [ "$dry" = 1 ]; then
      echo "[dry-run] swap $webdir.next into $webdir (old assets/ kept for open tabs)"
    else
      # Hashed asset names: an open tab keeps loading the files of the build it has.
      carry_assets "$webdir" "$webdir.next"
      rm -rf "$webdir.prev"
      if [ -d "$webdir" ]; then mv "$webdir" "$webdir.prev"; fi
      mv "$webdir.next" "$webdir"
    fi
    run "${verify[@]}" --check web || { block "the served web is not at ${target:0:9} after the swap"; return 1; }
  fi
}

# ---- phase B: under the deploy lock (algotrade-ingest deploy-hold --deploy-only) -------------
apply_phase() {
  local mode=$1 target=$2
  shift 2
  local acts=" $* " before
  before=$(git -C "$tree" rev-parse HEAD)
  # a later manual deploy must not be rewound by an earlier-planned cycle
  if [ "$before" != "$target" ] && git merge-base --is-ancestor "$target" "$before"; then
    say "skipped: tree already past ${target:0:9}"; return 0
  fi
  if ! git merge-base --is-ancestor "$before" "$target"; then
    block "the release tree ${before:0:9} has diverged from ${target:0:9}"; return 1
  fi
  slot_prepare || return 1
  slot_update "$target" || return 1
  slot_activate "$target" || return 1
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
  # --tree: the installed agents run the release tree, so the comparison must too
  "$api" schedule --agent api --tree "$tree" --out "$dir/com.algotrade.api.plist" > /dev/null || true
  "$api" schedule --agent deploy --tree "$tree" --out "$dir/com.algotrade.deploy.plist" > /dev/null || true
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

# ---- the ingest checkout, brought forward separately (ADR 0079 step 5) --------------------------
# After a serving deploy and on idle cycles: when the main checkout lacks the target, try BOTH locks
# without waiting; busy means silence and the next cycle retries. Never blocks serving: a main
# checkout that is dirty, off main or diverged posts one notification per reason and writes
# var/deploy/ingest_sync_blocked, cleared by the next successful sync.
ingest_sync() {
  local script=$1 slot=$2 target=$3 rc=0
  if [ ! -x "$ingest" ] && [ "$dry" = 0 ]; then return 0; fi  # no tree venv yet: nothing to hold with
  if [ "$dry" = 1 ]; then
    echo "[dry-run] ingest checkout: fast-forward $root to ${target:0:9} under both locks when it lacks it"
    return 0
  fi
  if git merge-base --is-ancestor "$target" HEAD 2> /dev/null; then  # nothing to bring forward
    rm -f "$state/ingest_sync_blocked"; return 0
  fi
  "$ingest" deploy-hold -- bash "$script" --slot "$slot" --ingest-apply "$mode" "$target" || rc=$?
  case "$rc" in
    0 | 75) ;;  # 75: an ingest or a deploy holds a lock; retry next cycle, say nothing
    *) say "ingest sync: deploy-hold exited $rc" ;;
  esac
  return 0
}

ingest_block() {  # one notification per reason; the file holds the current one
  local reason=$1
  if [ -f "$state/ingest_sync_blocked" ] && [ "$(cut -d' ' -f2- "$state/ingest_sync_blocked")" = "$reason" ]; then
    return 0
  fi
  printf '%s %s\n' "$(stamp)" "$reason" > "$state/ingest_sync_blocked"
  say "ingest sync: $reason"
  notify "the ingest checkout cannot sync: $reason"
}

ingest_apply() {  # under both locks: HEAD..target, never last_sha..target
  local target=$1 head hint=""
  if [ "$(git rev-parse --abbrev-ref HEAD)" != main ]; then
    ingest_block "the ingest checkout $root is on '$(git rev-parse --abbrev-ref HEAD)', not main"; return 0
  fi
  if [ -n "$(git status --porcelain -uno --ignore-submodules)" ]; then
    ingest_block "the ingest checkout $root has uncommitted changes"; return 0
  fi
  head=$(git rev-parse HEAD)
  if git merge-base --is-ancestor "$target" "$head"; then rm -f "$state/ingest_sync_blocked"; return 0; fi
  if ! git merge-base --is-ancestor "$head" "$target"; then
    ingest_block "the ingest checkout $root has commits that are not on origin/main (diverged)"; return 0
  fi
  local plan merr
  if ! plan=$("$api" deploy-plan --since "$head" --to "$target" 2> /dev/null); then
    say "ingest sync: deploy-plan failed for ${head:0:9}..${target:0:9}"
    ingest_block "deploy-plan failed for the ingest checkout's range"; return 0  # before any merge
  fi
  if [ -n "$("$api" deploy-plan --ingest-sync --since "$head" --to "$target" 2> /dev/null || true)" ]; then
    hint=", ingest code changed"
  fi
  if ! merr=$(git merge --ff-only -q "$target" 2>&1); then
    case "$merr" in *index.lock*) return 0 ;; esac  # a git command of the owner's is running: busy
    ingest_block "the fast-forward of $root to origin/main failed"; return 0
  fi
  case " $plan " in
    *" sync "*)
      if ! uv sync --all-packages --locked; then
        git reset -q --hard "$head"  # retried next cycle, not left half-synced
        if ! uv sync --all-packages --locked; then  # put the venv back on the old lock
          ingest_block "uv sync failed in the ingest checkout $root (venv left inconsistent)"; return 0
        fi
        ingest_block "uv sync failed in the ingest checkout $root"; return 0
      fi
      ;;
  esac
  rm -f "$state/ingest_sync_blocked"
  say "ingest checkout moved ${head:0:9} -> ${target:0:9}$hint"
}

# ---- --init-release: owner-run once -----------------------------------------------------------
# Creates var/release/<slot> from the private ref, links the overlay, builds its venv and web
# (carrying var/web's assets for tabs open on the old build), points `current` at it and prints
# the launchd commands. Never installs or restarts an agent. The main checkout may be behind and
# lack this very code, so when the target's copy of this script differs the work runs from it, in
# a temporary worktree of refs/deploy/main.
init_release() {
  local script=$1 slot=$2 target tmp rc=0
  need_tools || return 1
  if [ -e "$tree/.git" ]; then
    echo "the release tree $tree already exists"; init_next "$slot"; return 0
  fi
  fetch_private || { echo "refusing: git fetch failed" >&2; return 1; }
  target=$(git rev-parse "$PRIVATE_REF")
  if [ -L "$root/var/release/current" ] && [ "$(basename "$(readlink "$root/var/release/current")")" != "$slot" ]; then
    echo "refusing: var/release/current points at $(readlink "$root/var/release/current"), not $slot (only the blue/green flip moves it)" >&2
    return 1
  fi
  if [ -z "${ALGOTRADE_DEPLOY_REEXEC:-}" ] && [ "$dry" = 0 ] \
    && git cat-file -e "$target:scripts/ops/deploy.sh" 2> /dev/null \
    && ! git show "$target:scripts/ops/deploy.sh" | cmp -s - "$script"; then
    tmp=$(mktemp -d)
    git worktree add -q --detach "$tmp/tree" "$target" || { rm -rf "$tmp"; return 1; }
    say "init-release: running the deploy script of ${target:0:9} from a temporary worktree"
    ALGOTRADE_DEPLOY_REEXEC=1 bash "$tmp/tree/scripts/ops/deploy.sh" --slot "$slot" --init-release || rc=$?
    git worktree remove --force "$tmp/tree" || true
    rm -rf "$tmp"
    return "$rc"
  fi
  slot_space || return 1
  mkdir -p "$root/var/release"
  run git worktree add -q --detach "$tree" "$target" || return 1
  init_build "$target" || rc=$?
  if [ "$rc" != 0 ]; then
    echo "init-release failed: removing the half-made tree (fix the cause, then run it again)" >&2
    if [ "$dry" = 0 ]; then
      git worktree remove --force "$tree" || true
      rm -rf "$webdir.next"
    fi
    return "$rc"
  fi
  if [ "$dry" = 0 ] && [ ! -L "$root/var/release/current" ]; then ln -s "$slot" "$root/var/release/current"; fi
  say "init-release: $tree at ${target:0:9}"
  init_next "$slot"
}

init_build() {
  local target=$1
  slot_links || return 1
  run_in "$tree" uv sync --all-packages --locked || return 1
  if [ "$dry" = 0 ]; then rm -rf "$webdir.next"; fi
  run make -C "$tree" web-build WEB_DIST="$webdir.next" || return 1
  web_env_check "$webdir.next" || return 1
  if [ "$dry" = 0 ]; then
    carry_assets "$root/var/web" "$webdir.next"  # tabs open on the old build keep their files
    rm -rf "$webdir"
    mv "$webdir.next" "$webdir"
  fi
}

init_next() {
  local slot=$1
  cat << EOF
Nothing was installed or restarted. The owner now runs, from $root:
  launchctl bootout gui/$(id -u)/com.algotrade.deploy 2>/dev/null || true   # first: the old agent would keep swapping var/web
  $tree/.venv/bin/algotrade-api schedule --tree var/release/$slot
  $tree/.venv/bin/algotrade-api schedule --agent deploy --tree var/release/$slot
then the install commands each of them prints (the API and deploy agents together; docs/hosting.md).
EOF
}

main "$@"; exit $?
