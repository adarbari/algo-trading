# ADR 0077: The serving release: pages read one immutable, read-optimised snapshot per session

**Status:** proposed (2026-10-19; owner approved the direction the same day; amended
2026-10-21 with the owner-approved decisions 14-22 below, which win over 8, 10 and 13 where
they differ; amended 2026-10-22 (c): decisions 1 and 23 no longer create purpose-shaped
tables, the release pins business objects; amended 2026-10-22 (d): Ideas, only, gets a
derived per-viewer SQLite index (decision 28); design: the
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
1. **A serving release is a derived, immutable snapshot for one session S**: *(amended
   2026-10-22 (c): it holds a session record and a manifest, and pins stored business objects;
   it copies no read object, see the amendment below. The text that follows is the original
   wording, kept for the record where (c) does not replace it.)* the session record, stable
   additive schemas, a `format` version and a manifest (S, the build seq X, input tables and partitions with their
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
   disagree). `Session.newer` gains `PUBLISHING` (complete, release not yet promoted; disclosed only after `serving.publishing_delay_minutes` (site config, default 15; owner decision
   2026-10-19), counted from the `finished_at` of the run record that made S complete; the
   server computes a `publishing` flag with a time bucket in the key so the cached answer
   flips, never the browser, ADR 0038) with a
   Guide term (ADR 0051). `newer` and `complete` stay live from the nightly and post-session
   run records through a new `workflow_generation` (excludes job checkpoints); only
   `StatusStrip` and `SessionDate` key on it, and `served_token` leaves every other key.
8. **What does not come from the release** (*correction*: `visible_seq` leaves every
   default-session page key, not every key): user expression features (evaluated over the
   pinned feature store), the user's on-request screen runs (ADR 0033, composed with the
   pinned `results/screen_picks`; keyed by user and runs generation), admin ops pages (live; a lane capped at a thread count the plan sets), live quotes and usage logs, Builder previews (pinned per 3), and an explicit
   date other than the release's (ADR 0036). These keep their keys. (*Amended by 14*: the
   list of live keys is inverted into an allow-list of release-shared operations; a live key is
   never listed.)
9. **Roles and licences.** The pinned reads carry every name with its licence and the full `Cause`
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
    The proxy and colour plists are written by code and installed by the owner (0044); stopping
    a KeepAlive agent uses `launchctl bootout`. `SO_REUSEPORT` is rejected (BSD semantics, no control over when traffic moves); warm-before-
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
- A page can show data a day old, and shows `PUBLISHING` when promotion is later than the delay after COMPLETE.
- A new derived artifact (50-250 MB, three kept, about 1% of the store) and a new job to run.
- Risks: a pinned history-copy read leaking a later version (decision 2); missing data cast to
  zero in Arrow (tests with a missing table); non-deterministic row order (sort before write).
- Owner decisions 2026-10-19: r2 is promoted after post-session; ceiling 300 MB and floor
  max(5 GB, 3x the last release); blue/green through a front proxy. `PUBLISHING` is shown only after the configured delay (default 15 minutes)
  without promotion, in a neutral tone (the exact words are Guide content, ADR 0051). No
  owner decision is open.

## Amendment 2026-10-21: stale is never an option, slow is
Measured 2026-10-21: the keys carry `visible_seq`, so each ingest publish (the filing-text
backfill, every ~13 min) empties every API cache; one cold read took ~100 s on one core
(GIL-bound, starving `/health`); each deploy restart (every 10-30 min) does the same. With the
backfill paused for 20 min the same site was fast (warm p99 <= 0.11 s, 785 MB RSS). The machine
(10 cores, 16 GB, swap 5-7 GB) is shared with ingests and compaction. The owner approved on
2026-10-21 the safe way: the release (1-13) plus the following, built in the order of 21.

14. **Deny by default (inverts 8).** An operation is served from the release only if it is
    listed in the release-shared allow-list `architecture/release_shared_ops.toml` (a
    shrink-never-silently list: an entry needs a reason and the test of 17). Every other
    operation, above all every per-user one, reads live and **uncached**, unless it is in
    `SHARED_OPERATIONS` (keyed by the published state) or a user-keyed group (15). The old `live_read_keys.toml` idea (an allow-list of live keys,
    where a forgotten entry serves stale data) is dropped. A forgotten entry leaves a page
    slow, never stale. `response_cache.cacheable` already defaults to not cached; the
    allow-list keeps that default and extends it to the release. Of today's four groups:
    `SHARED_OPERATIONS` not on the allow-list stay cached in process, keyed by the published
    state as now, until P3 moves them; `USER_OPERATIONS` are keyed by 15; `RUN_OPERATIONS`
    read live run records and are never release-shared (16); `NEVER_CACHED` stays so.
15. **One writer, one version.** The owner of the per-user `config_generation` is
    `storage/configs` (ADR 0006: only it builds the path; the counter lives under
    `config/users/<id>/`, durable, never process memory) and is a seqlock: made odd before
    the first rename of a write and even after the last, and while it is odd nothing is
    cached (a crash between leaves it odd, so nothing stays cached under a half-written
    config until the next write or a repair on start). Every user write goes through the
    `ConfigWriter` Protocol (`storage/configs/writer.py`, called by `services/authoring`);
    both `FileConfigWriter` and `MemoryConfigWriter` bump it, `ConfigStore.generation(user)`
    reads it, a contract test covers both, and a fitness test forbids any other writer under
    `config/users/`. Order: the counter is made even **after the last config file of the write
    is durably renamed** (two files cannot change atomically; the other order would let a
    reader pair the new generation with the old config and cache it for good), and a key
    reads the generation before the answer is computed (the `visible_seq` rule, ADR 0022).
    CLI and hand edits that skip the routes must go through `ConfigWriter` too, else the
    stale-while-revalidate TTL is their only bound and the CLI says so. This replaces the
    process-local `WriteEpoch` / `CountWrites` middleware (lost on restart, invisible to a
    green process, skipped by routes outside `WRITE_PACKAGES`). Every user-keyed key **adds**
    `config_generation` to its existing parts (role, ADR 0056; licences, ADR 0069; served
    session, ADR 0062; runs generation where it applies) and all keys are built in the one
    `response_key` function (a fitness test forbids another key builder outside it and the
    loaders' `ResultCache` helpers). Site config changes arrive with a deploy, as today.
16. **Run state.** `runs_generation` is the store's, not per user (it moves on every saved
    run record, job checkpoints included). On-request writes that are not configs (a screens
    run, ADR 0033; an edge `evaluate`) save a run record and so move it; the gate of 17
    covers them; the run record is saved after the result files are durable, the same rule as in 15. `RUN_OPERATIONS` read live run records and are never release-shared; P3
    limits their churn (checkpoints) or declares it, since today it cools them on every
    ingest job. That is slow, not stale.
17. **The read-your-writes gate.** A fitness test enumerates every write route (PUT, POST,
    DELETE) of the OpenAPI document and requires, per route, either an entry in
    `architecture/read_your_writes.toml` naming a test (the counter and both new governed files need ownership and layout entries in the P2 PR), or a reason it is not persistent
    (Builder previews, draft-from-text, regime explain). The named test warms the cache against the
    published store (P3 extends it to a release in place), writes through the real route, reads the affected GraphQL operations
    and asserts the change shows (create, edit and delete). About 17 routes today: screeners
    delete, draft put and delete, finalise, copy, rebase; screens run; edges copy, put,
    delete, state, evaluate; user features; preferences ideas and views put and delete. A new
    write route without an entry fails CI, the same pattern as `rest_allowlist.toml`
    (shrink-only for the exemptions). It lands before the release exists (21).
18. **Client cache.** The web app has its own page cache (the page-cache chunk, TanStack
    Query). Responses carry `release_id` and `config_generation` (an "as of", also shown
    where the page shows its session). After a write the web app invalidates by the new
    generation; it derives nothing (ADR 0038). A small separate web PR (add-web-page skill,
    component-only layering); the web/network session owns route preloading and payload
    shaping, this ADR owns the version contract.
19. **Shadow comparison (optional, before the cutover).** For user-keyed operations the
    server may compute the release-served and the live answer, log differences (counts, never
    contents with user data) and serve the live one. Off by default; its result is recorded in
    the PR that flips an operation into the allow-list.
20. **Resources, as measured or estimated** (a doctor line each where a number is checked):
    - A release is 50-250 MB (estimate; the ceiling stays 300 MB), three kept, <= ~0.75 GB,
      ~1% of the store (52 GB in `var/data/tables`; the disk has 39 GB free of 228 GB).
    - A second release-tree slot (ADR 0079) is ~1 GB.
    - The retained store versions a release pins (3) are **not sized yet**: PR P3 measures
      the disk they hold (partition versions named by retained releases beyond the live
      index) and adds a `make doctor` line with a warning threshold.
    - Memory: a blue/green flip runs two API processes at once (+1-2.5 GB for minutes), so
      the flip runs only when no ingest or compaction runs, or after the new colour's warm
      completes; the deploy planner checks the same `doctor` memory gate. Pre-built page
      payloads are tens of MB per session (persisted cache, 12).
21. **Ingest isolation is its own item and comes first.** Ingestion and compaction run at
    background priority (`taskpolicy -b` where available, else `nice`), with worker and
    memory caps, so the API keeps its CPU (PR #734 started this; this item extends it and
    tests it: a unit test over the launch wrapper's argv and a test that every ingest
    entry point goes through it). Order of the code PRs, each small, naming first the test
    that would have caught the problem: (1) ingest isolation; (2) deny-by-default keys,
    `config_generation` and the gate of 17, **before the release exists**; (3) release
    build and promote, pages reading CURRENT instead of `visible_seq`; (4) the persisted
    payload cache and the separate low-priority warmer (12); (5) the blue/green front proxy
    and the flip, with ADR 0079 R3 (the colours are the release-tree slots; the deploy
    planner also stops restarting the API for changes it does not load, such as
    ingestion- or backtest-only source files).
22. **Acceptance (amends 13).** A writer-mode load test (`scripts/perf/load.py
    --writer-store --writer-cmd`) holds the page p95 criteria while an ingest publishes every
    few minutes, and a deploy shows no cold site; the read-your-writes gate is green; no stale
    answer after create, edit or delete in the tests. Load runs are by hand, with the
    backfill paused.

Owner decisions 2026-10-21: 14-22 as written; no owner decision is open.

## Amendment 2026-10-21 (b): the first release is a pin
The architect's design note (shared notes folder, `release-design-note.md`) found that pages are
slow because every loader key reads `visible_seq()` (`services/read/context.py`, `screens/hits.py`,
`instruments/*`, `regime/*`), not because pages lack precomputed tables. So the order of the
code PRs is refined (21's order stands for (1)-(3); (4) the separate warmer and (5) the proxy are deferred by 24):

23. **Format F1 is a pin.** The first release is a manifest `{release_id, session S, seq X,
    destructive_epoch, code_sha, inputs, content_hash}` plus the session record
    (`session.parquet`); default-session reads go through `StoreReader.pinned(X)` and every
    loader key holds `StoreReader.version()` (`("pin", X)` or `("live", visible_seq())`) instead
    of `visible_seq()` (a fitness test bans `visible_seq()` under `services/read`). *(Replaced by
    amendment (c): no purpose-shaped tables. Read-optimised derived data is stored as business
    objects in the existing homes and the release pins them; the deploy-time format rebuild gate
    waits for the first release format that carries a table other than the session record.)* A format mismatch falls back to live.
    - **Pinned reads** take `upto` on `TableStore.read/read_range/read_run/dates/partition_seq`;
      with `upto` set a read never retries at a fresh seq and raises `StaleSnapshotError`;
      `dates(upto)` drops partitions with no version at or below it.
    - **Retention (supersedes 3's protected `partition_seq` sets and its `promote` existence check;
      the pin floor and `destructive_epoch` replace them):** `TableStore.pin / unpin
      / pins` (durable, read under the commit lock); the version chain of a partition keeps every
      version some pin sees (at most pins + 1 long), honoured by `_referenced`, `_discard` and
      `drop_unreferenced`. `purge`, `remove_runs` and `drop` are not protected: each bumps a
      durable `destructive_epoch`, a release whose epoch differs is invalid and reads fall back
      to live (never a silently empty page).
    - **Release retention (amends 5):** keep CURRENT, the newest release of each of the last two
      sessions, and live drafts.
    - **Build rules:** a release is also rebuilt when an input's `partition_seq` moved (a restated
      or backfilled current session), not only for a new session; `begin` pins a provisional X
      and records the epoch before any read; the run records (`complete`, `cutoff`) are read
      before X is taken and are not pinned (a COMPLETE record is saved after its commits).
    - **Amends 11 and 12:** the deploy-time rebuild gate waits for the first release table beyond the session record;
      until then the API warms on promote inside the process.
    - **Fallback (today's path exactly, answer not cached):** no CURRENT, unknown format, hash or
      epoch mismatch, `StaleSnapshotError`, or the kill switch `serving.release_reads = false`.
    - **First family:** the role-only `SHARED_OPERATIONS` over stored tables (prices, market
      history, events, holdings, regime) read CURRENT, keyed `(release_id, role, document,
      variables, licences)`; the allow-list `architecture/release_shared_ops.toml` (reason plus
      test per entry) is introduced then. User operations keep `config_generation`, run operations
      their runs generation, as in 14-16. The CI test promotes a release, warms, makes commits
      (a next-session partition, a same-run restatement, a job checkpoint, an old-date
      filing-text commit) and asserts zero recomputes and byte-equal bodies.
24. **Deferred, not dropped.** The front proxy and blue/green (11), the separate warmer process
    (12) and shadow comparison (19) stay owner-approved but come after the pin has been measured
    under the writer-mode load test: a warm-on-promote plus a persisted response cache keyed on
    `release_id` (which survives restarts) may remove most of the need, and the deploy planner
    stops restarting the API for changes it does not load. Each is built if the writer-mode load test misses the read-model criteria (page p95 > 2.5 s,
    `/health` p99 >= 250 ms, `docs/api/read-model.md`), or the cold page p95 within 5 minutes of a
    deploy is above 1 s (the owner's cold-load goal; threshold proposed here, the owner may set
    another).

Owner decision 2026-10-21 (logged in `docs/decisions/log.md`): "try the pin first approach and
measure the impact"; the deferral in 24 is revisited with the load-test numbers.

## Amendment 2026-10-22 (c): the release pins business objects, it never copies them
Owner decision 2026-10-22 ("The domain tables look good. Let us go with them", logged in
`docs/decisions/log.md`, "Domain-aligned derived data"). Design: the architect's
`domain-derived-data.md` (shared notes folder), which replaces the page-shaped cards.

25. **Replaces decisions 1 and 23 where they name purpose-shaped Parquet tables (picks,
    Explore facts, feature frame, home, ideas, edge desk).** Read-optimised derived data is
    stored as business objects, each at its natural grain and key, written by its owner in an
    existing home: a feature group (ADR 0023), a `results/` table (ADRs 0022, 0053) or a run
    record. The release **pins** them (`StoreReader.pinned(X)`) and never copies them: no
    release-held read object, no second implementation of a loader, no per-read input seq
    check. The page shape (composition, projection, limits, pagination) is made on read in
    `services/read`. A table that only one page could ever read is a page table and is
    rejected.
26. **Planned homes (the build PRs add them, each with its `architecture/tables.toml` entry
    and owner; nothing exists yet):**
    - `results/screen_runs` (ScreenRun, one row per screener run) and `results/screen_picks`
      (ScreenPick, a run's picked and paused instruments), written by the screen's own writer
      in the same atomic publish as `rule_screen` (ADR 0022);
    - `market.macro_asof@v1`, a market feature group, built only if profiling shows the regime
      provenance read is most of the regime page cost;
    - `results/edge_verdict` (the EdgeVerdict headline, ADR 0053 amendment 2026-10-22), a
      business object read by the edges list and the follow check `verdict_level`, so not a
      page table; written by the edge-eval run's publish and the `edge-verdicts` task, and
      read only on a fingerprint match (else judged live).
27. **Decision 16 stays unchanged:** run operations are not release-shared and keep the
    runs generation; the results tables (`screen_runs`, `screen_picks`, `edge_verdict`) make them
    fast enough live. ADR 0005 and the
    writers line in `CLAUDE.md` do not change (the on-request run already writes `results/`,
    ADR 0033).

## Amendment 2026-10-22 (d): Ideas gets a derived per-viewer index (owner exception)
Owner decision 2026-10-22 (logged in `docs/decisions/log.md`, "Ideas ranking rule, store and
licence (confirmed)").

28. **Decision 25's rejection of a one-page table does not apply to Ideas.** The Ideas list
    is a per-viewer ranking (weight / position, site top 5 at weight 1, the viewer's own
    screeners top 20 at weight 3; an idea is its ticker's best pick score), stored as pointers
    and ranks in one SQLite index (ADR 0006 amendment 2026-10-22), written by the nightly
    `ideas` step and by the API after an on-request run (ADR 0005 amendment), stamped with
    `source_seq`, `screeners_hash` and `rule_hash`, with a live fallback. It is built only
    after the rule and smaller-response loader PRs and their re-measure. Every other page
    stays under decision 25. Decision 16 stays: IdeasPage is a run operation, never
    release-shared, and the index is not in the release manifest. For Ideas this supersedes
    the last sentence of decision 27 (ADR 0005 and the `CLAUDE.md` writes line change, by
    their amendments of the same date).
