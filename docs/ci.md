# CI: what runs on a pull request, and running it locally

The repo is public, so GitHub-hosted runners are free: every job runs on `ubuntu-latest`.
**Never add self-hosted runners while the repo is public**: a pull request from a fork could run
its code on that machine.

| Workflow / job | When |
|---|---|
| CI: changed areas | every run (seconds): decides which jobs a pull request needs |
| CI: lint, types, boundaries, ownership, dupes, file length, strategy evaluation | Python changes |
| CI: tests (py3.12 on PRs; 3.12 + 3.13 on main) | Python changes (web-only PRs run `tests/architecture`) |
| CI: web (lint, types, unit, Storybook, e2e, screenshots), in the Playwright image | web changes |
| CI: real app smoke (Vite dev server + the real API, empty and golden stores) | Python or web changes |
| Auto-merge sweeps | after every CI run and every 30 minutes |
| Nightly evaluation | daily |
| Release | version tags |

A pull request runs only what its changes can break; skipped jobs count as passed for
auto-merge. Every push to main runs everything.

| Files changed | Lint + evaluation | Tests | Web |
|---|---|---|---|
| only `apps/web/**` | skipped | `tests/architecture` only (web layout rules) | yes |
| none under `apps/web/` | yes | full suite | skipped |
| both, or `.github/workflows/ci.yml` or `apps/api/openapi.json` | yes | full suite | yes |

## Running the checks locally before pushing

`make check` runs every CI step (tests in parallel, one worker per CPU; `make test
WORKERS=0` runs them serially). The web screenshots need Docker: `make web-visual`.

## Pipeline

| Measure | Before (2026-10-07) | After |
|---|---|---|
| `VITEST_MAX_WORKERS=2 npm run test` (242 files) | 142 s | 35 s (`pool: 'vmThreads'`) |

### Local fast path

`make changed` runs the mirrored Python tests, then the web checks `scripts/changed_web.py`
maps from the changed `apps/web` files (slice or component folder -> vitest; page or route ->
the e2e spec named after it, else `smoke`; story or CSS module -> that component's screenshots,
printed as a Docker command off Linux; any `.ts` / `.tsx` -> `npm run typecheck`), then the
fast gates. Run the full `make check WORKERS=2 WEB_WORKERS=2` once before the push; after a
failure rerun only the failed gate. The vitest pool is `vmThreads`: jsdom is created once per
worker instead of once per file.
