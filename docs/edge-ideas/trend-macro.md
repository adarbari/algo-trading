# Edge ideas, family E. Trend, macro and cross-asset (ETFs)

Researched 2026-10-17 (deep-research agents; index and ranking: [README.md](README.md)). Ideas, not edges: nothing here is filed or tested. Figures marked *not verified*, *nv*, *recalled* or *from memory* must be checked against the source before an edge document cites them (quality bar item 5, [edges-plan.md](../edges-plan.md)).


**Family summary.** The best-evidenced ideas here are the slow, century-old ones: time-series momentum / trend following across asset classes (positive in every decade since 1880, net Sharpe ~0.4 per asset, ~0.8 diversified, with a 2010s drought, a +27% 2022 and a −20% drawdown May 2024 – May 2025), carry across asset classes, and absolute momentum used as a crash filter on a few ETFs. Equity-index timing by a single macro or valuation series (CAPE, curve inversion, Fed liquidity, copper/gold, VIX level) is mostly Weak-to-Dead as a standalone signal once tested out of sample, but several of these series are good *regime conditioners* for other edges. TAA families (GTAA, VAA, DAA, GEM) are real but heavily over-fitted: out-of-sample Sharpe runs roughly half the backtest, so each is filed with its published number and the honest post-publication record. Feasibility is high because almost everything maps to a dozen liquid ETFs and FRED series we already store; the binding gap is history (daily ETF bars only from 2024-10 until the Tiingo backfill to ~2010 lands) and the absence of futures term-structure data (IBKR later). Search budget was exhausted mid-task (shared cap); numbers marked "not verified" come from memory of the primary paper and should be checked against it before an edge document is written.

**Shared ETF map (used below).** Equity: SPY/VOO/IVV, QQQ, IWM, VEA/EFA, VWO/EEM, country iShares (EWJ, EWG, EWU, EWZ, EWY, EWT, INDA, FXI/MCHI, EWA, EWC …). Sectors: XLK XLF XLE XLV XLI XLY XLP XLU XLB XLRE XLC; defensives vs cyclicals via XLP/XLU/XLV vs XLY/XLI/XLB/XLF. Bonds: SHY/SHV/BIL, IEF, TLT, TIP, LQD, HYG/JNK, BND/AGG, EMB, BNDX. Commodities: GLD/IAU, SLV, USO, UNG, DBC/PDBC/GSG, DBA, CPER, DBB. Volatility: VIXY/VXX, SVXY/SVOL (products, not for timing data). Currencies: UUP/UDN, FXE, FXY, FXB, FXA, FXC (FX carry ETF DBV was delisted; CEW too — carry via single-currency ETFs only). Multi-asset proxies for CTA / managed futures: DBMF, KMLM, CTA (long-only tradeable versions of trend).

**Shared data map.** FRED (`macro/series`): T10Y3M, T10Y2Y, DGS*, BAMLH0A0HYM2 (HY OAS), BAMLC0A0CM (IG OAS), BAA10Y, DFII10 (10y real), DCOILWTICO, RRPONTSYD, ICSA, NFCI, EBP, OFR FSI, EPU, unemployment (Sahm), WALCL/TGA addable; `rates/treasury` daily par curve; IDX:SPX, IDX:COMP; `market_breadth@v1`, `market_cross_asset@v1`, `market_macro@v3`, `regime_indicators@v1`, `regime@v3` (label, macro_early / macro_confirming / market_stress); `events/macro_release` with `known_from`. Options: SPY/QQQ/sector chains → our own IV30, term structure, skew (a VIX-like series without VIX data; FRED VIXCLS and VIX3M are addable). Missing: futures curves (IBKR), per-country CAPE (Barclays / Research Affiliates publish monthly, scrapeable), NYSE advance/decline (we have universe breadth, which is close), ETF history before 2024-10 until the Tiingo backfill.

---

### tsmom_multi_asset_etf — Time-series momentum across asset classes (trend following) in ETFs
- **Thesis**: Each asset's own past 12-month excess return predicts its next month: hold ETFs whose trailing return is positive, hold cash (or short / underweight) those negative, across equities, bonds, commodities and currencies.
- **Mechanism**: Initial under-reaction to news (anchoring, slow-moving capital), then herding over-reaction; institutions' mandates and rebalancing rules force them to sell what rose and buy what fell at the wrong time; hedgers in futures pay speculators to carry trend risk.
- **Persistence**: Deep drawdowns (16 drawdowns >10% since 2000 in the SG Trend Index, roughly every 18–24 months; −20.4% May 2024 – May 2025) and years of nothing (2010s) are what nobody with a 3-year horizon wants to hold; capacity is large but allocation is pro-cyclical (outflows after droughts), which keeps the premium.
- **Rule (source's own)**: Moskowitz-Ooi-Pedersen (2012): sign of trailing 12-month excess return, position scaled to 40% ex-ante vol, 1-month hold, 58 futures 1985–2009. Hurst-Ooi-Pedersen (2017): equal-weighted 1-, 3-, 12-month trend signals, 67 markets 1880–2016. ETF long-only variant: hold each ETF when its 12-month return > T-bill, else cash.
- **Evidence**: HOP 2017: positive net returns in every decade since 1880; net Sharpe ~0.4 (one summary; Swedroe reports 0.76 after 2/20 fees — the two bases differ, check the paper). Baltussen-Swinkels-van Vliet (JFE 2021, 1800–2016): multi-asset trend Sharpe ~1.09 in the modern sample with limited out-of-sample decay; long-run average gross Sharpe across factors ~0.41. Live: SG Trend Index 2008 +20.9%, 2022 +27.4%, 2023 about −4% (Top Traders Unplugged), 2024 flat-to-negative, −20.4% drawdown to May 2025 (Cambridge Associates), who conclude it is cyclical, not structurally broken. Huang-Li-Wang-Zhou (JFE 135(3) 2020, "Time series momentum: Is it there?"): asset-by-asset regressions show little TSM in or out of sample, the pooled t-stat falls below bootstrap critical values, and the TSM strategy performs virtually the same as one built on the historical sample mean, which needs no predictability (verified, abstract).
- **Sources**: Moskowitz, Ooi, Pedersen 2012 JFE "Time series momentum"; Hurst, Ooi, Pedersen 2017 JPM "A century of evidence on trend-following investing" (https://www.TrendFollowing.com/whitepaper/Century_Evidence_Trend_Following.pdf); Baltussen, Swinkels, van Vliet 2021 JFE "Global factor premiums" (https://papers.ssrn.com/abstract=3325720); Cambridge Associates 2025 (https://www.cambridgeassociates.com/insight/does-trend-followings-recent-struggle-signal-that-the-strategy-is-structurally-broken/); SG CTA update 2025 (https://content.sgmarkets.com/CTA_UPDATE_KEEPING_UP_WITH_THE_TRENDFOLLOWERS_2025); Huang, Li, Wang, Zhou 2020 JFE 135(3) 774-794 "Time series momentum: Is it there?" (https://doi.org/10.1016/j.jfineco.2019.08.004).
- **Horizon / schedule**: 21 sessions; month_end (daily monitoring optional). Trigger known at the month-end close; first action next session's open.
- **Data needed**: ETF daily bars (have from 2024-10; need Tiingo backfill to ~2010 for ≥40 independent month-end events per ETF — ~15 years × 12 = 180 months, fine); T-bill rate from `rates/treasury`. Futures history (IBKR) only for a faithful MOP replication.
- **Individual fit**: Excellent: 10–20 ETFs, monthly turnover ~1 switch per asset per year (Antonacci measured 0.33–1.08 switches/yr), spreads tiny. Long-only variant loses the short leg (most of the 2008/2022 crisis alpha came from short bonds/equities; long-only keeps the cash-sitting part). Vol scaling needs leverage → skip or use partial.
- **Decoys / overlap**: Beta (long-only trend is mostly long equity beta in bull markets); overlaps with filed 12-1 cross-sectional momentum only in sign — this is time-series, per asset. Decoy: a 1950–2010 backtest dominated by the 1970s bonds bear and 2008.
- **Verdict**: Strong (as a family; Sharpe expectation after decay ~0.3–0.5 for long-only ETF version) — Needs data (Tiingo ETF backfill; futures via IBKR optional). Ready as soon as backfill lands.

### absolute_momentum_crash_filter — Absolute (12-month) momentum as an exit rule on core holdings
- **Thesis**: Hold SPY (or any risk asset) only while its trailing 12-month total return exceeds T-bills; otherwise sit in T-bills. Cuts drawdowns by half for a small cost in return.
- **Mechanism**: Same under-reaction / forced-selling as trend; bear markets are long enough (median > 12 months) that a slow exit still skips most of the damage.
- **Persistence**: It costs return in sideways and V-shaped markets (2011, 2015–16, 2020, 2023), which is when holders abandon it.
- **Rule (source's own)**: Antonacci (2013 "Absolute momentum"): monthly, risky asset if 12-month excess return > 0 else T-bills; tested 8 asset classes Jan 1973 – Dec 2012, 0.2% per switch.
- **Evidence**: Antonacci 2013: Sharpe up and max DD down for all 8 classes; 60/40 Sharpe 0.47 → 0.72, DD −29.3% → −13.4%; five-asset equal-weight Sharpe 0.62 → 1.06, DD −30.4% → −9.6% (CXO summary of indexes, not ETFs). Post-publication: the 12-month lookback was the best of 2–18 in-sample (snooping); the 2020 crash was too fast (exit after the bottom); 2022 worked (exit Jan–Feb 2022, re-entry early 2023). Zakamulin's SMA results (below) apply: ~80% of the time out of the market the rule underperforms buy-and-hold, it earns its keep in the 20%.
- **Sources**: Antonacci 2013 SSRN "Absolute Momentum: A Simple Rule-Based Strategy and Universal Trend-Following Overlay"; CXO review (https://www.cxoadvisory.com/momentum-investing/intrinsic-momentum-across-asset-classes/); Zakamulin 2014/2016 SSRN papers on moving-average timing (https://papers.ssrn.com/abstract=2677212).
- **Horizon / schedule**: 21 sessions; month_end.
- **Data needed**: ETF bars + T-bill; have (history pending backfill).
- **Individual fit**: Trivial: 1–5 ETFs, ~1 trade/yr each; tax drag is the real cost.
- **Decoys / overlap**: Pure beta timing; overlaps with tsmom (this is the one-asset long-only case) and with the regime label (which is a richer version of the same exit).
- **Verdict**: Promising (risk-management edge, not alpha) — Ready (needs backfill for ≥40 events; use index levels IDX:SPX for the pre-ETF period).

### sma10_timing_faber — Faber 10-month SMA timing (GTAA)
- **Thesis**: Hold each of five asset classes (US stocks, foreign stocks, bonds, commodities, REITs) when price is above its 10-month SMA, else cash.
- **Mechanism**: As trend; the SMA is just a smoothed 12-month momentum.
- **Persistence**: Same as above; also the rule whipsaws (false signals in ~every bull and bear).
- **Rule (source's own)**: Faber (2007 JWM "A quantitative approach to tactical asset allocation"): month-end close vs 10-month SMA, 20% per asset, cash = 90-day T-bill.
- **Evidence**: Faber in-sample 1972–2005: equity-like return at bond-like vol (CAGR 11.7%, Sharpe 0.81, max DD 9.5% monthly per Concretum's replication). Out-of-sample Jan 2006 – Mar 2025 (Concretum, 200-day SMA variant): CAGR 6.05%, Sharpe 0.68, max DD 11.7% — still decent risk-adjusted, far below in-sample absolute return, and below a 60/40 since 2009. Zakamulin (2013–2016): the 10-month window is optimal only for the S&P Composite among four indexes; with 1-month look-ahead removed the risk-adjusted improvement is not convincing; over 155 years timing rules outperform only in bear states and underperform ~80% of the out-of-market intervals.
- **Sources**: Faber 2007/2013 SSRN 962461; Concretum Group 2025 (https://concretumgroup.substack.com/p/global-tactical-asset-allocation); Zakamulin, "A comprehensive look at the empirical performance of moving average trading strategies" (https://papers.ssrn.com/abstract=2677212) and "Revisiting the profitability of market timing with moving averages"; CXO (https://www.cxoadvisory.com/technical-trading/net-performance-of-sma-and-intrinsic-momentum-timing-strategies).
- **Horizon / schedule**: 21 sessions; month_end.
- **Data needed**: Bars for SPY, VEA/EFA, IEF/BND, DBC/GSG, VNQ; have post-backfill.
- **Individual fit**: 5 ETFs, ~5–8 trades/yr total; very cheap.
- **Decoys / overlap**: Near-duplicate of absolute momentum (correlation of signals ~0.9); the "equity-like return" claim is period-specific (1970s bond bear, 2000–09 two crashes). Overlap: tsmom_multi_asset_etf, absolute_momentum_crash_filter.
- **Verdict**: Promising as a drawdown-control variant, Weak as alpha — Ready (after backfill). File as a variant of absolute momentum, not a separate edge.

### dual_momentum_gem — Antonacci Global Equities Momentum (relative + absolute)
- **Thesis**: Monthly, hold US stocks if they beat ex-US stocks over 12 months and beat T-bills; else ex-US if it beats T-bills; else aggregate bonds.
- **Mechanism**: Relative momentum captures cross-country under-reaction; absolute momentum the crash filter.
- **Persistence**: A three-asset switch is too concentrated for institutions; whipsaw cost and 2015–2024 lag vs the S&P 500 (US beat ex-US almost continuously, so the relative leg added nothing and the absolute leg cost 2020/2023 re-entries) deter followers.
- **Rule (source's own)**: Antonacci (2014, "Dual Momentum Investing"): 12-month total return of S&P 500 vs MSCI ACWI ex-US vs T-bill; month-end; invest 100% in the winner or in Barclays Aggregate.
- **Evidence**: Book backtest 1974–2013: CAGR ~17% vs ~12% ACWI, max DD ~−18% vs −60% (not verified). ReSolve (2019, "GEM: a craftsman's perspective"): attractive in- and out-of-sample 1950–2018, but returns are very sensitive to the lookback and rebalance day (the craftsman critique: an ensemble of lookbacks and tranches halves the dispersion). Live since 2014: lagged the S&P 500 (our search for the 2015–2025 track record hit the budget cap; the Antonacci site figures are not verified here). Hammerstad & Pettersen (2022) document momentum's declining effectiveness since 2009.
- **Sources**: Antonacci 2014 (book) and 2013 SSRN "Risk premia harvesting through dual momentum"; ReSolve 2019 (https://files.advisorperspectives.com/articles/2019/05/06/global-equity-momentum-a-craftsmans-perspective); Algo Edge Insights robustness post (https://algoedgeinsights.beehiiv.com/p/is-gary-antonacci-s-global-equity-momentum-strategy-robust).
- **Horizon / schedule**: 21 sessions; month_end.
- **Data needed**: SPY, VEU/ACWX, AGG/BND, T-bill. Have post-backfill.
- **Individual fit**: 3 ETFs, ~2 trades/yr; ideal retail strategy; long-only by design.
- **Decoys / overlap**: Mostly "US beat the world 2010–2024" plus a trend filter; overlaps absolute momentum and country momentum. Decoy: survivorship of the US as the test market.
- **Verdict**: Promising (risk-adjusted), Weak (recent alpha) — Ready after backfill; test as an ensemble over lookbacks (ReSolve) rather than the single 12-month rule.

### taa_keller_vaa_daa — Keller's Vigilant / Defensive Asset Allocation (breadth momentum + canary)
- **Thesis**: Rank a universe of ETFs by a 1-3-6-12-month momentum blend; go to cash in proportion to how many "canary" assets (VWO, BND) have negative momentum; otherwise hold the top T assets.
- **Mechanism**: EM equities and aggregate bonds turn down before global risk assets (liquidity canary); momentum ranks the rest.
- **Persistence**: Monthly all-or-nothing cash moves create whipsaw losses in choppy years; the canary rule is a hand-fitted heuristic nobody with a mandate can hold.
- **Rule (source's own)**: VAA (Keller & Keuning 2017): universe G4 = SPY VEA VWO BND; momentum 13612W (weighted toward 1 month); any negative-momentum asset → 100% cash to best of SHY/IEF/LQD. DAA (2018): canary universe VWO+BND, B = 2; cash fraction b/B; risky part top T by momentum from G12 (SPY IWM QQQ VGK EWJ VWO VNQ GSG GLD TLT HYG LQD).
- **Evidence**: VAA-G4 backtest (user-reported, unverified): CAGR 17.7%, Sharpe 1.07, max DD 16.1% (1971–2017). DAA: higher CAGR than VAA in 3 of 4 universes, worse drawdown in all 4 over Mar 2008 – Mar 2018; canary selected on 1926–1970, optimised 1971–1993, "out-of-sample" 1994–2018 (but published 2018, so everything is in-sample to the publication). Post-publication tracking (Allocate Smartly) could not be fetched (paywall); general TAA decay evidence: post-publication Sharpe falls ~43% (Falck et al. arXiv 2105.01380), 58% for factor anomalies (McLean-Pontiff 2016). The 13612W weighting on the most recent month is the biggest over-fitting red flag.
- **Sources**: Keller & Keuning 2017 SSRN 3002624 "Breadth momentum and Vigilant Asset Allocation"; Keller & Keuning 2018 SSRN 3212862 "Breadth momentum and the canary universe: Defensive Asset Allocation"; CXO review (https://www.cxoadvisory.com/strategic-allocation/multi-class-momentum-portfolio-with-canary-crash-protection/); Falck, Rej, Thesmar 2021 "Why and how systematic strategies decay" (https://arxiv.org/pdf/2105.01380).
- **Horizon / schedule**: 21 sessions; month_end.
- **Data needed**: 12–16 ETFs, all listed; post-backfill ~190 month-ends.
- **Individual fit**: Cheap, long-only, but 100%-cash moves are tax-inefficient.
- **Decoys / overlap**: A re-parametrised GEM / tsmom with a liquidity canary; expect out-of-sample Sharpe ~half the backtest. Overlap: all TAA ideas here.
- **Verdict**: Weak as published (over-fitted), Promising as the *canary idea* (EM + bonds as a risk-off trigger) — Ready after backfill; test the canary rule in isolation.

### carry_multi_asset_etf — Carry across asset classes via ETFs
- **Thesis**: Assets whose price would earn a positive return if nothing changed (high yield, backwardated curve, roll-down, high dividend) outperform low-carry assets; hold high-carry ETFs vs low-carry within each class.
- **Mechanism**: Compensation for crash risk (carry crashes in liquidity events), and investors over-weighting expected price change versus yield; regulated holders (banks, insurers) cannot hold the high-carry leg.
- **Persistence**: Negative skew and left-tail correlation with equities; 2008 and 2020 wiped out years of carry; no one wants that risk at the wrong time.
- **Rule (source's own)**: Koijen-Moskowitz-Pedersen-Vrugt (JFE 2018): carry = expected return if prices stay constant (futures basis / yield pickup); monthly rank within class; diversified carry portfolio Sharpe ~1.1 across equities, bonds, commodities, FX, credit, options 1983–2012 (headline figure from memory, not verified in this pass). Baltussen et al. 2021: multi-asset carry Sharpe ~1.15 in the modern sample, strong out of sample 1800–2016.
- **Evidence**: As above; live carry (FX) was poor 2008–2020, strong 2021–2024. Costs eat most retail FX carry.
- **Sources**: Koijen, Moskowitz, Pedersen, Vrugt 2018 JFE 127(2) 197–225 "Carry"; Baltussen, Swinkels, van Vliet 2021 JFE; Pedersen, "Efficiently Inefficient" ch. on carry; Ilmanen "Expected Returns" ch. on carry.
- **Horizon / schedule**: 21 sessions; month_end.
- **Data needed**: Bond carry: `rates/treasury` curve (yield + roll-down per maturity bucket → SHY/IEF/TLT), ETF yields from holdings (iShares files). Credit carry: HY OAS vs IG OAS (have). Commodity carry: futures curve — NOT stored (IBKR). FX carry: short rates by country — not stored (FRED has them; single-currency ETFs are illiquid). Equity carry: dividend yield vs rate (have dividends).
- **Individual fit**: Bond and credit carry are tradeable in 4–6 ETFs; commodity carry needs futures data and is hard in ETFs (USO/UNG embed the roll); FX carry is practically out of scope for an individual via ETFs.
- **Decoys / overlap**: Duration beta (bond carry = long duration most of the time); credit beta; overlaps credit_spread_timing and bond_curve_timing.
- **Verdict**: Promising (bond + credit legs), Out of scope for FX/commodity legs — Needs data (futures curves via IBKR).

### commodity_term_structure_roll — Commodity basis / roll yield (backwardation long, contango avoid)
- **Thesis**: Commodities in backwardation earn the roll; those in steep contango (USO 2009–2015, UNG almost always) bleed it; hold backwardated commodity ETFs, avoid or short contango ones.
- **Mechanism**: Hedging pressure (producers short the curve) and storage costs; passive long-only index investors (GSCI/BCOM trackers) are forced to roll long front contracts regardless of curve shape.
- **Persistence**: Index-tracker mandates and the ETF structure itself (USO/UNG must roll) keep the pressure; retail keeps buying UNG for "natural gas exposure".
- **Rule (source's own)**: Gorton-Hayashi-Rouwenhorst (2013 RF): sort on basis (front vs next contract), monthly; high-basis minus low-basis ~10%/yr, Sharpe ~0.5 1969–2006 (not verified). Boons & Prado (2019 JF, "Basis-momentum"): difference between front and second-contract momentum, Sharpe ~0.9 (not verified). Simpler ETF form: avoid single-commodity ETFs whose annualised roll cost > X%; prefer optimised-roll products (PDBC, USCI, COMT).
- **Evidence**: UNG lost >95% since 2007 inception while spot gas is roughly flat — the clearest roll-yield decay in any ETF. USO's 2020 forced roll (April negative WTI) is the extreme. Academic basis sorts hold out of sample (Bakshi-Gao-Rossi 2019 three-factor commodity model: basis, momentum, average factor — not verified in this pass).
- **Sources**: Gorton, Hayashi, Rouwenhorst 2013 Review of Finance "The fundamentals of commodity futures returns"; Boons & Prado 2019 JF "Basis-momentum"; Bakshi, Gao, Rossi 2019 Management Science; Koijen et al. 2018 (commodity carry leg).
- **Horizon / schedule**: 21 sessions; month_end (roll dates monthly).
- **Data needed**: Futures curve per commodity — NOT stored; needs IBKR futures (ADR 0026 read-only is fine) or CME settlement scraping. A weaker proxy: ETF price vs spot (FRED DCOILWTICO, Henry Hub) gives realised roll yield after the fact, not ahead.
- **Individual fit**: Long/avoid in 5–8 ETFs; shorting UNG/USO is possible but borrow and tail risk are real; "do not hold contango ETFs" is a free, defensive rule.
- **Decoys / overlap**: Commodity beta and the 2000s supercycle; overlaps commodity_momentum and carry.
- **Verdict**: Promising — Needs data (futures curves). Defensive sub-rule ("never hold UNG/USO as a trend position without checking roll") is Ready.

### commodity_momentum_etf — Commodity cross-sectional and time-series momentum
- **Thesis**: Commodities that rose over 12 months keep rising; those that fell keep falling.
- **Mechanism**: Inventory dynamics (low inventories → backwardation and rising prices persist), hedger pressure, slow supply response.
- **Persistence**: Few natural arbitrageurs; high vol; commodity crashes (2008, 2014–15, 2020) deter capital.
- **Rule (source's own)**: Miffre & Rallis (2007 JBF): 1–12 month formation, 1–12 month hold, long top / short bottom of ~31 futures, 1979–2004, up to ~9.4%/yr (not verified). Fuertes-Miffre-Rallis combine momentum + term structure.
- **Evidence**: Strong pre-2008; weak 2010–2020 (long sideways commodities), strong 2021–22. Baltussen et al. 2021 trend in commodities positive since 1800 (seasonality too).
- **Sources**: Miffre & Rallis 2007; Fuertes, Miffre, Rallis 2010 JBF; Bakshi, Gao, Rossi 2019; Baltussen et al. 2021.
- **Horizon / schedule**: 21 sessions; month_end.
- **Data needed**: Single-commodity ETFs: GLD SLV PPLT PALL USO BNO UNG UGA CPER DBB DBA CORN WEAT SOYB CANE — ~15 names, enough for a cross-section; their roll drag contaminates the signal (use futures via IBKR for a clean test).
- **Individual fit**: Long-only top-3 of 15 with cash filter; some ETFs thin (CANE, SOYB); K-1 tax forms on many.
- **Decoys / overlap**: Energy beta; overlaps tsmom and term structure; cross-sectional momentum already filed for stocks (this is a different asset class, propose as variant).
- **Verdict**: Promising — Needs data (futures curves preferred; ETF-only version Ready after backfill).

### credit_spread_trend — HY vs IG / Treasuries timing by spread trend
- **Thesis**: Hold HYG/JNK when HY OAS is falling (or HYG is above its 10-month SMA / trailing excess return positive); switch to IEF/LQD when spreads are widening.
- **Mechanism**: Credit cycles are slow (default waves take quarters); fund flows and dealer balance-sheet constraints make HY trends persistent; HY total return is "equity beta with a coupon" and trends like equities.
- **Persistence**: Negative convexity of credit (small coupon, big crash) makes buy-and-hold holders slow to react; regulated investors downgrade-sell.
- **Rule (source's own)**: Practitioner (Alpha Architect / Faber-style): monthly, HY index vs 10-month SMA or 12-month excess return > 0 → long HY, else Treasuries. Academic: Jostova et al. (2013 RFS, "Momentum in corporate bond returns") find momentum in non-investment-grade bonds only (long-short ~1.9%/month HY, not verified).
- **Evidence**: HY trend rules cut 2008 (HY −26%) and 2015–16 energy drawdowns in backtests, cost whipsaw 2011/2018/2020 (fast V). Our search for the specific Alpha Architect HY-trend study hit the budget cap — numbers not verified.
- **Sources**: Jostova, Nikolova, Philipov, Stahel 2013 RFS; Faber 2013 (GTAA incl. credit); Alpha Architect trend-following-in-HY posts (not fetched).
- **Horizon / schedule**: 21 sessions; month_end; or every_session on BAMLH0A0HYM2 crossing its 50/200-day average.
- **Data needed**: BAMLH0A0HYM2, BAMLC0A0CM, BAA10Y (have, personal licence); HYG/JNK/LQD/IEF bars (post-backfill); HYG dividends for total return (have).
- **Individual fit**: 2–3 ETFs, a few trades/yr; HY ETF spreads fine.
- **Decoys / overlap**: Equity beta (HYG ~0.7 correlation with SPY); duration; overlaps tsmom (HYG is one of its assets) and regime label (market_stress uses spreads).
- **Verdict**: Promising — Ready (FRED series have long history; ETF bars after backfill).

### bond_curve_timing — Duration timing from term spread / curve steepness and carry+roll
- **Thesis**: Extend duration (TLT vs SHY) when the term spread and roll-down are high and the bond trend is up; shorten when the curve is flat/inverted and trend is down.
- **Mechanism**: Term premium varies with inflation uncertainty and supply; investors anchor on the level of yields; the Fed's reaction function is slow.
- **Persistence**: Bond timing by valuation alone has repeatedly failed; the surviving version is carry + trend combined (Ilmanen), which few bond mandates can run (benchmark duration constraints).
- **Rule (source's own)**: Ilmanen ("Expected Returns", ch. 9; AQR bond timing notes): monthly, duration overweight when (yield curve slope + roll-down) > 0 and 12-month bond excess return > 0; Fama-Bliss / Campbell-Shiller: term spread predicts excess bond returns with R² ~5–15% at annual horizons (not verified).
- **Evidence**: Thornton & Valente (RFS 2012): forward-rate / Cochrane-Piazzesi predictability generates no systematic economic value out of sample and deteriorates over time. Carry+trend on bonds (Koijen et al., Baltussen et al.) holds; pure slope timing does not. 2022: curve flattened and trend turned down together — the combo sidestepped TLT's −31%.
- **Sources**: Thornton & Valente 2012 RFS 25(10) 3141–3168; Cochrane & Piazzesi 2005 AER; Ilmanen 2011 "Expected Returns"; Koijen et al. 2018 (bond carry).
- **Horizon / schedule**: 21 sessions; month_end.
- **Data needed**: `rates/treasury` daily par curve (have, long history), T10Y2Y/T10Y3M (have); TLT/IEF/SHY bars post-backfill.
- **Individual fit**: 3 ETFs; trivial costs; long-only via duration choice.
- **Decoys / overlap**: Falling-rate secular beta 1982–2020; overlaps carry and tsmom.
- **Verdict**: Promising (carry+trend), Dead (slope-only / CP factor) — Ready.

### vol_managed_equity — Volatility-managed / volatility-targeted equity exposure
- **Thesis**: Scale SPY exposure inversely to last month's realised variance (or to a 10% vol target); you get the same return with less risk because volatility spikes are not matched by higher expected returns.
- **Mechanism**: Leverage effect and vol clustering: after a shock, vol stays high for weeks but the expected return does not rise proportionally; leverage-constrained investors cannot lever up in calm times.
- **Persistence**: Needs leverage in calm regimes (retail/institutions constrained), and the unlevered version is just "de-risk after crashes", which costs the rebound.
- **Rule (source's own)**: Moreira & Muir (JF 2017): weight_t = c / RV²_{t−1} (previous month's realised variance), monthly; large alphas and Sharpe gains on market, value, momentum, profitability, investment, carry. Harvey et al. (JPM 2018): 10% vol target, 60+ assets since 1926; US equity Sharpe 0.40 → ~0.48–0.51; negligible for bonds, FX, commodities; cuts left tails everywhere.
- **Evidence**: Cederburg-O'Doherty-Wang-Yan (JFE 2020): across 103 equity strategies, vol-managed versions do not systematically beat unmanaged in direct comparison; alphas come from spanning regressions not implementable in real time; real-time versions earn lower CE and Sharpe; the exceptions are momentum, profitability and BAB. Barroso & Detzel: does not survive transaction costs for most factors. Verdict for an individual: a *vol target* (not inverse-variance) applied to equity beta is a real risk-management improvement, not alpha.
- **Sources**: Moreira & Muir 2017 JF (NBER w22208, https://www.nber.org/papers/w22208); Cederburg, O'Doherty, Wang, Yan 2020 JFE (https://www.lehigh.edu/~xuy219/research/COWY.pdf); Harvey et al. 2018 JPM 45(1) 14–33; Alpha Architect summary (https://alphaarchitect.com/does-portfolio-timing-based-on-volatility-signals-outperform-buy-and-hold/).
- **Horizon / schedule**: 21 sessions; month_end (or weekly).
- **Data needed**: SPY bars (realised vol), our SPY IV30 (implied alternative); have.
- **Individual fit**: Long-only, cap weight at 100% (no leverage) → mostly a de-risking rule; cheap.
- **Decoys / overlap**: Overlaps regime label (market_stress) and the VIX timing idea; decoy: looks like alpha in spanning regressions, isn't in direct comparison.
- **Verdict**: Weak as alpha, Promising as position sizing for every other edge in this family — Ready.

### risk_parity_etf — Risk parity (equal risk contribution) as the base allocation
- **Thesis**: Weight stocks, bonds, commodities (and gold) by inverse volatility rather than capital; the diversified portfolio has a higher Sharpe than 60/40, which leverage-constrained investors cannot capture, so they overweight equities.
- **Mechanism**: Leverage aversion (Asness-Frazzini-Pedersen 2012 FAJ): investors who cannot lever buy high-beta assets; the low-beta (bond) leg is under-priced.
- **Persistence**: Requires leverage to match equity returns; 2022 showed stocks and bonds falling together (RPAR −23%, not verified), after which inflows reversed.
- **Rule (source's own)**: AFP 2012: inverse 36-month vol weights, monthly, levered to market vol; 1926–2010 Sharpe above 60/40 (not verified). Unlevered ETF: RPAR, or DIY SPY/TLT/GLD/DBC.
- **Evidence**: Strong 1980–2020 (secular bond bull); 2022 the worst year since inception for most RP funds; stock-bond correlation turned positive in inflationary regimes (2021–23), which is the failure mode. Not alpha for us; a benchmark/construction choice.
- **Sources**: Asness, Frazzini, Pedersen 2012 FAJ "Leverage aversion and risk parity"; Ilmanen 2011; Harvey et al. 2018 (vol targeting on RP).
- **Horizon / schedule**: 63 sessions; month_end.
- **Data needed**: 4–6 ETF bars; have.
- **Individual fit**: Fine unlevered; leverage via margin is the constraint.
- **Decoys / overlap**: Falling rates 1982–2020; overlaps vol_managed_equity and the stock-bond correlation regime idea.
- **Verdict**: Weak as an edge (it is a portfolio construction, and its key assumption broke in 2022) — Out of scope as an edge; use as a benchmark.

### sector_momentum_rotation — Sector ETF relative-strength rotation
- **Thesis**: Hold the top 3 of 10–11 sector ETFs by 12-month return, monthly; add a trend filter to go to cash.
- **Mechanism**: Industry momentum (Moskowitz-Grinblatt 1999) from slow diffusion of industry-level news; factor momentum (Arnott et al.) and analysts' slow revisions.
- **Persistence**: Weak: sector ETFs are the most liquid vehicles on earth; the effect has largely gone.
- **Rule (source's own)**: Faber 2010 "Relative strength strategies for investing": 10 French industries 1928–2009, top 3 by 12-month return, monthly: 13.9%/yr vs ~10% buy-and-hold, vol 18.4%, Sharpe 0.54, max DD −46%; with a 10-month SMA filter the drawdown falls (not verified). Moskowitz-Grinblatt 1999: industry momentum ~0.43%/month long-short 1963–1995 (not verified).
- **Evidence**: Post-2000 in ETFs: Du, Denning & Zhao 2014 find no sector-ETF momentum; Tse 2015 finds no significant relative-strength returns in sector ETFs; Andreu, Swinkels & Tjong-A-Tjoe 2013: ~5%/yr in country and sector ETFs but not statistically different from zero. Grobys & Kolari 2020 still find long-short industry momentum in indices. Turnover 100–400%/yr.
- **Sources**: Moskowitz & Grinblatt 1999 JF "Do industries explain momentum?"; Faber 2010 SSRN 1585517; Quantpedia summary (https://quantpedia.com/strategies/sector-momentum-rotational-system); Larsen 2020 review (https://osuva.uwasa.fi/bitstream/10024/11076/3/UVA_2020_Larsen_Elias.pdf.txt); Arnott, Clements, Kalesnik, Linnainmaa 2021 "Factor momentum".
- **Horizon / schedule**: 21 sessions; month_end.
- **Data needed**: 11 SPDR sector ETFs (XLRE/XLC short history), post-backfill; our `relative_strength@v1` already computes sector RS.
- **Individual fit**: 3 ETFs, monthly; cheap; long-only.
- **Decoys / overlap**: Tech beta 2010–2024 (any 12-month rank bought XLK); overlaps filed 12-1 momentum (sector aggregate of it) — propose only as a variant.
- **Verdict**: Decayed (ETF era) — Ready after backfill; low priority.

### country_momentum_etf — Country ETF momentum (relative + absolute)
- **Thesis**: Hold the top-quartile country ETFs by 12-month return among ~25–40 iShares single-country funds, with an absolute-momentum filter.
- **Mechanism**: Country-level news (policy, currency, commodity exposure) diffuses slowly; home bias and benchmark hugging stop global allocators from chasing.
- **Persistence**: Moderate: country index momentum has held longer than sector momentum, but ETF liquidity outside the top 10 is thin and tracking is noisy.
- **Rule (source's own)**: Asness-Moskowitz-Pedersen (JF 2013, "Value and momentum everywhere"): 12-2 month return, monthly, 18 country indices: momentum Sharpe ~0.5–0.6 and value+momentum combo higher (not verified). Zaremba (various 2015–2020): country momentum present in 70+ markets but weaker and partly explained by size/liquidity.
- **Evidence**: Andreu et al. 2013 ~5%/yr in country ETFs, not significant. US dominance 2010–2024 made "momentum" = "overweight US". Strong 2025 (ex-US outperformance) — too recent to count.
- **Sources**: Asness, Moskowitz, Pedersen 2013 JF; Andreu, Swinkels, Tjong-A-Tjoe 2013 "Can ETFs be used to exploit country and industry momentum?"; Zaremba & Shemer "Country asset allocation" (2017 book).
- **Horizon / schedule**: 21 sessions; month_end.
- **Data needed**: ~30 country ETFs (listed; have post-backfill); FX exposure implicit in USD ETFs.
- **Individual fit**: Top 5 of 30, monthly; some ETFs have 10–20 bp spreads; long-only.
- **Decoys / overlap**: Dollar regime (strong dollar = US wins); overlaps dual momentum and 12-1 filed momentum (variant).
- **Verdict**: Weak-to-Promising — Ready after backfill; combine with country value (below) per AMP 2013.

### country_cape_value — Country rotation on CAPE (Shiller P/E10)
- **Thesis**: Buy the cheapest quartile of country equity markets by CAPE, rebalance annually; cheap markets outperform expensive ones over 3–10 years.
- **Mechanism**: Extrapolation of recent growth; capital flight from markets after bad decades (institutions cut allocations at the bottom).
- **Persistence**: Very slow (years), high tracking error vs ACWI, concentrates in disliked markets (Russia, Turkey, Brazil, Greece) — career risk nobody wants.
- **Rule (source's own)**: Faber (2012 SSRN "Global value" / 2014 book): equal-weight cheapest 25% (or third) of 32–44 countries by CAPE, annual rebalance, 1980–2013: cheapest third beat the equal-weight benchmark by ~4–7%/yr (1980–2011 version), gross of costs.
- **Evidence**: In-sample only (CXO: small samples, in-sample thresholds, no frictions). Live: GVAL (Cambria, launched 2014) lagged ACWI badly until 2022, recovered 2023–25 (track record not verified here). Research Affiliates' and Barclays' CAPE-based expected-return models have had the right sign for 10-year returns but no short-horizon timing power. Russia 2022 (cheapest market → zero) is the tail.
- **Sources**: Faber 2012 SSRN 2129474; Faber 2014 "Global Value"; CXO review (https://www.cxoadvisory.com/fundamental-valuation/a-few-notes-on-global-value); Research Affiliates Asset Allocation Interactive (CAPE by country, monthly).
- **Horizon / schedule**: 252 sessions; month_end check, annual rebalance.
- **Data needed**: Country CAPE — NOT stored (Barclays Indices / Research Affiliates / Siblis publish monthly; scrapeable); country ETF bars.
- **Individual fit**: 8–10 ETFs, annual; cheap; long-only; needs patience measured in years.
- **Decoys / overlap**: EM beta and commodity beta (cheap countries are commodity exporters); dollar regime; overlaps country momentum.
- **Verdict**: Weak (horizon too long for our harness's 40-event bar: ~45 annual events over 1980–2025 in-sample only) — Needs data (country CAPE).

### erp_timing_cape — Equity risk premium timing by CAPE / cross-asset valuation
- **Thesis**: Reduce equity exposure when CAPE (or the equity yield minus real bond yield) is in its top decile; raise it when cheap.
- **Mechanism**: Extrapolative expectations; mean reversion of valuation over 10 years.
- **Persistence**: Works only over very long horizons; the signal said "expensive" for most of 1992–2025.
- **Rule (source's own)**: Campbell & Shiller (1998): CAPE predicts 10-year real returns, R² ~0.3–0.4 in-sample. Asness-Ilmanen-Maloney (2017 JPM "Market timing: sin a little"): value timing alone is weak out of sample; combining value and momentum timing, scaled modestly, adds a little (Sharpe improvement small, not verified).
- **Evidence**: Goyal & Welch (2008 RFS) and Goyal, Welch & Zafirov (2024 RFS, "A comprehensive 2022 look at the empirical performance of equity premium prediction"): almost no predictor beats the historical mean out of sample at monthly/annual horizons; the few that do are fragile. CAPE-based de-risking since 1995 cost enormous return.
- **Sources**: Campbell & Shiller 1998 JPM; Goyal & Welch 2008 RFS; Goyal, Welch, Zafirov 2024 RFS; Asness, Ilmanen, Maloney 2017 JPM.
- **Horizon / schedule**: 252+ sessions; month_end.
- **Data needed**: Shiller CAPE (public monthly; addable as a published series), DFII10 (have) for the excess-CAPE yield.
- **Individual fit**: One knob on equity weight; trivial.
- **Decoys / overlap**: Overlaps absolute momentum (the "sin a little" combo = value + trend); fails the ≥40-independent-events bar (10-year horizon → ~3 independent events since 1990).
- **Verdict**: Dead as a timing edge; Weak as a slow tilt — Out of scope (horizon), keep as a regime conditioner.

### yield_curve_inversion_equity — Yield-curve inversion / re-steepening as an equity de-risk trigger
- **Thesis**: After the 10y–3m (or 10y–2y) spread has been inverted for a month, and especially when it re-steepens from inversion, cut equity exposure; recessions and bear markets follow 6–18 months later.
- **Mechanism**: Bank lending margins compress; the Fed is late; the signal is widely known but acting on it costs 6–18 months of bull market, which institutions cannot afford.
- **Persistence**: The lag is the moat: 1998, 2006–07 and 2019 inversions all preceded 12+ months of gains first. 2022–24: two years inverted, no recession, S&P +50%.
- **Rule (source's own)**: Estrella & Mishkin (1998 REStat): probit on 10y–3m predicts recession 12 months ahead; Resnick & Shoesmith (2002 FAJ): switch from stocks to bills when the spread falls below ~1% (not verified) — beat buy-and-hold 1970–1999 in-sample.
- **Evidence**: Our own card already records the record: 7 of 8 recessions since 1969 with false alarms 1998 and 2022–24. Equity timing on the inversion alone underperforms buy-and-hold since 1990 (the 2022–24 miss is decisive); the re-steepening-from-inversion variant has ~8 events since 1970 — too few.
- **Sources**: Estrella & Mishkin 1998; Resnick & Shoesmith 2002 FAJ "Using the yield curve to time the stock market"; our `config/site/regime/cards.toml` curve_10y3m card and links.
- **Horizon / schedule**: 126–252 sessions; every_session (slow).
- **Data needed**: T10Y3M, T10Y2Y (have, 1976–); `regime_indicators@v1.curve_10y3m` (have).
- **Individual fit**: Trivial.
- **Decoys / overlap**: Already inside `regime@v3` (macro_early tier); fails the 40-events bar (8 inversions).
- **Verdict**: Weak as a standalone trade — Ready as a regime conditioner only (no separate edge document).

### macro_regime_conditioner — Macro-regime gating of risk (our regime label; NFCI / FCI / EBP / Sahm)
- **Thesis**: Not an edge in itself: when the composite regime label says "stress" (credit spreads widening + breadth falling + financial conditions tightening), every long-equity edge in the catalogue has lower hit rates; use the label as a gate or size multiplier.
- **Mechanism**: Financial-conditions indices and the excess bond premium (Gilchrist-Zakrajšek 2012) carry forward-looking information on credit supply; equity drawdowns cluster in those states.
- **Persistence**: Combination signals are too slow and too "obvious" for fast money, and too complex for allocation committees; the information is cheap but acting on it is lumpy.
- **Rule (source's own)**: Gilchrist & Zakrajšek (2012 AER): EBP predicts real activity 12 months ahead; Adrian-Boyarchenko-Giannone (2019 AER, "Vulnerable growth"): NFCI tightening shifts the left tail of GDP growth — not equity timing rules. Equity timing on NFCI has no clean published out-of-sample result we could verify (search budget exhausted).
- **Evidence**: As a conditioner for trend/momentum: momentum crashes happen when market stress is high and reversing (Daniel & Moskowitz 2016 JFE), and vol management helps momentum (Cederburg et al. exception) — i.e., regime-gating momentum is the one well-evidenced conditional effect.
- **Sources**: Gilchrist & Zakrajšek 2012 AER; Adrian, Boyarchenko, Giannone 2019 AER; Daniel & Moskowitz 2016 JFE "Momentum crashes"; our `regime@v3` and `market_macro@v3`.
- **Horizon / schedule**: 21 sessions; every_session (label), used on_event:regime_change.
- **Data needed**: Have: NFCI, EBP, OFR FSI, ICSA, unemployment, spreads, breadth, regime label with `*_changed` flags.
- **Individual fit**: Free.
- **Decoys / overlap**: Everything; this is the shared conditioner for the whole family and for the filed 12-1 momentum edge.
- **Verdict**: Promising (as a conditioner; run the harness's lift tests split by regime for each edge) — Ready.

### breadth_thrust_entry — Breadth thrust / washout-recovery as an equity entry signal
- **Thesis**: When the 10-day average of advancing-issue share jumps from <40% to >61.5% within 10 sessions (Zweig Breadth Thrust), or ≥90% up-volume days cluster after a washout, equities are higher 6–12 months later.
- **Mechanism**: Forced short covering and under-invested institutions re-entering after capitulation; the start of a new trend from a liquidity bottom.
- **Persistence**: Rare (≈16 since 1950 by one count, 6 since 2010 on a broad universe); too infrequent to arbitrage.
- **Rule (source's own)**: Zweig (1986): 10-day EMA of advances/(advances+declines) from <0.40 to >0.615 within 10 days. Variants: Whaley/Lowry 90% up-days; Deemer "breakaway momentum".
- **Evidence**: thetrading.tools: 6 thrusts since 2010, S&P 500 higher 12 months later in all 6, mean +14.9%; one −4.6% at 3 months. SentimentTrader: the 61.5% threshold was chosen to exclude failures; at 60% returns deteriorate; 59.3% "almost" thrusts give good-not-great results; sample sizes too small. Forward returns after any strong rally are positive on average anyway (decoy).
- **Sources**: Zweig 1986 "Winning on Wall Street"; SentimentTrader (https://sentimentrader.com/blog/a-breadth-thrust-that-wasnt, https://sentimentrader.com/blog/zweig-breadth-thrust-recovery); thetrading.tools (https://www.thetrading.tools/concepts/zweig-breadth-thrust).
- **Horizon / schedule**: 126 sessions; on_event:breadth_thrust (known at that session's close, act next open).
- **Data needed**: `market_breadth@v1` (universe advances/declines — close to NYSE but thresholds were tuned to NYSE issues; recalibrate); IDX:SPX history for pre-2024 events.
- **Individual fit**: One SPY entry a few times per decade.
- **Decoys / overlap**: Momentum after a rally; fails the 40-events bar unless the threshold is loosened (and then the edge weakens); overlaps regime label (breadth component).
- **Verdict**: Weak (too few events, threshold-fitted) — Ready to test as a *loosened* breadth-recovery rule with ≥40 events; the strict ZBT is Rejected as an edge.

### vix_mean_reversion_entry — VIX spike / IV term-structure inversion as an equity entry
- **Thesis**: When SPY 30-day IV (or VIX) spikes above ~30–35 and the IV term structure inverts (1-month > 3-month), buying equities earns above-average 1–3 month returns; conversely very low VIX has no timing value.
- **Mechanism**: Vol spikes are forced de-risking (vol-target funds, dealers' gamma, margin calls) that overshoot; the variance risk premium is at its widest.
- **Persistence**: Catching the knife is psychologically hard and the distribution is bimodal (2008 and 2020 kept spiking); institutions are de-risking under rules at exactly this point.
- **Rule (source's own)**: Practitioner studies (e.g., Johnson 2017 JFQA "Risk premia and the VIX term structure": slope predicts VIX futures returns; Cboe / SentimentTrader VIX>30 tables) — the equity-timing version is practitioner, not academic: buy SPY when VIX > 30 and VIX/VIX3M > 1; hold 21–63 sessions.
- **Evidence**: Hit rates ~65–75% at 3 months for VIX>30 entries since 1990 in various practitioner tables (not verified; ~20–30 clusters of events, autocorrelated). Moreira-Muir says the opposite about vol (reduce exposure when vol is high) — the reconciliation is horizon: next month is worse, 3–12 months better (mean reversion). Decoy: mean reversion of equity returns after any −10% drawdown.
- **Sources**: Johnson 2017 JFQA; Cheng 2019 RFS "The VIX premium"; Moreira & Muir 2017; practitioner tables (SentimentTrader).
- **Horizon / schedule**: 63 sessions; on_event:vix_spike.
- **Data needed**: Our SPY IV30 and `iv_term@v1` (have, but only from 2024-10); FRED VIXCLS / VIX3M addable (1990–) for history.
- **Individual fit**: Occasional SPY add; fine.
- **Decoys / overlap**: Overlaps vol_managed_equity (opposite sign, different horizon) and filed VRP short-puts edge (same event, different instrument). Event count borderline (~25 independent spikes 1990–2025).
- **Verdict**: Promising but event-starved — Needs data (VIXCLS, VIX3M as published series).

### cross_asset_tsmom_bonds_to_equities — Bond returns lead equity returns (cross-asset time-series momentum)
- **Thesis**: Past 12-month bond-market returns positively predict next-month equity returns; past equity returns negatively predict bond returns; a cross-asset TSMOM portfolio beats plain TSMOM.
- **Mechanism**: Slow-moving capital across bond and equity markets (Pitkäjärvi-Suominen-Vaittinen): a bond rally lowers discount rates but equities incorporate it with a lag.
- **Persistence**: Published 2020 in JFE; too slow and too macro for fast money; plausible decay post-publication (not yet measured).
- **Rule (source's own)**: PSV (JFE 2020): 20 countries; signals = sign of trailing 12-month bond and equity index returns; monthly; the diversified cross-asset TSMOM portfolio has a Sharpe 45% higher than standard TSMOM (absolute Sharpe not shown in the abstract).
- **Evidence**: In-sample 1980–2016 (not verified); 2022 (bonds down then stocks down) fits; 2023–24 (bonds flat/down, stocks up) does not. No independent replication found in this pass.
- **Sources**: Pitkäjärvi, Suominen, Vaittinen 2020 JFE 136(1) 63–85 (https://ideas.repec.org/a/eee/jfinec/v136y2020i1p63-85.html).
- **Horizon / schedule**: 21 sessions; month_end.
- **Data needed**: IEF/TLT/AGG and SPY/VEA/VWO total returns (have post-backfill; bond index history via FRED/rates for pre-ETF).
- **Individual fit**: Overlay on the TSMOM ETF book; trivial.
- **Decoys / overlap**: Falling-rates beta; overlaps tsmom_multi_asset_etf (file as its variant).
- **Verdict**: Promising — Ready after backfill (as a tsmom variant).

### oil_shock_equity_lag — Oil price changes predict equity returns (Striking Oil) and oil-sensitive industries
- **Thesis**: A monthly oil price rise predicts lower next-month equity returns (and vice versa); the effect is strongest in oil-consuming industries (airlines, transports, autos).
- **Mechanism**: Investors under-react to oil's macro implications (Driesprong-Jacobsen-Maat 2008); analysts update industry earnings slowly.
- **Persistence**: Published 2008; the 2010s shale era changed the sign for US equities (oil up = US growth up in 2016–22), so the relationship is unstable — which is also why it is not arbitraged.
- **Rule (source's own)**: DJM (JFE 2008): regress next-month index return on this month's oil change; significant in 12 of 18 developed markets; a timing strategy beat buy-and-hold 1973–2003 (magnitude not verified). Industry version (Hong-Torous-Valkanov 2007 RFS "Do industries lead stock markets?": oil and other industries lead the market by a month).
- **Evidence**: Extensions find predictability for just under a fifth of US industries; Casassus-Higuera: oil the only variable with forecasting power including 2008; 1859–2013 study positive. Post-2008 US market-level predictability likely weak (shale); not independently verified here.
- **Sources**: Driesprong, Jacobsen, Maat 2008 JFE "Striking oil: another puzzle?"; Hong, Torous, Valkanov 2007 RFS; Casassus & Higuera (PUC working paper, https://www.economia.uc.cl/docs/doctra/dt-406.pdf).
- **Horizon / schedule**: 21 sessions; month_end.
- **Data needed**: DCOILWTICO (have; 10-day release lag — use USO/BNO or the EIA daily which FRED posts with lag; be careful with `knowledge_ts`), JETS, IYT, XLE, SPY.
- **Individual fit**: Pairs like long JETS / short XLE after oil drops: shorting optional; fine.
- **Decoys / overlap**: Energy beta; macro regime; the sign flip makes this a Weak standalone.
- **Verdict**: Weak — Ready (data present), low priority; test the industry (airlines/transports) version, not the index version.

### defensive_cyclical_rotation — Defensive vs cyclical sector rotation by regime / growth momentum
- **Thesis**: Overweight cyclicals (XLY XLI XLB XLF, IWM) when leading growth indicators (ISM new orders, claims trend, credit spreads) improve, defensives (XLP XLU XLV) when they deteriorate.
- **Mechanism**: Earnings cyclicality plus slow macro diffusion; sector allocators move after the data confirms.
- **Persistence**: Macro data are revised and lagged; the ISM/PMI is public at 10:00 on the first business day — the information is cheap, the discipline is not.
- **Rule (source's own)**: Practitioner (Fidelity "business cycle approach", MSCI cyclical/defensive indices, Goldman/MS PMI-momentum rotation): long cyclicals minus defensives when the 3-month change in ISM manufacturing PMI > 0 (not a published academic rule; magnitudes vary by note, not verified). Academic analogue: Hong-Torous-Valkanov 2007 industry lead-lag; Rapach et al. (2019) industry return predictability.
- **Evidence**: Backtests in sell-side notes show cyclical/defensive relative return correlating ~0.5 with PMI changes contemporaneously; predictive power at 1–3 months is modest and the 2020–24 cycle (ISM < 50 for 26 months while cyclicals rallied) was a clear failure. No independent out-of-sample study verified.
- **Sources**: Fidelity business-cycle sector guides; MSCI cyclical/defensive indices methodology; Hong, Torous, Valkanov 2007 RFS; Rapach, Strauss, Tu, Zhou 2019 "Industry return predictability: a machine learning approach".
- **Horizon / schedule**: 21–63 sessions; on_event:macro_release (ISM, claims; `events/macro_release` with `known_from`).
- **Data needed**: ISM PMI (FRED discontinued ISM series in 2016 — need a published source; `macro.toml` notes ISM "by rule" for the calendar only), ICSA (have), spreads (have), sector ETFs.
- **Individual fit**: Long-only tilt between two sector baskets; cheap.
- **Decoys / overlap**: Rates beta (utilities/staples are bond proxies), tech beta; overlaps sector momentum and regime conditioner.
- **Verdict**: Weak — Needs data (ISM/PMI series); file as a conditioner variant.

### dollar_regime_tilt — Dollar strength regime for EM / commodities / foreign equities
- **Thesis**: When the trade-weighted dollar is trending up, under-weight EM equities (VWO), commodities (DBC) and foreign equities (VEA); when trending down, over-weight them.
- **Mechanism**: Dollar funding and EM external debt (BIS "dollar as a global risk factor"), commodity invoicing in dollars; EM allocators react with a lag.
- **Persistence**: The dollar trend is itself a TSMOM signal; the mapping to EM/commodities is beta-like and widely known; mostly a conditioner.
- **Rule (source's own)**: No single canonical paper; BIS (Avdjiev-Bruno-Koch-Shin 2019) show a broad-dollar appreciation predicts weaker cross-border lending and EM investment; practitioner rules use DXY 12-month trend as a gate on EEM/DBC.
- **Evidence**: 2011–2022 strong dollar coincided with EM/commodity underperformance; 2003–07 and 2017, 2025 the reverse. Predictive (not contemporaneous) tests at 1 month are thin; largely explained by the EM ETF's own trend (decoy).
- **Sources**: Avdjiev, Bruno, Koch, Shin 2019 IMF Econ Review "The dollar exchange rate as a global risk factor"; Lustig, Roussanov, Verdelhan 2014 "Countercyclical currency risk premia" (dollar carry); BIS Quarterly Reviews.
- **Horizon / schedule**: 63 sessions; month_end.
- **Data needed**: DTWEXBGS (FRED broad dollar, addable), UUP bars; VWO/VEA/DBC bars.
- **Individual fit**: Free tilt.
- **Decoys / overlap**: EM/commodity own trend (tsmom); country momentum.
- **Verdict**: Weak standalone, Promising as a conditioner — Ready (add DTWEXBGS).

### copper_gold_yield_lead — Copper/gold ratio as a lead on 10-year yields and cyclicals
- **Thesis**: The copper/gold price ratio tracks (and some claim leads) the 10-year Treasury yield; divergences (ratio falling while yields rise) predict yield declines → long TLT; the ratio also proxies the cyclical/defensive cycle.
- **Mechanism**: Copper = growth demand, gold = real-rate/fear hedge; the ratio summarises global growth expectations faster than official data.
- **Persistence**: Popularised by Gundlach (2017–); a contemporaneous correlation, not a demonstrated lead; mostly a sentiment chart.
- **Rule (source's own)**: Practitioner only: 12-month change in CPER/GLD vs change in DGS10; trade the divergence. No academic paper with an out-of-sample test found; search budget exhausted before verifying any formal study.
- **Evidence**: High level correlation 2010–2021 (~0.8 in charts), broke in 2022–25 (gold rallied with yields rising and copper flat; ratio fell to multi-decade lows while 10y stayed ~4%+). Classic non-stationary-levels correlation.
- **Sources**: DoubleLine webcasts (Gundlach, 2017–2023); practitioner charts; no peer-reviewed source identified.
- **Horizon / schedule**: 63 sessions; month_end.
- **Data needed**: CPER, GLD bars; DGS10 (have); PCOPPUSDM / gold spot addable from FRED.
- **Individual fit**: TLT/SHY switch; trivial.
- **Decoys / overlap**: Bond trend (tsmom on TLT); dollar regime; macro conditioner.
- **Verdict**: Dead as an edge (no lead, broke 2022–25) — Rejected after this entry; keep only as a Guide chart if ever shown.

### fed_net_liquidity_equity — Fed net liquidity (balance sheet − TGA − RRP) driving equities
- **Thesis**: Changes in net liquidity lead the S&P 500 by weeks; buy when net liquidity rises, sell when it falls.
- **Mechanism**: Reserves and money-market balances flow into risk assets; QE/QT and Treasury cash-balance swings change system liquidity.
- **Persistence**: None demonstrated; the claim rests on the 2020–22 window.
- **Rule (source's own)**: Practitioner (Howell / Crossborder Capital, RIA, TradingView indicators): NL = WALCL − WTREGEN − RRPONTSYD weekly; trade the 4–8 week change.
- **Evidence**: eco3min (data to Mar 2026): net liquidity flat (+$0.06T) Sep 2022 – Mar 2026 while the S&P 500 rose 73%; rolling 52-week correlation peaked mid-2021, negative since mid-2025; 2023–24 correlation effectively zero; author's conclusion: a plumbing diagnostic, not a timing indicator. The 2022 forecasts built on it ("S&P 3,500 by year-end") failed. No formal out-of-sample study exists.
- **Sources**: eco3min net liquidity dataset (https://eco3min.fr/en/net-liquidity-index-dataset/); Advisor Perspectives 2022 (https://www.advisorperspectives.com/articles/2022/08/17/s-p-3-500-by-year-end) and 2024 (https://www.advisorperspectives.com/articles/2024/12/09/frontrunning-fed-liquidity-worth-watching).
- **Horizon / schedule**: 21 sessions; weekly (Thursday H.4.1 release).
- **Data needed**: WALCL, WTREGEN (addable), RRPONTSYD (have).
- **Individual fit**: Trivial.
- **Decoys / overlap**: Post-2009 equity bull coincident with QE; regime conditioner.
- **Verdict**: Dead — Rejected; do not re-research. (Keep RRP/TGA only as macro context.)

### betting_against_correlation_etf — Betting against correlation / low-risk via ETFs
- **Thesis**: Low-correlation (and low-beta) assets earn higher risk-adjusted returns because leverage-constrained investors overpay for high-beta exposure; in ETF form: overweight low-beta sectors/factor ETFs (USMV, SPLV, XLP, XLU) levered to market beta, or simply hold them unlevered for a higher Sharpe.
- **Mechanism**: Leverage constraints (Frazzini-Pedersen BAB; Asness et al. BAC separates the correlation channel from the volatility channel, supporting the leverage story).
- **Persistence**: Needs leverage to convert Sharpe into return; the unlevered low-vol ETF lags in bull markets (2013–21), which drives outflows and resets the premium.
- **Rule (source's own)**: Asness, Frazzini, Gormsen, Pedersen (JFE 2020): BAC = long low-correlation, short high-correlation stocks within vol-matched groups, beta-neutral; strong in the US and internationally (Sharpe not extracted in this pass). Frazzini-Pedersen 2014 BAB Sharpe ~0.78 US 1926–2012 (from memory, not verified).
- **Evidence**: Low-vol ETFs (USMV since 2011) delivered lower vol and roughly market Sharpe, below-market return; crowding concerns 2016 and 2019–20 (low vol fell with the market in March 2020). Novy-Marx & Velikov (2022) argue BAB's performance is partly a construction artefact.
- **Sources**: Asness, Frazzini, Gormsen, Pedersen 2020 JFE (https://www.aqr.com/Insights/Perspectives/Betting-Against-Correlation); Frazzini & Pedersen 2014 JFE "Betting against beta"; Novy-Marx & Velikov 2022 "Betting against betting against beta"; Alpha Architect summary (https://alphaarchitect.com/low-volatility-investing-insight-bet-against-correlation/).
- **Horizon / schedule**: 63 sessions; month_end.
- **Data needed**: Stock-level betas/correlations vs SPY from bars (have); ETF holdings for sector/factor ETFs.
- **Individual fit**: Long-only low-vol tilt is cheap; the levered long-short is not practical for an individual.
- **Decoys / overlap**: Rates beta (low-vol = bond proxies), value tilt; this is a stock-selection factor more than a macro edge — likely covered by another family (cross-sectional factors). Propose only the ETF-level rotation here.
- **Verdict**: Promising (factor), Out of scope for this family — hand to the cross-sectional-factor family.

### trend_carry_value_combo — Trend + carry + value across asset classes (the diversified "alternative risk premia" book)
- **Thesis**: Combining the three signals within each asset class (equity indices, bonds, commodities, currencies) gives a Sharpe well above any one (they are weakly or negatively correlated: trend and value especially).
- **Mechanism**: Each premium has a different holder of the opposite side (trend: late reactors; carry: crash-averse; value: extrapolators), so losses rarely coincide.
- **Persistence**: Each leg suffers decade-long droughts (value 2010–20, trend 2010s, carry 2008–20); the combo smooths but investors still quit on the worst leg.
- **Rule (source's own)**: Asness-Moskowitz-Pedersen 2013 (value+momentum everywhere: the 50/50 combination across all asset classes has an annual Sharpe of 1.45, 1972-2011 (corrected; was ~1.4 "across 8 markets")); Koijen et al. 2018 (carry+trend); Baltussen et al. 2021 (trend 1.09, carry 1.15, value and seasonality lower, multi-factor higher); Baz et al. 2015 (Man AHL, "Dissecting investment strategies in the cross section and time series"): gross Sharpe 1.40 for the cross-sectional and 1.37 for the time-series book combining carry, momentum and value across equities, rates, FX and commodities, 1.61 for the composite, 1990–2015 (corrected; was ~1.2–1.5; read in CXO's summary of the paper); AQR Style Premia live record: strong 2013–17, −20%+ 2018–20, recovered 2021–24.
- **Evidence**: Out-of-sample 1800–2016 robust (Baltussen); post-2010 live ARP funds disappointed (crowding + the 2018–20 value drawdown), then revived 2021–24. Suhonen-Lennkh-Perez (2017 JPM, "Quantifying backtest overfitting in alternative beta strategies"): across 215 bank strategies the median live Sharpe is 0.31 vs 1.20 backtested, a 73% median haircut, at least 50% in every asset class (corrected; was "~¼–½, ~70%") — the best single number for TAA/ARP decay.
- **Sources**: Asness, Moskowitz, Pedersen 2013 JF 68(3) "Value and Momentum Everywhere" (https://w4.stern.nyu.edu/facdir/lpederse/papers/ValMomEverywhere.pdf); Koijen et al. 2018 JFE; Baltussen, Swinkels, van Vliet 2021 JFE; Baz, Granger, Harvey, Le Roux, Rattray 2015 "Dissecting Investment Strategies in the Cross Section and Time Series" (Man AHL, SSRN 2695101, https://papers.ssrn.com/abstract=2695101; read via CXO https://www.cxoadvisory.com/value-premium/when-carry-momentum-and-value-work); Suhonen, Lennkh, Perez 2017 JPM 43(2) "Quantifying Backtest Overfitting in Alternative Beta Strategies" (read via CXO https://www.cxoadvisory.com/big-ideas/live-performance-of-alternative-beta-products/).
- **Horizon / schedule**: 21 sessions; month_end.
- **Data needed**: Trend: bars (have post-backfill). Carry: curve (have), futures curves (missing). Value: country CAPE (missing), real yields (have), commodity 5-year price ratio (bars).
- **Individual fit**: Long-only version in ~15 ETFs is feasible; the cross-asset short legs are not.
- **Decoys / overlap**: It is the union of tsmom, carry, country value; file as the portfolio-level combination, tested leg by leg.
- **Verdict**: Strong (gross, diversified), Promising (long-only ETF) — Needs data (futures curves, country CAPE) for two of three legs; trend leg Ready after backfill.

### stock_bond_correlation_regime — Inflation regime / stock-bond correlation as a hedging and sizing switch
- **Thesis**: When trailing inflation is above ~3% and rising, the stock-bond correlation turns positive and Treasuries stop hedging equities; shift the hedge leg to gold / commodities / trend (DBMF/KMLM) and reduce the bond allocation.
- **Mechanism**: In inflationary regimes the Fed tightens into weakness, so bonds and stocks fall together; in disinflationary regimes growth shocks dominate and they diverge. Allocators calibrate on the last 20 years (negative correlation) and are slow to update.
- **Persistence**: Regime shifts are rare (1960s–90s positive, 2000–20 negative, 2021–23 positive), so the lesson is relearned every generation.
- **Rule (source's own)**: Ilmanen (2003 JFI, "Stock-bond correlations"); Brixton et al. (AQR 2023, "A changing stock-bond correlation"): correlation driven by inflation level/uncertainty and monetary policy; rule-of-thumb switch when trailing 36-month realised correlation > 0 or core CPI > 3%.
- **Evidence**: 2022: 60/40 −17%, risk parity worse; trend +27%, commodities +16%. Historical regimes consistent across 1900–2023 (Ilmanen; Molenaar et al. 2023 "Empirical evidence on the stock-bond correlation", not verified). Only ~3–4 regime changes in 60 years — fails the 40-event bar as an edge; it is a sizing/hedge rule.
- **Sources**: Ilmanen 2003 JFI; Brixton, Brooks, Hecht, Ilmanen, Maloney, McQuinn 2023 (AQR, JPM); Molenaar, Senechal, Swinkels, Wang 2023 (Robeco).
- **Horizon / schedule**: 252 sessions; month_end.
- **Data needed**: CPI (CPIAUCSL via ALFRED — addable with vintages), SPY/TLT bars (correlation), GLD/DBC/DBMF.
- **Individual fit**: One allocation knob.
- **Decoys / overlap**: Risk parity failure mode; macro conditioner.
- **Verdict**: Promising as a conditioner, Out of scope as an edge (too few events) — Ready (add CPI).

### gold_real_rate_trend — Gold vs real yields (and gold trend) as a tactical holding
- **Thesis**: Gold rises when 10-year real yields fall and the dollar weakens; hold GLD when real yields are trending down and GLD is above its 10-month SMA.
- **Mechanism**: Gold is a zero-coupon real asset; its opportunity cost is the real yield; central-bank buying (2022–25) has recently dominated and broken the real-yield link.
- **Persistence**: Gold's 20-year bear (1980–2000) and the 2013 crash deter trend-less holders; the real-yield relationship is widely known but decade-unstable.
- **Rule (source's own)**: Erb & Harvey (2013 FAJ, "The golden dilemma"): gold's real price mean-reverts; no reliable inflation hedge at short horizons; real-yield correlation strong 2006–2021 (~−0.8 in levels, not verified). Trend on gold is part of every TSMOM study (Baltussen: trend positive in commodities incl. gold).
- **Evidence**: 2022–25: real yields rose from −1% to +2% while gold doubled — the real-yield model failed; the trend rule did not.
- **Sources**: Erb & Harvey 2013 FAJ; Baltussen et al. 2021; Hurst-Ooi-Pedersen 2017.
- **Horizon / schedule**: 21 sessions; month_end.
- **Data needed**: DFII10 (have), GLD bars, DTWEXBGS (addable).
- **Individual fit**: One ETF.
- **Decoys / overlap**: tsmom on GLD; the real-yield leg is Dead post-2022.
- **Verdict**: Weak (real-yield model), covered by tsmom (trend) — do not file separately.

### taa_ensemble_and_overfitting_guard — What is known about overfitting in TAA backtests (the meta-edge: ensembles beat the best single rule)
- **Thesis**: Any TAA rule with a chosen lookback, rebalance day and asset list is over-fitted; the robust version is an ensemble across lookbacks (3–12 months), tranches across rebalance days, and parameter-free signals; expect out-of-sample Sharpe ≈ 50–60% of in-sample.
- **Mechanism**: Researchers test many variants and publish the best (Harvey-Liu-Zhu 2016 "… and the cross-section of expected returns": t > 3 needed); strategy decay post-publication averages ~43–58% of Sharpe (Falck-Rej-Thesmar 2021; McLean-Pontiff 2016); bank ARP backtests lose more (Suhonen et al. 2017).
- **Persistence**: Not an edge; a discipline. It is what the harness's frozen period and decile-spread tests exist for.
- **Rule (source's own)**: Bailey-Borwein-Lopez de Prado-Zhu (2014) "Pseudo-mathematics and financial charlatanism" / deflated Sharpe ratio; ReSolve 2019 GEM craftsman ensemble; Zakamulin's bootstrapped out-of-sample SMA tests; Alpha Architect "beware geeks bearing formulas" (rebalance-day luck of several % CAGR, not fetched: 403).
- **Evidence**: GTAA in-sample Sharpe 0.81 → 0.68 OOS (Concretum); GEM returns vary by several % CAGR across rebalance days (ReSolve); DAA's 13612W weight; ZBT's 61.5% threshold. Across our whole family, assume a 40–50% Sharpe haircut and insist on ≥40 independent month-end events per rule.
- **Sources**: Harvey, Liu, Zhu 2016 RFS; McLean & Pontiff 2016 JF; Falck, Rej, Thesmar 2021 (https://arxiv.org/pdf/2105.01380); Bailey, Borwein, Lopez de Prado, Zhu 2014 Notices AMS; Suhonen, Lennkh, Perez 2017 JPM 43(2) (median 73% Sharpe haircut, 1.20 -> 0.31; read via CXO https://www.cxoadvisory.com/big-ideas/live-performance-of-alternative-beta-products/); ReSolve 2019.
- **Horizon / schedule**: n/a (harness policy).
- **Data needed**: none.
- **Individual fit**: n/a.
- **Decoys / overlap**: n/a.
- **Verdict**: Strong as a rule for the harness (every TAA edge is tested as an ensemble, with a deflated Sharpe) — Ready.

---

## Rejected on sight
- **Fed net liquidity timing** — level correlation from one window (2020–22); flat liquidity vs +73% S&P 2022–26; no out-of-sample test exists.
- **Copper/gold ratio → yields** — contemporaneous, non-stationary correlation; broke 2022–25; no lead demonstrated.
- **Strict Zweig Breadth Thrust** — ≤16 events since 1950, threshold chosen to exclude failures; only a loosened breadth-recovery rule is testable.
- **CAPE equity timing (standalone)** — horizon 10 years → ~3 independent events; Goyal-Welch(-Zafirov) show no out-of-sample power at tradeable horizons.
- **Yield-curve inversion as a sell signal** — 8 events, 6–18 month lag, 2022–24 false alarm; already inside `regime@v3` as a conditioner.
- **Cochrane-Piazzesi / forward-rate bond timing** — Thornton & Valente 2012: no economic value out of sample, deteriorating.
- **Risk parity as an edge** — portfolio construction, not alpha; central assumption (negative stock-bond correlation) failed 2022.
- **FX carry via ETFs** — DBV/CEW delisted; single-currency ETFs illiquid; costs exceed the premium for an individual.
- **Sector ETF momentum (as filed)** — three ETF-era studies find nothing significant; only a variant of the filed 12-1 momentum.
- **Gold vs real yields model** — failed 2022–25; the trend leg is already in tsmom.
- **Inverse-variance "volatility-managed" alpha** — Cederburg et al. 2020: not implementable in real time, loses to buy-and-hold in direct comparison except for momentum; keep only vol *targeting* as sizing.
- **ISM/PMI cyclical rotation (standalone)** — 26 months of ISM < 50 (2022–24) with cyclicals rallying; no verified out-of-sample study; ISM series not on FRED since 2016.
- **Leveraged / inverse VIX products as timing vehicles** — product decay (roll, daily reset) swamps any signal; VIX info enters through our own SPY IV instead.
- **Election / presidential-cycle and seasonal (Sell in May) macro timing** — not in this family's brief; seasonality is covered by Baltussen et al. but belongs to the calendar family.

## Notes on verification
First pass: the web search budget (shared across agents) was exhausted after the first 20 queries, so several figures were cited without a source check (unread primary papers or secondary summaries). Verified on 2026-10-17 (pickup-order and Strong ideas; the figures above carry "(verified)" or "(corrected; was ...)"): tsmom_multi_asset_etf: Huang-Li-Wang-Zhou 2020 abstract; trend_carry_value_combo: Asness-Moskowitz-Pedersen all-asset 50/50 Sharpe 1.45 (paper text), Baz et al. 2015 combined gross Sharpe 1.40 / 1.37 / composite 1.61 (CXO summary), Suhonen-Lennkh-Perez median 73% haircut, 1.20 -> 0.31 (CXO summary; also used by taa_ensemble_and_overfitting_guard). Verified in the first pass: Cambridge Associates SG Trend figures (2008 +20.9%, 2022 +27.4%, −20.4% May 2024–May 2025, 16 drawdowns >10%), SG 2023 ≈ −3 to −4%, Concretum GTAA in/out-of-sample (0.81 → 0.68 Sharpe), Antonacci 2013 absolute-momentum table, Hurst-Ooi-Pedersen scope and decade result, Baltussen et al. trend/carry Sharpe 1.09/1.15, Harvey et al. vol-targeting asset-class split, Cederburg et al. conclusions, Thornton-Valente abstract, Pitkäjärvi et al. abstract (+45% Sharpe), Faber CAPE 1980–2013 scope, Keller DAA rule and test design, Zweig threshold-sensitivity findings, eco3min net-liquidity divergence numbers, Falck et al. 43% decay, Quantpedia/Faber sector numbers (13.94%, Sharpe 0.54, DD −46%). Still open (out-of-scope ideas, which keep their markers): GEM live performance (dual_momentum_gem), HY trend / Alpha Architect (credit_spread_trend), Keller VAA exact numbers (taa_keller_vaa_daa), Koijen carry Sharpe ~1.1 (carry_multi_asset_etf), Gorton-Hayashi-Rouwenhorst / Boons-Prado / Bakshi-Gao-Rossi magnitudes (commodity_term_structure_roll), Miffre-Rallis magnitudes (commodity_momentum_etf), Asness-Ilmanen-Maloney and Goyal-Welch-Zafirov (erp_timing_cape), Resnick-Shoesmith threshold (yield_curve_inversion_equity), BAC Sharpe (betting_against_correlation_etf), and the ISM / copper-gold / dollar-regime claims (defensive_cyclical_rotation, copper_gold_yield_lead, dollar_regime_tilt).
