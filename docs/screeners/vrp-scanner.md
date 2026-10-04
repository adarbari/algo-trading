# Daily Stock Identifier — IV / HV Volatility Premium Scanner

> **Status in this repo:** a site rule-screen preset (not scheduled; run it from the Builder
> preview or as a `screen` job), over the expression features in `config/site/features/vrp.toml`
> (`vrp_iv30`, `vrp_iv30_source`, `vrp_iv_hv_spread`, `vrp_iv_hv_ratio`) and `price.toml`
> (`dist_52w`, `pct_vs_sma_20/50/200`). The latest version is
> `config/site/presets/screeners/vrp_scanner/v2.toml`; `v1.toml` stays as it was (immutable;
> user copies pinned to `vrp_scanner@1` keep computing it).
>
> - **v1** measured option liquidity with `option_liquidity@v1` (the target expiry's
>   0.15-0.40 delta put OI, chain-wide option volume, the short put's spread).
> - **v2** (`name = "VRP"`) picks the trade the "Option-trade follow-up" below describes and
>   scores it, never gates on it (owner decisions 2026-10-04 below). The rollup `put_wing@v1`
>   takes the expiry closest to 45 days within 30-60 (standard monthlies first, where open
>   interest concentrates) and, among its puts with OUR |delta| (ADR 0021) in 0.05-0.35, the
>   **best put**: nearest the 8-15 delta band (`delta_band_distance`, 0 inside, else the
>   distance to the nearer edge), then the highest ROC = premium / (strike x 100). SCORE
>   criteria: delta closeness (full points at 0, none at 0.20), the best put's OI > 1,000,
>   volume > 1,000 and stored bid/ask < 15% of mid; a missing value only costs points. The
>   columns `put_strike`, `put_expiry`, `put_delta`, `put_premium`, `put_roc` (plus OI,
>   volume, stored spread, band distance, band totals) identify the contract, so the UI can
>   fetch its live IBKR quote (`GET /chains/{id}/live`) during market hours: the spread is
>   judged live, not on the stored after-close quote. Flag `large_move` when
>   `price_moves@v1.one_day_move` (the largest |1-day close-to-close return| over 20
>   sessions, split-adjusted) > 10%.
> - Not yet features: the closest option expiry's DTE column (Ideas computes it on read), the
>   `vrp_setup` label.
>
> **Backfill (owner, after merge):** chains are stored from 2026-10-02 only, so the new
> groups are cheap to fill: `algotrade-ingest rollups --from 2026-10-02 --to <last session>
> --only put_wing@v1,price_moves@v1` (`price_moves@v1` can go further back with the bars).
> Until then every v2 row loses the put criteria's points (they are scores, so nothing is
> skipped) and the put columns are empty.
>
> See [README](README.md) for how each section maps onto the architecture.

## Owner decisions (2026-10-04, v2)

| Topic | Decision |
|---|---|
| Option liquidity | OI / volume / spread **scored, not gated** (owner 2026-10-04): SCORE criteria on the best put; the spread is judged on a live quote during market hours, never on the stored after-close one as a gate |
| Strike choice | delta closeness **scored** (owner 2026-10-04): the best put is the 0.05-0.35 delta put nearest 8-15 delta, then by ROC; a 20 delta best put scores higher than a 25 delta one and both still score; nothing is filtered on delta |
| Display | `put_strike`, `put_expiry`, `put_delta`, `put_premium`, `put_roc` (the Ideas page's columns); preset name "VRP" |

## Owner decisions (2026-10-03)

These take precedence over the original spec below wherever they differ. The scanner will be
a rule-screen preset ([rules.md](rules.md), [ADR 0029](../adr/0029-rule-screener.md)); the
mapping follows.

| Topic | Decision |
|---|---|
| IV30 gate | HARD, default **50%**, editable in the UI (the owner may lower it to 40%) |
| Missing data | any gating criterion missing → SKIPPED (`no <field>`), never a pass; every run reports passed, skipped by reason and the narrow misses |
| Scoring | 100 when every threshold is met, minus each miss's normalised distance (no 0-30 / 0-20 weights); ties by the IV−HV spread |
| Preset | a site preset visible in the Builder; users change it, re-run and see results; their copies pin the preset version |
| IV30 source for the gate | the **lower** of IBKR's and Cboe's IV30 when both exist, else whichever exists, else UNKNOWN; our own IV30 is not used for the gate |
| IV rank | IBKR's only; a SCORE criterion (missing lowers the score, never blocks) |
| ROC | premium / (strike × 100), cash-secured |
| Portfolio correlation | no correlation penalty |
| Leveraged / inverse ETFs | included and flagged |
| Earnings | **not a criterion**; results show the next quarterly earnings date and the DTE of the closest option expiry |
| IV/HV ratio | plain IV30 / HV30: **no HV30 floor** (owner decision, later the same day) |
| Output | screener results + Ideas (no email) |
| Universe | our daily universe snapshot (not the monthly CSVs) |

### Mapping to the rule-screen preset

| Spec | Preset criterion / output |
|---|---|
| IV30 >= 50% | hard `feature.vrp_iv30 gte 0.50` (UI-editable); new site feature `vrp_iv30 = min(coalesce(ibkr_iv.iv30_ibkr, iv30.iv30_cboe), coalesce(iv30.iv30_cboe, ibkr_iv.iv30_ibkr))`: the lower of the two, whichever exists, else null (UNKNOWN) |
| IV-HV >= 10 pts, IV/HV >= 1.25 | hard `feature.vrp_iv_hv_spread gte 0.10`, hard `feature.vrp_iv_hv_ratio gte 1.25`; new site features over `vrp_iv30` and `price_stats.hv30` (ratio = `vrp_iv30 / hv30`, no floor; HV30 missing or 0 → missing → SKIPPED); `[rank] tie_break = "feature.vrp_iv_hv_spread"` |
| Stronger tier 15 pts / 1.30 | `tiers.STRONG` |
| Within 10% of the 52W high / low; NEAR_HIGH / NEAR_LOW / BOTH | hard `feature.near_52w in [HIGH, LOW, BOTH]`; `classify = "feature.near_52w"` |
| IV rank (0-10) | score `rollup.ibkr_iv@v1.iv_rank_252d_ibkr` with a tolerance; a miss or missing value lowers the score |
| Price > $5 | hard `rollup.price_stats@v2.close gt 5` |
| ADV > $50M, option volume / OI > 1,000, spread < 15% ("flag, don't reject") | soft with a tolerance band: a near miss is WATCH (options too thin: `on_miss = LIQUIDITY_RISK`), beyond the band REJECT |
| Earnings < 14 days, event risk (0-5) | **dropped** (owner decision); `columns`: `rollup.earnings@v1.next_earnings_date` and a new feature, the closest option expiry's DTE |
| Low HV, leveraged / inverse ETF, > 10% one-day gap | `flags` (`instrument.is_leveraged`) |
| Momentum context, setup class | `columns` + a site label feature `vrp_setup` |
| Universe audit, "no qualified" only when COMPLETE | selection over the daily universe snapshot; the existing runner audit |
| Option follow-up ROC | premium / (strike × 100), cash-secured; no correlation penalty |
| Gaps (later) | catalysts (FDA etc.); the 8-15 delta put, its liquidity (scored) and the gap-move flag are in v2 (`put_wing@v1`, `price_moves@v1`) |

**Version:** 1.3\
**Purpose:** Daily identification of liquid stocks with unusually rich implied volatility relative to realized volatility, while the underlying is positioned near a meaningful 52-week extreme.

## Core thesis

Find stocks where option IV appears materially richer than realized volatility **and** price is close to a 52-week high or low. The scanner is an identification layer, not an automatic trade signal. Candidates must pass liquidity, event, and option-market quality checks before a short-premium trade is considered.

## Universe coverage — STATIC MONTHLY MASTER UNIVERSE (STOCKS + ADRs + ETFs)

> Owner decision 2026-10-03: the preset screens our daily universe snapshot; the CSV
> procedure below is the original spec.

The daily scan must use the monthly master universe files **`optionable_us_stock_universe.csv`**, **`optionable_us_etf_universe.csv`**, and any current pending/review universe explicitly supplied for the run as authoritative inputs. The scanner now includes **U.S.-listed common stocks, ADRs/depositary receipts, and ETFs**, including leveraged/inverse ETFs when present in the supplied universe. Do **not** rebuild the optionable universe every day and do not substitute a hand-picked watchlist or a top-N screener.

### Authoritative universe input

Load:

```text
optionable_us_stock_universe.csv
```

The file is refreshed approximately once per month by the **Monthly Optionable U.S. Stock Universe Refresh** process. It should contain one row per active U.S.-listed common stock with currently listed standard equity options.

The daily scanner should treat the CSV as the answer to **“what securities should I evaluate?”** and use its own market-data logic to answer **“which of those securities are interesting today?”**

### Production universe definition

The master universe should include:
- Active U.S.-listed common stocks
- Active U.S.-listed ADRs/depositary receipts with listed standard options
- Active U.S.-listed ETFs with listed options
- Leveraged/inverse ETFs when present and explicitly tagged

The master universe should exclude:
- ETNs unless explicitly tagged for inclusion
- Closed-end funds unless explicitly tagged
- Preferreds
- Warrants
- Rights
- Units
- Indexes
- Futures/futures options
- Structured products
- Securities whose available options are only adjusted/non-standard contracts
- Delisted/inactive securities

### Daily universe-loading procedure

1. Load every supplied master-universe file: stocks, ETFs, and ADRs.
2. Require `status=ACTIVE` and `optionable=TRUE`. Accept `COMMON_STOCK`, `ADR`, and `ETF` security types.
3. Normalize and deduplicate tickers.
4. Record the universe version and `last_verified` date.
5. Record the exact number of rows loaded and the number of unique production tickers.
6. Process **every unique production ticker exactly once** through the daily screening pipeline.
7. Do not silently skip a ticker because it is absent from a screener result.
8. If a ticker cannot be processed because market data is unavailable, place it in the skipped/error audit rather than deleting it from the universe.

### Daily universe audit

Every run must report:
- Universe file name
- Universe version
- Last verified date
- Rows loaded
- Unique production tickers
- Tickers processed
- Tickers skipped/error
- Duplicate rows removed, if any
- Missing/invalid universe metadata
- Processing coverage percentage

### Coverage requirement

The CSV is the authoritative coverage test. The daily scanner does not need to rediscover optionability from OCC/exchange directories every day.

The monthly refresh process is responsible for maintaining the completeness and freshness of the CSV.

If the CSV is missing, malformed, materially stale, or contains an unexplained universe-size change, report **UNIVERSE INCOMPLETE** and do not claim an exhaustive daily scan.

#### Security-type handling

Apply the same stock-level IV/HV and 52-week screening framework to stocks, ADRs, and ETFs, but keep security type visible in every result. For leveraged/inverse ETFs, add a mandatory `LEVERAGED/INVERSE` risk flag and do not treat them as equivalent to unleveraged stocks. For ADRs, retain the ADR flag and note country/foreign issuer exposure when available.

## Daily discovery paths

Once the full static universe is loaded, run the independent discovery paths below against the **same universe** so that ranking/screener limitations do not hide candidates:
- Full-universe quantitative pass
- Near 52-week highs
- Near 52-week lows
- High IV30
- High IV percentile/rank
- High IV30/HV30
- High IV30-HV30 spread
- High option-volume / open-interest names
- Existing seed/validation list

Union and deduplicate all candidates before applying the detailed validation stages.

### Data-source failure rule

If a daily market-data connector cannot process the complete static universe, report the run as **PARTIAL**, including the number processed and skipped. Never substitute a smaller watchlist and call it exhaustive.

### Exhaustiveness rule

Do **not** claim “NO QUALIFIED CANDIDATES” unless the static universe loaded successfully and essentially the entire production universe was processed, subject only to explicitly reported data failures.

### Candidate seed / expanded validation list

The following names were found during the September 2026 broader validation pass and should remain part of the recurring candidate-validation universe so they can be rechecked automatically each day:

**QURE, NN, GFL, VLO, ABVX, ENPH, U, UNH, MPC, DINO, IREN, RKLB, CRWV, SMCI, MSTR, COIN, HOOD, AMD, PLTR, TSLA, FRVO, PCVX, FSLY, MRNA, TEM, DOCN, PBF, INTC, AMBA, BE, RARE, PHVS, SLS, VKTX, PL, ALMS, CLYM, CAVA, CVNA, APP, ARM, SNOW, AFRM, UPST, RIVN, HIMS, TOST, SOFI, MU, NVDA.**

This list is a **seed/validation list, not the universe**. New names discovered by the broad scan must be added to the day's candidate set even if they are not on this list.

## Primary screening criteria

### 1. Implied volatility
- **IV30 >= 50%**
- Prefer IV30 in the highest available percentile of its own history.

### 2. IV versus realized volatility
Calculate:
- **Volatility premium = IV30 - HV30**
- **IV/HV ratio = IV30 / HV30**

Primary gates:
- **IV30 - HV30 >= 10 volatility points**
- Prefer **IV30 - HV30 >= 15 points** as a stronger candidate tier
- **IV30 / HV30 >= 1.25**
- Prefer **IV30 / HV30 >= 1.30** as a stronger candidate tier

Require both spread and ratio.

## 3. 52-week price positioning

Identify stocks within 10% of either extreme:

**Near 52-week high:**
`(52W High - Price) / 52W High <= 10%`

**Near 52-week low:**
`(Price - 52W Low) / 52W Low <= 10%`

Classify every candidate as:
- `NEAR_HIGH`
- `NEAR_LOW`
- `BOTH / COMPRESSED_RANGE`

Do not assume that being near a high or low is bullish or bearish.

## Liquidity and tradeability filters

Preferred minimums:
- Stock price **> $5**
- Average daily stock dollar volume **> $50M**
- Option volume **> 1,000 contracts/day** when available
- Open interest **> 1,000 contracts** for the target strike/expiry
- Bid/ask spread preferably **< 15% of midpoint**

Flag rather than automatically reject exceptional candidates that fail one liquidity threshold if the option market is otherwise deep and institutional-quality.

## Event-risk filters

Flag or exclude:
- Earnings within **14 days** for the standard short-put screen (owner decision 2026-10-03: not a criterion; shown as a column)
- Major known binary events such as FDA decisions, major litigation decisions, merger votes, or other scheduled catalysts
- Recent extraordinary gap moves that make HV30 unstable

For every candidate, explicitly show the next earnings date and days to earnings when available.

## Momentum / regime context

For each surviving candidate calculate/display:
- Price vs 20DMA
- Price vs 50DMA
- Price vs 200DMA
- 20-day and 60-day return
- Distance from 52W high
- Distance from 52W low
- IV percentile / IV rank when available
- HV20 and HV30
- IV30/HV20 and IV30/HV30

Classify the setup as:
- High-IV trend continuation
- High-IV reversal candidate
- High-IV range/mean-reversion candidate
- High-IV event-driven candidate

## Candidate scoring

Use a transparent score rather than a black-box prediction. (Owner decision 2026-10-03: the preset scores by distance from each threshold, [rules.md](rules.md#score), not these bands.)

**Volatility premium (0–30)** — larger IV-HV spread scores higher.\
**IV/HV ratio (0–20)** — higher ratio scores higher subject to a reasonable HV floor (owner decision 2026-10-03: no HV floor; plain IV30 / HV30).\
**52W positioning (0–15)** — stronger proximity scores higher.\
**IV percentile/rank (0–10)** — higher percentile scores higher.\
**Liquidity (0–10)** — higher dollar volume, option volume and OI score higher.\
**Option execution quality (0–10)** — tighter spreads and stronger OI score higher.\
**Event risk (0–5)** — fewer near-term binary events score higher.

Use the score for sorting only; it is not a probability of profit.

## Required daily output

Return the **top 10–20 candidates**, separated into:

### A. Near 52-week highs
Columns:
- Ticker
- Price
- IV30
- HV30
- IV-HV spread
- IV/HV ratio
- IV percentile/rank
- 52W high
- % below 52W high
- 52W low
- % above 52W low
- 20D return
- 60D return
- Price vs 50DMA
- Earnings date / DTE
- Stock ADV
- Option volume
- Target-option OI
- Bid/ask spread
- Setup classification
- Scanner score

### B. Near 52-week lows
Use the same columns.

### C. Watchlist / exceptions
Show interesting names that narrowly miss one gate, with the failed criterion explicitly identified.

### D. Universe audit
Always report:
- Source universe
- Approximate starting universe size
- Securities processed
- Securities skipped
- Reasons skipped
- Number passing each core gate
- Number reaching historical-driver review
- Number reaching option-chain review
- Number ultimately qualified

## Historical Crash-Driver / Near-Term Catalyst Check

For **every candidate that passes the core scanner**, identify historical instances where the stock fell **more than 10% over a rolling 5-trading-day period** over the last 2–3 years where data is available. Identify documented drivers rather than simply calling the move a selloff.

Potential drivers include earnings/guidance, growth/margin deterioration, analyst estimate resets, product/customer issues, regulatory/FDA/legal developments, financing/dilution, accounting/control issues, management changes, competition, macro/sector shocks, commodity/input costs, cyber/operational outages, government/policy actions and M&A events.

### Candidate-specific catalyst mapping

For every historical driver ask whether a scheduled, announced, or credibly reported comparable catalyst exists between **today and the next earnings date**, with particular attention to the next 3, 5, 10 and 20 trading days.

Output:

| Historical >10% decline | Date | Documented driver | Comparable catalyst upcoming? | Date | Risk level | Evidence |
|---|---|---|---|---|---|---|

Classify:
- **MATCH — HIGH RISK**
- **PARTIAL MATCH**
- **NO MATCH IDENTIFIED**
- **UNKNOWN**

Do not infer a catalyst merely because the stock previously fell for a particular reason. Require a current scheduled, announced, or well-supported indication.

## Option-trade follow-up

For candidates surviving stock-level screening and catalyst review:
- **30–60 DTE**
- Target approximately **8–15 delta puts**
- Compare premium, delta, IV, OI, bid/ask, DTE and capital/margin requirement
- Calculate **premium / margin capital ROC** (owner decision 2026-10-03: premium / (strike × 100), cash-secured)
- Estimate assignment exposure and downside loss at multiple underlying drawdowns
- Apply correlation penalties against the existing portfolio (owner decision 2026-10-03: none)

## Risk flags

Automatically flag:
- Earnings <14D
- Extremely high IV caused by a single known event
- Very low HV creating a misleading IV/HV ratio
- Poor option liquidity
- Large bid/ask spreads
- Recent >10–15% one-day move
- Highly correlated candidates
- Leveraged ETFs or structurally decaying products
- Stocks with unusually concentrated single-name risk

## Daily decision categories

**QUALIFIED — REVIEW OPTION CHAIN** — all core gates pass.\
**WATCH — ONE GATE MISSED** — interesting setup but one specified criterion fails.\
**EVENT RISK — DO NOT STANDARDIZE** — volatility premium may be event-driven.\
**LIQUIDITY RISK** — stock or options market is too thin for normal sizing.\
**REJECT** — materially fails the core setup.

## Fail-closed / data-integrity rules

- If critical IV/HV data is stale or unavailable, do not treat the stock as passing.
- If 52W high/low data is unavailable, do not infer proximity.
- If option-chain OI/bid/ask cannot be validated, do not label the option chain qualified.
- If earnings/catalyst information is unavailable, mark **UNKNOWN**, not NO MATCH.
- If the universe is incomplete, do not report an exhaustive “NO QUALIFIED CANDIDATES.”
- If data sources disagree materially, show the discrepancy and use the more conservative interpretation.

## Important interpretation

This scanner is designed to find **volatility-premium candidates**, not to predict whether the stock will rise or fall.

The final trade decision should incorporate:
1. Option-chain structure
2. Earnings/catalysts
3. Market regime
4. Correlation with the existing portfolio
5. Margin usage
6. Worst-case drawdown
7. Assignment consequences
8. Expected premium relative to risk capital

## Daily prompt

> Run the Daily Stock Identifier using the complete static master universe across **`optionable_us_stock_universe.csv`**, **`optionable_us_etf_universe.csv`**, and the ADR rows included in the supplied stock/universe files. Include COMMON_STOCK, ADR and ETF rows; do not exclude ADRs or ETFs merely because the original scanner was stock-only. Load every active production row, deduplicate it, and process every unique ticker exactly once. Do not rebuild the optionable universe from daily screeners and do not substitute a hand-picked list.
>
> Verify the universe audit first: file loaded, universe version, rows loaded, unique production tickers, tickers processed, skipped/error count, and coverage percentage. If the file is missing, malformed, materially stale, or processing is materially incomplete, mark the run **PARTIAL / UNIVERSE INCOMPLETE** rather than claiming exhaustive coverage.
>
> Then run independent discovery paths against the same full universe: high IV, high IV rank/percentile, high IV versus HV, 52-week highs, and 52-week lows. Deduplicate the candidate union and then apply the exact gates below.
>
> Screen for:
> - IV30 >= 50%
> - IV30 - HV30 >= 10 vol points
> - IV30/HV30 >= 1.25
> - Stock within 10% of its 52-week high OR 52-week low
> - Price > $5
> - Stock ADV > $50M
> - Prefer option volume >1,000 and target-strike OI >1,000
> - Prefer bid/ask spread <15%
> - Flag earnings and other binary events within 14 days
>
> Show the complete universe audit and do not claim exhaustive coverage unless the universe was actually enumerated.
>
> Show the top candidates near highs and lows separately, plus near-miss exceptions.
>
> Before advancing any candidate, review historical >10% weekly drawdowns, identify documented drivers, and check whether any comparable driver/catalyst is scheduled, announced, or credibly developing between today and the next earnings date. Show the historical driver → upcoming catalyst mapping and flag HIGH-RISK MATCH / PARTIAL MATCH / NO MATCH / UNKNOWN.
>
> Then run second-stage option-chain analysis for surviving candidates using 30–60 DTE and approximately 8–15 delta puts.
>
> Do not recommend a trade solely from the scanner. Return **NO QUALIFIED CANDIDATES** only when the universe is sufficiently complete and all candidates have actually been processed.
