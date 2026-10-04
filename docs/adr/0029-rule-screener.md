# ADR 0029: Rule screener, versioned user configs, and API writes through `services/authoring`

**Status:** accepted (2026-10-03; owner decisions folded in). Amends [0024](0024-api.md) (the API may write user
configs, and only through `services/authoring`). Builds on
[0015](0015-configs-selections-users.md) (configs, layering, users),
[0019](0019-ownership-and-boundaries.md) (one owner per responsibility),
[0022](0022-atomic-run-publication.md) (atomic publication) and
[0023](0023-feature-store.md) (catalogue, expression features). User-facing spec:
[docs/screeners/rules.md](../screeners/rules.md).

## Context
Every screener today is Python (`strategies/screeners/`), so changing a threshold needs a PR.
The owner wants screeners built and tuned in the web UI (Builder), with a live preview, saved
as versions, run nightly, and merged into one ranked Ideas list. Most of the parts exist: the
`Screener` contract and shared `Decision`, the coverage-audited runner, three-valued `Rule` /
`Group` predicates, the field catalogue with user expression features, and config layering.
Missing: a declarative screen spec and its evaluator, versioned writable user configs, a way
for the (read-only) API to save them, and a result shape that is the same for every config.

## Decision
### Engine (`impl = "rules"`, one more `Screener`)
- A screen is `selection` + `criteria` (a table keyed by criterion id) + optional `tiers`,
  `flags`, `classify`, `columns`, `[rank]`. A criterion is a selection `Rule` (`field`,
  `op`, `value`) over catalogue fields plus `mode`, `tolerance`, `on_miss`, `label`,
  `enabled`. Formulas are never inline: they are `feature.<name>` user features.
- **Missing data never passes.** A gating (HARD or SOFT) criterion whose value is missing
  (or of the wrong type) makes the row **SKIPPED** with the reason `no <field>`; SKIPPED rows
  are not processed (they count against coverage, like the contract's UNKNOWN) and are not
  scored.
- **Modes.** HARD is strict: FALSE → REJECT. SOFT is a **tolerance band** (`tolerance`,
  absolute or `{ relative = r }` of the threshold; numeric comparisons only): a value that
  misses the threshold by at most the tolerance is a **near miss** (the row is at best WATCH,
  or the criterion's `on_miss`: WATCH, LIQUIDITY_RISK or EVENT_RISK); beyond the tolerance it
  fails like HARD. SCORE never gates: a miss (or missing data) only lowers the score.
- **Decision order:** any gating criterion missing → SKIPPED; else any HARD fail or SOFT
  fail beyond tolerance → REJECT; else any near miss → the most severe near-miss `on_miss`
  (EVENT_RISK > LIQUIDITY_RISK > WATCH), every reason listed; else QUALIFIED.
- **Score**, for sorting only: a row meeting every threshold scores **100**. Each miss
  subtracts its penalty: a near miss (SOFT or SCORE) `10 × distance / tolerance` (at most 10;
  a SCORE miss beyond its tolerance, without one, or with missing data costs the full 10); a
  HARD fail or a SOFT fail beyond tolerance a fixed 100. More misses and bigger margins score
  lower; the score is not clipped (REJECT rows are scored, so near misses sort above clear
  fails). Ties sort by a configurable secondary column (`[rank] tie_break`, descending by
  default; the VRP preset uses the IV−HV spread), then by instrument id. Replaces linear-ramp
  weights: one rule ("distance from the threshold") instead of a ramp per criterion,
  deterministic, independent of the rest of the run (unlike cross-sectional percentiles).
- **Tiers** (ordered `Group`s, first TRUE wins), **flags** (`Group`s; add a flag, never
  change the decision), **classify** (a label field that buckets output), **columns**
  (display-only values stored with the row).
- **Run summary** (preview and nightly): passed (QUALIFIED) count, decision counts, skipped
  counts by reason, and the **narrow misses**: rows whose only misses were within tolerance,
  with each criterion, value, threshold and distance.
- **Fail closed:** a spec is validated (parse, catalogue, types, user features) before it
  runs or is finalised; an unknown field, a bad type, a SOFT criterion without a tolerance or
  on a non-numeric op, or a tolerance on a HARD criterion is an error, never a silent pass.

### Versioned configs
- Site presets: `config/site/presets/screeners/<id>.toml`, reviewed by PR, carrying
  `version = N`. User screens: `config/users/<u>/screeners/<id>/v<N>.toml` (finalised,
  immutable; latest = highest N) and `draft.toml` (the Builder's autosaved working copy),
  behind `ConfigStore` and a new `ConfigWriter` (a DB backend can replace the files later
  under the same protocol).
- Criteria merge by id (a user overrides one threshold; `enabled = false` removes one).
  `extends = "<preset>@<N>"` pins a preset version; the UI offers "rebase on vN+1".
- Every result row and run record carries `config_version` next to `user_id`, `config_id`
  and `config_hash`.

### API writes (amends ADR 0024)
The API stays read-only except for **user configs and user features**, which it writes only
by calling the new use-case package `services/authoring` (save / discard draft, finalise,
save user feature). Routes stay thin; an import-linter contract allows `apps/api` to import
`services.authoring` and no other write package. Phase 0 users are labels (no auth) until
identity arrives.

### Results
- `results/rule_screen` (partition `session_date`): one row per instrument with `decision`
  (incl. SKIPPED), `score`, `rank`, `tie_break`, `tier`, `class`, `flags`, `reasons`,
  `failed`, `near_missed`, `missing`, and `user_id`, `config_id`, `config_version`,
  `config_hash`, `knowledge_ts`, `source`, `run_id`.
- `results/rule_screen_values` (long): `instrument_id, criterion_id, field, mode, value_num,
  value_str, outcome (PASS / NEAR / FAIL / MISSING / INFO), distance, penalty`.
- The run summary above is stored in the screen's **run record** (`stats["summary"]`, next
  to the coverage audit; the screen job's result and the results page carry it). One schema
  for every config, so Ideas can query across screens; no per-config tables or drifting wide
  columns. Both tables merge per (`user_id`, `config_id`, `instrument_id`) because every
  config shares a session's partition; readers take a config's latest run (`run_id`).
- Pages (results, Ideas) read stored rows for sessions <= `?date=` and never recompute.

### Preview == nightly
Preview (`services/explore/screen_preview.py`, on the latest closed session only) and the nightly `screen` job
(`services/screening/run.py`) call the same `evaluate_screen(spec, view)`; a test asserts
equal rows for a fixed session. Preview writes nothing. Its warm path is an in-process LRU of
the session's field frame keyed by (session, field set, user-feature hash, store
`visible_seq()`); `visible_seq()` is the read-only publish counter being added to the storage
protocol in a parallel PR, so a nightly publish invalidates the cache. Budget: p95 <= 1 s
cold, <= 200 ms warm for ~10k instruments x <= 25 fields.

### Owner decisions (2026-10-03)
1. Missing data on a HARD or SOFT criterion → SKIPPED (`no <field>`), never a pass.
2. SOFT is a tolerance band; HARD is strict; SCORE never gates.
3. Score: 100 minus normalised distance penalties; REJECT rows are scored; ties by a
   configurable secondary column.
4. Several near misses → one category by precedence EVENT_RISK > LIQUIDITY_RISK > WATCH, with
   every reason listed.
5. Presets are visible and editable in the UI; user copies pin the preset version (rebase
   action).
6. Finalise and the nightly schedule are separate switches.
7. Preview runs on the latest closed session only (no time travel).
8. The user names formulas added in the Builder; they are saved as user features.
9. Ideas: one row per ticker listing every screener that picked it, ranked by the
   highest-priority screener, then score.
10. Sharing screeners and the "best put (premium, ROC)" column come later.

## Consequences
- The shared `Decision` gains `SKIPPED` (a gating criterion's data is missing); like
  `UNKNOWN` it is never counted as processed, so it lowers coverage.
- Screener thresholds change in the UI without a PR; Python screeners remain for logic rules
  cannot express. A preset port (`short_premium_liquidity`, golden-equal) proves the engine.
- New owners: `core/model/predicates.py` (three-valued predicate, moved from
  `engines/selection`), `config/strategy/screen_spec.py`, `strategies/screeners/rules/`,
  `services/authoring/`, `storage/configs/writer.py`, `services/explore/screen_preview.py`
  and `ideas.py`; registered in `ownership.toml` and `layout.toml` with the code PRs.
- The API is no longer strictly read-only: the write surface is one package, user-scoped,
  and validated fail-closed; it gains auth checks when identity arrives (phase 4).
- The preview cache is per process (one API process assumed).
