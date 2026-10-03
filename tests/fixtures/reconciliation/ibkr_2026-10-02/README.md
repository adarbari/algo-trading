# IBKR reconciliation fixtures, session 2026-10-02

Recorded inputs for `tests/reconciliation/test_ibkr_2026_10_02.py`: what Interactive Brokers
reported for six tickers (AAPL, SPY, KO, TQQQ, TSM, RPGL) next to the raw inputs our pipeline
stored for the same session. The test recomputes our features from our raw inputs with
production code and checks them against IBKR. No network is used.

## IBKR side: `ibkr.json`

Fetched 2026-10-03 through the IBKR MCP connector, **read-only** (market data and snapshot
calls only; no orders, no account changes).

- `dates`: the 32 sessions 2026-08-19 .. 2026-10-02 the bars cover.
- `bars.<ticker>`: daily `close`, `high`, `low`, `volume` per date (RPGL: `close` only).
  IBKR chart bars are **split-adjusted** (RPGL's 1-for-16 reverse split on 2026-09-25 is
  applied to earlier bars). The volume is IBKR's chart-bar trade set, narrower than the
  consolidated volume we store: recorded, not compared.
- `snapshot.<ticker>` (status FROZEN: the Friday 2026-10-02 close):
  - `high_52w`, `low_52w`: IBKR's 52-week range, **dividend-adjusted** by IBKR (we use a
    split-only basis; see `docs/testing.md`).
  - `hv30`: IBKR's own historical-volatility estimator (not close-to-close; not compared).
  - `iv`: IBKR's implied volatility of the underlying (decimal; `null` when none).
  - `div_yield`: trailing dividend yield (decimal).
  - `adv90`: 90-day average dollar volume, USD (not compared).
- `splits`: splits inside the bar window.

## Our side (read-only extract of the production store `var/data` through `algotrade.data`)

- `our_bars_1d_raw.csv`: stored `bars/1d`, **unadjusted** (as traded), 262 sessions ending
  2026-10-02 (RPGL: the 244 it has), columns `ticker, session_date, open, high, low, close, volume`.
- `our_split_events.csv`: `events/split` (`ticker, ts, ratio`; ratio = new shares per old).
- `our_dividend_events.csv`: `events/dividend` since 2025-01-01 (`ticker, ts, cash_amount,
  distribution_type`).
- `our_iv30_recorded.csv`: the stored `iv30@v1` row of 2026-10-02 (`iv30` ours, `iv30_cboe`
  the feed's, `iv30_status`), recorded as values (recomputing needs the full chains).

Refresh: see "Reconciliation suite" in `docs/testing.md`. Never hand-edit these files.
