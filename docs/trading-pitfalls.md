# Trading-system pitfalls and how this harness handles them

| Pitfall | What goes wrong | Mitigation here | Still to do |
|---|---|---|---|
| **Look-ahead bias** | Strategy uses data not yet known (e.g. today's close to trade today's close). | `MarketView` only exposes bars ≤ now; fills at next open; property test rewrites the future. | Point-in-time handling for fundamentals/corporate actions. |
| **Ignoring costs** | Turnover-heavy strategies look profitable. | `CostModel` defaults to 1bp commission + 5bp slippage; scorecard shows turnover. | Spread- and volume-aware slippage; borrow costs for shorts. |
| **Unrealistic fills** | Unlimited size at any price. | Buying power enforced at fill time; whole-lot sizing. | Volume participation caps, partial fills, limit/stop orders. |
| **Overfitting / data snooping** | Tuning parameters until the backtest looks good. | Fixed golden set incl. a null `random_walk`; every change visible in the baseline diff. | Walk-forward + out-of-sample split; Monte Carlo over many seeds; deflated Sharpe. |
| **Survivorship bias** | Only testing on symbols that still exist. | n/a for synthetic data. | Real-data loader must include delisted symbols. |
| **Bad data** | Gaps, NaNs, bad ticks silently produce fantasy P&L. | `validate_ohlcv` rejects NaN, non-monotonic or duplicate timestamps, broken OHLC, negative prices or volume; `align` drops rather than forward-fills. | Outlier/spike detection; split/dividend adjustment. |
| **Non-reproducibility** | "It worked on my machine." | Seeded generators, checksummed data, golden-master baseline, pinned CI. | Lock file for exact dependency versions. |
| **Timezones** | DST and exchange-time bugs. | UTC everywhere; ruff `DTZ` bans naive datetimes. | Exchange calendars per venue. |
| **Backtest ≠ live drift** | Live code path differs from backtest path. | `Broker` protocol: strategy and risk code are identical across sim/paper/live. | Paper-trading adapter; reconcile live fills vs simulated. |
| **Operational risk (live)** | Runaway orders, stale data, credential leaks. | Hard risk limits in a separate layer; `detect-private-key` hook. | Kill switch, max daily loss, order-rate limits, stale-data guard, audit log, secrets via env/secret manager, alerts. |

## Rules before anything goes live

1. Paper trade first, for long enough to cover different market regimes.
2. Every live order passes through the risk limits (`engines/backtest/limits.py` today). There is no bypass flag.
3. A kill switch that flattens and halts must exist and be tested.
4. Live P&L is reconciled daily against what the simulator would have done.
