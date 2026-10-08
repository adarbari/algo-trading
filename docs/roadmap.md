# Roadmap

## Now / Next

The pickup list a fresh session reads first. A PR that opens or closes an item updates it.

**Running** (check `make status`; verified 2026-10-05 05:40): nothing long-running. IBKR IV history backfill finished 2026-10-05 05:30 (all 4,200 names: 4,197 OK, 3 genuine NO_DATA; `ibkr_iv@v1` rollups over 502 sessions, rank FULL for 4,789 of 5,415 names on 2026-10-02).

**Next**
- **Market regime (RG, ADRs 0047-0049): code done** except the Backtests page items; owner actions (FRED key, macro backfill, rollups, scorecard review, `regime@v3` run, `make web-build`) in [RG details](#market-regime-rg-details).
- **The Guide (GD, ADR 0051):** GD1-GD3a done, GD3b, GD4a, GD4b and GD5a (regime reads) in review (`no-automerge`); next GD3c, GD5b ([GD details](#the-guide-gd-details)).
- **Event sensitivity (EV, ADR 0050):** EV0, EV1, EV7a done; next EV2; owner action: `make web-build`, the detached earnings backfill ([EV details](#event-sensitivity-ev-details)).
- **Workflows (WF, ADR 0039):** WF1-WF3 done; next WF3b, WF4; owner action first: the 2026-10-05 bars, rollups and screens ([WF details](#workflows-wf-details)).
- **ETF holdings (ADR 0035) and descriptions (ADR 0034):** after merge run `algotrade-ingest etf-holdings` once, then `algotrade-ingest descriptions --only funds --force` and stocks in chunks; ETF descriptions gap ([ETF details](#etf-holdings-etf-details), [Descriptions details](#descriptions-details)).
- **Read-model track (RM, ADRs 0036-0038): done**; open: the Ideas Expiry DTE backfill (owner action) and the Market.history perf item ([RM details](#read-model-rm-details)).
- **Identity (ID, ADR 0040) and hosting (H1, ADR 0044):** ID1-ID4 and H1 done; owner actions (Supabase, Tailscale Funnel, `make web-build`), next ID5 ([ID / H details](#identity-and-hosting-id--h-details)).
- **Backfills pending** (past sessions read UNKNOWN until run): volume, financials, TA bands and trend, options positioning, call wing and dividends ([Backfills details](#backfills-pending-details)).
- **Mobile UI (MU, ADR 0052): MU1-MU3 done, track closed** (MU2 #294 merged; MU3 #303 in review: the owner picks the filter bar's narrow form); owner action: `make web-build`, a phone pass ([MU details](#mobile-ui-mu-details)).
- **Pipeline (CI and local speed, [ci.md](ci.md) "Pipeline"):** P1, P1b, P1c, P1d, P2, P2b, P3a, P3b, P4, P4b, P5 done; Python PR 5.0 min after P1c (unit-a 4.5 min the long pole), P1d (#296) spread the rollup groups over two shards, re-measure on the next Python PR ([Pipeline details](#pipeline-details)).
- **Edges (ED, ADR 0053; plan [edges-plan.md](edges-plan.md)): ED0, ED1 done** (six edge documents, [edges.md](edges.md)); next ED2, the outcomes grain; `architect` reviews ED2 and ED3 ([ED details](#edges-ed-details)).

**Facts**
- IBKR fundamentals are not permitted on this account (error 10358): share-class counts stay SEC. Optional IBKR pace trial: `[ibkr] historical_min_interval_s` 5, then 3, watching timeouts and error 162 (the backfill ran at 10 s, IV only, about 6 names a minute). The nightly keeps the history current (100 names a night of any new gap).
- Massive's ticker overview has descriptions for stocks and ADRs, none for ETFs (free tier, checked 2026-10-04); ETF text is the SEC prospectus objective (~74% of ETFs). Massive: 5 requests a minute, so descriptions are capped at 100 stocks a night (ADR 0034). Company snapshots: `data.reference.companies` reads with `as_of=None`, so a past-dated `company-details --date` run would leak today's facts into backfilled features (`relative_strength@v1` sector); the loader should drop snapshots whose `knowledge_ts` is after the session (follow-up).
- Owner screener / VRP decisions: ADR 0029, ADR 0030 (rule screens: no selection, missing data never skips, no tiers / classify / labels; `vrp_scanner` v3) and `docs/screeners/vrp-scanner.md`. Natural-language drafts (ADR 0041) ship off: `config/site/llm.toml` `enabled = true` + a provider's `base_url` / `model` (Ollama, Gemini, Groq, OpenRouter examples in the file) and `ALGOTRADE_LLM_API_KEY` in `.env` turn on the Builder's "Describe it" box. **Field guide (ADR 0041 amended 2026-10-06):** `config/site/field_guide/*.toml` (37 fields, 7 situations, sourced) is in the prompt and rendered to `docs/data/field-guide.md`, because drafts chose the right fields but poor thresholds; the Builder shows it under each criterion (`FeatureInfo.guide`; "How to read it": the reading, each intent with a Use button, the caveats); coverage: every phrased or site-screened field must have an entry (fitness test), `add-feature` ships one per feature, `make features-doc` lists the unguided rest (167 of 218 fields guided, 2026-10-06: every liquidity, option, IV, price-level, momentum, swing, wall and episode field; the rest are statuses, dates and filing bookkeeping); next: a stored pending-deal flag (`add-feature`) replaces the `atr_pct` proxy of the takeover situation, and an evaluation of recorded draft sentences against the guide's thresholds. A v3 run stores a row per snapshot instrument (about 11.4k, was about 4.2k).
- Harness audit: last 2026-10-04 (`/audit-harness`; `/start` flags when older than 30 days; fixes log: [history.md](history.md)). Session review: last 2026-10-07 (`/review-sessions`; `/start` runs it when the date is before today; the day's top 3 and their fixes go in [history.md](history.md)).

---

## Track details

The full text of each Now / Next line: status, commands and owner actions. A PR that moves a track edits its line above and its subsection here.

### Market regime (RG) details

**Market regime (RG, ADRs 0047-0049): code done** except the Backtests page items (its regime bands, by-regime split and with / without toggle wait for the Backtests page mockup: [RG section](#market-regime-rg-recession-risk-and-market-stress-as-features-a-regime-gate-for-sizing-adrs-0047-0049); plan [market-regime-plan.md](market-regime-plan.md)). **Owner actions**, in order: (a) get a free FRED API key and set `ALGOTRADE_FRED_API_KEY` in `.env` (the published sources, Stooq SPX, EBP, OFR FSI and EPU, work without it); (b) the first macro backfill, detached ([README](../README.md) "Long runs"): `nohup sh -c '.venv/bin/algotrade-ingest run macro --since 1970-01-01 > var/logs/macro.log 2>&1; echo "exit=$? $(date -u +%FT%TZ)" > var/logs/macro.status' >/dev/null 2>&1 &`; (c) then `algotrade-ingest run market-rollups --from 2024-10-03 --to <last session>` (already run once for `market_macro@v2` / `regime@v1`: after PR 230 merges, run `algotrade-ingest run market-rollups --from 2024-10-02 --to <today> --only market_trend@v2,market_macro@v3,regime_indicators@v1,regime@v2` at once: `market_trend@v2` has no rows until then, regime rows keep v1-based values and `_changed` is null for 5 nights; the 1971 to 2024-10-01 backfill only after the calendar PR; superseded tables are read by nothing) and `algotrade-ingest rollups --from 2024-10-03 --to <last session> --only episode_behaviour@v1`; (d) `make evaluate` prints the regime scorecard and, once history exists, the probit coefficients to paste into `config/site/features/regime.toml`; (e) set `[regime] enabled = true` in the site config only after the scorecard is reviewed (RG4 shipped it off; the Ideas picked count and the results already exclude `PAUSED`); (f) `make web-build` for the hosted site; (g) review the Storybook stories for ScoreMeter and IndicatorRow, and the Backtests page mockup (it unblocks the last RG5 items). **RG8 (`regime@v3`, macro tiers; draft PR, `architect` review first):** after merge run, detached, `algotrade-ingest run market-rollups --from 1971-01-04 --to <last session> --only regime@v3` (about 17 minutes); until then every regime read is UNKNOWN; then delete `rollups/market/regime@v1` and `@v2` by hand; a user config naming `market.regime@v2.label` must say v3. Follow-up (2026-10-06): show `scores.macroEarly` / `macroConfirming` on the Regime page (the API and the explanation facts carry them), so a CAUTION carried by the curve's year of memory is visible while the "inverted now" curve card reads off.

### The Guide (GD) details

**The Guide (GD, ADR 0051; spec [ui/guide.md](ui/guide.md)): GD1, GD2, GD3a done** (spec, ADR, `add-guide-content`, prose check `architecture/web_prose.toml`; `InfoButton` / `HelpDrawer`; the Guide read model and `Query.guideIndex` / `guideField`); **GD3b in review** (top-bar Guide link and `?`, `/guide`, `/guide/fields`, `/guide/fields/<name>`, the Explore Field guide tab redirects for one release; mockup https://claude.ai/artifact/1HSXjM1zsiKzTe6fak8ieZ). Next GD3c (the drawer on feature-table headers), GD4-GD6 as the spec's section 6. **GD4a in review** (server side, `no-automerge`: architect review, the owner reads the playbook text): one `config/site/guide/playbooks/<id>.toml` per site preset with `[asks]` per criterion, `Query.guidePlaybook(id)` / `guideSituation(slug)`, Guide prose linked at catalogue names (`GuideProse`); next GD4b, the playbook and situation pages. **GD4b in review**: `LinkedProse` in `@algotrade/ui`, `/guide/playbooks[/<id>]`, `/guide/situations[/<slug>]`, linked reads and caveats on the field page, a Playbook link on every preset (Screeners list, Builder header). **GD5a in review** (server side, `no-automerge`: architect review): `Query.guideIndicator(key)` / `guideEpisode(slug)` (the regime cards and episodes without session values, linked prose, before-lines tied to episodes); next GD5b, the indicator and episode pages and the Regime page's drawers.

### Event sensitivity (EV) details

**Event sensitivity (EV, ADR 0050; plan [event-sensitivity-plan.md](event-sensitivity-plan.md)): EV0 done** (the ADR, the plan, the scope list `config/site/events/scope.toml` with the owner's 104 names); EV1 done (`known_from` and the one read rule, the macro release calendar, 8-K filings with the Item 2.02 earnings rows, the bar backfill from 2018, the leveraged-fund reference link); EV7a first (owner decision 2026-10-07: user value before EV2): EV7a done (the read model, the design-system components, and the Explore Events tab, chart markers and the TRADER Calendar page; **owner action:** `make web-build` for the hosted site); then EV2 ([EV section](#event-sensitivity-ev-what-moves-a-name-and-what-is-coming-adr-0050)). **Owner action:** the detached earnings backfill (README "Long runs"); after EV1d, the bar backfill.

### Workflows (WF) details

**Workflows (WF, ADR 0039):** WF1-WF3 done; next WF3b, then WF4 ([WF section](#workflows-wf-dependencies-succeed-or-fail-cadence-adr-0039)). **Owner action first:** Massive returned 403 for the 2026-10-05 bars and that nightly finished PARTIAL, so nothing retries it: once Massive serves the day run `algotrade-ingest bars --date 2026-10-05 --wait`, then `rollups --date 2026-10-05 --wait`, then the 2026-10-05 screens (until then lookback rollups from 2026-10-06 compute over the gap).

### ETF holdings (ETF) details

ETF holdings (ADR 0035, accepted): after merge run `algotrade-ingest etf-holdings` once (reads the ~1,140 covered funds, plus the non-optionable N-PORT funds with a 20-session dollar volume of $5M or more, up to ~900 (`fallback_scope = "liquid"`, `fallback_min_adv_usd`): about 1.5 hours per 1,140, extrapolated from the sample, mostly SEC header lookups; or let the nightly fill it, 200 funds a night, 6 weekday nights), ProShares funds (173, the VIX funds UVXY / SVXY / VIXY and the leveraged and inverse ones) are read from their daily file by the same run (weights are shares of gross exposure, ADR 0035), then the Overview tab renders `<HoldingsPanel symbol onSelectSymbol>` (`widgets/holdings-panel`) for ETFs. **ETF descriptions** for funds with no SEC prospectus objective: SPY, DIA, GLD, SLV, USO, IBIT, SOXL and the like (unit trusts, commodity and crypto trusts, some leveraged funds); 246 of the 1,464 ETFs trading $5M or more a day have none (2026-10-05). The SEC series match closes 83 of them; the rest need issuer pages (iShares and State Street page text for IBIT, SLV, SPY, DIA; ProShares and Direxion 497K or pages for SOXL, TSLL, UVXY) and an ADR.

### Read model (RM) details

**Read-model track (RM, ADRs 0036-0038, [api/read-model.md](api/read-model.md)): done** (RM1-RM10b; RM10b deleted `services/explore`: the Builder's dry runs are `services/preview` over the request's `ReadContext`, READ 2 covers every use case and the API). Every page reads GraphQL; REST is writes, job polling, health, live quotes and preview POSTs. **R (RM5):** the Ideas Expiry DTE column is UNKNOWN until `nearest_expiry@v1` is backfilled (the RM3 owner action). What the track left open is the [deferred list](#deferred-from-the-rm-track). **Owner action (RM3):** after merge run `algotrade-ingest rollups --from 2024-10-03 --to <last session> --only nearest_expiry@v1` (only sessions with a stored chain get rows; the store holds chains from 2026-10-02, so this takes seconds); the nightly computes it from then on. **Next (perf):** Market.history's 13,500-partition read must get under 5 s cold (14.2 s serial after the `ParquetFile` reader, synthetic, loaded machine; `make perf` ceiling 15 s): time the real `rollups/market/regime@v2` table on a quiet machine; only if still over 5 s, add a bounded executor as a new `parallel-partition-reads` responsibility owned by `storage/backends/local.py`, the `job-execution` detect narrowed to job-specific symbols (`add-responsibility`).

### Identity and hosting (ID / H) details

**Identity (ID, ADR 0040, Supabase Auth; outside users within a week of 2026-10-05):** ID1-ID4 done (the registry; `apps/api/algotrade_api/auth/` verifies Supabase tokens, email (+ optional pinned `subject`) in the git-ignored `config/users/<id>/identity.toml` -> registry user, 401 / 403 on every route but `/health`, `Query.viewer`; ID3: the web signs in through `@supabase/supabase-js` in `src/shared/api/auth.ts`, `/login`, `guard.ts` reads `viewer`, the web's `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY` go in `apps/web/.env.local`; ID4: `?user=` retired: writes act for the caller, an admin names another user in the `X-Act-For` header, the preview POSTs in a body `user`; `services/authoring` refuses undeclared users; the nine Admin GraphQL fields are `AdminOnly`, a trader gets `FORBIDDEN`; `GET /screens/{id}/run/{job}` is 403 for another user's job; `ALGOTRADE_CORS_ORIGINS`). **Owner action:** the Supabase project exists and passed the [configuration.md](configuration.md#environment) checklist on 2026-10-05 (sign-ups off, confirm email on, anonymous off, ES256 keys): set `ALGOTRADE_AUTH=supabase` in `.env`, write each user's `config/users/<id>/identity.toml`, and declare outside users in `config/site/users.toml`. **Hosting (H1, ADR 0044): done** in code: the owner's Mac behind Tailscale Funnel, one origin (the API serves the built web from `ALGOTRADE_WEB_DIST`, `make web-build` -> `var/web`), `algotrade-api schedule` (launchd agent, `127.0.0.1:8000`), `make doctor` checks the build and the installed agents, runbook [hosting.md](hosting.md). **Owner action**, in order ([hosting.md](hosting.md)): `make web-build`; `.env`: `ALGOTRADE_AUTH=supabase`, `SUPABASE_URL`, `ALGOTRADE_WEB_DIST=var/web`; `.venv/bin/algotrade-api schedule` and run the install commands it prints; install Tailscale (Standalone app or Homebrew `tailscaled`: the App Store app has no Funnel), sign in, enable MagicDNS + HTTPS certificates and the `funnel` node attribute; `tailscale funnel --bg localhost:8000`; Supabase Site URL + Redirect URLs = the `https://<machine>.<tailnet>.ts.net` address; onboard users (Supabase Add user, `users.toml`, `identity.toml`). Redo `make web-build` after every web change. **ID5 (next, owner ask 2026-10-06):** onboarding as one API workflow instead of three hand steps (Supabase user, `users.toml` entry, `identity.toml`): an admin-only write that declares the user and their email through `services/authoring` and, once the Supabase project opens UI sign-ups, a signed-in but unregistered account requests access from the login page and an admin approves it; the registry stays the role authority (ADR 0040).

### Backfills pending details

**Backfills pending (past sessions read UNKNOWN until run).** **Volume features (`volume@v1`: `session_volume`, `dollar_volume`, `adv_shares_20d`, `volume_ratio_5d_20d`, `volume_z_20d`, `up_volume_share_20d`, `cmf_20d`; expression features `volume_dry_up`, `volume_climax`, `volume_bias`; field guide and phrasebook theme `volume`):** after merge run `algotrade-ingest rollups --from 2024-10-03 --to <last session> --only volume@v1` (reads `bars/1d` only: seconds a session, estimated); past sessions read UNKNOWN until then. Company financials (`financials@v2`, `feature.pe_ratio`, `feature.revenue_growth_yoy`; Explore Overview reads them): after merge run `algotrade-ingest shares --force` (about 30 to 40 minutes, resumable), then `algotrade-ingest rollups --from 2024-10-03 --to <last session> --only financials@v2,fundamentals@v3` (a few seconds a session, estimated; the same run as the TA track's list below, which also lists them), and spot-check a few names ([vendors.md](data/vendors.md) "SEC EDGAR company facts"). **TA track ([data/technical.md](data/technical.md)): bands and trend statistics (`bands@v2`: `close_std_20`, `ema_20`, `bb_width_pctile_252d`, `band_walk`; `trend_stats@v2`: `ret_120d`, `ret_252d`, `mom_12_1`, `ret_z_20d`, `close_streak`, `sma20_streak`, `tight_range_sessions`; expression features in `config/site/features/bands.toml`: Bollinger bands, %B, bandwidth, Keltner channel, squeeze, price z-score, ATR stretches, Donchian position; guide entries for every one):** after merge run `algotrade-ingest rollups --from 2024-10-03 --to <last session> --only bands@v2,trend_stats@v2,vol_stats@v1,volume_profile@v1,anchored_vwap@v2,financials@v2,fundamentals@v3,candle@v1` (reads `bars/1d` only; seconds a session, estimated), then `algotrade-ingest retire-features --group bands@v1` and `--group trend_stats@v1` and `--group anchored_vwap@v1`, then `--group financials@v1` and `--group fundamentals@v2` (v2 added `sma_150` and the Clenow regression trend quality the same week; at most a nightly of v1 rows exists; `financials@v2` adds the year-ago EPS TTM and the latest quarter's revenue and EPS for `eps_growth_yoy`, `revenue_growth_qtr_yoy` and `eps_growth_qtr_yoy`, `fundamentals@v3` the year-ago share count for `shares_change_yoy`; every expression reading them, `market_cap`, `pe_ratio`, `revenue_growth_yoy`, `ps_ratio`, `net_margin` and `payout_ratio` included, reads UNKNOWN for past sessions until the run, so run `algotrade-ingest shares --force` first and retire v1 / v2 only after spot-checking v2 / v3; the two groups read `instruments/shares`, not only `bars/1d`); past sessions read UNKNOWN until then. **Options positioning (`chain_flow@v1`: volume and open interest by right and the unusual-activity columns; `flow_history@v1`; `implied_move@v1`: the straddle's implied move into earnings or at 30 days; expression features in `config/site/features/positioning.toml`: put/call ratios, `implied_move_1sd`, `implied_move_vs_hv`, `put_otm_pct`, `put_breakeven`, `put_roc_annualised`; guide entries for every one; ADR 0031 accepted in part):** after merge run `algotrade-ingest rollups --from 2026-10-02 --to <last session> --only chain_flow@v1,flow_history@v1,implied_move@v1,skew@v1,skew_history@v1,iv_term@v1` (reads the stored chains, which start 2026-10-02; seconds a session, estimated); `flow_history@v1` ratios read null until 10 sessions of chains exist. Next in the track, one PR each: levels (`pivot_strength`, `retest`, `gaps`; `swing_levels` moves to `features/rollups/levels/`), `volume_profile` + `anchored_vwap@v2`, `relative_strength` (RS vs SPY and the sector ETF, universe momentum percentiles), the remaining options shape groups of [data/positioning.md](data/positioning.md) (`skew`, `iv_term`; GEX stays parked on the owner's P1 decision). Built since: the covered-call wing (`call_wing@v1`, expression features `call_otm_pct`, `cc_yield_annualised`, `call_strike_above_resistance`, `cc_resistance_cushion_atr`) and the dividend schedule (`dividend_schedule@v1`, `ex_div_before_expiry`, `ex_div_before_nearest_expiry`): after merge run `algotrade-ingest rollups --from 2024-10-03 --to <last session> --only call_wing@v1,dividend_schedule@v1` (call_wing needs the stored chains: sessions without a chain stay UNKNOWN; dividend_schedule reads every `events/dividend` partition once, and sessions before the first stored corporate-actions partition have no row).

### Mobile UI (MU) details

**Mobile UI (MU, ADR 0052; owner ask 2026-10-07): MU1 and MU2 done** (MU1: one tree for phones and desktops: `MasterDetail` for Explore and screener results, touch sizing under a coarse pointer, DataTable pinned key column, chart pinch / drag and zoom buttons, screener names as buttons. MU2, from the owner's phone test: the ingestion drilldown on `MasterDetail`, `Tooltip` on tap, `KeyHints` hidden on touch, the workspace switch moved from the top bar into the `AccountMenu` behind the viewer's name (two-row bar, about 100 px; ADR 0052 amendment), narrow tables show their `essential` columns with the picker for the rest, screener rows open on tap, Explore's Compare button opens the detail sheet; checks: ESLint rule 10, `Narrow` stories, the e2e `phone` project with an assertion per item; skill `responsive-ui`). **MU3 done, track closed** (#303; ADR 0052 amendment 2026-10-07 MU3): `FilterBar` (under `sm` the search and a "Filters · N" button share a row, the chips and the many-valued fields open in a sheet; the `scroll` form is the alternative, both as `Narrow` stories: **owner pick pending**, one prop switches it); a phone remembers the columns added back on a narrow table (`DataTable` `narrowColumns`: the saved view's `narrow_columns` for screener results, the URL `ncols` for Explore); `ActionGroup` turns the pick-detail actions into icon buttons with tooltips under `sm`; the real-store smoke at 375 px found and fixed four things the mocked phone project missed (the Calendar grid's hidden caption widened the page to 10,000 px, duplicate React keys from repeated gap lines and a screener id shared by a user copy and a site preset, the two column pickers on two rows, the account name clipped), each with its test and a representative mock. **Owner action:** `make web-build`; a phone pass; pick the filter bar's narrow form (Storybook `Components/FilterBar`: `Narrow` + `NarrowOpen` vs `NarrowScroll`). Left for a later ask: the screener results header is tall on a phone (banner, search, chips, pager, view controls before the first row).

### Pipeline details

VRP live spread check in the UI via `GET /chains/{id}/live`. **Pipeline (CI and local speed, [ci.md](ci.md) "Pipeline"):** P1 done (#280: parallel web jobs, Storybook artifact, screenshot shards, docs-only skip, the flaky list `apps/web/quarantine.json`; web path 12 -> 6 min), P2 done (#281: `make changed` for the web, vitest vmThreads 142 -> 35 s, the one-full-check rule), P3a done (#283: `scripts/merge_main.sh`, `make numbering`, rerere off, filelen exemption), P4 done (#284: per-worktree ports, the `make check` lock, doctor warnings, `scripts/ops/deploy.sh`, the site `.local` overlay); P1b done (#286: three pytest shards + a coverage-combine gate, four screenshot shards, `npm audit` only on a dependency change); P1c done (#292: `unit` split in two; Python PR 5.0 min, unit-a 4.5 min the long pole); P1d done (#296: the rollup groups spread over two unit shards, not yet re-measured); P3b done (#290: id-ordered registries `test_registry_order`, track details with `make roadmap-check`, screenshot baselines from CI on the `update-screenshots` label, the play-with-click story rule); P4b done (#287: overlay allowlist, test isolation, deploy venv sync); P5 done (foreground checks and one last-action hand-back per agent, the `needs-owner` label listed by `/start`, stacked drafts, label ownership: only the session that set a label removes it).

### Descriptions details

Descriptions (ADR 0034, accepted): after merge run `algotrade-ingest descriptions --only funds --force` (ETFs, ~2 min; `--force` rereads the 6 quarters so the ~870 ETFs matched through the SEC series file get their text, 83 of the 246 liquid gaps), then stocks in chunks (`descriptions --limit 300`, ~1 h each, S&P 500 first, each run holds the ingest lock; the nightly adds 100). Then the Overview tab reads `reference.description` from `GET /instruments/{id}`.


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

### Edges (ED) details

**Edges (ED, ADR 0053; plan [edges-plan.md](edges-plan.md)): ED0 done** (the plan, the ADR: an edge is a typed document whose screeners are its implementations, scored point in time by one harness against a quarantined outcomes grain). **ED1 done**: the `Edge` document (`src/algotrade/config/edges/`, responsibility `edge-documents`; `config/site/edges/`, user drafts layered from `config/users/<id>/edges/`; `docs/edges.md` from `make features-doc`): three candidates (`vrp_short_premium` on `short_premium_liquidity` and `vrp_scanner`, `small_cap_earnings_drift`, `earnings_announcement_premium`), two rejected (`sp500_index_changes`, `leveraged_etf_rebalancing`) and one blocked (`russell_reconstitution`, until ED6). Next ED2 (the outcomes grain), then ED3 (the harness) ([ED section](#edges-ed-hypotheses-with-evidence-one-point-in-time-harness-adr-0053)).

## Workflows (WF): dependencies, succeed or fail, cadence (ADR 0039)

In order. WF1-WF3 shipped in one PR (resume and waivers are what make hold-back safe to run); `docs/architecture.md` ("The nightly workflow") describes the current behaviour.

| # | Delivers | Status |
|---|---|---|
| WF1 | Step model: `needs`, `critical`, acceptance checks (thresholds in `sources.toml [quality]`), SUCCEEDED / FAILED / NOT_RUN / SKIPPED / WAIVED; `quality` checks run per step; rollups fail on a gap in a lookback window; NYSE special closures | **done** |
| WF2 | Resume (steps done in an earlier attempt are reused; `--force` reruns all); sessions in order, stopping at a FAILED one (later ones held), none dropped (old PARTIAL records count as done) | **done** |
| WF3 | `nightly --date D --waive STEP --reason ...` (stored in the run record, kept on later attempts); expired latest-only steps name the unblock command; notifier names failing critical steps and held sessions, alerts on every failed retry | **done** |
| WF3b | Chains retry refetches only STALE_DATA / FETCH_ERROR names (today a FAILED chains step refetches all ~4,200, 2-4 h); consider starting the nightly later than close + 30 min (2026-10-05: ~50% STALE_DATA at 13:40 PT) | **done** for a SUCCEEDED chains step with names left (`Step.refetch`: re-run on retry while latest, when its staging exists). **Open:** the 2026-10-05 second fetch made 4,208 requests, so the first run's staging was gone by then (not purge, not recovery: both leave it); find what removes it. The later start is still open |
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

- **Backtests page**: the reads are on GraphQL (RM9); the page needs mockups first.
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
| RG1a | `FeatureGroup.entity`, the `rollups/market/` table family, `MKT` / `IDX` / `MACRO` ids, `field_source`, inputs `universe` and `instruments/symbol_ids`, catalogue "Market features", the expression entity check (a toy market group: backfilled rows equal nightly rows) | **done** |
| RG1b | The `market-rollups` task and its non-critical step before the screens | **done** |
| RG1c | Market groups `trend` and `breadth` | **done** |
| RG1d | `cross_asset` group: turbulence and absorption ratio (`eigvalsh`) in `quant/covariance.py` | **done** |
| RG1e | Market reads and `Query.regime` (label UNKNOWN until RG3) | **done** |
| RG1f | Design-system pieces: `ScoreMeter`, `IndicatorRow`, `Chart.bands` | **done** |
| RG1g | `entities/regime` (`useRegime`, `useRegimeBands`, `RegimeChip`, `toChartBands`), the top-bar chip, the page header and cards | **done** |
| RG1h | Per-instrument episode features `episode_behaviour@v1` (`features/rollups/price/episodes.py`; `Input.windows` for each episode's own closes) | **done** |
| RG2a | The `macro/series` table, `data/macro.py`, `Input.ids`, `config/site/macro.py` settings | **done** |
| RG2b | FRED / ALFRED and published-file adapters against recorded payloads | **done** |
| RG2c | The `macro` task, step and `check_macro`; then a detached backfill | **done** (the detached backfill is an owner action: Now / Next) |
| RG3 | The macro group; regime expression features (with an `ncdf` built-in for the probit); the regime group; Pagan-Sossounov dating in `quant/turning_points.py`; the episode scorecard in `services/evaluation` | **done** (RG3a: the macro, indicator and regime groups; RG3b: EBP / OFR FSI / EPU, the probit, the scorecard: `make regime-scorecard` after the macro backfill; open: the Pagan-Sossounov published-table check) |
| RG4 | Overlays (`engines/overlays/`), `Decision.PAUSED`, `[regime]` config, with-versus-without evaluation | **done** (PR 217) |
| RG5 | The embeddings (Ideas strip and paused section, results header, Explore and Backtests bands) and the full Regime page | **done** except the Backtests page items (its bands, the by-regime split and the with / without toggle: wait for the Backtests page mockup). RG5a: Explore's "In rough markets"; RG5b: `Idea.regime` / `sizeMultiplier`, `Ideas.paused`, `ScreenerRun.paused` / `regime` (`NOT_PICKED` excludes `PAUSED`), `MarketRegime.sizing` per caller, the Size column, "Paused by regime (n)", the results header chip, the Builder gate line; the Admin Users & configs block is the read-only `regime-sizing` widget on the Regime page until that Admin page exists |
| RG6 | On-demand explanation: the text-model seam (ADR 0041 amended), `services/explaining`, `POST /regime/explain`, its cache | **done** |
| RG8 | The macro score's early and confirming tiers and the curve's year of memory, set on the 1971-2026 scorecard (`regime@v3`); scorecard section (g), each macro signal's own leads | in review (draft PR; macro 4 of 6 recession bears 63+ sessions early, CRISIS false alarms 0 -> 2 in 9 years) |
| RG7 follow-up | Storage read path: `ParquetFile` + arrow filter and a bounded executor in `LocalBackend.at`, target under 5 s cold for a 13,500-partition `Market.history` read (about 12 s today on a quiet machine; the 25 s `COLD_CEILING` in `tests/unit/services/read/market/test_performance.py` is a temporary guard, tighten it to 5 s when this lands); needs an `architect` review (the pinned read of one commit sequence) | open |

## Event sensitivity (EV): what moves a name, and what is coming (ADR 0050)

Plan and requirements: [event-sensitivity-plan.md](event-sensitivity-plan.md) (the owner's
decisions in its section 8). Every PR branches from `main`; `architect` review of EV1 (`known_from` and the
data-layer read) and of EV2 and EV4 (the groups' windows, the tables). Models per CLAUDE.md:
Opus for the design, storage and point-in-time pieces, Sonnet for the scoped implementation.

| # | Delivers | Status |
|---|---|---|
| EV0 | ADR 0050, the plan, `config/site/events/scope.toml` (kind `events`, typed loader) with the owner's lists | **done** |
| EV1a | `known_from` on event rows (the event grain's optional `known_from date`; null: the stored session) and the one read rule in `data/events.py` (`known_from <= S`), applied by `Instrument.events` and the earnings feature input; the earnings task sets `known_from = min(session, report date)` and gains the resumable `algotrade-ingest earnings --from --to` backfill (README "Long runs"); closes the deferred "Events point in time" item | **done** |
| EV1b | The macro release calendar: `config/site/events/releases.toml`, FRED `release/dates`, ISM by rule and the FOMC dates listed from the Fed calendar (FRED release 101 lists every day) into `events/macro_release`; the `macro-calendar` task, a non-critical step of the nightly beside the other reference steps until WF4 moves them to the weekly `reference` workflow; acceptance `[quality] min_calendar_future_dates`. **Owner action:** `algotrade-ingest run macro-calendar` once | **done** |
| EV1c | 8-K filings (SEC submissions JSON) into `events/filing`; 8-K Item 2.02 as the authoritative earnings date and time (`source = "sec_8k"`): the `filings` task (`tasks/events/`), a non-critical nightly step (acceptance `[quality] max_filings_failed`). **Widened to the whole universe** (owner decision 2026-10-07): the backfill is per CIK, the nightly reads EDGAR's daily form index and asks only the CIKs that filed. **Owner action:** `algotrade-ingest run filings --since 2018-01-01 --wait` once, detached (about 20 to 40 minutes; README "Long runs"; resumable, `--limit N` CIKs a run) | **done** |
| EV1d | Daily bars from 2018 for the scoped names: Tiingo by default (owner decision on the vendor and its tier), unadjusted into `bars/1d`, split factors checked against `events/split`; the `bars-history` task | **done** (PR 240; defaults to the scope list and its funds' references, `--include-tiers` adds the tier A / B names: Tiingo Power tier) |
| EV1e | `fund_reference@v1` for leveraged funds (holdings, else the name rule through `SymbolResolver`), after the owner's `etf-holdings` run; the scope resolved each run | **done** (`applies_to = leveraged_fund`; `services/events` is the one owner of the scope; owner action: run `etf-holdings` once so the group has holdings to read) |
| EV2 | `event_reaction@v1`: own earnings, macro and market-structure events, the big-move flags, the unattributed residual, `IDX:SPX` as the market's reaction | |
| EV3 | `peer_sensitivity@v1`: measured peers (industry, sector ETF co-holdings, correlation candidates), peer earnings as events | |
| EV4 | Attribution: `events/filing` (8-K items), Massive headlines capped to the session's big movers, `services/attributing` through the text-model seam, `events/attribution` | |
| EV5 | The `event-deep-dive` skill, the dossier schema and `dossier-import` (`instruments/factors`, `events/factor_occurrence`, reviewed attributions); first run on the scope list | |
| EV6 | `event_calendar@v1`, the screener expression features (`days_to_next_impact_event`, `impact_events_before_expiry`, `unscheduled_gap_rate_1y`, ...), field-guide entries, phrasebook | |
| EV7a-A | The what-is-coming read: `InstrumentEvents` / `EventCalendar` (`services/read/events/`), `Instrument.eventStudy`, `Query.eventCalendar` | **done** (PR 260) |
| EV7a-B | Design-system components: `EventChip`, `EventTimeline`, `ExpiryLadder`, `CalendarGrid`, chart filing / macro markers | **done** (PR 259) |
| EV7a-C | The Explore Events tab (ahead list, expiry ladder, filings, fund reference, the gaps), chart event markers and the TRADER Calendar page (`entities/event`, `widgets/event-study-panel`, `widgets/event-calendar-panel`, `features/calendar-source`); owner step `make web-build` | **done** |
| EV7 | The Explore Events tab's history with causes and drivers after EV2 (what is coming is EV7a) | |
| EV8 | `EventCalendar` read + `Query.eventCalendar`; the cross-name Calendar page; the Admin scope screen with its write (amends ADR 0029) and the review-staleness flag | |

## Edges (ED): hypotheses with evidence, one point-in-time harness (ADR 0053)

Items ED0 to ED7, their gates and status live in [edges-plan.md](edges-plan.md) (ED0 **done**: the plan and ADR 0053; ED1 **done**: the edge documents; next ED2); `architect` reviews ED2 (the outcomes grain, point in time) and ED3 (the harness and the `quant/` statistics).

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

**Parked:** the rest of the options positioning set (gamma and delta exposure, hedge wall, skew
and rank, GARCH rank, dark pool / short volume; the flow ratios and the implied move are built,
ADR 0031 accepted in part, 2026-10-06). Drafts kept, not
scheduled: [data/positioning.md](data/positioning.md) and
[ADR 0031](adr/0031-options-positioning-features.md) (OP1 parked on the P1 sign decision). Revisit when a
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
| Stale-chain limit vs screener coverage | `max_chain_stale_share` 20% (rest tier, ADR 0043) lets `chains` SUCCEED while `short_premium_liquidity` (`min_coverage` 98%) fails on the same names (2026-10-05: 199 of 4,205). Options: rest tier 2% (`1 - min_coverage`, with a fitness test tying the two), or keep 20% and accept the waive when the retry refetch does not clear them | owner to decide (amends ADR 0043) |
| User identity scheme | Labels now; auth provider in phase 4 | **decided: site registry + Supabase Auth** (ADR 0040; roadmap ID1-ID4) |
| Production job queue | Redis/RQ, Postgres-backed, cloud queue | local runner until hosting |
| Hosting target | VM + docker-compose, a container platform | local only |
