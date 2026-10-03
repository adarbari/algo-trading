# CI: where checks run, and running them locally

The repo is private, and GitHub bills private repos per minute of hosted runners. So the
Python jobs run on the owner's Mac as **self-hosted runners** (free), and only what needs
Linux runs on GitHub.

| Workflow / job | Runs on | Why |
|---|---|---|
| CI: lint, types, boundaries, ownership, dupes, file length | Mac | |
| CI: tests (py3.12 on PRs; 3.12 + 3.13 on main) | Mac | the bulk of the minutes |
| CI: strategy evaluation | Mac | |
| CI: web (lint, types, unit, Storybook, e2e, screenshots) | GitHub, `ubuntu-latest` | the Playwright Linux container; screenshot baselines are rendered on Linux |
| Auto-merge sweeps | Mac | runs after every CI run and every 30 minutes |
| Nightly evaluation | Mac | |
| Release (tags only) | GitHub, `ubuntu-latest` | rare; `make check` needs Node on Linux |

Jobs on the Mac wait (queued, not failed) while it is asleep or offline, and auto-merge
waits with them. Two runners let two jobs run at once; a PR runs three Mac jobs, so the
third starts when one finishes.

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
