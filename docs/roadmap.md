# Roadmap

## Now / Next

The pickup list a fresh session reads first. A PR that opens or closes an item updates it.

**Running** (check `make status`; verified 2026-10-05 05:40)
- Nothing long-running. IBKR IV history backfill finished 2026-10-05 05:30 (all 4,200 names: 4,197 OK, 3 genuine NO_DATA; `ibkr_iv@v1` rollups over 502 sessions, rank FULL for 4,789 of 5,415 names on 2026-10-02).

**Next**
- **Market regime (RG, ADRs 0047-0049):** RG0-RG3 done (RG3b: the episode scorecard and the bear-state probit, `make regime-scorecard` after the macro backfill); next RG4 ([RG section](#market-regime-rg-recession-risk-and-market-stress-as-features-a-regime-gate-for-sizing-adrs-0047-0049); plan [market-regime-plan.md](market-regime-plan.md)).
- **Workflows (WF, ADR 0039):** WF1-WF3 done; next WF3b, then WF4 ([WF section](#workflows-wf-dependencies-succeed-or-fail-cadence-adr-0039)). **Owner action first:** Massive returned 403 for the 2026-10-05 bars and that nightly finished PARTIAL, so nothing retries it: once Massive serves the day run `algotrade-ingest bars --date 2026-10-05 --wait`, then `rollups --date 2026-10-05 --wait`, then the 2026-10-05 screens (until then lookback rollups from 2026-10-06 compute over the gap).
- ETF holdings (ADR 0035, accepted): after merge run `algotrade-ingest etf-holdings` once (reads the ~1,140 covered funds, plus the non-optionable N-PORT funds with a 20-session dollar volume of $5M or more, up to ~900 (`fallback_scope = "liquid"`, `fallback_min_adv_usd`): about 1.5 hours per 1,140, extrapolated from the sample, mostly SEC header lookups; or let the nightly fill it, 200 funds a night, 6 weekday nights), ProShares funds (173, the VIX funds UVXY / SVXY / VIXY and the leveraged and inverse ones) are read from their daily file by the same run (weights are shares of gross exposure, ADR 0035), then the Overview tab renders `<HoldingsPanel symbol onSelectSymbol>` (`widgets/holdings-panel`) for ETFs.
- ETF descriptions for funds with no SEC prospectus objective: SPY, DIA, GLD, SLV, USO, IBIT, SOXL and the like (unit trusts, commodity and crypto trusts, some leveraged funds); 246 of the 1,464 ETFs trading $5M or more a day have none (2026-10-05). The SEC series match closes 83 of them; the rest need issuer pages (iShares and State Street page text for IBIT, SLV, SPY, DIA; ProShares and Direxion 497K or pages for SOXL, TSLL, UVXY) and an ADR.
- Optional IBKR pace trial: `[ibkr] historical_min_interval_s` 5, then 3, watching timeouts and error 162 (the backfill ran at 10 s, IV only, about 6 names a minute). The nightly keeps the history current (100 names a night of any new gap).
- **Read-model track (RM, ADRs 0036-0038, [api/read-model.md](api/read-model.md)): done** (RM1-RM10b; RM10b deleted `services/explore`: the Builder's dry runs are `services/preview` over the request's `ReadContext`, READ 2 covers every use case and the API). Every page reads GraphQL; REST is writes, job polling, health, live quotes and preview POSTs. **R (RM5):** the Ideas Expiry DTE column is UNKNOWN until `nearest_expiry@v1` is backfilled (the RM3 owner action). What the track left open is the [deferred list](#deferred-from-the-rm-track). **Owner action (RM3):** after merge run `algotrade-ingest rollups --from 2024-10-03 --to <last session> --only nearest_expiry@v1` (only sessions with a stored chain get rows; the store holds chains from 2026-10-02, so this takes seconds); the nightly computes it from then on.
- **Identity (ID, ADR 0040, Supabase Auth; outside users within a week of 2026-10-05):** ID1-ID4 done (the registry; `apps/api/algotrade_api/auth/` verifies Supabase tokens, email (+ optional pinned `subject`) in the git-ignored `config/users/<id>/identity.toml` -> registry user, 401 / 403 on every route but `/health`, `Query.viewer`; ID3: the web signs in through `@supabase/supabase-js` in `src/shared/api/auth.ts`, `/login`, `guard.ts` reads `viewer`, the web's `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY` go in `apps/web/.env.local`; ID4: `?user=` retired: writes act for the caller, an admin names another user in the `X-Act-For` header, the preview POSTs in a body `user`; `services/authoring` refuses undeclared users; the nine Admin GraphQL fields are `AdminOnly`, a trader gets `FORBIDDEN`; `GET /screens/{id}/run/{job}` is 403 for another user's job; `ALGOTRADE_CORS_ORIGINS`). **Owner action:** the Supabase project exists and passed the [configuration.md](configuration.md#environment) checklist on 2026-10-05 (sign-ups off, confirm email on, anonymous off, ES256 keys): set `ALGOTRADE_AUTH=supabase` in `.env`, write each user's `config/users/<id>/identity.toml`, and declare outside users in `config/site/users.toml`. **Hosting (H1, ADR 0044): done** in code: the owner's Mac behind Tailscale Funnel, one origin (the API serves the built web from `ALGOTRADE_WEB_DIST`, `make web-build` -> `var/web`), `algotrade-api schedule` (launchd agent, `127.0.0.1:8000`), `make doctor` checks the build and the installed agents, runbook [hosting.md](hosting.md). **Owner action**, in order ([hosting.md](hosting.md)): `make web-build`; `.env`: `ALGOTRADE_AUTH=supabase`, `SUPABASE_URL`, `ALGOTRADE_WEB_DIST=var/web`; `.venv/bin/algotrade-api schedule` and run the install commands it prints; install Tailscale (Standalone app or Homebrew `tailscaled`: the App Store app has no Funnel), sign in, enable MagicDNS + HTTPS certificates and the `funnel` node attribute; `tailscale funnel --bg localhost:8000`; Supabase Site URL + Redirect URLs = the `https://<machine>.<tailnet>.ts.net` address; onboard users (Supabase Add user, `users.toml`, `identity.toml`). Redo `make web-build` after every web change.
- Company financials (`financials@v1`, `feature.pe_ratio`, `feature.revenue_growth_yoy`; Explore Overview reads them): after merge run `algotrade-ingest shares --force` (about 30 to 40 minutes, resumable), then `algotrade-ingest rollups --from 2024-10-03 --to <last session> --only financials@v1` (a few seconds a session, estimated), and spot-check a few names ([vendors.md](data/vendors.md) "SEC EDGAR company facts").
- VRP live spread check in the UI via `GET /chains/{id}/live`. Flaky tests: preview timing under load, smoke axe admin light, one builder e2e, the Ideas e2e "shows the stored display values and the watch-outs" (failed once under `make web-check` with `WEB_WORKERS=2` on 2026-10-05, passed on re-run).
- Descriptions (ADR 0034, accepted): after merge run `algotrade-ingest descriptions --only funds --force` (ETFs, ~2 min; `--force` rereads the 6 quarters so the ~870 ETFs matched through the SEC series file get their text, 83 of the 246 liquid gaps), then stocks in chunks (`descriptions --limit 300`, ~1 h each, S&P 500 first, each run holds the ingest lock; the nightly adds 100). Then the Overview tab reads `reference.description` from `GET /instruments/{id}`.

**Facts**
- IBKR fundamentals are not permitted on this account (error 10358): share-class counts stay SEC.
- Massive's ticker overview has descriptions for stocks and ADRs, none for ETFs (free tier, checked 2026-10-04); ETF text is the SEC prospectus objective (~74% of ETFs). Massive: 5 requests a minute, so descriptions are capped at 100 stocks a night (ADR 0034).
- Owner screener / VRP decisions: ADR 0029, ADR 0030 (rule screens: no selection, missing data never skips, no tiers / classify / labels; `vrp_scanner` v3) and `docs/screeners/vrp-scanner.md`. Natural-language drafts (ADR 0041) ship off: `config/site/llm.toml` `enabled = true` + a provider's `base_url` / `model` (Ollama, Gemini, Groq, OpenRouter examples in the file) and `ALGOTRADE_LLM_API_KEY` in `.env` turn on the Builder's "Describe it" box. **Field guide (ADR 0041 amended 2026-10-06):** `config/site/field_guide/*.toml` (37 fields, 7 situations, sourced) is in the prompt and rendered to `docs/data/field-guide.md`, because drafts chose the right fields but poor thresholds; next: the Builder shows it per field (`guide` on GraphQL `FeatureInfo`; `add-graphql-field` + `add-ui-component`) and a stored pending-deal flag (`add-feature`) replaces the `atr_pct` proxy of the takeover situation. A v3 run stores a row per snapshot instrument (about 11.4k, was about 4.2k).
- Harness audit: last 2026-10-04 (`/audit-harness`; `/start` flags when older than 30 days; fixes log: [history.md](history.md)).

---

Shipped fixes (with owner actions) are logged in [history.md](history.md). Each phase is one or more PRs, merged only with CI green. Update the status column as work
lands. The target state of every item is described in [architecture.md](architecture.md).

| # | Phase | Delivers | Status |
|---|---|---|---|
| — | Harness | Layered library, tests, golden datasets, baseline, CI, auto-merge | done |
| — | Decisions | Docs, ADRs 0004–0017, workflows (skills) | done |
| 0 | Restructure | Target layout; instrument ids + multipliers; storage-backed backtests and the four data layers; source interface; configs, selections and users; jobs; uv workspace. Baseline identical throughout. | done |
| 1 | Ingestion: universe, reference, bars, events | Nasdaq earnings, Massive bars + splits/dividends, FIGI ids (ADR 0018), universe builder, SEC company details, nightly quality checks, launchd scheduler (1.1-1.8; history in git and `docs/history.md`) | **done** |
| 2a | Options liquidity slice | Cboe chains, `option_liquidity@v1`, `short_premium_liquidity`, screening engine with coverage audit, legacy CSV exports | done |
| 2b | Quant + rollups | `quant/` (ADR 0021), Treasury rates, the rollup framework and groups (`price_stats`, `earnings`, `dividends`, `iv30`, `iv_history`, `fundamentals` from SEC shares), rebalancing selections (2b.1-2b.5; groups: [data/features.md](data/features.md)) | **done** (2b.1–2b.5) |
| 3 | Screeners | VRP scanner ([spec](screeners/vrp-scanner.md)) with its 8–15 delta second stage; cash-secured puts / covered calls, IV rank, unusual activity, credit spreads; a screener results baseline | **done**: VRP scanner and rule screeners (ADR 0029); the rest is in Next |
| 4 | API | FastAPI app over `services/`; authenticated users mapped to `user_id` with per-user access enforced in services; jobs endpoints; DB-backed `ConfigStore`; TypeScript client generated from the API schema | **done**: API v1 (ADR 0024) and authoring writes (ADR 0029) |
| 5a | Design system | Tokens → **owner approves mockups** → components + catalogue → lint enforcement | **done**: tokens final 2026-10-03 (ADR 0011, 0025) |
| 5b | Web app | Screener list, results table, contract detail, data freshness; L4 watchlists and preferences | **done** (pages in `apps/web/src/pages`; further pages via Next) |
| 6 | Expansion | Backtests from the UI on a queue-backed job runner; on-request pulls; futures (IBKR); intraday bars + `rollups/daily/*`; S3 storage backend and hosting; screener outcome tracking | |

## Workflows (WF): dependencies, succeed or fail, cadence (ADR 0039)

In order. WF1-WF3 shipped in one PR (resume and waivers are what make hold-back safe to run); `docs/architecture.md` ("The nightly workflow") describes the current behaviour.

| # | Delivers | Status |
|---|---|---|
| WF1 | Step model: `needs`, `critical`, acceptance checks (thresholds in `sources.toml [quality]`), SUCCEEDED / FAILED / NOT_RUN / SKIPPED / WAIVED; `quality` checks run per step; rollups fail on a gap in a lookback window; NYSE special closures | **done** |
| WF2 | Resume (steps done in an earlier attempt are reused; `--force` reruns all); sessions in order, stopping at a FAILED one (later ones held), none dropped (old PARTIAL records count as done) | **done** |
| WF3 | `nightly --date D --waive STEP --reason ...` (stored in the run record, kept on later attempts); expired latest-only steps name the unblock command; notifier names failing critical steps and held sessions, alerts on every failed retry | **done** |
| WF3b | Chains retry refetches only STALE_DATA / FETCH_ERROR names (today a FAILED chains step refetches all ~4,200, 2-4 h); consider starting the nightly later than close + 30 min (2026-10-05: ~50% STALE_DATA at 13:40 PT) | next |
| WF4 | Split into `market-daily` / `reference` (weekly) / `enrichment`: CLI commands, three launchd agents from `ops/schedule.py`, `ibkr-iv` session snapshot vs history backfill | |
| WF5 | Reads default to the latest SUCCEEDED `market-daily` session (`services/read/session.py`); architecture docs rewritten | |

## Read model (RM): one session, one read model, one graph (ADRs 0036-0038)

Every page read serves one resolved session, comes from a domain read object in
`services/read/` and is served by GraphQL; per-instrument values are catalogue features.
Plan, rules and enforcement: [api/read-model.md](api/read-model.md) ("Migration plan").

| # | Delivers | Status |
|---|---|---|
| RM1 | ADRs 0036-0038, the spec, empty `services/read` + `graphql` packages, ownership entries, import-linter contracts, REST GET allow-list (shrink-only), web derivation list, skills `add-graphql-field` / `add-domain-object`, Strawberry dependency | **done** |
| RM2 | `read/session.py` (`resolve_session`), `values.py` (`Unknown`, `to_scalar`), `context.py`; split `tests/architecture`, READ 2 test | **done** |
| RM3 | Stored facts: `nearest_expiry@v1`, `feature.earnings_before_expiry`; owner backfill | **done** |
| RM4 | GraphQL vertical slice: Instrument + features, schema snapshot, codegen, Overview facts by catalogue name | **done** |
| RM5 | Screens read model + Ideas on GraphQL (one latest-run rule, NOT_RUN, server counts); `ideas/ranking.py` deleted | **done** |
| RM6 | Explore detail pane on GraphQL (one query per tab); `explore/{instruments,chains,funds}` deleted; `Instrument.screenerHits` moves to RM5 / RM8 (needs the screens read model) | **done** |
| RM7 | Columnar FeatureTable, `widgets/feature-table`, column factories; Explore tickers + compare | **done** |
| RM8 | Screener results, preview and views on the one table widget; `explore/screens` deleted; `Instrument.screenerHits` | **done** |
| RM9 | Catalogue, distribution, backtests, configs on GraphQL; screener authoring reads (`myScreens`, `screenDetail`, `screenVersions`); `explore/{features,backtests,configs}` deleted | **done** |
| RM10a | Admin on GraphQL (`read/ops/{runs,quality,ingestion,review}`, `Query.{nightlyRuns,run,runItems,quality,verification,completeness,ingestionCell,figiReview,leverageReview}`); `explore/{runs,ingestion,review}` and the `/admin` routes deleted | **done** |
| RM10b | `services/explore` deleted (preview to `services/preview` over `ReadContext`; `ReadStore` to API `deps`), `explore-queries` removed, READ 2 widened to every use case and the API; skills and harness updated | **done** |

### Deferred (from the RM track)

Not part of any RM PR; each is its own work item:

- **Events point in time**: `Instrument.events` reads each event's latest stored version, so a
  past session can show an event stored after it (read-model.md "Risks"). Branch
  `feat/events-point-in-time` has the edits written; it needs its checks run and the owner to
  decide (point-in-time: `architect` review).
- **Backtests page**: the reads are on GraphQL (RM9); the page needs mockups first.
- **Options rollups folder split**: `features/rollups/options/` is at 8 of 10 modules; plan the
  split by kind before the next group.
- **IB-B licence hiding**: the API hides `personal`-licence features from other users (LV
  table, IB-B).
- **Empty distribution on gap sessions**: `Query.distribution` on a session with no partition
  shows an empty distribution; say UNKNOWN (`NO_PARTITION`) instead.
- **Ideas list on the feature table**: the top-ideas list still has its own columns (WEB 4
  `PENDING`); move it to `widgets/feature-table`.
- **A final Sonnet harness dry run**: brief a Sonnet implementer on a small page read end to end
  (`add-graphql-field`) and fix the gaps it hits.

## Live verification (LV): our data against IBKR, read-only (ADR 0026)

| # | Delivers | Status |
|---|---|---|
| LV1 | IB Gateway session source (`sources/vendors/ibkr/`, read-only facade over `ib_async`; session sources in the framework; IBKR pacing), the `verify` task (`tasks/verification/`: sample, checks with the reconciliation tolerances, `verification/ibkr`), nightly step (SKIPPED when the gateway is down), quality check `verification`, email section, read-only fitness test + import contract. **Owner action:** set up IB Gateway (README, "Live verification") and set `[ibkr] enabled = true` | **done** |
| LV2 | A trend of verification failures per check in the email; IBKR as the source of `option_symbols` IV history once a subscription is in place | later |
| IB-A | IBKR enrichment (ADR 0028): `ibkr-contracts` (conids, monthly + new names), `ibkr-iv` (IB's IV / HV history backfill, resumable and capped; nightly snapshot), `ibkr_iv@v1`, `iv_rank` / `iv_percentile` with `iv_rank_source` (IBKR first, ours as the fallback), `licence` on features (catalogue, API). **Owner action:** the backfill (README, "IBKR enrichment"; ~23 h, resumable) | **done** |
| IB-B | The API hides `personal`-licence features from users other than the owner (when there are any) | later |

## Restructure (R): one owner per responsibility (ADR 0019)

Each PR moved code to its target owner in `architecture/ownership.toml`, shrank
`architecture/known_violations.toml` and enabled its `pending_contract`s in `pyproject.toml`.
Baseline identical throughout. **The track is complete:** the ratchet is empty, every planned
contract is enforced, and a fitness test keeps it so (new exceptions need an ADR).

| # | Delivers | Status |
|---|---|---|
| R1 | Ownership registry, shrink-only ratchets (`make ownership`, `make dupes`), fitness tests, ADR 0019 | **done** |
| R2 | `algotrade/data/` read layer + one snapshot rule (`reference`, `prices`, `events`, `chains`); fixes backtests before the first snapshot (flagged `survivorship_bias`) and reads events by event date; backtests pin `as_of` = launch time (ADR 0007 amended); contracts R1, R2 | **done** |
| R3 | `IngestRun` (the ingest loop, written once) + task registry (`jobs/` → `tasks/`); CLI (`run <task>` + the named commands) and nightly dispatch through the registry; settings defaults applied once; `cboe.workers` honoured | **done** |
| R4 | Source registry from `sources.toml` + shared cross-process rate limiter (retry cap, circuit breaker) + run lock (`--wait`, exit 3, job recovery) + index lock; vendor helpers out of tasks; contract R3 | **done** |
| R5 | Nightly workflow (`workflows/`): isolated steps with status + duration, hard dependencies vs data preconditions, quality + purge always last, COMPLETE / PARTIAL / FAILED rule in one place; exchange calendar `core/time/calendar.py` (NYSE holidays, early closes, `last_closed_session`); catch-up of missed sessions (capped, chains latest only); screens submitted as `screen` jobs (`universe_pre_snapshot` in the audit); failure notification + `var/logs/nightly-latest.json` (`config/site/nightly.toml`); launchd `RunAtLoad` false; apps run jobs through `services.jobs.run_job`, contract R5 | **done** |
| R6 | Typed site settings: one loader (`config/site/settings.py`) for every `config/site/*.toml`, frozen dataclasses, unknown keys and bad values fail with their path; environment read only in `config/env.py` (the storage factory takes the URL); screens and backtests open / close run records through `storage.runs` (`start_run`, `RunRecord.finish`); golden CSVs are a registered fixture source; OHLCV checks in `core/validation/bars.py`, contract R4 in full; typed table schemas (declared column types, cast on write, `schema_version` stamped, older files cast on read, ~64k-row groups + page index); known violations 11 → 0, no pending contracts | **done** |

## Feature store (FS): features as named, documented columns (ADR 0023)

Pure refactors for stored data unless a step says otherwise (FS3 re-versions four groups). The
catalogue of every feature is [data/features.md](data/features.md).

| # | Delivers | Status |
|---|---|---|
| FS1 | Per-feature definitions (`Feature`: entity, kind, dtype, unit, description, null meaning, valid range, categories, inputs, version) declared in feature groups (`FeatureGroup`, the eight rollups, byte-identical output); one registry (`GROUPS`, `FEATURES`, `feature(name)` lookups); generated catalogue `docs/data/features.md` (`make features-doc`) with fitness tests | **done** |
| FS2 | Inputs through `data/`: features ask `data.feature_inputs` by table name (each table's read in its owner; generic stored-group reader); `features/` never imports storage or a domain reader (import-linter); ownership `feature-input-loading` | **done** |
| FS3 | Expression features, virtual by default (owner decisions: TOML definitions, `materialise = true` opt-in, per-feature versions, float32 when re-versioning): a typed formula language (`features/expressions/`, never Python `eval`), `config/site/features/*.toml` through the one settings loader, `feature.<name>` selection fields and `FeatureView` columns computed on read from only the stored columns needed, materialised expressions stored by the `rollups` task (`div_yield@v1`, read by `iv30@v1`); liquidity class, `div_yield`, `market_cap`, `pct_from_high/low_52w`, `iv_hv_spread/ratio` moved to expressions, new `near_52w`; `price_stats@v2`, `dividends@v2`, `fundamentals@v2`, `iv_history@v2` with float32 columns (`liquidity_class@v1` dropped); `algotrade-ingest retire-features`. Exact on real data (116k rows, 10 sessions: every class and tier identical; numbers within float32 rounding). **Owner action:** `algotrade-ingest rollups --from 2024-10-03 --to <last session>` (backfills the v2 groups and `div_yield@v1`), then `retire-features --group <name>@v1 --dry-run` and without `--dry-run` for `price_stats`, `dividends`, `fundamentals`, `iv_history`, `liquidity_class` | **done** |
| FS4 | User expression features (L4, `config/users/<id>/features/*.toml`): the site schema through the one loader, always virtual (`materialise` rejected); `feature.<name>` resolves user-first in the user's catalogue, never shadowing a site feature; selections / configs of that user may name them and the definitions they read join the config hash; `GET /features` returns the caller's catalogue with `scope` / `owner`; Explore tickers / compare accept them; `algotrade-backtest config validate-features` | **done** |
| FS5 | Features by name for group features: unique group-independent names, copies become references | next |
| FS6 | `cross_section` features (ranks, z-scores within the universe or a sector) | later |
| FS7 | Feature quality: null rates and `valid_range` checks in nightly (out-of-range values reported, never clipped) | later |
| FS8 | New grains (`market`, `contract`, `sector`) when a feature needs one; market: RG track (ADR 0047) | later |

## Market regime (RG): recession risk and market stress as features, a regime gate for sizing (ADRs 0047-0049)

Plan: [market-regime-plan.md](market-regime-plan.md). Phases 1 and 2 run in parallel; every PR
branches from `main`. `architect` review after RG1a, RG1d, RG2a, RG3 and RG4. Reference data:
`config/site/regime/` (the twelve episodes, the indicator cards).

| # | Delivers | Status |
|---|---|---|
| RG0 | ADRs 0047-0049, this track, `config/site/regime/{episodes,cards}.toml`, the plan doc | **done** |
| RG1a | `FeatureGroup.entity`, the `rollups/market/` table family, `MKT` / `IDX` / `MACRO` ids, `field_source`, inputs `universe` and `instruments/symbol_ids`, catalogue "Market features", the expression entity check (a toy market group: backfilled rows equal nightly rows) | next |
| RG1b | The `market-rollups` task and its non-critical step before the screens | **done** |
| RG1c | Market groups `trend` and `breadth` | next |
| RG1d | `cross_asset` group: turbulence and absorption ratio (`eigvalsh`) in `quant/covariance.py` | next |
| RG1e | Market reads and `Query.regime` (label UNKNOWN until RG3) | **done** |
| RG1f | Design-system pieces: `ScoreMeter`, `IndicatorRow`, `Chart.bands` | next |
| RG1g | `entities/regime` (`useRegime`, `useRegimeBands`, `RegimeChip`, `toChartBands`), the top-bar chip, the page header and cards | next |
| RG1h | Per-instrument episode features `episode_behaviour@v1` (`features/rollups/price/episodes.py`; `Input.windows` for each episode's own closes) | **done** |
| RG2a | The `macro/series` table, `data/macro.py`, `Input.ids`, `config/site/macro.py` settings | next |
| RG2b | FRED / ALFRED and published-file adapters against recorded payloads | next |
| RG2c | The `macro` task, step and `check_macro`; then a detached backfill | next |
| RG3 | The macro group; regime expression features (with an `ncdf` built-in for the probit); the regime group; Pagan-Sossounov dating in `quant/turning_points.py`; the episode scorecard in `services/evaluation` | **done** (RG3a: the macro, indicator and regime groups; RG3b: EBP / OFR FSI / EPU, the probit, the scorecard: `make regime-scorecard` after the macro backfill; open: the Pagan-Sossounov published-table check) |
| RG4 | Overlays (`engines/overlays/`), `Decision.PAUSED`, `[regime]` config, with-versus-without evaluation | in review (architect review pending) |
| RG5 | The embeddings (Ideas strip and paused section, results header, Explore and Backtests bands) and the full Regime page; before `[regime]` is turned on, the read model's picked count must exclude `PAUSED` (`services/read/screens/runs.py` `NOT_PICKED`) | next |
| RG6 | On-demand explanation: the text-model seam (ADR 0041 amended), `services/explaining`, `POST /regime/explain`, its cache | **done** |

## Swing levels and momentum (SW): support, resistance and momentum from daily bars

A small set the owner can explain in one sentence each and check against a chart. All from
stored daily bars (plus earnings dates and chain OI for two of them); no new vendor. Each is a
`FeatureGroup` or expression feature (ADR 0023; `.claude/skills/add-feature`). Values were
checked against TA-Lib and on charts (below). Existing features are reused, not
repeated: `sma_20/50/200`, `high_52w`, `low_52w`, `ret_20d`, `ret_60d`, `hv20`, `pct_vs_sma_*`.

| # | Delivers | Status |
|---|---|---|
| SW0 | Spec [data/swing.md](data/swing.md): definitions, worked examples, null rules; `features/rollups/` split by kind (`price/`, `options/`, `corporate/`) so the new groups need no `price_stats` re-version | **done** |
| SW1 | Momentum and volatility: `atr_14`, `atr_pct`, `rsi_14`, `ret_5d`, `rel_volume` (volume / 20-day average), `high_20d`, `low_20d`, `high_50d`, `low_50d`, `range_20d_pct`, `trend_state` (group `momentum@v1` + expression features in `config/site/features/swing.toml`) | **done** |
| SW2 | Levels: `swing_high`, `swing_low` (most recent pivots), `dist_to_resistance`, `dist_to_support` (percent and in ATR) (group `swing_levels@v1` with pivot dates; distances are expression features) | **done** |
| SW3 | Setups as expression features: `breakout_20d`, `pullback_to_sma20` (`config/site/features/swing.toml`) | **done** |
| SW4 | `avwap_earnings` (VWAP anchored to the last earnings date) and OI-based `call_wall` / `put_wall` (strike with the most call OI above spot, the most put OI below spot; Cboe OI is end of day) (groups `anchored_vwap@v1`, `oi_walls@v1` with `wall_status`) | **done** |

SW0-SW4 are done and backfilled (2026-10-04): `momentum@v1` and `swing_levels@v1` over 501
sessions (2024-10-03..2026-10-02); `anchored_vwap@v1`, `oi_walls@v1` and `earnings@v1` hold
the 2026-10-02 session only, by design. Chart check done (2026-10-05): ATR and RSI match
TA-Lib on AAPL, SPY, TSLA, NVDA and QURE; pivots, OI walls, rel_volume, the highs and lows and
`trend_state` match an independent recomputation; charts rendered to `var/charts/`.

**Parked:** the wider options positioning set (gamma and delta exposure, hedge wall, flow
ratios, skew and rank, implied move, GARCH rank, dark pool / short volume). Drafts kept, not
scheduled: [data/positioning.md](data/positioning.md) and
[ADR 0031](adr/0031-options-positioning-features.md) (proposed, not accepted). Revisit when a
screener needs one of them. If DPI comes back, FINRA daily short-sale volume (published after
the close, not real time) is the likely source.

## Phase 0 follow-ups (the architecture is the target; these close the gaps)

| # | Item | Lands in |
|---|---|---|
| F1 | Configured backtests save results (`results/backtest_equity`, `results/backtest_fills`) and record dataset versions on the run | **done** (1.1) |
| F2 | `ALGOTRADE_USER` env var as the default for `--user` | **done** (1.1) |
| F3 | A single `InstrumentView` reader (reference + selected rollups, as of a date) | **done** (1.1) |
| F4 | Job idempotency keyed by (kind, config hash, session), so editing a config and resubmitting runs again | **done** (1.1) |
| F5 | Reject secret-like keys in config files | **done** (1.1) |
| F6 | DuckDB as the query engine and catalog (storage is Parquet read with pyarrow today) | when queries need it |
| F7 | `rebalance_selection` (re-evaluate a backtest's selection at an interval) | **done** (2b.5) |

## Open decisions

| Decision | Options | Status |
|---|---|---|
| Earnings-calendar source | Nasdaq public calendar (free, no key, all US, tested) | **decided: Nasdaq**; cross-check source optional |
| Massive API key | Free tier account | **done** (in `.env`; rotate it, it was shared in chat) |
| SEC EDGAR contact | A contact email in the user agent (SEC policy) | **done** (`ALGOTRADE_SEC_CONTACT` in `.env`) |
| FIGI-based `instrument_id` | Keep symbol ids, or migrate to FIGI ids | **decided: FIGI ids** (ADR 0018); owner runs `migrate-ids` on the local store |
| Cboe terms | Confirm acceptable use of the delayed feed | owner to confirm |
| User identity scheme | Labels now; auth provider in phase 4 | **decided: site registry + Supabase Auth** (ADR 0040; roadmap ID1-ID4) |
| Production job queue | Redis/RQ, Postgres-backed, cloud queue | local runner until hosting |
| Hosting target | VM + docker-compose, a container platform | local only |
