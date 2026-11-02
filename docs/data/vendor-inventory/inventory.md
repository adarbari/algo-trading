# Source inventory: free, paid, trial

One page for the owner: every data source the system reads or plans to read, what it costs, what
it feeds, its licence, and what dropping it would lose. Detail per vendor: [vendors.md](../vendors.md).
Written 2026-11-02 from `config/site/sources.toml`, `config/site/llm.toml`, the vendor adapters in
`libs/sources/algotrade_sources/` and ADRs 0012, 0014, 0028, 0034, 0069, 0084, 0087. Prices are the
figures recorded in those docs (researched 2026-10-02 to 2026-10-25), not re-checked today; no outside
research was done for this page and nothing was bought or signed up for.

Data tenet (owner 2026-11-01): never compromise data quality, store everything for future use,
minimise paid sources. So "a free alternative" below always names what quality it would lose.

## At a glance

| Cost today | Sources |
|---|---|
| **Paid, recurring** | none, except Tiingo Power (trial month, ends 2026-11-09) |
| **Paid, one-time** | HistoricalOptionData Level 2, $1,495 (chosen, ADR 0084) |
| **Free, key or account needed** | Massive, Tiingo (free tier), FMP, Finnhub, FRED, IBKR (delayed data, needs the brokerage account and IB Gateway), SEC EDGAR (a contact email, no key) |
| **Free, no key, official** | Nasdaq Trader, SEC EDGAR, Treasury, FINRA, SSGA / iShares / ProShares holdings files, Fed EBP, OFR FSI, Shiller, Ken French |
| **Free, no key, unofficial** (terms are grey; can break) | Cboe delayed quotes and VIX / VX files, Nasdaq earnings calendar, Yahoo (owner-only), fja05680/sp500 on GitHub |
| **Looked at, not bought** | Cboe display licence (~$333 a month), ORATS ($599), Norgate Platinum ($630 a year), Massive paid tiers (from ~$29 a month), HistoricalOptionData L1 ($1,150) and L3 ($2,035) |
| **Text model** (off by default) | Ollama, Gemini and Groq free tiers; Claude API is paid per token (budget-capped); the owner's Claude Code login |

**Licence caution that "free" hides.** ADR 0083 makes the trader site a paid product. A free source is
not cleared for it: Tiingo, FMP, Finnhub, IBKR, HistoricalOptionData and the Cboe VIX / VX files are
`personal` licence; Yahoo is owner-only (`yahoo`); FINRA tables are `no_ml`. The licence gate
(ADR 0069) keeps their derived values from other viewers, so nothing is served wrongly today, but
a subscriber-facing launch would need each source's terms reviewed or a redistribution licence bought.
That, not the sticker price, is where paid money could still be needed.

## Per source

Tier: F = free, P = paid, T = trial. Licence: open unless stated (ADR 0028, 0069).

| Source (config section) | Feeds | Tier, cost, renewal | Licence | Limits | Free alternative, and what it loses |
|---|---|---|---|---|---|
| **Cboe delayed quotes** (`[cboe]`) | Option chains (`chains/*`): bid, ask, OI, IV, Greeks, the underlying `iv30`; the screens, `iv30` and IV history | F. No key. | open for the screens; the display licence (~$333 a month, not bought) is what a vendor quote shown to users would need, so trader screens show only our computed values (decision log 2026-11-02) | ~57 requests a minute (Cloudflare 429 above); ~75 min for 4.2k underlyings | None for the whole universe nightly. Schwab (free with account, 120 requests a minute) would cover a list, needs the account and a new adapter; IBKR is capped at ~100 market-data lines. Loses: whole-universe breadth or the nightly time budget |
| **Cboe VIX family and VX futures** (`[cboe_vx]`) | `volatility` indices (VIX9D, VIX6M, VVIX, SKEW, COR, DSPX), `futures` VX curve | F. No key. | personal, non-commercial (cboe.com/terms) | static CDN files, no published limit | FRED has VIXCLS only (no VX, no VVIX / SKEW). Loses: the curve and the vol-of-vol inputs |
| **Massive** (`[massive]`) | `bars/1d` (all US tickers), `events/split`, `events/dividend`, identifiers, delisted list (ADR 0087), stock descriptions (ADR 0034) | F (free key). Paid tiers from ~$29 a month, not bought | open (free tier) | 5 requests a minute (12.5 s); 2 years of history; descriptions capped at 100 a night | Alpaca (free), IBKR bars. Loses: Massive's one-request grouped daily and the delisted list; paid tier would add depth and rate, not needed now |
| **Tiingo** (`[tiingo]`) | `bars/1d` history from 2010 / 2018 for the event-study names (`bars-history`), splits and dividends back to 2002, CEF NAVs (`X<ticker>X`), ETF launch dates, supported tickers | **T**: Power plan ($10 a month) bought 2026-10-09 for one month; **ends 2026-11-09** (renewal is not planned, decision log 2026-11-02). Otherwise F | personal (`licence = "personal"`) | Power: 10,000 requests an hour, ~110,000 symbols a month. Free: 50 an hour, 1,000 a day, 500 symbols a month | Massive (2 years only), Yahoo (unofficial). Loses: history before 2024, delisted-name bars and CEF NAVs; free-tier 500 symbols a month cannot cover ~12k listings, so any backfill must finish inside the Power month |
| **SEC EDGAR** (`[sec_edgar]`) | `instruments/company`, share counts, financial statements (`financials@v3`), 8-K events, Form 4 insider, 10-K / 10-Q text, cover shares, fund descriptions (N-PORT, prospectus), ETF holdings fallback | F. No key, contact email in `.env` | open (public domain) | 10 requests a second; the config uses 5 to 8 | None needed; this is the best source for every one of these |
| **FRED / ALFRED** (`[fred]`) | `macro/*` series with every vintage, release calendar | F (free key) | open (some series carry their own terms, ADR 0048) | 120 requests a minute | None needed |
| **U.S. Treasury** (`[treasury]`) | `rates/treasury` par yield curve (risk-free rate for Greeks) | F. No key | open | polite, 1 s | FRED `DGS*` (needs a key, same data) |
| **FINRA Query API** (`[finra]`) | short interest (twice a month), daily short-sale volume | F. No key | rows are `no_ml` (finra.org terms bar ML use) | 1,200 requests a minute, paced 0.5 s; API serves a rolling year of daily volume | FMP short interest is paid. Loses: the series, or ML training on it |
| **FMP** (`[fmp]`) | `analyst/*`: estimates, price targets, grades; `analyst_*@v2` features | F (free key). Paid tiers not bought | personal | ~250 calls a day (budget 200); many symbols refused (402) on the free plan | Yahoo fills the refused names; paid tier would give quarterly estimates and all symbols. Loses: coverage of ~part of the universe |
| **Finnhub** (`[finnhub]`) | analyst recommendation trends (`analyst_ratings@v2`) | F (free key) | personal | 60 calls a minute; 300 names a night | Yahoo recommendation counts (owner-only). Price targets are paid-only (denied) |
| **Yahoo Finance via yfinance** (`[yahoo]`) | standby analyst estimates, targets, ratings where FMP / Finnhub have none; report dates | F. No key, unofficial | `yahoo`: owner-only, never served to others (terms forbid scraping) | no published limit; 360 names a night, 600 call ceiling, stops on 429 | None free that covers the same names. Loses: standby coverage, and it is the first candidate to drop if the product goes subscriber-facing |
| **IBKR** (`[ibkr]`) | `volatility/ibkr_iv30` and IV history (`iv_rank`), `instruments/ibkr_contracts`, futures curves, live option quotes, verification checks | F: the account is needed and IB Gateway must run; delayed data (type 3) is free. A live subscription (~$10 a month, waived above a commission threshold) is not required today | personal (features carry `licence = "personal"`) | 50 messages a second; historical 10 s apart (60 per 10 min); ~100 data lines | Our own IV30 from the Cboe chains accrues from 2026-10-02 (the fallback, labelled `iv_rank_source`). Loses: two years of IV history on day one, futures. Read-only boundary, ADR 0026 |
| **State Street, iShares, ProShares files** (`[ssga]`, `[ishares]`, `[proshares]`) | `holdings/*` ETF holdings, SPY membership, iShares daily shares outstanding (flows) | F. No key | open (robots.txt allows) | 1 s a request | SEC N-PORT (quarterly, months old) for the rest. Loses freshness |
| **Nasdaq Trader** (`[nasdaq_trader]`) | universe: symbol directory, listed options | F. No key | open | none | None needed |
| **Nasdaq earnings calendar** (`[nasdaq_earnings]`) | `events/earnings`: dates, timing, EPS forecast, reported EPS | F. No key, unofficial (browser user agent) | open as used; Nasdaq's site terms bar automation, so treat as grey | 0.5 s | SEC 8-K Item 2.02 gives actual report dates, not forward ones; FMP / Yahoo give report dates for part of the universe. Loses: the forward calendar |
| **fja05680/sp500** (`[sp500_history]`) | S&P 500 membership intervals since 1996 (`index-membership`) | F. GitHub file | MIT | one file | SPY daily holdings from now on only. Loses: pre-2026 membership |
| **Published series** (`[published]`) | Fed EBP, OFR FSI, Shiller CAPE, Ken French factors | F. No key | open (French: ask the author for site use, decision log; Shiller: credit the author) | static files | none; Stooq is dead (browser check), not used |
| **HistoricalOptionData** (`hod_files`, a folder source, no HTTP) | `option_history/*`: end-of-day chains 2002 to purchase date, ~4,300 underlyings incl. delisted; feeds option-setup verdicts (ADR 0088) | **P, one time**: Level 2 $1,495 (chosen; L1 $1,150 and L3 $2,035 are the other levels; L1's sample does not parse with our importer, L2's does). No renewal. Confirm the purchase and the download | personal (owner-only until the owner reads its terms on derived statistics, ADR 0084) | none (files you download) | ORATS ($599, from 2007: loses 2002-2006 and was rejected on format fit); the free Cboe pull has history from 2026-10-02 only: no verdict could rest on it for years |
| **Text models** (`config/site/llm.toml`) | Describe-it screener drafts, regime explanations (`TextModel` seam) | F: Ollama (local), Gemini and Groq free tiers. **P** (per token, budget-capped by `[budget]`): Claude / OpenAI keys. The owner's Claude Code login (`claude_cli`, `only_users`) | n/a | provider limits; calls logged in `usage/llm_calls` | Free chain first (Gemini, Groq); loses answer quality and the retry headroom, not data |

## Dropped or never used

- **Stooq**: now behind a browser check, replaced by FRED `SP500` (10 years of daily history).
- **Norgate Platinum** ($630 a year, delisted names to 1990): decided not now (ADR 0087 decision 5): Personal Use only.
- **Nasdaq IPO calendar**: terms bar automated capture; SEC full-text search is used instead.
- **Vanguard, Invesco, ARK holdings**: no usable public file.

## Recommended actions

1. **Tiingo, 2026-11-09:** set `[tiingo] min_interval_s = 72` and `monthly_symbol_budget = 450`; do not renew Power unless the delisted-id bars (ADR 0087 PR2 ids) and the 2010 backfill cannot finish before then (decision log 2026-11-02). Check the run status in the week before. This ends the only recurring spend.
2. **HistoricalOptionData:** confirm Level 2 is bought and downloaded (the roadmap expected 2026-10-26, nothing in the repo says it was); run the import per [option-history.md](../option-history.md). One-time spend only. Do not also buy L1 or L3.
3. **Do not buy the Cboe display licence** (~$333 a month): trader screens show our computed values only, so no vendor quote needs it. Buy only if that rule changes.
4. **Before a subscriber-facing launch**, review the terms of every `personal` / `yahoo` / `no_ml` source above (Tiingo, FMP, Finnhub, IBKR, HOD, Cboe VIX / VX, Yahoo, FINRA). This is the decision most likely to cost money; owner decision, not made here.
5. **Candidates to drop** if minimising sources: Yahoo (unofficial, owner-only, standby only), the Nasdaq earnings calendar (grey terms, forward dates only), and FMP / Finnhub if the analyst features prove unused by any verdict. Keep everything else: each is free and has no equal substitute.
6. **Refresh the prices** in this page before relying on them (ADR 0012 asks for it); the Fable pricing pass was not run because nothing here needs a purchase decision tonight.
