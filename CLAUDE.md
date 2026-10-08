# Working in this repo (for humans and AI agents)

This file is the entry point. The decisions below are **settled**; do not re-open them
without writing an ADR. Fresh session: run `/start` (`make doctor` + `make status` + the roadmap pickup list); end with
`/wrap-up`. Note owner corrections and rule-preventable errors as you go; propose them via
`.claude/skills/capture-learning` (checked for overlap and contradiction) before the PR.
Read in this order, **by section and only when the task needs it** (grep, then read the lines):

1. `docs/roadmap.md`, **"Now / Next" only** (`/start` reads just that): running jobs, next
   items, facts; a PR that opens or closes one updates it. Phase tables and open decisions only on request.
2. `docs/architecture.md` (target architecture + the rules enforced on today's code) and the
   spec for your area: `docs/data/layers.md`, `docs/configuration.md`, `docs/data/storage.md`,
   `docs/data/instruments.md`, `docs/data/vendors.md`, `docs/ui/architecture.md`,
   `docs/ui/design-system.md`, `docs/screeners/`, `docs/api/read-model.md`.
3. `docs/adr/README.md`: why things are the way they are (the ADR number follows each decision below).

## Settled decisions (one line each; the ADR has the detail)

- **Four apps, one repo** (`apps/{ingestion,backtest,api,web}`): they never import each other; they share `src/algotrade/` and talk through storage (HTTP for web to api). (ADR 0004)
- **Writes**: ingestion writes market and feature data. The API writes only user configs (ADR 0029), its live-quote log (ADR 0028) and the results of a screener run on request (ADR 0033) and a derived cache of regime explanations (ADR 0041). (ADR 0005)
- **Vendor sources are a shared package** `libs/sources/algotrade_sources/` (vendor SDKs live there): ingestion uses it for batch pulls, the API for live quotes; backtests and the library never import it. (ADR 0027)
- **Storage by grain** behind `Protocol` interfaces, Parquet locally; no code outside `storage/backends/` builds a path. (ADR 0006)
- **Point-in-time**: rows carry `ts`, `session_date`, `knowledge_ts`, `source`, `run_id`; features are `name@version`, precomputed nightly. (ADR 0007)
- **Feature store**: every stored feature is a declared `Feature` in a `FeatureGroup`; a formula over features is a TOML expression feature (never Python `eval`); catalogue `docs/data/features.md` is generated (`make features-doc`); mechanics in `.claude/skills/add-feature`. (ADR 0023)
- **Backtests only read stores**; missing data is an error. (ADR 0008)
- **Generic instruments** keyed by `instrument_id` with `multiplier`, `parent_id`, `calendar`. (ADR 0009)
- **FIGI ids** (`EQ:<composite FIGI>`): turn a ticker into an id only through `SymbolResolver`; never build `EQ:` strings. (ADR 0018)
- **Long-running work is a job** via `services/jobs`. (ADR 0010)
- **Configs, selections, users**: layering defaults < site < user < run; site presets in `config/site/`, user configs in `config/users/<id>/`; runs record user + config hash; missing data never passes a selection. (ADR 0015) **Users** are declared in `config/site/users.toml` with a role (`admin` / `trader`; `UsersSettings`); Supabase Auth authenticates them behind the one `Authenticator` seam in `apps/api/algotrade_api/auth/` (roles never come from the provider), and `guard.ts` reads the role from `Query.viewer`. (ADR 0040)
- **Hosting**: from the owner's Mac behind Tailscale Funnel; the API serves the built web (`make web-build` -> `var/web`, `ALGOTRADE_WEB_DIST`) on its own origin, mounted last; the API runs as a launchd agent (`algotrade-api schedule`, written, never installed); runbook `docs/hosting.md`. (ADR 0044)
- **Design-system-first UI**: screens use only `@algotrade/ui`; a missing component is added to the design system first; the web app is layered and component-only (Web UI below). (ADRs 0011, 0025)
- **One UI for phones and desktops**: no mobile pages or variants; layout by container query, a multi-column `Grid` passes `collapse`, a list beside its detail is `MasterDetail`, touch sizing from the density tokens; checked by ESLint rule 10, a `Narrow` story per responsive component and the e2e `phone` project; skill `.claude/skills/responsive-ui`. (ADR 0052)
- **Vendors**: free first behind the source interface; Cboe chains, IBKR for futures and enrichment (IV rank prefers IBKR, labelled `iv_rank_source`; IBKR-derived features carry `licence = "personal"`); we compute Greeks ourselves; descriptions: Massive overview for stocks (capped per night), SEC prospectus objective for ETFs (ADR 0034). (ADRs 0012, 0014, 0028, 0034)
- **Broker access is read-only**: IBKR only through `algotrade_sources/vendors/ibkr/gateway.py`; no orders, no account functions (fitness test + import-linter). (ADR 0026)
- **Universe**: S&P 500 + Nasdaq-listed stocks + all ETFs, daily snapshots. (ADR 0013)
- **Reads serve one session**: every read resolves the session once (`services/read/session.py`) and reads session-grain tables for exactly that date; a fact not stored for it is UNKNOWN with a reason (`services/read/values.py`), never an older partition; a screener with no run for it is NOT_RUN. Snapshot tables (reference, company, universe) follow ADR 0007's one rule and say which snapshot they used. (ADR 0036)
- **One read model, one graph**: page data is a domain read object in `src/algotrade/services/read/` (one loader per object) served by GraphQL (`apps/api/algotrade_api/graphql/`, snapshot `apps/api/schema.graphql`). REST only for writes, job polling, health, live quotes, preview POSTs and files (`architecture/rest_allowlist.toml`, shrink-only). New page read: `.claude/skills/add-graphql-field`; new object: `.claude/skills/add-domain-object`; status and plan: `docs/api/read-model.md`. (ADR 0037)
- **Per-instrument stored values are catalogue features**: read by name through `features(names)`, never a typed field (REST legacy reads included: `features` dict; test `test_no_typed_catalogue_fields_in_api_schemas`); a fact a page needs that is not stored is a feature first (`add-feature`). The browser derives nothing from raw rows (`architecture/web_forbidden_derivations.toml`); tables are `widgets/feature-table` with the column factories in `entities/feature`. (ADR 0038)
- **Natural-language screener drafts**: a sentence becomes a draft rule screen through one `TextModel` protocol (`services/text_model`, also behind the on-demand regime explanation in `services/explaining`) and the one OpenAI-compatible adapter in `algotrade_sources/llm` (provider by `config/site/llm.toml` `base_url`; key only from `ALGOTRADE_LLM_API_KEY`; off by default); the prompt is the sentence, the catalogue, the phrasebook and the field guide (`config/site/field_guide/*.toml`: how to read each field, the criterion per intent, the caveats; rendered to `docs/data/field-guide.md` by `make features-doc`); invented fields are dropped with a reason, the rest validated as finalise; a draft the Builder loads, never a write or a run. (ADR 0041)
- **The Guide** (`/guide`, a utility link on the right of the top bar): every explanation is written once as a Guide entry in site config (fields, situations, regime indicators and episodes, playbooks, glossary, how-to) and a page shows it only through `InfoButton` + `HelpDrawer` given an entry reference, never text; no explanatory prose in `apps/web/src` (shrink-only baseline `architecture/web_prose.toml`); spec `docs/ui/guide.md`, mechanics `.claude/skills/add-guide-content`. (ADR 0051)
- **Event sensitivity**: what moves a name is measured per event class (own, peer, macro, market structure, unscheduled, factor-dated) as catalogue features over the scope list `config/site/events/scope.toml` plus tier A / B names; every event row carries `known_from` (read as `known_from <= S`; statistics only over events complete by S); unscheduled moves are attributed from 8-K items, then capped headlines through the text-model seam, then the owner-run deep-dive skill whose dossier enters through `dossier-import` (ingestion stays the writer); plan `docs/event-sensitivity-plan.md`. (ADR 0050)
- **Edges**: an edge is a typed document `config/site/edges/<id>.toml` (thesis, persistence reason, outcome, schedule, frozen period) whose screeners are its implementations; outcomes are a grain `outcomes/instrument/<name>@v1` (`session_date` = start session, `knowledge_ts` = window close) written only by ingestion and read only by `data/outcomes`, importable only from `services/evaluation` (the one exception to the one-session rule); one cross-section harness scores each screener point in time (hit rate vs base rate, lift, decile spread, frozen period, trial log; statistics in `quant/`); ML proposes and implements, never judges; plan `docs/edges-plan.md`. (ADR 0053)
- **Ingestion workflows** by cadence: `market-daily` (gates screens), weekly `reference`, `enrichment`. A step declares `needs` and runs only when they SUCCEEDED; it SUCCEEDS or FAILS by its acceptance checks (thresholds in `sources.toml [quality]`), never PARTIAL; a failed critical step holds back the workflow and every later session until it succeeds or is waived by hand (`--waive`). (ADR 0039)

## Ownership (ADR 0019; enforced by `make ownership`, `make dupes`, `make arch`)

**Before writing code that does X, find X's owner:** `grep <keyword> architecture/*ownership.toml`
(authoritative: every responsibility; stored tables are in `architecture/tables.toml`). Extend the owner; never re-implement it elsewhere. **A new responsibility needs an entry + owner in the same PR** (`.claude/skills/add-responsibility`). The ownership ratchet
(`architecture/known_violations.toml`) is **at zero**: any violation fails CI, and a fitness
test forbids parking new ones there or adding pending contracts. A genuine exception needs an
ADR and an `allowed` entry with the reason. **Never game a check** (e.g. reordering fields to
dodge `make dupes`): fix the structure, or justify the exception in the PR. The dupes ratchet (`architecture/dupes_baseline.txt`)
only shrinks (`make dupes-update`).
Non-obvious: the expression language is `features/expressions/`, definitions are TOML in
`config/site/features/`; run ids / run records are `storage/runs.py` + `services/jobs/` +
`IngestRun` (never write the ingest loop in a task); only `data/` reads market data
(consumers never import `storage.tables.readers`).

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

**Where does this go?** `grep -n purpose architecture/*layout.toml` (every folder, with its
purpose). The non-obvious cases:

| Kind of code | Folder |
|---|---|
| A formula over existing features (ratio, spread, label from thresholds) | `config/site/features/<theme>.toml`, an expression feature: no code; `make features-doc` (`add-feature`) |
| A feature (a documented column) in a feature group | `src/algotrade/features/rollups/<kind>/<group>.py` (`FEATURES` + pure compute); then `make features-doc` |
| A feature derived from a personal-use source (IBKR) | its group in `features/rollups/` with `licence="personal"` on each `Feature`; expression features over it inherit the licence (ADR 0028) |
| Comparing our data with a live source (verification check) | `apps/ingestion/.../tasks/verification/` (`checks.py`) |
| A read object or loader a page needs | `src/algotrade/services/read/<area>/` (`add-domain-object`) |
| A GraphQL field | `apps/api/algotrade_api/graphql/types/<area>/<object>.py` (`add-graphql-field`) |
| A REST write, job, live or file endpoint | `apps/api/algotrade_api/{routes,schemas}/` (`add-api-endpoint`); a Builder dry run (preview POST) in `src/algotrade/services/preview/` |
| Web: component / page / feature | see Web UI below and `docs/ui/architecture.md` |

**If nothing fits, add a new folder for the new kind**: declare it in `architecture/layout.toml`
with a purpose (+ `contracts` if an import-linter rule guards it), give it an `__init__.py`
docstring, and mirror it in tests. Never park code in a neighbouring folder
(`.claude/skills/add-responsibility`). A folder at its cap: split it by kind first.

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
Every folder is a `[[web_dir]]` in `architecture/web_layout.toml`. Lint messages name the rule and
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
   90%. **A fix for a reported issue adds the test that would have caught it** at
   implementation time (a fitness test over config, a contract test, or a unit test; a
   regression test only when nothing structural fits) and names it first in the PR
   (owner rule 2026-10-06; `capture-learning`). Storage backends must pass `tests/contract/storage/`. Vendor adapters are tested
   against recorded responses; CI never calls the network: a root autouse fixture
   (`tests/conftest.py`) refuses real sockets; a test that needs a localhost server is marked
   `@pytest.mark.allow_localhost`.
5. **UTC, timezone-aware datetimes only.** `session_date` is the trading day. No `print`
   outside CLI/app entry points.
6. **Never hand-edit** `datasets/golden/*` or `benchmarks/baseline.json`. Use
   `make datasets-build` / `make baseline`, and explain baseline diffs in the PR.
7. **Strategies and screeners are deterministic** and must pass `tests/property`.
8. Secrets come only from environment variables. Never commit credentials.
   Dependencies go in the pyproject of the package that needs them (an app's own, not the
   library's), then `uv lock`; commit `uv.lock`.
9. Check narrow first (`make changed`: mirrored tests, mapped web checks, fast gates), then run the full
   `make check WORKERS=2 WEB_WORKERS=2` once before the push; after a failure rerun only the failed
   gate (`make <gate>` / `npm run <script>`), never the whole `make check` again.
10. **Push and open the PR yourself, then move on.** When `make check` passes, push the
    feature branch (never `main`, never force-push; merge `origin/main` right before every push
    when other sessions are landing PRs), open the PR from the template and start
    the next work item; do not ask the owner first and do not wait for CI (owner decision
    2026-10-04). Only merging is off limits (below). A harness-learning PR still follows
    `capture-learning`. ADR and web-rule numbers are checked against origin/main
    (`make numbering`): take the next free number right before the push; `scripts/merge_main.sh`
    does the merge of main, regenerating generated files on conflict.
    **PRs auto-merge** (squash, branch deleted) once every CI check on the latest commit
    passes (`.github/workflows/auto-merge.yml`). Open work in progress as a draft, or label
    it `no-automerge`, to keep it open for review. **Never merge yourself**: no
    `gh pr merge` (with or without `--auto`), no enabling GitHub auto-merge, no admin
    bypass. Branch protection on `main` requires the CI checks (admins included); only
    the workflow merges, and only on green. The repo is public: CI runs on
    GitHub-hosted runners only, never self-hosted ones (`docs/ci.md`).
    **No stacked PRs into a branch that will be deleted**: squash-merge deletes the base and
    GitHub closes the stacked PR (#99, #103). Branch from `main`; if stacking is unavoidable,
    label the stacked PR `no-automerge` and retarget it to `main` before its base merges.
    **Generated files** (`apps/api/openapi.json`, `apps/web/src/shared/api/generated/*`): on a
    merge conflict never hand-merge; take main's, then regenerate (`scripts/export_openapi.py`,
    `npm run api:generate`).
## Workflows: use the matching skill

| Task | Skill |
|---|---|
| New vendor / data source | `.claude/skills/add-data-source` |
| New dataset or data grain | `.claude/skills/add-dataset` |
| New feature (a stored column, or a formula over features: TOML) | `.claude/skills/add-feature` |
| New trading strategy | `.claude/skills/add-strategy` |
| New screener | `.claude/skills/add-screener` |
| New UI component (design system) or visual element | `.claude/skills/add-ui-component` |
| Explaining anything to the user (meaning, how to read, when it lies), or moving an explanation into the Guide | `.claude/skills/add-guide-content` |
| Any UI change: keep it working on phones and desktops (one tree) | `.claude/skills/responsive-ui` |
| New web page, route or data hook | `.claude/skills/add-web-page` |
| New responsibility, or moving one between modules | `.claude/skills/add-responsibility` |
| New page read (a GraphQL field) | `.claude/skills/add-graphql-field` |
| New domain read object (and its loader) | `.claude/skills/add-domain-object` |
| New REST endpoint (writes, jobs, live, files only) | `.claude/skills/add-api-endpoint` |
| A decision that changes architecture | `.claude/skills/write-adr` |
| A lesson from this session (owner correction, rule-preventable error) | `.claude/skills/capture-learning` |

Worktrees: `scripts/worktree.sh <branch> [base]` makes `../algo-trading-<slug>` off
`origin/main` (links `.venv`, writes `worktree.env` with the worktree's absolute `PYTHONPATH`,
runs its own `npm ci`); `source` that file; `--remove` cleans up one, `--prune-merged` removes the worktrees of merged PRs
(leftovers filled the disk 2026-10-06; `make doctor` warns). Never symlink `node_modules`
to main's: `make check`'s `npm ci` through the link empties main's. **Never `uv sync` /
`make install` in a worktree** (agent worktrees too): through the `.venv` link it points the
main checkout's venv, which launchd's nightly and the API run, at the worktree's code
(2026-10-05); use `worktree.env`'s `PYTHONPATH`. `make install` refuses, `make doctor` fails,
the nightly refuses to start. An agent worktree (`.claude/worktrees/`) links `.venv` and writes
`worktree.env` itself; where `source` is refused, prefix with `env PYTHONPATH=...`
(`.claude/agents/implementer.md`). Never `--no-verify` / `SKIP=`: the hooks work in a worktree.

Commands (need `uv`; `make doctor` checks the machine, `make status` shows PRs, jobs, store): `make install` (= `uv sync --all-packages --locked`), `make check`, `make test`, `make perf` (strict timing budgets; run on an idle machine), `make layout`, `make evaluate`, `make baseline`, `make features-doc`.
Web (need Node 24): `make web-install`, `make web-check` (part of `make check`), `make web-visual` (screenshots, Docker); in `apps/web`: `npm run dev|storybook|check|visual:update`.
Ingestion: `algotrade-ingest --help` lists the commands; `algotrade-ingest run <task>` runs any registry task, e.g. `run ibkr-contracts`, `run ibkr-iv --from D1 --to D2 [--limit N]` (the resumable IBKR IV backfill; see `README.md`).
API: `algotrade-api [--reload]` (127.0.0.1:8000; reads, plus user-config writes via `services/authoring`); after a route / schema change run
`scripts/export_openapi.py` and commit `apps/api/openapi.json`.
Configs: site presets in `config/site/` (reviewed via PR); user configs in `config/users/<id>/`
(git-ignored). Check one with `algotrade-backtest [--user U] config validate|show <id>`; a
user's expression features with `config validate-features`.

## Agents, models and tokens (spend tokens where mistakes are expensive)

Match the model to the risk of the task, not its size. Subagents in `.claude/agents/`
(`scout`, `checker`, `implementer`, `architect`; their descriptions say when) pin their
model; delegate by name (for an ad hoc agent, pass `model` explicitly).

Quality is not traded for tokens: the cheaper model never decides design, `make check`
gates every change whatever wrote it, a change in an `architect` area (new responsibility /
folder / table / ADR, layer boundaries, point-in-time, `quant/` maths, atomic publish, locks
and jobs, the IBKR read-only boundary, a bug that survived two fixes) gets an `architect`
review of the diff before it is finished, and an agent that hits ambiguity or fails the same
check twice escalates one tier instead of retrying.

Shared machine: at most 2 agents at once, and agents run `make check WORKERS=2 WEB_WORKERS=2`
(`pytest -n 2`, `vitest --maxWorkers=2`; overload caused false timeouts on #94 / #95 / #98).
The owner and CI use the defaults (`WORKERS=auto`).

Token habits (every session):

- **Never `pkill -f make`, `pkill -f node`, `pkill -f vite` or `pkill -f playwright`**: it kills
  another session's 30-40 min run. Stop your own run by its PID or job; `make check` holds a
  per-worktree lock (`scripts/ops/check_lock.sh`) and `make doctor` lists the other runs.
- **One fresh session per work item**; batch related bugs into it. Sonnet for scoped fixes,
  Opus for design, storage, IBKR, point-in-time and engine work. Plan before code on new work.
  Do not keep a session waiting on CI: close it when its PR is up. Spin side issues off as
  separate tasks.
- **Ingestion / backfill runs longer than ~2 h run detached** (`nohup` script writing a status
  file under `var/logs/`; README "Long runs"), never as a tool background command (killed at
  its limit).
- **Grep, then read the lines you need.** Long docs (`docs/architecture.md`,
  `docs/configuration.md`, `docs/data/layers.md`) are read by section; owners by grepping
  `architecture/ownership.toml`; the feature catalogue `docs/data/features.md` by grep.
- **Never open generated or bulk files**: `uv.lock`, `apps/web/package-lock.json`,
  `apps/api/openapi.json`, `datasets/golden/**`, `tests/fixtures/**`, `__screenshots__/`.
- **Verify narrow first**: `make changed` (the mirrored tests of every file changed vs
  `origin/main`, then `arch`, `layout`, `ownership`), or one test file (`.venv/bin/python -m
  pytest <path> -q -x`); then `make check` once before pushing. Send long runs to `checker`
  or pipe through `tail`. Re-run `make web-visual` only when the design system changed.
- **Brief by pointer, report in the PR**: brief a subagent with paths, the owner, the skill
  and the acceptance check, not pasted file contents. A subagent's hand-back is at most 150
  words (PR link, checks and result, deviations from the brief, decisions needed); the full
  write-up (findings, timings, screenshots) goes in the PR description, where it is read once.
- **Check pages by text first**: verify a web page through its text and accessibility tree;
  take a screenshot only for a visual state they cannot show, once per state, at reduced
  scale.
- **Load only the matching skill**, run independent agents in parallel in one message, and
  do not re-read a file you just edited or paste whole files or diffs into the chat.

Harness audit: `/audit-harness` (`.claude/skills/audit-harness`); `/start` flags one older than
30 days (date in `docs/roadmap.md` Now / Next), `/wrap-up` triggers it at CLAUDE.md >= 290 lines.
