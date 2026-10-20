# ADR 0077: The serving release: pages read one immutable, read-optimised snapshot per session

**Status:** proposed (2026-10-19; owner approved the direction the same day; design: the
architect's memo, which corrected four points of the first sketch, marked below). Amends
[0022](0022-atomic-run-publication.md) (a pinned read of the history copy, a build-wide pin and retained versions), [0060](0060-history-copy.md) (how the copy serves a pinned read), [0044](0044-hosting-from-the-owners-mac.md) (a second port, blue/green),
[0062](0062-reads-serve-the-last-complete-session.md) (the default session is the current
release's), [0005](0005-ingestion-is-the-only-writer.md) (a persisted response cache is an API write; ingestion
writes releases) and [0057](0057-auto-deploy-from-origin-main.md) (a format gate, blue/green). Plan:
[docs/api/serving-release-plan.md](../api/serving-release-plan.md).

## Context
While the nightly runs, the site is very slow. Every ingestion commit moves `visible_seq`
(`storage/backends/local.py`, `commits.published()`) and the runs generation, and both sit in
nearly every key: the GraphQL response key (`graphql/response_cache.py` `response_key`) and the
loaders' `ResultCache` keys (`services/read/context.py`, `screens/hits.py`,
`instruments/{table,series,identity,chains}.py`, `ops/ingestion.py` and more). Each commit
therefore empties the caches, and the warmer (`graphql/warm.py`) re-warms in the same pool the
requests use. The owner accepts data up to a day stale and wants fast loads always.

## Decision
1. **A serving release is a derived, immutable snapshot for one session S**: small
   purpose-shaped Parquet tables (session record, picks by instrument, per-instrument Explore
   facts and feature frame, home, ideas, edge desk), stable additive schemas, a `format`
   version and a manifest (S, the build seq X, input tables and partitions with their
   `partition_seq`, row counts, content hash). It is not serialised GraphQL. Id
   `"{S}.{X}.f{F}"`. **It is a derived cache like the history copy (ADR 0060: dropping it
   loses nothing), not a second source**, so 0005 and 0007 stand; rows keep `knowledge_ts`,
   `source`, `run_id`, `licence`. Determinism is tested (two builds, equal bytes).
2. **Exactness (amends 0022).** "A release equals a pinned read at X" holds only if the build
   reads at X. Today every read pins its own fresh seq, so a multi-table build would mix
   sequences. Add `StoreReader.pinned(seq)` (every read passes `upto=X`); a partition
   recommitted twice during the build raises `StaleSnapshotError` and the build restarts at a
   new X (a bounded number of tries); at seal the build verifies no input partition's seq passed X.
   The build runs under its own `exclusive_run(name="serve")`, **not** the ingest lock (that
   would make the restart dead code, block post-session and the hourly retry, and deadlock when
   the nightly starts it: the nightly enqueues the job after it releases its lock). The history copy built after X serves a pinned read only when every
   requested day's `partition_seq <= upto`, else partitions (its signature rule alone could
   leak a restated older partition).
3. **Reads not in the release are pinned the same way.** Series, chains and every other
   default-session store read use the current release's X and key on `release_id`; S+1
   partitions are invisible at X; a stale pin falls back to the live seq and that answer is
   not cached. **The versions a pinned read names are retained**: the index keeps only one older
   version per partition, so the `partition_seq`s named by every retained release and by the in-flight one (recorded
   at `begin` with X) are protected (prev-drop and purge skip them) until the release is pruned,
   and `promote` checks they still exist, else the build is redone (the ingest writer's
   prev-drop holds the ingest lock, not `serve`, so the guard is the index, not a lock); without this a pin at X fails after two
   recommits and every series read would recompute through the nightly. Time series stay in stored tables; a release never copies history.
4. **Who builds (amends 0005).** Ingestion only, as its own job `serve-release` with its own
   run record, **not the nightly's last step** (*correction*): ADR 0062 defines the session by
   the nightly's COMPLETE record, saved after the last step; ADR 0070 forbids a late step that
   writes session-bound tables; a failed release must neither hold back sessions (0039) nor
   trigger the hourly retry. The nightly starts it after COMPLETE; `post-session` starts it
   again at its end (**release r2 of the same S**, so the edge desk's evaluation arrives the
   same day; *correction*: one release per workflow that changes served inputs, not per
   nightly); the post-session watchdog retries a missing release. `algotrade-ingest
   serve-release [--rebuild]` is the manual and deploy entry. Weekly `reference` and
   `enrichment` commits arrive with the next release.
5. **Promotion.** Build -> validate (acceptance checks below) -> warm -> `promote`: one atomic
   write of `serving/CURRENT` (temp file, fsync, `os.replace`, directory fsync) after `seal` has
   fsynced; CURRENT holds `release_id` and the manifest hash, which readers verify. Readers
   resolve CURRENT once per request and retry once if the release vanished (pruned). A failed or partial build is invisible;
   pages keep the older release (fail closed and stale, which the owner accepts) and the alert
   fires. Retention: the current release, the last release of the previous session, and the
   one in flight; older deleted, orphans pruned. Releases live on the volume of `var/data`.
   **No release** (none promoted, an unsupported format, or a vanished one after P3 removes the
   fallback): the 0062 rule serves from the store, uncached and disclosed. `--rebuild` builds the
   latest complete session.
6. **Acceptance checks:** schema matches the format; every expected table present; row counts
   at or above the universe floor; no input seq past X; **size at most the ceiling (300 MB)**;
   **free space before the build at least the floor (max of 5 GB and 3x the last release)**
   (the disk is at 94-96%).
7. **Which session is served (amends 0062).** The default session is the current release's
   session, not the latest complete one (else S+1 is complete but unreleased and pages
   disagree). `Session.newer` gains `PUBLISHING` (complete, release not yet promoted) with a
   Guide term (ADR 0051). `newer` and `complete` stay live from the nightly and post-session
   run records through a new `workflow_generation` (excludes job checkpoints); only
   `StatusStrip` and `SessionDate` key on it, and `served_token` leaves every other key.
8. **What does not come from the release** (*correction*: `visible_seq` leaves every
   default-session page key, not every key): user expression features (evaluated over the
   release's feature frame), the user's on-request screen runs (ADR 0033, composed with the
   release's preset picks; keyed by user and runs generation), admin ops pages (live; a lane capped at a thread count the plan sets), live quotes and usage logs, Builder previews (pinned per 3), and an explicit
   date other than the release's (ADR 0036). These keep their keys, listed in the shrink-only
   `architecture/live_read_keys.toml`.
9. **Roles and licences.** The release stores every name with its licence and the full `Cause`
   chain; the API filters by the viewer's licences (0069) and redacts causes for non-admins
   (0056). Nothing is pre-rendered per role; a missing value is null with its kind and reason.
10. **Cache keys:** `(release_id, operation, variables, role, user if not shared, licences)`.
    The build id is in the key of a persisted cache only (an in-process key dies with the
    build). A persisted cache is an API write (0005) and its path comes from
    `storage/backends` through a `services/read` facade.
11. **Formats and deploys (amends 0057).** Each API build declares `READS_FORMATS`; changes
    are additive by default (a new nullable column keeps F). The deploy gate compares them with
    CURRENT, then runs `serve-release --rebuild` (current code, no re-ingest) under
    `deploy-hold`, or holds; it never rolls back. Blue/green: the new process warms from the
    current release on a second port and takes traffic only after a health and latency probe;
    the old one stays if the probe fails. The same warm-before-swap applies on promotion.
    **Mechanism (owner decision 2026-10-19): a small front proxy**, its own launchd agent on
    127.0.0.1:8000 (Funnel's fixed target, 0044, unchanged), forwarding to the blue or green API
    agent on its own port; the deploy starts the idle colour, warms and probes it, flips the
    proxy's target atomically, drains the old colour, then stops it; a failed probe never flips.
    `SO_REUSEPORT` is rejected (BSD semantics, no control over when traffic moves); warm-before-
    restart is rejected as the end state (a gap, no probe-gated rollback). The proxy is a single
    point of failure kept alive by launchd, with no logic beyond forwarding and the flip.
12. **The warmer is a separate process** (it warms shared role keys only, never per-user or admin-cause answers, 0056) (`algotrade-api warm`) writing the persisted cache the
    API reads (*correction*: a separate process cannot fill the API's in-memory LRU, so it
    only helps with the persisted cache). Until then a dedicated one-thread warm pool outside
    `READ_THREADS` at lower priority; nice / Background I/O caps are a backstop, not the fix.
13. **Latency is a gated invariant.** CI gates a deterministic one (*correction*: a p95 on
    GitHub-hosted runners is noisy): under N concurrent commits, zero recomputes of
    default-session page operations (cache misses counted). `make load` gains a
    `nightly-writer` scenario, run by hand, keeping the p95 criteria of
    `docs/api/read-model.md` (Performance rules).

## Ownership and layout (entries ship with the code PR that adds each, as `add-responsibility` requires)
`serving-release-store` (`storage/backends/release/`, Protocol `ReleaseStore`: begin, write,
seal, promote, current, open, prune, free_bytes), `serving-release-read` (`data/serving/`),
`serving-release-build` (`services/serving/`, pure shapers over the existing `services/read`
loaders at a pinned context: no second implementation of a page), `serve-release-job`
(`workflows/serve_release/`; an import-linter contract keeps `services/serving` off
`data/outcomes`, ADR 0053: edge-desk data only through the `services/read` loaders), the API's `serving/` folder (persisted cache, warm process, `front-proxy`);
extend `session-resolution`. Five folders declared in `architecture/layout*.toml` with test
mirrors. No `tables.toml` entry: a release is not a stored table, as `_history` is not; a
fitness test requires release inputs to be stored tables, never `own_run`.

## Consequences
- Page reads stop depending on ingestion commits; a night of ingestion changes no key.
- A page can show data a day old, and shows `PUBLISHING` between COMPLETE and promotion.
- A new derived artifact (50-250 MB, three kept, about 1% of the store) and a new job to run.
- Risks: a pinned history-copy read leaking a later version (decision 2); missing data cast to
  zero in Arrow (tests with a missing table); non-deterministic row order (sort before write).
- Owner decisions 2026-10-19: r2 is promoted after post-session; ceiling 300 MB and floor
  max(5 GB, 3x the last release); blue/green through a front proxy. Open: the wording of
  `PUBLISHING` (proposed: shown only after about 15 minutes, neutral tone).
