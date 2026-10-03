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
| End-of-day option chains | **IBKR** (you have an account) for a focused list; see below | Schwab Trader API (free with account; Greeks; all expiries in one call; 120 req/min); Tradier (needs a brokerage account for Greeks); Alpaca (free indicative feed, history from 2024-02); Massive options (paid, from ~$29/mo, needed for the full universe in bulk) | No free source covers end-of-day chains for the whole universe with history. **We build our own IV history from day one.** |
| Futures (later) | **IBKR** (contracts, history, including recently expired) | Databento (pay-as-you-go history), Massive futures (paid), Yahoo/Stooq continuous (unofficial, unclear rolls) | |
| Synthetic | `sources/synthetic.py` (golden datasets) | — | Lets the whole pipeline run in CI with no account |

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

## Options universe tiers (open decision)

| Tier | Underlyings | Feasible source |
|---|---|---|
| Liquid | S&P 500 + liquid ETFs (including leveraged), about 600–800 | IBKR (paced, about 1–2 h nightly) or Schwab |
| Full | All optionable, about 4.2k | Massive options (paid) or Schwab |

Start with the **liquid** tier on IBKR. Moving to the full tier is a source and config
change, not an architecture change.
