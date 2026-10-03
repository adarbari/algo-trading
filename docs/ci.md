# CI: where checks run, and running them locally

The repo is private, and GitHub bills private repos per minute of hosted runners. So the
CI jobs run on the owner's Mac as **self-hosted runners** (free); only releases run on GitHub.
The web job runs inside the official Playwright Linux image through Docker, so Docker must be
running on the Mac.

| Workflow / job | Runs on | Why |
|---|---|---|
| CI: lint, types, boundaries, ownership, dupes, file length | Mac | |
| CI: tests (py3.12 on PRs; 3.12 + 3.13 on main) | Mac | the bulk of the minutes |
| CI: strategy evaluation | Mac | |
| CI: web (lint, types, unit, Storybook, e2e, screenshots) | Mac, inside the Playwright Linux image (Docker) | screenshot baselines are rendered in that image |
| Auto-merge sweeps | Mac | runs after every CI run and every 30 minutes |
| Nightly evaluation | Mac | |
| Release (tags only) | GitHub, `ubuntu-latest` | rare; `make check` needs Node on Linux |

Jobs on the Mac wait (queued, not failed) while it is asleep or offline, and auto-merge
waits with them. Each runner runs one job at a time; a PR runs four jobs, so with two
runners two wait for a free one.

## Setting up the runners (once)

```bash
scripts/mac_runner.sh install 2   # downloads the runner, registers 2, starts them as services
scripts/mac_runner.sh status      # name, online/offline, busy
scripts/mac_runner.sh uninstall   # stop and deregister
```

Run `install` from a normal login shell: each runner keeps that shell's `PATH` (for `make`,
`gh`, `jq`). The services start at login. Jobs check out into
`~/actions-runner/runner-N/_work`; uv's cache and managed Pythons are shared in your home
directory, so environments build in seconds.

Only use self-hosted runners while the repo is **private**: on a public repo, a pull request
from a fork could run its code on the Mac.

## Running the checks locally before pushing

`make check` runs every CI step (tests in parallel, one worker per CPU; `make test
WORKERS=0` runs them serially). The web screenshots need Docker: `make web-visual`.
