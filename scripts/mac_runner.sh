#!/usr/bin/env bash
# Register this Mac as GitHub Actions self-hosted runners for the repo (docs/ci.md).
#
#   scripts/mac_runner.sh install [COUNT]   # default 2 CI runners, each a launchd service
#   scripts/mac_runner.sh install-light     # 1 runner for light jobs only (auto-merge sweeps)
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

# register NAME DIR [config.sh flags...]: unpack the runner into DIR, register it, start the service
register() {
  local name="$1" dir="$2"
  shift 2
  if [ -f "$dir/.runner" ]; then echo "$name: already registered"; return; fi
  mkdir -p "$dir" && tar xzf "$tarball" -C "$dir"
  (cd "$dir" && ./config.sh --unattended --url "https://github.com/$REPO" --token "$reg" \
    --name "$name" --work _work --replace "$@" \
    && ./svc.sh install && ./svc.sh start)
}

download() {
  [ "$(uname -sm)" = "Darwin arm64" ] || { echo "Apple silicon Mac only"; exit 1; }
  version=$(gh api repos/actions/runner/releases/latest --jq .tag_name | sed 's/^v//')
  tarball="$ROOT/actions-runner-osx-arm64-$version.tar.gz"
  mkdir -p "$ROOT"
  [ -f "$tarball" ] || curl -fsSL -o "$tarball" \
    "https://github.com/actions/runner/releases/download/v$version/actions-runner-osx-arm64-$version.tar.gz"
  reg=$(token registration-token)
}

case "$action" in
  install)
    download
    for i in $(seq 1 "$count"); do register "$(hostname -s)-$i" "$ROOT/runner-$i"; done
    ;;
  install-light)
    # Only the label `light`: CI jobs ask for [self-hosted, macOS, ARM64] and never land here.
    download
    register "$(hostname -s)-light" "$ROOT/runner-light" --no-default-labels --labels light
    ;;
  status)
    gh api "repos/$REPO/actions/runners" \
      --jq '.runners[] | "\(.name)\t\(.status)\tbusy=\(.busy)\t\([.labels[].name] | join(","))"'
    ;;
  uninstall)
    rem=$(token remove-token)
    for dir in "$ROOT"/runner-*; do
      [ -d "$dir" ] || continue
      (cd "$dir" && { ./svc.sh stop || true; } && { ./svc.sh uninstall || true; } \
        && ./config.sh remove --token "$rem")
    done
    ;;
  *) echo "usage: $0 install [COUNT] | install-light | status | uninstall"; exit 2 ;;
esac
