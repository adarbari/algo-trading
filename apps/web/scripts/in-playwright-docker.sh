#!/usr/bin/env bash
# Runs a command inside the official Playwright image (the same Linux + browsers as CI), so
# screenshot baselines are byte-comparable. Usage: scripts/in-playwright-docker.sh npm run visual
set -euo pipefail
cd "$(dirname "$0")/.."
version=$(node -p "require('@playwright/test/package.json').version")
exec docker run --rm --init --ipc=host -e CI=1 \
  -v "$PWD":/work -v algotrade-web-node-modules:/work/node_modules -w /work \
  "mcr.microsoft.com/playwright:v${version}-noble" \
  bash -c "npm ci --no-fund --no-audit >/dev/null && $*"
