# algo-trading

A research → backtest → (eventually) live trading harness, built so that strategies can be
added quickly **without** the codebase or the results quietly rotting.

## Quickstart

```bash
make install          # venv + dev deps + pre-commit hooks (Python 3.12+)
make check            # everything CI runs: lint, types, boundaries, file length, tests, evaluation
.venv/bin/algotrade datasets list
.venv/bin/algotrade backtest --strategy sma_crossover --dataset bull_trend --param fast=10
.venv/bin/algotrade evaluate --report scorecard.md
```

## Nightly options pipeline

```bash
export ALGOTRADE_DATA_URL=file://./var/data     # default; git-ignored
algotrade-ingest universe --stocks optionable_us_stock_universe.csv \
                          --etfs optionable_us_etf_universe.csv --version 2026-10
algotrade-ingest nightly --export-dir out/      # chains -> option_liquidity@v1 -> screen -> CSVs
algotrade-ingest purge-raw --keep-days 90
```

Each step can also run on its own (`chains`, `features`, `screen`), resumes after
interruption, and prints its audit. See [docs/screeners/](docs/screeners/README.md).

## What's in the box

| Guardrail | Enforced by |
|---|---|
| Strict layered architecture (`core` → domain layers → `backtest` → `evaluation` → `cli`) | `import-linter` contracts in `pyproject.toml`, CI + pre-commit |
| No file over 1000 lines | `scripts/check_file_length.py`, CI + pre-commit + architecture test |
| Strategies cannot see the future | `MarketView` API + property test that rewrites future bars |
| Orders fill at the *next* open with slippage, commission and buying-power limits | `execution/simulated.py` |
| Every strategy × every golden dataset, every PR | `algotrade evaluate` vs `benchmarks/baseline.json` |
| Coverage ≥ 90 %, strict mypy, ruff | CI |
| Nightly heavy property tests + scorecard | `.github/workflows/nightly.yml` |
| PRs merge themselves once every CI check passes (`no-automerge` label or draft to opt out) | `.github/workflows/auto-merge.yml` |

## Layout

```
src/algotrade/
  core/         domain types, MarketView (no pandas, no I/O, imports nothing internal)
  data/         loading, validation, alignment, synthetic + golden datasets
  strategies/   pure decision logic -> target weights (imports only core)
  risk/         limits + weights -> orders
  execution/    broker protocol, cost model, simulated broker
  portfolio/    cash/positions accounting
  analytics/    performance metrics, report formatting
  backtest/     the engine wiring the above together
  evaluation/   strategy x dataset suite, regression baseline
  cli/          `algotrade` command
tests/
  unit/<layer>/ mirrors src; fast, isolated
  property/     hypothesis invariants (no look-ahead, accounting identity, no shorts)
  integration/  real data + engine stack across the golden set
  e2e/          the CLI, end to end, against committed data + baseline
  architecture/ structural rules (file length, docs, test mirroring)
datasets/golden/   committed, checksummed synthetic market regimes
benchmarks/        baseline.json: golden-master results
docs/              architecture, testing, trading pitfalls, ADRs
```

Read [docs/architecture.md](docs/architecture.md) before adding code, and
[docs/trading-pitfalls.md](docs/trading-pitfalls.md) before trusting a backtest.
