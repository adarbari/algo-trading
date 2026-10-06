# Market regime layer: learning from the big drawdowns (plan, draft 2026-10-06, rev 2)

Status: **proposal for review**, not yet a roadmap track or an ADR. Written from desk research
(sources at the end) plus a read of the codebase as of `main` 89203fe. Rev 2 adds what the
academic and practitioner literature contributes (section 3E), the free-source inventory
(section 3F), the plain-language layer for non-expert users (section 5.5) and the on-demand
Gemini explanation (section 5.6). Numbers for 2025 and
2026 come from the web and should be re-checked against our own bars once ingested.

## 1. The question

Every time SPY or the Nasdaq lost more than ~20% over several weeks, what caused it, what
would have warned us, and how early? Then: store those warnings as **parameters the platform
tracks every night**, so screeners and strategies can size down or skip ideas when the
backdrop looks like the start of one of these episodes.

## 2. The episodes

Twelve S&P 500 drawdowns of 19% or more (closing basis) since 1970, plus the Nasdaq where it
differed. "Recession" is the NBER dating. Durations are peak to trough.

| # | Peak -> trough | S&P 500 | Nasdaq | Length | Recession? | What caused it |
|---|---|---|---|---|---|---|
| 1 | 1973-01-11 -> 1974-10-03 | -48% | about -60% | 21 mo | Nov 73 - Mar 75 | Oil embargo (Oct 73), inflation, Fed funds 3.5% -> 13%, Nifty-Fifty valuations, Bretton Woods collapse |
| 2 | 1980-11-28 -> 1982-08-12 | -27% | about -25% | 20 mo | Jan - Jul 80, Jul 81 - Nov 82 | Volcker hikes to 19-20%, double-dip recession, unemployment to 10.8% |
| 3 | 1987-08-25 -> 1987-12-04 | -34% (-20.5% on one day) | -36% | 3 mo | No | Rates +300 bp in 1987, dollar / Louvre tension, portfolio insurance, stretched valuations |
| 4 | 1990-07-16 -> 1990-10-11 | -20% | -33% | 3 mo | Jul 90 - Mar 91 | Iraq invades Kuwait, oil doubles, S&L crisis and credit crunch |
| 5 | 1998-07-17 -> 1998-10-08 | -19% close, -22% intraday | -30% | 2.5 mo | No | Asian crisis, Russian default (Aug 17), LTCM; Fed cut three times |
| 6 | 2000-03-24 -> 2002-10-09 | -49% | -78% | 31 mo | Mar - Nov 01 | Dot-com valuations (CAPE 44), Fed to 6.5%, capex bust, 9/11, Enron / WorldCom |
| 7 | 2007-10-09 -> 2009-03-09 | -57% | -56% | 17 mo | Dec 07 - Jun 09 | Housing bust, subprime, bank leverage, Lehman (Sep 15 08), credit freeze |
| 8 | 2011-04-29 -> 2011-10-03 | -19% close, -22% intraday | -19% | 5 mo | No | US downgrade (Aug 5), debt ceiling, euro sovereign crisis |
| 9 | 2018-09-20 -> 2018-12-24 | -20% | -24% | 3 mo | No | Fed hikes plus QT "on autopilot", trade war, growth scare; Fed pivoted Jan 19 |
| 10 | 2020-02-19 -> 2020-03-23 | -34% | -30% | 5 weeks | Feb - Apr 20 | COVID shutdowns; credit froze; Fed to zero, unlimited QE |
| 11 | 2022-01-03 -> 2022-10-12 | -25% | -36% (Nov 21 -> Dec 22) | 9 mo | No (two negative GDP quarters) | CPI at 9%, Fed 0 -> 4.5% in a year, QT, Ukraine; long-duration growth re-rated |
| 12 | 2025-02-19 -> 2025-04-08 | -19% close, -21% intraday | -24% (Dec 24 -> Apr 25) | 7 weeks | No | "Liberation Day" tariffs (Apr 2); VIX closed 45; 90-day pause on Apr 9 began the recovery; new high by Jun 27 |

Context today (web, unverified): the S&P fell 9% from Jan 27 to Mar 30 2026 (AI capex and
geopolitical fears), the Nasdaq more than 10%, both recovered. At the end of Q3 2026 the S&P
was about 2% from its high while 83% of its members were more than 10% below theirs and 42%
more than 20% below. The Fed **raised** rates on 2026-09-16 to 3.75-4.00% with inflation
"elevated". Index near a high, breadth poor, Fed tightening into inflation: that is the 2000
and 2022 shape, which is exactly what this layer should be able to say out loud.

### Two kinds of drawdowns, two kinds of warning

The table splits cleanly:

- **Recession bears** (1, 2, 4, 6, 7, 10): deep (-20% to -57%), long (3 to 31 months, median
  about 17), and slow to recover (1 to 7 years). Macro data warned **6 to 18 months ahead**:
  an inverted yield curve, falling housing permits, tightening lending standards, rising
  claims, then widening credit spreads. 2020 is the exception on cause but not on signals:
  the curve had inverted in 2019 and ISM was below 50 for five months before the virus.
- **Shocks and re-ratings** (3, 5, 8, 9, 11, 12): -19% to -36%, 5 weeks to 9 months,
  V-shaped recoveries in 4 to 8 months (2022 took 2 years). Macro gave **no** recession
  warning. What was visible: stretched valuation (1987, 2000-like 2021), a Fed hiking into a
  high market (1987, 2018, 2022), narrowing breadth with the index at a high (2021, 2018),
  and then fast price-based confirmation: index through its 200-day average, VIX term
  structure inverting, high-yield spreads gapping, breadth collapsing within days.

Implication for us: **one score is not enough.** We need a slow macro score (recession risk,
updated weekly or monthly, long lead, sizes the book for the next quarters) and a fast market
stress score (daily, from our own bars and the VIX, lead of days, sizes the next trades). The
2022-24 experience (curve inverted 2 years, Sahm rule tripped in Jul 2024, no recession)
says the macro score is a **probability that scales size**, never a binary switch.

## 3. The parameters: what warned, how early, where to get it

Lead times are what the series did before the recession bears above. "False positives" are
the known misses. FRED ids are the free St. Louis Fed API (needs a free key); ALFRED gives
the **vintage** of every observation, which is what we need for point-in-time correctness
(ADR 0007: `knowledge_ts` is the release date, not the observation date).

### A. Slow macro (recession risk)

| Parameter | Series / source | Cadence | Signal | Lead | Record |
|---|---|---|---|---|---|
| Yield curve slope 10y-3m, 10y-2y | we already store the Treasury par curve (`rates/treasury`, ADR 0021); FRED `T10Y3M`, `T10Y2Y` for history to 1982 / 1976 | daily | inverted for 1+ month; un-inversion (bull steepening) is the late warning | 6-18 mo | 8 of 8 recessions since 1969; false: 1998 (brief), 2022-24 (so far) |
| Credit spreads | FRED `BAMLH0A0HYM2` (HY OAS, 1996-), `BAMLC0A0CM` (IG), `BAA10Y` (Baa minus 10y, long history) | daily | HY OAS above 5%, or +150 bp off its 6-month low | 3-9 mo, and concurrent | 5 of 5 since 1996; widens in shocks too (2018, 2025) |
| Jobless claims | FRED `ICSA`, `IC4WSA` | weekly (Thu, for prior week) | 4-week average 15-20% above its 52-week low | 1-6 mo | reliable but late; revised |
| Sahm rule | FRED `SAHMREALTIME`, `UNRATE` | monthly (first Fri) | 3-mo avg unemployment 0.5 pp above 12-mo low | concurrent (recession start) | 100% before 2020; false Nov 1976, Jul 2024 |
| Housing permits / starts | FRED `PERMIT`, `HOUST` | monthly | down 20%+ YoY | 12-24 mo (2006-07 textbook) | misses shocks |
| Activity | Chicago Fed `CFNAI` (FRED `CFNAIMA3`, rule: below -0.7), Philly Fed, Atlanta Fed GDPNow (CSV) | monthly / weekly | CFNAI-MA3 < -0.7 | concurrent | ISM PMI is no longer on FRED; use CFNAI plus S&P Global PMI headline by hand |
| Bank lending standards | FRED `DRTSCILM` (SLOOS, net % tightening C&I) | quarterly | above +20% | 2-4 quarters | 1990, 2001, 2008 all flagged; 2023 false |
| Fed policy | FRED `FEDFUNDS`, `DFII10` (10y real) | daily / monthly | 12-month change in funds rate above +200 bp; real yield rising fast | 6-18 mo | every recession bear since 1973 followed a hiking cycle; so did 1987, 2018, 2022 |
| Oil shock | FRED `DCOILWTICO` | daily | 12-month change above +50% | 0-12 mo | 1973, 1990, 2008 |
| Model probabilities | FRED `RECPROUSM156N` (Chauvet-Piger, smoothed), NY Fed curve-based probability (we can compute the probit from the slope) | monthly | > 20% / > 30% | lagging / 12 mo | reference, not a driver |

### B. Fast market stress (from our own data, day one)

All from `bars/1d` (SPY, QQQ, sector and factor ETFs are already priority symbols in
`sources.toml`) and the Cboe / FRED VIX series.

| Parameter | Computation | Threshold (starting point) | Caught |
|---|---|---|---|
| Index trend | SPY and QQQ close vs 200-day SMA; 50/200 cross | below 200d; death cross | every episode, 2-6 weeks after the peak; whipsaws in 2023, 2025 |
| Index drawdown | close vs 252-day high | -10% (stress), -20% (bear) | definitional; the 2025 and 2026 episodes stopped near -10 / -19 |
| Realised vol | 20-day stdev of SPY returns, annualised | above 25% | 1987, 2008, 2020, 2025 |
| Implied vol level | VIX (FRED `VIXCLS`, Cboe) | 25 caution, 35 stress | all since 1990 |
| Vol term structure | VIX / VIX3M (FRED `VXVCLS`) | above 1.0 (backwardation) | 2008, 2011, 2018, 2020, 2025; the cleanest short-horizon stress flag |
| Breadth | % of universe above 200d SMA; % more than 20% below 52-week high; new lows minus new highs | below 40% / above 40% | 2000 and 2021: breadth broke a year before the index; today 42% of S&P members are in a bear |
| Leadership ratios | RSP/SPY (equal weight), IWM/SPY, XLY/XLP, HYG/IEF, CPER/GLD, XLU and XLP relative strength | 3-month relative momentum negative | risk-off rotation preceded 2007, 2018, 2021 |
| Credit via ETFs | HYG/LQD ratio, HYG distance from 200d | below 200d | daily proxy for the OAS series above |

### C. Slow positioning and valuation (why the fall is deep, not when)

| Parameter | Source | Note |
|---|---|---|
| Shiller CAPE | Shiller data (monthly CSV) | above 30 in 1929, 2000, 2021: deep bears possible, timing useless |
| Margin debt | FINRA (monthly) | 12-month growth above +30% preceded 2000, 2007, 2021 |
| Fed net liquidity | FRED `WALCL` - `WTREGEN` - `RRPONTSYD` | falling liquidity during 2018 and 2022 |
| Put/call, AAII sentiment | Cboe, AAII (free) | extremes mark bottoms (2009, 2020, 2022, 2025) more than tops |

### D. Bottoming signals (as important as the warnings)

2020 and 2025 recovered in 4 to 6 months. A layer that only sizes down loses the rebound, so
the same page must show capitulation: breadth washout (under 15% above 200d) followed by a
breadth thrust (over 55% within 10 sessions), VIX peak then 20% below its 10-day high, HY OAS
turning down from its peak, and a policy response (Fed cut or pause, 2025's tariff pause).

### E. What the research literature adds

The table in A-D is the practitioner's list. The papers below were read for two things:
signals we were missing, and evidence on lead time. Only the free, reproducible ones become
parameters; the rest are deep-dive links for users.

| Line of research | Finding we use | Parameter it adds (free source) |
|---|---|---|
| **Bear-market prediction with macro variables**: Chen (2009, probit and Markov switching), Nyberg (2013, dynamic probit), Hauptmann et al. (Trier 2020), Candelon et al. (2015, severe simultaneous bears) | Bear states (not just recessions) are forecastable 1-6 months out; the **term spread and inflation** are the strongest predictors, the **external finance premium** (credit spread) next; a dynamic probit that knows yesterday's state beats a static one | `cpi_yoy` and its 12-month change (FRED `CPIAUCSL`); a **bear-state probit** we fit ourselves on term spread, inflation and HY spread, reported as a probability |
| **Bear and bull dating algorithms**: Pagan-Sossounov (2003), Lunde-Timmermann (2004), after Bry-Boschan | A bear market is a rule, not a judgment call: local peaks and troughs with a minimum phase length and a 20% threshold | The **episode scorecard dates its episodes with Pagan-Sossounov**, so the ground truth is reproducible and extends to the Nasdaq and to any index we hold |
| **Excess bond premium**: Gilchrist and Zakrajsek (2012); Fed FEDS Notes update it monthly | The part of credit spreads not explained by default risk leads downturns; the Fed publishes it with a 12-month recession probability | `ebp` and `ebp_recession_prob` (free CSV, monthly, revised: store vintages) |
| **Credit expansion and neglected crash risk**: Baron and Xiong (2017), 20 countries, 1920-2012 | Three-year bank credit growth raises equity **crash** probability while mean returns stay normal: exactly the "size, do not exit" situation | `bank_credit_3y_change` (FRED `TOTBKCR`, `BUSLOANS`) |
| **Bubbles for Fama**: Greenwood, Shleifer and You (2019) | A 100% two-year run-up of an industry does not predict low average returns but raises **crash probability from 20% to 53%**; the tell-tales are rising volatility, turnover, issuance and acceleration of the run-up | `sector_runup_2y`, `sector_vol_change`, `sector_turnover_change` from our sector and theme ETF bars; per-industry from the universe once history allows |
| **Turbulence and the absorption ratio**: Kritzman and Li (2010), Kritzman, Li, Page and Rigobon (2011), Kritzman, Page and Turkington (2012) | Mahalanobis distance of today's cross-asset returns (turbulence) and the share of variance explained by the first principal components (absorption) rise before and during drawdowns; a regime-switching strategy on them beat buy-and-hold | `turbulence_60d`, `absorption_ratio_500d` computed daily from the ETF basket we already hold (SPY, QQQ, IWM, TLT, IEF, HYG, LQD, GLD, USO, sector SPDRs) |
| **Financial conditions and growth at risk**: Adrian, Boyarchenko and Giannone (2019, AER) | Tight financial conditions (Chicago Fed NFCI) shift the whole **downside** of the GDP distribution while barely moving its centre | `nfci` and `anfci` (FRED, weekly) as the one financial-conditions input; `ofr_fsi` (daily CSV), `stlfsi4`, `kcfsi` as cross-checks |
| **Uncertainty indices**: Baker, Bloom and Davis (EPU); Jurado, Ludvigson and Ng (macro and financial uncertainty) | News-based policy uncertainty spikes around shocks (2011, 2018, 2025); JLN macro uncertainty rises into recessions | `epu_daily` (policyuncertainty.com CSV), `jln_macro_uncertainty` (FRED, twice-yearly update: context only) |
| **Unemployment trend**: Philosophical Economics "growth-trend timing"; Cleveland Fed (2021) on the unemployment trend | The unemployment rate crossing above its 12-month average led every post-war recession by about 3.5 months on average, earlier than the Sahm rule | `unrate_above_12m_avg` (FRED `UNRATE`) |
| **Syndrome composites**: Goldman Sachs bull/bear indicator (ISM percentile, curve slope, core inflation, unemployment, Shiller PE); Hussman's recession warning composite (credit spreads widening, S&P below six months ago, flat curve, PMI below 54 with payroll growth below 1.3%) | Weak signals are strong **together**: both houses score a count of conditions, which is the design in section 4 | `core_pce_yoy` (FRED `PCEPILFE`), `payrolls_yoy` (`PAYEMS`), a free PMI proxy (average of the Philly, Richmond, Dallas and Kansas City Fed manufacturing surveys, all on FRED; ISM itself is not free) |
| **Trend following as crash protection**: Faber (2007, 10-month SMA), AQR on trend in bear markets, VanEck on breadth, Zweig breadth thrust, Lowry 90% days | Trend rules miss the first 5-10% and pay whipsaws, but sidestepped most of 2000-02 and 2007-09; breadth thrusts mark durable bottoms | Already in B; adds `zweig_thrust` (10-day advancing share from under 40% to over 61.5%) and `pct_90_down_days_20d` |
| **Regime detection by HMM and machine learning** (2024-25 papers; Two Sigma, Man AHL practitioner notes) | 2-3 state hidden Markov models on returns and volatility find the same regimes after the fact and flip a few days after price does | A later, clearly labelled **model view** (`hmm_bear_prob`) next to the rules, never the primary signal: it cannot be explained to a non-expert in one sentence and it is not point-in-time stable |
| **Positioning and sentiment**: AAII (1987-), Yale crash-confidence index, Cboe put/call, FINRA margin debt, NAAIM | Extremes mark bottoms better than tops; margin-debt growth above 30% preceded 2000, 2007, 2021 | `aaii_bull_bear_spread` (free weekly), `put_call_equity` (Cboe daily), `margin_debt_yoy` (FINRA monthly page); NAAIM went subscription-only on 2026-08-01 (free data is 3 months delayed), so it is dropped; Yale is link-only (copyright) |

What the literature does **not** support: a single indicator with a reliable lead, precise
crash timing from valuation, or exits on the first signal. Everything above argues for a
count of conditions, a probability, and sizing.

### F. Free sources, by how we would ingest them

| Tier | Source | What it carries | Terms to check |
|---|---|---|---|
| 1 | **FRED and ALFRED API** (one free key) | about 80% of section A, E and the stress indices: `T10Y3M`, `T10Y2Y`, `BAMLH0A0HYM2`, `BAMLC0A0CM`, `BAA10Y`, `ICSA`, `IC4WSA`, `UNRATE`, `SAHMREALTIME`, `PAYEMS`, `PERMIT`, `HOUST`, `CFNAIMA3`, `DRTSCILM`, `FEDFUNDS`, `DFII10`, `DCOILWTICO`, `CPIAUCSL`, `PCEPILFE`, `TOTBKCR`, `BUSLOANS`, `NFCI`, `ANFCI`, `STLFSI4`, `KCFSI`, `RECPROUSM156N`, `GDPNOW`, `WEI`, `VIXCLS`, `VXVCLS`, `NASDAQCOM`, `WALCL`, `WTREGEN`, `RRPONTSYD`, the JLN uncertainty indices; ALFRED gives every vintage | FRED terms of use; the ICE BofA series carry their own notice: mark them `licence = "personal"` like the IBKR features (ADR 0028) |
| 2 | **Published CSVs** | Fed EBP (`ebp_csv.csv`, monthly, 1973-), OFR Financial Stress Index (daily), EPU (daily and monthly), Shiller CAPE (monthly), Atlanta Fed GDPNow (also on FRED), NY Fed WEI (also on FRED), Cboe daily market statistics (put/call), Treasury par curve (already ours) | each page states its terms; all are free for personal use |
| 3 | **Computed from our own stores** | trend, drawdown, realised vol, breadth, leadership ratios, turbulence, absorption ratio, sector run-ups, curve slope (from `rates/treasury`), Zweig thrust, 90% days | none |
| 4 | **Page-level or link-only** | FINRA margin statistics (monthly HTML table), AAII weekly survey (free email or page), Conference Board LEI headline (press release only; the series is paid), Yale confidence indices (display only), Google Trends "unemployment benefits" (Choi and Varian; unofficial API) | scrape only where terms allow; otherwise the card links out and we store nothing |
| gap | **Not free**: ISM PMI, Conference Board LEI series, NAAIM (from Aug 2026), Sornette LPPLS confidence feed, S&P Global PMI history | replaced by the FRED regional surveys, the Fed and Chicago Fed indices, and our own run-up features |

Index history for the scorecard: `NASDAQCOM` (FRED, 1971-) and `SP500` (FRED, the last 10
years), as `IDX:` instruments (section 5.1). Stooq's `^SPX` download (decades) now sits behind a
JavaScript challenge, so a long daily SPX history (before 2016) needs another source; Shiller's
monthly file (the `xlrd` parser follow-up, `docs/data/vendors.md`) covers the scorecard's older
episodes at monthly resolution.

## 4. The regime model we would ship

Two scores and one label, all stored as **features** so they are documented, versioned and
point-in-time like everything else (ADR 0023).

- `macro_risk_score@v1` (0-100, weekly): a weighted count of section A and E signals on,
  weights set on the six recession bears and penalised on 2022-24. Starting weights: curve 20,
  credit (HY spread or EBP) 20, labour (unemployment trend, Sahm, claims) 20, financial
  conditions (NFCI) 15, lending standards 10, permits 5, Fed change and inflation 10. The
  bear-state probit from section E is shown beside it as a second opinion.
- `market_stress_score@v1` (0-100, daily): section B signals plus turbulence and absorption;
  trend 20, vol term structure 20, drawdown 10, breadth 20, leadership and credit ETFs 15,
  turbulence and absorption 15.
- `fragility_score@v1` (0-100, monthly, context only): valuation (CAPE), credit expansion,
  sector run-ups, margin debt. It never changes the regime label; it changes the text ("a
  fall from here would likely be deep") and the deep-dive links.
- `regime@v1`: `CALM` (both low), `CAUTION` (macro high, market calm: late cycle), `STRESS`
  (market high, macro low: a shock), `CRISIS` (both high). Hysteresis: a regime is left only
  after 5 sessions below its threshold, to cut whipsaw.
- `regime_size_multiplier@v1`: site default 1.0 / 0.75 / 0.5 / 0.25, user-overridable
  (ADR 0015 layering), plus per-idea-kind rules: short-volatility ideas (the VRP scanner)
  are off in `STRESS` and `CRISIS`; momentum longs halve in `CAUTION`; defined-risk
  mean-reversion longs are allowed in `CRISIS` only after a bottoming signal (section D).

Validation before anything consumes it (section 6): an **episode scorecard** that replays the
twelve episodes with vintage data and reports, per episode, when each score crossed its
threshold relative to the peak, and the number of false alarms per decade. Acceptance: the
macro score is above 50 at least 3 months before each recession bear's peak; the stress score
is above 50 within 15 sessions of each peak; fewer than one false `CRISIS` per 3 years.

## 5. Where it goes in the platform

Everything below follows the settled decisions in `CLAUDE.md`; the three items marked **ADR**
change architecture and need `write-adr` plus an `architect` review.

### 5.1 Data: a market grain and a macro dataset

1. **Market-level features (ADR).** `docs/data/storage.md` already lists the
   "cross-section / market" grain (one row per date for the whole market) and the roadmap has
   FS6 (`cross_section` features) as "later". Today every feature is keyed by
   `instrument_id`. Decision to make: either (a) a `features/market` table keyed by
   `market_id` (`US`) + `session_date` with the same point-in-time columns, and a `scope =
   "market"` on `Feature` so the catalogue, `features(names)` and expression features work
   unchanged; or (b) a synthetic instrument per index. Recommend (a): breadth is a property of
   the universe, not of an instrument, and (a) keeps `SymbolResolver` honest (ADR 0018). New
   owner entries: `features.rollups.market` (compute), `storage.tables.market_features`
   (table), in `architecture/ownership.toml` and `architecture/layout.toml`.
2. **Index history (small ADR or an amendment to ADR 0009).** Our bars start when our
   ingestion started, so the 1990-2020 episodes cannot be replayed from `bars/1d`. Add
   `asset_class = "index"` instruments (`IDX:SPX`, `IDX:COMP`, `IDX:VIX`, `IDX:VIX3M`) fed
   from FRED (`NASDAQCOM` from 1971, `SP500` for 10 years, `VIXCLS`, `VXVCLS`),
   stored in the existing `bars/1d` table so every price feature group applies to them.
   Breadth cannot be rebuilt before our universe history begins; the scorecard says so and
   validates breadth only on the window we have.
3. **Macro series dataset** (`add-data-source` + `add-dataset`): vendor adapter
   `libs/sources/algotrade_sources/vendors/fred/` (ALFRED endpoint, vintages), a
   `macro/series` table at grain series x observation date x vintage (`knowledge_ts` = the
   vintage's `realtime_start`), a series registry in `config/site/macro.toml` (id, source,
   cadence, release lag, transform). Nightly step `macro` after `bars`, `critical = false`
   (ADR 0039): a FRED outage must never hold back the screens. Shiller, FINRA and GDPNow are
   CSV pulls through the same adapter shape, weekly in the `enrichment` cadence.

### 5.2 Features (`add-feature`)

- `features/rollups/market/trend.py`: index vs SMA, drawdown, realised vol, death cross
  (computed once per index, stored at market scope).
- `features/rollups/market/breadth.py`: the universe cross-section (% above 200d, % in a
  bear, new highs minus lows). This is the one group that needs the whole universe in its
  view; FS6 covers the mechanics.
- `features/rollups/market/macro.py`: curve slope from `rates/treasury`, HY OAS change,
  claims vs 52-week low, Sahm gap, permits YoY, SLOOS, Fed 12-month change, CFNAI.
- Everything else is **TOML expression features** in `config/site/features/regime.toml`:
  the ratios, the thresholds, the two scores, the label and the multiplier. No Python, and
  `make features-doc` documents them.

### 5.3 Consumption: sizing and skipping

- **Backtests**: an overlay in the engine, not in each strategy (strategies import only
  `core` and `quant`). `MarketView` exposes `market_features(names)`; the engine multiplies a
  strategy's `TargetWeights` by `regime_size_multiplier` when the run config enables the
  overlay, and the run record carries the config hash, so every backtest can be run with and
  without it. Metric to report in `make evaluate`: max drawdown, Sharpe and time-in-market
  with versus without the overlay.
- **Screeners**: `FeatureView` gets the market features; a screener row that the regime
  gate blocks is returned as `SKIPPED` with the reason (`regime=STRESS: short-vol off`), never
  silently dropped, so the Ideas page can show what was skipped and why. The gate itself is
  selection config (ADR 0015): `[regime] max_regime`, `size_multiplier`, per-screener
  overrides; site defaults in `config/site/`, user overrides in `config/users/<id>/`.
- **Ideas**: every idea carries the regime at its session and its sized weight.

### 5.4 Read model and web

- Read object `MarketRegime` in `src/algotrade/services/read/regime/` (`add-domain-object`):
  the label, both scores, each indicator with value, threshold, status, release date and
  lead-time note, the last 2 years of each series for sparklines, and UNKNOWN with a reason
  when a series is missing for the session (ADR 0036). GraphQL `Query.regime` and a `regime`
  field on `ideas` (`add-graphql-field`).
- Web (`add-web-page`, `add-ui-component`): a **Regime** page in the TRADER workspace with
  (1) the label and the two scores, (2) the indicator table, slow and fast, with status
  badges and sparklines, (3) an "episode overlay" that plots the chosen indicator through
  the twelve episodes against today, (4) the sizing rules in force for this user. On the
  Ideas page, a regime strip at the top and a `SKIPPED by regime` section. The design system
  has `StatusBadge`, `Sparkline`, `Chart` and `HeatGrid`; it needs a score meter and an
  indicator row component, added to `@algotrade/ui` first with stories.
- Admin: the `macro` step in the Ingestion page like any other step; its quality checks are
  staleness (no observation newer than the release lag plus two days) and vintage count.

### 5.5 Explaining it to people who are not experts (no model involved)

Our users will not read "10y-3m inverted 4 months, HY OAS +140 bp, NFCI +0.3". The page
speaks plain English first and shows the technical name on expand. All of this is
deterministic, generated from stored values and hand-written text, and therefore always
available and testable:

1. **One headline, four words.** The regime label is shown as market weather: `CALM` =
   "Clear", `CAUTION` = "Clouds building", `STRESS` = "Storm", `CRISIS` = "Severe storm". One
   sentence under it, templated from the counts: "4 of 8 slow-moving warning signs are on,
   up from 2 last month. The fast signs are quiet. This is how late 2007 and late 2021
   looked." Analogues come from the scorecard (nearest episodes by signal pattern).
2. **A card per indicator** in `config/site/regime_cards.toml`, reviewed by PR like any site
   preset: `plain_name` ("Are banks still lending?"), `one_liner` (what it measures),
   `why_it_matters` (two sentences), `what_on_means`, `before` (what it did before 2008,
   2020, 2022 in one line each), `lead_time`, `false_alarms`, and `links` (the FRED page,
   the Fed note or paper, one explainer). The web shows a traffic light, the plain name, the
   one-liner, "changed this week" and a "learn more" expander; the technical series id and
   value sit behind it.
3. **What changed and why it matters to you.** A "this week" list of indicators that turned
   on or off, and the sizing rule in force for this user ("new positions are sized at 75%;
   short-volatility ideas are paused"), each linking to the card that caused it.
4. **Honesty built in.** Every card shows the false-alarm line, the page shows the scorecard
   ("this setup preceded 6 of the last 12 big falls and gave 3 false alarms since 1990"),
   and a label never flips on one day's data (hysteresis, section 4).
5. **Deep-dive links** are curated in the cards and in a short reading list on the page:
   the Fed's recession-probability notes, the Sahm rule explainer, Chicago Fed NFCI page,
   the papers in section E. The model (next section) may only cite links from this list.

### 5.6 On-demand explanation through the existing text-model seam (Gemini, free tier)

ADR 0041 already gives us one `TextModel` protocol (`services/drafting/model.py`), one
OpenAI-compatible adapter (`algotrade_sources/llm/chat.py`) and `config/site/llm.toml`,
which on this machine is pointed at Gemini's OpenAI-compatible endpoint (`gemini-3.5-flash`,
free tier, key in `ALGOTRADE_LLM_API_KEY`). The explanation reuses all of it and adds one
prompt and one route:

- **Only when asked.** Nothing calls the model on page load or in the nightly. An "Explain
  in plain words" button on the regime header, and one per card, sends a request; the page
  shows the templated text (5.5) until then, so the feature degrades to "no button" when
  `llm.toml` is disabled or the provider is down (`ModelUnavailableError`, as drafting does).
- **Prompt = our facts, nothing else.** The system text is the task ("explain to someone who
  does not follow markets; describe, do not advise; use only the facts and links given;
  under 150 words; name the one or two signals that matter most"), the cards of the
  indicators currently on, the regime counts, the analogues and the allowed links. The user
  text is the question ("what is happening?", or the card's plain name). No market data
  beyond those numbers, no user data, no credentials, no free-text from the page: the same
  shape ADR 0041 fixed for drafting. The answer is plain text; links are rendered only if
  they are in the allowed list (an invented URL is dropped), and numbers in the answer are
  checked against the prompt's numbers before display (a mismatch shows the templated text
  with a note).
- **Cheap by construction.** Answers are cached by (`session_date`, the hash of the signals
  on, the question) on disk under `var/`, so the first click of the day pays and the rest
  of the team reads the cache; per-user rate limit of a few calls a minute. Gemini's free
  tier is per project and roughly 15 requests a minute and in the low thousands a day for
  Flash (it changed twice in 2025; the console shows the live number), which this never
  approaches. `reasoning_effort = "low"` and `answer_limit` stay as set for drafting.
- **Where it lives.** A new use case `src/algotrade/services/explaining/` (prompt, allowed
  links, answer checks) with its own owner entry; the adapter and settings stay owned by
  the drafting seam, which ADR 0041 is amended to call "the text-model seam" with two
  callers. REST `POST /regime/explain` (compute over a request body, the same class as
  `draft-from-text`) added to `architecture/rest_allowlist.toml`; it writes nothing but the
  cache. Tests: recorded Gemini answers in `tests/fixtures/`, the prompt rendered
  byte-stable from the cards (as `prompt.py` does today), the link and number checks.
- **Web.** A `features/regime-explain` slice with the button, a loading state, the answer
  as a `Surface` with the citations as chips, and the "model text, may be wrong" footer the
  design system already has for drafts.

### 5.7 Where it shows up: one source, many embeddings

The regime is a fact about the session, not a page. The web gets **one** `entities/regime`
slice (a Query hook for the session's regime, a `RegimeChip`, and a bands mapping for
charts); every embedding below reuses those three things and nothing else fetches or
derives anything (ADR 0038).

| Surface | Treatment |
|---|---|
| **Top bar, every screen** | the weather label beside the session date; hover: the one sentence and "what changed this week"; click: the Regime page. The one place a non-expert always sees it |
| **Ideas** | a strip under the header (sentence + the sizing rule in force for this user); a "Size" column with the multiplier applied; a collapsed "Paused by regime (n)" section listing the ideas the gate skipped, with reasons, never hidden silently |
| **Screener results and Builder** | the run's regime in the results header; `SKIPPED` rows carry the regime reason and a filter chip; the Builder shows the gate in one line ("pauses in Storm") linking to the user's regime settings |
| **Explore (instrument)** | the price chart shades Storm and Severe-storm sessions as bands (the same bands component as backtests); the Overview panel gets an "In rough markets" line: `beta_252d` and this name's drawdown in the 2020, 2022 and 2025 episodes, which are ordinary per-instrument features from bars (`features/rollups/price/episodes.py`) and so also feature-table columns |
| **Backtests** | regime bands on the equity curve; metrics split by regime (return and drawdown in Clear vs Storm); a with / without toggle = two runs differing only in the overlay config |
| **Admin** | the `macro` step and series freshness in Ingestion; per-user regime settings (max regime, multipliers) in Users & configs |
| **Regime page** | the full deep dive (5.4-5.6): header, cards, what changed, episode overlay, reading list, the explain button (also on the chip popover) |

Data cost: one `regime` query per session shared by every embedding; the per-instrument
episode features ride the existing `features(names)` read.

## 6. Sequence (each line is one or two PRs; `architect` review where marked)

| Phase | Deliverable | Notes |
|---|---|---|
| 0 | Roadmap track "RG" and ADR: market grain + `scope` on `Feature`; episodes as `config/site/regime_episodes.toml` (causes and notes) with the dates re-derived by Pagan-Sossounov from index history (the scorecard's ground truth); the cards file skeleton | architect **Status: done (RG0).** |
| 1 | `features/market` table, market rollups from data we already have: index trend, realised vol, breadth, ETF ratios, turbulence, absorption ratio, sector run-ups, curve slope from `rates/treasury`; `Query.regime` returning only these; a first Regime page with the plain-language header and cards (5.5) | no new vendor; usable within weeks **Status: done (RG1a-RG1h).** |
| 2 | FRED and ALFRED adapter with vintages, `macro/series`, `macro.toml` (tier 1 series), the tier 2 CSV pulls (EBP, OFR FSI, EPU, Shiller) through the same adapter shape, nightly `macro` step; index history (`IDX:` instruments from FRED and Stooq) | architect on the vintage / `knowledge_ts` mapping **Status: done (RG2a-RG2c); open: the first detached macro backfill (owner action).** |
| 3 | Macro rollup group, the TOML regime features (scores, label, multiplier, fragility), the bear-state probit, the episode scorecard in `make evaluate`, weights tuned on the scorecard | property tests: deterministic, no lookahead (vintage-only reads) **Status: done (RG3a, RG3b); open: the Pagan-Sossounov published-table check, and weights and probit coefficients tuned once the backfill has run.** |
| RG3a | `market_macro`, `regime_indicators` and `regime` groups: the scores, the label and its hold | **done** (#216) |
| RG3b | EBP, OFR FSI and EPU series (`market_macro@v2`, EBP in the credit signal), the `_Vintages` input, `quant/probit.py` + `ncdf` + the `bear_prob_6m` / `bear_prob_source` expression features, the episode scorecard (`algotrade-backtest regime-scorecard`, in `make evaluate`) | **done**; open: the Pagan-Sossounov published-table check (the paper's own dating table), and weights and probit coefficients tuned once the macro backfill has run |
| 4 | Engine overlay, screener `SKIPPED` reasons, `[regime]` selection config, Ideas badge; backtest with versus without on the strategies we have | architect (engine, point-in-time) **Status: done (RG4, #217; the screener reasons became `Decision.PAUSED`).** |
| 5 | `entities/regime` slice, top-bar chip, Ideas strip and paused section, chart bands on Explore and Backtests, per-instrument episode features; then the full Regime page: indicator table, episode overlay, bottoming signals, sizing rules, "what changed this week", reading list | design system first **Status: done (RG1g, RG5a, RG5b, the Regime page); open: the Backtests bands, the by-regime split and the with / without toggle (wait for the Backtests page mockup).** |
| 6 | On-demand explanation (5.6): `services/explaining`, `POST /regime/explain`, cache, the web button; ADR 0041 amendment | small; after the cards exist, since the prompt is the cards **Status: done (RG6).** |
| later | HMM model view, Google Trends, per-industry run-ups from the universe | only after the scorecard says the rules work **Status: open.** |

Phases 1 and 2 are independent and can run as two work items in parallel.

## 7. What this will not do, said up front

- **Twelve episodes is a small sample.** Weights tuned on them will overfit; keep the model
  to counts and thresholds, publish the scorecard, and resist adding parameters to catch one
  more episode.
- **It costs return in bull markets.** Trend and macro filters were wrong for most of 2023
  and would have cut size into the 2025 V-recovery. The sizing multiplier, hysteresis and
  the bottoming signals limit that; the with-versus-without backtest measures it.
- **Macro data is revised and released late.** Without vintages the backtest cheats; this is
  why phase 2 insists on ALFRED and why `knowledge_ts` is the release date.
- **Shocks are not forecastable from macro.** For 1987, 2011, 2018 and 2025 the honest claim
  is: valuation and Fed tightening said "fragile", and the stress score confirmed within days
  and sized us down for the rest of the fall. That is still worth having.
- Breadth history starts with our universe history; the early episodes validate only the
  index-based and macro signals.
- **The model explains; it never decides.** The regime, the sizing and every number on the
  page come from stored features. The Gemini text is a reading aid, cached, opt-in, and
  checked against the facts it was given.
- **Free-tier terms move.** NAAIM closed its free feed in Aug 2026 and Gemini's free quota
  changed twice in 2025; every tier 2 and tier 4 source needs a terms line in `macro.toml`
  and the nightly step must degrade (UNKNOWN with a reason), never fail the workflow.

## 8. Sources

- Episode dates and depths: [History of Market, S&P 500 drawdown table](https://historyofmarket.com/sp500/drawdown/);
  [Seeking Alpha, complete history of bear markets](https://seekingalpha.com/article/4483348-bear-market-history);
  [Hartford Funds, bear markets](https://hartfordfunds.com/practice-management/client-conversations/managing-volatility/bear-markets.html);
  [Wikipedia, 2025 stock market crash](https://en.wikipedia.org/wiki/2025_stock_market_crash).
- 2026 context: [Motley Fool, Nasdaq and S&P correction, Mar 2026](https://www.fool.com/investing/2026/03/27/nasdaq-sp-500-correction-sell-off-2026/);
  [Nasdaq, September 2026 review and outlook](https://www.nasdaq.com/articles/september-2026-review-and-outlook);
  [Haver, FOMC lowers / raises target](https://www.haver.com/articles/fomc-lowers-fed-funds-rate-target-as-expected);
  [Stephens, Fed update 2026-09-16](https://www.stephens.com/uploads/shared/documents/PCG-Docs/FOMC-Updates/Fed-Update-9-16-26.pdf).
- Indicator track records: [eco3min, how accurate are recession indicators](https://eco3min.fr/en/recession-indicators-accuracy/);
  [CAIS, revisiting top recession indicators](https://www.caisgroup.com/articles/circling-the-recession-runway-revisiting-top-indicators);
  [Diamond Hill, yield curves, GDP and the Sahm rule](https://www.diamond-hill.com/insights/a-703/articles/yield-curves-gdp-and-the-sahm-rule-navigating-recession-signals-for-fixed-income-investors/);
  [J.P. Morgan Private Bank, why this cycle is defying history](https://privatebank.jpmorgan.com/nam/en/insights/markets-and-investing/why-this-economic-cycle-is-defying-history-and-breaking-the-rules).
- Data: [FRED common series](https://glama.ai/mcp/servers/@stefanoamorelli/fred-mcp-server/blob/41a5270f604aef6d81d0c33a9f2054be0d43a4dd/docs/resources/common-series.mdx);
  [ALFRED vintages](https://alfred.stlouisfed.org/search?st=daily).
- Bear-market prediction: [Chen (2009) and Nyberg (2013) as surveyed in Hsu's job-market paper](https://econ.washington.edu/sites/econ/files/documents/job-papers/hsu_jmpaper_0.pdf);
  [Hauptmann et al., predictability of bull and bear markets (Trier 2020)](https://www.uni-trier.de/fileadmin/fb4/prof/VWL/EWF/Research_Papers/2020-01.pdf);
  [external finance premium and bear markets (MPRA)](https://mpra.ub.uni-muenchen.de/49093/1/MPRA_paper_49093.pdf);
  [predicting severe simultaneous bear markets](https://ideas.repec.org/a/eee/finlet/v13y2015icp196-204.html);
  [when a correction turns into a bear market (2023)](https://link.springer.com/article/10.1057/s41260-023-00306-3);
  [bbdetection: Pagan-Sossounov and Lunde-Timmermann dating](https://cran.r-universe.dev/bbdetection).
- Credit and crashes: [Fed, updating the recession risk and the excess bond premium (CSV link inside)](https://www.federalreserve.gov/econres/notes/feds-notes/updating-the-recession-risk-and-the-excess-bond-premium-20161006.html);
  [Gilchrist and Zakrajsek, credit spreads and business cycle fluctuations](https://mfm.uchicago.edu/wp-content/uploads/2020/07/Gilchrist_Zakrajsek_Credit-Spreads-and-Business-Cycle-Fluctuations-UPDATED.pdf);
  [Baron and Xiong, credit expansion and neglected crash risk](https://www.nber.org/papers/w22695).
- Bubbles and fragility: [Greenwood, Shleifer and You, Bubbles for Fama](https://www.nber.org/papers/w23191);
  [Kritzman, Page and Turkington, regime shifts: implications for dynamic strategies](https://www.researchgate.net/publication/256020455_Regime_Shifts_Implications_for_Dynamic_Strategies);
  [Kritzman et al., principal components as a measure of systemic risk (absorption ratio)](https://web.mit.edu/finlunch/Fall10/PCASystemicRisk.pdf);
  [Alpha Architect, are stock market bubbles identifiable (LPPLS)](https://alphaarchitect.com/are-stock-market-bubbles-identifiable/).
- Financial conditions and uncertainty: [Adrian, Boyarchenko and Giannone, Vulnerable Growth](https://www.aeaweb.org/doi/10.1257/aer.20161923);
  [FRED blog on NFCI](https://fredblog.stlouisfed.org/tag/nfci/); [FRED blog on KCFSI and the other stress indices](https://fredblog.stlouisfed.org/tag/kcfsi/);
  [Baker, Bloom and Davis, measuring economic policy uncertainty](https://www.hoover.org/research/measuring-economic-policy-uncertainty);
  [Ludvigson, macro and financial uncertainty indexes](https://sydneyludvigson.com/macro-and-financial-uncertainty-indexes).
- Labour trend and composites: [Philosophical Economics, in search of the perfect recession indicator](https://www.philosophicaleconomics.com/?p=7644);
  [Cleveland Fed, recessions and the trend in the unemployment rate](https://www.clevelandfed.org/publications/economic-commentary/ec-202101-recessions-and-the-trend-in-the-us-unemployment-rate);
  [Goldman Sachs bull/bear indicator (CNBC)](https://www.cnbc.com/2018/11/12/goldmans-bear-market-indicator-shows-zero-returns-over-next-year.html);
  [Hussman, recession warning composite](https://hussmanfunds.com/wmc/wmc120109.htm).
- Trend and breadth: [VanEck, market breadth whitepaper](https://www.vaneck.com/globalassets/home/us/insights/blogs/guided-allocation/market-breadth-whitepaper_2019.11.pdf);
  [StockCharts, trend signals after whipsaws](https://articles.stockcharts.com/article/articles-arthurhill-2023-02-should-we-continue-taking-tren-946/);
  [Quantified Strategies, Faber's trend rule on the S&P 500](https://quantifiedstrategies.substack.com/p/trend-following-strategy-in-s-and-005).
- Regime models: [adaptive hierarchical HMMs for structural market change (2025)](https://www.mdpi.com/1911-8074/19/1/15);
  [LSEG, market regime detection with statistical and ML approaches](https://developers.lseg.com/en/article-catalog/article/market-regime-detection).
- Nowcasts and sentiment: [GDPNow on FRED](https://fred.stlouisfed.org/data/GDPNOW); [NY Fed Weekly Economic Index](https://datawrapper.dwcdn.net/os0lZ/1);
  [Choi and Varian, predicting the present with Google Trends](https://www.frbsf.org/Varian-part_1.pdf);
  [AAII sentiment survey](https://www.aaii.com/o/sentimentsurvey); [NAAIM exposure index (subscription from Aug 2026)](https://naaim.org/programs/naaim-exposure-index/);
  [Cboe daily market statistics](https://www.cboe.com/us/options/market_statistics/daily/); [FINRA margin statistics](https://www.finra.org/investors/margin-statistics);
  [Yale stock market confidence indices](https://som.yale.edu/centers/international-center-for-finance/data/stock-market-confidence-indices/united-states).
- Gemini free tier (changes often; the console is authoritative): [free-tier limits guide, 2026](https://yingtu.ai/en/blog/google-gemini-api-free-tier).
