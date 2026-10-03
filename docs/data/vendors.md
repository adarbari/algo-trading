# Data vendors

Decision record: [ADR 0012](../adr/0012-data-vendors.md). Researched 2026-10-02; re-check
limits and prices before relying on them.

Every vendor sits behind the same source interface in `apps/ingestion/sources/`. Adding or
swapping a vendor never touches storage, features, strategies or the UI.

## By use case

| Data | Primary (free) | Alternatives | Notes |
|---|---|---|---|
| Ticker universe | Nasdaq Trader symbol directory (`nasdaqlisted.txt`, `otherlisted.txt`, `options.txt`) | — | Official, free, updated daily |
| S&P 500 membership | SPY daily holdings file (State Street) | — | Membership changes become events |
| Daily stock and ETF bars (swing / momentum) | Massive (formerly Polygon) free tier: all US tickers, 2 years history, 5 calls/min; "grouped daily" = whole market in 1 call | Alpaca (free account), IBKR, Yahoo (unofficial, history backfill only) | |
| End-of-day option chains | **Cboe delayed-quotes feed** (ADR 0014): whole chain + Greeks + IV + OI and the underlying's `iv30` in one request per underlying; about 4.2k requests a night | IBKR for a focused list / cross-check; Schwab Trader API (free with account; Greeks; all expiries in one call; 120 req/min); Tradier (needs a brokerage account for Greeks); Alpaca (free indicative feed, history from 2024-02); Massive options (paid, from ~$29/mo; licensed fallback) | No free source covers end-of-day chains for the whole universe with history. **We build our own IV history from day one.** |
| Futures (later) | **IBKR** (contracts, history, including recently expired) | Databento (pay-as-you-go history), Massive futures (paid), Yahoo/Stooq continuous (unofficial, unclear rolls) | |
| Synthetic | `sources/synthetic.py` (golden datasets) | — | Lets the whole pipeline run in CI with no account |

## Cboe delayed-quotes feed (primary for options)

`https://cdn-api.cboe.com/api/global/delayed_quotes/options/<SYMBOL>.json` (index options
use a leading underscore, e.g. `_SPX`). Checked 2026-10-02: SPY returned 13,280 contracts
in about 0.3 s.

| Per contract | bid/ask (+ sizes), last, volume, open interest, IV, delta, gamma, vega, theta, rho, theo |
|---|---|
| Per underlying | price, OHLC, previous close, volume, `iv30` |

Caveats, handled in `apps/ingestion/algotrade_ingestion/sources/cboe.py`:

- **Not a licensed product.** It is the undocumented feed behind cboe.com and can change or
  disappear. Check Cboe's site terms; keep Massive or Schwab as the fallback.
- Delayed quotes. The snapshot is taken after the close, so it is valid for end-of-day use.
- `open_interest` is OCC's figure as of the previous session.
- Greeks and IV are Cboe's model values; ours (`quant/`) will cross-check them.
- Be polite: 4 workers by default, Retry-After honoured on 429. **403 is an error, never
  "no chain"**, and a run where more than 25% of optionable names return no chain is PARTIAL.
- Raw responses are about 1–3 GB/day across the universe, so raw retention is limited
  (ADR 0014, `algotrade-ingest purge-raw --keep-days 90`).

## What IBKR gives us

**Good for:**

- **Futures**: contract definitions, roll and expiry information, and historical bars. This
  is the main reason futures can be added later without a new vendor.
- **Option chains on a focused list**: chain structure (expiries and strikes) comes back
  in one call; quotes come with IB-computed IV and Greeks.
- **Stocks and ETF bars**: a second source to cross-check the free vendor.
- **Execution later**: the `Broker` protocol in `execution/` gets an IBKR adapter, so
  paper and live trading reuse strategy and risk code unchanged.

**Limits that shape the design:**

- Historical data pacing: **no more than 60 requests per 10 minutes**, no identical
  requests within 15 s ([IB docs](https://www.interactivebrokers.com/docs/tws-api/doc/market-data-historical/historical-data-limitations/pacing-violations-for-small-bars-30-secs-or-less)).
  The IBKR adapter must have a built-in rate limiter and resumable jobs.
- Quotes are per contract, and there is a cap on simultaneous market data lines. Pulling
  ~1M option contracts every night is **not practical**; IBKR suits a curated options
  universe (for example S&P 500 + the most liquid ETFs) rather than every optionable name.
- Needs TWS or IB Gateway running locally (with periodic re-login). The adapter treats
  "gateway down" as a normal, alertable failure.
- Live data needs market data subscriptions (for example the US Securities Snapshot and
  Futures Value Bundle, about $10/mo, waived above a monthly commission threshold); OPRA
  options data is a separate, small add-on. Delayed data is free for many products.
- IB's Greeks come from IB's own model. We still compute Greeks ourselves in `quant/`, so
  the numbers stay consistent if we switch vendors; IB values are kept as a cross-check.

## Options universe coverage

With the Cboe feed the **full** optionable universe (about 4.2k underlyings) is covered
nightly. IBKR is no longer needed for option chains; it remains the plan for futures, for
cross-checks and for execution.
