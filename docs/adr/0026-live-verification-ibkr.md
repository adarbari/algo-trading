# ADR 0026: Live verification against IBKR (read-only)

**Status:** accepted (2026-10-03, owner-approved option A: IB Gateway + the IBKR API, strictly
read-only). Extends [0012](0012-data-vendors.md) (IBKR as a cross-check),
[0019](0019-ownership-and-boundaries.md) (owners, R3) and [0020](0020-directory-layout.md)
(a new vendor folder and task domain). Code: `apps/ingestion/algotrade_ingestion/sources/vendors/ibkr/`,
`sources/framework/{base,registry}.py`, `tasks/verification/`. Setup: README "Live
verification (IB Gateway)"; vendor notes: [docs/data/vendors.md](../data/vendors.md#ibkr).

## Context
Our numbers (split-adjusted bars, `price_stats`, `dividends`, `iv30`, option chains) come from
free sources (Massive, Cboe) and our own maths. The reconciliation suite (`docs/testing.md`)
proves them against one recorded IBKR snapshot, offline; nothing checks each night's data
against an independent source. The owner has an IBKR account and runs IB Gateway locally, so
IBKR can be that source, but an account that can trade must never be put at risk by a data job.

## Decision

### Read-only by construction
Nothing in this repository may place, modify or cancel an order or touch account functions.
Three independent layers enforce it:

1. **A narrow facade.** `sources/vendors/ibkr/gateway.py` (`IbkrMarketData`) is the only module
   that imports `ib_async` (the maintained fork of `ib_insync`). It exposes market data only:
   daily bars, the underlying's implied-volatility history, IB dividends (tick 456), option
   chain parameters and option snapshots, each returned as plain JSON-able values. The
   `ib_async.IB` object is wrapped at once in a guard that lets through only the market-data
   calls it names (`MARKET_DATA_CALLS`, `CLIENT_CALLS`) and raises `ReadOnlyViolationError` for any
   other attribute, before a message is sent. It never calls `IB.connect`: even with
   `readonly=True` that requests positions (and by default account updates, open orders and
   executions) to synchronise state; the facade performs only the API handshake
   (`IB.client.connect`). It refuses to connect unless its config is `readonly` (always).
2. **A fitness test and an import contract.** `tests/apps/ingestion/sources/vendors/ibkr/test_read_only_guard.py`
   fails on any reference (name, attribute, import or string) to an order or account API of
   `ib_async` (`placeOrder`, `cancelOrder`, `reqGlobalCancel`, `MarketOrder`, `LimitOrder`,
   `bracketOrder`, `whatIfOrder`, `reqAccountUpdates`, `reqPositions`, `accountValues`,
   `reqExecutions`, ...) anywhere in `src/` and `apps/`, and on generic ones (`Order`, `Trade`,
   `portfolio`, `positions`, ...) in any module that imports `ib_async`. The import-linter
   contract "Broker API: only the read-only IBKR facade imports ib_async" fails any other
   import. Tests prove the guard catches a planted `placeOrder`.
3. **The gateway setting.** The owner ticks IB Gateway's "Read-Only API" (Configure → Settings
   → API → Settings), so the gateway itself rejects order messages. The README setup and the
   `[ibkr]` comments in `sources.toml` say so; the source stays disabled until the owner
   enables it.

### Session sources
IBKR is a stateful socket session, unlike the HTTP sources. The source framework gains one
generic kind (`sources/framework/base.py`): a `SessionSource` has `probe()` (why it cannot
open now, from a TCP check of the port, without connecting), `open()` (raises
`SessionUnavailableError`) and `close()` (never raises), and `opened(source)` is the one
lifecycle: open for a block, always close. The registry (`sources/framework/registry.py`)
declares session sources once (`SessionSpec`): section, limiter keys, required environment
variables, and a builder that gets settings, the environment and the shared limiters
(`SessionInputs`) and returns the source unconnected. Responses are serialised to JSON and saved
raw by `IngestRun.fetch` like every other source's (`[ibkr] raw_retention_days = 30`).

Pacing uses the shared cross-process limiter (`sources/framework/limiter.py`) with IBKR's
rules: every message waits on key `ibkr` (`min_interval_s = 0.02`: 50 messages/s); every
historical-data request also waits on `ibkr_historical` (`historical_min_interval_s = 10`:
60 per 10 minutes and never two identical requests within 10 s).

Configuration: `config/site/sources.toml [ibkr]` (`enabled = false` until the owner turns it
on, `min_interval_s`, `historical_min_interval_s`, `market_data_type` 1 live / 3 delayed,
`connect_timeout_s`, `request_timeout_s`, `stream_wait_s`, `raw_retention_days`); host, port
and client id only from `ALGOTRADE_IBKR_HOST` / `_PORT` / `_CLIENT_ID` (`config/env.py`).

### The verify task
`tasks/verification/verify.py` (registry task `verify`; `algotrade-ingest verify --date D
[--symbols A,B]`) samples, per session: the `core_symbols` of `config/site/verification.toml`
(AAPL, SPY, QQQ, IWM, KO, TQQQ, TSM, NVO, JNJ, RPGL: ETFs, a leveraged ETF, ADRs, dividend
payers, a thin reverse-split name), every instrument with a split, dividend, symbol or name
change dated that session, and `rotating` (10) more chosen by a hash of (session, instrument).
For each it pulls about 260 IBKR daily TRADES bars, the implied-volatility history and IB
dividends, and for `option_symbols` (AAPL, SPY) the chain parameters and the ATM call and put
of the expiry nearest 30 days. Checks (`checks.py`), with the reconciliation suite's
tolerances: split-adjusted close / high / low (worst session), missing sessions, `hv20`
recomputed from IBKR closes, `high_52w` (split-only basis), `low_52w` by the dividend-gap rule
(ours at or above IBKR's, by at most `div_ttm`), `div_yield`, `iv30` and `iv30_cboe` vs IB's
implied vol, option listed and option mid within the spread band. Each is PASS, WARN (over
tolerance by at most `warn_multiple`), FAIL or NA. Rows go to `verification/ibkr` (one
producer; key instrument + check); the run record holds counts by status and failing examples.

### Nightly, quality, email
`verify` runs after the screens, for the latest session only. When `[ibkr]` is disabled or
nothing listens on the gateway port, the step is SKIPPED with the reason ("IB Gateway not
reachable on host:port"); a gateway that refuses the handshake also SKIPS (the task records
`skipped`), so verification never fails ingestion. The quality check `verification` FAILs
when more than `[quality] max_verify_failures` (10%) of the graded checks FAIL, WARNs on any
FAIL or on no rows while `[ibkr]` is enabled. The nightly email has a "Verification vs IBKR"
section (counts and failing examples) built by the deterministic report builder.

| Alternative | Rejected because |
|---|---|
| IBKR Client Portal Web API | needs a browser login every day and exposes order endpoints over the same session; no read-only switch |
| `ib_async.IB.connect(readonly=True)` | still requests positions and account updates at startup |
| Trust the gateway's Read-Only API setting alone | one setting the owner can untick; the code must be safe by itself |
| Re-use the reconciliation suite only | one recorded day; misses regressions in nightly data |

## Consequences
- A new dependency, `ib_async`, in the ingestion app only (it pins `tzdata < 2026`).
- CI never connects to IBKR: tests use a fake IB client that records calls.
- Until the owner enables `[ibkr]`, the nightly shows `verify` SKIPPED; enabling it adds about
  2 historical requests per name (10 s each): ~7 minutes for ~22 names.
- Any future broker code (orders, if ever) needs a new ADR that supersedes this one.
