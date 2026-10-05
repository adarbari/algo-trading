# algo-trading

A research → backtest → (eventually) live trading harness, built so that strategies can be
added quickly **without** the codebase or the results quietly rotting.

## Quickstart

```bash
brew install uv       # once: the package/workspace manager (https://docs.astral.sh/uv/)
make install          # library + apps + dev tools into .venv from uv.lock, + pre-commit hooks
make check            # everything CI runs: lint, types, boundaries, file length, tests, evaluation
make changed          # narrow first check: tests mirroring the files you changed, then the fast gates
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
algotrade-ingest descriptions [--only funds|massive] [--limit N] [--symbols A,B] [--force]   # company / ETF descriptions: ETFs from SEC prospectuses (one run, ~2 min), stocks from Massive (5/min: --limit 600 is ~2 h; nightly adds 100)
algotrade-ingest rollups --from 2024-10-03 --to 2026-10-02   # backfill rollups (price_stats, earnings, option_liquidity) per session
algotrade-ingest rollups [--date D] [--only price_stats@v2]    # one session (alias: features); config/site/rollups.toml
algotrade-ingest retire-features --group price_stats@v1 [--dry-run]   # delete a superseded group's tables once v2 covers them
algotrade-ingest nightly --export-dir out/      # catch up missed sessions (a quiet no-op when up to date; --force re-runs); universe -> company details -> shares -> earnings -> bars -> rates -> corporate actions -> chains -> rollups -> screen jobs -> descriptions -> quality -> purge
algotrade-ingest report --date D [--out r.html] [--send]   # the nightly summary email for a past session (read-only)
algotrade-ingest quality                        # data-quality checks for a session
algotrade-ingest schedule                       # writes a launchd agent (weekdays 15:00, at login, hourly); prints install commands
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
- **Scheduling:** see [Scheduling the nightly](#scheduling-the-nightly) below.

### Scheduling the nightly

`algotrade-ingest schedule [--time 15:00] [--watchdog-minutes 60] [--export-dir out]` writes
`var/com.algotrade.nightly.plist` (it never installs it). The agent runs
`algotrade-ingest nightly --export-dir out/` (no `--date`):

- **weekdays at 15:00 local time** (Pacific: the US close is 13:00 PT, a session counts as
  closed at close + `settle_minutes`, so 15:00 leaves margin);
- **at login / boot** (`RunAtLoad`): a Mac that was off at 15:00 catches up when it is on;
- **every hour** (`StartInterval`, `--watchdog-minutes`, 0 turns it off): heals anything else
  that was missed. A 15:00 missed while the Mac sleeps also fires on wake.

Repeated starts are cheap and quiet. When every session up to the last closed one already has
a COMPLETE / PARTIAL nightly, `nightly` prints `nothing to do: <session> already ingested` and
exits 0 without a run record, an email or a notification. While a nightly (or any ingest) is
still running it prints `busy: ...` and exits 3, again without notifying (launchd also never
starts a second copy of the agent). Otherwise it catches up every missed session (at most 5).
Until today's close + settle has passed, the last closed session is the previous one, so a
login at 10:00 PT runs yesterday's nightly if it is missing and is a no-op otherwise. A watchdog
or login start can begin the nightly as early as close + settle (13:30 PT), before 15:00.
`algotrade-ingest nightly --force` runs anyway (the last closed session again).

Catch-up has one limit: Cboe serves only the current option-chain snapshot, so a missed
session's chains can be fetched only until the next session opens (09:30 New York, 06:30 PT).
A nightly that runs later still catches up bars, rates, corporate actions, earnings and
rollups, but the missed session has no chains (and no chain-based screens).

Install, or replace an installed agent (the plist's paths are absolute, so run `schedule`
from the checkout the agent should use):

```bash
algotrade-ingest schedule                     # writes var/com.algotrade.nightly.plist
mkdir -p var/logs
launchctl unload ~/Library/LaunchAgents/com.algotrade.nightly.plist 2>/dev/null || true
cp var/com.algotrade.nightly.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.algotrade.nightly.plist
launchctl list | grep com.algotrade.nightly   # loaded; RunAtLoad starts a run (or a no-op) now
```

Logs go to `var/logs/nightly.log` and `var/logs/nightly.err.log`. Optional: to have the Mac
wake (or power on) before the run on weekdays, run `sudo pmset repeat wakeorpoweron MTWRF
14:55:00` yourself (`pmset -g sched` shows it, `sudo pmset repeat cancel` removes it). Without
it, a Mac asleep or off at 15:00 runs the nightly as soon as it wakes or you log in.

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

## Live verification (IB Gateway)

Each night `verify` compares the latest session's stored data with Interactive Brokers:
split-adjusted closes / highs / lows, HV20, the 52-week range, dividend yield, our `iv30` and
Cboe's vs IB's implied vol, and a few option quotes (ADR 0026). It is **read-only by
construction**: market data only, through a facade that cannot place, modify or cancel orders
or read accounts, a fitness test that fails on any order / account API in the code, and the
gateway's own Read-Only API setting. Results land in `verification/ibkr`, the quality check
`verification` and a "Verification vs IBKR" section of the summary email. While the gateway
is down (or `[ibkr]` is disabled, the default) the step is SKIPPED with a warning; ingestion
never fails because of it.

**Owner setup (once):**

1. Install **IB Gateway** (stable) and log in (paper or live account; the job only reads).
2. **Configure → Settings → API → Settings:** tick **Read-Only API**; tick "Enable ActiveX
   and Socket Clients"; note the **Socket port** (4001 live, 4002 paper); add `127.0.0.1` to
   Trusted IPs; untick "Allow connections from localhost only" only if the gateway runs on
   another host.
3. In `.env` (see [`.env.example`](.env.example)): `ALGOTRADE_IBKR_HOST=127.0.0.1`,
   `ALGOTRADE_IBKR_PORT=<socket port>`, `ALGOTRADE_IBKR_CLIENT_ID=<a number no other API
   client uses>`. The API's live option quotes connect as `ALGOTRADE_IBKR_API_CLIENT_ID`
   (default: the client id + 1), so `algotrade-api` and an ingestion run never collide.
4. In [`config/site/sources.toml`](config/site/sources.toml) set `[ibkr] enabled = true`
   (`market_data_type = 3` delayed is free; 1 live needs a market data subscription).
5. Try it: `algotrade-ingest verify --date <last session> --symbols AAPL,SPY` (about 20 s per
   name: IB's historical-data pacing), then look at the run summary.
6. Keep the gateway logged in at the nightly time (IB Gateway restarts daily; enable
   auto-restart in Configure → Settings → Lock and Exit).

What is verified and the tolerances: [`config/site/verification.toml`](config/site/verification.toml).

### IBKR enrichment: contract ids and IV history (ADR 0028)

With the gateway set up, the nightly also resolves IBKR contract ids for new optionable names
(`ibkr-contracts`; every name again once a month, spread over the month) and snapshots every
underlying's IBKR implied and historical vol after the chains (`ibkr-iv`), which feed the
`ibkr_iv@v1` features and `iv_rank` (IBKR's rank where it has one, else ours; `iv_rank_source`
says which). Everything derived from IBKR is tagged `licence = personal`. Owner commands:

```bash
# once: contract ids for the whole optionable universe (~4.2k names, a few minutes)
.venv/bin/algotrade-ingest run ibkr-contracts --date <last session>
# the IV history backfill: 1 request per underlying at the historical pace (10 s each),
# most liquid first, ~12 h for all ~4.2k. Resumable: re-run the same command to continue
# (names IB did not answer are retried); --limit N caps a run (e.g. --limit 1500 = ~4 h
# overnight), --symbols A,B for a few names
.venv/bin/algotrade-ingest run ibkr-iv --from <2 years ago> --to <last session> --limit 1500
# then the features for that session
.venv/bin/algotrade-ingest run rollups --date <last session> --only ibkr_iv@v1
```

### Long runs (ops note)

Anything longer than ~2 h (the IBKR IV backfill is ~4 h per 1500 names) runs detached from
the agent or terminal session, not as a tool background command (those are killed at their
limit). A resumable run only loses the batch in flight:

```bash
mkdir -p var/logs
nohup sh -c '.venv/bin/algotrade-ingest run ibkr-iv --from <2 years ago> --to <last session> --limit 1500 \
  > var/logs/ibkr-iv.log 2>&1; echo "exit=$? $(date -u +%FT%TZ)" > var/logs/ibkr-iv.status' >/dev/null 2>&1 &
cat var/logs/ibkr-iv.status   # appears when the run ends; tail var/logs/ibkr-iv.log meanwhile
```

The nightly step continues the backfill on its own, `[ibkr] iv_backfill_per_night = 100`
names a night (~17 min), so new names fill in without a command; the email's `ibkr-iv` line
shows coverage, names still pending and the estimated hours left.

## API

A read-only HTTP API over everything above, the web app's only backend
([ADR 0024](docs/adr/0024-api.md); endpoints in [architecture §12](docs/architecture.md#12-api)):

```bash
.venv/bin/algotrade-api            # http://127.0.0.1:8000 (docs at /docs, schema at /openapi.json)
.venv/bin/algotrade-api --reload   # development: restart on code changes
```

It reads the store at `ALGOTRADE_DATA_URL` and the configs at `ALGOTRADE_CONFIG_DIR` (both from
`.env`) as the user `ALGOTRADE_USER` (default `local`), and never writes. After changing a
route or schema run `.venv/bin/python scripts/export_openapi.py` and commit
`apps/api/openapi.json` (CI fails when it is stale); the web client is generated from it.

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
| `algotrade-sources` | `libs/sources` | vendor sources (`algotrade_sources`, ADR 0027): adapters, HTTP, pacing, registry, vendor SDKs |
| `algotrade-ingestion` | `apps/ingestion` | `algotrade-ingest` (the only writer of data) |
| `algotrade-backtest` | `apps/backtest` | `algotrade-backtest` (`algotrade` alias) |
| `algotrade-api` | `apps/api` | `algotrade-api` (read-only FastAPI, ADR 0024) |

Each app declares only its own dependencies; `uv.lock` pins everything (`make lock-check`).

## Layout

Every directory under `src/`, `libs/` and `apps/` is declared, with its purpose, in
[`architecture/layout.toml`](architecture/layout.toml) (one kind of thing per folder, at most
10 modules; checked by `tests/architecture/test_layout.py`, ADR 0020).

```
libs/
  sources/      algotrade-sources (ADR 0027). In algotrade_sources/: framework/ (protocols,
                HTTP, pacing, registry), vendors/<vendor>/, fixtures/. Never imported by backtests
apps/
  ingestion/    algotrade-ingest. Only writer of data. In algotrade_ingestion/:
    cli/          argument parsing (main.py) and command bodies
    ops/          scheduling (launchd)
    tasks/        framework/ (IngestRun, registry), reference/, market/, derived/, maintenance/
    workflows/    nightly/
  backtest/     algotrade-backtest: datasets, backtest, evaluate
  api/          algotrade-api: read-only FastAPI. main (app factory), routes/ (one router per
                area), schemas/ (response models = openapi.json), deps
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
  services/     use cases: backtests/, screening/ (+ exports), jobs/, evaluation/, explore/
                (read-only queries the API serves); shared helpers
tests/
  unit/<layer>/ mirrors src; fast, isolated
  contract/     one suite every storage backend must pass
  apps/         app tests: ingestion (fake vendor feeds, no network), api (TestClient)
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
