# ADR 0079: A release tree for serving: a deploy never waits on an ingest

**Status:** proposed (2026-10-20; owner chose option 2 the same day: the API and web serve from
a separate release tree; the architect reviews before code). Amends
[0057](0057-auto-deploy-from-origin-main.md) (decision 4 and its 2026-10-09 amendment: the
ingest lock leaves the serving deploy) and [0044](0044-hosting-from-the-owners-mac.md) (what the
API agent runs and where the web build lives). Consistent with
[0077](0077-serving-release.md) decision 11 (blue/green behind a front proxy): its colours are
this ADR's slots. Runbook: [docs/hosting.md](../hosting.md) "Auto-deploy".

## Context
The auto-deploy has skipped every cycle since 04:42Z on 2026-10-20: back-to-back ingest
backfills hold the ingest run lock and the pending diff touches `apps/ingestion` and `config/site`,
which a running ingest loads (`holds_ingest`). The live API was at `dbbe73c10` and the web at
`fa786e289` while `origin/main` moved on. The ingest lock exists because the ingest, the API and
the deploy share one checkout and one venv: a `git merge` or `uv sync` under a running ingest gives
it mixed-version code (late imports, a half-written venv). That is a property of sharing a tree,
not of serving, so the fix is to stop sharing it. A second, smaller defect has the same cause:
the deployer's `git fetch origin main` writes `refs/remotes/origin/main`, which every session
sharing the checkout's object store also fetches, so it races them
(`cannot lock ref refs/remotes/origin/main`).

## Decision
1. **Serving runs from a release tree, never from the main checkout.** A release tree is a git
   worktree of this repo at `var/release/<slot>` (detached HEAD; a slot is named, the first is
   `blue`), with its own `.venv` (created by `uv sync --all-packages --locked` run **inside the
   release tree**: its venv is its own, never the link CLAUDE.md forbids using from a session
   worktree) and its own web build in `var/release/<slot>/web`. The API agent runs
   `var/release/<slot>/.venv/bin/algotrade-api` with `WorkingDirectory` and `ALGOTRADE_WEB_DIST`
   in that tree. The tree is the deployer's alone: it is reset to the target sha (`git checkout
   --detach`, `reset --hard`) and is never edited, so the dirty / off-main / diverged guards of
   0057 decision 7 apply to it only as "the tree is not at the sha it should be".
2. **Ingestion, the nightly, the monthly fill and every other agent keep running from the main
   checkout and its venv**, unchanged. The main checkout stays on `main` (CLAUDE.md) and no longer
   serves. It reaches new code in step 5.
3. **A serving deploy needs only the `deploy` lock** (`algotrade-ingest deploy-hold
   --deploy-only`), never the ingest run lock. Nothing the deploy touches (the release tree, its
   venv, its web build, the API agent) is loaded by a running ingest, so the 0057 amendment's
   reason is gone; a nightly takes only the ingest lock, so it never meets the deploy lock. `holds_ingest` and the `deploy-plan --locks` allowlist stop deciding serving deploys.
4. **Deploy steps, per cycle** (`deploy.sh --auto`, same script, same bash-parses-first rule):
   fetch into a private ref (`git -c gc.auto=0 fetch --refmap= -q origin +main:refs/deploy/main`:
   `--refmap=` is required, since an explicit refspec otherwise still updates
   `refs/remotes/origin/main` as a side effect; only the deployer writes the private ref, so it
   cannot race other sessions' fetches; a test asserts `refs/remotes/origin/main` is untouched), plan the diff of
   `last_sha..refs/deploy/main` against the same action map as today (`sync` when `uv.lock` or a
   `pyproject.toml` changed, `web`, `restart`, `plists`), move the release tree to the target,
   `uv sync` in it when the plan says so, build the web into `<slot>/web.next` and rename it into
   place (0057 decision 5 unchanged, hashed assets of the previous build carried), restart the
   API agent from its own tree, `deploy-verify` against `/health` (the API's build stamp is the
   release tree's commit, `ops/build.py` `REPO`, so verification needs no change), then write
   `var/deploy/last_sha` (temp file and rename). `last_sha` and `blocked` stay in the main
   checkout's `var/deploy/` (state is one place). A failed sync, build, restart or verify blocks
   and notifies as in 0057 decision 7 and rolls back nothing; because the release tree is clean
   by construction (clean means `git status --porcelain -uno`; the web build and the symlinks live
   outside tracked paths, below) the "dirty tree" block no longer exists for serving.
5. **The ingest tree is brought forward separately and never blocks serving.** After a serving
   deploy, and on cycles with nothing to serve, the script tries the ingest run lock without
   waiting (`algotrade-ingest deploy-hold`, both locks) and, when it gets it, fast-forwards the
   main checkout to the same sha (and `uv sync` when dependencies changed) as soon as the lock is held (it
   is held anyway; the range is main `HEAD..target`, never `last_sha..target`, so a change that
   arrived in an earlier lock-busy cycle is still applied), and runs `uv sync` only on a
   dependency change. `holds_ingest` is then only a log hint (which changes matter to an ingest). Lock busy: log nothing,
   retry next cycle. So ingestion picks up new code the next time it starts (the nightly's
   watchdog, the next backfill) or in any gap between runs, and a run is never rewritten under
   itself. A dirty, off-main or diverged main checkout never blocks serving: it posts one
   notification per reason ("the ingest checkout cannot sync: ...") and writes
   `var/deploy/ingest_sync_blocked`, cleared by the next successful sync. The manual deploy
   (`deploy.sh`, `--dry-run`) does both.
6. **Ingest code may lag the served code.** The API deployed at sha B can read stores written by
   ingestion at an older sha A. That is already the model: a fact not stored is UNKNOWN with a
   reason (0036), and 0077 makes the release format additive by default with a format gate for
   the rest. A change that needs new ingested data to be correct is merged in two PRs, or says so
   in the PR; the deploy does not coordinate them.
7. **Launchd and paths.** `algotrade-api schedule --agent api` and `--agent deploy` take the release tree
   (`--tree var/release/blue`, default the main checkout so today's command still works) for
   `ProgramArguments[0]`, `WorkingDirectory` and `ALGOTRADE_WEB_DIST`, and `plists_check` passes
   it too (else every cycle sends a false "reinstall"); the deploy agent runs
   `var/release/current/scripts/ops/deploy.sh --auto` (`current` a symlink to the active slot, so
   the plist is written once and a slot change never needs a reinstall); the ingestion plists
   (`nightly`, watchdog, Tiingo fill) are untouched: `repo` stays the main checkout. The owner
   reinstalls the API and deploy agents once (0044: written by code, installed by the owner); a
   `plists` action keeps comparing and notifying as in 0057.
   **Two roots in `deploy.sh`:** a *tree root* (where it runs from; `deploy-plan`, `deploy-verify`,
   `schedule` and the git moves use that tree's venv) and a *state root* (the main checkout:
   `var/deploy`, `deploy-hold`, `--clear`). Today it resolves everything to the main checkout
   through `--git-common-dir`; R1 splits it. A mid-cycle flip of `current` never changes the
   running `$script`.
8. **What the release tree shares with the main checkout** is only what is git-ignored and
   live: `var/` (data, logs, deploy state), `.env`, `config/users/` and `config/site/*.local.toml`.
   The deployer symlinks them into the tree (`var` -> the main `var`, the others file by file,
   created once and checked each cycle); `.gitignore` gains `/var` and `/config/users` without a
   trailing slash (a slash pattern never matches a symlink). The web build goes outside any git
   path, `var/release/<slot>.web`, and `ALGOTRADE_WEB_DIST` points there. The ingest never reads the tree. Nothing outside
   `scripts/ops/deploy.sh` creates a release tree (`.claude/worktrees/` agents use
   `worktree.sh`, a different thing).
9. **Fit with 0077 blue/green.** A slot is a colour: `var/release/blue` and `var/release/green`,
   each with its own tree, venv, web build and API agent on its own port. The deploy then updates
   the **idle** slot instead of the active one (steps 3 and 4 unchanged, in the idle tree), starts
   it, warms and probes it, flips the proxy and stops the old colour (0077 decision 11; the proxy's
   target is the truth and `current` follows it right after the flip: two files, never one rename); the
   release tree is what makes "old colour keeps serving old code while the new one starts" true
   (two venvs, two web builds). Until 0077 P4 lands there is one slot and step 4 restarts it in
   place (the gap 0057 has today). Both slots cost disk (below).
   **`serve-release --rebuild` (0077 decision 11)** writes a release with ingestion code, and the
   ingest checkout lags, so it can run from neither tree as is: a deploy whose diff changes the
   release format holds until step 5 has brought the main checkout to the target, then rebuilds
   from the main venv under both locks. 0077 P4 owns the gate; this is its constraint.

## Consequences
- A deploy runs within minutes of a merge whatever the ingest is doing; the five-minute skip log
  line disappears for serving. The deploy still serialises with another deploy and with the
  ingest-tree sync.
- Disk (the volume is at 94-96%): a release tree is the source (about the repo), a venv and a
  web build, plus `node_modules` when the web is built there; two slots double it. Phase 1
  measures it, and the deploy refuses with a clear block when free space is under a floor (the
  max of 5 GB and 3x the measured tree), as 0077 decision 6 does for a release.
- Two venvs, so `make doctor` and `make status` read the running version from `/health` (they
  already do) and list both trees' shas; the `cannot lock ref` race goes away.
- The checkout the API runs from is no longer where an agent's `git` commands land: debugging
  the served code means the release tree path.
- Risks: a symlink for `var` makes the tree reach into main's `var/release` (a path cycle, harmless
  to git and to the API, checked by the Phase 1 test that nothing walks `var/`); the API's
  `Path(__file__).parents[4]` constants (`ops/build.py` `REPO`, `main.py` `SEED_PAGES`) resolve to
  the tree, which is wanted; a hard-coded `./var/...` relative to the cwd resolves through the
  symlink; a venv built on another Python than the ingest's is fine (the API pins
  `.python-version` through its own `uv sync`). Measured: the main venv is 376 MB and
  `node_modules` 400 MB, so about 1 GB per slot with source and build (uv clones from its cache).

## Plan (sequenced around ADR 0077)
Every PR `no-automerge` until the owner accepts this ADR; Opus `architect` reviews each (locks,
atomic swap, deploys). Overlap with 0077's phases is in `scripts/ops/deploy.sh` (the restart and
verify block), `apps/api/algotrade_api/ops/deploy.py` (actions, the format gate),
`apps/api/algotrade_api/ops/schedule.py` and `docs/hosting.md`; so R1 lands **before** 0077 P4
touches any of them, and P4 builds on R1's slot functions.

- **R0, this PR:** the ADR and plan (docs only; `needs-owner`).
- **R1, the release tree (Sonnet `implementer`, Opus review):** `deploy.sh` gains `--init-release`
  (owner-run once, **from `refs/deploy/main`** through a temporary worktree, since the main
  checkout is behind and has no R1 code: creates `var/release/blue`, links, venv, web build with
  the current `var/web` assets carried for open tabs, prints the commands; the owner `bootout`s
  the old deploy agent first and installs the API and deploy agents together, else the old agent
  keeps swapping a `var/web` nothing serves); the two roots and the slot functions (`slot_prepare`, `slot_update`, `slot_activate`: the last
  restarts in place, which 0077 P4 replaces by the flip); the private-ref fetch; the cycle takes
  `--deploy-only`; `schedule --agent api --tree`; `deploy-plan --locks` renamed to the
  ingest-sync decision. Tests: the stub-tool temp-repo tests of `deploy.sh`
  (`tests/scripts/ops/`) cover a deploy during a held ingest lock (the regression), the private
  ref beside a concurrent fetch, a clean tree after a deploy, `refs/remotes/origin/main` untouched, `last_sha`, a symlinked
  overlay not showing in `git status`; a unit test for the plan. Acceptance: with an ingest lock held, a diff touching `apps/ingestion` and `config/site`
  deploys.
- **R2, the ingest tree sync (Sonnet):** step 5, `ingest_sync_blocked`, notification once per
  reason, `make doctor` / `make status` lines, the hosting runbook. Can ship with R1 or right
  after; no 0077 overlap.
- **R3, 0077 P4's proxy phase builds the second slot** (`green`): the colours are the slots,
  `current` flips with the proxy; owned by that session, informed here.
- Owner actions: run `deploy.sh --init-release`, reinstall the API and deploy agents once
  (`docs/hosting.md`), bring the main checkout forward (R2 does it on the next gap).
- Out of scope: `make web-check`'s own builds, CI, agent worktrees, a second machine.

## Review
Architect review 2026-10-20: design sound; nine edits applied (refmap, rebuild constraint, ingest-sync range, two roots, plists, symlinks, bootstrap, proxy truth, lock wording). A re-review of R1 is required (locks, format and deploy lifecycle change there).

## Open decisions
None for the owner: the choice of option 2 is the owner's. Judgement calls the architect should
confirm: the opportunistic ingest-tree sync (step 5) instead of a sync at each nightly start, and
the symlinked `var`.
