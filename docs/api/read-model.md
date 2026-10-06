# The read model: one session, one read model, one graph

The spec behind [ADR 0036](../adr/0036-session-strictness-for-reads.md) (reads serve one
session), [ADR 0037](../adr/0037-domain-read-model-served-by-graphql.md) (a domain read model
served by GraphQL) and [ADR 0038](../adr/0038-catalogue-named-values.md) (catalogue-named
values). Skills: `.claude/skills/add-domain-object`, `.claude/skills/add-graphql-field`.

**What exists now (the track is complete: read-model PRs 1-10b).** The decisions, this spec, the packages
`src/algotrade/services/read/{,instruments,screens,ops}` and
`apps/api/algotrade_api/graphql/{,types}` (declared in `architecture/layout.toml`, guarded by
two import-linter contracts), the ownership entries, the REST GET allow-list
(`architecture/rest_allowlist.toml`) and the web derivation list
(`architecture/web_forbidden_derivations.toml`), and the `strawberry-graphql[fastapi]`
dependency of `apps/api`. PR 2 added the session plumbing: `read/session.py`
(`resolve_session`, `Session`, the table grains `grain_of`, `NotFoundError`), `read/values.py`
(`Unknown`, `UnknownCode`, `to_scalar`; `services/views.to_value` imports it) and
`read/context.py` (`ReadContext`, `open_context`, `partition`, `ResultCache`; explore's
`store.py` re-exported `NotFoundError` and `ResultCache` until PR 10b), plus READ 2 in
`tests/architecture/api/test_read_model.py`. **PR 4 built the pipeline on one pane**: the
loaders `read/instruments/{identity,features,catalogue}.py` (`load_instrument`,
`load_feature_values`, `load_catalogue` with the server-derived `format`), the GraphQL layer
`apps/api/algotrade_api/graphql/{schema,context,scalars,errors,loaders,limits}.py` and
`types/{query,session,instrument,feature}.py` at `POST /graphql`, the snapshot
`apps/api/schema.graphql`, the web codegen (`apps/web/codegen.ts`, `shared/api/graphql.ts`,
`generated/{graphql,catalogue.ts}`) and the Explore Overview on `useInstrumentFacts`; READ 3,
6, 7, 9 and WEB 2, 5, 6 are on. **PR 9 moved the catalogue, distributions, backtests, configs
and the Builder's screen reads**: `Query.{catalogue,distribution,configs,backtests,backtest,
myScreens,screenDetail,screenVersions}` over `read/instruments/distribution.py`,
`read/ops/{configs,backtests}.py` and `read/screens/documents.py` (types in
`graphql/types/{instruments,ops,screens}/`); `explore/{features,backtests,configs}.py` and their
routes are deleted. Fields over configs and run records are not session data: they read a
session-free `StoreContext` (`context.open_stores`, `RequestContext.stores()`), so they answer
on a store with no market data yet; the user's drafts and versions are read through the `ConfigStore`
protocol (the `ConfigWriter` only writes them). **PR 6 moved the Explore detail pane**: the loaders
`read/instruments/{events,chains,holdings,prices,series}.py` (and `identity.load_instruments`,
the batch), `Instrument.{events,chain,holdings,prices,series}` with `OptionChain.quotes(expiry)`
and `Holding.instrument`, each through a per-request dataloader (`graphql/loaders.batched`:
one loader call per distinct arguments), the web entities `instrument`, `chain` and
`holdings` on GraphQL (one operation per tab: `InstrumentEvents`, `InstrumentPrices`,
`InstrumentFeatureValues` / `InstrumentHistory` in chunks of 60 names, `OptionChain` then
`OptionQuotes`, `EtfHoldings`), `explore/{instruments,chains,funds}` deleted (compare moved to
`explore/compare.py` until PR 7; live quotes read the read model's chain) and their GETs off
the allow-list; the PR 6 derivation entries are on. `Instrument.screenerHits` lands with PR 8. **PR 5 moved Ideas**: `read/screens/{screeners,runs,results,ideas,views}.py`
(`Screener` per id as the user sees it, `runs.load_latest_runs` THE latest-run rule: exact
session, else `NOT_RUN`; `ScreenResult`; `Ideas` with per-screener `picked` and `top` over the
whole run; `TableView`), `types/screens/{screener,result,ideas,view}.py` (PR 5 split `types/` by area: `instruments/`, `screens/`), `Query.{ideas,screeners,view}`,
the `screener_latest_run` dataloader, `identity.load_instruments` (one identity read for a
table's rows) and `partition(ctx, table, columns, instruments)`; the Ideas page reads one
`IdeasPage` query with its facts by name (`entities/idea/model/facts.ts`); `ideas/ranking.py`,
`GET /ideas` and `summarise()` are gone. **PR 7 moved the tables' read and the
Explore table**: `read/instruments/table.py` (`load_table`: the universe snapshot the session
sees, or the instruments `keys` name, filtered by `UniverseFilter` over catalogue fields, sorted
server-side, one page of `columns` read only for that page's rows; the filtered, sorted order
cached per query and published state) at `Query.table`; `field_view` reads expression features
only for the ids asked (deferred from PR 4: a table with no rows for those ids is no longer
"missing" when it has a partition); the column factories in `entities/feature/model/columns.tsx`
and the one table widget `widgets/feature-table` (server or client sort, paging, the column
picker); the Explore ticker table (one page per request) and compare (the chart from one
`ComparePrices` request, the side-by-side values a client-sorted feature table of the compare
set) on them; WEB 4 on; `explore/{universe,compare}.py`, `/explore/*` and `/universe` deleted
(the admin review lists moved to `explore/review.py` and `/admin/review/*` until PR 10, which
owns admin); one `decisions.ts` (labels, tones, `OUTCOME_FILL`) in `entities/screen`. **PR 8
moved the screener results, the preview's rows and the views**: `Query.screener(id)` with
`Screener.{criteria,displayColumns}` and `ScreenerRun.{previousSession,changes,audit,
results(decisions, change, q, sort, columns, page, size)}` over `read/screens/results.py`
(`load_result_page`: `explore/screens/table.py`'s filter / sort / page, moved; the catalogue
columns the reader adds come columnar as a `FeatureTable`'s; `load_run_changes` against
`runs.load_previous_run`, the screener's run in the previous stored session, named through
`context.previous_session` / `at_session`); `ScreenResult.{change,previousDecision}`;
`Instrument.screenerHits` (`read/screens/hits.py`, dataloader `screener_hits`); the one
display-column predicate `storage/tables/schemas.is_display_column` (writer and readers) and,
on the web, `isShownCriterion` (`entities/screen`); `TableView` scopes generalised to
`views.<scope>` (`screener:<id>`) in `preferences.toml` (`services/authoring/preferences.py`
moves a view saved under `screeners.<id>` on the user's next preferences write; the read side
reads both until then), written by `PUT` / `DELETE /preferences/views/{scope}/view` and read
only through `features/table-view` (`useTableView(scope)`, `ViewControls`; WEB 7); the
`widgets/feature-table` renders all four tables (`FeatureTable`, `ScreenerResults`,
`PreviewResults` on one `TableFrame`; `widgets/{screener-results,preview-results}` deleted) with
the new factories `screenColumn`, `reasonsColumn` (and `decisionColumn(leaving)`,
`scoreColumn(labelOf)`); `POST /screeners/preview` stays REST but its rows carry the
instrument's name, its draft's `criteria` / `display_columns` and `changes` against the saved
run of the session (`entered` / `left`, decided on the server: the NOT_PICKED entry is on);
`explore/screens/*`, `/screens`, `/screens/{id}/{results,table}` and the view GET are deleted;
the `_float/_text/_num` rule is on. **PR 10a
moved Admin**: `read/ops/{runs,quality,ingestion,review}.py` (`NightlyRun`, `RunDetail`,
`RunItem`; the session's `QualityReport` and `Verification`; `Completeness` and `CellDetail`;
`ReviewList`), `types/ops/{run,quality,ingestion,review}.py`, `Query.{nightlyRuns,run,runItems,
quality,verification,completeness,ingestionCell,figiReview,leverageReview}`, the Admin entities
`ingestion`, `run`, `verification` and `review` on GraphQL, and the context's inventory reads
(`stored_dates`, `partition_on`, `snapshot_on`: what is stored on dates the caller names, for
`read/ops/ingestion.py` only, `test_inventory_reads_only_in_the_completeness_loader`); `explore/{runs,ingestion,review}.py`,
`routes/{admin,runs}.py` and their schemas are deleted and every `/admin` GET is off the
allow-list. Run records are session-free (`stores()`); the quality checks and the verification
are for exactly the session (`NOT_RUN` / `NO_PARTITION`, never an earlier session's, ADR 0036),
the completeness window ends at it and the review lists read its reference snapshot. **PR 10b
ended explore**: `services/explore/` is deleted. The Builder's dry runs moved to
`services/preview/` and take the request's `ReadContext` (the routes' `deps.Context`): the
draft is previewed, and a formula sampled, on `ctx.session` (no per-input "latest", no "on or
before the last closed session" of its own); `ReadStore` / `open_store` are API wiring in
`apps/api/algotrade_api/deps.py` (over `context.open_read_stores`); `latest_session` and
`store_info` (`GET /health`) are in `read/session.py`, `records` in `read/values.py`; live
quotes take the request's `ReadContext`; `paginate`, `Page`, `record`, `cached`,
`partition_for` are gone. `explore-queries` is out of ownership and READ 2 scans every use case
and the API. A new page read is a GraphQL field (`add-graphql-field`).

## What is wrong today

| Fact | Read today by | Partition rule |
|---|---|---|
| A ticker's feature values | `services/features.field_view` (Explore, compare, screen table, preview); `explore/instruments` (`rollup_row` per group); `explore/chains` (`rollup_row(iv30)`); `explore/features._values` / `_expression_values`; `explore/universe.VIEW_FIELDS`; `ideas/ranking._earnings` | six rules: exact session; latest on or before (`rollup_row`, `partition_for`); `latest_session` (bars else reference); max stored date of any input; holdings as of |
| "Latest run of a screen" | `ideas/ranking._latest_runs` (20-session lookback); `screens/results.run_rows` (`partition_for`, first owner with rows) | two |
| Symbol / name | `data.reference.resolver`; `universe` snapshot columns | two |
| Scalar coercion | `services/views.to_value`; `ranking._float/_text`; `screens/table._text`; web `num()` / `text()` | re-implemented |
| Nearest expiry, DTE, earnings before expiry | computed per request in `ranking.top_ideas`; the web re-derives it | not stored |
| Next / last earnings | `earnings@v1` rollup **and** the web's `overview.ts nextAndLast()` from raw events and the browser clock | the browser re-derives a stored fact |
| Per-screener counts, top 3 | web `idea.ts summarise()` over a 200-row page | wrong by construction |
| Tables | four widgets each build rank / ticker / decision / score / criterion / feature columns | 4x |

One page can show a value for session S next to one for S-3 with no marker. That is the bug.

## Catalogue feature or typed field

The rule ([ADR 0038](../adr/0038-catalogue-named-values.md)), quoted by the skills:

> **Typed field**: identity and structure. Who something is (`instrumentId`, `symbol`,
> `name`, `securityType`, `assetClass`, `exchange`), what links to what (`Idea.instrument`,
> `ScreenerRun.screener`, `Holding.instrument`), and run / session bookkeeping (`runId`,
> `session`, `status`, `knowledgeTs`, decision, score, rank, criterion outcomes). These come
> from snapshot or result tables and never from `rollups/*`.
>
> **Catalogue feature**: anything **per instrument, per session, stored or computed on read**
> that a selection could also use: every `rollup.<group>@vN.<col>`, every `feature.<name>`,
> and the `instrument.<col>` reference facts the catalogue already exposes (`in_sp500`,
> `is_leveraged`, `sector`, ...). Read **by catalogue name only**, never as a typed field.

**Every API surface, REST legacy reads included.** Never add a response field named like a catalogue column (e.g. `last_earnings_date` on `Idea`), not even "for now": return a `features: dict[str, Any]` keyed by catalogue name. Enforced by `tests/architecture/test_structure.py::test_no_typed_catalogue_fields_in_api_schemas` (`TYPED_FACT_FIELDS` lists today's exceptions and only shrinks; PR 5 removed the two `Idea` entries).

Decided grey zone: `optionable` is a catalogue field (`instrument.optionable`); a chain's
`status` (OK / NO_CHAIN / STALE) is typed on `OptionChain` (it describes the pull);
`description` is a typed field of `Instrument` (text, not selectable). `change` (new / dropped)
compares two runs and stays typed on `ScreenResult`. Settled in PR 6: each listed expiry's
`days` from the session is typed on `OptionChain.expiries` (structure of the chain, one per
expiry; the nearest's DTE as a fact is `rollup.nearest_expiry@v1.dte`); the chain's
per-instrument facts (our IV30, the underlying's price with the chain, the target expiry) are
catalogue features, not chain fields; a `PriceBar`'s OHLCV are typed (a point of a range-grain
series, `RANGE_GRAIN_FIELDS` in `test_read_model.py`, as `Bar.close` was on REST).

**A fact a page needs that is computed on read becomes a stored feature first**
(`.claude/skills/add-feature`): `rollup.nearest_expiry@v1.{expiry_date,dte,sessions_to_expiry}`
(new group `features/rollups/options/nearest_expiry.py`, kind `chain`) and the expression
`feature.earnings_before_expiry` (`config/site/features/earnings.toml`) land in PR 3.
`earnings.days_to_earnings` already exists.

## The domain objects

Owner folder `src/algotrade/services/read/` (ownership `domain-read-model`). Every loader is
`load_<object>(ctx: ReadContext, ...)` returning a frozen dataclass; it reads only
`ctx.session.date` (a range or a previous run is an explicit, named argument).

| Object | Identity | Typed fields | Backing tables | Loader module | Replaces |
|---|---|---|---|---|---|
| Session | `date` | `date, requested, isLatest, latestWithBars, referenceSnapshot, preSnapshot, present, missing` | `bars/1d` (latest), partition lists | `read/session.py` | `explore/store.partition_for`, `latest_session`, preview's store half, ranking's `max(...)` |
| Instrument | `instrumentId` | `symbol, name, securityType, assetClass, exchange, isEtf, description, referenceSnapshot` | `instruments/reference`, `company`, `description` | `read/instruments/identity.py` | `explore/instruments.resolve_key`, `description_of`; the symbol lookups in results, table, ranking, preview |
| FeatureValue | (`instrumentId`, `name`, `session`) | `name, value: JSON?, unknown?, info` | `rollups/instrument/*`, expressions, reference columns | `read/instruments/features.py` (wraps `services.features.field_view`) | the features bag, `rollup_row` in chains, `VIEW_FIELDS`, `ticker_columns`, `ranking._earnings` |
| FeatureInfo | `name` | `kind, source, dtype, format, description, nullMeaning, version, group, key, inputs, unit, range, categories, scope, owner, licence` | registry + user `FeatureSet` | `read/instruments/catalogue.py` (PR 4; `Query.catalogue` PR 9) | `explore/features.feature_catalogue` (deleted) |
| FeatureDistribution | (`name`, `session`) | `info, count, nulls, quantiles[{q, value}], histogram, categories, unknown` | as FeatureValue (`load_feature_values` over the session's reference snapshot: `NO_ROW` not counted, `NULL` counted as null, `NO_PARTITION` makes it UNKNOWN) | `read/instruments/distribution.py` (its own module: it reads `features.py`, which reads `catalogue.py`) | `explore/features.feature_distribution` (deleted) |
| Event | (`instrumentId`, `table`, `ts`) | `kind, date, ts, values` | `events/*` by event date | `read/instruments/events.py` (PR 6) | `explore/instruments.instrument_events` |
| OptionChain | (`underlyingId`, `session`) | `session, status, expiries[{date, days}], strikes, quotes(expiry)` | `chains/*` exact session | `read/instruments/chains.py` (PR 6) | `explore/chains.option_chain` (minus `our_iv` and the underlying quote: features) |
| Holdings | (`fundId`, `asOf`) | `asOf, source, total, items[{rank, name, symbol, instrumentId, weight, assetClass, instrument?}]` | `holdings/etf` | `read/instruments/holdings.py` (PR 6) | `explore/funds/holdings` |
| PriceSeries / FeatureSeries | (`instrumentId`, range) | `adjustment, start, end, bars[{session, open, high, low, close, volume, vwap}]`; `names, start, end, points[{session, values}]` | `bars/1d` + actions; rollups | `read/instruments/{prices,series}.py` (PR 6) | `instrument_bars`, `instrument_features`, `compare_prices` (PR 7: the compare set's `table(keys) { instruments { prices } }`) |
| FeatureTable | (query) | `session, universeSnapshot, preSnapshot, columns: [FeatureInfo], instruments: [Instrument], rows: [[JSON]], unknown: [[UnknownCode]], sort, total, page, size, missing` (columnar; `missing`: tables the filters and sort read with nothing for the session, incl. a company snapshot taken after it; the nightly tables: `session.missing`) | FeatureValues + identity, `universe` snapshot | `read/instruments/table.py` (PR 7) | `universe.ticker_table`, `universe_page`, `compare_features` |
| Screener | (`owner`, `configId`) | `id, owner, scope, name, version, hash, criteria, displayColumns, latestRun, notRun` (PR 5; `criteria, displayColumns` PR 8). One per id: the user's own finalised config, else the site preset; rule screens only | configs, run records | `read/screens/screeners.py` | `results.screen_configs`, ranking's `_screeners` (both deleted) |
| ScreenerRun | `runId` | `runId, configId, owner, session, status, knowledgeTs, configVersion, decisions, picked, audit` (PR 5; `audit`, `changes, previousSession, results(...)` PR 8) | `results/rule_screen` exact session; the previous run in the previous stored session | `read/screens/runs.py` (`load_latest_runs` / `latest_run`: THE rule; `load_previous_run`) | `results.run_rows`, `ranking._latest_runs`, `table._previous` (deleted) |
| ScreenResult | (`runId`, `instrumentId`) | `rank, instrument, decision, score, tieBreak, reasons, flags, criteria, columns, change, previousDecision` (PR 5; `change, previousDecision` PR 8: null when not compared, e.g. Ideas); a page of them: `ScreenResultPage` (`load_result_page`) | `results/rule_screen*` | `read/screens/results.py` | `table.ScreenTableRow`, `ranking.Pick` (deleted) |
| ScreenerHit | (`instrumentId`, screener) | `screener, result` (the user's screeners that picked it in the session) | as ScreenerRun + ScreenResult | `read/screens/hits.py` (PR 8) | the Explore "Screener hits" placeholder |
| Ideas / Idea | (`user`, `session`) | `session, priority, screeners[{screener, run?, notRun?, picked, top}], total, items[{rank, instrumentId, instrument, picks}]` | ScreenerRun + ScreenResult | `read/screens/ideas.py` | `ideas/ranking.py` (deleted in PR 5) |
| TableView | (`user`, `scope`, `name?`) | `columns, sort, decisions, names`; `scope` `screener:<id>` (PR 8: `views.<scope>`) | `preferences.toml` | `read/screens/views.py` | `explore/screens/view.py` (deleted) |
| Backtest, BacktestDetail | `runId` | `configId, user, status, start, end, startedAt, finishedAt, metrics`; detail: `configHash, selection, data, rebalances, equity[], fills[]` | run records; the run's own `results/backtest_{equity,fills}` partition as of the run (`context.run_partition`) | `read/ops/backtests.py` (PR 9) | `explore/backtests.py` (deleted) |
| Config | (`scope`, `configId`) | `kind, impl, selection, hash, error` | configs | `read/ops/configs.py` (PR 9) | `explore/configs.py` (deleted) |
| Viewer | `id` (the caller) | `name, role, workspaces` (never the email) | `config/site/users.toml` + `config/users/<id>/identity.toml` (the registry, in memory) | `read/users/viewer.py` (ID2, ADR 0040; `load_viewer(user)`: no store read) | the open `canEnter` |
| ScreenListing, ScreenDetail, ScreenVersion | (`user`, `screenerId`) | `status, latest, hasDraft, presetId`; `draft, draftError, versions, preset{presetId, pinned, current, rebaseAvailable}, hash, layers, resolved, error, working`; `version, document` | the user's drafts and versions (`ConfigStore`) | `read/screens/documents.py` (PR 9) | `services/authoring/screens.{screen_detail,list_screens,screen_versions}` |
| NightlyRun, RunDetail, RunItem | `runId` | `runId, session, status, startedAt, finishedAt, durationS, steps[{name, status, durationS, reason, error, counts}], problems`; `job, itemsTotal, itemsByStatus, failures[{reason, count, examples, statuses}], stats`; `key, code, status` | run records (session-free: `Stores`) | `read/ops/runs.py` (PR 10a) | `explore/runs.py` (deleted) |
| QualityReport, Verification | `session` | `runId, status, finishedAt, checks[{name, status, detail}], unknown` (`NOT_RUN`: no `data_quality` run for the session); `runIds, instruments, counts, byCheck, failing, unknown` (`NO_PARTITION`) | the session's `data_quality` run records; `verification/ibkr` exact session | `read/ops/quality.py` (PR 10a) | `explore/{runs,ingestion}.py` (deleted; both were "latest on or before") |
| Completeness, CellDetail | (`session`, window); (`dataset`, `session`) | `sessions, datasets, cells[{dataset, session, status, present, expected, basis, runIds}], lastClosed`; `cell, job, groups, runs` | every dataset's partitions on the window's sessions (inventory reads), `chains/status`, universe snapshot, run records | `read/ops/ingestion.py` (PR 10a) | `explore/ingestion.py` (deleted) |
| ReviewList | (kind, `session`) | `session, source, items: [JSON]` | the `figi_review` of the `universe_build` record on or before the session (never a later one), else the session's reference snapshot; leverage: that snapshot | `read/ops/review.py` (PR 10a) | `explore/review.py` (deleted) |

`explore`'s `ResultCache` moved to `read/context.py` (PR 2) and `records` to `read/values.py`;
`ReadStore` / `open_store` became API wiring (`deps.py`); `services/explore/` was deleted in
PR 10b.

## Values and UNKNOWN

`services/read/values.py` (ownership `scalar-coercion`) holds the one coercion and the UNKNOWN
vocabulary. `FeatureValue.value is None` always comes with `unknown` set.

| `UnknownCode` | Meaning |
|---|---|
| `NO_PARTITION` | the table has no partition for the session |
| `NO_ROW` | the partition exists, the instrument has no row |
| `NULL` | stored null: see `FeatureInfo.nullMeaning` |
| `NOT_IN_CATALOGUE` | the name is not in the caller's catalogue |
| `LICENCE` | a `personal`-licence feature and the caller is not its owner (ADR 0028) |
| `NOT_RUN` | a screener (or the nightly data-quality check) has no run for the session |
| `PRE_SNAPSHOT` | identity came from a later snapshot (survivorship) |

In PR 4 `features(names)` returns `NO_PARTITION`, `NO_ROW` and `NULL`. A name the caller's
catalogue lacks is a request error (`UNKNOWN_FEATURE`, naming it) when the client asked for it;
`NOT_IN_CATALOGUE` is for names the server reads on its own (a saved view's columns, PR 8).
`LICENCE` waits for a second user (ADR 0028: personal values are hidden from other users once
there are any). Identity is disclosed, not blanked: `PRE_SNAPSHOT` is reserved for the screens'
universe (PR 5); `instrument.*` values and `Instrument` say which snapshot through
`Session.preSnapshot` / `referenceSnapshot`.

`Unknown(code, detail)`: `detail` names the table and session
(`"rollups/instrument/earnings@v1 has no partition for 2026-10-03"`). `to_scalar(value)` is
today's `services/views.to_value`, moved; `views.py` imports it back so runs and reads agree.

## Session resolution

One resolver, `services/read/session.py` (ownership `session-resolution`):
`resolve_session(reader, requested) -> Session`. Requested given: that date, even if nothing is
stored for it (everything UNKNOWN). None: the latest `bars/1d` partition; no bars: the latest
reference snapshot; an empty store: `NotFoundError("nothing stored")`. Loaders read a
session-grain table only through `partition(ctx, table) -> DataFrame | Unknown`, which is
`ctx.reader.table(table, ctx.session.date)`: no `on`, no `snapshot()`, no `dates()` in a loader.

Rules by **table grain** (the only place grain decides anything):

| Grain | Tables | Read for `Session.date` |
|---|---|---|
| session | `rollups/instrument/*`, `chains/*`, `results/*`, `bars/1d` (the day's bar), `verification/*`, `live/*` | **exactly the date**; absent: `Unknown(NO_PARTITION)` |
| snapshot | `instruments/reference`, `instruments/company`, `universe`, `instruments/id_map`, `instruments/ibkr_contracts` | `data.reference.snapshot` (ADR 0007's one rule: latest on or before, else earliest with `pre_snapshot`); **disclosed** as `Session.referenceSnapshot` / `preSnapshot` |
| event | `events/*` | by event date (ADR 0007), never by partition |
| issuer-dated | `holdings/etf` | latest `as_of` on or before the date with `filed <= date`; `Holdings.asOf` disclosed |
| incremental | `instruments/description` | the latest stored row per instrument (text, not a fact) |
| range | bars, feature series | `[start, end]` given explicitly; never "latest" |

`session.grain_of(table)` is this table in code (range is a read shape, not a table grain, so
it has no entry); `partition` refuses a table of another grain or with no declared grain
(`ValueError`), so a loader cannot read a snapshot or event table by exact date by mistake. A
table a loader needs that is not listed gets its grain here and in `GRAINS` first.

Retired as their last caller moved (all gone by PR 10b; `latest_session` lives on in
`read/session.py` for what is not a page read): `explore/store.partition_for` and `latest_session`,
`data/rollups.rollup_row` in reads, `explore/features._expression_values` / `_values`,
`ranking._latest_runs` / `_earnings`, `results.run_rows`'s owner-fallback loop,
`table._previous` (a loader with the explicit prior session), `preview.preview_session`'s store
half, `views.to_value` (moved), `ranking._float/_text`, `table._text`. `data/` keeps every
generic read (R1 unchanged); what goes is each consumer deciding which partition.

### Settled details for PR 2 (do not re-decide)

- **`NotFoundError`** moves to `services/read/context.py` (importable from there; defined in
  `session.py`, which raises it, to avoid an import cycle); `services/explore/store.py`
  re-exports it (`from algotrade.services.read.context import NotFoundError`) until explore is
  deleted. `services/read` never imports `services/explore`.
- **`ReadContext`** fields, exactly: `reader: StoreReader`, `configs: ConfigStore`,
  `user: UserContext`, `session: Session`, `features: FeatureSet` (the caller's catalogue, read
  once per request), `cache: ResultCache`. `preview_cache` stays on explore's `ReadStore` (it
  moves with preview in PR 8). `loaders` is added by PR 4 (GraphQL), not PR 2.
- **`Session.present` / `Session.missing`**: the expected session-grain tables are the
  `[[table]]` entries in `architecture/ownership.toml` whose name starts with `rollups/instrument/`,
  `chains/` or `results/`, plus `bars/1d`. `present` = those with a partition for the date
  (`reader.dates(table)`), `missing` = the rest. `verification/*` and `live/*` are not expected
  nightly and are never listed. The list is read once at import (a module constant), not per
  request.
- **Ownership in PR 2**: `session-resolution` `owner` becomes
  `["src/algotrade/services/explore/*", "src/algotrade/services/read/session.py", "src/algotrade/services/read/context.py"]`
  (`open_context` calls `resolve_session` once per request; nothing else in `services/read`
  may); `target_owner` drops `session.py`. `scalar-coercion` `owner` becomes
  `src/algotrade/services/read/values.py`, with `services/views.py` in `allowed` (it re-exports).
- **`tests/architecture` is at its 10-module cap**: PR 2 adds a declared subfolder
  `tests/architecture/api/` (`[[dir]]` in `layout.toml`, purpose "fitness tests for the API
  surface and the read model"), moves the REST allow-list tests out of `test_structure.py` into
  `tests/architecture/api/test_rest_allowlist.py`, and adds `tests/architecture/api/test_read_model.py`.

## GraphQL conventions

- **Library**: Strawberry (code-first from typed Python, first-party FastAPI router, built-in
  `DataLoader`, validation extensions). Mounted at `POST /graphql` (GET off; GraphiQL only when
  `ApiSettings.debug`). Ariadne (schema-first: SDL that mypy cannot see) and graphene (weak
  typing) rejected.
- **Where**: `apps/api/algotrade_api/graphql/`: `schema.py` (schema + router factory),
  `context.py` (`get_context` -> `ReadContext` via `services.read.context.open_context`),
  `scalars.py`, `errors.py`, `loaders.py`, and `types/<area>/<object>.py` (one per domain object, by area as the read model: `instruments/`, `screens/`; `types/` holds `query.py` and `session.py`).
- **Thin resolvers**: a `types/*.py` module imports only `strawberry`, `algotrade.services.read.*`,
  `algotrade.core`, `algotrade.config` and sibling types (import-linter "GraphQL types are thin",
  enforced now). A resolver reads `info.context`, calls **one** loader or one dataloader
  `.load`, wraps the result. Logic is a loader first.
- **`.of()`**: each type has one `@classmethod of(cls, d: read.X)`, the single mapping from the
  domain dataclass; the only logic allowed in `types/`. A fitness test (PR 4) checks a type's
  fields are a subset of its dataclass's fields plus its declared resolvers.
- **Dataloaders** (built per request in `get_context`): `features` keyed
  `(instrument_id, names)` (one `feature_values` call per distinct `names`), `instruments`
  keyed `instrument_id`, `events` keyed `(instrument_id, start, end)`, `screener_latest_run`
  keyed `(owner, config_id)`, `holdings` keyed `(fund_id, top)`; PR 6 adds `chains`
  (`instrument_id`), `quotes` (`(underlying_id, expiry)`), `prices`
  (`(instrument_id, start, end, adjustment)`) and `series` (`(instrument_id, names, start,
  end)`); PR 8 `screener_hits` (`instrument_id`). A type resolves a child object
  only through a dataloader. Tables (`FeatureTable`, run results, Ideas) are built by
  whole-population loaders, never per row.
- **Feature values**: `features(names: [FeatureName!]!): [FeatureValue!]!` with
  `FeatureValue { name value: JSON unknown { code detail } info: FeatureInfo }`. `value` is JSON
  (dtype varies); the client formats with `info.format` (`percent`, `currency`, `date`,
  `number`, `compact`, `flag`, `category`, `text`), derived server-side from `unit` + `dtype`.
- **`FeatureName` scalar**: `instrument.<col>`, `rollup.<group>@vN.<col>` or `feature.<name>`,
  validated against the caller's catalogue at request time (the error names the field). Site
  names are also typed at compile time in TS: `scripts/export_catalogue.py` writes
  `apps/web/src/shared/api/generated/catalogue.ts` (`SITE_FEATURES`, `feature('<name>')`).
- **Errors**: 200 with `data` + `errors[]`, each with `extensions.code` (`NOT_FOUND`,
  `BAD_REQUEST`, `UNKNOWN_FEATURE`, `NO_DATA`) mapped in `graphql/errors.py` from the library
  exceptions `main.py` maps today. "No such thing" is a null field; "nothing stored yet" is
  never an error (UNKNOWN values, empty lists, `session.missing`).
- **Limits**: `QueryDepthLimiter(8)`, `MaxAliasesLimiter(10)`, `MaxTokensLimiter(5000)`, and a
  rule capping `features(names)` at 60 and `first` / `size` at 1000.
- **Snapshot**: `scripts/export_graphql_schema.py` writes `apps/api/schema.graphql`;
  `tests/apps/api/graphql/test_schema.py::test_committed_schema_is_up_to_date` fails on drift
  (as `openapi.json` today). The web codegen reads only this file.
- **User scoping**: `get_context` builds `UserContext` (today `ALGOTRADE_USER`); catalogue,
  screeners, views and Ideas are scoped by it.
- **No** mutations (writes stay REST), **no** persisted queries.
- **Settled in PR 4** (do not re-decide):
  - The session is each top-level field's `date` argument (default: the latest with bars).
    `RequestContext.read(date)` (`graphql/context.py`) opens one `ReadContext` per date per
    request (fields of one operation that pass the same `date` share it and its dataloaders);
    the objects a field returns carry it (`strawberry.Private`). An empty store (no session to
    resolve) is a null field, not an error. `get_context` is the router's `context_getter`.
  - `Query` lives in `types/query.py` (READ 3 covers it); the list caps are a field extension
    (`limits.MaxItems`, on `features(names)`); the document limits are per-request extension
    factories (`limits.EXTENSIONS`).
  - Enums are GraphQL-cased: `FeatureFormat` (`PERCENT`, `CURRENCY`, `COMPACT`, `NUMBER`,
    `DATE`, `FLAG`, `CATEGORY`, `TEXT`) and `UnknownCode`. `format` comes from `unit` + `dtype`
    (`catalogue.format_of`): `decimal` -> `PERCENT`, `usd_per_share` -> `CURRENCY`, `usd` /
    `shares` -> `COMPACT`, `pct_points` and other numbers -> `NUMBER` (`PERCENT` means a
    fraction). The client picks digits and dollars from `unit` / `dtype`
    (`entities/feature/model/value.ts`).
  - `FeatureName` checks the form when the request is parsed (`BAD_REQUEST`); the catalogue
    check is the loader's (`UnknownFeatureError` -> `UNKNOWN_FEATURE`).
  - Strawberry's `@strawberry.field(...)` is untyped under mypy strict even with its plugin:
    `# type: ignore[untyped-decorator]` on that decorator line in `types/` only
    (`test_type_ignores_only_on_strawberry_field_decorators`).
  - `catalogue.ts` is written by `scripts/export_catalogue.py` (Python); its freshness test is
    `tests/scripts/test_export_catalogue.py` (the web CI job has no Python). `npm run
    api:generate` runs both web generators (OpenAPI types, GraphQL codegen).
  - The resolved `Session` is cached in the result cache keyed on `visible_seq` (the ~26
    `dates()` calls run once per publish, not per request).
- **Settled in PR 5** (do not re-decide):
  - A `Screener` is a config, one per id as the user sees it: their own finalised config, else
    the site preset (resolved as its owner, like the run that stored it). Results stored for an
    id with no config (an archived screen) are no screener. Rule screens only: the legacy
    `short_premium_liquidity` impl stays on REST `/screens` until PR 8.
  - THE latest-run rule (`runs.load_latest_runs`): the owner's rows of the config in
    `results/rule_screen` for exactly the session, of the run with the latest `knowledge_ts`.
    No run: `NOT_RUN`, never an older session and never the site's run of an id the user owns.
    `ScreenerRun.status` is the run record's (`complete`, `partial`; null without a record).
  - Ideas ranking is unchanged otherwise: priority place (unlisted screeners share the last
    place), then score, tie-break, screener id; `Ideas.screeners[].top` (the run's 3 best picks
    by rank) keeps the ranking panel's "best finds" a server fact.
  - The Ideas Earnings cell (`widgets/top-ideas/model/facts.ts`): `next_earnings_date`, else
    muted "Last <d MMM>" from `last_earnings_date`, else "Unknown"; the reason is the tooltip.
    The earnings filter counts `days_to_earnings` in sessions ("Hide earnings within 14
    sessions"). IV30 is `feature.vrp_iv30` by name; the screens' other display columns are
    their stored values.
  - `Query.view(scope, name)` takes no `date` (preferences, not session data). Codegen maps the
    `DateTime` scalar to `string`.
- **Settled in PR 8** (do not re-decide):
  - A run's review table is `Query.screener(id) { latestRun { results(...) } }`: its run for
    exactly the session (NOT_RUN otherwise: no older run). `change` compares it with the same
    owner's run in the previous stored session of `results/rule_screen` (the table's previous
    partition, as before), by the same latest-run rule; none: nothing is new or dropped.
  - Sort keys are the factories' column ids: `rank`, `score`, `symbol`, `decision`, `change`,
    `criterion:<id>`, `column:<name>` (a display column) or a catalogue name; missing values
    last, ties in rank order. The search `q` matches the symbol or name (a missing name no
    longer hides a row: the Explore table too).
  - A table view's scope is `<kind>:<id>`; the only kind is `screener` (its results). The web
    saves the table's default sort as none.
  - The preview stays a REST POST; it is shaped as the review table (each row's instrument
    name; the draft's `criteria` and `display_columns`) and carries `changes` against the
    screener's saved run of the preview's session (the user's view of the screener: their
    own config, else the preset's site run), over every row rather than the rows shown.
- **Web**: `@graphql-codegen/cli` client preset (`apps/web/codegen.ts`, documents
  `src/**/*.{ts,tsx}`, `fragmentMasking: true`) over TanStack Query; the one transport is
  `gql(document, variables)` in `src/shared/api/graphql.ts`; query keys
  `queryKeys.gql(operationName, variables)`. Each entity's `api/` holds its operations and
  fragments; other entities compose fragments through the entity's `index.ts`. No Apollo, no
  urql (ESLint bans them now).

Example (the Ideas page, one query):

```graphql
query IdeasPage($date: Date, $limit: Int!, $names: [FeatureName!]!) {
  ideas(date: $date, limit: $limit) {
    session { date isLatest missing }
    screeners { screener { id name } run { runId status } notRun { code detail } picked }
    items {
      rank
      instrument { instrumentId symbol name features(names: $names) { name value unknown { code } info { format } } }
      picks { decision score reasons flags criteria { id field outcome value } }
    }
  }
}
```

## What stays REST

`architecture/rest_allowlist.toml` lists every GET route; it **only shrinks**
(`tests/architecture/api/test_rest_allowlist.py::test_rest_get_routes_are_allowlisted` and
`test_rest_allowlist_only_shrinks`; `make rest-allowlist-update` lowers the committed count).

| Stays REST | Why |
|---|---|
| Writes: `routes/authoring/*`, `POST /screens/{id}/run` | a different contract (ADRs 0029, 0033); mutations would be a second write surface |
| `GET /screens/{id}/run/{job_id}` | job polling, kept with its POST |
| `GET /health` | liveness probe for scripts and `make doctor` |
| `GET /chains/{id}/live` | latency-bound, records to `live/*`, bypasses the session model on purpose (ADR 0028) |
| `POST /screeners/preview`, `POST /features/check` | compute over a request body with its own cache |
| Files (exports) | binary / streaming |

Every read for a trader page goes to GraphQL. No new GET serving stored data.

## What the browser may not derive

`architecture/web_forbidden_derivations.toml`, checked by
`tests/architecture/test_layout_web.py::test_no_forbidden_derivations`. Enabled now: the
browser clock outside `src/shared/lib/date/`, and building `EQ:` ids. The others are commented
"pending, enable in PR N" entries; the PR that removes the derivation enables its entry.

| Forbidden in `apps/web/src` | Ask instead | Enabled |
|---|---|---|
| next / last earnings from `events/earnings` (`nextAndLast`, `nextEarningsDate`) | `rollup.earnings@v1.{next,last}_earnings_date` | **on** (PR 4; only `entities/instrument/model/events.ts` names `events/earnings`) |
| days to earnings, DTE, earnings before expiry | `rollup.earnings@v1.days_to_earnings`, `rollup.nearest_expiry@v1.dte`, `feature.earnings_before_expiry`, `OptionChain.expiries[].days` | **on** (PR 6: `daysBetween(`) |
| "today" / `new Date()` against stored dates | `session.date` from the response | **on** (`new Date()`; `todayIso()` since PR 6: the features panel's history ends at the values' session) |
| per-screener counts, top-N from a page (`summarise`) | `Ideas.screeners[].picked` / `.top`, `ScreenerRun.decisions` | **on** (PR 5) |
| picked / not picked from a decision string | `ScreenResult.change`, the preview's `changes` | **on** (PR 8: `NOT_PICKED`) |
| symbol from an instrument id, or the reverse | `Instrument.symbol` | now |
| new / dropped between runs | `ScreenResult.change` | **on** (PR 8: the server decides; with the entry above) |
| the universe size via a `size=1` page | `FeatureTable.total` | **on** (PR 7: `useUniverseSize`) |
| a value's format from the feature's name | `FeatureInfo.format` | **on** by construction (PR 7: `featureColumn(info)` formats from `info.format`; WEB 4 keeps columns in the factories) |

**Presentation is not derivation.** Choosing which of several values the server sent to
show is presentation and belongs in the widget's `model/` (e.g. the Ideas earnings cell shows
`rollup.earnings@v1.next_earnings_date`, else muted "Last <date>" from
`rollup.earnings@v1.last_earnings_date`, else the UNKNOWN label). Computing a value the server
did not send (a date from raw events, a count over a page, a difference against the browser
clock) is derivation and is forbidden. Ask for both values by catalogue name; never compute one
from the other.

**Column factories.** Tables render through one widget, `widgets/feature-table` (PR 7), and
columns come only from the factories in `entities/feature/model/columns.tsx`: `rankColumn`,
`tickerColumn`, `decisionColumn`, `scoreColumn`, `flagsColumn`, `criterionColumn`,
`featureColumn(info)` (format from `info.format`; a null cell reads "Unknown" with the reason
from its code), `changeColumn`, each with a stable `id` that is also the server sort key
(`symbol`, `rank`, `decision`, `score`, `flags`, `change`, `criterion:<id>`, a catalogue name).
A widget is a `ColumnPlan` (an ordered list of factory calls), never a `DataTableColumn`
literal (ESLint `algotrade/column-factories`, `apps/web/lint-rules/columns.js`). The rows are
`TableRow`s (an instrument, its cells by catalogue name, and a result's typed fields); the
widget sorts on the server (`sortMode="server"`: one page per request, the design system's
`DataTable` only reports the sort) or in the table (`"client"`: a few keyed rows; the preview).
The widget renders all four tables: the Explore tickers and compare (`FeatureTable`), a
screener's results (`ScreenerResults`) and the Builder's preview (`PreviewResults`). Decision
labels, tones and the outcome tint (`OUTCOME_FILL`) live once in `entities/screen`
(`model/decisions.ts`); `entities/idea` imports them. Settled in PR 7: tables whose rows are not
instruments x catalogue features (an option chain's quotes, events, holdings, one instrument's
feature list, screeners, admin run records and checks) keep typed structure columns and are
listed, with the reason, in `columns.js`'s `STRUCTURE`; the instrument tables not migrated yet
are in its shrink-only `PENDING` (PR 8 removed screener results and preview; top ideas remains:
its earnings, expiry and display-value cells are Ideas-specific presentation, so moving it is
its own change). View preferences go through one adapter, `features/table-view`
(`useTableView(scope)`, PR 8; WEB 7).

## Enforcement

| # | Rule | Mechanism | Status |
|---|---|---|---|
| READ 1 | Only `services/read/session.py` decides which partition a read sees | ownership `session-resolution` (`partition_for`, `latest_session`, `latest_date`, `rollup_row`, `resolve_session`) | **on**: owners `session.py` and `context.py` (`open_context`); explore was an owner until PR 10b deleted it; any other caller fails |
| READ 2 | Only `services/read/**` reads session partitions for display | `tests/architecture/api/test_read_model.py::test_only_loaders_read_partitions` (AST); `test_inventory_reads_only_in_the_completeness_loader` (the context's inventory reads: `read/ops/ingestion.py` only, calls and imports) | **on**, widened in PR 10b to every use case (`src/algotrade/services/**`) and the API (`apps/api/**`): only `PARTITION_READERS` (`read/session.py`, `read/context.py`, `ondemand/screens.py` and the run-input modules `features.py`, `views.py`, `datasets.py`, each with its reason; shrink-only) pick or read a partition |
| READ 3 | GraphQL types are thin | import-linter "GraphQL types are thin" + `test_resolvers_call_one_loader` | **on** |
| READ 4 | The read model is read-only | import-linter "Read model is read-only" | **on** |
| READ 5 | No new REST GET for stored data | `architecture/rest_allowlist.toml` + two tests | **on** |
| READ 6 | Schema snapshot fresh | `tests/apps/api/graphql/test_schema.py::test_committed_schema_is_up_to_date` | **on** |
| READ 7 | Every GraphQL object mirrors a read dataclass | `test_types_mirror_read_model` | **on**; it is why `scripts/check_dupes.py` skips `graphql/types/` (ADR 0037: the mirror is by design) |
| READ 8 | One scalar coercion | ownership `scalar-coercion` (`to_value`, `to_scalar`, `call_regex = "^_(float\|text\|num)$"`) | **on** (the re-implementation rule since PR 8, with `allowed` vendor parsers, text formatters and the option-liquidity arithmetic) |
| READ 9 | Per-instrument stored values are catalogue features | `test_no_typed_feature_fields` (GraphQL types) + `test_no_typed_catalogue_fields_in_api_schemas` (REST) | **on** |
| READ 10 | A fact computed in a read is a feature first | ownership `domain-read-model` (`rollups/instrument/` literals); `chain_expiries` rule | **on** (literals; `chain_expiries` since PR 5) |
| WEB 1 | Only `shared/api` talks HTTP; no Apollo / urql / graphql-request | ESLint `HTTP_LIBRARIES` | **on** |
| WEB 2 | GraphQL documents only through the generated `graphql()` tag | ESLint ban of `graphql-tag` / `graphql` outside `shared/api/generated/graphql` | **on** |
| WEB 3 | No browser-derived facts | `web_forbidden_derivations.toml` | **on** (clean patterns); the rest per the table above |
| WEB 4 | Column defs only from the factories | ESLint `algotrade/column-factories` on `DataTableColumn` outside `entities/feature/model/columns.tsx` (`apps/web/lint-rules/columns.js`) | **on** (PR 7); `PENDING` (shrink-only) lists top ideas only since PR 8 |
| WEB 5 | Feature names typed | ESLint on `rollup.` / `feature.` / `instrument.` literals outside `feature('<name>')` (tests and stories exempt) | **on** |
| WEB 6 | Generated files fresh | `npm run generated:check` (`schema.ts`, `generated/graphql/**`); `catalogue.ts` by `tests/scripts/test_export_catalogue.py` | **on** |
| WEB 7 | One view-prefs adapter | ESLint `algotrade-views/view-adapter` on a `/preferences/` literal outside `features/table-view/api` (`apps/web/lint-rules/views.js`; `features/ideas-priority/api` allowed: the Ideas priority is not a table view) | **on** (PR 8) |

### Ownership during the migration

The ownership ratchet stayed at zero throughout: no violation was parked, no rule was narrowed
to pass. How each entry held (and, after PR 10b, holds):

- **`session-resolution`**: full detect rules on. Owners were `services/read/session.py`,
  `services/read/context.py` (`open_context` resolves once per request) and, until its modules
  were deleted, `services/explore/*` (where the six rules lived); `data/reference.py` (the
  snapshot primitive) and `services/ondemand/screens.py` (a write that runs a screen for the
  latest session, ADR 0036 decision 5) are `allowed`. Each explore module dropped out as PRs
  4-10b deleted it; `session.py` and `context.py` are now the only owners.
- **`domain-read-model`**: the `rollups/instrument/` literal rule is on (producers, the
  catalogue prefix, the table schema and screener inputs are `allowed` with reasons). The
  `chain_expiries` rule is on since PR 5 (which deleted its last read-time caller,
  `explore/ideas/ranking.py`): only `data/` and the producing feature group call it.
- **`scalar-coercion`**: `to_value` / `to_scalar` call rules on; owner `services/read/values.py`
  (`to_scalar`); `services/views.py` is `allowed` (it imports it back as `to_value`), as are
  the callers of the one coercion (explore until PR 10b; `services/preview`, screening exports
  and `rule_results`, selection). The `call_regex = "^_(float|text|num)$"` re-implementation rule is **on since
  PR 8** (`screens/table._text` deleted; `rule_results._num` reads through `to_value`), with
  `allowed` entries for the vendor payload parsers in `libs/sources`, the nightly email
  renderer and timing lines, the config writer's TOML float and the option-liquidity rollup's
  arithmetic, which parse, format or compute rather than coerce stored values.
- **`graphql-schema`**: `import strawberry` outside `apps/api/algotrade_api/graphql/*` fails now.
- **`explore-queries`**: `target_owner = services/read/*` while moving; removed in PR 10b.
  `screen-preview` is owned by `services/preview/*` since.

`tests/architecture/` was at its 10-module cap: PR 2 split the API surface and read-model
fitness tests into `tests/architecture/api/` (`test_rest_allowlist.py`, `test_read_model.py`).

## Migration plan

Each PR is independently shippable with `make check` green and updates `docs/roadmap.md`
(track RM). **R** = owner action after merge.

| # | PR | Contents | Done when |
|---|---|---|---|
| 1 | Decisions and harness | ADRs 0036-0038; this spec; `CLAUDE.md` lines; `layout.toml` dirs (empty packages, mirrored tests); ownership entries; the two import-linter contracts; `rest_allowlist.toml` + tests + `make rest-allowlist-update`; `web_forbidden_derivations.toml` (clean patterns on, the rest pending) + test; ESLint GraphQL-client bans; skills `add-graphql-field`, `add-domain-object`, rewritten `add-api-endpoint`, edited `add-web-page` / `add-feature`; `strawberry-graphql[fastapi]` in `apps/api` | `make check` green; no behaviour change |
| 2 | Session + values | `read/session.py` (`resolve_session`), `values.py` (`Unknown`, `to_scalar`; `views.to_value` becomes an import of it), `context.py` (`ReadContext`, `open_context`, `ResultCache` moved from `explore/store.py`, re-export kept); unit tests incl. the grain table; split `tests/architecture` by kind, then `test_read_model.py` with READ 2 scoped to `services/read` | 100% covered; explore untouched |
| 3 | Stored facts | `features/rollups/options/nearest_expiry.py`, its `[[table]]`, `feature.earnings_before_expiry`, `make features-doc`. **R:** `algotrade-ingest rollups --from 2024-10-03 --to <last> --only nearest_expiry@v1` | the catalogue lists them |
| 4 | Vertical slice: Instrument + features | `read/instruments/{identity,features,catalogue}.py` (+ `format`); `graphql/{schema,context,scalars,errors,loaders}.py`, `types/{session,instrument,feature}.py`; `POST /graphql`; `scripts/export_graphql_schema.py`, `apps/api/schema.graphql`, snapshot test, READ 3 resolver test, READ 7, READ 9; mypy Strawberry plugin; `scripts/export_catalogue.py` -> `catalogue.ts`; web `shared/api/graphql.ts`, `codegen.ts`, `generated/graphql`, `queryKeys.gql`, WEB 2 / 5 / 6; overview-panel reads its facts through `useInstrumentFacts`; `overview.ts` loses `earningsFacts/nextAndLast/nextEarningsDate`; enable the PR 4 derivation entries | Overview shows session-exact facts with UNKNOWN reasons |
| 5 | Screens read model + Ideas | `read/screens/{screeners,runs,results,ideas,views}.py` (one `latest_run`); `types/{screener,result,ideas,view}.py`; Ideas on the `IdeasPage` query; `summarise()` and `ideas/ranking.py` deleted; `GET /ideas` off the allow-list; the two `Idea` entries out of `TYPED_FACT_FIELDS`; `chain_expiries` detect rule; PR 5 derivation entry | every value in an Ideas row is for `ideas.session.date` or says why not |
| 6 | Explore detail pane (**done**) | `read/instruments/{events,chains,holdings,prices,series}.py`; `Instrument.{events,chain,holdings,prices,series,screenerHits,description}` (`description` came in PR 4; `screenerHits` needs PR 5's screens read model: it lands with PR 5 or PR 8); `explore/{instruments,chains,funds}` deleted; `/instruments/*`, `/chains/{id}` off the list | the detail pane is one query (per tab) |
| 7 | FeatureTable + Explore tickers + compare (**done**) | `read/instruments/table.py` (columnar, server-paged); `Query.table`; `widgets/feature-table`, the column factories (WEB 4); ticker table and compare rebuilt; `explore/{universe,compare}.py` deleted (admin review lists to `explore/review.py` until PR 10); `/explore/*`, `/universe` off the list | one page per request (no 12-page fan-out) |
| 8 | Screener results + preview + views (**done**) | `ScreenerRun.results`; `features/table-view` (+ `views.<scope>` in `preferences.toml`); screener and preview results on `feature-table`; `explore/screens/*` deleted; `/screens*` and the view GET off the list; the `_float/_text/_num` detect rule; WEB 7; `Instrument.screenerHits` | one table widget renders all four tables |
| 9 | Catalogue, distribution, backtests, configs (**done**) | `Query.{catalogue,distribution,backtests}`, screener authoring reads; `explore/{features,backtests,configs}.py` deleted; their GETs off the list | the trader workspace is fully on GraphQL |
| 10a | Admin on GraphQL (**done**) | `read/ops/{runs,quality,ingestion,review}.py`; `types/ops/*`; the Admin entities (ingestion, run, verification, review) on GraphQL; `explore/{runs,ingestion,review}.py`, `routes/{admin,runs}.py` and their schemas deleted; every `/admin` GET off the list | Admin reads no REST |
| 10b | The end of explore (**done**) | `services/explore/` deleted (preview to `services/preview/` over `ReadContext`; `store.py` split: `ReadStore` to API `deps`, `latest_session` / `store_info` to `read/session.py`, `records` to `read/values.py`); `explore-queries` removed; READ 2 widens to all use cases and the API; `add-api-endpoint` loses its read steps | allow-list = writes, jobs, health, live, preview, files |

Order: PR 4 proves the pipeline (Strawberry, dataloader, codegen, lint) on one pane with little
logic; PR 5 is the first user-visible fix and deletes the biggest bespoke module; tables come
after the object graph because they need the columnar type and the factories.

## Risks and tough calls

- **Strictness changes what users see.** On a session whose `rollups` step failed every
  feature cell is `NO_PARTITION` and Ideas lists screeners as `NOT_RUN`; the UI's
  `session.missing` banner (PR 4) makes it read as information.
- **Identity snapshots are not strict.** Making them strict needs the universe build to run for
  every catch-up session first (an ingestion change).
- **The Ideas 20-session lookback goes away** (owner decision): a screen not run for S is
  `NOT_RUN`.
- **Columnar `FeatureTable`** (`[[JSON]]`) is the honest trade for 11k rows.
- **User expression features are runtime-checked only** in TS; site features are typed.
- **Two generators** (OpenAPI and GraphQL): resolved in PR 10b. OpenAPI now describes only
  what stays REST (writes, job polling, health, live quotes, preview POSTs), GraphQL every page
  read; both stay by design, and generated-file conflicts follow the existing rule (take
  main's, regenerate).
- **Strawberry under mypy strict**: enable its plugin in PR 4; if it fights `strict`, keep
  `# type: ignore[misc]` to `graphql/types/*` only, capped by a fitness test.
- **Performance**: add `IdeasPage`, `ExploreDetail`, `Table` to the 1 s budget in
  `tests/apps/api/test_main.py` (`OPERATIONS`) as PRs 5-7 add them; PR 4 added
  `InstrumentFacts` (the Overview), PR 5 `IdeasPage`, PR 6 the detail tabs' operations
  (`InstrumentEvents`, `InstrumentPrices`, `InstrumentHistory`, `OptionChain`, `OptionQuotes`,
  `EtfHoldings`), PR 7 `Table` (the Explore table's `FeatureTable`, sorted on an expression
  feature), `CompareTable` and `ComparePrices`, PR 8 `ScreenerResults` (a run sorted on an
  expression feature with catalogue columns).
- **Events are not knowledge-dated** (PR 6): `Instrument.events` reads each event's latest
  stored version by event date, so a read pinned to a past session can show an event or a
  revision stored after it. Bounding it by `knowledge_ts` / stored partition is open; until
  then the web reads events only for the latest session. `prices` / `series` refuse an `end`
  after the session.
