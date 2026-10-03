#!/usr/bin/env bash
# Register this Mac as GitHub Actions self-hosted runners for the repo (docs/ci.md).
#
#   scripts/mac_runner.sh install [COUNT]   # default 2 runners, each a launchd service
#   scripts/mac_runner.sh status
#   scripts/mac_runner.sh uninstall         # stop, remove the services, deregister
#
# Needs `gh` logged in with admin rights on the repo. Run it from your normal login shell:
# each runner records the current PATH (uv, gh, make) for its jobs.
set -euo pipefail

REPO="${REPO:-adarbari/algo-trading}"
ROOT="${RUNNER_ROOT:-$HOME/actions-runner}"
action="${1:-status}"
count="${2:-2}"

token() { gh api -X POST "repos/$REPO/actions/runners/$1" --jq .token; }

case "$action" in
  install)
    [ "$(uname -sm)" = "Darwin arm64" ] || { echo "Apple silicon Mac only"; exit 1; }
    version=$(gh api repos/actions/runner/releases/latest --jq .tag_name | sed 's/^v//')
    tarball="$ROOT/actions-runner-osx-arm64-$version.tar.gz"
    mkdir -p "$ROOT"
    [ -f "$tarball" ] || curl -fsSL -o "$tarball" \
      "https://github.com/actions/runner/releases/download/v$version/actions-runner-osx-arm64-$version.tar.gz"
    reg=$(token registration-token)
    for i in $(seq 1 "$count"); do
      dir="$ROOT/runner-$i"
      if [ -f "$dir/.runner" ]; then echo "runner-$i: already registered"; continue; fi
      mkdir -p "$dir" && tar xzf "$tarball" -C "$dir"
      (cd "$dir" && ./config.sh --unattended --url "https://github.com/$REPO" --token "$reg" \
        --name "$(hostname -s)-$i" --work _work --replace \
        && ./svc.sh install && ./svc.sh start)
    done
    ;;
  status)
    gh api "repos/$REPO/actions/runners" --jq '.runners[] | "\(.name)\t\(.status)\t\(.busy)"'
    ;;
  uninstall)
    rem=$(token remove-token)
    for dir in "$ROOT"/runner-*; do
      [ -d "$dir" ] || continue
      (cd "$dir" && { ./svc.sh stop || true; } && { ./svc.sh uninstall || true; } \
        && ./config.sh remove --token "$rem")
    done
    ;;
  *) echo "usage: $0 install [COUNT] | status | uninstall"; exit 2 ;;
esac
