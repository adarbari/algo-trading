# Working in this repo (for humans and AI agents)

This file is the entry point. The decisions below are **settled**; do not re-open them
without writing an ADR. Read in this order:

1. `docs/architecture.md`: target architecture + the rules enforced on today's code
2. `docs/roadmap.md`: which phase we are in and the open decisions
3. The spec for your area: `docs/data/layers.md`, `docs/configuration.md`,
   `docs/data/storage.md`, `docs/data/instruments.md`,
   `docs/data/vendors.md`, `docs/ui/design-system.md`, `docs/screeners/`
4. `docs/adr/README.md`: why things are the way they are

## Settled decisions (summary)

- **Four apps, one repo**: `apps/ingestion`, `apps/backtest`, `apps/api`, `apps/web`. Apps
  never import each other. They share libraries in `src/algotrade/` and talk through
  storage (and HTTP for web → api). (ADR 0004)
- **Only ingestion writes** market and feature data. Vendor SDKs and secrets live only in
  `apps/ingestion/sources/`. (ADR 0005)
- **Storage by grain** (reference, event, bar(interval), chain, universe, feature, result)
  behind `Protocol` interfaces. Parquet locally (DuckDB planned). No code outside
  `storage/backends/` builds a path. (ADR 0006)
- **Point-in-time**: rows carry `ts`, `session_date`, `knowledge_ts`, `source`,
  `run_id`. Features are `name@version`, precomputed nightly. (ADR 0007)
- **Backtests only read stores.** They never fetch; missing data is an error. (ADR 0008)
- **Generic instruments** keyed by `instrument_id` with `multiplier`, `parent_id` and
  `calendar`, so futures and options fit without redesign. (ADR 0009)
- **FIGI ids**: equities/ETFs are `EQ:<composite FIGI>` (symbol id without one). Turn a
  ticker into an id only through `SymbolResolver` (`StoreReader.resolver(date)`); never
  build `EQ:` strings. (ADR 0018)
- **Long-running work is a job** via `services/jobs` (backtests, screens, nightly; the UI and
  on-request pulls later). (ADR 0010)
- **Configs, selections, users**: the universe is coverage; each strategy/screener picks a
  subset with a typed `Selection`. Site presets live in `config/site/`, user configs in
  `config/users/<id>/`; layering is defaults < site < user < run. Runs record user +
  config hash. Missing data never passes a selection. (ADR 0015)
- **Design-system-first UI**: screens use only `@algotrade/ui`. Missing component? Add it
  to the design system generically first. Dense but calm; no gradients, emoji icons or
  card-wrapped numbers. (ADR 0011)
- **Vendors**: free first, each behind the source interface. Option chains come from the Cboe
  delayed feed (full universe, nightly); IBKR covers futures and cross-checks. We compute
  Greeks ourselves. (ADRs 0012, 0014)
- **Universe**: S&P 500 + all Nasdaq-listed stocks + all ETFs including leveraged and
  inverse, saved as daily snapshots. (ADR 0013)

## Code rules (enforced by CI; follow them up front)

1. **Respect layers.** Strategies and screeners import only `core` (plus `FeatureView` /
   `quant` once they exist). `core/` imports no other `algotrade` package and no pandas.
   Check with `make arch`.
2. **No file over 1000 lines** (aim for under 300). Split by responsibility. `make filelen`.
3. **Every module starts with a docstring** stating its single responsibility.
4. **Tests mirror src**: `src/algotrade/<layer>/x.py` → `tests/unit/<layer>/`. Coverage gate is
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
    it `no-automerge`, to keep it open for review.

## Workflows: use the matching skill

| Task | Skill |
|---|---|
| New vendor / data source | `.claude/skills/add-data-source` |
| New dataset or data grain | `.claude/skills/add-dataset` |
| New feature | `.claude/skills/add-feature` |
| New trading strategy | `.claude/skills/add-strategy` |
| New screener | `.claude/skills/add-screener` |
| New UI widget or screen | `.claude/skills/add-ui-component` |
| A decision that changes architecture | `.claude/skills/write-adr` |

Commands (need `uv`): `make install` (= `uv sync --all-packages --locked`), `make check`, `make test`, `make evaluate`, `make baseline`.
Ingestion: `algotrade-ingest universe|universe-build|company-details|earnings|bars|corporate-actions|chains|features|screen|nightly|quality|schedule|purge-raw|migrate-ids|golden` (see `README.md`).
Configs: site presets in `config/site/` (reviewed via PR); user configs in `config/users/<id>/`
(git-ignored). Check one with `algotrade-backtest [--user U] config validate|show <id>`.
