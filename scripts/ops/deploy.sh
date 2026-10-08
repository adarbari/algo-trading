#!/usr/bin/env bash
# Update the running site from the main checkout (docs/hosting.md): pull main, rebuild the web,
# restart the API agent, print its health. Run it from anywhere in the repo.
#
#   scripts/ops/deploy.sh [--dry-run]
#
# Refuses unless the main checkout is on `main` with a clean tree. The git-ignored overlay
# (config/site/*.local.toml, .env, var/) never counts as dirty. --dry-run prints the plan.
set -euo pipefail

dry=0
for a in "$@"; do
  case "$a" in
    --dry-run) dry=1 ;;
    -h | --help) sed -n '2,8p' "$0"; exit 0 ;;
    *) echo "usage: scripts/ops/deploy.sh [--dry-run]" >&2; exit 2 ;;
  esac
done

main=$(cd "$(git rev-parse --git-common-dir)/.." && pwd)
branch=$(git -C "$main" rev-parse --abbrev-ref HEAD)
if [ "$branch" != main ]; then
  echo "refusing: the main checkout $main is on '$branch', not main" >&2; exit 1
fi
if [ -n "$(git -C "$main" status --porcelain -uno --ignore-submodules)" ]; then
  echo "refusing: the main checkout $main has uncommitted changes (untracked and git-ignored files are fine;" \
    "a committed file edited here is not: move it to config/site/<name>.local.toml)" >&2
  git -C "$main" status --short >&2
  exit 1
fi

run() {
  if [ "$dry" = 1 ]; then echo "[dry-run] $*"; else echo "+ $*"; "$@"; fi
}

cd "$main"
run git pull --ff-only origin main
run make web-build
run launchctl kickstart -k "gui/$(id -u)/com.algotrade.api"
if [ "$dry" = 1 ]; then
  echo "[dry-run] curl -s http://127.0.0.1:8000/health"
else
  sleep 3
  curl -s http://127.0.0.1:8000/health || echo "health check failed: see var/logs/api.err.log" >&2
  echo
fi
