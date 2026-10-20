# API memory: why the process swells to 15-36 GB, and the path to about 1 GB

Measured 2026-10-20 on the owner's 16 GB Mac (store session 2026-10-19), without touching the
live API: a separate process from this tree, the API's own Arrow caps (`ARROW_CPU_THREADS=2`),
the real store read-only, a footprint watchdog (`footprint -p`, killed at 3.5-5 GB), niced.
Scripts and logs: the session's scratchpad (`prof_warm.py`, `prof_read.py`).
Related: [ADR 0077](../adr/0077-serving-release.md) (serving release, persisted warm cache),
[ADR 0078](../adr/0078-outcomes-run-compaction.md) (run compaction), `docs/perf/api-latency-baseline.md`.

## What was observed

| Observation | Number |
|---|---|
| Live API, 5 min after a restart (pid 11399, an outcomes ingest running) | footprint **36 GB**, 35 GB compressed, RSS 0.67 GB |
| Live API, 2.5 h after start (owner, earlier) | footprint 15 GB, 14 GB compressed, swap 7.2 of 8 GB |
| Harness, API start + `home_steps` | passes 4.3 GB within 5 s of the `screen rows` step, then 5.4 GB in the `screener hits` step (watchdog stops) |
| Live API log | `warming the home page took over 60 s: serving anyway` 153 times |

RSS reads small because macOS compresses the cold anonymous pages: the footprint is memory that
was allocated, touched and then kept (freed to the allocator, not the OS, or still referenced).

## Root cause, in order of size

**1. A session partition of `results/rule_screen` is 940 run files and 12.6 million rows; every
read decodes all of them, merges, and keeps one tenth.**
`services/read/screens/runs.py` `screen_rows` -> `partition()` -> `table_range` ->
`LocalBackend._partition`: a `merge` table reads *every* run of the partition (`select_runs`),
`concat`s them in Arrow, `merge_rows` (latest run wins per key), then `to_frame`. The session
2026-10-19 holds 112 screen configs with up to 10 runs each (reruns and backfills; nothing
compacts them: ADR 0078 covers the outcomes tables only), 12,583,498 rows, 1.4 GB of it the
`reasons` column uncompressed. Measured on a 60-file sample: 352 MB decoded -> 80 k rows merged
(x0.1); scaled to 940 files: **about 5.5 GB decoded, a peak near 8 GB** (the 7.7 GB seen 72 s
after the restart), 1.26 M rows (542 MB) kept. A consumer then picks only each config's newest
run (`last_run_rows`): the nine older runs are read for nothing.

**2. `results/rule_screen_values` is the same shape, larger.** `_read_values` (screener hits,
Ideas, results pages) reads the session's 941 files (620 MB compressed, about 25 M rows) with
only the instrument filter applied after decode; the harness was stopped at 5.4 GB inside it.

**3. The result cache cannot hold what the loaders put in it, so entries are recomputed.**
`ResultCache` is bounded to 400 MB (`MAX_CACHE_BYTES`) and keeps "the newest entry even when it
alone is over the bound"; the merged `rule_screen` frame weighs 542 MB. The next `put` evicts it.
`load_run_changes` then reads the *previous* session's partition once per run (112 times in a
home warm), alternating two 8 GB-peak reads: `rule_screen` was computed four times in the first
30 s of the harness. Every ingestion commit moves `visible_seq` and every key (ADR 0077 context),
so this repeats after each commit, in the read pool's 6 threads at once.

**4. `run_rows` copies the whole frame per request.** It sorts the 1.26 M-row frame and splits it
with `groupby(...).reset_index` into 112 per-run frames, memoised in `ctx.memo` (per request):
about 1 GB of transient copies for every request that touches a screener, concurrently.

**5. The allocator keeps freed memory.** Arrow's default pool here is mimalloc (`jemalloc` is not
built). On the 60-file sample the peak was 811 MB, **811 MB after everything was freed**, 697 MB
after `release_unused()`. With `ARROW_DEFAULT_MEMORY_POOL=system`: peak 810, **399 MB after
free, 183 MB after `release_unused()`**. `release_unused` is only called when the cache evicts.
After the harness's `ideas` step the cache held 94 MB while the footprint was 2.3 GB.

## Where each GB goes (full session, home warm, API caps)

| Item | Bytes | When | Owner |
|---|---|---|---|
| Interpreter, imports, GraphQL schema, configs | 0.3 GB | steady | `apps/api` |
| `rule_screen` decode of 940 files + merge temporaries | 5.5 GB decoded, ~8 GB peak | warm-up, then each publish / eviction | `services/read/screens/runs.py`, `storage/backends/local.py` |
| `rule_screen` merged frame held | 0.54 GB (cap 0.4) | steady, evicted by the next put | `ResultCache` |
| `rule_screen_values` decode (941 files) | over 3.4 GB (stopped at 5.4 GB total) | warm-up (`screener hits`), per publish | `screens/results.py` |
| Previous session's `rule_screen`, once per run | repeats of row 1 | warm-up, per publish | `load_run_changes` |
| `run_rows` split copies | ~1 GB per request | per request | `screens/runs.py` |
| Retained freed pages (mimalloc) | peak minus live, up to all of it | steady (the 14 GB compressed) | `arrow_memory.py` |
| Regime, ideas, completeness reads | +0.6, +1.0, 0 GB footprint (cache 94 MB) | warm-up | read model loaders |
| `ResponseCache` | 100 MB cap (gzip bytes) | steady | `graphql/response_cache.py` |
| Thread stacks, Arrow IO/CPU pools | under 0.1 GB | steady | `main.py` caps |

The 36 GB is these peaks overlapping across the six read threads, repeated per eviction and per
commit, with the freed pages never returned.

## Path to about 1 GB steady

Budget: 0.3 interpreter + 0.3 caches (real bytes) + 0.3 transient decode + 0.1 headroom.

**P0, now, no semantic change (own PR, below):**
- `ARROW_DEFAULT_MEMORY_POOL=system` for the API process (set before `pyarrow` is imported) and
  `release_unused()` after every warm step: freed pages go back to the OS. Peak unchanged,
  retained -> near zero.
- A warm ceiling and a `make doctor` line for the API footprint (guards below).

**P1, architect review first (changes which rows a read decodes, not its answer):**
- Read only the newest run of each (user, config) for `rule_screen` and `rule_screen_values`
  (the run rule `last_run_rows` applies anyway): about x0.1 decode, 8 GB -> under 1 GB peak,
  measured in the harness with the newest-run prototype (screen rows: 0.31 -> 0.77 GB footprint,
  1.1 s instead of the >5 s). Needs a backend read of named runs (`read_run` exists; the list of
  newest runs comes from the run records, not from the rows).
- Stop the previous-session read per run: read the previous session's rows once for all runs.

**P2, loaders:**
- Cache budget by real bytes (Arrow `nbytes` plus strings, not `weigh`'s estimate) with a cap
  above the largest entry, or shard the frame per config so no entry is larger than the cap.
- Project columns: the 1.4 GB `reasons` column is read for every row and used for picks only;
  read it for picked instruments (predicate pushdown on `decision`).
- Build the per-run index once per cached frame, not per request (`run_rows`).

**P3, ADR 0077 phases (do not duplicate):** the release's "picks by instrument" and per-run
tables replace these frames outright; the separate warm process gets the ceiling below. This
document only adds that the release build must itself read newest-runs (P1), or the build is
the same 8 GB peak, moved into ingestion.

**P4, ingestion:** stop the fragmentation (a rerun of an unchanged config writes no run, ADR 0078
decision 6) (no purge: the review dropped it). Not a
`compact-runs` tables entry: its E2 scheme drops rows that differ only in `run_id`, which the
screen readers group by.

**Deploys:** `ops/deploy.py` restarts the API for any `src/*`, `libs/*`, `config/site/*` path, so
ingestion-only changes (`src/algotrade/workflows`, `libs/sources/.../vendors`, `nightly.toml`,
`config/site/edges`...) restart it and re-balloon it. Narrow it to the API's import closure
(computed by a test, deny by default like `_INGEST_FREE`): a follow-up PR.

## Architect review (2026-10-20) folded in

- **P1 is sound but needs guards**: a restating run (`migrate_ids`, `IngestRun.rewrite`)
  restamps every config's rows and the merge starts from it, so "newest run per config" falls
  back to the full merge when the partition holds a restating run (or a file whose `user_id` /
  `config_id` footer min != max). Choose runs from the **visible index entries** (own run
  included) mapped through the footer statistics, never from run records (the newest record can
  be running or failed; `screen-{config}-{user}` is ambiguous with `-`), and choose and read inside
  one `pinned_read(upto)` as a new backend method with `tests/contract/storage/` tests and an
  ownership entry. Also cover `results.py` `_run_fields` and `_stored_key`, which decode the whole
  values partition again outside the shared cache.
- **P2's cache budget goes before "previous session once"**: the previous session is already one
  cached key, recomputed only because the 400 MB cap evicts it.
- **P4's purge is dropped**: it commits (moves `visible_seq` / `partition_seq`) and gives up older
  `as_of` reads (ADRs 0007, 0077); only the rerun skip (ADR 0078 decision 6) stays.
- **Allocator**: Arrow reads `ARROW_DEFAULT_MEMORY_POOL` once, when it first creates the pool, and
  the API imports pyarrow before `main`, so P0 calls `pa.set_memory_pool(pa.system_memory_pool())`
  (`arrow_memory.use_system_pool`, PR #756). The ADR 0077 warm process and release build need it
  too. Measured on the home warm (newest-run prototype): footprint after `ideas` 0.98 GB vs 2.26 GB.

## Guards so it cannot regress

1. **Footprint budget in `make doctor`**: reads the footprint of the process on :8000
   (`footprint -p`, read-only) and warns above 2 GB, with the number.
2. **Warm ceiling**: the warmer stops between steps when the process footprint passes a ceiling
   (`[serving] warm_ceiling_mb`, default 3000) and logs which step; a test with a fake probe.
3. **Per-read budget test** (with P1): a store with 10 runs x 20 configs in one session; the
   screen-rows read's peak Arrow allocation (`pa.default_memory_pool().max_memory()`) stays within
   2x the newest-run bytes. This is the test that would have caught the fan-out.
4. **Allocator test** (`tests/apps/api/test_main_memory.py`, #756): importing `algotrade_api.main` in a subprocess leaves the default
   Arrow pool `system`.
