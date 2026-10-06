# Architecture Decision Records

Each ADR records one decision: its context, the decision and its consequences. To change a
decision, add a new ADR that supersedes the old one, and update the old one's status line.
Do not rewrite history. Use `.claude/skills/write-adr` to add one.

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-layered-architecture.md) | Layered architecture enforced by import-linter | accepted |
| [0002](0002-fill-model.md) | Decide at close, fill at next open | accepted |
| [0003](0003-golden-master-baseline.md) | Golden datasets and a golden-master results baseline | accepted |
| [0004](0004-apps-and-shared-libraries.md) | Four apps, shared libraries, one repo | accepted |
| [0005](0005-ingestion-is-the-only-writer.md) | Ingestion is the only writer of market and feature data | accepted, amended by 0027, 0028 |
| [0006](0006-storage-grains-and-adapters.md) | Storage by data grain, Parquet (DuckDB-readable), swappable adapters | accepted |
| [0007](0007-point-in-time-data.md) | Point-in-time data and versioned features (`as_of` is a version pin; one snapshot rule) | accepted, amended |
| [0008](0008-backtests-read-only-from-stores.md) | Backtests read only from stores | accepted |
| [0009](0009-generic-instrument-model.md) | Generic instrument model (futures-ready) | accepted |
| [0010](0010-jobs-model.md) | Long-running work is a job | accepted |
| [0011](0011-design-system-first-ui.md) | Design-system-first UI | accepted |
| [0012](0012-data-vendors.md) | Several data sources, free first, IBKR for derivatives | accepted |
| [0013](0013-universe.md) | The universe | accepted |
| [0014](0014-cboe-options-source.md) | Cboe delayed feed for option chains; limited raw retention | accepted |
| [0015](0015-configs-selections-users.md) | Configs, selections and users | accepted |
| [0016](0016-four-data-layers.md) | Four data layers; instrument level as daily snapshots | accepted |
| [0017](0017-golden-data-through-ingestion.md) | Golden datasets load through ingestion into a separate fixture store | accepted |
| [0018](0018-figi-instrument-ids.md) | FIGI-based instrument ids through one symbol resolver | accepted |
| [0019](0019-ownership-and-boundaries.md) | Every responsibility has one owner; ownership registry and boundary guardrails | implemented |
| [0020](0020-directory-layout.md) | Directory layout: one kind of thing per folder, declared in a layout registry | implemented |
| [0021](0021-option-pricing-conventions.md) | Option pricing conventions: BSM, calendar/365 time, Treasury rates, IV failure codes; IV30 method, dividend yield, IV rank (2b.3 addendum) | accepted |
| [0022](0022-atomic-run-publication.md) | A run's table writes publish atomically: pending until COMPLETE / PARTIAL commits them all, FAILED publishes nothing; `as_of` sees a run from its commit | accepted |
| [0023](0023-feature-store.md) | Feature store: per-feature definitions (kind, dtype, unit, null meaning, range) in feature groups, a generated catalogue, inputs asked of `data/` by table name; steps 3-7 (features by name, expressions in config, virtual by default, quality, new grains) recorded | accepted (steps 1-4 implemented) |
| [0024](0024-api.md) | API v1: a read-only FastAPI over `services.explore`; thin routes, pydantic schemas as the OpenAPI contract | accepted, amended by 0028, 0029, 0037 ("Explore queries" superseded by 0037: `services/explore` deleted in read-model PR 10b) |
| [0025](0025-frontend-architecture.md) | Frontend architecture: layered (app, pages, widgets, features, entities, shared), component-only web app; TRADER / ADMIN workspaces; enforced by ESLint, Stylelint, layout and design-system checks | accepted, amended by 0037 |
| [0026](0026-live-verification-ibkr.md) | Live verification against IBKR, read-only by construction (facade, fitness test, gateway setting); session sources; the `verify` task, quality check and email section | accepted |
| [0027](0027-vendor-sources-shared-package.md) | Vendor sources as a shared package (`libs/sources`, `algotrade_sources`): batch use by ingestion, live read-only use by the API (quotes, 0028), never by backtests; amends 0005 | accepted |
| [0028](0028-ibkr-enrichment-source.md) | IBKR as an enrichment source, read-only: conids and IB's IV / HV history (backfill + nightly snapshot), `ibkr_iv@v1`, `iv_rank` with a labelled fallback to ours, `licence` tags on features | accepted |
| [0029](0029-rule-screener.md) | Rule screener (`impl = "rules"`): HARD (strict) / SOFT (tolerance band) / SCORE criteria, missing data → SKIPPED, distance-from-threshold score (100 = every threshold met), run summary with narrow misses, tiers / flags / classify; versioned user configs (immutable `v<N>` + draft, pinned `extends`); API writes user configs only via `services/authoring` (amends 0024); `results/rule_screen*`; preview == nightly | accepted |
| [0030](0030-rule-screener-simplification.md) | Rule screens: one list of criteria (no selection; the base gates are HARD criteria), missing data never skips (HARD missing = REJECT, SOFT / SCORE missing cost points), no tiers / classify / label, `in` for text only, near-52w as `dist_52w`; amends 0015, 0029 | accepted |
| [0031](0031-options-positioning-features.md) | Options positioning features (gamma / delta exposure, walls, flow, skew, implied move) are daily estimates from stored chains with a stated dealer convention; definitions in `docs/data/positioning.md` | proposed |
| [0032](0032-screener-review-table.md) | Screener results are the default surface; one review table over a rule screen's stored run (decision, criteria, display columns, catalogue features, new / dropped); column choices are a per-user view in `preferences.toml`, not part of a screener version; extends 0029, 0030 | accepted |
| [0033](0033-screeners-run-nightly-and-on-request.md) | Every screener runs nightly (no schedule switch: every site preset and every finalised user screen); a screener can be run on request from the API for the latest session, results stored like the nightly's; the API's one narrow write path (`services/ondemand`, `screen` jobs only, under the writer lock); amends 0029, 0005, 0024 | accepted |
| [0034](0034-instrument-descriptions.md) | Instrument descriptions: a capped nightly pull into `instruments/description` (stocks from Massive's ticker overview, ETFs from SEC prospectus objectives); nightly only, no on-demand API write | accepted |
| [0035](0035-etf-holdings.md) | ETF holdings: one `HoldingsSource` shape with issuer adapters (State Street and iShares daily files, SEC N-PORT as the universal fallback), the `holdings/etf` grain (fund x holding x as-of date), tickers linked through `SymbolResolver` (N-PORT via CUSIPs), a weekly slot per fund in the nightly, `GET /instruments/{id}/holdings`; extends 0012, 0013, 0027 | accepted |
| [0036](0036-session-strictness-for-reads.md) | Reads serve one session: every read resolves one session (requested, else latest with bars); session-grain facts are read for exactly that date or are UNKNOWN with a reason, never an older partition; a screener with no run for it is NOT_RUN (no Ideas lookback); snapshot, event and issuer-dated tables keep their one rule and disclose the date; extends 0007 | accepted |
| [0037](0037-domain-read-model-served-by-graphql.md) | A domain read model (`services/read`, one loader per object, one `ReadContext`) served by GraphQL (Strawberry, thin types, dataloaders, limits, SDL snapshot; web: graphql-codegen client preset over TanStack Query); REST only for writes, jobs, health, live, preview, files, admin (shrink-only GET allow-list); amends 0024, 0025 | accepted |
| [0038](0038-catalogue-named-values.md) | Per-instrument, per-session values are catalogue features read by name (`FeatureValue` + `FeatureInfo` + UNKNOWN), never typed fields; facts computed on read become stored features; format from the catalogue; the browser derives no fact from raw rows; one table widget with column factories; extends 0023, 0032 | accepted |
| [0039](0039-ingestion-workflows-dependencies-and-acceptance.md) | Ingestion workflows by cadence (`market-daily`, weekly `reference`, `enrichment`); steps declare `needs` and run only when those SUCCEEDED; each step SUCCEEDS or FAILS by a declared acceptance rule (no PARTIAL workflow status); a failed critical step holds the workflow and later sessions back, retried hourly from where it stopped; snapshot steps past their day are waived only by hand; reads default to the latest SUCCEEDED session; amends R5, 0033, 0034, 0035, 0036 | accepted, amended 2026-10-05 |
| [0040](0040-identity-and-roles.md) | Users declared in `config/site/users.toml` with a role (`admin`, `trader`; single-user defaults without the file), configs belong to declared users, Supabase Auth verified offline behind one `Authenticator` seam (email -> registry user; no `/auth` routes, no password material), `Query.viewer` feeds the one role-gating seam `guard.ts`; closes "User identity scheme", extends 0015, 0024, 0025, 0029, 0037 | accepted, amended 2026-10-05 |
| [0041](0041-natural-language-screener-drafts.md) | Natural-language screener drafts: a sentence becomes a draft rule screen through one `TextModel` protocol (`services/drafting`) and one OpenAI-compatible adapter (`algotrade_sources/llm`, the provider by `config/site/llm.toml` `base_url`, the key only from the environment, off by default); the prompt is the sentence and the catalogue; invented fields are dropped with a reason and the rest validated as finalise; `POST /screeners/{id}/draft-from-text` returns a draft the Builder loads, never a write or a run; extends 0027, 0029, 0037 | accepted |
