# Serving release: phased plan

Decision: [ADR 0077](../adr/0077-serving-release.md) (proposed 2026-10-19). Goal: page reads
never depend on ingestion commits, so the site stays fast during the nightly; data up to a day
old is accepted. Every PR is `no-automerge`; the model tier is the executor's (CLAUDE.md
"Agents, models and tokens"); **Opus `architect` reviews every PR from P2 on** (atomic publish,
pinning, locks, deploys).

## P0: quick wins (another session; Sonnet `implementer`)
- Owner: `apps/api/algotrade_api/graphql/{warm,offload}.py`, `scripts/perf/load.py`, `make doctor`.
- Scope: a warm pool outside `READ_THREADS` at lower priority; the edge-desk warm failure; a
  free-space check in `make doctor`; `StatusStrip` / `SessionDate` keyed on a
  `workflow_generation` (excludes job checkpoints); a `nightly-writer` scenario in `load.py`;
  the commit-storm test `tests/apps/api/graphql/test_cache_survives_commits.py` (xfail with a
  reason until P3).
- Acceptance: the storm test exists and fails only for the known keys; `make doctor` warns
  under the floor. Architect reviews the generation split.

## P1: the ADR (this PR; Opus `architect` drafted and reviewed, Sonnet landed)
- Files: `docs/adr/0077-serving-release.md`, amendment notes in 0005, 0022, 0057, 0062, this
  plan, the roadmap line. Follow-ups with the code: `CLAUDE.md` Writes and Reads lines (done in this PR), `docs/data/storage.md` section,
  `docs/api/read-model.md` (Performance rules 2), the `PUBLISHING` Guide entry (`add-guide-content`).
- Acceptance: `make numbering`, docs layout tests; owner accepts or amends the ADR.

## P2: session record and picks-by-instrument (Sonnet `implementer`; Opus review each PR)
- PR a, storage: `storage/backends/release/{local,memory,manifest}.py`, `ReleaseStore`
  Protocol, `StoreReader.pinned`, history-copy `upto` rule. Acceptance: contract tests
  `tests/contract/storage/releases/test_releases.py`; the versions of every retained and the in-flight release survive two recommits, and a promote whose version vanished rebuilds (failed seal invisible, atomic promote, prune,
  pinned read plus stale restart, history copy under `upto`). Ownership: `serving-release-store`.
- PR b, build: `services/serving/`, `workflows/serve_release/` writing `session` and
  `picks_by_instrument` (from `screens/hits.py`, `pick_history.py`); size and free-space checks.
  Acceptance: two builds give equal bytes; `tests/architecture/serving/test_release_inputs.py` (new subfolder: the folder caps), an import-linter contract for `services/serving` (no `data/outcomes`) (inputs
  are stored tables, no `own_run`, manifest seq at most X). Ownership: `serving-release-build`,
  `serve-release-job`; the nightly and post-session start it.
- PR c, API: `data/serving/` and the `services/read` hook (`context.py` session, `hits.py`),
  falling back to the store path with no release or an unsupported format. Acceptance:
  `tests/unit/services/serving/test_release_equivalence.py` (release answer equals the store
  answer pinned at X).

## P3: remaining page reads, remove the fallback (Sonnet, one area per PR; Opus reviews key removal and the 0062 change)
- Areas: ideas, edge desk, Explore facts and feature frame, regime, completeness for S; store
  reads pinned at X and keyed on `release_id`; `PUBLISHING` state, its Guide entry, `guide_coverage.toml`, the `schema.graphql` snapshot and the web `SessionDate`.
- Then remove the cached store path (no release serves from the store uncached, ADR 0077 decision 5) and `visible_seq` / `runs_generation` / `served_token` from
  default-session keys. Acceptance: `tests/architecture/api/test_page_keys.py` (AST scan of
  `ctx.cache` keys; exceptions only in shrink-only `architecture/live_read_keys.toml`); the
  storm test turns green and becomes the CI gate; `make load` with `nightly-writer` meets the
  p95 rule (run by hand, numbers in the PR).

## P4: serving operations (Sonnet implementer after an Opus design note; Opus reviews all)
- Files: `apps/api/algotrade_api/serving/` (persisted cache, `algotrade-api warm` process),
  `ops/deploy.py` (format gate, `--rebuild`, blue/green).
- The warmer warms shared role keys only (0056); the admin lane's thread cap is set here.
- Order: persisted cache and warmer; warm-before-swap on promotion; format gate; then the
  front proxy (its own launchd agent on 8000, blue and green API agents on two ports, flip after
  a health and latency probe, drain, stop; `docs/hosting.md` runbook; retargeting nothing in
  Funnel).
- Acceptance: tests in `tests/apps/api/ops/` (the format gate holds, a failed probe keeps the
  old process, the deploy plan); `make load` during a simulated promotion.

## Owner decisions
Decided 2026-10-19: r2 after post-session; size ceiling 300 MB and free-space floor
max(5 GB, 3x the last release); blue/green through a front proxy. `PUBLISHING` is shown only after about 15 minutes
without promotion, neutral tone (Guide entry in P3). None open.
