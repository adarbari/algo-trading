# algo-trading

A research → backtest → (eventually) live trading harness, built so that strategies can be
added quickly **without** the codebase or the results quietly rotting.

## Quickstart

```bash
brew install uv       # once: the package/workspace manager (https://docs.astral.sh/uv/)
make install          # library + apps + dev tools into .venv from uv.lock, + pre-commit hooks
make check            # everything CI runs: lint, types, boundaries, file length, tests, evaluation
.venv/bin/algotrade-backtest --data-url file://datasets/golden/store datasets list   # after `make golden-store`
.venv/bin/algotrade-backtest --data-url file://datasets/golden/store backtest --strategy sma_crossover --dataset bull_trend --param fast=10
make evaluate                                   # every strategy x golden dataset vs baseline
```

## Nightly options pipeline

```bash
# Storage location: set ALGOTRADE_DATA_URL in .env (default file://./var/data, git-ignored).
# What each night adds: docs/data/nightly-footprint.md
algotrade-ingest universe --stocks optionable_us_stock_universe.csv \
                          --etfs optionable_us_etf_universe.csv --version 2026-10
algotrade-ingest universe-build --review-out leveraged_candidates.csv   # universe + reference; CSV = ETFs whose leverage is still UNKNOWN
                                            # also writes var/figi_review.csv (FIGI disagreements; --figi-review-out)
algotrade-ingest bars --from 2024-10-01 --to 2026-10-01   # 2-year backfill (needs ALGOTRADE_MASSIVE_API_KEY in .env)
algotrade-ingest rates --from 2024-01-01 --to 2026-10-02   # Treasury par yield curve (one request per year; no key)
algotrade-ingest company-details [--force] [--limit N]   # SEC EDGAR company details (needs ALGOTRADE_SEC_CONTACT in .env)
algotrade-ingest shares [--force] [--limit N]   # shares outstanding from SEC company facts (first run ~6k CIKs, ~30-40 min)
algotrade-ingest rollups --from 2024-10-03 --to 2026-10-02   # backfill rollups (price_stats, earnings, option_liquidity) per session
algotrade-ingest rollups [--date D] [--only price_stats@v1]    # one session (alias: features); config/site/rollups.toml
algotrade-ingest nightly --export-dir out/      # catch up missed sessions; universe -> company details -> shares -> earnings -> bars -> rates -> corporate actions -> chains -> rollups -> screen jobs -> quality -> purge
algotrade-ingest report --date D [--out r.html] [--send]   # the nightly summary email for a past session (read-only)
algotrade-ingest quality                        # data-quality checks for a session
algotrade-ingest schedule --time 23:30          # writes a launchd agent; prints install commands
algotrade-ingest purge-raw [--keep-days 90]     # raw per source (SEC 7 days) + unfinished-run scratch older than 14 days (defaults: sources.toml)
algotrade-ingest migrate-ids [--dry-run]        # symbol ids -> FIGI ids per instruments/id_map (new runs, ADR 0018)
algotrade-ingest run <task> [--date D | --from D --to D]   # any registry task (tasks/framework/registry.py), same flags
```

Source switches, pacing, retention and quality thresholds live in
[`config/site/sources.toml`](config/site/sources.toml). Pacing per vendor is shared by every
process on the machine (`var/run/limits/`), and every command that writes to the store takes
its ingest lock: a second run started while one is going exits with code 3 (pass `--wait` to
queue behind it instead). A disabled vendor or a missing key skips the tasks that need it,
with the reason.

How the nightly behaves ([architecture §6](docs/architecture.md#the-nightly-workflow-r5);
settings in [`config/site/nightly.toml`](config/site/nightly.toml)):

- **Sessions come from the NYSE calendar** (holidays, 13:00 early closes). Without `--date`
  every command uses the last *closed* session (close + 30 min), so a run started during
  market hours never stores intraday chains as end of day.
- **Catch-up:** the nightly runs every session missed since the last COMPLETE / PARTIAL
  nightly (at most 5). Bars, corporate actions and earnings catch up; rollups catch up too (a
  rollup whose input a session lacks reports `no_input`); chains (Cboe serves only the current
  snapshot), the universe build, company details and screens run for the latest session only. `--date D` runs exactly D.
- **Isolated steps:** a failing step is recorded as FAILED and the next steps still run (a
  step that needs it is BLOCKED); data-quality checks (universe size, bar freshness and count,
  chain coverage, earnings present) end each session and the raw purge ends the run. The run
  is COMPLETE, PARTIAL (anything failed, blocked or partial, including a quality FAIL) or
  FAILED (nothing succeeded); each step reports its status and duration.
- **Screens run as `screen` jobs**, one per scheduled config, exports included.
- **When it is not COMPLETE** you get a macOS notification; every run's summary is written to
  `var/logs/nightly-latest.json`. A long run (`[alerts] max_duration_minutes`) is recorded as a
  warning.
- **Every night you get a summary email** (once set up, below): high-level statistics per step
  (status, duration, items OK / failed, rows written, rollups, screen decisions and coverage,
  quality checks), run timing (start / end in Pacific and UTC, per-step duration, share,
  throughput, sub-steps, trend vs the previous run and the 7-run median, slow steps flagged,
  the duration alert) and a failure deep dive (failed items grouped by reason, a few examples each,
  failed checks, screen coverage gaps, short "what to do" hints).
- **Scheduling:** `algotrade-ingest schedule` writes a launchd agent (weekdays, `RunAtLoad`
  false). A run missed while the Mac sleeps starts on wake, which is safe because of the
  calendar and catch-up.

### Setting up the nightly summary email

1. In your Google Account: **Security → 2-Step Verification → App passwords**, create an app
   password (2-Step Verification must be on). Other providers: their SMTP host and login.
2. In `.env` (never committed; see [`.env.example`](.env.example)):
   ```
   ALGOTRADE_NOTIFY_EMAIL_TO=you@gmail.com          # comma-separated for several
   ALGOTRADE_NOTIFY_EMAIL_FROM=                     # optional; default: the first recipient
   ALGOTRADE_SMTP_USER=you@gmail.com
   ALGOTRADE_SMTP_PASSWORD=<the 16-character app password>
   ```
3. In [`config/site/nightly.toml`](config/site/nightly.toml) set `[notify.email] enabled = true`
   (`smtp_host` / `smtp_port` default to Gmail, `smtp.gmail.com:587` with STARTTLS;
   `max_examples` is the number of examples per failure group).
4. Test it on a past night: `algotrade-ingest report --date 2026-10-02 --send` (add
   `--out r.html` to look at the HTML first).

A missing variable or an SMTP error never fails the nightly: it is recorded as a `notify` WARN
in the run summary (`var/logs/nightly-latest.json`).

Each step can also run on its own (`chains`, `rollups`, `screen`), resumes after
interruption, and prints its audit. See [docs/screeners/](docs/screeners/README.md).

## What's in the box

| Guardrail | Enforced by |
|---|---|
| Strict layered architecture (`core` → domain layers → `backtest` → `evaluation` → `cli`) | `import-linter` contracts in `pyproject.toml`, CI + pre-commit |
| No file over 1000 lines | `scripts/check_file_length.py`, CI + pre-commit + architecture test |
| Strategies cannot see the future | `MarketView` API + property test that rewrites future bars |
| Orders fill at the *next* open with slippage, commission and buying-power limits | `execution/simulated.py` |
| Every strategy × every golden dataset, every PR | `algotrade-backtest evaluate` vs `benchmarks/baseline.json` |
| Coverage ≥ 90 %, strict mypy, ruff | CI |
| Nightly heavy property tests + scorecard | `.github/workflows/nightly.yml` |
| PRs merge themselves once every CI check passes (`no-automerge` label or draft to opt out) | `.github/workflows/auto-merge.yml` |

## Packages (uv workspace)

| Package | Path | Provides |
|---|---|---|
| `algotrade` | `src/algotrade` | the shared library |
| `algotrade-ingestion` | `apps/ingestion` | `algotrade-ingest` (the only writer of data) |
| `algotrade-backtest` | `apps/backtest` | `algotrade-backtest` (`algotrade` alias) |

Each app declares only its own dependencies; `uv.lock` pins everything (`make lock-check`).

## Layout

Every directory under `src/` and `apps/` is declared, with its purpose, in
[`architecture/layout.toml`](architecture/layout.toml) (one kind of thing per folder, at most
10 modules; checked by `tests/architecture/test_layout.py`, ADR 0020).

```
apps/
  ingestion/    algotrade-ingest. Only writer of data. In algotrade_ingestion/:
    cli/          argument parsing (main.py) and command bodies
    ops/          scheduling (launchd)
    sources/      framework/ (protocols, HTTP, pacing, registry), vendors/<vendor>/, fixtures/
    tasks/        framework/ (IngestRun, registry), reference/, market/, derived/, maintenance/
    workflows/    nightly/
  backtest/     algotrade-backtest: datasets, backtest, evaluate
src/algotrade/  shared library
  core/         pure domain code (no pandas, no I/O): model/ (types, instruments, ids, errors),
                time/ (calendar, clock), views/ (MarketView, FeatureView, series), validation/
  config/       site/ (L3 settings loader), strategy/ (configs, selections, resolution), env, user
  storage/      data contract: tables/ (schemas, readers/writers), backends/ (local + memory,
                the only Parquet code), configs/ (config store), runs, locks
  quant/        pure numerics (numpy): Black-Scholes price + Greeks, implied vol, realised vol,
                Treasury rate conventions (ADR 0021)
  data/         the domain read API (reference, prices, events, chains, rates)
  strategies/   trading/ (backtest strategies) and screeners/: pure, see only core and quant
  features/     rollups: framework/ (declaration, typed columns, inputs via data, runner),
                rollups/ (option_liquidity, price_stats, earnings @v1), registry
  analytics/    performance metrics, report formatting
  engines/      backtest/ (loop, risk limits, sizing, simulated broker, portfolio), screening/
  services/     use cases: backtests/, screening/ (+ exports), jobs/, evaluation/; shared helpers
tests/
  unit/<layer>/ mirrors src; fast, isolated
  contract/     one suite every storage backend must pass
  apps/         ingestion app tests (fake vendor feeds, no network)
  property/     hypothesis invariants (no look-ahead, accounting identity, no shorts)
  integration/  real data + engine stack across the golden set
  e2e/          the CLIs, end to end, against committed data + baseline
  architecture/ structural rules (layout, ownership, file length, docs, test mirroring)
datasets/golden/   committed, checksummed synthetic CSVs; `make golden-store` loads them into
                   datasets/golden/store (git-ignored), the store backtests and CI read
benchmarks/        baseline.json: golden-master results
docs/              architecture, testing, trading pitfalls, ADRs
```

Read [docs/architecture.md](docs/architecture.md) before adding code, and
[docs/trading-pitfalls.md](docs/trading-pitfalls.md) before trusting a backtest.
