# CI: what runs on a pull request, and running it locally

The repo is public, so GitHub-hosted runners are free: every job runs on `ubuntu-latest`.
**Never add self-hosted runners while the repo is public**: a pull request from a fork could run
its code on that machine.

| Workflow / job | When |
|---|---|
| CI: changed areas | every run (seconds): decides which jobs a pull request needs |
| CI: lint, types, boundaries, ownership, dupes, file length, strategy evaluation | Python changes |
| CI: tests (py3.12 on PRs; 3.12 + 3.13 on main) | Python changes; web-only and docs-only PRs run `tests/architecture` only (the layout rules, the ADR index, links, the roadmap cap) |
| CI: web static (generated files fresh, ds:check, lint, types, unit) | web changes |
| CI: web e2e (production build, Playwright, in the Playwright image) | web changes |
| CI: web Storybook build (uploaded as the `storybook-static` artifact) | web changes |
| CI: web screenshots + axe, two shards over the artifact, in the Playwright image | web changes |
| CI: web (the gate: passes when the four web jobs passed or were skipped) | every run |
| CI: real app smoke (Vite dev server + the real API, empty and golden stores) | Python or web changes |
| Auto-merge sweeps | after every CI run and every 30 minutes |
| Nightly evaluation | daily |
| Release | version tags |

A pull request runs only what its changes can break; skipped jobs count as passed for
auto-merge and for branch protection. Every push to main runs everything.

| Files changed | Lint + evaluation | Tests | Web jobs |
|---|---|---|---|
| only `docs/`, `.claude/`, `*.md`, `LICENSE` | skipped | `tests/architecture` only | skipped |
| only `apps/web/**` | skipped | `tests/architecture` only (web layout rules) | yes |
| none under `apps/web/` or the docs set | yes | full suite | skipped |
| both, or `.github/workflows/ci.yml`, `apps/api/openapi.json`, `apps/api/schema.graphql` | yes | full suite | yes |

Branch protection on `main` requires five check names (`Changed areas`, the lint job, `Tests
(py3.12)`, `Web (lint, types, unit, design system, build, Storybook, e2e, screenshots)`, the
real-app smoke). They are repo settings only the owner changes, so the web jobs report through
one gate job with the protected name; `tests/architecture/pipeline/test_ci_workflow.py` fails a
rename.

## Pipeline

What the pipeline looked like on 2026-10-07 (30 PRs merged that day) and what each change
bought. Numbers are wall-clock on GitHub-hosted runners unless marked local.

| Measure | Before (2026-10-07) | After |
|---|---|---|
| CI critical path on a web PR | 12 min: one serial Web job (lint, types, unit, build, Storybook, e2e, 760 screenshots + axe) | the longest of four parallel web jobs: Storybook build (~2 min) then two screenshot shards (~3 min each); target 5–6 min; measured on the first PRs after this change |
| CI on a docs-only PR | quality 1 min + tests 5 min + web 12 min | the tests job runs `tests/architecture` only (~1 min) |
| Local full pass (`make check WORKERS=2 WEB_WORKERS=2`) | 30–40 min, run 2–3 times per PR (396 runs in the week to 2026-10-07, 4.5 per PR, three to five at once on the shared machine) | narrowed by `make changed` (Local fast path below), then the push: CI is the full gate (rule 9). A deliberate local `make check` is scope-aware (below): python-only measured 11 min 48 s on 2026-10-08 (pytest 10 min 45 s of it, 5,174 tests at `-n auto`, another session's pytest running alongside), web-only = the web gates in parallel with no pytest, mixed = the longer side, not the sum; `FULL=1` is the old 30–40 min |
| `VITEST_MAX_WORKERS=2 npm run test` (242 files) | 142 s | 35 s (`pool: 'vmThreads'`) |
| Flaky reruns | a standing list in the roadmap; one PR (#196) existed only for a flake | `apps/web/quarantine.json` (below); one Playwright retry in CI; 20 s timeout for integration-style vitest files |
| Merge rounds per PR | 3 merges of origin/main + 2 screenshot regenerations in one session | one `scripts/merge_main.sh` run (generated files regenerated on conflict); `make numbering` catches ADR and rule number collisions before the push |

### Local fast path

`make changed` runs the mirrored Python tests, then the web checks `scripts/changed_web.py`
maps from the changed `apps/web` files (slice or component folder -> vitest; page or route ->
the e2e spec named after it, else `smoke`; story or CSS module -> that component's screenshots,
printed as a Docker command off Linux; any `.ts` / `.tsx` -> `npm run typecheck`), then the
fast gates. Then push: CI is the full gate (owner decision 2026-10-08: the machine never
runs the full `make check`); after a CI failure rerun only the failed gate locally. The vitest pool is `vmThreads`: jsdom is created once per
worker instead of once per file.

### Scope-aware `make check` (the release, and a deliberate full run)

`make check` gates the areas the branch changed vs `origin/main` (`make check-scope` prints
them; `scripts/changed_tests.py --areas`, the rule of CI's "Changed areas" job: `apps/web/*`
is web; `docs/`, `.claude/`, `*.md` are docs; the CI workflow and the API's exported schemas
are both; everything else is python; a branch with no change is every area). The python side
(`lock-check` … `test evaluate`) and the web side (`web-check web-real`) run side by side
(`CHECK_JOBS=2`); docs-only runs the architecture fitness tests (`make fitness`). The web gates
are make targets (`web-generated` first, then `web-ds web-lint web-typecheck web-unit
web-storybook web-e2e` in parallel), so `tsc -b` runs once (typecheck) and `vite build` once
(the e2e's web server); `npm run check` stays the serial form. `FULL=1` runs every gate
whatever changed: CI runs the gates per job and the release runs `make check FULL=1`.
`CHECK_SCOPE="python web"` overrides the detection. The outputs interleave (GNU make 3.81 on
macOS has no `-O`); make names the failed target at the end.

One check at a time on the machine: `scripts/check_lock.py` wraps the run in a lock
(`~/.cache/algotrade/check.lock`, `CHECK_LOCK=`), a second check waits and prints who holds it
(pid, worktree, start time), and each run gets every core (`WORKERS=auto`, no vitest cap: the
`WORKERS=2 WEB_WORKERS=2` habit dated from the overloads of #94 / #95 / #98, when three to
five full checks ran side by side). The machine: 10 cores (4 performance), 16 GB.

How the web jobs are cut:

- **web-static** (plain Node): `generated:check`, `ds:check`, lint, `npm run typecheck` (`tsc -b`,
  the only type gate: `npx tsc -p .` passes code that `tsc -b` with `exactOptionalPropertyTypes`
  rejects), unit tests.
- **web-e2e** (Playwright image): `npm run e2e`, whose web server builds the production bundle
  (`vite build`): the `tsc -b` half of `npm run build` is web-static's typecheck.
- **web-storybook** (plain Node): `storybook build`, uploaded as the `storybook-static` artifact.
- **web-screenshots** (Playwright image, `shard 1/2` and `2/2`): download the artifact, check
  the image tag matches the locked `@playwright/test`, screenshots + axe. Adding a shard is one
  matrix entry plus the `/2` in the command.
- All four share one `apps/web/node_modules` cache keyed on the lockfile (`npm ci` only on a
  miss); the real-app job uses the same cache.

## Flaky specs

A spec that fails under load and passes on re-run goes in `apps/web/quarantine.json`, never
`test.skip` in the spec (a fitness test refuses that):

- `skipped`: not run by `npm run e2e` / `npm run test` (Playwright `grepInvert`, Vitest
  `exclude`). `QUARANTINE=only npm run e2e` runs exactly those, to see whether a fix holds.
  At most 8; the oldest is fixed before another is added.
- `watched`: still runs and gates; listed with the fix that keeps it green.
- Every entry: `kind`, `file`, `title` (e2e), `since`, `reason` (what flakes, the fix it waits for).
- One retry in CI for Playwright only (`playwright.config.ts`, `playwright.visual.config.ts`);
  the real-app smoke, pytest and vitest never retry. Integration-style vitest files (`pages/`,
  `widgets/`, `features/`, `scripts/`) are the `integration` vitest project with a 20 s timeout
  (`vite.config.ts`; Vitest fixes a test's timeout at collection, so a setup-file hook is too late).
- A story whose `play` function clicks and whose canvas redraws later screenshots differently
  run to run (two CI rounds on 2026-10-07): the screenshot suite waits for Storybook's render
  phase `finished` and `document.fonts.ready`; a story that still settles later must wait for
  its own ready state inside `play`, or go in the list.

## Running the checks locally before pushing

`make check` runs every CI step (tests in parallel, one worker per CPU; `make test
WORKERS=0` runs them serially). The web screenshots need Docker: `make web-visual`.
