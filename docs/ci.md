# CI: what runs on a pull request, and running it locally

The repo is public, so GitHub-hosted runners are free: every job runs on `ubuntu-latest`.
**Never add self-hosted runners while the repo is public**: a pull request from a fork could run
its code on that machine.

| Workflow / job | When |
|---|---|
| CI: changed areas | every run (seconds): decides which jobs a pull request needs |
| CI: lint, types, boundaries, ownership, dupes, file length, strategy evaluation | Python changes |
| CI: tests, four shards (`unit-a`, `unit-b` by subfolder; `apps`, `libs`, `contract`, `architecture`; the slow rest: property, integration, e2e, scripts, reconciliation) per Python version (3.12 on PRs; 3.12 + 3.13 on main) | Python changes; web-only and docs-only PRs run `tests/architecture` only (the layout rules, the ADR index, links, the roadmap cap) |
| CI: tests (the gate: fails on a failed shard; combines the shards' coverage, 90 %) | every run |
| CI: web static (generated files fresh, ds:check, lint, types, unit) | web changes |
| CI: web e2e (production build, Playwright, in the Playwright image) | web changes |
| CI: web Storybook build (uploaded as the `storybook-static` artifact) | web changes |
| CI: web screenshots + axe, four shards over the artifact, in the Playwright image | web changes |
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
| CI critical path on a web PR | 12 min: one serial Web job (lint, types, unit, build, Storybook, e2e, 760 screenshots + axe) | #280: 6.0 min (Storybook 30 s, then two screenshot shards of 5.3 min); #286: 3.0 min (four shards of ~2.5 min) |
| CI critical path on a Python PR | 12 min (the Web job; the tests job 5 min) | #280: 9.0 min, all of it the one pytest job (5 142 tests with branch coverage, 8 min 34 s); #286: 6.1 min (shards unit 5.6, apps 3.3, rest 1.7 min, then the combine); P1c splits `unit` in two, target ~4 min |
| CI on a docs-only PR | quality 1 min + tests 5 min + web 12 min | the tests job runs `tests/architecture` only (~1 min) |
| Local full pass (`make check WORKERS=2 WEB_WORKERS=2`) | 30–40 min, run 2–3 times per PR (396 runs in the week to 2026-10-07, 4.5 per PR, three to five at once on the shared machine) | narrowed by `make changed` (Local fast path below), then the push: CI is the full gate (rule 9). A deliberate local `make check` is scope-aware (below): python-only measured 11 min 48 s on 2026-10-08 (pytest 10 min 45 s of it, 5,174 tests at `-n auto`, another session's pytest running alongside), web-only = the web gates in parallel with no pytest, mixed = the longer side, not the sum; `FULL=1` is the old 30–40 min |
| `VITEST_MAX_WORKERS=2 npm run test` (242 files) | 142 s | 35 s (`pool: 'vmThreads'`) |
| Several sessions on one machine | web servers fought over 8000 / 5173 / 4173 / 5801-5802 / 8801-8802 / 6007; two `make check` runs timed each other out; `pkill -f node` killed other sessions' runs | each worktree has its own port block (`ALGOTRADE_PORT_BASE` in `worktree.env`); `make check` refuses a second run in a worktree; `make doctor` lists the other runs and warns when the main checkout is off `main` or has local `config/site` edits |
| Flaky reruns | a standing list in the roadmap; one PR (#196) existed only for a flake | `apps/web/quarantine.json` (below); one Playwright retry in CI; 20 s timeout for integration-style vitest files |
| Merge rounds per PR | 3 merges of origin/main + 2 screenshot regenerations in one session | one `scripts/merge_main.sh` run (generated files regenerated on conflict); `make numbering` catches ADR and rule number collisions before the push; `architecture/ownership.toml`, `layout.toml` and `web_layout.toml` entries are id-ordered inside each section (fitness test), so two PRs adding an entry stop colliding at the end of the file; screenshot baselines regenerate in CI on the `update-screenshots` label (below) instead of Docker; the roadmap's Now / Next is one line per track (details under "Track details"), so two PRs rarely edit the same line |

### Local fast path

`make changed` runs the mirrored Python tests, then the web checks `scripts/changed_web.py`
maps from the changed `apps/web` files (slice or component folder -> vitest; page or route ->
the e2e spec named after it, else `smoke`; story or CSS module -> that component's screenshots,
printed as a Docker command off Linux; any `.ts` / `.tsx` -> `npm run typecheck`), then the
fast gates. Then push: CI is the full gate (owner decision 2026-10-08: the machine never
runs the full `make check`); after a CI failure rerun only the failed gate locally. The vitest pool is `vmThreads`: jsdom is created once per
worker instead of once per file.

### Scope-aware `make check` (the release, and a deliberate full run)

A bare `make check` refuses and prints rule 9 (the mechanical side of "CI is the gate": an
agent that types it out of habit is stopped by the Makefile). `make check SCOPED=1` gates the areas the branch changed vs `origin/main` (`make check-scope` prints
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
macOS has no `-O`); make names the failed target at the end. It runs under the per-worktree
lock below. With rule 9 (sessions push after `make changed`; CI gates) full local runs are
rare, so the `WORKERS=2 WEB_WORKERS=2` caps go: a run gets every core (10, 4 performance;
16 GB). The caps dated from the overloads of #94 / #95 / #98, when three to five full checks
ran side by side.

Shared machine (several sessions, one Mac):

- **Ports.** `scripts/worktree.sh` writes `ALGOTRADE_PORT_BASE = 10000 + cksum(path) % 500 * 10`
  into `worktree.env`: API +0, Vite dev +1, real-app api/web pairs +2..+5, Storybook preview
  +6, vite preview +7 (`vite.config.ts`, `playwright*.config.ts`). Unset (CI, the main
  checkout) the usual numbers apply. Two worktrees can hash to one block (1 in 500): re-create one.
- **`make check` lock.** `make check` is `scripts/ops/check_lock.sh make check-gates`: a
  `mkdir` lock `var/check.lock.d` with the PID, stale when the PID is dead, released on exit.
  A second `make check` in the same worktree refuses and names the first run's PID and start.
  Stop a run by its PID, never `pkill -f make|node|vite|playwright` (a rule in CLAUDE.md).
- **Deploy.** `scripts/ops/deploy.sh [--dry-run]` updates the running site from the main
  checkout (must be on `main`, clean): pull, `make web-build`, restart the API agent, health.
- **Machine-local site config.** `config/site/<name>.local.toml` (git-ignored) is merged over
  `<name>.toml` (docs/configuration.md), so the main checkout stays clean for `deploy.sh`.

### Permission prompts

Commands the owner approves once in `.claude/settings.json` `permissions.allow` stop the
prompts for the pipeline's own scripts: `launchctl kickstart`, `scripts/worktree.sh`,
`scripts/ops/deploy.sh`, `scripts/merge_main.sh`, `gh pr ready`, `gh pr edit` (the proposed list
is in the PR that added this note). Agents never edit `settings.json` themselves.

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
  miss); the real-app job uses the same cache. `npm audit` (44 s) runs only when a package
  file changed (`changes.web_deps`): nothing else can alter its answer.

How the Python tests are cut (`make test` locally is unchanged):

- **test** runs four shards in parallel, `make test-shard SHARD=unit-a|unit-b|apps|rest` (the folders
  in the Makefile's `TEST_SHARD_*`; a fitness test keeps them covering every `tests/` folder),
  each writing `.coverage.<shard>` with the gate off, uploaded as an artifact.
- **tests** is the protected check `Tests (py3.12)`: it fails when a shard failed, then
  downloads the data files and runs `make coverage-combine` (`coverage combine`, the
  90 % gate, `coverage.xml`). A web-only or docs-only PR runs `tests/architecture` in the
  `rest` shard and the gate passes without coverage.

### Screenshot baselines from CI

Baselines are Linux PNGs, so a change to a story or component used to need Docker locally.
Add the label `update-screenshots` to the PR (or run the "Screenshot baselines" workflow on a
branch): `.github/workflows/screenshots.yml` runs in the same Playwright image as CI
(`mcr.microsoft.com/playwright:v1.63.0-noble`, a fitness test keeps the two in step), builds
Storybook, runs `npm run visual -- --update-snapshots --fully-parallel`, commits the changed
PNGs to the PR branch as `github-actions[bot]` and removes the label. It never runs for a
fork. A push with `GITHUB_TOKEN` starts no CI run, so push any follow-up commit (or
`gh workflow run ci.yml --ref <branch>`) afterwards, so CI and auto-merge see the new head.
Review the PNG diff in the PR before that follow-up.

## Flaky specs

A spec that fails under load and passes on re-run goes in `apps/web/quarantine.json`, never
`test.skip` in the spec (a fitness test refuses that):

- `skipped`: not run by `npm run e2e` / `npm run test` (Playwright `grepInvert`, Vitest
  `exclude`). `QUARANTINE=only npm run e2e` runs exactly those, to see whether a fix holds.
  At most 8; the oldest is fixed before another is added.
- `watched`: still runs and gates; listed with the fix that keeps it green.
- Every entry: `kind`, `file`, `title` (e2e), `since`, `reason` (what flakes, the fix it waits for).
- A story whose `play` clicks must settle before the screenshot: `await waitFor(` or
  `await expect(` after the last click, or `tags: ['no-screenshot']` on the story (the visual
  suite skips it, so it has no PNG). `npm run ds:check` fails otherwise: a screenshot taken
  while the click's redraw is in flight is the commonest flake.
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
