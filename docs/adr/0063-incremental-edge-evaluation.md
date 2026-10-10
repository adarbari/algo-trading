# ADR 0063: Incremental edge evaluation (stored legs)

**Status:** proposed (2026-10-10; architect-reviewed 2026-10-10, fixes folded in; owner decision
pending: exact invalidation vs the append-only alternative). Extends
[0053](0053-edges-hypotheses-outcomes-and-one-harness.md) (the harness, the trial log) and
[0059](0059-edge-evaluations-on-request.md) (runs on request); writes only through `ResultWriter`
([0005](0005-ingestion-is-the-only-writer.md)), published atomically ([0022](0022-atomic-run-publication.md)).

## Context
`edge-eval` recomputes every decision session of the range on every run: for
`vrp_short_premium` (7 edge variants x 3 screeners x 3 horizons, 2011-01-03..2026-10-06) that is
18 minutes (job `job-edge-eval-d1832c8c408e0db5`, 2026-10-10) before the hot-spot fixes of the
same PR, of which per-session work (the screen at D, the eligible set, the implied vol, the
outcome scoring) is nearly all and the statistics (slices, deflated Sharpe, PBO, the random
measures) a few seconds. A night adds at most a few closed windows per horizon, so the nightly
redoes thousands of identical per-session computations to add a handful. Owner target: under a
minute per edge for the nightly.

The unit that is computed per session is already explicit in the harness: one `SessionStat`
per (edge variant, variant, horizon, decision session D) and, for a screener out of sample, one
`RandomStat`. Everything a result row holds is a pure function of these legs plus the run's
split (`measures.slice_measures`, `pool_stats`, `_deflate`, `_pbo`, `random_measures`).

## Decision (proposed)
1. **A leg is stored.** New result table `results/edge_legs` (ResultWriter only; the API's and
   the CLI's job, never ingestion's): one row per (user_id, edge_id, edge_variant, variant,
   trial hash, horizon, decision session D) with the leg's `SessionStat` fields, entry session
   S, and the random draw sums (`value_sums`, `hit_sums` as float32 lists; screener legs from
   the split onward only: ~4 GB per edge if every leg kept them, so moving the split is a FULL
   run).
   `session_date` = D, `knowledge_ts` = the run's compute instant, `run_id` = the run. Plus the
   **leg key**: `sha256(HARNESS_VERSION, LEG_VERSION, trial hash, universe selection hash,
   iv_field, event class + offset, seed scheme, draws, hash of the resolved expression-feature
   definitions the screens and the universe read)`: a TOML formula edit changes no partition
   and no config hash, so it must change the key. A leg is reused only under the same key.
2. **What a session read, recorded.** Screens read their inputs with `as_of = None` (the store as
   it is), so a leg depends on the store's state, not on the run's `as_of`. The harness reads
   through a recording reader: per decision session D, every (table, partition) read (screens,
   eligible set, implied vol, regime label, event schedules, the historical-identity proxies),
   stored once per D (`results/edge_legs` session rows, not per leg) with `inputs_seq` (the
   store's commit sequence, `StoreReader.visible_seq`, at the read). Outcomes are recorded the
   same way per (S, horizon): one mechanism for both. No hand-kept table list (it drifts).
3. **Reuse rule (point in time).** A run at `as_of` reuses a stored leg only when all hold:
   (a) same leg key; (b) the leg's `knowledge_ts <= as_of` (a leg computed after `as_of` may hold
   rows not known then: a historical re-run is always FULL); (c) no outcome row of (S, horizon)
   with `knowledge_ts` in (the leg's read, `as_of`] (a revised or late row, e.g. an ADR 0061
   UNMEASURED rewrite, recomputes the leg); (d) every recorded partition of D still exists and
   its highest index `seq` is at most `inputs_seq` (a feature backfill or restatement, or a
   retention purge, recomputes it); (e) for a snapshot table (reference, universe), no newer
   snapshot partition in (the snapshot read, D]. (d) and (e) need one new storage Protocol
   method, `partition_seq(table, dates)` (index entries carry `seq`: `local_index`), with
   `tests/contract/storage/` coverage for every backend. Commit markers are deleted after
   apply, so there is no change log to replay; recording run ids is no more precise than `seq`.
4. **New legs.** Every (plan, variant, D) of the range with a closed window and no reusable leg
   is computed exactly as today (same code path, `_stat`, `_measure_random`), so a FULL run is
   the incremental run with an empty store of legs. Nightly: only the decision sessions whose
   window closed since the last run, plus any invalidated by 3(c)/(d).
5. **Statistics always from all legs.** Slices, pooled blocks, deflated Sharpe, PBO and the
   random measures are recomputed from the full set of legs on every run (seconds). The
   `results/edge_eval` rows of an incremental run equal a full run's at the same `as_of` exactly
   (the acceptance test, below).
6. **Random draws no longer depend on the run.** The seed is today (run hash, edge variant,
   horizon, D) and the run hash holds the range and `as_of`, so every run redraws every session.
   Seed by (leg key, edge variant, horizon, D) instead; `SEED_VERSION` 3. A run's draws are then
   the same for a session whatever the range or the night; the draws stay independent of the
   outcome, and the stored rows of earlier runs keep their own seed version.
7. **Trial log unchanged.** A trial is still a distinct (edge variant, variant, config hash,
   horizon); an incremental run writes the same run record with the same trials, so the count
   the deflated Sharpe ratio is taken over does not grow by re-running. The record adds `mode`
   (`full` | `incremental`), `legs_reused`, `legs_computed`, `legs_invalidated` (by reason).
   An exploratory split changes no `SessionStat` leg; draws exist only from the stored split, so
   a run under another split is FULL for its draws. The statistics read only the legs of the
   current plans' trials; legs of a trial the edge no longer has are pruned on publish.
8. **Atomic.** The run's new legs, its `edge_eval` rows and its run record publish in one
   `writer.publishing` block: a crash leaves the previous legs and rows, never legs without a run.
   Superseded legs (same key, D) are replaced, never appended twice (`merge_rows` on the key).
9. **Audit.** `--full` recomputes every leg and rewrites them; the weekly `enrichment` cadence
   runs one full evaluation per open edge and compares its rows with the last incremental run
   (a difference fails the job and names the legs).

10. **Where it lives.** `services/evaluation/cross_section/legs/` (a new folder: `cross_section/`
   is at 10 modules and `harness.py` at 955 lines), declared in `architecture/layout.toml`; the
   table in `architecture/tables.toml` with its reader restricted to `cross_section`; an ownership
   entry `edge-leg-reuse`.

## Alternative (owner decision)
Append-only nightly: store legs, never invalidate, and let the weekly full run replace them.
Under 60 s with no new storage method, but a restated feature or a rewritten outcome reaches the
results only at the next weekly run (up to a week stale). The design above is the smallest exact
one; the alternative is cheaper to build.

## Acceptance
- Contract test: for the golden `cross_section` store, incremental after a full run at the same
  `as_of` gives identical `edge_eval` rows; a full run at `as_of` then an incremental at
  `as_of + 1 night` equals a full run at `as_of + 1 night`.
- Invalidation tests: a rewritten outcome row (UNMEASURED) and a re-committed feature partition
  at D each recompute exactly that leg; an `as_of` before the legs' `knowledge_ts` runs FULL.
- Fitness: `results/edge_legs` is read only by `services/evaluation/cross_section` (with the
  outcomes import contract: a leg holds outcome-derived values).
- Nightly target: an incremental `vrp_short_premium` under 60 s on the owner's Mac.

## Open questions for the architect
1. Is `inputs_seq` + per-partition commit sequence (3d) sound, or should a leg record the run ids
   of the input partitions it read (more precise, a bigger row)?
2. Should `edge_legs` live under `results/` (written by the API's job runner too, ADR 0059) or be
   a cache under `var/` outside the store (not point-in-time data, no `knowledge_ts` semantics)?
   This ADR proposes `results/` so the publish is atomic with the rows.
3. Seed change (6): acceptable that the draws of runs before SEED_VERSION 3 are not comparable
   with later ones (the verdict reads only the latest run)?
