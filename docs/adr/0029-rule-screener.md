# ADR 0029: Rule screener, versioned user configs, and API writes through `services/authoring`

**Status:** proposed (2026-10-03; the defaults under "Pending owner confirmation" are
proposals until the owner confirms them). Amends [0024](0024-api.md) (the API may write user
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
  `flags`, `classify`, `columns`, `[decision]`. A criterion is a selection `Rule`
  (`field`, `op`, `value`) over catalogue fields plus `mode`, `weight`, `score`, `on_miss`,
  `label`, `enabled`. Formulas are never inline: they are `feature.<name>` user features.
- **Modes.** HARD: must be TRUE; FALSE gives `on_miss` (default REJECT); UNKNOWN gives
  UNKNOWN. SOFT: FALSE or UNKNOWN is a miss; the row is never QUALIFIED, gets `on_miss`
  (default WATCH), and more than `max_soft_misses` misses is REJECT. SCORE: never gates,
  only earns points; UNKNOWN earns 0, is recorded, and is not a miss.
- **Decision order:** any hard UNKNOWN → UNKNOWN; else any REJECT → REJECT; else the most
  severe soft `on_miss` (EVENT_RISK > LIQUIDITY_RISK > WATCH); else QUALIFIED.
- **Score 0-100**, for sorting only: each weighted criterion earns `weight * ramp(value)`, a
  linear ramp from `score.from` (0) to `score.to` (full), reversed when `from > to`, clipped;
  a boolean or label pass earns full weight; UNKNOWN earns 0. `score = 100 * points /
  sum(weights)`, computed for every non-UNKNOWN row. Chosen over pass counts (too coarse)
  and cross-sectional percentiles (depend on the rest of the run, unstable day to day).
- **Tiers** (ordered `Group`s, first TRUE wins), **flags** (`Group`s; add a flag, never
  change the decision), **classify** (a label field that buckets output), **columns**
  (display-only values stored with the row).
- **Fail closed:** a spec is validated (parse, catalogue, types, user features) before it
  runs or is finalised; an unknown field or bad type is an error, never a silent pass.

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
- `results/rule_screen` (partition `session_date`): one row per instrument with `decision`,
  `score`, `tier`, `class`, `flags`, `reasons`, `hard_failed`, `soft_missed`, `unknown`, and
  `user_id`, `config_id`, `config_version`, `config_hash`, `ts`, `knowledge_ts`, `source`,
  `run_id`.
- `results/rule_screen_values` (long): `instrument_id, criterion_id, field, value_num,
  value_str, outcome (PASS / FAIL / UNKNOWN / INFO), points`. One schema for every config,
  so Ideas can query across screens; no per-config tables or drifting wide columns.
- Pages (results, Ideas) read stored rows for sessions <= `?date=` and never recompute.

### Preview == nightly
Preview (`services/explore/screen_preview.py`) and the nightly `screen` job
(`services/screening/run.py`) call the same `evaluate_screen(spec, view)`; a test asserts
equal rows for a fixed session. Preview writes nothing. Its warm path is an in-process LRU of
the session's field frame keyed by (session, field set, user-feature hash, store
`visible_seq()`); `visible_seq()` is the read-only publish counter being added to the storage
protocol in a parallel PR, so a nightly publish invalidates the cache. Budget: p95 <= 1 s
cold, <= 200 ms warm for ~10k instruments x <= 25 fields.

### Pending owner confirmation (proposed defaults)
1. Hard criterion with missing data → UNKNOWN (not REJECT).
2. Soft criterion with missing data → a miss (recorded as `unknown:<id>`).
3. `max_soft_misses` defaults to 1 for every screen.
4. Several soft misses → one category by precedence EVENT_RISK > LIQUIDITY_RISK > WATCH, with
   every reason listed.
5. User screens pin the preset version they extend; a rebase action moves them forward.
6. Finalise and schedule (`schedule = "nightly"`) are separate toggles.
7. Preview runs on the latest closed session only (no time travel).
8. The user names formulas added in the Builder; they are saved as user features.
9. Ideas: one row per ticker listing every screener that picked it, ranked by the
   highest-priority screener, then score.
10. Sharing screeners and the "best put (premium, ROC)" column come later.
11. REJECT rows are still scored (near-miss sorting).

## Consequences
- Screener thresholds change in the UI without a PR; Python screeners remain for logic rules
  cannot express. A preset port (`short_premium_liquidity`, golden-equal) proves the engine.
- New owners: `core/model/predicates.py` (three-valued predicate, moved from
  `engines/selection`), `config/strategy/screen_spec.py`, `strategies/screeners/rules/`,
  `services/authoring/`, `storage/configs/writer.py`, `services/explore/screen_preview.py`
  and `ideas.py`; registered in `ownership.toml` and `layout.toml` with the code PRs.
- The API is no longer strictly read-only: the write surface is one package, user-scoped,
  and validated fail-closed; it gains auth checks when identity arrives (phase 4).
- The preview cache is per process (one API process assumed).
