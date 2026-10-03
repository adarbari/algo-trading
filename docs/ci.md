# CI: where checks run, and running them locally

The repo is private, and GitHub bills private repos per minute of hosted runners. So the
CI jobs run on the owner's Mac as **self-hosted runners** (free); only releases run on GitHub.
The web job runs inside the official Playwright Linux image through Docker, so Docker must be
running on the Mac.

| Workflow / job | Runs on | Why |
|---|---|---|
| CI: lint, types, boundaries, ownership, dupes, file length, strategy evaluation | Mac | |
| CI: tests (py3.12 on PRs; 3.12 + 3.13 on main) | Mac | the bulk of the minutes |
| CI: web (lint, types, unit, Storybook, e2e, screenshots) | Mac, inside the Playwright Linux image (Docker) | screenshot baselines are rendered in that image |
| Auto-merge sweeps | Mac, its own `light` runner | runs after every CI run and every 30 minutes; never waits behind a CI job |
| Nightly evaluation | Mac | |
| Release (tags only) | GitHub, `ubuntu-latest` | rare; `make check` needs Node on Linux |

A pull request runs only what its changes can break (the `Changed areas` job decides; skipped
jobs count as passed for auto-merge). Every push to main runs everything.

| Files changed | Lint + evaluation | Tests | Web |
|---|---|---|---|
| only `apps/web/**` | skipped | `tests/architecture` only (web layout rules) | yes |
| none under `apps/web/` | yes | full suite | skipped |
| both, or `.github/workflows/ci.yml` or `apps/api/openapi.json` | yes | full suite | yes |

Jobs on the Mac wait (queued, not failed) while it is asleep or offline, and auto-merge
waits with them. Each runner runs one job at a time; a PR touching both sides runs four
jobs (including the few-second `Changed areas`), so some wait for a free runner.

## Setting up the runners (once)

```bash
scripts/mac_runner.sh install 2   # downloads the runner, registers 2, starts them as services
scripts/mac_runner.sh install-light  # 1 more, label `light` only: auto-merge sweeps
scripts/mac_runner.sh status      # name, online/offline, busy
scripts/mac_runner.sh uninstall   # stop and deregister
```

Two CI runners is the right number for a 10-core, 16 GB Mac: two overlapping jobs already use
every core (Python tests run 5 workers, `make test WORKERS=5`; the web container sees 5 CPUs,
`--cpuset-cpus=0-4`, so Vitest and Playwright size to 5), and more would only swap. The
`light` runner has no default labels, so CI jobs never land on it; it only runs the auto-merge
sweep (a few GitHub API calls), so merging never queues behind a test run. Install it before
anything else: without it, sweeps wait and nothing auto-merges.

Run `install` from a normal login shell: each runner keeps that shell's `PATH` (for `make`,
`gh`, `jq`). The services start at login. Jobs check out into
`~/actions-runner/runner-N/_work`; uv's cache and managed Pythons are shared in your home
directory, so environments build in seconds.

Only use self-hosted runners while the repo is **private**: on a public repo, a pull request
from a fork could run its code on the Mac.

## Running the checks locally before pushing

`make check` runs every CI step (tests in parallel, one worker per CPU; `make test
WORKERS=0` runs them serially). The web screenshots need Docker: `make web-visual`.
