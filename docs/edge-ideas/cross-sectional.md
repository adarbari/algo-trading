# Edge ideas, family A. Cross-sectional factors and anomalies

Researched 2026-10-17 (deep-research agents; index and ranking: [README.md](README.md)). Ideas, not edges: nothing here is filed or tested. Figures marked *not verified*, *nv*, *recalled* or *from memory* must be checked against the source before an edge document cites them (quality bar item 5, [edges-plan.md](../edges-plan.md)).


**Family summary (5 lines)**
1. The replication literature agrees on a small core: momentum, profitability/quality, investment/asset growth, net share issuance and (weaker, revived with intangibles) value replicate in value-weighted, large/mid-cap US data (Hou-Xue-Zhang 2020; Jensen-Kelly-Pedersen 2023; Chen-Zimmermann 2022). Size, seasonality, leverage and most "trading friction" anomalies do not.
2. Everything decays: McLean-Pontiff (2016) put the post-publication haircut at ~58% (26% out-of-sample + 32% post-publication); Chen-Velikov (JFQA 2023) find the *average* of 204 anomalies nets ~4 bp/month after spreads in the post-2000 era, the best ~10 bp, combinations ~20 bp. Plan on half the published number, at best.
3. Most of the alpha of the "mispricing" anomalies (IVOL, MAX, distress, accruals, issuance, asset growth) lives in the **short leg** and in small caps (Stambaugh-Yu-Yuan 2012/2015). For an individual without cheap borrow these become **avoid-lists and ranking tilts inside a long book**, not long-short trades.
4. Feasibility is high: Tiingo daily bars to 2010 (incl. delisted) plus SEC XBRL financials with real filing dates give point-in-time fundamentals that are *better* than the Compustat convention (no lagging guesswork). Missing: short interest, analyst coverage counts (maybe via FMP/Finnhub), supply-chain links.
5. Top picks to file: volatility-scaled / crash-managed momentum (variant of filed 12-1), residual momentum, cash-based operating profitability, net share issuance (buyback characteristic), frog-in-the-pan information discreteness, factor momentum, intangibles-adjusted value. Dead/decayed: accruals, Amihud illiquidity, F-score, raw size, classic B/M alone, 1-month raw reversal after costs.

Grading key used below (evidence): **Strong** = replicates in HXZ/JKP/CZ value-weighted large-cap tests *and* positive post-2010; **Promising** = replicates but post-publication evidence thin, mixed or short-leg-heavy; **Weak** = marginal or microcap-only; **Decayed** = was real, now ~zero; **Dead** = never robust. Where a number is from memory and not re-checked in this session it is marked *(approx., not verified)*.

---

### volatility_scaled_momentum — Risk-managed / crash-managed 12-1 momentum (variant of filed 12-1)
- **Thesis**: Hold the 12-1 momentum spread, but scale exposure down when momentum's own recent realised volatility is high (or after bear markets), which removes most momentum crashes and roughly doubles the Sharpe.
- **Mechanism**: Momentum crashes happen when the loser leg (high-beta, beaten-down junk) rebounds violently after a bear market; the strategy's beta turns sharply negative exactly when the market rallies (Daniel-Moskowitz "optionality"). Nobody arbitrages it because the crash is a short-leg event that requires leverage and shorting into a rally.
- **Persistence**: Still-known-and-still-there: the crash risk is a genuine conditional risk that mandates (long-only funds, benchmarked managers) cannot time; retail chases winners late. Scaling is a time-series overlay on a cross-sectional edge, so capacity is that of momentum itself.
- **Rule (source's own)**: Barroso & Santa-Clara: WML weight = (target vol 12% annualised) / (realised vol of WML over the past 126 trading days); monthly rebalance. Daniel & Moskowitz: weight = forecast mean / forecast variance using bear-market indicator (past 24-month market return < 0) interacted with trailing vol.
- **Evidence**: BSC 2015 (JFE), 1927-2011: Sharpe of WML from ~0.5 to ~1.0, max drawdown cut from ~-97% to ~-45% *(approx.)*; DM 2016 (JFE): dynamic strategy "approximately doubles" alpha and Sharpe. Post-publication: the 2020-2021 (Nov 2020 vaccine day) and 2022-2023 momentum reversals were exactly the predicted crash pattern; vol-scaling helped in 2020; Robeco (2023) and Alpha Architect confirm the pattern held. Long-only momentum (which an individual runs) has far less crash risk to begin with, because the crash is mostly the short leg.
- **Sources**: Barroso & Santa-Clara 2015 JFE "Momentum has its moments"; Daniel & Moskowitz 2016 JFE "Momentum crashes" https://business.columbia.edu/faculty/research/momentum-crashes; Alpha Architect summary https://alphaarchitect.com/avoiding-momentum-crashes/; Grobys, Ruotsalainen & Äijö 2018 Quant. Finance (industry version; echo not robust) https://ideas.repec.org/a/taf/quantf/v18y2018i10p1715-1733.html; Robeco 2023 "Taming momentum crashes" https://www.robeco.com/en-ch/insights/2023/02/quant-chart-taming-momentum-crashes.
- **Horizon / schedule**: 1-month hold, month_end rebalance; scaling recomputed every_session is fine (it is slow-moving).
- **Data needed**: daily bars (have, Tiingo to 2010); market index return for bear flag (have); nothing missing.
- **Individual fit**: Long-only top-decile momentum book, 30-50 names, scale gross exposure 0.5x-1x by the vol rule (or move to cash/ETF). Costs: ~100% annual turnover one way, fine with zero commissions. No shorting required.
- **Decoys / overlap**: This is the filed 12-1 momentum with a timing overlay; file as a *variant*. Decoy: the improvement may be just "less exposure in high-vol regimes", which helps most long-short strategies (test vol-scaling the market as a control).
- **Verdict**: **Strong**; feasibility **Ready**.

### residual_momentum — Idiosyncratic (factor-residual) momentum
- **Thesis**: Rank on the past 12-1 month *residual* return from a 3-factor regression (scaled by residual vol) instead of raw return; same premium, half the volatility, far smaller crashes.
- **Mechanism**: Raw momentum loads on whatever factor did well last year, so its crashes are factor reversals (market, size, value); residual momentum isolates the firm-specific underreaction (slow diffusion of firm news) that is the actual behavioural anomaly.
- **Persistence**: Behavioural (anchoring, slow analyst revisions); less crowded than raw momentum because index-based momentum products use raw returns. 2023 critiques (AEA) argue part of it is a hidden betting-against-beta plus factor-momentum effect, which is a decoy to test, not a death.
- **Rule (source's own)**: Each month, regress the past 36 monthly returns on FF3; take the residuals of months t-12..t-2; signal = mean residual / std residual; long top decile, short bottom; 1-month hold; monthly rebalance.
- **Evidence**: Blitz, Huij & Martens 2011 (J. Empirical Finance), US 1926-2009: long-short decile 11.2%/yr vs 10.3% for raw; Sharpe 0.90 vs 0.45; crash in 2009 small. Robeco reports the result holds in global samples and after publication (their own live products). 2023 AEA paper: confounded with BAB/factor momentum; 2023 theses: better Sharpe equal-weighted, not value-weighted in Sweden; FF5 residuals do not reduce crash risk further.
- **Sources**: Blitz, Huij & Martens 2011 "Residual momentum" (Quantpedia #136 https://quantpedia.com/Screener/Details/136); CXO summary https://www.cxoadvisory.com/momentum-investing/stripping-risks-from-a-stock-momentum-strategy/; AEA 2023 critique https://www.aeaweb.org/conference/2023/program/paper/8Ah8THYY; Blitz, Hanauer & Vidojevic 2020 "The idiosyncratic momentum anomaly" (Int. Rev. Economics & Finance; global confirmation) *(not re-verified this session)*.
- **Horizon / schedule**: 20 sessions; month_end.
- **Data needed**: daily/monthly bars (have); factor returns (compute our own SMB/HML from our universe, or download Ken French library as a reference series; a decision for the harness). Nothing missing.
- **Individual fit**: Long-only top decile, 30-60 names; turnover similar to momentum. Works without shorting. Good complement to raw momentum (lower correlation with the market's factor swings).
- **Decoys / overlap**: Overlaps filed 12-1 momentum (correlation ~0.6-0.7); decoy = low-beta tilt (test BAB-neutral version) and factor momentum (below).
- **Verdict**: **Strong**; **Ready**.

### cash_based_operating_profitability — Cash-based operating profitability (Ball-Gerakos-Linnainmaa-Nikolaev)
- **Thesis**: Firms with high *cash* operating profits to assets (operating profit minus accrual components) earn higher returns; this one measure subsumes both the profitability premium and the accruals anomaly.
- **Mechanism**: Investors extrapolate reported earnings; accrual-inflated earnings mean-revert. Removing accruals from profitability keeps the signal of durable cash generation and removes the part that reverses. Holders of expensive glamour and of low-profit "story" stocks are the systematically wrong side.
- **Persistence**: Profitability premium is partly risk-like (profitable firms are not cheap; Fama-French adopted it as RMW in 2015) and partly limits-to-arbitrage on the short side. It is well known yet still positive in the 2010s because the long leg (quality growth) is not an uncomfortable trade and the short leg (junk) is expensive to short.
- **Rule (source's own)**: Cash-based operating profitability = (Revenue - COGS - SG&A, excl. R&D) - ΔAR - ΔInventory - ΔPrepaid + ΔDeferred revenue + ΔAP + ΔAccrued expenses, scaled by total assets; annual update ~4 months after fiscal year end (we can use actual 10-K filing date); decile sorts; 12-month hold.
- **Evidence**: BGLN 2016 (JFE), 1963-2014: cash-based OP high-minus-low decile: VW raw spread 0.47%/month (t = 3.2; JFE Table 4A as recorded in Chen-Zimmermann's SignalDoc, NYSE breakpoints), three-factor alpha 90 bp/month for the decile and 72 bp for the quintile (t = 8.5 / 8.2; April 2015 working paper, VW, 1963-2013) **(verified; was "~0.4-0.5%/month", unsourced)**; it outperforms operating profitability (decile alpha 75 bp) and accruals add nothing once it is included (the cash-OP-neutral accruals strategy earns -4 bp/month, t = -0.4). Novy-Marx 2013 gross profitability: GP/A quintile spread 0.31%/month VW 1963-2010 (t = 2.5; Table 2a per the CZ SignalDoc) **(verified)**; HXZ 2020 replicate profitability-class anomalies as among the strongest; JKP 2023: "Profitability" and "Quality" themes replicate out of sample and across 93 countries. Post-2013 US: profitability/quality was among the best-performing factors of the 2010s (QMJ 1964-2023: 4.7%/yr, Sharpe 0.47 per Swedroe/AQR data).
- **Sources**: Ball, Gerakos, Linnainmaa & Nikolaev 2016 JFE 121(1) "Accruals, cash flows, and operating profitability in the cross section of stock returns", https://doi.org/10.1016/j.jfineco.2016.03.002 (April 2015 working paper https://www.ivey.uwo.ca/media/3775325/gerakos.pdf ); Chen & Zimmermann SignalDoc https://github.com/OpenSourceAP/CrossSection/blob/master/SignalDoc.csv ; Novy-Marx 2013 JFE "The other side of value" https://www.nber.org/system/files/working_papers/w15940/w15940.pdf; HXZ 2020 RFS https://ideas.repec.org/a/oup/rfinst/v33y2020i5p2019-2133..html; JKP 2023 JF https://nber.org/system/files/working_papers/w28432/w28432.pdf; Alpha Architect on QMJ https://alphaarchitect.com/value-and-quality-stocks/.
- **Horizon / schedule**: 250 sessions (annual) or quarterly refresh; on_event:10-K/10-Q filing for the update, month_end for the portfolio.
- **Data needed**: SEC financial statements (income, balance, cash flow; have) with filing dates (have via filings table); shares outstanding (have). All present; XBRL coverage from ~2009-2011 limits history to ~14 years (fine, >40 independent monthly events).
- **Individual fit**: Long-only top quintile within S&P 500 + large Nasdaq, 40-80 names, ~30% annual turnover; excellent fit. No shorting.
- **Decoys / overlap**: Overlaps gross profitability, QMJ, accruals (it is designed to subsume them). Decoy: a growth/large-cap tech tilt in 2010-2024 (control with sector-neutral sorts).
- **Verdict**: **Strong**; **Ready** (needs the SEC-financials-to-feature plumbing already planned).

### quality_minus_junk — Composite quality (profitability + growth + safety) as a characteristic
- **Thesis**: Rank on a z-scored composite of profitability, profit growth and safety (low beta, low leverage, low earnings volatility, low bankruptcy risk); high quality earns more and is a reliable long-only tilt.
- **Mechanism**: Quality is under-priced relative to its (Gordon-growth) justified premium; investors overpay for junk because of lottery preferences and benchmark-relative incentives (leverage-constrained managers prefer high-beta junk; see BAB).
- **Persistence**: Risk-based explanations are weak (quality has *lower* beta and did well in crises); crowding is real since 2015 (quality ETFs) but the 2010s and 2022 showed it still worked. Capacity huge (mega-cap long leg).
- **Rule (source's own)**: Asness, Frazzini & Pedersen: quality = z(profitability) + z(growth) + z(safety); long top 30%, short bottom 30%, size-neutral; monthly rebalance using data lagged to be public.
- **Evidence**: AFP 2019 (Review of Finance), US 1957-2016 and 24 countries: QMJ US ~0.39%/month, t > 5 *(approx.)*; 1964-2023 US 4.7%/yr, Sharpe 0.47 (Swedroe summarising AQR data, 2024). JKP: Quality theme replicates. Post-2019: strong 2019-2021 and 2022, lagged in 2023 (AI mega-caps dominated, though many are high-quality).
- **Sources**: Asness, Frazzini & Pedersen 2019 Review of Finance "Quality minus junk" (AQR data library updates monthly); Alpha Architect/Swedroe https://alphaarchitect.com/value-and-quality-stocks/; JKP 2023; Novy-Marx 2014 "Quality investing" (shows most quality definitions are dominated by gross profitability) *(not re-verified)*.
- **Horizon / schedule**: 250 sessions; month_end.
- **Data needed**: SEC financials (have), daily bars for beta/vol (have), shares outstanding (have). Nothing missing; needs a 3-5 year window of financials for growth, which our XBRL history supports.
- **Individual fit**: Ideal long-only core tilt, very low turnover, large caps. No shorting needed.
- **Decoys / overlap**: Largely gross/cash profitability (above) plus low vol (below); test whether the composite beats cash-based OP alone (Novy-Marx says mostly not).
- **Verdict**: **Strong** (as a tilt); **Ready**.

### net_share_issuance — Net share issuance / buyback characteristic
- **Thesis**: Firms shrinking their share count (net buybacks) outperform; firms issuing (SEOs, option exercise, stock acquisitions) underperform for 1-3 years.
- **Mechanism**: Managers time the market: they issue when they believe shares are overvalued and repurchase when undervalued; investors do not discount this fully. Issuers are also often glamour / high asset growth.
- **Persistence**: One of the few anomalies Fama-French (2008, "Dissecting anomalies") found robust across all size groups, and it entered their 5-factor model indirectly via investment. Partially mechanical (dilution) and partially informed-manager; it persists because the short leg (serial issuers) is costly and the long leg is boring.
- **Rule (source's own)**: Pontiff & Woodgate 2008: net issuance = log change in split-adjusted shares outstanding over the prior 12 (or 36) months; decile sorts; 1-month hold, monthly rebalance. Daniel-Titman 2006 "composite issuance" = 5-year log market-cap growth minus 5-year log return.
- **Evidence**: Pontiff & Woodgate 2008 JF: post-1970 issuance predicts returns more significantly than size, B/M or momentum, with no significant power pre-1970 **(verified: abstract)**; the decile spread **(figure dropped: not stated in the JF abstract / RePEc listing; full text not accessible)**; FF 2008: significant in micro, small and big caps. HXZ 2020: net share issuance among the anomalies that replicate; JKP: part of the "Low leverage / Investment" family that replicates. Post-publication: still positive 2008-2020 in CZ data; the S&P 500 Buyback Index (the 100 highest buyback-ratio names, equal weight) lagged the S&P 500 over the decade to 2024, most of all in the growth run since 2020 (Barron's, 30 Dec 2024, citing B. Safalow; no numeric return stated) **(corrected; was "outperformed 2000-2015 then lagged 2017-2024")**.
- **Sources**: Pontiff & Woodgate 2008 JF 63(2) "Share issuance and cross-sectional returns", https://doi.org/10.1111/j.1540-6261.2008.01335.x ; Barron's (Alpert, 2024-12-30) "Buybacks Aren't Always Bullish", mirror https://www.itiger.com/news/2495567006 ; Daniel & Titman 2006 JF "Market reactions to tangible and intangible information"; Fama & French 2008 JF "Dissecting anomalies"; Chen & Zimmermann 2022 CFR open-source data https://papers.ssrn.com/abstract=3604626 (predictor "ShareIss1Y", "ShareIss5Y").
- **Horizon / schedule**: 20-60 sessions; month_end (signal updates on_event:10-Q/10-K cover-page share count).
- **Data needed**: shares outstanding history (have, SEC; also Tiingo fundamentals), split data (have). Nothing missing.
- **Individual fit**: Long-only "shrinking share count" screen inside large caps; a natural *filter* on other screens (exclude heavy issuers). No shorting.
- **Decoys / overlap**: Overlaps asset growth / investment (issuance funds investment) and value (issuers are expensive). Decoy: the 2010-2024 buyback era is also the mega-cap era.
- **Verdict**: **Strong**; **Ready**.

### frog_in_the_pan — Information discreteness (continuous-information momentum)
- **Thesis**: Momentum is strong when the past-year return accumulated through many small same-sign days (continuous information) and weak/reversing when it came from a few big jumps.
- **Mechanism**: Limited attention: gradual information attracts less attention than salient jumps, so underreaction is largest for "frogs in the pan"; jumps are over-reacted to and reverse.
- **Persistence**: Attention is a scarce resource; the signal is subtle, so less arbitraged than raw momentum; still has the momentum crash exposure.
- **Rule (source's own)**: Da, Gurun & Warachka 2014: ID = sign(PRET) × (%negative days - %positive days) over the 12-month formation window (skip the last month); within momentum winners/losers, sort on ID; long continuous-info winners, short continuous-info losers; 6-month hold (overlapping).
- **Evidence**: DGW 2014 (RFS), 1927-2007: momentum among continuous-information stocks ~8.9%/yr vs ~2.9%/yr among discrete-information stocks over 6 months *(approx., not verified)*; the continuous portfolio's profits persist beyond a year while the discrete ones reverse. Replication: Chen-Zimmermann include it (predictor "frogs in the pan"/InfoDiscreteness) with t > 2 in their sample; independent post-2007 US evidence is thin — the fact that the 2020-2021 jump-driven meme/vaccine names reversed fits.
- **Sources**: Da, Gurun & Warachka 2014 RFS "Frog in the pan: continuous information and momentum"; Chen & Zimmermann 2022 CFR; Alpha Architect coverage (2014) *(URL not retrieved)*.
- **Horizon / schedule**: 120 sessions, overlapping; month_end.
- **Data needed**: daily bars (have). Nothing missing.
- **Individual fit**: Long-only continuous-information winners, 30 names; low extra turnover over plain momentum. No shorting.
- **Decoys / overlap**: Variant of filed 12-1; decoy = low-IVOL tilt (continuous-info winners have smoother paths, i.e. lower IVOL; control for IVOL and MAX).
- **Verdict**: **Promising**; **Ready**.

### factor_momentum — Momentum in factor (characteristic-portfolio) returns
- **Thesis**: Factors that did well over the past 1-12 months keep doing well next month; rotate the long-only tilt (value / momentum / quality / low vol / size...) toward last year's winning factors.
- **Mechanism**: Factor premia are time-varying and persistent (mispricing that corrects slowly; flows into factor products); individual-stock momentum is largely the sum of this factor autocorrelation (Ehsani-Linnainmaa).
- **Persistence**: Factor timing is "sinful" in the industry, so few funds do it; the persistence is at a 1-12 month horizon that benchmark-relative managers cannot exploit.
- **Rule (source's own)**: Ehsani & Linnainmaa 2022: each month, for each of ~20 factors, go long the factor if its past 12-month return > 0, else short (time-series version); or Gupta & Kelly 2019: scale factor weights by past 1-month (or 12-month) return.
- **Evidence**: EL 2022 (JF): average factor earns 6 bp/month after a losing year vs 51 bp/month after a winning year (1963-2019); factor momentum subsumes stock momentum. Gupta & Kelly 2019 (JPM) "Factor momentum everywhere": time-series factor momentum Sharpe ~0.8-1.0 across 65 factors in US and global *(approx., not verified)*. Arnott, Clements, Kalesnik & Linnainmaa 2023 (RFS) "Factor momentum": industry momentum is explained by factor momentum. Post-publication: 2022 (value/low-vol regime) and 2024 (momentum/quality) were persistent regimes consistent with the effect; 2023's abrupt flip hurt it.
- **Sources**: Ehsani & Linnainmaa 2022 JF https://www.nber.org/papers/w25551; Alpha Architect summary https://alphaarchitect.com/is-momentum-a-separate-factor/; Gupta & Kelly 2019 JPM; Arnott et al. 2023 RFS "Factor momentum" (earlier SSRN 2018) *(not re-verified)*.
- **Horizon / schedule**: 20 sessions; month_end.
- **Data needed**: we must build our own long-short factor return series from our universe (value, momentum, profitability, investment, low vol, size, issuance...) — all computable from Tiingo + SEC. Alternatively download Ken French / JKP factor series as reference inputs (a "data we can fetch" decision). Nothing fundamentally missing.
- **Individual fit**: Implement as rotating which long-only tilt gets weight; or via factor ETFs (MTUM, QUAL, VLUE, USMV, SIZE etc., which we hold holdings for). Very low cost, high capacity.
- **Decoys / overlap**: Overlaps every other factor here and with the filed 12-1 momentum; decoy = "just momentum applied to ETFs" (test against sector momentum and stock momentum).
- **Verdict**: **Promising**; **Ready** (needs factor-return construction work).

### intangibles_adjusted_value — Value with capitalised intangibles (iHML / intangible value)
- **Thesis**: Add capitalised R&D and a share of SG&A (knowledge + organisation capital) to book equity before sorting on book-to-market; the adjusted value premium is larger and did not die in 2007-2020.
- **Mechanism**: Accounting expenses intangibles, so modern asset-light firms look "expensive" on raw B/M; raw HML now sorts on industry/business model rather than cheapness. Value investors mechanically using raw B/M are the wrong side; fixing the measure recovers the original "cheap-vs-dear" mispricing (extrapolation of growth).
- **Persistence**: The value premium's own persistence is debated (risk vs extrapolation); the intangible fix removes a measurement error that has grown with the economy's shift to intangibles, which the big value indices (Russell, MSCI) still mostly ignore.
- **Rule (source's own)**: Eisfeldt, Kim & Papanikolaou 2022: intangible book = book equity + capitalised R&D (perpetual inventory, 15% depreciation) + 30% of SG&A capitalised (20% depreciation); HML construction otherwise as Fama-French (2x3 sorts, June rebalance). Arnott, Harvey, Kalesnik & Linnainmaa 2021 use a similar iHML.
- **Evidence**: EKP 2022 (CFR): intangible value factor prices as well as or better than HML with substantially higher returns, including in recent decades when HML underperformed; sorts better within industries. Arnott et al. 2021 (FAJ) "Reports of value's death may be greatly exaggerated": most of value's 2007-2020 drawdown is from cheapening (valuation spread widened), not profitability; iHML cut the drawdown. Classic HML: FF data 1963-2024 ~0.3%/month, but ~0 since 2007 *(approx.)*; HXZ: B/M-type value replicates but is weaker than investment/profitability; JKP: Value theme replicates. 2021-2022 value rebound, 2023-2024 lag.
- **Sources**: Eisfeldt, Kim & Papanikolaou 2022 CFR "Intangible value" https://nowpublishers.com/article/Details/CFR-0113, NBER w28056 https://nber.org/papers/w28056; Arnott, Harvey, Kalesnik & Linnainmaa 2021 FAJ; Israel, Laursen & Richardson 2021 JPM "Is (systematic) value investing dead?" *(not re-verified)*; Peters & Taylor 2017 JFE "Intangible capital and the investment-q relation" (the capitalisation recipe).
- **Horizon / schedule**: 250 sessions; annual rebalance (June) or quarterly with filings.
- **Data needed**: SEC income statement R&D and SG&A history (have, from ~2009; the perpetual-inventory stock needs ~8-10 years, so usable from ~2017-2018 onward, or seed with Peters-Taylor-style initial stock); book equity, shares, prices (have).
- **Individual fit**: Long-only cheap-quality screen inside large caps; low turnover. No shorting.
- **Decoys / overlap**: Overlaps profitability (intangible-heavy firms are profitable) and classic value; decoy = sector tilt (test industry-neutral). Composite value (E/P, CF/P, sales/P, EV/EBITDA) is the practitioner alternative and should be tested alongside.
- **Verdict**: **Promising** (classic B/M alone: **Decayed**); **Ready** (history limited by R&D stock build-up).

### asset_growth — Investment / asset growth anomaly
- **Thesis**: Firms whose total assets grew fastest last year earn low returns; slow-growth or shrinking firms earn high returns.
- **Mechanism**: Over-investment by empire-building managers and investor extrapolation of growth; also q-theory: low discount rates cause high investment (rational side).
- **Persistence**: Became the CMA factor (FF 2015) and the investment factor in q-models — "known" yet still carrying a premium in large caps through the 2010s, partly because it is a short-leg / glamour-avoidance effect.
- **Rule (source's own)**: Cooper, Gulen & Schill 2008: AG = total assets(t-1)/total assets(t-2) - 1; sort in June into deciles; hold 12 months; equal- and value-weighted.
- **Evidence**: CGS 2008 (JF), 1968-2003: decile spread ~1.7%/month EW, ~1.0%/month VW *(approx., not verified)*. HXZ: investment anomalies among the robust group; JKP: Investment theme replicates. Critiques: Cooper, Gulen & Ion (2018 WP) show the factor's pricing power drops when "traditional" investment measures are used, i.e. the AG measure captures financing (issuance) as much as investment. Post-publication: CMA ~0.2%/month 2008-2024, weak since 2017 *(approx.)*.
- **Sources**: Cooper, Gulen & Schill 2008 JF "Asset growth and the cross-section of stock returns" (Quantpedia https://quantpedia.com/strategies/asset-growth-effect); Cooper, Gulen & Ion WP https://finance.unibocconi.eu/sites/default/files/files/media/attachments/Cooper_Gulen_Ion_Manuscript20190507084119.pdf; HXZ 2020; Morningstar discussion https://www.morningstar.com/stocks/rethinking-investment-factors-are-asset-growth-models-misguided.
- **Horizon / schedule**: 250 sessions; annual (June) or on_event:10-K.
- **Data needed**: SEC balance sheet total assets (have). Nothing missing.
- **Individual fit**: Mostly an *avoid* filter (exclude top-decile asset growers, especially acquisitive issuers); long-only low-growth leg is a value/profitability proxy. No shorting.
- **Decoys / overlap**: Heavy overlap with net issuance and value; decoy = acquisitions/IPOs (test ex-M&A).
- **Verdict**: **Promising** (as avoid filter); **Ready**.

### industry_momentum — Industry / sector momentum
- **Thesis**: Industries that outperformed over the past 6-12 months continue to outperform over the next 1-6 months; a chunk of stock momentum is industry momentum.
- **Mechanism**: Slow diffusion of industry-wide news and institutional sector rotation flows; analysts update sector views gradually.
- **Persistence**: Debated: Arnott et al. show industry momentum is spanned by factor momentum; Grobys et al. find the industry "echo" not robust across subsamples. Still the simplest and cheapest momentum to trade via sector ETFs.
- **Rule (source's own)**: Moskowitz & Grinblatt 1999: 20 value-weighted industries; rank on past 6-month return; long top 3, short bottom 3; hold 6 months (1-month version also). Quantpedia sector-rotation: top 3 of ~10 SPDR sectors by 12-month return, monthly.
- **Evidence**: MG 1999 (JF), 1963-1995: ~0.43%/month top-minus-bottom-3 at 6/6 *(approx., not verified)*, survives size, B/M, stock momentum. Post-publication: Quantpedia reports the sector ETF version positive 2000-2020 but with weaker Sharpe (~0.3-0.5) *(not verified)*; Arnott-Clements-Kalesnik-Linnainmaa 2023 RFS: subsumed by factor momentum; Grobys et al. 2018 QF: not robust in subsamples; Europe weak (Nijman et al. 2004).
- **Sources**: Moskowitz & Grinblatt 1999 JF "Do industries explain momentum?" https://ideas.repec.org/a/bla/jfinan/v54y1999i4p1249-1290.html; Quantpedia sector momentum https://quantpedia.com/strategies/sector-momentum-rotational-system; Grobys, Ruotsalainen & Äijö 2018; Arnott et al. 2023 RFS.
- **Horizon / schedule**: 20-120 sessions; month_end.
- **Data needed**: industry classification (have via reference / SIC from SEC), sector ETF bars (have). Nothing missing.
- **Individual fit**: Trivial to implement with 11 sector ETFs long-only (top 3); minimal cost. Capacity unlimited.
- **Decoys / overlap**: Subsumed by factor momentum + stock momentum; decoy = tech-sector trend 2010-2024. File as a *variant* of filed momentum.
- **Verdict**: **Promising** (weak standalone); **Ready**.

### fifty_two_week_high — Nearness to the 52-week high
- **Thesis**: Stocks trading near their 52-week high outperform those far below it over the next 6-12 months, and this ranking explains much of price momentum without the long-run reversal.
- **Mechanism**: Anchoring: traders are reluctant to push a price through a salient reference point (the high), so good news is underreacted to near the high; bad news is underreacted to near the low.
- **Persistence**: Behavioural anchor that cannot be arbitraged away without taking momentum-like risk; still used in practice (breakout systems). Weaker in emerging markets/indices.
- **Rule (source's own)**: George & Hwang 2004: ratio = price / 52-week high; long top 30%, short bottom 30%; 6-month hold; exclude January in some tests.
- **Evidence**: GH 2004 (JF), 1963-2001: roughly 0.45%/month long-short, stronger ex-January, no reversal after 1-5 years *(approx., not verified)*. George, Hwang & Li 2018 (JFE) tie it to q-theory and show it survives in the q-factor model. Chen-Zimmermann include "High52" (significant). Post-2004 US evidence: positive but weaker; emerging-market indices fail (Malin & Bornholt 2010).
- **Sources**: George & Hwang 2004 JF "The 52-week high and momentum investing"; Alpha Architect on GHL https://alphaarchitect.com/52-week-high-q-factor-investment-model/; Malin & Bornholt 2010 https://research-repository.griffith.edu.au/items/41995ba4-ea62-565b-bc6a-9233b7978ae0; Bhootra & Hur 2013 JBF "The timing of 52-week high price and momentum" (recency of the high matters) *(not re-verified)*.
- **Horizon / schedule**: 120 sessions; month_end (compute every_session; feature is cheap).
- **Data needed**: daily bars (have). Nothing missing.
- **Individual fit**: Long-only near-high screen; combine with momentum (GH say they are complementary). Costs low.
- **Decoys / overlap**: Overlaps 12-1 momentum (ρ ~0.5-0.6) and low vol (near-high stocks are calmer). Variant of filed momentum.
- **Verdict**: **Promising**; **Ready**.

### stock_time_series_momentum — Time-series (absolute) momentum on single stocks
- **Thesis**: A stock's own past 12-month excess return sign predicts its next-month return (long if positive, flat/short if negative), independent of its rank vs. peers.
- **Mechanism**: Same underreaction as cross-sectional momentum plus a time-varying market exposure: TSMOM is long the market after up-years and short after down-years, so part of its return is market timing.
- **Persistence**: Goyal & Jegadeesh 2018 show the difference between TS and CS momentum in stocks is entirely the net long position (market timing); the stock-level TS edge beyond CS momentum is small.
- **Rule (source's own)**: Moskowitz, Ooi & Pedersen 2012 (futures): sign of past 12-month excess return, vol-scaled to 40% annual, 1-month hold. Stock version (Lim, Wang & Yao 2018): same rule on individual stocks, monthly.
- **Evidence**: MOP 2012 (JFE) for futures: ~1.6%/month vol-scaled *(approx.)*. Goyal & Jegadeesh 2018 (RFS): in stocks, TS beats CS only because of its time-varying net long exposure; equalising exposure removes the difference. Lim, Wang & Yao 2018 (JBF) report stock TSMOM positive 1927-2014 *(not verified)*. Post-2018: 2022 was good for TS-style trend, 2023 a whipsaw.
- **Sources**: Moskowitz, Ooi & Pedersen 2012 JFE "Time series momentum"; Goyal & Jegadeesh 2018 RFS "Cross-sectional and time-series tests of return predictability: what is the difference?"; Lim, Wang & Yao 2018 JBF "Time-series momentum in nearly 100 years of individual stock returns" *(not re-verified)*.
- **Horizon / schedule**: 20 sessions; month_end.
- **Data needed**: daily bars (have); risk-free rate (have, Treasury). Nothing missing.
- **Individual fit**: Natural long-only filter ("only hold names above their own 12-month trailing return of zero / above 200-day MA"); cheap. Zero shorting.
- **Decoys / overlap**: Market timing (control: market 12-month sign) + filed 12-1 momentum. Likely to be judged a decoy of both.
- **Verdict**: **Promising** as a filter, **Weak** as standalone; **Ready**.

### idiosyncratic_volatility_and_max — IVOL puzzle and MAX (lottery) stocks (short leg: avoid-list)
- **Thesis**: Stocks with high idiosyncratic volatility or an extreme best daily return last month earn very low subsequent returns; the effect is almost entirely in the short leg among over-priced, hard-to-short names.
- **Mechanism**: Lottery demand (retail buys skewness) plus arbitrage asymmetry: overpricing in high-IVOL names is not shorted away because IVOL *is* the arbitrage risk (Stambaugh-Yu-Yuan). Highest when sentiment is high.
- **Persistence**: Short-sale constraints and retail lottery preference are structural; the anomaly persisted post-publication (Alpha Architect 2020) and was spectacular in 2021 (meme reversal). But Hou-Xue-Zhang classify IVOL/MAX as weak in VW large caps; JKP: "Low risk" theme replicates, but as a long-leg low-vol effect.
- **Rule (source's own)**: Ang, Hodrick, Xing & Zhang 2006: IVOL = std of daily FF3 residuals over the prior month; quintiles; 1-month hold. Bali, Cakici & Whitelaw 2011: MAX = largest daily return in the prior month (or mean of top 5); deciles; 1-month hold.
- **Evidence**: AHXZ 2006 (JF), 1963-2000: VW top-minus-bottom quintile ~ -1.06%/month *(approx.)*. BCW 2011 (JFE), 1962-2005: low-minus-high MAX decile > 1%/month. Post-2009: mixed internationally (Turkey 2011-2017 none; Korea yes); Gorman et al. 2021 confirm underperformance after high MAX; US post-publication alive per Alpha Architect 2020 but concentrated in microcaps; HXZ: fails in VW large caps.
- **Sources**: Ang, Hodrick, Xing & Zhang 2006 JF; Bali, Cakici & Whitelaw 2011 JFE https://www.nber.org/papers/w14804.pdf; Stambaugh, Yu & Yuan 2015 JF "Arbitrage asymmetry and the idiosyncratic volatility puzzle" https://ideas.repec.org/a/bla/jfinan/v70y2015i5p1903-1948.html; Alpha Architect "IVOL puzzle then and now" https://alphaarchitect.com/2020/01/the-idiosyncratic-volatility-puzzle-then-and-now; Gorman et al. 2021 CFR https://cfr.ivo-welch.info/published/papers/gorman2021could.pdf.
- **Horizon / schedule**: 20 sessions; month_end.
- **Data needed**: daily bars (have). Nothing missing.
- **Individual fit**: Not a long trade; use as an **exclusion filter** on every long screen (drop top-decile IVOL/MAX, especially small caps) and as a candidate for buying puts on lottery names when IV is cheap (ties to our options data). Shorting not practical (borrow cost is the mechanism).
- **Decoys / overlap**: Size, price level, distress, low volatility: all the same cluster. Decoy = the small-cap lottery cluster, not a separate effect.
- **Verdict**: **Promising** (as avoid filter / options overlay), **Weak** as standalone VW; **Ready**.

### betting_against_beta_low_vol — Low beta / low volatility
- **Thesis**: Low-beta and low-volatility stocks earn higher risk-adjusted (and historically similar raw) returns than high-beta stocks; the security market line is too flat.
- **Mechanism**: Leverage constraints: investors who want more return buy high-beta instead of levering low-beta, bidding high-beta up (Frazzini-Pedersen); benchmark-relative managers avoid low-vol tracking error; lottery demand for high-vol.
- **Persistence**: Structural constraints persist, but the anomaly became crowded (USMV, SPLV, 2012-2019 inflows), valuations of low-vol rose, and low-vol indices lagged their parents from late 2019 through 2024 while failing to protect in March 2020 (Robeco 2021; S&P 2025). Novy-Marx & Velikov 2022 show BAB's reported Sharpe came largely from micro-cap overweights via its rank weighting; costs cut profitability ~60%.
- **Rule (source's own)**: Frazzini & Pedersen 2014: rank on shrunk beta (5-year correlation, 1-year vol), rank-weight long low-beta / short high-beta, each leg levered to beta 1, monthly. Low-vol version (Blitz-van Vliet 2007): decile sort on 3-year volatility, long low decile.
- **Evidence**: FP 2014 (JFE), 1926-2012: BAB Sharpe 0.78; FF5 alpha only 16 bp/month, insignificant (NMV critique). Blitz & van Vliet 2007: low-vol decile beats high-vol with far lower risk 1986-2006 *(approx.)*. JKP: Low-risk theme replicates (one of the strongest). Recent: lagged 2019-2024, flat-to-positive on a risk-adjusted basis over 25 years (S&P: vol 11.6% vs 15.3%, beta 0.7).
- **Sources**: Frazzini & Pedersen 2014 JFE "Betting against beta"; Novy-Marx & Velikov 2022 JFE "Betting against betting against beta" (Alpha Architect https://alphaarchitect.com/betting-against-beta-bab-construction/); Robeco 2021 https://www.robeco.com/en-uk/insights/2021/11/low-volatility-defies-the-basic-finance-principles-of-risk-and-reward; S&P Indexology 2025 https://www.indexologyblog.com/2025/04/09/expectations-and-anomalies/; Han 2019 CFR "Understanding the low-volatility anomaly" https://cfr.ivo-welch.info/published/papers/han2019understanding.pdf.
- **Horizon / schedule**: 20-60 sessions; month_end.
- **Data needed**: daily bars (have). Nothing missing.
- **Individual fit**: Long-only low-vol book is easy and cheap; the premium is in *risk-adjusted* terms, so for an un-levered individual it mainly lowers drawdown rather than raising return. Pairs well with quality.
- **Decoys / overlap**: Quality, size (NMV), value tilts (2000s), interest-rate sensitivity (bond proxy 2010-2021). High overlap with QMJ safety.
- **Verdict**: **Promising** (risk-adjusted), **Decayed** in raw terms 2019-2024; **Ready**.

### short_term_residual_reversal — 1-month (residual) reversal
- **Thesis**: Last month's losers (relative to their factor-implied return) beat last month's winners next month; the residual version doubles the Sharpe of raw reversal and survives costs in large caps.
- **Mechanism**: Liquidity provision: reversal returns are the compensation to those who absorb uninformed order-flow imbalances (Nagel 2012); it is the return of being the market-maker of last resort at a monthly horizon.
- **Persistence**: Compensation for providing liquidity when nobody else will; strongest in stress. But raw 1-month reversal's gross return has fallen since the 1990s/2000s as market-making became cheaper (Chen-Velikov place short-term reversal among the most cost-sensitive), and Medhat-Schmeling (2022) show high-turnover stocks exhibit short-term *momentum*, not reversal.
- **Rule (source's own)**: Jegadeesh 1990: rank on past 1-month return, long bottom decile, short top; 1-month hold. Blitz, Huij, Lansdorp & Verbeek 2013: residuals from a 36-month FF3 regression, standardised by residual vol; deciles; monthly; large caps > NYSE median.
- **Evidence**: Jegadeesh 1990: ~2%/month raw spread 1934-1987 *(approx.)*, mostly microcaps; BHLV 2013 (JFM), 1926-2008: residual reversal roughly twice the risk-adjusted return of conventional, significant net of costs in large caps post-1990. Frazzini-Israel-Moskowitz 2015: reversal has the lowest capacity (~$9bn US). Medhat & Schmeling 2022 RFS: reversal is in low-turnover illiquid names; high-turnover names show short-term momentum. Post-2013: Robeco runs it live; public post-publication US numbers not verified.
- **Sources**: Blitz, Huij, Lansdorp & Verbeek 2013 JFM "Short-term residual reversal" https://repub.eur.nl/pub/40707; Nagel 2012 RFS "Evaporating liquidity"; Medhat & Schmeling 2022 RFS "Short-term momentum" (Alpha Architect https://alphaarchitect.com/short-term-momentum/); De Groot, Huij & Zhou 2012 JBF (costs) ; Chen & Velikov 2023 JFQA https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/zeroing-in-on-the-expected-returns-of-anomalies/945133D5A3ECEEAF466AEE91551FD225.
- **Horizon / schedule**: 20 sessions; month_end (or weekly).
- **Data needed**: daily bars (have). Turnover (have: volume/shares). Nothing missing.
- **Individual fit**: Poor as a core strategy (200%+ monthly turnover, needs shorts); usable as a *timing* input on entries into other screens ("buy the quality/momentum name after its down month"). Long-only residual-loser basket in S&P 500 is testable.
- **Decoys / overlap**: Liquidity/size; earnings-announcement reactions (exclude announcement months). Overlaps filed PEAD (opposite sign after earnings news!): reversal after *non-news* moves, drift after news — a good joint test.
- **Verdict**: **Promising** (residual, large-cap, as timing input), raw version **Decayed** after costs; **Ready**.

### short_term_momentum_high_turnover — Medhat-Schmeling short-term momentum in liquid names
- **Thesis**: Among the highest-turnover stocks, last month's winners *continue* next month (the reversal sign flips); the effect is strongest in the most liquid names, so it is cheap to trade.
- **Mechanism**: In heavily traded names, last month's return reflects information absorbed by many traders (not liquidity shocks), and underreaction dominates; in thin names the liquidity-provision reversal dominates.
- **Persistence**: Published 2022 (RFS); liquid-name alpha is the most vulnerable to arbitrage. Robust across 22 developed markets in the paper, so not an artefact.
- **Rule (source's own)**: Each month double-sort: turnover (volume / shares) deciles × past-1-month return deciles; among the top turnover decile, long past-month winners, short losers; 1-month hold.
- **Evidence**: Medhat & Schmeling 2022 (RFS), US 1963-2018: in the top-turnover decile, winners minus losers ~1.4%/month *(approx., not verified)*, t > 4, FF5+momentum alpha significant; replicated in international data. Post-2018: no independent evidence found; 2021-2023 meme/high-turnover episodes argue for caution (big reversals).
- **Sources**: Medhat & Schmeling 2022 RFS "Short-term momentum" https://alphaarchitect.com/short-term-momentum/; Alpha Architect "Alpha from short-term signals" https://alphaarchitect.com/alpha-from-short-term-signals/.
- **Horizon / schedule**: 20 sessions; month_end.
- **Data needed**: daily bars + volume + shares outstanding (have). Nothing missing.
- **Individual fit**: Long-only high-turnover winners, large caps; monthly turnover ~100%; fine on zero commission. No shorting.
- **Decoys / overlap**: Momentum (12-1) and attention/retail flow; a decoy is "high turnover = large-cap tech 2010-2024".
- **Verdict**: **Promising**; **Ready**.

### same_month_seasonality — Heston-Sadka same-calendar-month return seasonality
- **Thesis**: A stock's return in a given calendar month predicts its return in the same month in later years (lags 12, 24, ... up to 240 months), earning ~1%/month long-short.
- **Mechanism**: Firm-specific and factor-level seasonal patterns (dividend months, fiscal-year effects, index/tax-driven flows, seasonal earnings) that investors do not arbitrage because each month's signal is weak and the pattern is non-intuitive; Keloharju et al. show it is mostly common factor seasonality that reverses in other months (sum to zero within the year).
- **Persistence**: JKP's "Seasonality" theme is one of the three that **fail** to replicate under their Bayesian test; Heston-Sadka 2008 and KLN 2016 are strong in-sample. The effect is offset by seasonal reversals in the other 11 months (KLN 2021), so a single-month trade is noisy.
- **Rule (source's own)**: Heston & Sadka 2008: rank on the average return in the same calendar month over the prior 20 years (lags 12, 24, ..., 240); deciles; 1-month hold, monthly. KLN 2016: same, with 13%/yr.
- **Evidence**: HS 2008 (JFE), 1965-2002: long-short ~1.1%/month *(approx.)*; KLN 2016 (JF): ~13%/yr; KLN 2021 (JFE): seasonalities and reversals net to zero across the year, mispricing not risk. Post-publication: JKP replication failure for the seasonality theme (in VW, implementable construction); Chen-Zimmermann include it as significant on EW.
- **Sources**: Heston & Sadka 2008 JFE "Seasonality in the cross-section of stock returns"; Keloharju, Linnainmaa & Nyberg 2016 JF "Return seasonalities" https://www.nber.org/papers/w20815.pdf; KLN 2021 JFE "Are return seasonalities due to risk or mispricing?"; JKP 2023 (CXO summary of failing themes https://cxoadvisory.com/?p=35142).
- **Horizon / schedule**: 20 sessions; month_end.
- **Data needed**: monthly returns to 2010 (have) — but the signal wants 10-20 years of history, so only ~5-14 lags are available from 2015 onward. History is the constraint.
- **Individual fit**: Low cost, long-only top decile; but noisy and small per-month edge; best as a secondary ranking tiebreaker.
- **Decoys / overlap**: January/small-cap effect, dividend months, earnings months (our earnings calendar can control). Factor seasonality (sector).
- **Verdict**: **Weak** (JKP failure, short history); **Ready** but low priority.

### size_conditional_on_quality — Small caps, but only quality ones
- **Thesis**: The raw size premium is gone, but small *quality* stocks (profitable, low leverage, stable) still beat large ones; junk small caps drag the size effect down.
- **Mechanism**: Small caps are dominated by junk (unprofitable, distressed, lottery-like) whose underperformance masks a real size premium; controlling for quality uncovers it (Asness et al. 2018). Mechanism of the premium itself: illiquidity, neglect, and risk.
- **Persistence**: Debated; raw SMB ~0 since 1983 and Russell 2000 badly lagged the S&P 500 2010-2024; HXZ and JKP find size does not replicate as a standalone theme. The conditional claim rests largely on AQR's work.
- **Rule (source's own)**: Asness, Frazzini, Israel, Moskowitz & Pedersen 2018: SMB regressed on QMJ; or double sort size × quality, long small-quality.
- **Evidence**: AFIMP 2018 (JFE), 1957-2012 US + 24 countries: size premium becomes large and significant (t > 4) after controlling for QMJ *(approx.)*. Post-publication 2013-2024: small caps lagged massively; small-quality (e.g. S&P 600 which has an earnings screen) beat the Russell 2000 but not the S&P 500 *(not verified)*. JKP: Size theme fails.
- **Sources**: Asness, Frazzini, Israel, Moskowitz & Pedersen 2018 JFE "Size matters, if you control your junk"; JKP 2023; Alpha Architect (various) on the size premium *(URL not retrieved)*.
- **Horizon / schedule**: 250 sessions; month_end.
- **Data needed**: market cap (have), SEC financials (have). Our universe is S&P 500 + Nasdaq-listed + ETFs, so "small" means small Nasdaq names; no Russell 2000 coverage (brief: blocked) but the Nasdaq small/mid tail is enough.
- **Individual fit**: Long-only small-quality screen; costs higher (spreads), capacity irrelevant for an individual.
- **Decoys / overlap**: It is quality (above) applied to small caps; probably not a separate edge. Illiquidity.
- **Verdict**: **Weak**; **Ready**.

### distress_failure_probability — Financial distress / failure probability (short-leg avoid-list)
- **Thesis**: Stocks with high predicted failure probability (CHS logit or Ohlson O-score) earn anomalously low returns despite higher beta and vol.
- **Mechanism**: Lottery demand, shareholder-advantage / debt-renegotiation stories, and limits to arbitrage (hard to short, low institutional ownership); investors overpay for the option-like upside of distressed equity.
- **Persistence**: Short-side, small-cap concentrated; HXZ find distress anomalies largely insignificant in VW; the positive evidence is weaker after 2008 and some papers find a *positive* premium when conditioning on recessions.
- **Rule (source's own)**: Campbell, Hilscher & Szilagyi 2008: 12-month-ahead failure probability from a dynamic logit on NIMTA, TLMTA, EXRET, SIGMA, RSIZE, CASHMTA, MB, PRICE; deciles; monthly rebalance; long low-distress, short high-distress.
- **Evidence**: CHS 2008 (JF), 1981-2003: top-5% distress stocks earn ~ -0.7%/month below bottom *(approx.)*; CHS 2011 (JOIM) confirm, weaker where frictions are low. Dichev 1998 (O-score): similar. Replication: HXZ 2020: O-score / failure probability weak in VW large caps; CZ: significant EW. Post-2010: unverified; 2020-2021 distressed-equity rally shows the crash risk of the short leg.
- **Sources**: Campbell, Hilscher & Szilagyi 2008 JF "In search of distress risk"; CHS 2011 JOIM https://joim.com/article/predicting-financial-distress-and-the-performance-of-distressed-stocks/; Dichev 1998 JF "Is the risk of bankruptcy a systematic risk?"; HXZ 2020.
- **Horizon / schedule**: 20-60 sessions; month_end.
- **Data needed**: SEC financials (have), market cap, price, vol (have). Nothing missing; the logit coefficients can be taken from the paper (no re-estimation).
- **Individual fit**: Avoid-list / options overlay (long puts on distressed names when IV undervalues jump risk); not a long trade. Shorting impractical (borrow).
- **Decoys / overlap**: IVOL/MAX/low-price cluster, size, leverage. Mostly a decoy of the lottery cluster.
- **Verdict**: **Weak** standalone / **Promising** as an exclusion; **Ready**.

### piotroski_f_score — F-score fundamental screen within value stocks
- **Thesis**: Among high book-to-market stocks, those with a high 9-signal fundamental score (profitability, leverage/liquidity, efficiency improvements) beat low scorers by ~23%/yr (original).
- **Mechanism**: Value investors do not separate cheap-and-recovering from cheap-and-dying; simple financial-statement signals do it.
- **Persistence**: Decayed: post-2000 US samples show low-F firms no longer underperform, high-F sometimes *underperforms* low-F; the signal is widely screened (every value site). Still popular with retail, which argues against persistence.
- **Rule (source's own)**: Piotroski 2000: within the top B/M quintile, F = sum of 9 binary signals (ROA>0, CFO>0, ΔROA>0, CFO>ROA, Δleverage<0, Δliquidity>0, no issuance, Δmargin>0, Δturnover>0); long F≥8, short F≤1; form 4 months after fiscal year end; 12-month hold.
- **Evidence**: Piotroski 2000 (JAR), 1976-1996: 23%/yr long-short, 7.5%/yr long-only improvement. Post-publication: Kim & Lee 2014 show synchronised formation cuts gross hedge return from 8.9% to 6.0% (1976-2007); a 2026 Cardiff thesis (1997-2019): low-F no longer underperforms, predictive power only under log returns; Seeking Alpha / CXO note it "no longer works" in simple returns; Walkshäusl 2020 finds it works internationally *(not verified)*.
- **Sources**: Piotroski 2000 JAR "Value investing: the use of historical financial statement information"; CXO https://www.cxoadvisory.com/fundamental-valuation/revisiting-performance-of-piotroskis-fscore/; Cardiff thesis https://orca.cardiff.ac.uk/id/eprint/189413/; Walkshäusl 2020 https://epub.uni-regensburg.de/44019/1/Walksh%C3%A4usl2020_Article_PiotroskiSFSCOREInternationalE.pdf.
- **Horizon / schedule**: 250 sessions; on_event:10-K.
- **Data needed**: SEC financials (have). Nothing missing.
- **Individual fit**: Long-only, low turnover, trivially cheap. A fine *component* of a quality score, not an edge.
- **Decoys / overlap**: Profitability + issuance + accruals; superseded by cash-based OP and QMJ.
- **Verdict**: **Decayed**; **Ready** (test once as a baseline/decoy).

### accruals — Sloan accruals anomaly
- **Thesis**: Firms with high accruals (earnings far above cash flow) earn low returns as the accrual component reverses.
- **Mechanism**: Investors fixate on earnings and ignore their cash/accrual composition; accruals mean-revert.
- **Persistence**: **Dead in the US since ~2002**: Green, Hand & Soliman 2011 show hedge returns no longer reliably positive, attributing it to hedge-fund capital; Mohanram 2014 to analysts' cash-flow forecasts. Chen-Velikov list it among the decayed. BGLN 2016 show cash-based OP subsumes it.
- **Rule (source's own)**: Sloan 1996: accruals = (ΔCA - ΔCash) - (ΔCL - ΔSTD - ΔTaxes payable) - Dep, scaled by average assets; deciles; form 4 months after FYE; 12-month hold.
- **Evidence**: Sloan 1996 (TAR), 1962-1991: 10.4%/yr hedge; GHS 2011 (Mgmt Sci): decayed to zero post-2002 *(verified)*; HXZ 2020: accrual anomalies weak in VW; JKP: "Accruals" theme replicates but with small magnitude.
- **Sources**: Sloan 1996 TAR; Green, Hand & Soliman 2011 Mgmt Sci "Going, going, gone? The apparent demise of the accruals anomaly" https://pubsonline.informs.org/doi/fpi/10.1287/mnsc.1110.1320; Mohanram 2014 CAR https://academicnewsletter.sufe.edu.cn/info/411509; Ball et al. 2016 JFE.
- **Horizon / schedule**: 250 sessions; on_event:10-K.
- **Data needed**: SEC financials (have).
- **Individual fit**: Avoid filter only.
- **Decoys / overlap**: Subsumed by cash-based operating profitability.
- **Verdict**: **Decayed**; **Ready** (as a decoy control only).

### long_term_reversal — 3-5 year losers beat winners (De Bondt-Thaler)
- **Thesis**: Stocks with the worst 3-5 year past returns (skipping the last year) outperform the best over the next 3-5 years.
- **Mechanism**: Over-extrapolation of multi-year performance; reverting fundamentals; partly a value effect in disguise.
- **Persistence**: Weak and mostly a January/microcap/value effect; HXZ and FF (1996, 2008) find it subsumed by HML and size; JKP's "Low leverage"/"Value" absorb it. Post-2010 evidence not verified.
- **Rule (source's own)**: De Bondt & Thaler 1985: rank on 36-month cumulative abnormal return; long losers, short winners; 36-month hold. FF LTR factor: 13-60 month prior return, 2x3 sorts, monthly.
- **Evidence**: DBT 1985 (JF), 1926-1982: losers beat winners by ~25% over 36 months *(approx.)*. FF LTR factor 1931-2024: ~0.2%/month, insignificant since 1990s *(approx., not verified)*. HXZ: long-term reversal insignificant in VW.
- **Sources**: De Bondt & Thaler 1985 JF "Does the stock market overreact?"; Fama & French 1996 JF "Multifactor explanations of asset pricing anomalies"; HXZ 2020; Ken French data library (LTR factor).
- **Horizon / schedule**: 250-750 sessions; annual.
- **Data needed**: bars to 2010 (have); ≥ 5 years formation + 3 years hold limits independent events (~10 years usable).
- **Individual fit**: Long-only deep-loser basket is a value/distress bet with a high failure rate; small-cap heavy.
- **Decoys / overlap**: Value, distress, size. Mostly a decoy.
- **Verdict**: **Weak**; **Ready** (low priority).

### amihud_illiquidity_premium — Illiquidity (Amihud) premium
- **Thesis**: Stocks with high |return|/dollar-volume (price impact) earn a premium.
- **Mechanism**: Compensation for trading costs and liquidity risk.
- **Persistence**: Declined sharply after 2000 as costs fell: Harris & Amato (CFR) replicate the original but find a much weaker relation in recent data; Drienko, Smith & von Reibnitz 2019 (CFR) find out-of-sample results lose significance and monotonicity. HXZ: 96% of trading-friction anomalies fail in VW.
- **Rule (source's own)**: Amihud 2002: ILLIQ = average over the year of |r_d| / dollar volume_d; sort (within NYSE); hold 1 year.
- **Evidence**: Amihud 2002 (JFM), 1964-1997: significant cross-sectional premium; replications 1998-2015: weak/insignificant *(verified via CFR summaries)*. Emerging markets still show a (diminishing) premium.
- **Sources**: Amihud 2002 JFM; Harris & Amato CFR replication https://nowpublishers.com/article/Details/CFR-0058; Drienko, Smith & von Reibnitz 2019 CFR; CXO https://www.cxoadvisory.com/equity-premium/illiquidity-as-a-stock-return-factor.
- **Horizon / schedule**: 250 sessions.
- **Data needed**: bars + volume (have).
- **Individual fit**: Illiquid names are exactly where an individual's costs bite; no.
- **Decoys / overlap**: Size, price level.
- **Verdict**: **Decayed**; **Ready** but not worth filing except as a control variable (illiquidity is a *decoy* for many other edges).

### low_turnover_premium — Share turnover as a characteristic
- **Thesis**: Low-turnover (less traded) stocks earn higher returns than high-turnover (glamour / high-attention) stocks; high turnover marks over-pricing.
- **Mechanism**: Turnover proxies for disagreement + short-sale constraints (Miller 1977 overpricing) and for liquidity; high-turnover names are over-owned by retail.
- **Persistence**: Trading-friction anomaly class; HXZ find most fail VW; turnover's role has flipped in the short-term momentum literature (Medhat-Schmeling). Weak.
- **Rule (source's own)**: Datar, Naik & Radcliffe 1998: turnover = volume/shares, average over prior 3 months; deciles; monthly. Lee & Swaminathan 2000: double sort momentum × volume; high-volume losers and low-volume winners.
- **Evidence**: DNR 1998 (JFM), 1962-1991: ~ -0.4%/month per decile step *(approx.)*. Lee & Swaminathan 2000 (JF): volume predicts momentum persistence (low-volume winners have more persistent momentum; high-volume losers reverse faster). Post-2000: not verified; likely decayed with the illiquidity premium.
- **Sources**: Datar, Naik & Radcliffe 1998 JFM "Liquidity and stock returns"; Lee & Swaminathan 2000 JF "Price momentum and trading volume"; HXZ 2020.
- **Horizon / schedule**: 20 sessions; month_end.
- **Data needed**: volume, shares (have).
- **Individual fit**: As a conditioning variable on momentum (Lee-Swaminathan) it is cheap and long-only.
- **Decoys / overlap**: Illiquidity, size, IVOL; conflicts with Medhat-Schmeling short-term momentum (which is *high*-turnover).
- **Verdict**: **Weak**; **Ready** (only as a momentum conditioner).

### analyst_coverage_conditioned_momentum — Low analyst coverage amplifies momentum (Hong-Lim-Stein)
- **Thesis**: Momentum profits are much larger among stocks with few analysts (controlling for size), especially on the loser side; coverage measures the speed of information diffusion.
- **Mechanism**: Gradual information diffusion: with fewer analysts, firm-specific (especially bad) news travels slowly; managers hide bad news, analysts surface it.
- **Persistence**: Behavioural / information-structure based; coverage has fallen since MiFID II and sell-side shrinkage, which should strengthen it. The standalone "neglected firm" premium is a size effect (Beard & Sias 1997).
- **Rule (source's own)**: Hong, Lim & Stein 2000: residual coverage = analyst count orthogonalised to size (and Nasdaq dummy); within coverage terciles, 6-month momentum, 6-month hold.
- **Evidence**: HLS 2000 (JF), 1980-1996: momentum profits in low-coverage tercile ~1.1%/month vs ~0.5%/month in high *(approx., not verified)*. Post-publication: results replicated internationally; US post-2000 not verified. Neglected-firm premium alone: dead after size control (Beard & Sias 1997).
- **Sources**: Hong, Lim & Stein 2000 JF "Bad news travels slowly: size, analyst coverage, and the profitability of momentum strategies"; Beard & Sias 1997 FAJ "Is there a neglected-firm effect?" https://rpc.cfainstitute.org/research/financial-analysts-journal/1997/is-there-a-neglected-firm-effect; Hou 2007 RFS "Industry information diffusion and the lead-lag effect" *(not re-verified)*.
- **Horizon / schedule**: 120 sessions; month_end.
- **Data needed**: analyst coverage count per stock, point in time. **Missing**: FMP/Finnhub free tiers give current estimates/recommendations; a historical count must be accumulated by our own snapshots from now (no history). Partial feasibility.
- **Individual fit**: Long-only low-coverage winners; small/mid caps; moderate costs.
- **Decoys / overlap**: Size, illiquidity, institutional ownership. Variant of filed 12-1 momentum.
- **Verdict**: **Promising**; **Needs data** (historical analyst count; can start accumulating).

### rd_intensity — R&D-to-market (and R&D growth) as a characteristic
- **Thesis**: Firms with high R&D expense relative to market value (or rising R&D) earn higher returns; the market under-values expensed intangibles.
- **Mechanism**: Conservative accounting expenses R&D, depressing book and earnings; investors anchored on reported numbers under-price R&D-intensive firms; also higher risk (uncertain payoffs).
- **Persistence**: HXZ list R&D-to-market among anomalies that replicate (significant VW), one of the few "intangibles" anomalies to do so; JKP place it in the "Value"/"Intangibles" cluster. R&D/market is partly a value measure (market in the denominator). R&D/sales and R&D growth are weaker.
- **Rule (source's own)**: Chan, Lakonishok & Sougiannis 2001: R&D expense / market cap (and / sales); quintiles; form at mid-year; 12-month hold (3-year horizon in paper). Li 2011: R&D intensity interacted with financial constraints.
- **Evidence**: CLS 2001 (JF), 1975-1995: top R&D/market quintile excess ~6%/yr over 3 years *(approx., not verified)*; R&D/sales no effect. HXZ 2020: R&D-to-market significant in VW *(from memory of their tables; not re-verified)*. Post-2010: biotech/tech dominate the top quintile; results not verified.
- **Sources**: Chan, Lakonishok & Sougiannis 2001 JF "The stock market valuation of research and development expenditures"; Li 2011 RFS "Financial constraints, R&D investment, and stock returns"; HXZ 2020; Eisfeldt-Kim-Papanikolaou 2022 (related).
- **Horizon / schedule**: 250 sessions; on_event:10-K / annual.
- **Data needed**: SEC income statement R&D (have; XBRL tag coverage varies), market cap (have). Nothing missing.
- **Individual fit**: Long-only; the top quintile is small biotech (lottery cluster) unless size-filtered; apply within large/mid caps.
- **Decoys / overlap**: Value (R&D/market), intangibles-adjusted value, IVOL (biotech). Likely a component of intangibles value rather than separate.
- **Verdict**: **Promising**; **Ready**.

### dividend_initiation_omission_drift — Dividend initiations / omissions as events and dividend yield as a characteristic
- **Thesis**: Firms initiating dividends drift up for 1-3 years and omitters drift down; high dividend yield as a cross-sectional characteristic is a weak value proxy.
- **Mechanism**: Underreaction to the strong signal of a management commitment (initiation) or distress (omission); dividend clienteles adjust slowly.
- **Persistence**: Event evidence is 1964-1988; later samples show weaker drift and fewer initiations (buybacks replaced dividends). Dividend yield as a characteristic does not replicate well (HXZ: weak; dividends are mostly a value tilt).
- **Rule (source's own)**: Michaely, Thaler & Womack 1995: initiations (first dividend) and omissions; CAR over 1-3 years post-announcement. Yield: Litzenberger-Ramaswamy 1979 monthly yield sorts.
- **Evidence**: MTW 1995 (JF), 1964-1988: +7.5% 1-year drift after initiation, -11% after omission *(approx., not verified)*. Boehme & Sorescu 2002 (JF): drift not robust across subperiods/methods. Yield: FF 1988 time-series predictability, cross-sectional yield effects weak after value.
- **Sources**: Michaely, Thaler & Womack 1995 JF "Price reactions to dividend initiations and omissions: overreaction or drift?"; Boehme & Sorescu 2002 JF "The long-run performance following dividend initiations and resumptions: anomaly or chance?" *(not re-verified)*; HXZ 2020.
- **Horizon / schedule**: 250 sessions; on_event:dividend_initiation / omission.
- **Data needed**: dividend history (have) — initiations/omissions derivable; from 2010 maybe 300-600 initiations in our universe.
- **Individual fit**: Long-only initiations; low turnover; cheap.
- **Decoys / overlap**: Value, quality (initiators are profitable), issuance (payout). Overlaps buyback characteristic.
- **Verdict**: **Weak**; **Ready**.

### stock_split_drift — Post-split drift
- **Thesis**: Stocks drift up for ~12 months after a split announcement (signalling / attention).
- **Mechanism**: Underreaction to the manager's confidence signal; splits attract retail and analyst attention.
- **Persistence**: Decayed/not robust: Byun & Rozeff 2003 find no abnormal returns 1927-1996 overall and none after 1990 in robust methods; splits became rare in the 2010s (though 2020-2024 saw mega-cap splits: AAPL, TSLA, NVDA, AMZN, GOOGL).
- **Rule (source's own)**: Ikenberry, Rankine & Stice 1996: 2-for-1 splits, 1975-1990, buy-and-hold 1 and 3 years vs size/B/M matched.
- **Evidence**: IRS 1996: +7.9% 1-year, +12% 3-year excess *(approx.)*; Ikenberry & Ramnath 2002: +9% 1-year in 1990s; Byun & Rozeff 2003 (JF): not robust. Post-2010: too few events for independence except 2020-2024 mega caps (momentum decoy).
- **Sources**: Ikenberry, Rankine & Stice 1996 JFQA; Ikenberry & Ramnath 2002 RFS; Byun & Rozeff 2003 JF "Long-run performance after stock splits: 1927 to 1996".
- **Horizon / schedule**: 250 sessions; on_event:split.
- **Data needed**: splits (have); announcement dates (8-K / press release; have filings).
- **Individual fit**: Long-only; too few events.
- **Decoys / overlap**: Momentum (splitters are winners), size.
- **Verdict**: **Weak/Decayed**; **Ready** (event count is the issue, < 40 independent large-cap events since 2010 likely).

### low_priced_stocks — Nominal price level (low-priced stocks)
- **Thesis**: Low nominal share prices (< $5-10) predict low returns (lottery, nominal-price illusion); high price is a mild positive.
- **Mechanism**: Nominal price illusion: investors treat low-priced stocks as having more upside ("cheap"), over-paying for skewness (Birru & Wang 2016).
- **Persistence**: It is the microcap/lottery cluster; HXZ-type VW tests kill it; useful only as an exclusion.
- **Rule (source's own)**: Birru & Wang 2016: sort on price; low-price stocks have higher expected skewness and lower returns.
- **Evidence**: Birru & Wang 2016 (JFE) "Nominal price illusion"; decile spreads concentrated below $5 *(approx.)*.
- **Sources**: Birru & Wang 2016 JFE; related MAX / IVOL literature.
- **Horizon / schedule**: 20 sessions.
- **Data needed**: bars (have).
- **Individual fit**: Exclusion filter (price > $5 or $10) only.
- **Decoys / overlap**: IVOL/MAX/size/distress; pure decoy.
- **Verdict**: **Weak**; **Ready** as a filter.

### fifty_two_week_low_proximity — Nearness to the 52-week low
- **Thesis**: Stocks near their 52-week low underperform (distress/anchoring) or, in the "recency" variant, rebound if the low was long ago.
- **Mechanism**: Anchoring at the low, tax-loss selling, distress. Mirror image of the high.
- **Persistence**: Thin literature; mostly captured by the 52-week-high ratio (far from high = near low), distress and reversal.
- **Rule (source's own)**: Derived: price / 52-week low; Bhootra & Hur 2013 "recency" of the high/low.
- **Evidence**: No standalone robust published result found; effectively the bottom tercile of George-Hwang.
- **Sources**: George & Hwang 2004; Bhootra & Hur 2013 JBF *(not re-verified)*.
- **Horizon / schedule**: 20-120 sessions.
- **Data needed**: bars (have).
- **Individual fit**: Exclusion filter / tax-loss rebound January candidate list.
- **Decoys / overlap**: 52-week high, distress, reversal.
- **Verdict**: **Weak**; **Ready**, do not file separately.

### earnings_and_margin_stability — Earnings stability / gross-margin stability as quality sub-signals
- **Thesis**: Firms with stable earnings and stable gross margins (low volatility of ROE / GM over 5 years) earn higher risk-adjusted returns.
- **Mechanism**: Safety component of quality: investors under-price boring stability (benchmark-relative managers prefer variance); stable margins indicate pricing power.
- **Persistence**: As standalone signals they are weak; they live inside QMJ "safety" and Novy-Marx 2014 shows gross profitability dominates most quality definitions. "Gross margin stability" is a practitioner (Robeco/AQR) sub-signal with little independent published evidence found.
- **Rule (source's own)**: AFP 2019 safety: -σ(ROE) over 5 years (EVOL); low-margin-volatility screens from practitioner research.
- **Evidence**: No standalone published magnitude found; QMJ composite above. Novy-Marx 2014 "Quality investing": earnings stability (Grantham) and other definitions add little beyond gross profitability *(not re-verified)*.
- **Sources**: Asness, Frazzini & Pedersen 2019; Novy-Marx 2014 (working paper) *(URL not retrieved)*.
- **Horizon / schedule**: 250 sessions.
- **Data needed**: SEC quarterly financials (have), 5-year window (have from ~2011).
- **Individual fit**: Component of a quality score.
- **Decoys / overlap**: Low vol, profitability. Not a separate edge.
- **Verdict**: **Weak**; **Ready**, fold into quality_minus_junk.

### customer_supplier_momentum — Economic-link lead-lag (customer momentum)
- **Thesis**: A supplier's stock drifts for a month after its principal customers' stocks move; industry and supply-chain returns lead the returns of economically linked firms.
- **Mechanism**: Limited attention: investors in the supplier do not watch the customer's news; information diffuses across the link with a lag.
- **Persistence**: Published 2008 with ~1.5%/month; subsequent work (Menzly-Ozbas 2010, Hou 2007 industry lead-lag) consistent; crowding by quant funds likely reduced it; supply-chain datasets are now sold (FactSet Revere), which argues for decay in liquid names.
- **Rule (source's own)**: Cohen & Frazzini 2008: identify principal customers from Compustat segment disclosures (SFAS 131, >10% of sales, in the 10-K); each month, sort suppliers by the past-month return of their customer portfolio; long top quintile, short bottom; 1-month hold.
- **Evidence**: CF 2008 (JF), 1980-2004: long-short ~1.55%/month, 18.6%/yr *(approx., not verified)*. Menzly & Ozbas 2010 (JF): related industries' returns predict; Hou 2007 (RFS): big firms lead small firms within industries. Post-publication US: not verified; Lee, Sun, Wang & Zhang 2019 (JFE) show technology-link momentum (patent similarity) ~1%/month *(not verified)*.
- **Sources**: Cohen & Frazzini 2008 JF "Economic links and predictable returns"; Menzly & Ozbas 2010 JF "Market segmentation and cross-predictability of returns"; Hou 2007 RFS; Lee, Sun, Wang & Zhang 2019 JFE "Technological links and predictable returns" *(not re-verified)*.
- **Horizon / schedule**: 20 sessions; month_end.
- **Data needed**: principal-customer links — **missing** as a table, but extractable from 10-K text (Item 1 / segment note "customers accounting for more than 10% of revenue") through our text-model seam, point in time by filing date. Our SEC filings table makes this feasible with work.
- **Individual fit**: Long-only suppliers of last month's winning customers; monthly turnover high but names are large/mid caps.
- **Decoys / overlap**: Industry momentum, factor momentum, 12-1 momentum.
- **Verdict**: **Promising**; **Needs data** (customer links via LLM extraction from 10-Ks).

### composite_value — Classic multi-metric value (B/M, E/P, CF/P, EV/EBITDA, S/P)
- **Thesis**: Cheap stocks on a blend of fundamentals-to-price ratios outperform expensive ones.
- **Mechanism**: Extrapolation of past growth (glamour over-priced), plus risk (distress, cyclicality).
- **Persistence**: Survived 2007-2020 only as a Sharpe near zero in the US; composites beat single B/M (Novy-Marx, AQR); interacts with profitability (cheap-and-profitable is the robust trade).
- **Rule (source's own)**: Lakonishok, Shleifer & Vishny 1994: B/M, E/P, CF/P, sales growth; deciles; annual. Asness-Frazzini 2013 "The devil in HML's details": use *current* price in B/M, monthly.
- **Evidence**: LSV 1994 (JF), 1968-1990: ~10%/yr value-minus-glamour *(approx.)*; HML 1963-2024 ~0.3%/month, ~0 since 2007 *(approx.)*; Israel-Laursen-Richardson 2021: not dead, just cheap; Arnott et al. 2021: drawdown from cheapening. HXZ/JKP: value replicates, modest.
- **Sources**: Lakonishok, Shleifer & Vishny 1994 JF; Asness & Frazzini 2013 JPM; Arnott, Harvey, Kalesnik & Linnainmaa 2021 FAJ; Israel, Laursen & Richardson 2021 JPM.
- **Horizon / schedule**: 250 sessions; month_end or annual.
- **Data needed**: SEC financials, prices, shares (have).
- **Individual fit**: Long-only, cheap, low turnover; the core of the "cheap + profitable" long book.
- **Decoys / overlap**: Sector, interest rates, intangibles-adjusted value (which supersedes it), profitability interaction.
- **Verdict**: **Promising** only in combination with profitability (standalone **Decayed**); **Ready**.

### momentum_x_quality_interaction — Quality-conditioned momentum / momentum-conditioned value
- **Thesis**: Momentum among high-quality (or cheap) stocks is more persistent and crashes less; cheap stocks with positive momentum avoid value traps.
- **Mechanism**: Combines underreaction (momentum) with a fundamental anchor; the loser-leg junk that drives momentum crashes is excluded by the quality filter; value traps (cheap and still falling) are excluded by the momentum filter.
- **Persistence**: Standard practitioner combination (AQR "Value and momentum everywhere" shows the negative correlation; Alpha Architect QMOM/QVAL). Combination strategies are where Chen-Velikov find the only meaningful net alpha (~20 bp/month).
- **Rule (source's own)**: Asness, Moskowitz & Pedersen 2013: 50/50 value and momentum; Alpha Architect: top-decile momentum screened for quality/frog-in-the-pan; Novy-Marx 2013: value conditioned on profitability.
- **Evidence**: AMP 2013 (JF): combined value+momentum Sharpe ~1.0 vs ~0.5 each in US stocks *(approx.)*; Novy-Marx 2013: profitability-conditioned value doubles value's Sharpe *(approx.)*. Chen & Velikov 2023: combinations net ~20 bp/month.
- **Sources**: Asness, Moskowitz & Pedersen 2013 JF "Value and momentum everywhere"; Novy-Marx 2013; Chen & Velikov 2023 JFQA; Alpha Architect fund methodology https://etfarchitect.com/wp-content/uploads/compliance/etf/education/Focused_Factors_etf_summary_vF.pdf.
- **Horizon / schedule**: 60-250 sessions; month_end / quarterly.
- **Data needed**: all present.
- **Individual fit**: This is the most realistic long-only book for one trader: 30-50 names, quarterly rebalance, ~50-80% annual turnover.
- **Decoys / overlap**: It is the combination of filed 12-1 momentum with items above; file as a *variant/combination* rule, not a new mechanism.
- **Verdict**: **Strong** (as a portfolio construction rule); **Ready**.

---

## Rejected on sight (do not re-research)
- **Raw size (SMB)**: ~zero since 1983, fails HXZ/JKP; small caps lagged 2010-2024. Only as size-conditional-on-quality (above, Weak).
- **Raw 1-month reversal in all stocks**: net of costs ~zero post-2000 (Chen-Velikov, Novy-Marx-Velikov); microcap-driven.
- **Weekly (Lehmann) reversal**: turnover ~5000%/yr; needs intraday-quality execution; capacity ~$9bn industry-wide; not for EOD retail.
- **Amihud illiquidity premium**: decayed (CFR replications); keep only as a decoy control.
- **Accruals (Sloan)**: dead since ~2002 in the US; subsumed by cash-based OP.
- **Piotroski F-score standalone**: post-2000 US low-F no longer underperforms.
- **Neglected-firm premium (standalone)**: a size effect (Beard-Sias 1997).
- **Dividend yield as a return predictor (cross-section)**: weak value proxy; no independent replication.
- **Stock-split drift**: not robust (Byun-Rozeff 2003); too few events since 2010.
- **Nominal price level**: lottery/microcap decoy; filter only.
- **52-week-low proximity**: no standalone literature; captured by 52-week-high ratio and distress.
- **Earnings / gross-margin stability standalone**: no independent magnitude; fold into quality.
- **January effect / turn-of-year small-cap**: microcap, decayed, and outside a cross-sectional rule (seasonality handled under same_month_seasonality, graded Weak).
- **Leverage (book leverage) as a factor**: JKP's leverage theme fails; subsumed by value/quality.
- **O-score alone**: weaker than CHS failure probability and fails VW.
- **Sales growth / "glamour" (LSV) standalone**: subsumed by asset growth and value.
- **Beta itself as a long signal (high beta for return)**: SML too flat; the opposite (BAB) is the anomaly.
- **Return skewness (expected idiosyncratic skewness, Boyer-Mitton-Vorkink)**: same lottery cluster as MAX/IVOL; adds nothing an individual can trade.
- **Shorting any of the short legs directly**: borrow costs are the mechanism (Stambaugh-Yu-Yuan); we have no borrow data.

## Cross-cutting notes for the harness
- **Point-in-time fundamentals**: use the SEC filing acceptance date as `knowledge_ts`, never fiscal period end + fixed lag; this removes the biggest lookahead decoy in fundamental anomalies.
- **Delisting returns**: Tiingo history with delisted names is essential for every short-leg/avoid-list idea (distress, IVOL, issuance); without them the "avoid" value is overstated by survivorship, and with them it is real.
- **Default haircut**: file expected size at ≤ 50% of the published long-short number and ~1/3 of it for the long-only leg (most anomaly return is in the short leg).
- **Decoy battery to run on every idea in this family**: size, 12-1 momentum, IVOL/MAX, illiquidity (Amihud), beta, sector, and the 2010-2024 mega-cap-growth regime.
