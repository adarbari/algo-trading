# Architecture

## Layers

Dependencies point **downwards only**. Siblings in the middle row may not import each other.
This is enforced by `import-linter` (`[tool.importlinter]` in `pyproject.toml`); a PR that
breaks a contract fails CI.

```
            cli/
              │
         evaluation/
              │
          backtest/
              │
 ┌─────────┬──┴──────┬───────────┬────────────┬───────────┐
data/  strategies/  risk/   execution/   portfolio/   analytics/
 └─────────┴─────────┴────┬──────┴────────────┴───────────┘
                        core/
```

| Package | Responsibility | May import |
|---|---|---|
| `core/` | Value objects (`Order`, `Fill`, `PriceSeries`), `MarketView`, errors, time helpers. | numpy only |
| `data/` | The **only** code that reads/writes data files. Validation, alignment, synthetic generators, golden catalogue. | core, pandas |
| `strategies/` | Pure decision logic: `MarketView` in, target weights out. No I/O, no sizing, no orders. | core |
| `risk/` | Clip target weights to limits; convert weights to orders. | core |
| `execution/` | `Broker` protocol, `CostModel`, `SimulatedBroker`. Live brokers go here later. | core |
| `portfolio/` | Cash, positions, equity. The single source of truth for holdings. | core |
| `analytics/` | Metrics and report formatting from equity curves + fills. | core |
| `backtest/` | The engine loop wiring the layers above. Owns the timing model. | everything below |
| `evaluation/` | Runs every strategy on every golden dataset; compares to baseline. | backtest and below |
| `cli/` | Argument parsing and printing. The only place `print` is allowed. | everything |

## Data flow for one bar

```
open of bar t   : SimulatedBroker fills orders queued at t-1 (slippage, commission, buying power)
                  -> Portfolio.apply_fill
close of bar t  : Portfolio marked to market -> equity[t]
                  Strategy.on_bar(MarketView(data, cursor=t)) -> target weights | None
                  risk.apply_limits -> risk.targets_to_orders -> Broker.submit
```

## Rules of thumb

- **One responsibility per module; 1000 lines is a hard ceiling**, ~300 is the target.
  When a file grows, split by responsibility, not alphabetically.
- **Strategies are pure.** If a strategy needs something new (fundamentals, a signal from
  another model), add it to `MarketView`/`core` and populate it from `data/`. Never let a
  strategy open a file or call an API.
- **Everything is UTC and timezone-aware.** ruff's `DTZ` rules reject naive datetimes.
- **Fail loudly.** Bad data raises `DataValidationError`; bad config raises
  `ConfigurationError`. Never silently fill, drop or default.
- **Changing a boundary needs an ADR** in `docs/adr/` plus the `pyproject.toml` contract.

## Adding things

| To add… | Do this |
|---|---|
| A strategy | New module in `strategies/`, one line in `registry.py`, unit tests in `tests/unit/strategies/`. Property tests pick it up automatically. Run `make baseline` and commit the new rows. |
| A dataset | New `GoldenSpec` in `data/golden.py`, `make datasets-build`, `make baseline`. Never edit an existing dataset: add `name_v2`. |
| A metric | `analytics/metrics.py` + test; `make baseline`. |
| A live/paper broker | New module in `execution/` implementing `Broker`. Keep credentials out of the repo (env vars). |
