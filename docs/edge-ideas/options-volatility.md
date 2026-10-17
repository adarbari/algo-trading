# Edge ideas, family C. Options signals and volatility trading

Researched 2026-10-17 (deep-research agents; index and ranking: [README.md](README.md)). Ideas, not edges: nothing here is filed or tested. Figures marked *not verified*, *nv*, *recalled* or *from memory* must be checked against the source before an edge document cites them (quality bar item 5, [edges-plan.md](../edges-plan.md)).


**Family summary (5 lines).**
1. The best-evidenced, most feasible ideas here are *option data predicting stock returns* over 1-4 weeks: the call-put IV spread (Cremers-Weinbaum), IV smirk/skew (Xing-Zhang-Zhao), changes in call/put IV (An-Ang-Bali-Cakici), and the O/S volume ratio (Johnson-So). All four are computable from our Cboe EOD chains; all four show in-sample decay toward the end of their samples and thinner post-2010 evidence, so expect roughly half the published spread.
2. On the *option-selling* side, the robust facts are: (a) the per-name IV-HV gap predicts straddle / delta-hedged returns (Goyal-Saretto, Vasquez term structure, Zhan et al. characteristics, Bali et al. ML), which is a *ranking* edge, not a buy-and-hold one; (b) index put-writing (PUT/BXM) earns equity-like returns with lower vol but *lags* equities in bull markets because it carries ~0.5-0.75 beta and an uncompensated reversal exposure; (c) short-VIX roll yield is real but has a fat left tail (XIV died 2018-02-05) and needs a term-structure filter.
3. Earnings is a two-sided story: buying ATM straddles 3 days before the announcement earns ~3.3% gross (Gao-Xing-Zhang 2018) because IV is *under*-estimated ahead of earnings in small / noisy names; selling the crush works only in large liquid names and is net of a jump tail.
4. Honest P&L note: nearly every short-vol strategy here has a win rate of 65-90% and a P&L distribution that loses 2-10 years of premium in one tail event; Sharpe ~0.5-1.0 pre-cost with max drawdowns 30-95%. Report drawdown, not hit rate. Retail option bid-ask spreads (3-10% of premium on single names) eat a large part of every published gross number (Heston et al. 2023: option momentum ~0 after full spreads).
5. Decoys to test on every item: IV level (volatility anomaly / idiosyncratic vol), size, illiquidity, short-sale constraints and the earnings date itself. Several "option" signals are the low-vol anomaly or the short-interest signal wearing a mask. Our filed VRP short-put/strangle edge overlaps with items C09-C13; everything in part (1) is a *stock* edge and overlaps nothing filed.

Verification status: items marked **[verified]** were checked against the paper abstract or a secondary source this session; **[not verified]** numbers are from memory and must be confirmed before filing. The web search budget ran out before Pan-Poteshman, Martin-Wagner, Boyer-Vorkink, WPUT, Cboe 0DTE research and Muravyev-Pearson could be checked.

---

## Part 1 — Option data as a predictor of STOCK returns

### c01_call_put_iv_spread — Call-put implied volatility spread (put-call parity deviation)
- **Thesis**: When calls are implied-richer than same-strike puts, informed buying is in the calls; the stock outperforms over the next week to month.
- **Mechanism**: Informed traders use options for leverage and to dodge short-sale constraints; market makers widen the side being hit, so the IV spread leaks the direction of informed flow before the stock moves. Stock-market participants do not read option surfaces.
- **Persistence**: Needs option data plus a weekly rebalance of hundreds of names; capacity is small (effect concentrated in illiquid stocks with liquid options); arbitrage of the parity deviation itself is blocked by borrow costs and early exercise.
- **Rule (source's own)**: Volatility spread = open-interest-weighted average over matched call/put pairs of (IV_call − IV_put). Sort stocks weekly into quintiles/deciles; long top, short bottom; hold one week (also tested four weeks).
- **Evidence** [verified]: Cremers & Weinbaum (JFQA 2010) 1996-2005: top-minus-bottom ≈ 50 bp/week, risk-adjusted; predictability *declines over the sample*, which the authors read as mispricing being arbitraged. Bali & Hovakimian (Mgmt Sci 2009) find the call-put spread positively priced and interpret it as jump risk. A 2024 master's thesis extending to 2024 reports continued significance at 1- and 4-week horizons (not peer-reviewed); a 2011-2015 thesis reports 19 bp at 1 week and 73 bp at 4 weeks. Chen-Zimmermann OSAP includes this signal; expect roughly 50% post-publication shrinkage per McLean-Pontiff [not verified for this specific signal].
- **Sources**: Cremers & Weinbaum, "Deviations from Put-Call Parity and Stock Return Predictability", JFQA 45(2) 2010, https://ideas.repec.org/a/cup/jfinqa/v45y2010i02p335-367_00.html ; Bali & Hovakimian, "Volatility Spreads and Expected Stock Returns", Mgmt Sci 2009, https://pubsonline.informs.org/doi/fpi/10.1287/mnsc.1090.1063 ; CBS thesis "Trading on deviations from put-call parity", https://research-api.cbs.dk/ws/portalfiles/portal/60755923/306868_Trading_on_deviations_from_put_call_parity_and_mean_reversion.pdf ; CXO summary https://www.cxoadvisory.com/volatility-effects/do-informed-traders-tip-their-hands-via-option-purchases/
- **Horizon / schedule**: 5-20 sessions; every_session (weekly rebalance in the source).
- **Data needed**: Cboe EOD chains (IV per strike, OI) -> we already store IV surface, put/call wings; need a *matched-pair, OI-weighted* spread feature (`add-feature`). Dividend and borrow adjustments: we lack borrow fees (noise, not a blocker).
- **Individual fit**: Long-only top-quintile variant works (most of the spread is on the long side in later samples [not verified]); 20-50 names weekly; stock-side costs only. Good fit.
- **Decoys / overlap**: Short interest / borrow cost (we lack it); past-month return reversal; size. Overlaps c02, c04 (same information channel). No filed overlap.
- **Verdict**: **Promising**, Ready.

### c02_iv_smirk_skew — Individual option volatility smirk (OTM put IV − ATM call IV)
- **Thesis**: Stocks whose OTM puts are unusually expensive relative to ATM calls underperform over the next months.
- **Mechanism**: Informed traders with bad news buy OTM puts (cheap leverage, no borrow); the smirk steepens before the stock falls and before negative earnings surprises. Equity holders do not read the put wing.
- **Persistence**: Shorting the steep-smirk names is costly (they are often hard to borrow); the long-only side is a mild quality tilt; signal is slow (months), so it is not arbitraged by fast money.
- **Rule (source's own)**: SKEW = IV(OTM put, moneyness 0.80-0.95, 10-60 DTE) − IV(ATM call, 0.95-1.05); weekly average; sort into quintiles monthly; long lowest-smirk, short highest-smirk; hold 1 month (effect persists ~6 months).
- **Evidence** [verified abstract]: Xing, Zhang & Zhao (JFQA 2010) 1996-2005: low-minus-high smirk ≈ 10.9% per year risk-adjusted; steep smirk predicts negative earnings surprises. Post-publication: in Chen-Zimmermann OSAP ("Skew1"), later-sample returns are weaker and the long-short t-stat falls [not verified in detail]. Recent ML/crash-risk work (arXiv 2025/2026 "Option-Implied Signals and Crash Risk") still finds skew informative for crash probability.
- **Sources**: Xing, Zhang, Zhao, "What Does the Individual Option Volatility Smirk Tell Us About Future Equity Returns?", JFQA 2010 ; Chen & Zimmermann, Open Source Asset Pricing (Skew1) ; arXiv https://arxiv.org/pdf/2608.26115
- **Horizon / schedule**: 20-60 sessions; month_end (weekly average of daily skew as input).
- **Data needed**: We store skew already (Cboe); need the exact XZZ moneyness/DTE windows as a declared feature. Ready.
- **Individual fit**: Long-only low-smirk quintile viable; the short side needs borrow. Monthly, low turnover, cheap.
- **Decoys / overlap**: Correlates with low idiosyncratic vol and with short interest; test against IV30 level and 12-1 momentum (filed). c01 overlap (common component ~0.3-0.5 [not verified]).
- **Verdict**: **Promising**, Ready.

### c03_iv_change_call_put — Changes in call and put implied volatility (An-Ang-Bali-Cakici)
- **Thesis**: A rise in call IV over the past month predicts higher stock returns next month; a rise in put IV predicts lower.
- **Mechanism**: Information diffuses slowly from option prices to the stock; demand for calls (puts) by informed traders pushes their IVs up before the underlying reprices.
- **Persistence**: Monthly horizon with ~1%/month spread survives in a crowded space because it needs IV *changes* per side (not level) and the names are mid-cap; the authors show it is distinct from the smirk and the spread.
- **Rule (source's own)**: ΔCVOL = change over the prior month in the IV of the ATM 30-day call (OptionMetrics surface), ΔPVOL likewise for the put; decile sort monthly; long high ΔCVOL / short low; symmetric for puts with signs reversed; hold 1 month, persists ~6 months.
- **Evidence** [verified]: An, Ang, Bali & Cakici (JF 2014) 1996-2008(?): decile spread ≈ 1%/month on call-IV changes; put-IV changes carry the opposite sign; reverse predictability from stocks to options too. Post-publication evidence thin; the ML literature (Bali-Beckmeyer-Moerke-Weigert 2023) ranks IV changes among the stronger option-based predictors of *option* returns.
- **Sources**: NBER w19590 https://www.nber.org/papers/w19590.pdf ; SSRN https://papers.ssrn.com/abstract=2008902 ; Alpha Architect summary https://alphaarchitect.com/2014/11/does-option-implied-volatility-predict-stock-returns/
- **Horizon / schedule**: 20 sessions; month_end.
- **Data needed**: Our IV30 history exists but is a blended surface; need separate call-side and put-side ATM 30d IV series (feature). Ready with a small feature addition.
- **Individual fit**: Long-only high-ΔCVOL decile; monthly; 30-50 names.
- **Decoys / overlap**: Short-term stock momentum/reversal (IV rises after a rally too); earnings-month IV ramps (exclude names with earnings in the window); overlaps c01/c02.
- **Verdict**: **Promising**, Ready (after feature split).

### c04_option_stock_volume_ratio — O/S option-to-stock volume ratio
- **Thesis**: Stocks with unusually high option volume relative to stock volume underperform over the next week to month.
- **Mechanism**: Bad news is traded in options because shorting is costly; O/S spikes when informed traders lever bad news; stock holders do not watch option tape.
- **Persistence**: The signal predicts *negative* returns mostly, so harvesting it means shorting hard-to-borrow names; long-only harvesting (avoid high O/S) is a filter not a return source.
- **Rule (source's own)**: O/S = total option volume (contracts × 100) / stock share volume over the week; weekly decile sort; low O/S minus high O/S ≈ 0.34%/week (19.3% annualised) 1996-2010 [verified]. Ge, Lin & Pearson (JFE 2016): the power comes from option *leverage*; opening call purchases are the strongest sub-signal (we lack open/close flags).
- **Evidence**: Johnson & So (JFE 2012) as above; Blau et al. (JBF 2014): P/C ratios predict better daily, O/S weekly-monthly. Post-publication: in OSAP the signal shrinks materially after 2012 [not verified]; practitioner replications report the effect concentrated in the short leg and in small caps.
- **Sources**: Johnson & So, "The option to stock volume ratio and future returns", JFE 2012 https://academicnewsletter.sufe.edu.cn/info/356813 ; Ge, Lin, Pearson, "Why does the option to stock volume ratio predict stock returns?", JFE 2016 https://research.monash.edu/en/publications/why-does-the-option-to-stock-volume-ratio-predict-stock-returns/ ; Quantpedia entry https://vvv.quantpedia.com/?p=527
- **Horizon / schedule**: 5-20 sessions; every_session (weekly).
- **Data needed**: Cboe daily option volume per name (we store chain flow volume/OI) + daily share volume. Ready. Missing: opening vs closing trades, signed volume.
- **Individual fit**: As an *exclusion* filter on long screens (drop top-decile O/S) rather than a trade; the short leg is impractical.
- **Decoys / overlap**: Pre-earnings volume ramps; small size; illiquidity; short interest. Overlaps c05.
- **Verdict**: **Weak** as a standalone trade / **Promising** as a filter; Ready.

### c05_put_call_ratio_volume — Put/call volume ratio (Pan-Poteshman style)
- **Thesis**: Names with a high put/call volume ratio underperform the next day/week.
- **Mechanism**: Same as c04; Pan & Poteshman (RFS 2006) used *non-public* open-buy volume and found ~40 bp/day in the extreme deciles; with *public* total volume the effect is far smaller and fades within days [not verified this session].
- **Persistence**: The public-data version is largely arbitraged; survives only at daily horizon in small names.
- **Rule (source's own)**: P/C = put volume / (put + call volume) over the day or week; quintile sort; long low P/C, short high; hold 1 day to 1 week.
- **Evidence** [not verified]: Pan-Poteshman 2006 1990-2001 with proprietary data; Blau-Nguyen-Whitby (JBF 2014) with public data: daily predictability only. Widely replicated as weak after costs.
- **Sources**: Pan & Poteshman, "The Information in Option Volume for Future Stock Prices", RFS 2006 ; Blau et al., JBF 2014 (see c04 search).
- **Horizon / schedule**: 1-5 sessions; every_session.
- **Data needed**: Cboe daily volume per side. Ready.
- **Individual fit**: Poor: daily turnover, costs dominate. Only usable as a sentiment input or exclusion flag.
- **Decoys / overlap**: c04; stock reversal.
- **Verdict**: **Decayed** (public-data version), Ready as a filter only.

### c06_risk_neutral_skewness — Option-implied (BKM) risk-neutral skewness
- **Thesis**: Stocks whose option-implied return distribution is more negatively skewed earn higher (CDG) or lower (SKP) returns next month: the sign is contested.
- **Mechanism**: Two competing stories: (a) skewness preference: investors overpay for positive-skew (lottery) stocks, so negative RN skew earns a premium (Conrad-Dittmar-Ghysels 2013); (b) informed trading contaminates RN skew: steep put wings reflect bad news, so positive RN skew predicts higher returns (Stilger-Kostakis-Poon 2017: +55 bp/month FFC alpha 1996-2012 [verified]). Doshi-Luo-Yae argue (b) is a short-horizon contamination and (a) holds once it fades.
- **Persistence**: Unclear; sign instability is itself a warning.
- **Rule (source's own)**: Bakshi-Kapadia-Madan model-free skewness from OTM calls and puts at 30 DTE; monthly quintile sort; hold 1 month.
- **Evidence** [verified abstracts]: CDG (JF 2013) negative relation; SKP (RFS 2017) positive relation; Bali-Murray (JFQA 2013) skewness assets negatively priced. Kang-Sim: positive relation from information channel. Mixed and definition-sensitive.
- **Sources**: Conrad, Dittmar, Ghysels, "Ex Ante Skewness and Expected Stock Returns", JF 2013 https://pages.stern.nyu.edu/~dbackus/Disasters/ConradDittmarGhysels%20skewness%20Dec%2009.PDF ; Stilger, Kostakis, Poon, "What Does Risk-Neutral Skewness Tell Us About Future Stock Returns?", Mgmt Sci 2017 https://academicnewsletter.sufe.edu.cn/info/392653 ; Yae, "A Comprehensive Look at the Option Implied Predictors of Stock Returns" https://acfr.aut.ac.nz/__data/assets/pdf_file/0007/29797/J-Yae_A-Comprehensive-Look-at-the-Option-Implied-Predictors-of-Stock-Returns.pdf
- **Horizon / schedule**: 20 sessions; month_end.
- **Data needed**: Full chain OTM quotes (we have Cboe EOD); BKM integration is a new `quant/` function (architect area). Needs code, not data.
- **Individual fit**: Long-only one quintile; monthly.
- **Decoys / overlap**: Nearly collinear with c02 smirk in practice; lottery/MAX anomaly; idiosyncratic vol.
- **Verdict**: **Weak** (sign unstable), Needs code; test only as a robustness variant of c02.

### c07_iv_minus_realized_stock — Realised-minus-implied volatility spread for stock returns
- **Thesis**: Stocks whose realised vol is far above implied earn lower returns next month (and vice versa).
- **Mechanism**: Bali-Hovakimian read RV−IV as a volatility-risk proxy; stocks with IV >> RV have buyers of protection/upside, which precedes positive returns. Alternative: it is the volatility anomaly in disguise.
- **Persistence**: Modest; slow monthly signal.
- **Rule (source's own)**: RV (past month daily returns) − ATM IV (30d); monthly quintile sort; long lowest spread, short highest; 0.5-0.9%/month raw and risk-adjusted 1996-2005 [verified via CXO summary].
- **Evidence**: Bali & Hovakimian (Mgmt Sci 2009); Atilgan-Bali-Demirtas (JBES 2015) at the market level. Little post-2010 single-name evidence; the ML paper finds IV−RV mainly predicts *option* returns (c09), not stock returns [not verified].
- **Sources**: https://pubsonline.informs.org/doi/fpi/10.1287/mnsc.1090.1063 ; https://www.cxoadvisory.com/volatility-effects/sources-of-volatilitys-predictive-power-for-stock-returns ; https://ideas.repec.org/a/taf/jnlbes/v33y2015i1p87-101.html
- **Horizon / schedule**: 20 sessions; month_end.
- **Data needed**: IV30 and HV20/HV30: we have both (the filed VRP edge uses them). Ready.
- **Individual fit**: Long-only; monthly; cheap.
- **Decoys / overlap**: Low-vol anomaly; the filed VRP (same input, different asset). c01.
- **Verdict**: **Weak**, Ready (cheap to test alongside the filed VRP).

### c08_iv_term_structure_slope_stock — IV term-structure slope as a stock-return signal
- **Thesis**: An inverted single-name IV term structure (short IV > long IV) flags near-term event risk; stocks with steep upward slopes outperform. (Vasquez 2017 is about *option* returns; the stock-return version is a thinner literature.)
- **Mechanism**: Short-dated IV inflates before scheduled/unscheduled events; a persistent inversion outside earnings means an informed bid for near-term protection.
- **Persistence**: Short-dated; crowded only in earnings names.
- **Rule**: slope = IV(90d) − IV(30d) (or 180−30); monthly or weekly quintile sort. The stock-return magnitude is not well-established [not verified].
- **Evidence**: Vasquez (JFQA 2017) documents the slope predicts *straddle* returns (see c10). For stocks, Johnson (2017, "Risk premia and the VIX term structure") is at index level; single-name stock evidence is sparse and mixed.
- **Sources**: Vasquez, JFQA 2017 https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/equity-volatility-term-structures-and-the-cross-section-of-option-returns/F0A40E99FD2458367DD9A56A89783D38 ; CXO https://www.cxoadvisory.com/volatility-effects/exploiting-the-implied-volatility-term-structure/
- **Horizon / schedule**: 5-20 sessions; every_session.
- **Data needed**: We store the IV term structure. Ready.
- **Individual fit**: Long-only filter / exclusion of inverted names outside earnings.
- **Decoys / overlap**: Earnings date (the main driver of inversion); c03.
- **Verdict**: **Weak** for stock returns; Ready. File the option-return version (c10) instead.

### c09_unusual_options_activity — Unusual options activity / OI surges
- **Thesis**: A one-day surge in option volume or new OI far above the name's norm precedes a stock move in the direction of the surge's side.
- **Mechanism**: Informed (incl. illegally informed) traders act in options before M&A and news; Augustin-Brenner-Subrahmanyam (2019) find abnormal option volume before ~25% of M&A announcements [not verified exact figure].
- **Persistence**: Ex post detectable, ex ante noisy: most surges are hedges, rolls or spread legs; without trade-level data the direction is unknown.
- **Rule**: volume_z = (today's option volume − 20d mean)/20d sd per name per side; threshold ≥ 3; hold 5-20 sessions in the side's direction. No peer-reviewed rule with a published return exists for *EOD aggregate* UOA; practitioner services (Cheddar Flow etc.) publish no audited numbers.
- **Evidence**: Augustin, Brenner & Subrahmanyam, "Informed Options Trading Prior to Takeover Announcements", Mgmt Sci 2019 (pre-event detection, not a trading rule); Cao-Chen-Griffin (2005). No post-publication trading evidence.
- **Sources**: as above [not verified this session].
- **Horizon / schedule**: 5-20 sessions; on_event:option_volume_spike.
- **Data needed**: Daily option volume and OI per strike (we have). Missing: trade-level signed data (not stored), which is what separates a sweep from a spread.
- **Individual fit**: Event-driven; few events per name; the targets are often takeovers (large payoffs, low frequency).
- **Decoys / overlap**: c04/c05 (same volume); earnings ramps; index rebalances.
- **Verdict**: **Weak** (no replicable published rule), Needs data (trade-level flow).

### c10_dealer_gamma_pinning — Dealer gamma / GEX and max-pain pinning at expiry
- **Thesis**: Heavily optioned stocks close near a strike on expiration Friday more often than chance; dealer-positive gamma compresses moves, negative gamma amplifies them.
- **Mechanism**: Delta-hedge rebalancing by market makers as time decay pulls deltas toward 0/1 (Avellaneda-Lipkin 2003); some manipulation by prop traders (Ni-Pearson-Poteshman JFE 2005).
- **Persistence**: Weekly and daily expiries split OI, weakening the monthly pin; GEX is an *inferred* dealer position (sign assumptions about who is long).
- **Rule (source's own)**: NPP: probability of closing within 0.125 of a strike on expiration Friday is elevated for optionable stocks 1996-2002 (pinning, not "max pain"). Practitioner GEX: sum over strikes of OI × gamma × sign; positive = range, negative = trend. No published return number for a *trading* rule.
- **Evidence** [verified via summaries]: NPP pinning is real but small (a few percent excess clustering); max-pain level follows spot (reverse causality); a later S&P futures study found pinning where the model predicted anti-pinning. GEX intraday claims are practitioner-only; Barbon-Buraschi "Gamma fragility" (2020) is index-level and about vol amplification, not a tradable EOD signal [not verified].
- **Sources**: Ni, Pearson, Poteshman, "Stock Price Clustering on Option Expiration Dates", JFE 2005 ; Avellaneda & Lipkin, "A market-induced mechanism for stock pinning", 2003 https://math.nyu.edu/~avellane/PowerLaw.pdf ; SpotGamma explainer https://spotgamma.com/what-is-gex-gamma-exposure/ ; Konstanz "Pinning in the S&P" paper (link in search).
- **Horizon / schedule**: 1-5 sessions; on_event:opex (monthly third Friday; weeklies).
- **Data needed**: OI per strike (have), our own Greeks (have): GEX is a feature we can compute. OI walls already stored.
- **Individual fit**: EOD trader cannot trade intraday pinning; the EOD version is an iron-fly/short-straddle on expiry week around the OI wall in high-OI names: small premium, large gap risk.
- **Decoys / overlap**: Low realised vol in large caps; OPEX week effect (c27).
- **Verdict**: **Weak** (pinning real, trading rule not shown), Ready to measure, Out of scope to trade intraday.

### c11_option_implied_expected_return — Option-implied cost of capital / expected return (Martin-Wagner)
- **Thesis**: A stock's expected return can be read from its risk-neutral variance relative to the index's (SVIX-based), with no estimation; high implied expected return predicts higher realised return.
- **Mechanism**: Under a bound that is tight for a log investor, E[R_i] − R_f ≈ SVIX² + ½(SVIX_i² − average SVIX²): expected return rises with idiosyncratic risk-neutral variance.
- **Persistence**: It is a model, not a mispricing; magnitude is a few percent per year of cross-sectional spread [not verified].
- **Rule (source's own)**: Monthly SVIX_i from the 30-day OTM option portfolio of each name; sort or regress.
- **Evidence**: Martin & Wagner (JF 2019) show out-of-sample predictive power 1996-2014; Kadan-Tang (RFS 2020) lower bound on expected returns. Post-publication tests mixed [not verified].
- **Sources**: Martin & Wagner, "What Is the Expected Return on a Stock?", JF 2019 ; Kadan & Tang, "A Bound on Expected Stock Returns", RFS 2020. [not verified this session]
- **Horizon / schedule**: 20 sessions; month_end.
- **Data needed**: Full OTM chain (have); SVIX integration (new `quant/` function).
- **Individual fit**: Long-only; monthly. Low turnover.
- **Decoys / overlap**: It *is* (by construction) high IV / high idiosyncratic vol, so the low-vol anomaly runs against it.
- **Verdict**: **Weak** (theory-driven, small), Needs code.

---

## Part 2 — Option-selling and volatility edges

### c12_vrp_cross_section_iv_hv — Per-name VRP ranking: IV−HV straddles / delta-hedged options (Goyal-Saretto)
- **Thesis**: Rank names by (HV − IV); buy straddles where HV >> IV, sell where IV >> HV: option prices under-react to long-run realised vol.
- **Mechanism**: Option traders over-weight recent events in IV; vol mean-reverts to its 12-month level; the cross-sectional spread is a mispricing, not risk (not explained by factors).
- **Persistence**: Needs delta-hedged option portfolios across hundreds of names (capacity small, costs high); pros run it (it is the origin of "vol surface arbitrage"); still a top predictor in the 2023 ML study.
- **Rule (source's own)**: HV = 12-month realised vol of daily returns; IV = 1-month ATM; monthly decile sort on log(HV/IV); long decile 10 straddles / short decile 1 straddles; hold to next month. Decile spread for straddles ≈ 22%/month gross [not verified exact figure]; delta-hedged ≈ 1.5-2%/month [not verified]; 1996-2006.
- **Evidence** [verified abstract]: Goyal & Saretto (JFE 2009); robust across industries and liquidity; Vasquez 2017 (term-structure slope), Cao-Han 2013 (idiosyncratic vol), Zhan et al. 2022 and Bali et al. 2023 (ML) extend it; Bali et al. find nonlinear models profitable *after* costs through 2020. This is the best-evidenced option-return anomaly.
- **Sources**: Goyal & Saretto, "Cross-section of option returns and volatility", JFE 2009 ; EDHEC "Empirical properties of straddle returns" https://risk.edhec.edu/publications/empirical-properties-straddle-returns ; Bali, Beckmeyer, Moerke, Weigert, RFS 2023 https://www.wiwi.uni-muenster.de/fcm/en/publication/98329575
- **Horizon / schedule**: 20 sessions; month_end (also tested weekly).
- **Data needed**: IV30, HV (we have both), chain quotes for straddle P&L (have Cboe EOD). Ready. A clean *option P&L* outcome grain is needed in the harness (mid-to-mid, then half-spread).
- **Individual fit**: Variant for an individual: sell short-dated straddles/strangles only in the top (IV >> HV) decile, buy nothing (or buy in bottom decile as hedge). Spreads on single-name options are the killer: 5-10% of premium; the ML paper and Heston et al. show roughly half the gross vanishes.
- **Decoys / overlap**: **Directly overlaps the filed VRP short-put/strangle** — propose it as the *ranking* variant: the filed edge sells when IV > HV in aggregate; this one sells the cross-sectional top decile and tests whether ranking beats the unconditional sale. Decoy: earnings within the holding month (IV >> HV is often just an upcoming earnings date: exclude or test separately).
- **Verdict**: **Strong**, Ready (as a variant of the filed VRP).

### c13_iv_term_structure_straddles — IV term-structure slope predicts straddle returns (Vasquez)
- **Thesis**: Buy straddles on names with a steep upward IV term structure, sell on inverted ones: short-dated IV mean-reverts to the long end.
- **Mechanism**: Short-dated IV over-reacts; the slope forecasts the direction of the next month's IV change.
- **Persistence**: Same as c12.
- **Rule (source's own)**: slope = IV(long, ~1y or 6m ATM) − IV(1m ATM); monthly decile sort; long high-slope straddles, short low-slope; hold to expiry. Decile spread economically large (not explained by jump risk or factors) 1996-2007 [verified abstract, number not retrieved].
- **Evidence**: Vasquez (JFQA 2017); the earlier 2011 WP tested naked calls/puts, straddles, delta-hedged versions. Retained as a predictor in Bali et al. 2023.
- **Sources**: https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/equity-volatility-term-structures-and-the-cross-section-of-option-returns/F0A40E99FD2458367DD9A56A89783D38 ; https://alphaarchitect.com/2014/01/equity-term-structure-and-option-returns/
- **Horizon / schedule**: 20 sessions; month_end.
- **Data needed**: IV term structure (have). Ready.
- **Individual fit**: As a second ranking factor on top of c12 for *which* names to sell premium in (inverted term structure outside earnings = sell front month).
- **Decoys / overlap**: Earnings inversion; c12; filed VRP.
- **Verdict**: **Promising**, Ready.

### c14_delta_hedged_characteristics — Delta-hedged option returns predicted by stock characteristics (Zhan-Han-Cao-Tong; Cao-Han)
- **Thesis**: Writing delta-hedged calls earns more on stocks with low price, low profitability, high cash-flow variance, high issuance, high distress, high analyst dispersion, high idiosyncratic vol.
- **Mechanism**: Retail demand for lottery-like options and dealers' limits to arbitrage: the same characteristics that make a stock speculative make its options overpriced.
- **Persistence**: Authors report Sharpe > 2 and profits after costs; explained by two option factors, not equity factors; still works in the ML paper through 2020.
- **Rule (source's own)**: Monthly, for each name, sell one ATM call ~1.5 months to expiry, delta-hedge daily (or at least at open), hold one month; sort on each characteristic into deciles; long-short decile returns. Cao-Han (JFE 2013): delta-hedged returns decrease in idiosyncratic vol.
- **Evidence** [verified abstract]: Zhan, Han, Cao, Tong, "Option Return Predictability", RFS 2022; Cao & Han, "Cross section of option returns and idiosyncratic stock volatility", JFE 2013; Bali et al. 2023 (ML) confirms stock characteristics add incremental power.
- **Sources**: https://research.polyu.edu.hk/en/publications/option-return-predictability/ ; https://www.cxoadvisory.com/equity-options/option-strategies-based-on-factor-sorts ; ABFER draft https://abfer.org/media/abfer-events-2016/annual-conference/investment-finance/226-option-return-predictability.pdf
- **Horizon / schedule**: 20 sessions; month_end.
- **Data needed**: SEC financials (profitability, cash, issuance: have), analyst dispersion (FMP/Finnhub: partial), price, idiosyncratic vol (have). Daily delta-hedge P&L needs our Greeks + daily bars (have). Ready-ish.
- **Individual fit**: Hedging daily across 50 names is heavy for one person; the practical variant is *selecting* which names to sell covered calls / strangles on (overlay on c12). Costs are the binding constraint.
- **Decoys / overlap**: Idiosyncratic vol explains much of the characteristic spread (Cao-Han); c12; filed VRP.
- **Verdict**: **Promising**, Ready (as a selection overlay).

### c15_option_momentum — Option (straddle) return momentum
- **Thesis**: Straddles with high past 6-36 month returns keep outperforming; no long-run reversal.
- **Mechanism**: Slow learning about which names' vol is persistently under-priced; option-specific (not stock momentum).
- **Persistence**: Published 2023; but *after full bid-ask spreads the return is near zero* even in the liquid half.
- **Rule (source's own)**: Monthly ATM straddle returns per name; sort on past 12-month (skip 1) average; long winners short losers; 1996-2019 [verified].
- **Evidence**: Heston, Jones, Khorram, Li, Mo, "Option Momentum", JF 2023 (DOI 10.1111/jofi.13279).
- **Sources**: https://alphaarchitect.com/2022/11/option-momentum/ ; https://www.cxoadvisory.com/?p=34737
- **Horizon / schedule**: 20 sessions; month_end.
- **Data needed**: Monthly straddle returns per name: computable from Cboe EOD since 2024-10 only (~2 years, too short for 12-36 month lookbacks for most names). Needs data (option history pre-2024).
- **Individual fit**: Poor after costs by the authors' own reckoning.
- **Decoys / overlap**: c12 (the names with persistent IV<RV).
- **Verdict**: **Weak** (dies after costs), Needs data.

### c16_pre_earnings_straddle_buy — Buy ATM straddles 3 days before earnings (Gao-Xing-Zhang)
- **Thesis**: IV under-estimates the earnings move in small, noisy, costly-to-trade names; buying the straddle a few days before and closing at the announcement earns ~3% gross.
- **Mechanism**: Investors under-estimate event uncertainty where signals are noisy; the pre-announcement IV ramp plus the move more than covers theta.
- **Persistence**: Concentrated in small / illiquid / high-cost names: exactly where spreads are widest; the authors say it is only profitable if costs are low enough.
- **Rule (source's own)**: ATM straddle, nearest expiry after the announcement, bought at close t−3, sold at close of the announcement day (or t+1 for AMC); average 3.34% return 1996-2013 [verified]; stronger in small, high-vol/kurtosis, volatile-surprise, low-volume names.
- **Evidence**: Gao, Xing, Zhang, "Anticipating Uncertainty: Straddles around Earnings Announcements", JFQA 2018; Gao-Hu-Zhang "Uncertainty Resolution Before Earnings Announcements" (pre-announcement premium). Post-publication: practitioner backtests (BSIC "Straddling outside and into earnings") report the pre-earnings ramp still positive but thinner in large caps [not peer-reviewed].
- **Sources**: https://resolve.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/anticipating-uncertainty-straddles-around-earnings-announcements/7B34877AD5E06304BA3C55FBA3219FDD ; Tsinghua WP https://www.pbcsf.tsinghua.edu.cn/__local/A/11/35/B0A1714D795BD9799087BCCC2AD_A01C4283_54641.pdf ; https://bsic.it/straddling-outside-and-into-earnings/
- **Horizon / schedule**: 3-4 sessions; on_event:earnings (expected date known weeks ahead: trigger at t−3 close, act t−3 close or t−2 open).
- **Data needed**: Earnings expected dates (have), chains (have), implied move (have). Ready. Outcome grain: straddle mid-to-mid P&L.
- **Individual fit**: Long options, defined risk, no margin; costs are the whole game: restrict to names with spread < 5% of straddle price, which removes much of the published edge. ~1,500 earnings events per quarter in universe: plenty of events.
- **Decoys / overlap**: Filed "earnings announcement premium" (stock) found no premium; this is the *vol* premium, distinct. Decoy: the pre-earnings IV ramp alone (sell at t−1 before the move) vs holding through the move: test both legs.
- **Verdict**: **Promising**, Ready.

### c17_earnings_iv_crush_sell — Sell the earnings move (IV crush) in large liquid names
- **Thesis**: In large caps the implied move exceeds the realised move on average; selling the straddle/strangle at the close before the announcement and covering after earns the crush.
- **Mechanism**: Demand for event protection and lottery calls by retail; dealers charge for jump risk they cannot hedge.
- **Persistence**: Well known and crowded (tastytrade et al. publish it); average edge small (implied move / realised move ratio ~1.1-1.3 in large caps [not verified]); the P&L is a short-jump tail: one 30% gap wipes 10-20 trades.
- **Rule (practitioner)**: At close t−1 sell ATM straddle (or 16-delta strangle) expiring after the event, cover at open/close t+1. No peer-reviewed rule with a published return; Gao-Xing-Zhang find straddles *lose* on average outside the pre-earnings window and the announcement-day return is positive on average for small names, so the selling edge is a large-cap phenomenon [inference].
- **Evidence**: Mixed: published academic work favours *buying* into earnings in small names; practitioner evidence for selling in large caps is unaudited. Our own implied-move vs reaction data can settle it quickly.
- **Sources**: Gao-Xing-Zhang 2018 (above) ; tastytrade/ORATS research pages [not verified].
- **Horizon / schedule**: 1-2 sessions; on_event:earnings.
- **Data needed**: Implied move (have), earnings reactions (have). Ready: compute the ratio of implied to realised move by size/liquidity bucket first.
- **Individual fit**: Undefined-risk short straddles need margin and nerves; iron flies / defined-risk versions cut the tail and most of the edge. Report P&L distribution, not win rate (expect 65-70% wins, negative skew).
- **Decoys / overlap**: Filed VRP (it is VRP at an event); c16 (the mirror image by size).
- **Verdict**: **Promising** for large caps / **Weak** for small caps; Ready.

### c18_iv_rank_conditional_selling — IV-rank / IV-percentile conditional premium selling
- **Thesis**: Selling premium only when IV rank is high (IV in the top half of its 1-year range) improves the risk-adjusted return of short options.
- **Mechanism**: IV mean-reverts; a high rank means IV is more likely to fall; practitioners (tastytrade "IVR > 50") treat this as doctrine.
- **Persistence**: High IV rank clusters in crashes and before earnings, i.e. when realised vol is also highest, so the conditional edge over unconditional selling is small; academic evidence that IV *rank* (vs IV−HV) adds anything is weak [not verified].
- **Rule (practitioner)**: IVR = (IV − 1y min)/(1y max − 1y min); sell 45-DTE 16-delta strangles when IVR > 50; manage at 50% of credit or 21 DTE.
- **Evidence**: Practitioner backtests (tastytrade, ORATS, Spintwig) report modest Sharpe improvement and larger drawdowns in high-IVR regimes; no peer-reviewed study. The academic analogue is Goyal-Saretto's IV−HV (c12), which does have evidence.
- **Sources**: tastytrade research, Spintwig "SPY short strangle" backtests [not verified this session].
- **Horizon / schedule**: 20-45 sessions; every_session (entry filter).
- **Data needed**: IBKR IV rank (have, `iv_rank_source`), IV history (have). Ready.
- **Individual fit**: Natural filter for the filed VRP edge.
- **Decoys / overlap**: **Filed VRP** (this is a conditioning variable for it); c12 IV−HV likely dominates IVR: test both.
- **Verdict**: **Weak** as an edge / **Promising** as a filter on the filed VRP; Ready.

### c19_index_put_write — Index put-writing / covered-call (PUT, BXM, WPUT) as a return source
- **Thesis**: Systematically selling ATM SPX puts (PUT) or calls against the index (BXM) earns equity-like returns with ~2/3 the volatility because index options are over-priced (the index VRP).
- **Mechanism**: Structural demand for index protection (insurance mandates, overlays) and dealers' short-gamma aversion; the index VRP is the most durable premium in this family (Driessen-Maenhout-Vilkov: index IV 24.7% vs RV 20.8% 1996-2003 [verified]).
- **Persistence**: Decades of evidence; but the *return* comes mostly from embedded equity beta (Israelov-Nielsen: equity exposure most of risk and return; short vol Sharpe ~1 but only 10% of risk; reversal exposure ~25% of risk for little return [verified]). It lags equities in bull markets because beta ~0.5-0.75 (Israelov-Ndong 2023: higher-yield call writing cuts beta to ~0.75 [verified]).
- **Rule (source's own)**: PUT: sell one-month ATM SPX put monthly, fully collateralised in T-bills, roll at expiry. BXM: hold S&P 500, sell one-month ATM call monthly. WPUT: weekly version.
- **Evidence** [verified via summaries]: Cboe-commissioned study 1986-2015: returns similar to S&P 500 with lower vol and lower max drawdown; First Trust: S&P beat BXM by 14.4 pp in 2023 and 10.6 pp through Nov 2024; PUT nearly flat Dec 2024. Long run (1986-2024) PUT ≈ S&P total return with ~2/3 vol [not verified exact]. Drawdown 2008: PUT ≈ −33% vs S&P −51% [not verified]. 2020 and 2022 saw PUT lose with the market.
- **Sources**: Israelov & Nielsen, "Covered Calls Uncovered", FAJ 2015 https://rpc.cfainstitute.org/research/financial-analysts-journal/2015/covered-calls-uncovered ; Israelov & Nielsen, "Covered Call Strategies: One Fact and Eight Myths", FAJ 2014 https://www.aqr.com/-/media/AQR/Documents/Insights/Journal-Article/FAJ-Covered-Call-Strategies-One-Fact-and-Eight-Myths.pdf ; First Trust covered-call updates https://www.ftportfolios.com/Commentary/MarketCommentary/2025/3/6/an-update-on-covered-call-returns ; Hedgeweek on the Cboe study https://www.hedgeweek.com/new-study-analyses-performance-cboe-sp-500-options-selling-indexes/ ; DMV, "The Price of Correlation Risk", RFS 2009.
- **Horizon / schedule**: 20 sessions (monthly) or 5 (weekly); month_end / every_week.
- **Data needed**: SPX/SPY chains (have via Cboe), T-bill rate (have). Ready. We do not store the Cboe index levels themselves (PUT, BXM) as benchmarks: add as reference series if we want to replicate.
- **Individual fit**: SPY/XSP put-writing is the most realistic retail short-vol trade: tight spreads, cash-secured, monthly. The honest comparison is PUT vs 60/40 or vs 0.7×SPX: on that basis the alpha is ~1-2%/yr pre-cost [not verified].
- **Decoys / overlap**: Equity beta (the main decoy: compare to beta-matched SPX, not SPX); **filed VRP short-put** (index version thereof).
- **Verdict**: **Promising** (as a beta-adjusted VRP harvest), Ready. Weekly vs monthly (WPUT vs PUT): Cboe data show WPUT with lower return and similar vol since 2006 [not verified]; weekly adds gamma risk and 4× costs: do not favour.

### c20_short_vix_roll_yield — VIX futures contango roll yield / short VIX ETPs with a term-structure filter
- **Thesis**: VIX futures sit in contango ~80% of the time; shorting the front month (or holding SVXY) collects the roll; a slope filter avoids backwardation regimes.
- **Mechanism**: Structural demand for forward volatility (long-vol ETPs, hedgers) keeps futures above the expected VIX; Cheng (RFS 2019) shows the ex-ante VIX premium predicts realised futures returns one-for-one and *falls* when risk rises (hedgers de-risk), which is why unfiltered short vol gets hit exactly when premium is lowest [verified].
- **Persistence**: Survives because the tail is horrific: XIV lost ~95% on 2018-02-05 and was terminated; SVXY cut leverage to −0.5× afterwards [not verified exact]. Nobody with a mandate can hold it unlevered through that.
- **Rule (source's own)**: Simon & Campasano (JAI 2014): short front VIX future when basis (F1−VIX) is in contango beyond a threshold, hedged with mini-S&P futures; CXO summary: sell futures when futures/spot ratio > 1 else cash: 4.3%/month excess 2004-2014 [verified via summary; period pre-2018]. Quantpedia "Exploiting term structure of VIX futures".
- **Evidence**: Cheng, "The VIX Premium", RFS 2019 https://academicnewsletter.sufe.edu.cn/info/352766 ; Simon & Campasano, "The VIX Futures Basis: Evidence and Trading Strategies", JAI 2014 [not verified] ; CXO https://www.cxoadvisory.com/volatility-effects/timing-vix-futures-with-the-futures-spot-ratio/ ; Quantpedia https://quantpedia.com/strategies/exploiting-term-structure-of-vix-futures . Post-2018: filtered versions survived Feb 2018 (the curve inverted days before) but 2020-03 and 2024-08-05 produced 50%+ drawdowns in unfiltered short-vol ETPs [not verified].
- **Horizon / schedule**: 5-20 sessions; every_session (slope check daily).
- **Data needed**: VIX futures curve: **not stored** (IBKR possible); VIX and VIX3M/VIX9D indices as proxies: not stored either (FRED has VIX only). Needs data.
- **Individual fit**: SVXY/VXX shorts via ETFs; position must be sized for a −90% day; Sharpe ~0.7-1.0 with −60% to −95% max DD [not verified]. For an EOD trader a realistic sizing is 2-5% of equity.
- **Decoys / overlap**: Equity beta (short vol ≈ 2-3× SPX beta in a crash); filed VRP (same premium at index level).
- **Verdict**: **Promising**, Needs data (VIX futures history / VIX term indices).

### c21_vix_futures_basis_signal — VIX futures basis as a *stock market* timing signal
- **Thesis**: Steep backwardation (F1 < VIX) marks capitulation and precedes equity rebounds; steep contango marks complacency.
- **Mechanism**: Hedging demand surges when risk rises; the basis is a cleaner fear gauge than VIX level.
- **Persistence**: Few events (backwardation episodes ~10-20 since 2004), weak out-of-sample, mostly a regime label.
- **Rule**: ratio VIX/VIX3M > 1 (or F1/F2 > 1) -> expect positive 20-60 day SPX returns; practitioners (Bilello, Allocate Smartly) show higher forward returns after inversion, but the sample is small [not verified].
- **Evidence**: Johnson (2017, "Risk premia and the VIX term structure", JFQA): the slope predicts variance-swap returns, less so equity. Mostly practitioner.
- **Sources**: Johnson, JFQA 2017 [not verified] ; Allocate Smartly / Bilello charts [not verified].
- **Horizon / schedule**: 20-60 sessions; on_event:term_structure_inversion.
- **Data needed**: VIX term indices (not stored). Needs data. Fewer than 40 independent events likely.
- **Individual fit**: Regime input only.
- **Decoys / overlap**: VIX level; drawdown-based mean reversion; our regime label.
- **Verdict**: **Weak** (too few events), Needs data.

### c22_dispersion_trade — Dispersion: short index vol, long single-name vol (implied correlation premium)
- **Thesis**: Index IV embeds an implied correlation well above realised correlation; selling index straddles and buying a basket of constituent straddles earns the correlation premium.
- **Mechanism**: Index put demand (hedgers) vs single-name call supply (overwriters) leaves index vol rich and single-name vol fair or cheap (DMV 2009: single names show little or no VRP [verified]).
- **Persistence**: Needs vega-neutral baskets of 30-50 names, continuous hedging, and loses in correlation spikes (crashes); institutional strategy, but the *premium* persists (Faria-Kosowski-Wang 2021: 6.7-8.9 correlation points at 91 days [verified via summary]; DMV: ~18 points 1996-2003).
- **Rule (source's own)**: Monthly: sell ATM S&P 100/500 straddle, buy vega-weighted ATM straddles on constituents; hold to expiry; delta-hedge. Cboe DSPX index (dispersion) now tracks implied dispersion.
- **Evidence**: Driessen, Maenhout, Vilkov, "The Price of Correlation Risk", RFS 2009 ; Faria, Kosowski, Wang 2021 ; Quantpedia https://quantpedia.com/strategies/dispersion-trading/ ; Resonanz on DSPX https://resonanzcapital.com/insights/dispersion-trading-and-the-dspx-index ; BSIC backtest https://bsic.it/backtesting-dispersion-trading-chapter-i/
- **Horizon / schedule**: 20 sessions; month_end.
- **Data needed**: Index and constituent chains (have), S&P weights (have ETF holdings). Implied correlation is a computable feature. Ready to *measure*; trading it is heavy.
- **Individual fit**: Poor: 30+ legs, hedging, margin. A retail proxy (sell SPY straddle, buy 5-10 largest-weight straddles) carries huge idiosyncratic risk. Better as a *signal*: implied-correlation level as a regime / VRP-timing input.
- **Decoys / overlap**: Index VRP (c19) explains most of it; filed VRP.
- **Verdict**: **Promising** as a measured premium / **Out of scope** to trade; Ready to compute implied correlation.

### c23_skew_risk_reversal_trade — Selling index skew (risk reversals) / skew premium
- **Thesis**: Index OTM puts are over-priced relative to OTM calls; selling the put and buying the call (risk reversal) harvests the skew premium.
- **Mechanism**: Crash insurance demand; dealers' negative-skew aversion. Kozhan-Neuberger-Schneider (RFS 2013): the skew risk premium is large and strongly linked to the variance premium [not verified].
- **Persistence**: It is a leveraged long-equity, short-crash position: the premium is the cost of being short the crash.
- **Rule (source's own)**: KNS: skew swap returns on S&P 500 options 1996-2012; practitioner: monthly 25-delta risk reversal, delta-hedged.
- **Evidence**: Kozhan, Neuberger, Schneider, "The Skew Risk Premium in the Equity Index Market", RFS 2013 [not verified]; SKEW index behaviour shows the premium is persistent and not a timing signal (Cboe SKEW has poor forecasting power for crashes).
- **Sources**: KNS 2013 ; Cboe SKEW white papers [not verified].
- **Horizon / schedule**: 20 sessions; month_end.
- **Data needed**: Index chain (have). Ready to measure.
- **Individual fit**: Short OTM puts = the filed short-put edge with a call kicker; margin-heavy.
- **Decoys / overlap**: Equity beta; filed VRP short put.
- **Verdict**: **Weak** (restates the index VRP with more beta), Ready.

### c24_tail_hedge_cost_benefit — Tail hedging with OTM puts: cost vs benefit
- **Thesis**: A small permanent allocation to deep-OTM puts improves compound growth (Universa claim) vs. the finding that put protection is a poor, expensive drawdown reducer (Israelov "Pathetic Protection").
- **Mechanism**: Puts are rich (c19/c23) so the hedger pays the VRP; benefit only if the hedge is monetised at the crisis peak and the portfolio is levered up accordingly.
- **Persistence**: Not an edge for the buyer; it is the mirror of c19.
- **Rule (source's own)**: Cboe PPUT (5% OTM put protection) index; Israelov: compared to de-levering, PPUT reduced drawdowns little and cost ~2-3%/yr [verified direction, not number]. Universa: 3.33% in the tail fund + 96.67% S&P claimed to beat S&P, 76%/yr life-to-date on the tail sleeve (self-reported, not independently verified) [verified as claim].
- **Evidence**: Israelov, "Pathetic Protection: The Elusive Benefits of Protective Puts", JAI 2019 ; Spitznagel letters ; CalPERS dropped its tail programme in Oct 2019 as too costly, months before Mar 2020.
- **Sources**: https://www.advisorperspectives.com/articles/2020/05/06/an-aqr-warning-and-a-3-612-return-fire-up-the-black-swan-debate ; https://www.wealthmanagement.com/equities/hedging-tail-risks-tortoise-versus-hare ; https://www.institutionalinvestor.com/index%2ephp/article/2bsxa6cu6tic60crzi6f4/portfolio/youre-doing-it-wrong-a-tail-risk-hedger-calls-out-his-industry
- **Horizon / schedule**: n/a (portfolio overlay); month_end roll.
- **Data needed**: Index chain. Ready to measure the cost.
- **Individual fit**: As an overlay on the short-vol edges (c12/c17/c19) a far-OTM put wing converts undefined risk to defined and costs ~20-30% of the premium [not verified]: this is the right use, not standalone.
- **Decoys / overlap**: Simply holding less equity (Israelov's point).
- **Verdict**: **Dead** as an edge / useful as risk design; Ready.

### c25_iron_condor_etf — Iron condors / CNDR on index ETFs
- **Thesis**: Selling a monthly OTM strangle on SPX with protective wings (CNDR: 20-delta short, 5-delta long) earns the VRP with defined risk.
- **Mechanism**: Same as c19 (index VRP) with the tails bought back.
- **Persistence**: The wings cost most of the premium; CNDR has lagged PUT and BXM historically with similar drawdowns in fast moves (2018, 2020) [not verified exact].
- **Rule (source's own)**: Cboe CNDR methodology: monthly, sell 20Δ put and call, buy 5Δ put and call, cash-collateralised.
- **Evidence**: Cboe study 1986-2015 includes CNDR (returns similar to S&P with lower vol); no 2024-2025 CNDR figures found. Practitioner backtests (Spintwig) show iron condors with Sharpe ~0.3-0.6 after costs.
- **Sources**: Hedgeweek (Cboe study) ; Cboe index pages.
- **Horizon / schedule**: 20 sessions; month_end.
- **Data needed**: SPX/SPY chain (have). Ready.
- **Individual fit**: Best-fitting *structure* for a retail account (defined risk, no margin shock); worst-fitting *edge* (the wings pay away the premium). Win rate 75-85%, max loss ~5-8× average win.
- **Decoys / overlap**: c19; filed VRP strangle.
- **Verdict**: **Weak** (structure, not edge), Ready.

### c26_weekend_nontrading_option_mispricing — Option over-pricing across weekends / holidays (Jones-Shemesh)
- **Thesis**: Option prices do not fully discount the near-zero variance of non-trading days; selling options Friday and buying back Monday earns a negative option return of ~−0.62% per Friday-Monday on single names.
- **Mechanism**: Traders treat calendar days as if variance accrued; a persistent, widespread mispricing in single-name options; little evidence in SPX options.
- **Persistence**: Costs: a weekly round trip on single-name options eats far more than 0.6%; the authors note it is pervasive but it is harvestable only by market makers / those already holding positions.
- **Rule (source's own)**: Portfolios of delta-hedged single-name options; average Friday-to-Monday return −0.62% vs positive on other days, 1996-2007 [verified]; stronger before long weekends/holidays.
- **Evidence**: Jones & Shemesh, "Option Mispricing around Nontrading Periods", JF 2018 https://ideas.repec.org/a/bla/jfinan/v73y2018i2p861-900.html ; CXO https://www.cxoadvisory.com/?p=5800 . Post-publication: not re-tested in the literature found.
- **Horizon / schedule**: 1-3 sessions; on_event:pre_weekend / pre_holiday.
- **Data needed**: Cboe EOD chains daily (have). Ready to measure.
- **Individual fit**: As *timing* for entries of the short-vol edges (open short premium Friday close, not Monday) rather than a trade: costless improvement.
- **Decoys / overlap**: Theta accounting conventions; all short-vol edges.
- **Verdict**: **Promising** as execution timing / **Weak** as trade; Ready.

### c27_opex_week_effect — Option-expiration week equity returns (Stivers-Sun)
- **Thesis**: Large-cap optionable stocks earn abnormally high returns in the monthly third-Friday week and modestly low returns the fourth-Friday week.
- **Mechanism**: Delta-hedge unwinds by market makers (reduction of short-stock hedges as options decay/expire) and falling implied vol into expiry.
- **Persistence**: Weeklies have diluted the monthly cycle; practitioner backtests say the effect deteriorated in the last ~4 years [verified via blog].
- **Rule (source's own)**: Long S&P 100 stocks (esp. high option-volume) Monday-Friday of expiration week; 1983-2008 for the index, S&P 100 names in the JBF paper [verified].
- **Evidence**: Stivers & Sun, "Market cycles and the performance of relative strength strategies"? — no: Stivers & Sun, JBF 2013 37(11) 4226-4240 "The other January effect"? [citation details not verified; the JBF 2013 option-expiration paper is the one summarised at https://ideas.repec.org/a/eee/jbfina/v37y2013i11p4226-4240.html] ; CXO drill-down https://cxoadvisory.com/calendar-effects/option-expiration-week-stock-return-drill-down ; Quantpedia #102 https://quantpedia.com/Screener/Details/102 ; Quantified Strategies https://quantifiedstrategies.substack.com/p/the-options-expiration-week-effect-aa2
- **Horizon / schedule**: 5 sessions; on_event:opex_week (known from the calendar; act Friday close before).
- **Data needed**: Daily bars (have), option volume per name (have). Ready; ~12 events/year, 40 events in 3.5 years, Tiingo history to 2010 gives 180.
- **Individual fit**: Long-only SPY or top-option-volume names one week a month; cheap.
- **Decoys / overlap**: Turn-of-month / mid-month flows; general calendar effects (family of another researcher?).
- **Verdict**: **Decayed** (weakening, small), Ready.

### c28_zero_dte_premium — 0DTE SPX option selling
- **Thesis**: Same-day SPX options are over-priced on average because retail buys them as lotteries; selling them (esp. puts, esp. after the open) is profitable net of fees.
- **Mechanism**: Beckmeyer-Branger-Gayda (2023): retail lost >$70m in 0DTE Jan 2021-Feb 2023 ($358k/day after daily expiries began May 2022); ~60% of losses are transaction costs and ~60% from put buying; short positions were profitable after fees [verified].
- **Persistence**: Intraday gamma risk; a 2% afternoon move wipes weeks; the edge accrues mostly in the first minutes of the day (two-thirds in the first minute) which an EOD trader cannot access.
- **Rule (source's own)**: Not a trading rule; the paper measures retail P&L by position. Practitioner rules (sell 10-16Δ strangles at 9:45, close at 15:30) are intraday.
- **Evidence**: Beckmeyer, Branger, Gayda, "Retail Traders Love 0DTE Options... But Should They?", SSRN 4404704, 2023 ; Bloomberg coverage https://www.bnnbloomberg.ca/day-traders-lose-358-000-per-day-gambling-on-zero-day-options-1.1910634 ; Cboe's own 0DTE studies find no measurable effect on close-to-close volatility [not verified].
- **Horizon / schedule**: intraday; not schedulable in our EOD harness.
- **Data needed**: Intraday option quotes: not stored.
- **Individual fit**: Out of scope for EOD; a Monday-expiry 1-DTE overnight sale is the EOD-compatible cousin (overnight gap risk, no theta of note).
- **Decoys / overlap**: Index VRP.
- **Verdict**: **Promising** in the literature / **Out of scope** (intraday).

### c29_wheel_strategy — The "wheel" (cash-secured puts -> covered calls)
- **Thesis**: Selling puts on names you want to own, then calls on the assigned shares, earns income with a smoother path than buy-and-hold.
- **Mechanism**: It is PUT + BXM on single names: a short-vol overlay on a long-equity position with path dependence.
- **Persistence**: No edge beyond c19/c12: single-name VRP is small or absent on average (DMV 2009), and the assignment rule introduces a mean-reversion bet (buy after a drop, sell after a rally) which Israelov-Nielsen show is uncompensated.
- **Rule (practitioner)**: Sell 30-45 DTE 30Δ put; if assigned sell 30Δ call; repeat.
- **Evidence**: No academic study; practitioner backtests (Spintwig "wheel") show it tracks a ~0.6-beta equity portfolio with a worse Sharpe than put-write on the index [not verified].
- **Sources**: Israelov & Nielsen 2015 (reversal exposure) ; practitioner backtests [not verified].
- **Horizon / schedule**: 20-45 sessions; every_session.
- **Data needed**: Have.
- **Individual fit**: Popular, workable, but the "income" framing is an accounting illusion (FAJ 2014 "Eight Myths").
- **Decoys / overlap**: Equity beta; c19; filed VRP.
- **Verdict**: **Weak**, Ready (only as a benchmark for c12/c14 selection).

### c30_calendar_spread_term_kinks — Calendar spreads on term-structure kinks (incl. earnings)
- **Thesis**: When front-month IV is inflated relative to the second month beyond what the event justifies, sell front / buy back month; reverse when the front is cheap.
- **Mechanism**: Vasquez (c13) at the spread level: short-dated IV over-reacts.
- **Persistence**: Earnings calendars are crowded; non-earnings kinks are rare and often reflect real events (FDA dates, trials).
- **Rule**: slope_z of IV(30)−IV(60) vs the name's own history, excluding earnings windows; sell front when z > 2. No published number [not verified].
- **Evidence**: Only indirect (Vasquez 2017; Jones-Shemesh for holiday kinks). Practitioner anecdote.
- **Sources**: as c13.
- **Horizon / schedule**: 20 sessions; every_session.
- **Data needed**: IV term structure (have). Ready.
- **Individual fit**: Defined-risk, cheap; vega-heavy, needs the back month to hold IV.
- **Decoys / overlap**: c13, c17.
- **Verdict**: **Weak**, Ready (fold into c13).

### c31_lottery_options_short — Short OTM calls on lottery-like stocks (Boyer-Vorkink)
- **Thesis**: OTM calls on high expected-skewness stocks are over-priced; writing them (hedged) earns a premium.
- **Mechanism**: Retail skewness preference; limits to arbitrage for dealers.
- **Persistence**: Published 2014; retail call-buying has grown since 2020, so the premium is plausibly larger now, but so is the squeeze tail (GME/AMC).
- **Rule (source's own)**: Monthly sort on ex-ante option skewness; short high-skew OTM calls; delta-hedged; 1996-2009; returns strongly negative for high-skew calls [not verified magnitude].
- **Evidence**: Boyer & Vorkink, "Stock Options as Lotteries", JF 2014 [not verified this session]; Zhan et al. 2022 (c14) share the mechanism.
- **Sources**: Boyer & Vorkink, JF 69(4) 2014.
- **Horizon / schedule**: 20 sessions; month_end.
- **Data needed**: OTM call IV vs ATM (call wing skew: have). Ready.
- **Individual fit**: Naked short calls on meme stocks is the single most dangerous trade in this file; covered-call version only.
- **Decoys / overlap**: c14 (idiosyncratic vol), MAX/lottery stock anomaly (another family).
- **Verdict**: **Promising** (mechanism strengthened post-2020) / Ready only as covered-call selection.

---

## Rejected on sight (one line each)

- **Max-pain as a price target**: OI follows spot, not the reverse; only weak pinning survives (c10).
- **Cboe SKEW index as a crash timer**: no documented forecasting power; it measures the price of crash insurance, not its probability.
- **VIX level mean-reversion as a standalone equity timer**: VIX level is the realised-vol/beta decoy; covered by regime label.
- **Buying VXX/UVXY for "cheap" protection**: roll decay ~5-8%/month in contango; the mirror of c20, no edge for the buyer.
- **Selling naked 0DTE from EOD**: intraday only; no overnight edge documented (c28).
- **Weekly put-write over monthly (WPUT)**: lower return, 4× costs, more gamma; Cboe's own index comparison does not favour it [not verified].
- **Put/call ratio as a market-level contrarian timer (CBOE equity P/C extremes)**: short-sample, mostly post-hoc chart lore; no peer-reviewed return.
- **Covered calls as "income"**: accounting framing; the return is equity beta minus upside (Israelov-Nielsen 2014).
- **Option momentum for an individual**: zero after full spreads by the authors' own test (c15).
- **Delta-neutral straddle buy-and-hold on single names**: −17%/month gross average (Xing-Zhang summary); only the pre-earnings window is positive.
- **Tail hedging as alpha**: the buyer pays the index VRP (c24); use only as risk design.
- **Dispersion trade execution at retail**: 30+ legs and hedging; keep only the implied-correlation *signal* (c22).
- **GEX intraday regime trading**: inferred positions, intraday horizon, no published return (c10).
- **Pre-holiday option selling as a standalone trade**: round-trip costs exceed the 0.6% weekend effect; use as entry timing only (c26).
