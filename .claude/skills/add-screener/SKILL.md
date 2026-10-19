---
name: add-screener
description: Add an end-of-day screener (options or equities) that filters and ranks instruments from stored features. Use when creating or changing a screener.
---

# Add a screener

**Rules first (ADR 0029, `docs/screeners/rules.md`).** Most screeners are a **rule screen**:
`impl = "rules"`, HARD / SOFT / SCORE criteria over catalogue fields, no Python. Add a
versioned site preset `config/site/presets/screeners/<id>/v<N>.toml` (model it on
`vrp_scanner/v2.toml`; a missing field is SKIPPED, never a pass) and its sha256 line in
`architecture/preset_versions.toml` (versions are immutable: change = add `v<N+1>.toml`).
A new preset goes in a family of `config/site/guide/sections.toml` and gets its playbook
`config/site/guide/playbooks/<family>/<id>.toml`; a new version updates that file's `[asks]` to its
criteria (`add-guide-content`; fitness tests fail otherwise). A formula the criteria need is an expression feature (`add-feature`). Check it with
`algotrade-backtest config validate <id>`; a test goes with it. Write a **Python screener**
(steps below) only when the rules cannot express it; say why in the PR.

Read first: ADR 0029 (rule screens), ADRs 0007 and 0008, and `docs/data/storage.md` (feature and result grains).

**Ownership check (ADR 0019):** a screener only scores a `FeatureView`. Selecting,
auditing coverage, writing results and run records belong to `services/screening/run.py`;
running it belongs to the job runner (`services/jobs`, kind `screen`; nightly submits
`screen` jobs). Shared filters live in one helper, not copies: `make dupes` must pass.
Owners are listed in `architecture/*_ownership.toml`.

0. **Where it goes:** `strategies/screeners/` (rule screens: `strategies/screeners/rules/`); running it is `services/screening/` (`grep -n purpose architecture/*layout*.toml`); no fit: new folder, `add-responsibility` step 3. Tests mirror it; if a folder is at 8+ modules, plan the split (`make layout`).
1. **Location:** `src/algotrade/strategies/screeners/<name>.py`. Implement the screener
   interface (`strategies/screeners/base.py`): `screen(view: FeatureView) -> ranked rows`;
   `FeatureView` is `core/views/feature_view.py`, built by `services/views.py`. Each row carries
   `instrument_id`, a score and human-readable `reasons`.
2. **Pure:** read only from `FeatureView` (point-in-time). Needs a new input? Add a
   feature. Apply liquidity filters (minimum open interest, maximum spread %) through
   shared helpers, not copy-paste.
3. **Parameters** go in a typed config with defaults, so the UI can show and edit them.
4. **Register it** with one line in `strategies/screeners/registry.py`. Legacy CSV
   exports, if any, live in `services/screening/exports.py`.
5. **Tests:** unit tests on synthetic chains; property tests (deterministic, every row
   satisfies the declared filters, no data after `as_of` is read).
6. **Baseline:** results on the golden option chains go into the screener baseline
   (`make baseline`).
7. **UI:** columns and formats are declared on the screener, so the generic `DataTable`
   renders it without any screen-specific code.
8. **Config (Python screener):** add a site preset in `config/site/presets/strategies/<id>.toml` (`kind =
   "screener"`, `impl`, `params`, a `selection` preset or inline selection; `schedule =
   "nightly"` if it should run every night). Never filter instruments inside the screener
   itself; that is the selection's job. Check it with `algotrade-backtest config validate <id>`.
9. Run `make changed`, then push: CI is the full gate.

## Edge-document checklist (from eight architect reviews; the edge document is `config/site/edges/<id>/edge.toml`)

- **Do not gate the base on the screener's own field**: picks equal the base, lift is about 0
  and a retire rule on it is a tautology (`tests/unit/config/site/test_edge_base.py` flags it;
  a `not_null` coverage gate is fine).
- **A sparse score** needs the universe gated on the score (`not_null`) and a coverage test
  (`MIN_SCORE_COVERAGE` 0.8).
- **No `[published]`** for a two-group spread or a figure the harness does not measure; a proxy
  is disclosed as a proxy.
- **A variant cannot carry screeners**: a different screener is a separate edge.
- **Time-series edges**: `base = "out_of_window"`, `benchmark = "none"`, horizon = window length.
  `portfolio_return`: `lift` is `None` and the verdict is a picks-series t.
- **Every new feature column ships its field-guide entry**, whether or not a screen reads it
  (`scripts/features_doc.py` lists unguided fields).
- **Guide text**: sentences under 30 words, no banned words (`tests/unit/config/site/guide/test_style.py`,
  not mapped by `make changed`: run it); a playbook folder holds at most 12 files.
- **After a merge of main**: recount preset and screener test totals as the SUM; on a
  `benchmarks/baseline.json` conflict take main's, then `make baseline`, never hand-edit. Run
  `git fetch origin main` before every merge, never merge a local copy.
