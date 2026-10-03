# Working in this repo (for humans and AI agents)

This file is the entry point. The decisions below are **settled**; do not re-open them
without writing an ADR. Read in this order:

1. `docs/architecture.md`: target architecture + the rules enforced on today's code
2. `docs/roadmap.md`: which phase we are in and the open decisions
3. The spec for your area: `docs/data/layers.md`, `docs/configuration.md`,
   `docs/data/storage.md`, `docs/data/instruments.md`,
   `docs/data/vendors.md`, `docs/ui/architecture.md`, `docs/ui/design-system.md`,
   `docs/screeners/`
4. `docs/adr/README.md`: why things are the way they are

## Settled decisions (summary)

- **Four apps, one repo**: `apps/ingestion`, `apps/backtest`, `apps/api`, `apps/web`. Apps
  never import each other. They share libraries in `src/algotrade/` and talk through
  storage (and HTTP for web → api). (ADR 0004)
- **Only ingestion writes** market and feature data. (ADR 0005)
- **Vendor sources are a shared package**: every vendor adapter, the source framework and the
  vendor SDKs live in `libs/sources/algotrade_sources/` (uv workspace member
  `algotrade-sources`). Ingestion uses it for batch pulls; the API may use it later for live,
  read-only reads; backtests and the library never import it (import-linter). (ADR 0027,
  amending ADR 0005)
- **Storage by grain** (reference, event, bar(interval), chain, universe, feature, result)
  behind `Protocol` interfaces. Parquet locally (DuckDB planned). No code outside
  `storage/backends/` builds a path. (ADR 0006)
- **Point-in-time**: rows carry `ts`, `session_date`, `knowledge_ts`, `source`,
  `run_id`. Features are `name@version`, precomputed nightly. (ADR 0007)
- **Feature store**: every stored feature column is a declared `Feature` (kind, dtype, unit,
  description, null meaning, range) in a `FeatureGroup`; the catalogue `docs/data/features.md`
  is generated (`make features-doc`). Features ask `data.feature_inputs` for inputs by table
  name. A formula over existing features is an **expression feature** in
  `config/site/features/<theme>.toml` (typed language, never Python `eval`), computed on read
  unless `materialise = true`; selectable as `feature.<name>`. Users add their own (always
  virtual, never shadowing a site name) in `config/users/<id>/features/`. Re-versioned groups
  store `float32`. (ADR 0023)
- **Backtests only read stores.** They never fetch; missing data is an error. (ADR 0008)
- **Generic instruments** keyed by `instrument_id` with `multiplier`, `parent_id` and
  `calendar`, so futures and options fit without redesign. (ADR 0009)
- **FIGI ids**: equities/ETFs are `EQ:<composite FIGI>` (symbol id without one). Turn a
  ticker into an id only through `SymbolResolver` (`data.reference.resolver(reader, date)`); never
  build `EQ:` strings. (ADR 0018)
- **Long-running work is a job** via `services/jobs` (backtests, screens, nightly; the UI and
  on-request pulls later). (ADR 0010)
- **Configs, selections, users**: the universe is coverage; each strategy/screener picks a
  subset with a typed `Selection`. Site presets live in `config/site/`, user configs in
  `config/users/<id>/`; layering is defaults < site < user < run. Runs record user +
  config hash. Missing data never passes a selection. (ADR 0015)
- **Design-system-first UI**: screens use only `@algotrade/ui`. Missing component? Add it
  to the design system generically first. Dense but calm; no gradients, emoji icons or
  card-wrapped numbers. (ADR 0011) The web app is layered and component-only: see Web UI
  below. (ADR 0025)
- **Vendors**: free first, each behind the source interface. Option chains come from the Cboe
  delayed feed (full universe, nightly); IBKR covers futures and cross-checks. We compute
  Greeks ourselves. (ADRs 0012, 0014)
- **Broker access is read-only**: IBKR only through the market-data facade
  `algotrade_sources/vendors/ibkr/gateway.py`; no code may place, modify or cancel orders or touch
  account functions (ADR 0026, enforced by a fitness test and import-linter).
- **Universe**: S&P 500 + all Nasdaq-listed stocks + all ETFs including leveraged and
  inverse, saved as daily snapshots. (ADR 0013)

## Ownership (ADR 0019; enforced by `make ownership`, `make dupes`, `make arch`)

**Before writing code that does X, find X's owner in `architecture/ownership.toml`. Extend
the owner; never re-implement it elsewhere. A new responsibility needs an entry + owner in
the same PR** (`.claude/skills/add-responsibility`). The ownership ratchet
(`architecture/known_violations.toml`) is **at zero**: any violation fails CI, and a fitness
test forbids parking new ones there or adding pending contracts. A genuine exception needs an
ADR and an `allowed` entry with the reason. The dupes ratchet (`architecture/dupes_baseline.txt`)
only shrinks (`make dupes-update`).

| Responsibility | Owner |
|---|---|
| Which snapshot a read sees (on or before D, else earliest + `pre_snapshot`); domain reads of market data | `algotrade/data/` (`reference`, `prices`, `events`, `chains`, `rates`: the Treasury curve a date sees; `rollups`: stored rollup rows; `shares`: share counts by filing date); consumers never import `storage.tables.readers` |
| What a feature group reads (each input table's point-in-time read, by table name; other groups' rows) | `data/feature_inputs.py` (`load_input`; each read lives in its `data` owner); `features/` never imports storage or a domain reader |
| Computing feature groups (rollups); feature definitions + the feature catalogue | `features/framework/` (`FeatureGroup`, `Feature`, runner), `features/rollups/<group>.py` (`FEATURES` + pure compute), `features/registry.py` (`GROUPS`, `FEATURES`, `feature(name)`, `SUPERSEDED`), `features/site.py` (the site `FeatureSet`: groups + expression features), `features/catalogue.py` → `docs/data/features.md`; stored only by `tasks/derived/rollups.py` |
| Expression features: the formula language (parse, type check, evaluate); definitions from `config/site/features/*.toml`; computing them on read; retiring superseded group tables | `features/expressions/` (lexer, parser, checker, evaluator, functions; `definitions.py`, `feature_set.py`); typed by `config/site/settings.py` (`load_features`); read path `services/features.py` (`read_expressions`, column-pruned through `data.rollups.feature_rows`); `tasks/maintenance/retire_features.py` (`algotrade-ingest retire-features`) |
| Option prices + Greeks; implied vol (NaN + status code); realised vol; rate conventions (par → continuous, curve) | `algotrade/quant/` (`black_scholes`, `implied_vol`, `realized_vol`, `rates`): pure numpy, conventions in ADR 0021 |
| Run ids, run records, COMPLETE / PARTIAL | `storage/runs.py` (`start_run` + `RunRecord.finish` in services), `services/jobs/`; in ingestion `tasks/framework/run.py` (`IngestRun`): never write the loop in a task |
| Raw save; stamping; ticker → id in ingestion | `tasks/framework/run.py` (`IngestRun`) |
| Which ingestion steps run, with which defaults | `tasks/framework/registry.py`; nightly order, isolation, catch-up: `workflows/nightly/nightly.py` |
| Nightly summary report + notifications (desktop alert, daily summary email over SMTP) | `workflows/nightly/` (`records.py` inputs, `report.py` pure builder, `timing.py` run timing, `render.py` text/HTML, `notify.py` notifiers) |
| Vendor HTTP, retries, circuit breaker; pacing; building sources (incl. the golden fixture source); vendor specifics | `sources/framework/http.py`; `sources/framework/limiter.py` (one per key, cross-process); `sources/framework/registry.py`; `sources/vendors/<vendor>/` |
| Session sources (a stateful gateway connection: `SessionSource`, `opened`, `SessionSpec`) | `sources/framework/base.py`, `sources/framework/registry.py` |
| Broker API, READ-ONLY (the only `ib_async` import; market data only, never orders / accounts) | `sources/vendors/ibkr/gateway.py` (ADR 0026; `tests/libs/sources/vendors/ibkr/test_read_only_guard.py`) |
| Live verification vs IBKR (sample, checks, tolerances, `verification/ibkr`) | `tasks/verification/` (graded by the quality check `verification`) |
| Locks: named store locks, run-index lock; one ingest run at a time | `storage/locks.py`; `services/jobs/exclusive.py` |
| A run's table writes publish atomically (pending until COMPLETE / PARTIAL commits them all; FAILED drops them; crash recovery) | `storage/backends/` (`local_index.py`: commit marker + sequence); driven by `IngestRun` and `ResultWriter.publishing` (ADR 0022) |
| Running long work (threads, recovery), screens | `services/jobs/` (apps call `run_job`, never build a runner; fan-out: `as_completed`); screens: `services/screening/run.py`, submitted as `screen` jobs |
| Site settings (`config/site/*.toml` → frozen dataclasses); environment variables + `.env` | `config/site/settings.py` (one loader); `config/env.py` (storage and sources receive values as parameters) |
| Session / exchange calendar (holidays, early closes, last closed session) | `core/time/calendar.py`; never compute weekdays elsewhere |
| Which runs of a partition a read sees (`snapshot`: latest; `merge`, all `events/*` + `instruments/id_map`, `instruments/symbol_history`: union, latest per key, from the latest restating run) | `storage/backends/run_selection.py`, per `TableSpec.runs` (ADR 0007) |
| HTTP (FastAPI routers, response schemas, CORS, error mapping); read-only queries pages show | `apps/api/algotrade_api/` (routes call one query each); `services/explore/` (ADR 0024) |
| Table schemas (columns, declared types, validation); Parquet / Arrow I/O | `storage/tables/schemas.py`; `storage/backends/` (`arrow.py`: casts, `schema_version`, row groups) |
| Each stored table | exactly one producing module (`[[table]]` in the registry) |
| Which directory a module belongs in | `architecture/layout.toml` (see Directory layout below) |

## Directory layout (ADR 0020; enforced by `tests/architecture/test_layout*.py`, `make layout`)

One folder holds one kind of thing. `architecture/layout.toml` declares every directory under
`src/`, `libs/`, `apps/`, `tests/`, `config/` and `docs/` with its purpose and rules; a new folder (or
a file in an undeclared one) fails CI until it is declared there in the same PR. At most 10
modules per code or test folder and 12 files per config / docs folder (split by kind; no
exceptions); `make layout` lists folders at 8+ modules so the split is planned, not forced.
Every `__init__.py` docstring says what the folder holds. No grab-bag module names (`utils`,
`helpers`, `common`, `misc`, `shared`, ...: `[banned_module_names]`). Tests mirror their
source (`tests/unit/<path>` = `src/algotrade/<path>`, `tests/libs/sources/<path>` =
`libs/sources/algotrade_sources/<path>`, `tests/apps/ingestion/<path>` =
`apps/ingestion/algotrade_ingestion/<path>`); shared test builders live in `tests/helpers/`
(vendor payloads in `tests/helpers/payloads/`), recorded data in `tests/fixtures/`.

**Where does this go?**

| Kind of code | Folder |
|---|---|
| Vendor adapter (fetch + normalise) | `libs/sources/algotrade_sources/vendors/<vendor>/` (registered in `sources/framework/registry.py`) |
| HTTP, pacing, source protocols | `libs/sources/algotrade_sources/framework/` |
| Ingestion task | `apps/ingestion/.../tasks/<domain>/` (`reference`, `market`, `derived`, `maintenance`, `verification`) + `tasks/framework/registry.py` |
| Comparing our data with a live source (verification check) | `apps/ingestion/.../tasks/verification/` (`checks.py`) |
| Nightly step / ordering | `apps/ingestion/.../workflows/nightly/` |
| Feature (a documented column) in a feature group (rollup) | `src/algotrade/features/rollups/<group>.py` (`FEATURES` + pure compute; framework: `features/framework/`; then `make features-doc`) |
| A formula over existing features (ratio, spread, label from thresholds) | `config/site/features/<theme>.toml` (an expression feature: no code; `make features-doc`) |
| The expression language itself (a new function, operator or type) | `src/algotrade/features/expressions/` |
| What a feature group reads from a table (feature input) | `src/algotrade/data/feature_inputs.py` (`INPUTS`) + the table's read in its `data/` owner |
| Trading strategy / screener | `src/algotrade/strategies/trading/` / `strategies/screeners/` |
| Numeric model (pricing, vol, rates) | `src/algotrade/quant/` |
| Domain read of market data | `src/algotrade/data/` |
| Domain value object, calendar, strategy view | `src/algotrade/core/{model,time,views}/` |
| Use case (what an app or job runs) | `src/algotrade/services/<use-case>/`; long work as a job: `services/jobs/` |
| Read-only query a page shows (the API's backend) | `src/algotrade/services/explore/<area>.py` |
| API route / response schema | `apps/api/algotrade_api/routes/<area>.py` / `schemas/<area>.py` (`.claude/skills/add-api-endpoint`) |
| Engine running strategies / screeners | `src/algotrade/engines/<engine>/` |
| Table schema, store protocol / backend, config documents | `src/algotrade/storage/{tables,backends,configs}/` |
| Site setting | `config/site/<group>.toml` + typed in `src/algotrade/config/site/settings.py` |
| Tests | the mirrored `tests/unit/...` or `tests/apps/<app>/...` folder; builders `tests/helpers/`; cross-source checks `tests/reconciliation/` (recorded data `tests/fixtures/reconciliation/`) |
| Docs | the `docs/` area folder (`data/`, `screeners/`, `ui/`); a decision: `docs/adr/` |
| Web: token, styling, HTML, reusable visual component | `apps/web/design-system/{tokens,primitives/<Name>,components/<Name>}/` (`@algotrade/ui`) |
| Web: route, workspace (TRADER / ADMIN), provider | `apps/web/src/app/{routes/<workspace>,workspaces,providers}/` |
| Web: what one route shows / a page section | `apps/web/src/pages/<page>/` / `apps/web/src/widgets/<widget>/` |
| Web: user action or flow with state / domain model + read hooks | `apps/web/src/features/<feature>/` / `apps/web/src/entities/<entity>/` |
| Web: HTTP client, query keys / pure helper / env | `apps/web/src/shared/{api,lib/<kind>,config}/` |

**If nothing fits, add a new folder for the new kind**: declare it in `architecture/layout.toml`
with a purpose (+ `contracts` if an import-linter rule guards it), give it an `__init__.py`
docstring, and mirror it in tests. Never park code in a neighbouring folder
(`.claude/skills/add-responsibility`). Library folders: `core/{model,time,views,validation}`
(pure), `config/{site,strategy}`, `storage/{tables,backends,configs}`, `quant/`, `data/`,
`features/{framework,rollups,expressions}`, `strategies/{trading,screeners}`,
`engines/{backtest,screening,selection}`, `analytics/`,
`services/{backtests,screening,evaluation,jobs,explore}`. API app: `routes/`, `schemas/`.
Vendor sources (`libs/sources/algotrade_sources/`): `framework/`, `vendors/<vendor>/`,
`fixtures/`. Ingestion app: `cli/`, `ops/`, `tasks/{framework,<domain>}`,
`workflows/nightly/`.

## Web UI (ADR 0025; `docs/ui/architecture.md`; enforced by ESLint, Stylelint, `make web-check`, `test_layout_web.py`)

`apps/web` (Vite, React 19, TypeScript strict, TanStack Router + Query, Storybook, Vitest,
Playwright; npm workspaces, lockfile `apps/web/package-lock.json`). **Every part of the UI is a
component**: styling and raw HTML exist only in `apps/web/design-system/` (`@algotrade/ui`:
tokens, primitives, components, each with stories for every state, a unit test with axe and
light / dark screenshots). App code in `src/` is layered `app -> pages -> widgets -> features ->
entities -> shared -> @algotrade/ui`: it imports only downward, other slices only through their
`index.ts`, never a sibling slice; it renders no HTML elements and passes no `className` /
`style`; no CSS files, colours or px outside the design system; only `src/shared/api` talks HTTP
(client generated from the API's OpenAPI document), data through Query hooks in entities /
features; only `src/app` routes. Two workspaces in a horizontal top bar: TRADER (Ideas,
Screeners, Explore, Backtests) and ADMIN (Ingestion, Screener runs, Users & configs); role
gating goes only in `src/app/workspaces/guard.ts`. Order (ADR 0011): tokens (FINAL, approved
mockups 2026-10-03) -> primitives -> components -> screens; screens lay out and set text only
with the primitives (Box, Surface, Stack, Grid, Text, Heading, Mono, Divider, VisuallyHidden).
Every folder is a `[[web_dir]]` in `architecture/layout.toml`. Lint messages name the rule and
the skill with the fix.

## Code rules (enforced by CI; follow them up front)

1. **Respect layers.** Strategies and screeners import only `core` (`core.views` for data,
   `core.model` for types and errors) and `quant` (pricing maths). `quant` imports only numpy
   and `core`. `core/` imports no other `algotrade` package and no pandas.
   Check with `make arch`.
2. **No file over 1000 lines** (aim for under 300). Split by responsibility. `make filelen`.
3. **Every module starts with a docstring** stating its single responsibility.
4. **Tests mirror src**: `src/algotrade/<path>/x.py` → `tests/unit/<path>/` (apps:
   `tests/apps/<app>/<path>/`; enforced by the layout tests). Coverage gate is
   90%. Storage backends must pass `tests/contract/storage/`. Vendor adapters are tested
   against recorded responses; CI never calls the network.
5. **UTC, timezone-aware datetimes only.** `session_date` is the trading day. No `print`
   outside CLI/app entry points.
6. **Never hand-edit** `datasets/golden/*` or `benchmarks/baseline.json`. Use
   `make datasets-build` / `make baseline`, and explain baseline diffs in the PR.
7. **Strategies and screeners are deterministic** and must pass `tests/property`.
8. Secrets come only from environment variables. Never commit credentials.
   Dependencies go in the pyproject of the package that needs them (an app's own, not the
   library's), then `uv lock`; commit `uv.lock`.
9. Before finishing any change, run `make check`.
10. **PRs auto-merge** (squash, branch deleted) once every CI check on the latest commit
    passes (`.github/workflows/auto-merge.yml`). Open work in progress as a draft, or label
    it `no-automerge`, to keep it open for review. CI's Python jobs run on the owner's Mac
    (self-hosted runners; they queue while it sleeps): see `docs/ci.md`.

## Workflows: use the matching skill

| Task | Skill |
|---|---|
| New vendor / data source | `.claude/skills/add-data-source` |
| New dataset or data grain | `.claude/skills/add-dataset` |
| New feature (a stored column, or a formula over features: TOML) | `.claude/skills/add-feature` |
| New trading strategy | `.claude/skills/add-strategy` |
| New screener | `.claude/skills/add-screener` |
| New UI component (design system) or visual element | `.claude/skills/add-ui-component` |
| New web page, route or data hook | `.claude/skills/add-web-page` |
| New responsibility, or moving one between modules | `.claude/skills/add-responsibility` |
| New API endpoint | `.claude/skills/add-api-endpoint` |
| A decision that changes architecture | `.claude/skills/write-adr` |

Commands (need `uv`): `make install` (= `uv sync --all-packages --locked`), `make check`, `make test`, `make layout`, `make evaluate`, `make baseline`, `make features-doc`.
Web (need Node 24): `make web-install`, `make web-check` (part of `make check`), `make web-visual` (screenshots, Docker); in `apps/web`: `npm run dev|storybook|check|visual:update`.
Ingestion: `algotrade-ingest universe|universe-build|company-details|shares|earnings|bars|rates|corporate-actions|chains|rollups|verify|screen|nightly|report|quality|schedule|purge-raw|retire-features|migrate-ids|golden`, or `algotrade-ingest run <task>` for any registry task (see `README.md`).
API: `algotrade-api [--reload]` (read-only, 127.0.0.1:8000); after a route / schema change run
`scripts/export_openapi.py` and commit `apps/api/openapi.json`.
Configs: site presets in `config/site/` (reviewed via PR); user configs in `config/users/<id>/`
(git-ignored). Check one with `algotrade-backtest [--user U] config validate|show <id>`; a
user's expression features with `config validate-features`.
