# Configuration: configs, selections and users

The **universe is coverage** (every instrument we ingest). Each strategy or screener works on
its own subset, chosen by a **selection** in a **config**. Configs exist at the site level
(L3, shared) and per user (L4). Decision record: [ADR 0015](adr/0015-configs-selections-users.md).
Where configs sit among the data layers: [data/layers.md](data/layers.md).

## Where configs live

```
config/site/                        L3: reviewed via PR, versioned by git
  defaults.toml                     [screening] and [backtest] defaults
  presets/selections/<id>.toml      shared selections
  presets/strategies/<id>.toml      shared strategy / screener configs
config/users/<user_id>/             L4: git-ignored locally; a DB behind ConfigStore later
  selections/<id>.toml
  strategies/<id>.toml
```

The location comes from `ALGOTRADE_CONFIG_DIR` (default `./config`) or `--config-dir`. Only
`storage/backends/config_files.py` knows this layout; everything else uses the `ConfigStore`
protocol (`load(scope, kind, name)`, `names`, `users`).

## Objects (`src/algotrade/config/`, pure, no I/O)

```text
Rule           { field, op: eq|ne|in|not_in|gt|gte|lt|lte|between|is_null|not_null, value }
Group          { all: [Rule|Group] } | { any: [Rule|Group] } | { not: Rule|Group }
Selection      { name, where: Group, max_instruments?, order_by? }   # top-N by a field
StrategyConfig { id, kind: screener|strategy, impl, params, selection (preset name or inline),
                 selection_overrides?, schedule?: nightly, exports?: [...],
                 screening?: {...}, backtest?: {...}, extends? (user configs) }
ResolvedConfig { config, selection, settings, user, layers, hash }
UserContext    { user_id }   # a validated label: [a-z0-9_-]{1,64}
```

Parsing errors name the exact path, e.g. `users/alice/strategies/x.selection.where.all[2]: op
must be one of [...]`. A bad config never runs (fail closed).

## Resolution

```
built-in defaults  <  L3 site (defaults.toml + preset)  <  L4 user config  <  run-time overrides
```

- **Find the document.** A user config with the same id overrides the site preset of that id;
  `extends = "<preset id>"` builds a new id on top of a preset; a user-only config needs no
  preset. The `site` user (scheduled site presets) never reads user documents.
- **Merge.** Tables merge deeply; lists are replaced.
- **Selection.** A preset name resolves user-first, then site. A user either **narrows** the
  preset with `selection_overrides` (AND-ed with the preset's rules, so later preset fixes
  still apply) or **replaces** it with its own `selection`. A user can never widen coverage:
  covering a new instrument is a site change.
- **Settings.** `[screening]` and `[backtest]` come from defaults, overridden by the config.
- **Hash.** SHA-256 of everything that affects results (impl, params, selection, schedule,
  exports, settings), not of provenance. Every result row and run record carries `user_id`,
  `config_id` and `config_hash`; `layers` records which files were used.

## Selections

Fields come from a catalogue built from the code, so a typo or a type mismatch fails at load:

| Field | Source table | Example |
|---|---|---|
| `instrument.<column>` | L1 `instruments/reference` | `instrument.security_type`, `instrument.is_leveraged` |
| `rollup.<name>@v<N>.<column>` | `rollups/instrument/<name>@v<N>` (columns declared on the rollup) | `rollup.option_liquidity@v1.put_tier` |

Evaluation (`engines/selection/`) uses **three-valued logic**: a missing value is UNKNOWN,
UNKNOWN propagates through `all`/`any`/`not`, and only TRUE selects. Missing data therefore
excludes an instrument and is counted, never passed. The audit saved with every run has, per
top-level rule, the counts passed / failed / unknown and the funnel remaining after each rule
(for `all`). Selection is evaluated **as of the run's session** (a backtest's start date), so
backtests never use today's universe.

Example site preset (`config/site/presets/selections/liquid_optionable.toml`):

```toml
name = "liquid_optionable"
[where]
all = [
  { field = "instrument.security_type", op = "in", value = ["COMMON_STOCK", "ADR", "ETF"] },
  { field = "instrument.status", op = "eq", value = "ACTIVE" },
  { field = "instrument.optionable", op = "eq", value = true },
]
```

Example user config narrowing a preset (`config/users/abhinav/strategies/short_premium.toml`):

```toml
extends = "short_premium_liquidity"
schedule = "nightly"
[selection_overrides]
all = [ { field = "instrument.is_leveraged", op = "eq", value = false } ]
```

## Users

Phase 0 identity is a **label for namespacing, not authentication**: `--user` on both CLIs
(default `local`; `site` for runs scheduled from site presets). Market data and rollups are
global; configs, results and jobs are per user. Phase 4 maps authenticated users to
`user_id`, and services enforce that users only read and write their own configs, results
and jobs.

Rules: configs never contain secrets (credentials come only from environment variables); ids
are restricted to `[a-z0-9_-]`, so they are safe in paths.

## Running configs

```bash
algotrade-backtest [--user U] config validate|show <id>
algotrade-backtest [--user U] backtest --config <id> --start 2024-01-02 --end 2025-12-31
algotrade-ingest   screen --config <id> --user U [--date D] [--export-dir out/]
algotrade-ingest   nightly        # every config with schedule = "nightly": site presets + each user's
```

All of these run as **jobs** (see [architecture.md](architecture.md#jobs)).

## Planned (see the [roadmap](roadmap.md))

| Item | Status |
|---|---|
| `ALGOTRADE_USER` env var as the default for `--user` | follow-up |
| Lint rejecting secret-like keys (`*key*`, `*token*`, `*secret*`) in config files | follow-up |
| `rebalance_selection`: re-evaluate a backtest's selection at an interval | phase 2b |
| L4 `watchlists/` and `preferences.toml` | phase 4–5 |
| Database-backed `ConfigStore` written by the UI | phase 4 |
