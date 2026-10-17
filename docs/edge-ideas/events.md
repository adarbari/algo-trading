# Edge ideas, family B. Earnings, analyst and corporate events

Researched 2026-10-17 (deep-research agents; index and ranking: [README.md](README.md)). Ideas, not edges: nothing here is filed or tested. Figures marked *not verified*, *nv*, *recalled* or *from memory* must be checked against the source before an edge document cites them (quality bar item 5, [edges-plan.md](../edges-plan.md)).


Research date 2026-10-17. Verification status: figures marked **(verified)** were confirmed against a
source abstract or summary during this pass; figures marked **(from memory, not verified)** are the
author's recollection of the paper and must be re-checked before an edge document cites them.
Nothing here is implemented; nothing in the repo was modified.

## Family summary (5 lines)

1. The classic earnings-event edges (SUE-based PEAD, recommendation drift, dividend-change drift, buyback-announcement drift, split drift) are **decayed or dead in large caps** since roughly 2003-2006 (Martineau 2022; Altinkilic-Hansen-Ye 2016; Fu-Huang 2015; Chen-Lopez-Lira-Zimmermann "What Useful Alphas": median anomaly return 48 bp/mo pre-2005 -> 19 bp/mo after). What survives lives in small/micro caps, in illiquid names, or in *slower-moving* signals the market still underweights.
2. The best-evidenced, still-alive ideas with data we already hold: **earnings-date advances vs delays** (Johnson & So 2018, ~260 bp/month, we store expected and confirmed dates), **net share-count change / net buyback yield** (Pontiff-Woodgate; shares outstanding from SEC financials), **the dividend-month premium** (Hartzmark-Solomon, dividend calendar), **S&P 500 deletions long** (membership history), **8-K item drift** (we store items), and the **double-surprise (earnings + revenue) small-cap PEAD** variant of the filed edge.
3. The analyst family (revision momentum, revision breadth, target-price implied return, dispersion) is the strongest *living* cross-sectional block in the literature but hinges on the FMP/Finnhub free analyst data being deep enough (point-in-time revision dates are the whole game); recommendation-change drift itself is dead.
4. Corporate-action edges that need data we do not store yet: insider cluster/opportunistic buys (Form 4), activist 13D, IPO lockup calendar, credit-rating actions, PDUFA calendar, conference / investor-day calendars, uplistings. Of these only Form 4 and 13D are cheaply ingestible (EDGAR) and have strong enough evidence to justify the pipe.
5. Rejected on sight or dead for a long-only individual: SPAC/de-SPAC longs, IPO longs, name-change longs, special dividends, ex-dividend capture, split drift, Friday-announcer "burying", Nasdaq-100 reconstitution, bankruptcy-emergence equity (too few events).

---

### earnings_date_advance_delay — Earnings-date advances vs delays (Johnson & So)
- **Thesis**: Firms that move their confirmed earnings date earlier than the expected date go on to beat and outperform; firms that delay disappoint and underperform in the following month.
- **Mechanism**: Managers schedule good news early and need extra days for bad news (audit, restatement risk, guidance negotiation). The scheduling notice is public weeks ahead but investors ignore it because it is not an "earnings number".
- **Persistence**: Tiny, unglamorous signal, only a few weeks of life per quarter, needs a reliable expected-date model (vendors sell this: Wall Street Horizon). Capacity small; large funds cannot size a 1-month trade across thousands of names on a 260 bp edge.
- **Rule (source's own)**: Expected date = same weekday/week as the prior year's announcement (the paper's model); signal = confirmed date minus expected date in trading days (advance <0, delay >0). Long advancers, short delayers from the day the date is confirmed, hold through the announcement + a few days (~1 month).
- **Evidence**: Johnson & So (JFQA 2018): advancers outperform delayers by ~260 bp in the month after the revision **(verified via WSH/MIT summaries)**; options markets price the volatility timing correctly but equities do not. Post-publication: Wall Street Horizon continues to publish quarterly updates claiming persistence (vendor, not independent). Skinner (ABFER 2021 slides) notes the result's sensitivity to how the expected date is defined. No independent failed replication found.
- **Sources**: Johnson, T. L. & So, E. C. (2018), "Time Will Tell: Information in the Timing of Scheduled Earnings News", JFQA 53(6), https://doi.org/10.1017/S0022109018000492 ; MIT DSpace https://dspace.mit.edu/handle/1721.1/122364 ; Skinner, D., ABFER 2021 slides, https://www.abfer.org/media/abfer-events-2021/annual-conference/slides-accounting/Information-in-Mandatory-and-Voluntary-Earnings-Announcement-Date-Forecasts_Douglas-Skinner.pdf ; deHaan, Shevlin & Thornock (JAE 2015) on advance-notice length and bad news.
- **Horizon / schedule**: ~20 sessions; on_event:earnings_date_confirmed (first session after the confirmation becomes known).
- **Data needed**: earnings events (expected dates and confirmed dates) — **we store both**; need `known_from` on the confirmation so the trigger is point-in-time; prior-year announcement dates for the expected-date model (history being added). Flag: confirmation timestamps from the vendor may be back-dated; must log our own first-seen date.
- **Individual fit**: Excellent. Long-only variant: buy advancers only (roughly half the spread). Costs: one round trip per quarter per name. Liquid names qualify.
- **Decoys / overlap**: Advancers may simply be past winners (momentum); control with 12-1 momentum (filed). Overlaps with "momentum at earnings" (filed) only through holding over the announcement. Delays in small caps may proxy for distress.
- **Verdict**: **Strong**; feasibility **Ready** (once `known_from` of the confirmed date is stored and the expected-date model exists).

### net_share_count_change — Net share issuance / net buyback yield (actual repurchases, not announcements)
- **Thesis**: Firms whose split-adjusted share count shrank over the past year outperform; those that issued (SEOs, stock deals, option exercise) underperform.
- **Mechanism**: Managers time issuance to overvaluation and buy back when cheap; investors anchor on the announcement, not the realised change in shares, and the signal moves slowly.
- **Persistence**: One of the most robust published cross-sectional predictors (Pontiff & Woodgate 2008; Daniel & Titman 2006 composite issuance; Boudoukh et al. 2007 net payout yield). Survives in Chen-Zimmermann and Hou-Xue-Zhang replications **(from memory, not verified)**. Works at 12-month horizons where arbitrage capital is thin.
- **Rule (source's own)**: Pontiff-Woodgate: annual log change in split-adjusted shares outstanding; decile long/short, 1-year hold, rebalanced monthly or annually. Boudoukh et al.: net payout yield = dividends + repurchases - issuance over market cap.
- **Evidence**: Pontiff & Woodgate (JF 2008): share issuance is a stronger predictor than size, B/M or momentum post-1970, roughly 5-7% per year decile spread **(from memory, not verified)**. Fu & Huang (2015) and Lee, Park & Pearson (2019) show the *announcement*-based buyback drift has shrunk since 2001-2003 in the US **(verified)**, while Bargeron, Bonaime & Thomas (2017) find returns realised only as programs are *executed* **(verified via summary)** — which is exactly the realised-share-count signal. Manconi, Peyer & Vermaelen (JFQA 2019): no decay outside the US **(verified)**.
- **Sources**: Pontiff & Woodgate (2008) JF "Share Issuance and Cross-Sectional Returns"; Boudoukh, Michaely, Richardson & Roberts (2007) JF "On the Importance of Measuring Payout Yield"; Lee, Park & Pearson (2019) "Repurchases Have Changed", https://www.business.kaist.ac.kr/faculty/inmoo/Articles/RepurchasesHaveChanged_June2019_final.pdf ; Manconi, Peyer & Vermaelen (2019) JFQA, https://www.ecgi.global/sites/default/files/are_buybacks_good_for_longterm_shareholder_value_evidence_from_buybacks_around_the_world.pdf ; Bargeron, Bonaime & Thomas (2017) JFQA.
- **Horizon / schedule**: 250 sessions (12-month hold, monthly rebalance); month_end.
- **Data needed**: shares outstanding (SEC financials, dei:EntityCommonStockSharesOutstanding on 10-Q/10-K covers) — **stored**; splits (stored) to adjust; dividends (stored) for net payout yield. Point-in-time: use the filing date as `known_from`, never the period end.
- **Individual fit**: Excellent; long-only (bottom-decile issuers, or top-decile shrinkers) is the natural form; low turnover.
- **Decoys / overlap**: Issuers are growth/high-beta/small; shrinkers are value/profitable. Must beat a value + profitability control. Overlaps with 12-1 momentum weakly.
- **Verdict**: **Strong**; **Ready**.

### double_surprise_pead_small — Double surprise (earnings AND revenue beat) small-cap drift
- **Thesis**: Drift after earnings is concentrated in firms that beat on both EPS and revenue in the same direction; a revenue beat marks a surprise that persists.
- **Mechanism**: Revenue is more persistent and harder to manage than EPS; analysts update forecasts slowly to revenue news (Jegadeesh & Livnat).
- **Persistence**: Requires both surprises and lives mostly in small caps where coverage is thin; Martineau (2022) shows PEAD is gone for large caps since 2006 but only recently fading for microcaps **(verified)**.
- **Rule (source's own)**: Jegadeesh & Livnat (FAJ 2006): revenue surprise = (actual revenue - analyst consensus or seasonal random-walk) scaled by price; sort on both SUE and revenue SUE; long the top/top cell, short bottom/bottom, hold to the next announcement (~60 sessions).
- **Evidence**: Jegadeesh & Livnat (2006): drift materially stronger when revenue and earnings surprise agree, robust to institutional ownership, arbitrage risk and turnover **(verified)**; exact cell magnitudes not retrieved. Livnat & Mendenhall (2006): analyst-based surprises drift more than time-series surprises **(verified)**. Martineau (2022, Critical Finance Review): SUE-based PEAD gone in large caps since 2006; two 2025 papers dispute, Subrahmanyam attributes the dispute to design **(verified)**.
- **Sources**: Jegadeesh & Livnat (2006) FAJ 62(2) https://ideas.repec.org/a/taf/ufajxx/v62y2006i2p22-34.html ; Livnat & Mendenhall (2006) JAR; Martineau (2022) CFR https://cfr.ivo-welch.info/published/papers/martineau2021rest.pdf ; UCLA Anderson Review https://anderson-review.ucla.edu/is-post-earnings-announcement-drift-a-thing-again/
- **Horizon / schedule**: 60 sessions (to next announcement); on_event:earnings_announcement (first session after).
- **Data needed**: earnings events with EPS surprise (stored); **revenue actual and consensus** — partly: SEC income statement gives actual revenue with a lag; FMP/Finnhub free estimates may carry revenue consensus (check). Fallback: seasonal random-walk revenue surprise from SEC financials (lagged to filing date).
- **Individual fit**: Good; long-only (double beat) in small caps with ADV filter; 4 trades/year/name.
- **Decoys / overlap**: Variant of the filed small-cap PEAD (announcement excess return). Must show the revenue conditioning adds to the announcement return. Size/illiquidity decoy.
- **Verdict**: **Promising**; **Ready** (with revenue consensus; else Needs data: revenue estimates).

### sp500_deletions_long — Buy S&P 500 deletions (demotions), fade additions
- **Thesis**: Stocks dropped from the S&P 500 outperform the stocks added in the following year.
- **Mechanism**: Forced index-fund selling at the effective date pushes deletions below value; additions are bought at a premium after a run-up; both revert. Deletions are often beaten-down value names demoted into the S&P 400/600.
- **Persistence**: Index funds are mandated to trade at the close of the effective date regardless of price; nobody is paid to hold demoted names.
- **Rule (source's own)**: Research Affiliates ("Buy High and Sell Low with Index Funds!", Arnott, Kalesnik, Wu 2018): equal-weight the deletions, hold 12 months from the effective date; compare with additions. Their published number: deletions beat additions by roughly 20 percentage points over the next 12 months (1990-2017) **(from memory, not verified)**.
- **Evidence**: Greenwood & Sammon (2024, "The Disappearing Index Effect"): the addition premium fell to 0.8% in 2010-2020 and deletions to -0.6% **(verified)** — the *announcement* effect is gone (filed as rejected), but the *post-deletion long-run* effect is a different claim. Needs an independent test; sample ~20-25 deletions/year, so >= 40 events in a few years.
- **Sources**: Arnott, Kalesnik & Wu (2018) Research Affiliates, "Buy High and Sell Low with Index Funds!"; Greenwood & Sammon (2024) NBER w30748 https://causalclaims.trfetzer.com/paper/w30748.html ; Alpha Architect summary https://alphaarchitect.com/disappearing-index-effect/
- **Horizon / schedule**: 250 sessions; on_event:index_change_effective.
- **Data needed**: S&P 500 membership history and index changes — **stored**. Need daily bars for the demoted names (Tiingo history incl. delisted — being added).
- **Individual fit**: Excellent; long-only; ~20 names/year; liquid.
- **Decoys / overlap**: Deletions are value + long-term reversal; additions are momentum. Compare against a matched value/reversal control. Does not overlap the rejected "S&P 500 additions" idea (that was the announcement premium).
- **Verdict**: **Promising**; **Ready**.

### eight_k_item_drift — Drift after specific 8-K items (4.02 non-reliance, 4.01 auditor change, 5.02 forced CEO exit, 1.01 material agreement)
- **Thesis**: The market underreacts to unscheduled 8-K disclosures, especially negative governance items, in small firms; prices drift for 20-60 sessions.
- **Mechanism**: 8-Ks arrive unscheduled, are unstructured, and nobody has a forecast to compare to; attention is low; small firms have no analysts to translate.
- **Persistence**: Needs item-level parsing and judgement; hundreds of items a day; institutional desks skip small filers.
- **Rule (source's own)**: Lerman & Livnat (RAST 2010): abnormal returns on 8-K filing days and a post-filing drift that is larger for small firms and for items with a negative filing-day reaction **(from memory, not verified)**. Item 4.02: sec-api.io study of >8,000 filings 2004-2023: CAR -1.1% day +1, -2% over 20 days **(verified)**; prior work: negative drift 20-30 sessions after restatement news **(verified via Audit Analytics summary)**. Item 4.01 auditor resignations (vs dismissals) are negative (Whisenant, Sankaraguruswamy & Raghunandan 2003) **(from memory)**. Item 5.02: forced CEO departures negative, retirements neutral (classic turnover literature) **(from memory)**.
- **Evidence**: Mixed by item; the strongest numbers are for 4.02 and for small firms. The Audit Analytics 2005-2016 restatement study finds the *later* windows noisy (positive in window 2, negative only in slow-to-resolve cases) **(verified)**, so the drift is a short-horizon (20-30 session) claim.
- **Sources**: Lerman & Livnat (2010) RAST "The New Form 8-K Disclosures"; sec-api.io (2024) https://sec-api.io/resources/stock-price-reactions-to-item-4-02-disclosures-in-sec-form-8-k-filings ; Audit Analytics (2019) https://blog.auditanalytics.com/long-term-capital-market-consequences-of-financial-restatements/ ; Cooley PubCo summary https://cooleypubco.com/2019/02/15/audit-analytics-consequences-of-restatements/
- **Horizon / schedule**: 20-60 sessions; on_event:8k_item (first session after acceptance timestamp).
- **Data needed**: SEC filings with 8-K items — **stored**; need EDGAR acceptance timestamp as `known_from`; text-model seam to classify 5.02 (forced vs retirement) and 4.01 (resignation vs dismissal).
- **Individual fit**: Short-biased for the negative items; long-only variant: *avoid/exit* names with 4.02/4.01-resignation (a filter edge, not a return edge). 1.01 material agreements can be long but need classification.
- **Decoys / overlap**: Small-cap, low-price, distress. Overlaps the event-sensitivity track (ADR 0050) which already attributes unscheduled moves from 8-K items — build on that scope list.
- **Verdict**: **Promising** (short/filter), **Weak** (long); **Ready** for 4.02; **Needs data** (text classification) for 5.02/4.01.

### dividend_month_premium — Dividend-month premium (Hartzmark & Solomon)
- **Thesis**: Stocks earn abnormal returns in the months they are predicted to pay a dividend, concentrated between the declaration and the ex-date; the pattern reverses later.
- **Mechanism**: Dividend-seeking investors buy ahead of a predictable dividend (price pressure), and the "free dividend" fallacy makes them treat the payout as income; a small, predictable demand shock with no information.
- **Persistence**: Uninformed demand that is structural (income clienteles, dividend-capture funds); returns are small per name and need breadth.
- **Rule (source's own)**: Hartzmark & Solomon (JFE 2013): predicted dividend month = the month 3, 6 or 12 months after the last payment depending on frequency; long predicted payers, short non-payers (or all other stocks), monthly rebalance; abnormal return ~37-53 bp/month **(from memory, not verified)**; stronger within the declaration-to-ex-date window.
- **Evidence**: Hartzmark & Solomon (2013) JFE "The Dividend Month Premium"; follow-up "The Dividend Disconnect" (JF 2019) documents the free-dividend fallacy. Post-publication: Chen-Zimmermann includes a dividend-month style signal; decay not verified. Kalay & Michaely-type ex-day evidence says the drop ratio is near 1 when dividends and gains are taxed alike (Spain 2006 reform study **(verified)**), so the *ex-day* capture itself is not the edge; the *pre-ex run-up* is.
- **Sources**: Hartzmark & Solomon (2013) JFE 109(3); Hartzmark & Solomon (2019) JF "The Dividend Disconnect"; Spanish ex-day study https://merit.url.edu/en/publications/ex-dividend-day-returns-when-dividend-and-capital-gains-are-taxed-4/
- **Horizon / schedule**: ~20 sessions (declaration to ex-date); month_end or on_event:dividend_declared.
- **Data needed**: dividends with declaration and ex-dates — **stored**; need frequency inference for the prediction.
- **Individual fit**: Good; long-only; many names; low per-name cost but many trades; best as a tilt.
- **Decoys / overlap**: Low-vol/quality tilt of payers; the calendar structure is the test. Little overlap with filed edges.
- **Verdict**: **Promising**; **Ready**.

### analyst_revision_momentum — Earnings-estimate revision momentum (and revision breadth)
- **Thesis**: Stocks whose consensus EPS estimates were revised up over the past 1-3 months, by many analysts (breadth), keep outperforming for 3-6 months.
- **Mechanism**: Analysts herd and under-revise (anchoring); each revision is a partial step toward the truth, so revisions predict revisions; investors wait for the "number".
- **Persistence**: Well known (Zacks Rank, StarMine), yet it survives because it has moderate turnover and lives in mid/small caps; crowded in large caps.
- **Rule (source's own)**: Chan, Jegadeesh & Lakonishok (JF 1996) "REV6": sum over the last 6 months of (change in consensus)/price; decile long/short, 6-12 month hold. Breadth variant: (#up - #down)/#estimates over 1 month (practitioner; Zacks "agreement" factor).
- **Evidence**: CJL 1996: REV6 decile spread ~ 7-8% over 12 months **(from memory, not verified)**. Hou-Xue-Zhang q-factor replication keeps forecast revisions among surviving anomalies **(from memory, not verified)**; Chen, Lopez-Lira & Zimmermann report median post-2005 anomaly returns falling from 48 bp to 19 bp/month across ~200 signals **(verified)** — expect roughly half the published spread. Recommendation drift is a different, dead signal (below).
- **Sources**: Chan, Jegadeesh & Lakonishok (1996) JF "Momentum Strategies"; Gleason & Lee (2003) TAR "Analyst Forecast Revisions and Market Price Discovery"; Chen & Zimmermann (2022) CFR "Open Source Cross-Sectional Asset Pricing" https://papers.ssrn.com/abstract=3604626 ; Chen, Lopez-Lira & Zimmermann "What Useful Alphas?" (CXO summary https://www.cxoadvisory.com/big-ideas/open-source-stock-predictor-data-and-code/).
- **Horizon / schedule**: 60-120 sessions; month_end.
- **Data needed**: analyst estimates and revisions — **FMP/Finnhub free tier (estimates, revisions)**: must verify revision *dates* are point-in-time and that history is deep enough (>= 24 months, >= 40 rebalances). Flag: free consensus snapshots often lack the as-of history; we may have to accumulate our own daily snapshots from now.
- **Individual fit**: Good; long-only top decile; monthly turnover moderate.
- **Decoys / overlap**: Price momentum (filed 12-1) and PEAD both correlate with revisions; the test is incremental to 12-1 and SUE.
- **Verdict**: **Promising**; **Needs data** (point-in-time revision history).

### target_price_implied_return — Analyst target-price implied return, within industry
- **Thesis**: Stocks whose consensus 12-month target price implies the highest return relative to industry peers outperform over the next 1-3 months; target-price *upgrades* carry more information than recommendation changes.
- **Mechanism**: Target prices embed analysts' valuation work; investors over-focus on the rating label; the relative (within-industry) implied return nets out analyst optimism bias.
- **Persistence**: Optimism bias makes the raw implied return useless, so the signal needs normalisation; moderate capacity.
- **Rule (source's own)**: Da & Schaumburg (JFM 2011): implied return = consensus TP / price - 1, demeaned within industry; quintile long/short rebalanced monthly; roughly 1-2% per month spread **(from memory, not verified)**. Brav & Lehavy (JF 2003): target-price revisions have information beyond recommendation and earnings revisions, with post-revision drift **(from memory)**.
- **Evidence**: Da & Schaumburg (2011); Brav & Lehavy (2003). Post-2010 replication not found this pass; the Altinkilic-Hansen-Ye decay result is for *recommendations*, not targets.
- **Sources**: Da & Schaumburg (2011) Journal of Financial Markets "Relative Valuation and Analyst Target Price Forecasts"; Brav & Lehavy (2003) JF "An Empirical Analysis of Analysts' Target Prices".
- **Horizon / schedule**: 20-60 sessions; month_end.
- **Data needed**: consensus target prices with history — **FMP / Finnhub** (price targets are in FMP's free-ish endpoints; depth unverified); sector/industry classification (reference, stored).
- **Individual fit**: Good; long-only within-industry top quintile.
- **Decoys / overlap**: Long-term reversal and value (beaten-down names have high implied returns); must control for 12-1 momentum and B/M.
- **Verdict**: **Promising**; **Needs data** (target-price history).

### analyst_dispersion_short — Analyst forecast dispersion (high dispersion underperforms)
- **Thesis**: Stocks with the widest disagreement among analysts about next-year EPS earn lower returns, especially small past losers.
- **Mechanism**: Short-sale constraints let optimists set the price (Miller 1977); dispersion also forecasts lower future profitability.
- **Persistence**: Short-side anomaly; costly to arbitrage; but post-SOX evidence says it has weakened.
- **Rule (source's own)**: Diether, Malloy & Scherbina (JF 2002): std of FY1 EPS forecasts / |mean|; quintile; monthly rebalance; top minus bottom -9.48%/yr **(verified via citing papers)**.
- **Evidence**: DMS 2002: 9.48%/yr spread **(verified)**. Johnson (JF 2004) risk explanation; Min, Qiu & Roh (2019): predictability disappears controlling for future profitability and is **insignificant post-SOX (2002+)** **(verified)**. Treat as decayed.
- **Sources**: Diether, Malloy & Scherbina (2002) JF; Johnson (2004) JF https://timothyjohnson.web.illinois.edu/papers/JF_2004.pdf ; Min, Qiu & Roh (2019) https://acfr.aut.ac.nz/__data/assets/pdf_file/0016/105460/89269-What-drives-the-dispersion-anomaly.pdf
- **Horizon / schedule**: 20 sessions; month_end.
- **Data needed**: per-analyst estimate distribution (std, count) — FMP/Finnhub free tier may only give the mean/high/low; high-low range is a usable proxy.
- **Individual fit**: Short side; long-only use = exclusion filter (avoid high dispersion in small losers).
- **Decoys / overlap**: Low profitability, high idiosyncratic vol, lottery. Overlaps the volatility family.
- **Verdict**: **Decayed** (filter use only); **Needs data**.

### recommendation_change_drift — Analyst recommendation upgrades/downgrades and initiations
- **Thesis**: Upgrades drift up and downgrades drift down for weeks after the change.
- **Mechanism**: Investors underreact to analyst opinion; brokers' clients trade first.
- **Persistence**: None left: HFT and Reg FD-era speed.
- **Rule (source's own)**: Womack (JF 1996): post-recommendation drift +2.4% (upgrades, 1 month) / -9.1% (downgrades, 6 months) **(from memory, not verified)**; Barber, Lehavy, McNichols & Trueman (JF 2001): daily-rebalanced consensus portfolios ~4%/yr gross, zero after costs **(from memory)**.
- **Evidence**: Altinkilic, Hansen & Ye (JFE 2016): post-revision drift **not different from zero in 2003-2010** **(verified)**. Barber, Lehavy & Trueman (2010): upgrades to Buy earn most conditional on level **(verified)**, pre-2010 sample. Loh & Stulz (RFS 2011): only ~12% of recommendation changes are "influential" **(verified via summary)**.
- **Sources**: Altinkilic, Hansen & Ye (2016) JFE, CFA Digest https://rpc.cfainstitute.org/research/cfa-digest/2016/08/can-analysts-pick-stocks-for-the-long-run-digest-summary ; Barber, Lehavy & Trueman (2010) FM https://deepblue.lib.umich.edu/items/340f4538-7acb-4f44-987f-200ec237c06c ; Loh & Stulz (2011) RFS.
- **Horizon / schedule**: 20 sessions; on_event:recommendation_change.
- **Data needed**: recommendation changes with dates (Finnhub free gives monthly recommendation trends, too coarse).
- **Individual fit**: Poor; drift is intraday now.
- **Decoys / overlap**: Earnings revisions do the work; recommendations add nothing.
- **Verdict**: **Dead**; Out of scope (keep only as a covariate for revision momentum).

### guidance_change_drift — Management guidance changes (raise / cut), bundled with earnings
- **Thesis**: Firms that raise guidance drift up and those that cut drift down for the quarter after, beyond the EPS surprise.
- **Mechanism**: Guidance is forward-looking, soft, and often bundled with the earnings release; investors anchor on the realised EPS beat and under-weight the guide.
- **Persistence**: Requires parsing text (press releases / 8-K 2.02), inconsistent formats, no vendor consensus of "guidance surprise" in free data.
- **Rule (source's own)**: Milian (EAR 2018): bundled guidance surprise (guidance midpoint vs pre-announcement consensus for the next quarter), decile long/short, hold to next announcement: ~200 bp drift, about half arriving at the next announcement **(verified)**.
- **Evidence**: Milian (2018) ~200 bp **(verified)**. Earlier: Anilowski, Feng & Skinner (2007), Rogers & Van Buskirk (2013) on guidance and attention. Post-2018 replication not found. Martineau's caveat (drift gone in large caps) applies.
- **Sources**: Milian, J. (2018) European Accounting Review 27(1) "Bundled Earnings Guidance and the Market's Response to Earnings News" https://ideas.repec.org/a/taf/euract/v27y2018i1p105-128.html ; Zhang (Columbia) "Analyst responsiveness" https://business.columbia.edu/sites/default/files-efs/pubfiles/3737/zhang.pdf
- **Horizon / schedule**: 60 sessions; on_event:earnings_announcement.
- **Data needed**: guidance figures — **not stored**; extractable from 8-K Item 2.02 exhibits (stored as filings) via the text-model seam; next-quarter consensus from FMP/Finnhub.
- **Individual fit**: Good if extraction works; long-only raisers; 4 trades/year.
- **Decoys / overlap**: Collinear with EPS surprise and announcement return (filed PEAD); test incremental.
- **Verdict**: **Promising**; **Needs data** (guidance extraction).

### call_tone_change_drift — Earnings-call tone and tone *change*
- **Thesis**: A quarter-on-quarter increase in management negativity on the call predicts lower returns over the following weeks, beyond the headline numbers.
- **Mechanism**: Managers leak private information through word choice; analysts and investors only partly decode it; the Q&A is unscripted.
- **Persistence**: Needs transcripts and NLP; now heavily mined by quant funds in large caps, so expect the residual in mid/small caps.
- **Rule (source's own)**: Druz, Petzev, Wagner & Zeckhauser (NBER w20991, "When Managers Change Their Tone"): change in Loughran-McDonald negativity vs the firm's own history; post-call drift over ~60 sessions; analysts' revisions lag the tone change **(verified qualitatively; magnitude not retrieved)**. Price, Doran, Peterson & Bliss (JBF 2012): call tone (Henry dictionary) predicts 60-day drift, more than press-release tone **(from memory)**.
- **Evidence**: Druz et al. (NBER 2015/ RF 2020) **(verified)**; 2026 arXiv preprint: FinBERT section-weighted sentiment subsumes L-M and shows gradual adjustment **(verified, preprint)**; Brazilian replication 2010-2017 positive **(verified)**. Decay in US large caps likely; not measured here.
- **Sources**: Druz, Petzev, Wagner & Zeckhauser https://www.nber.org/papers/w20991.pdf ; Price et al. (2012) JBF 36(4); arXiv 2604.13260 https://econpapers.repec.org/paper/arxpapers/2604.13260.htm ; Loughran & McDonald (2011) JF.
- **Horizon / schedule**: 60 sessions; on_event:earnings_call (transcript availability date).
- **Data needed**: **transcripts not stored**; FMP has a transcripts endpoint (paid tier, verify); text-model seam can score tone. Expensive at scale.
- **Individual fit**: Medium; long-only (tone improvers) in small/mid caps.
- **Decoys / overlap**: Tone correlates with the surprise and the announcement return (filed); test incremental.
- **Verdict**: **Promising**; **Needs data** (transcripts).

### pre_earnings_runup_winners — Pre-earnings run-up in past winners (attention) and the post-announcement give-back
- **Thesis**: Stocks with extreme 12-month returns rise in the 5 sessions before earnings (retail attention) and give it back in the 5 after.
- **Mechanism**: Individual investors buy attention-grabbing winners ahead of the news; the demand is uninformed and reverses.
- **Persistence**: Small, short, and requires trading around the announcement; capacity-limited.
- **Rule (source's own)**: Aboody, Lehavy & Trueman (RAST 2010): top-decile prior-12-month winners: +1.58% market-adjusted in the 5 days before, about -1.86% in the 5 days after **(verified)**.
- **Evidence**: ALT 2010 (sample to mid-2000s); Chen, Cohen & Wang (SSRN 2020, "Famous Firms, Earnings Clusters") find high returns before *post-close* announcement clusters only **(verified)**; So & Wang (JFE 2014) find reversal strategies more profitable before announcements (liquidity provision) **(from memory)**. The "earnings announcement premium" itself is filed as not found (Heitz et al. 2020), so this is the *conditional* version.
- **Sources**: Aboody, Lehavy & Trueman (2010) RAST 15(2) https://ideas.repec.org/a/spr/reaccs/v15y2010i2d10.1007_s11142-009-9104-9.html ; Chen, Cohen & Wang https://papers.ssrn.com/abstract=3685452 ; So & Wang (2014) JFE.
- **Horizon / schedule**: 5 sessions in / 5 out; on_event:earnings_expected (T-6).
- **Data needed**: earnings expected dates (stored), daily bars (stored), 12-month momentum (stored).
- **Individual fit**: Fine for a few names; the pre-window long is the long-only leg; the post-window short is the better half but needs shorting/puts (implied move is stored — a put spread when IV is cheap).
- **Decoys / overlap**: Momentum at earnings (filed) is the opposite sign over the announcement; must be reconciled in one test.
- **Verdict**: **Weak/Promising**; **Ready**.

### earnings_streak_drift — "Street beat" streaks and streak breaks
- **Thesis**: Firms with long consecutive beat streaks earn a premium that *reverses* when the streak breaks; drift after a surprise is stronger when it continues a streak.
- **Mechanism**: Investors extrapolate streaks (representativeness); management manages expectations to keep the streak; a break reveals the game.
- **Persistence**: Behavioural, slow; but the meet-or-beat premium has shrunk since 2002 (Koh, Matsumoto & Rajgopal 2008) **(from memory)**.
- **Rule (source's own)**: Loh & Warachka (Management Science 2012): streak = sign of consecutive surprises; drift conditional on a continuing streak is larger than the unconditional PEAD; strategies over 60 sessions **(from memory, not verified)**. Bartov, Givoly & Hayn (JAE 2002): meet-or-beat premium ~3% quarterly return advantage **(from memory)**.
- **Evidence**: Loh & Warachka (2012); Bartov et al. (2002); Kasznik & McNichols (2002). No post-2015 replication found.
- **Sources**: Loh & Warachka (2012) MS "Streaks in Earnings Surprises and the Cross-Section of Stock Returns"; Bartov, Givoly & Hayn (2002) JAE; Koh, Matsumoto & Rajgopal (2008) CAR.
- **Horizon / schedule**: 60 sessions; on_event:earnings_announcement.
- **Data needed**: earnings surprises history (stored; depth from Tiingo backfill).
- **Individual fit**: Good; long-only streak continuers; short/avoid streak breakers.
- **Decoys / overlap**: Quality/profitability; the filed PEAD. Test the streak term as incremental.
- **Verdict**: **Weak**; **Ready**.

### pead_large_vs_small_since_2010 — Where does PEAD still live? (size-conditioned drift as a research check)
- **Thesis**: Any drift edge must be sized by market cap: it is zero in large caps since ~2006 and shrinking in microcaps.
- **Mechanism**: Decimalisation and HFT arbitrage the announcement day in liquid names (Martineau); illiquidity and limited attention keep it alive in small names (Chordia et al. 2009).
- **Persistence**: Only in names arbitrageurs cannot size.
- **Rule (source's own)**: Martineau (2022): SUE and announcement-return deciles by size tercile; large caps: zero post-2006; micro: positive until ~2015 then fading **(verified qualitatively)**. Chordia, Goyal, Sadka, Shanken & Subrahmanyam (JFE 2009): PEAD concentrated in illiquid stocks; after costs ~zero in liquid ones **(verified via summary)**.
- **Evidence**: As above; two 2025 papers dispute Martineau; Subrahmanyam's reconciliation **(verified)**.
- **Sources**: Martineau (2022) CFR; Chordia et al. (2009) JFE; UCLA Anderson Review 2025 https://anderson-review.ucla.edu/is-post-earnings-announcement-drift-a-thing-again/
- **Horizon / schedule**: 60 sessions; on_event:earnings_announcement.
- **Data needed**: stored (earnings, bars, cap). This is a *gate* for the filed small-cap PEAD, not a new edge.
- **Individual fit**: n/a (design input).
- **Decoys / overlap**: Direct overlap with filed small-cap PEAD; propose as its size/liquidity retirement rule.
- **Verdict**: **Decayed (large), Weak (small)**; **Ready** as a retirement rule.

### insider_opportunistic_cluster_buys — Opportunistic / clustered insider purchases (Form 4)
- **Thesis**: Open-market purchases by several insiders in a short window, excluding routine (same-month-every-year) traders, predict 1-12 month outperformance, strongest in small caps.
- **Mechanism**: Insiders know; buying with own money is costly; routine trades are liquidity/diversification noise that dilutes the signal.
- **Persistence**: Form 4 is public within 2 business days, yet the signal needs filtering (routine vs opportunistic, cluster, 10b5-1 flags) that most retail screens skip; small-cap capacity.
- **Rule (source's own)**: Cohen, Malloy & Pomorski (JF 2012): routine = traded in the same calendar month 3 consecutive years; opportunistic-only portfolio 82 bp/month VW alpha (1986-2007), routine ~0 **(verified)**. Lakonishok & Lee (RFS 2001): aggregate net purchases over 6 months predict 12-month returns in small caps **(from memory)**. Cluster: >= 3 distinct insiders buying within 30 days (practitioner rule, e.g. Alpha Architect / Quantpedia "insider cluster buying").
- **Evidence**: CMP sample ends 2007 **(verified)**; post-2010 out-of-sample not found this pass; practitioner trackers (InsiderScore, 2iQ) claim persistence (not independent).
- **Sources**: Cohen, Malloy & Pomorski (2012) JF https://papers.ssrn.com/abstract=1692517 ; NBER w16454 https://www.nber.org/papers/w16454.pdf ; Lakonishok & Lee (2001) RFS.
- **Horizon / schedule**: 60-250 sessions; on_event:form4_filed (acceptance timestamp).
- **Data needed**: **Form 4 not stored**; EDGAR XML Form 4 is free and structured (transaction code P, owner role, 10b5-1 flag since 2023). Needs an `add-dataset` + ingestion step; `known_from` = acceptance time.
- **Individual fit**: Excellent; long-only by construction; small caps with ADV filter.
- **Decoys / overlap**: Insiders buy after declines: long-term reversal / value decoy; control for 12-1 momentum and B/M.
- **Verdict**: **Strong** (evidence) ; **Needs data** (Form 4 ingestion; cheap).

### activist_13d_drift — Activist Schedule 13D filings
- **Thesis**: Buy on the first session after an activist hedge fund's 13D is filed; the announcement jump does not reverse and operating changes add drift.
- **Mechanism**: The activist commits capital and effort to force change; other holders underreact to the probability of a sale or restructuring.
- **Persistence**: Hard to replicate because the activist's identity matters; non-hedge-fund 13Ds (passive-turned-active, founders) are noise.
- **Rule (source's own)**: Brav, Jiang, Partnoy & Thomas (JF 2008): CAR +7-8% over (-20,+20) around the filing; no negative drift over 12 months **(verified)**. Tradable portion: the post-filing return (filing to +250), which Brav et al. report as roughly flat to slightly positive **(from memory)**.
- **Evidence**: Brav et al. 2008 and 2013 extensions (1994-2007) **(verified)**; Hartmann, Pelster & Sievers (QREF 2023): wide dispersion, even top activists often show low or negative 2-year BHAR **(verified)**. Post-filing drift is the weak part; the jump is not tradable.
- **Sources**: Brav, Jiang, Partnoy & Thomas (2008) JF https://business.columbia.edu/sites/default/files-efs/pubfiles/4132/jiang_activism.pdf ; Brav, Jiang & Kim review https://business.columbia.edu/sites/default/files-efs/pubfiles/19209/Jiang_activism_review.pdf ; Hartmann, Pelster & Sievers (2023) QREF https://ideas.repec.org/a/eee/quaeco/v89y2023icp174-187.html
- **Horizon / schedule**: 250 sessions; on_event:13d_filed.
- **Data needed**: 13D/13D-A filings (EDGAR, free, not stored); filer classification (hedge fund vs other) via a curated list or the text model.
- **Individual fit**: Good; long-only; ~100-200 US hedge-fund 13Ds/year; mostly small/mid caps.
- **Decoys / overlap**: Targets are small value names with poor past returns: value/reversal decoy; M&A optionality.
- **Verdict**: **Weak/Promising**; **Needs data** (13D ingestion).

### merger_arb_cash_deals — Merger arbitrage spreads on announced cash deals
- **Thesis**: Buying announced cash targets and collecting the spread to the deal price earns a positive, equity-like-Sharpe return that is uncorrelated with the market except in crashes.
- **Mechanism**: Target holders sell to lock in gains and avoid deal risk; arbitrage capital is limited and risk-averse after failures (insurance premium with negative skew).
- **Persistence**: Deal-break risk nobody wants; capacity limited by deal flow; returns compress when arb capital is abundant.
- **Rule (source's own)**: Mitchell & Pulvino (JF 2001): all deals, buy target (hedge acquirer for stock deals), size by spread; 1963-1998: ~4% per year excess after costs, market-neutral except in down markets (nonlinear beta) **(from memory, not verified)**. Baker & Savasoglu (JFE 2002) ~ similar.
- **Evidence**: HFRI Merger Arbitrage index low single digits over 2010-2024 **(from memory)**; completion rate ~82-90% **(verified via theses/Verdad summary)**; NYU Shanghai 2026 thesis on 2016-2024 deals: realised returns fall with failure risk, strongest in healthcare **(verified)**. Spreads widened in 2022-2023 (antitrust) and narrowed in 2024-2025.
- **Sources**: Mitchell & Pulvino (2001) JF "Characteristics of Risk and Return in Risk Arbitrage"; Baker & Savasoglu (2002) JFE; Alpha Architect / Verdad (2023) https://alphaarchitect.com/merger-spread/ ; Wang (2026) NYU Shanghai thesis https://cdn.shanghai.nyu.edu/sites/default/files/xiya_wang_thesis_nyush_honors_2026.pdf
- **Horizon / schedule**: deal length (60-250 sessions); on_event:merger_announced.
- **Data needed**: deal announcements with terms, expected close — **not stored** (8-K Item 1.01 + press release gives the announcement; terms need text extraction or a vendor); daily bars (stored).
- **Individual fit**: Fine for cash deals (long-only); stock deals need shorting the acquirer. Costs low; risk is concentrated (a broken deal costs 20-40%).
- **Decoys / overlap**: Not a cross-sectional anomaly; it is a risk premium with negative skew. Overlaps none of the filed edges.
- **Verdict**: **Promising** (modest, steady); **Needs data** (deal terms).

### acquirer_stock_deal_underperformance — Avoid / short acquirers in stock-financed deals
- **Thesis**: Acquirers paying in stock underperform cash acquirers by ~10 pp over 6-12 months after the announcement.
- **Mechanism**: Managers issue stock when it is overvalued; arbitrageurs short the acquirer (price pressure); integration disappoints.
- **Persistence**: Short side; well known; but long-horizon and hard to arbitrage.
- **Rule (source's own)**: Loughran & Vijh (JF 1997): stock acquirers -25% 5-year excess, cash acquirers +62% **(from memory)**. Nova SBE 2010-2023 work project (>$500m deals): stock deals underperform cash by 10-13 pp at 6 and 12 months, no announcement-day difference **(verified; unreviewed)**.
- **Evidence**: Malmendier, Moretti & Peters (RFS 2018): long-run underperformance even for cash deals vs losing bidders **(verified)**; Swedish 2010-2024 thesis: no long-horizon abnormal returns **(verified, weak source)**. Mixed.
- **Sources**: Loughran & Vijh (1997) JF; Malmendier, Moretti & Peters (2018) RFS https://www.nber.org/index%2ephp/papers/w18024 ; Nova SBE https://run.unl.pt/entities/publication/1a6ec532-6bdf-47fc-aca9-8b4c7eaace94
- **Horizon / schedule**: 120-250 sessions; on_event:merger_announced.
- **Data needed**: deal announcements with payment method — not stored (see above); share-count change (stored) is the continuous proxy.
- **Individual fit**: Long-only use = exclusion filter; the net_share_count_change edge already captures most of it.
- **Decoys / overlap**: Collinear with share issuance; test whether "stock acquirer" adds to issuance.
- **Verdict**: **Weak**; **Needs data**; fold into net_share_count_change.

### spinoff_parent_and_spinco — Spin-offs: spinco and parent after the distribution
- **Thesis**: Spun-off subsidiaries outperform peers over 1-3 years as forced sellers (index funds, mandates that cannot hold the small spinco) exit in the first months; parents outperform when the spin increases focus.
- **Mechanism**: Forced selling by holders with size/mandate constraints; no analyst coverage at birth; management incentives reset.
- **Persistence**: Structural (mandates) but widely known since Greenblatt; the 2001-2013 US evidence is mixed.
- **Rule (source's own)**: Cusatis, Miles & Woolridge (JFE 1993): spincos +33% and parents +18% 3-year matched excess (1965-1988) **(from memory, not verified)**. S&P Global (2017): US spincos beat industry peers by 8.4% (1 year) and 22.1% (3 years); parents only when divesting a different industry **(verified)**. McConnell, Sibley & Xu (JPM 2015), 2001-2013: spinco excess returns positive but mostly not statistically significant **(from memory, not verified)**.
- **Evidence**: As above; Nordic theses to 2022 give spincos +30% 3-year vs matches (significant) or zero depending on sample **(verified)**; Goldman Sachs 2023 note: spincos beat parents by ~4 pts (headline only) **(verified, not accessed)**.
- **Sources**: Cusatis, Miles & Woolridge (1993) JFE; S&P Global Market Intelligence (2017) https://www.spglobal.com/marketintelligence/en/documents/capital-market-implications-of-spinoffs.pdf ; McConnell, Sibley & Xu (2015) JPM; NHH thesis 2022 https://openaccess.nhh.no/nhh-xmlui/handle/11250/3052763
- **Horizon / schedule**: 250-750 sessions, entering 20-60 sessions after the distribution (after the forced selling); on_event:spinoff_distribution.
- **Data needed**: spin-off events — partly derivable: a new instrument with `parent_id` (instruments are generic with `parent_id`, ADR 0009), plus Form 10/8-K; ~20-40 US spins/year, so >= 40 events needs 2+ years of history (Tiingo backfill helps).
- **Individual fit**: Excellent; long-only; low turnover; small caps.
- **Decoys / overlap**: Size, value, low analyst coverage; the first-months reversal is a short-term-reversal decoy.
- **Verdict**: **Promising**; **Needs data** (spin-off event tagging; partially derivable).

### ipo_lockup_expiry — IPO lockup expiration (short / avoid; re-entry after)
- **Thesis**: Prices fall into and on the ~180-day lockup expiry as insiders and VCs become free to sell; the decline is concentrated in VC-backed IPOs and reverses afterwards.
- **Mechanism**: Predictable supply shock; shorting is expensive and borrow is scarce pre-expiry, so the price cannot fully pre-adjust.
- **Persistence**: Borrow constraints; the dates are known, so the remaining edge is small per event.
- **Rule (source's own)**: Field & Hanka (JF 2001): -1.5% 3-day abnormal return at expiry, -3.1% for VC-backed; volume +40% permanently **(from memory, not verified)**. Bradley, Jordan, Yi & Roten (JFR 2001) similar.
- **Evidence**: Erasmus thesis (1990-2022): negative CAR only for VC-backed **(verified)**; Aalto thesis (2003-2022): negative abnormal returns and higher volume around expiry; buyout-backed issuers *positive* **(verified)**; SMU thesis: decline stops at expiry and reverses **(verified)**.
- **Sources**: Field & Hanka (2001) JF "The Expiration of IPO Share Lockups"; Bradley et al. (2001) JFR; Erasmus thesis https://thesis.eur.nl/pub/67687/572140.pdf ; Aalto thesis https://aaltodoc.aalto.fi/items/05aae052-991d-4947-8363-6b2a5df9fb89
- **Horizon / schedule**: -10 to +2 sessions around expiry (short); +2 to +60 (long re-entry); on_event:lockup_expiry.
- **Data needed**: IPO dates (derivable from first bar in universe snapshots) and lockup terms (default 180 days; exceptions in the S-1/424B; **not stored**); VC-backed flag (text model over the prospectus).
- **Individual fit**: Short leg needs borrow (often impossible); long-only version = do not buy new IPOs until after the expiry, then buy the post-expiry dip in non-VC names (weak).
- **Decoys / overlap**: IPO long-run underperformance (below) explains the slow decline; isolate the expiry window.
- **Verdict**: **Weak** (long) / **Promising** (filter); **Needs data** (lockup dates).

### ipo_long_run_underperformance — IPOs underperform for 3-5 years (exclusion rule)
- **Thesis**: Newly public operating companies underperform size- and B/M-matched firms by ~2%/year over 5 years; worst in hot-issue years and low-sales firms.
- **Mechanism**: Issuers time windows of optimism; lockups and analyst quiet periods delay the correction; retail overpays.
- **Persistence**: Short side only; survives because shorting new issues is hard.
- **Rule (source's own)**: Ritter (JF 1991) and Ritter's updated tables: 1980-2024, 9,343 IPOs: -2.1%/yr vs matched over 5 years (equal-weighted) **(verified via a third-party summary of Ritter's March 2026 update; check Ritter's site)**; style-adjusted 3-year returns by underwriter tier around -6.6% for top underwriters **(verified)**.
- **Evidence**: Gompers & Lerner (NBER 2001) and Brav-Gompers: disappears in calendar-time / value-weighted tests **(verified)**; Nasdaq 2005-2021 IPOs substantially underperform matched firms on BHAR **(verified, thesis)**.
- **Sources**: Ritter, J., "IPOs: Long-run returns" https://site.warrington.ufl.edu/ritter/files/IPOs-long-run-returns-on-IPOs.pdf ; Gompers & Lerner (2001) NBER w8505 https://www.nber.org/papers/w8505.pdf ; Loughran & Ritter (1995) JF "The New Issues Puzzle".
- **Horizon / schedule**: 750-1250 sessions; every_session (as an exclusion flag "listed < 3 years").
- **Data needed**: first trade date per instrument (universe snapshots, Tiingo backfill) — **stored/derivable**.
- **Individual fit**: Long-only use = exclude recent IPOs from screens; shorting is infeasible.
- **Decoys / overlap**: Small growth, high issuance (net_share_count_change captures it); young firms = low profitability.
- **Verdict**: **Weak** (as alpha) / useful as a **filter**; **Ready**.

### despac_underperformance — De-SPAC post-merger underperformance
- **Thesis**: Companies that went public by SPAC merger underperform the market by ~20+ pp in the year after the merger.
- **Mechanism**: Dilution from sponsor promote, warrants and redemptions leaves little net cash per share; retail buys the story.
- **Persistence**: Short side; borrow scarce; SPAC volume collapsed after 2022 so the event count going forward is small.
- **Rule (source's own)**: Klausner, Ohlrogge & Ruan (Yale J. Reg. 2022): 47 mergers Jan 2019-Jun 2020: median post-merger returns deeply negative; dilution ~50% of cash **(verified qualitatively)**. Gahng, Ritter & Zhang (RFS 2023): de-SPAC 1-year BHAR -15.6% vs CRSP VW +8.7% **(verified via Advisor Perspectives summary; attribution uncertain)**.
- **Evidence**: Klausner & Ohlrogge (2023): the 243 mergers in the following 18 months confirmed the crash was predictable **(verified)**.
- **Sources**: Klausner, Ohlrogge & Ruan (2022) Yale J. on Regulation "A Sober Look at SPACs"; Klausner & Ohlrogge (2023) https://www.yalejreg.com/wp-content/uploads/Michael-Klausner-Michael-Ohlrogge-Was-the-SPAC-Crash-Predictable-40-Yale.-J.-on-Regul.-Bulletin-101-2023.pdf ; Gahng, Ritter & Zhang (2023) RFS "SPACs".
- **Horizon / schedule**: 250 sessions; on_event:despac_close.
- **Data needed**: de-SPAC flag (8-K "Super 8-K" Item 2.01 + shell-company status; derivable from stored filings).
- **Individual fit**: Exclusion filter only.
- **Decoys / overlap**: Overlaps IPO underperformance and share issuance.
- **Verdict**: **Decayed** (volume gone) ; filter only; **Ready** as a flag.

### nasdaq100_reconstitution — Nasdaq-100 annual reconstitution additions/deletions
- **Thesis**: Additions rise into the December effective date and deletions fall, then partly revert.
- **Mechanism**: QQQ and tracker demand at the effective close.
- **Persistence**: Mostly intraday / pre-announced; arbitraged.
- **Rule (source's own)**: Biktimirov & Xu (JAM 2019): 1997-2015: symmetric, transitory price response with a volume spike at the effective date; permanent gain only for first-time additions (awareness) **(verified)**.
- **Evidence**: As above; the index effect decline (Greenwood-Sammon) applies to "other index families" too **(verified)**.
- **Sources**: Biktimirov & Xu (2019) Journal of Asset Management 20(2) https://ideas.repec.org/a/pal/assmgt/v20y2019i2d10.1057_s41260-019-00108-6.html ; EFMA 2018 paper https://efmaefm.org/0EFMAMEETINGS/EFMA%20ANNUAL%20MEETINGS/2018-Milan/papers/EFMA2018_0575_fullpaper.pdf
- **Horizon / schedule**: 5-20 sessions; on_event:index_change_announced (December).
- **Data needed**: Nasdaq-100 changes (index changes stored? S&P 500 is; Nasdaq-100 would need adding; ~5-10 changes/year, 40 events takes 5+ years).
- **Individual fit**: Poor; too few events, transitory.
- **Decoys / overlap**: Momentum (additions are winners).
- **Verdict**: **Weak/Decayed**; Out of scope (event count).

### sp400_600_additions_from_outside — S&P 400/600 additions of names *not* previously in an S&P index
- **Thesis**: Additions to the MidCap 400 / SmallCap 600 from outside the S&P family still carry a positive announcement-to-effective return, and liquidity matters more than for the 500.
- **Mechanism**: Smaller names, larger index-fund ownership share relative to float, less pre-positioning.
- **Persistence**: Index effect is shrinking everywhere; S&P itself documented weakening for 400/600 by 2004 **(verified)**.
- **Rule (source's own)**: No single published 2010s rule; the Montclair work notes liquidity explains 400/600 abnormal returns where it does not for the 500 **(verified)**.
- **Evidence**: Thin; Greenwood-Sammon: similar decline in other index families **(verified)**.
- **Sources**: Alpha Architect summary of Greenwood-Sammon https://alphaarchitect.com/disappearing-index-effect/ ; Montclair State (Nasdaq-100 and index comparison) https://digitalcommons.montclair.edu/acctg-finance-facpubs/140
- **Horizon / schedule**: 5 sessions; on_event:index_change_announced.
- **Data needed**: S&P 400/600 change history — **not stored** (only S&P 500 membership).
- **Individual fit**: Poor (announcement-to-effective is 3-5 sessions).
- **Decoys / overlap**: Same decay as the rejected S&P 500 additions.
- **Verdict**: **Weak**; **Needs data**; low priority.

### late_filer_nt_drift — NT 10-K / NT 10-Q late-filing notices (negative drift)
- **Thesis**: Firms filing Form 12b-25 (NT) continue to drift down for months, especially with boilerplate or accounting reasons; legitimate explanations are neutral or positive.
- **Mechanism**: The notice is a weak-form admission of a problem; small firms, low attention; investors under-weight it until the delayed numbers arrive.
- **Persistence**: Short side, small caps, borrow hard.
- **Rule (source's own)**: Dee, Hillison & Pacini (2010): 2-day CAR negative for boilerplate reasons, positive for specific legitimate reasons **(verified)**. Impink et al. (RAST 2012): -1.35% when the reason is an internal-control weakness **(verified)**. Cao, Chen & Higgs (RAST 2016) and the 2017 study summarised by CPA Practice Advisor: downward drift in the post-filing months for both NT 10-K and NT 10-Q **(verified)**. S&P Global (Russell 3000, 1994-2015): negative abnormal returns before and after the NT filing **(verified)**.
- **Evidence**: Consistent sign across studies; magnitudes modest; confounded by poor fundamentals.
- **Sources**: Dee, Hillison & Pacini (2010) RAR https://ideas.repec.org/a/eee/reacre/v22y2010i2p121-127.html ; Impink, Lubberink, van Praag & Veenman (2012) RAST https://ideas.repec.org/a/spr/reaccs/v17y2012i2d10.1007_s11142-011-9172-5.html ; S&P Global "Late to File" https://www.spglobal.com/marketintelligence/en/news-insights/research/late-to-file ; CPA Practice Advisor (2017) https://www.cpapracticeadvisor.com/2017/11/30/study-shows-investors-punish-companies-for-late-financial-statements/28096/
- **Horizon / schedule**: 60 sessions; on_event:nt_filing.
- **Data needed**: NT 10-K / NT 10-Q form types from EDGAR — the SEC filings dataset should carry form type; check that NT forms are ingested; text model to classify the reason.
- **Individual fit**: Exclusion filter for longs; shorting small caps impractical.
- **Decoys / overlap**: Distress, low price, small size; overlaps 8-K 4.02 drift.
- **Verdict**: **Promising** as a filter; **Ready** if NT forms are stored.

### credit_rating_downgrade_drift — Credit rating downgrades (negative drift), upgrades (none)
- **Thesis**: Equity underperforms for up to a year after a rating downgrade, especially for speculative-grade and small firms; upgrades carry no drift.
- **Mechanism**: Rating-sensitive holders (insurers, funds with IG mandates) sell bonds and equity slowly; agencies lag, so the downgrade confirms a trend investors have not fully priced.
- **Persistence**: Mandates; but leakage before the event eats most of it.
- **Rule (source's own)**: Dichev & Piotroski (JF 2001): Moody's downgrades 1970-1997: ~-10% to -14% abnormal in the following year, concentrated in small and low-grade firms; nothing for upgrades **(from memory, not verified)**.
- **Evidence**: Theses 2000-2025 (Finnish, US 1985-2021): downgrades negative, upgrades nil; Nordic 2001-2018: most of the negative return occurs *before* the event **(verified, weak sources)**. Post-2010 peer-reviewed US drift evidence not found.
- **Sources**: Dichev & Piotroski (2001) JF "The Long-Run Stock Returns Following Bond Ratings Changes"; Turku theses https://www.utupub.fi/handle/10024/194658 , https://www.utupub.fi/items/a6cca374-ea82-464e-8ae2-f73650434ed7/full
- **Horizon / schedule**: 250 sessions; on_event:rating_change.
- **Data needed**: rating actions — **not stored**; no free structured feed (some appear in 8-K Item 8.01 / press; FMP has a ratings endpoint of unclear provenance).
- **Individual fit**: Exclusion filter.
- **Decoys / overlap**: Distress, momentum (downgraded names are past losers; 12-1 momentum already shorts them).
- **Verdict**: **Weak**; **Needs data**.

### bankruptcy_emergence_equity — Post-reorganisation equity
- **Thesis**: New equity of firms emerging from Chapter 11 earns large positive excess returns over the first 200 sessions, driven by the right tail.
- **Mechanism**: Creditors who receive the equity are forced sellers; no coverage; new shares list with no history.
- **Persistence**: Few events, illiquid, lumpy; nobody can size it.
- **Rule (source's own)**: Eberhart, Altman & Aggarwal (JF 1999): 131 emergences 1980-1993: ACAR +22.8% to +29.6% over 200 sessions **(verified)**. Duke FinReg (2021): 40-50% mean abnormal over 200 days, **median zero** **(verified)**.
- **Evidence**: Mixed 1994-2011 sub-sample (positive and negative) **(verified)**.
- **Sources**: Eberhart, Altman & Aggarwal (1999) JF 54(5) https://ideas.repec.org/a/bla/jfinan/v54y1999i5p1855-1868.html ; Duke FinReg Blog (2021) https://sites.duke.edu/thefinregblog/2021/09/17/has-post-reorg-equity-outperformed-in-the-last-three-decades/
- **Horizon / schedule**: 200 sessions; on_event:emergence (first trade of new equity).
- **Data needed**: emergence events (8-K Item 1.03 / plan confirmation; derivable from filings + a new instrument appearing); ~10-30 listed emergences/year; >= 40 events needs several years.
- **Individual fit**: Fine in size, but median zero means a basket of >= 20 is required; lottery-like.
- **Decoys / overlap**: Small, distressed, high-vol: lottery/skew decoy.
- **Verdict**: **Weak**; **Needs data**; low priority (event count).

### dividend_initiation_omission — Dividend initiations (long) and omissions / cuts (short)
- **Thesis**: Initiators drift up ~7% and omitters drift down ~11% in the year after the announcement.
- **Mechanism**: Dividend changes signal persistent cash-flow changes; investors underreact to the signal's persistence.
- **Persistence**: Classic; likely decayed with other announcement drifts; cuts cluster in crises (2008, 2020) which breaks independence.
- **Rule (source's own)**: Michaely, Thaler & Womack (JF 1995): 12-month market-adjusted +7.5% initiations, -11.0% omissions; long/short positive 22 of 25 years **(verified)**. Grullon, Michaely & Swaminathan (JB 2002) dividend *increases*: +? small; mostly a risk reduction story **(from memory)**.
- **Evidence**: Boehme & Sorescu (JF 2002): initiation long-run returns consistent with chance / sample-specific **(verified)**; Drexel 2003: omission underperformance concentrated in year 1 **(verified)**. No post-2010 US replication found.
- **Sources**: Michaely, Thaler & Womack (1995) JF, NBER w4778 https://www.nber.org/papers/w4778 ; Boehme & Sorescu (2002) JF 57(2); Grullon, Michaely & Swaminathan (2002) Journal of Business.
- **Horizon / schedule**: 250 sessions; on_event:dividend_declared (initiation / omission detected from the dividend history).
- **Data needed**: dividends — **stored**; initiation = first regular dividend; omission = scheduled payment missed (needs frequency model); ~50-150 events/year.
- **Individual fit**: Good; long-only initiators; omitters as an exclusion.
- **Decoys / overlap**: Initiators are maturing profitable firms (quality); omitters are distressed (reversal). Also overlaps net payout yield.
- **Verdict**: **Weak/Decayed**; **Ready**.

### dividend_change_at_earnings — Dividend increases bundled with earnings (and surprise interaction)
- **Thesis**: An earnings beat accompanied by a dividend raise drifts more than a beat alone; a dividend cut with a miss drifts more negatively.
- **Mechanism**: Two costly signals agreeing; investors process only the headline EPS.
- **Persistence**: Variant of PEAD conditioning; small.
- **Rule (source's own)**: No canonical paper; Kane, Lee & Marcus (JF 1984) "Earnings and Dividend Announcements: Is There a Corroboration Effect?" found a corroboration effect in announcement returns **(from memory)**; drift version is ours to test.
- **Evidence**: Thin; treat as a conditioning variable on the filed small-cap PEAD.
- **Sources**: Kane, Lee & Marcus (1984) JF; Michaely, Thaler & Womack (1995).
- **Horizon / schedule**: 60 sessions; on_event:earnings_announcement.
- **Data needed**: dividends + earnings events — **stored**.
- **Individual fit**: Good; long-only.
- **Decoys / overlap**: Direct overlap with filed PEAD and dividend_month_premium.
- **Verdict**: **Weak**; **Ready**.

### special_dividend_announcement — Special dividends
- **Thesis**: Special dividend announcements are followed by positive drift.
- **Mechanism**: Excess-cash signal; but modern specials are tax-driven or PE-recap related.
- **Persistence**: None documented recently.
- **Rule (source's own)**: Brickley (JFE 1983): positive announcement return, smaller than regular increases **(from memory)**. No drift paper found.
- **Evidence**: None retrieved this pass; practitioner lore only.
- **Sources**: Brickley (1983) JFE "Shareholder Wealth, Information Signaling and the Specially Designated Dividend"; DeAngelo, DeAngelo & Skinner (2000) JFE "Special Dividends and the Evolution of Dividend Signaling".
- **Horizon / schedule**: 60 sessions; on_event:special_dividend.
- **Data needed**: dividends (stored) with a "special" flag (vendor dependent).
- **Individual fit**: Fine but few events.
- **Decoys / overlap**: Value/cash-rich.
- **Verdict**: **Weak**; **Ready**; low priority.

### ex_dividend_capture — Ex-dividend day capture
- **Thesis**: Buy before the ex-date and sell after; the price drops by less than the dividend.
- **Mechanism**: Tax clienteles (Elton & Gruber 1970).
- **Persistence**: Arbitraged by dividend-capture desks; drop ratio near 1 where tax rates are equal (US since 2003 qualified dividends).
- **Rule (source's own)**: Elton & Gruber: drop ratio = (P_cum - P_ex)/D; trade when ratio < 1 persistently.
- **Evidence**: Spain 2006: anomaly vanished when rates equalised **(verified)**; US post-2003 drop ratios near 1 **(from memory)**; a 2-day trade cannot pay the spread for an individual.
- **Sources**: Elton & Gruber (1970) REStat; Spanish study https://merit.url.edu/en/publications/ex-dividend-day-returns-when-dividend-and-capital-gains-are-taxed-4/
- **Horizon / schedule**: 2 sessions; on_event:ex_dividend.
- **Data needed**: dividends (stored).
- **Individual fit**: Poor after costs; tax drag.
- **Decoys / overlap**: dividend_month_premium captures the pre-ex run-up instead.
- **Verdict**: **Dead**; Out of scope.

### stock_split_announcement_drift — Stock split announcements
- **Thesis**: Splitting firms drift up for 3-12 months after the announcement.
- **Mechanism**: Managers split when confident; attention and retail affordability demand.
- **Persistence**: Splits became rare (2010s: ~10-30/yr among larger names), so the sample is thin and biased to mega-cap winners.
- **Rule (source's own)**: Ikenberry, Rankine & Stice (JFQA 1996): +7.9% first year, +12% over 3 years (1975-1990) **(from memory)**. Chan, Li & Lin (JBF 2019): drift exists mainly in the first 3 months **(verified)**. Gharghori & Nguyen (1975-2011): +5%/yr full sample, not robust; -11% for firms that do not split again **(verified)**.
- **Evidence**: Boehme & Danielsen (FR 2007): drift short-lived and due to frictions **(verified)**; Aalto thesis 2004-2018: effect fades within ~40 days **(verified, weak)**.
- **Sources**: Ikenberry, Rankine & Stice (1996) JFQA; Chan, Li & Lin (2019) JBF; Gharghori & Nguyen https://acfr.aut.ac.nz/__data/assets/pdf_file/0005/105476/89582-Splits-Longrun-2017.pdf ; Boehme & Danielsen (2007) FR https://ideas.repec.org/a/bla/finrev/v42y2007i4p485-506.html
- **Horizon / schedule**: 60 sessions; on_event:split_announced.
- **Data needed**: splits (stored) — but the *announcement* date is needed, not the ex-date (8-K/press; stored filings may carry it).
- **Individual fit**: Fine; long-only; few events.
- **Decoys / overlap**: Pure momentum decoy (splitters are big winners); the filed 12-1 momentum should subsume it.
- **Verdict**: **Decayed**; Out of scope (momentum subsumes).

### seo_announcement_underperformance — Seasoned equity offerings (avoid)
- **Thesis**: SEO issuers underperform matched firms by 30%+ over 5 years.
- **Mechanism**: Issuance timed to overvaluation.
- **Persistence**: Captured continuously by share-issuance measures.
- **Rule (source's own)**: Loughran & Ritter (JF 1995), Spiess & Affleck-Graves (JFE 1995): 5-year underperformance >30% vs matched **(verified)**.
- **Evidence**: Sensitive to horizon definition (Australian study) **(verified)**; calendar-time tests weaken it; the SEO *event* is subsumed by net_share_count_change.
- **Sources**: Loughran & Ritter (1995) JF; Spiess & Affleck-Graves (1995) JFE https://ro.ecu.edu.au/ecuworks/1325 ; Denis & Sarin (2001) JFQA https://resolve.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/is-the-market-optimistic-about-the-future-earnings-of-seasoned-equity-offering-firms/93FABC3ABA2C4D1C628CFB76FFA11048
- **Horizon / schedule**: 250-1250 sessions; on_event:seo (424B prospectus; stored filings may carry 424B form types).
- **Data needed**: 424B filings (check) or share-count jumps (stored).
- **Individual fit**: Exclusion filter.
- **Decoys / overlap**: Fully overlaps net_share_count_change.
- **Verdict**: **Decayed as an event**; fold into net_share_count_change.

### earnings_timing_afterhours_friday — After-hours / Friday / busy-day announcers (bad-news timing)
- **Thesis**: Announcements scheduled for Fridays, after the close with little notice, or on busy days carry bad news, and the scheduling notice itself predicts the reaction.
- **Mechanism**: Managers try to hide bad news when attention is low.
- **Persistence**: The *news* is bad, but the market is not inattentive on Fridays (deHaan et al.), so no drift; the exploitable piece is the notification (overlaps earnings_date_advance_delay).
- **Rule (source's own)**: deHaan, Shevlin & Thornock (JAE 2015), 120k announcements 2000-2011: bad news reported after hours, on busy days, with short notice; negative return at the *notification* of a Friday date; no lower attention on Fridays **(verified)**. Michaely, Rubin & Vedrashko (RF 2014) after-close announcers: no robust drift **(from memory)**.
- **Evidence**: As above; Bagnoli, Clement & Watts (2005) Friday effect pre-2005 **(from memory)**.
- **Sources**: deHaan, Shevlin & Thornock (2015) JAE https://wallstreethorizon.com/upload/SSRN-id2545966_dehaan.pdf ; Michaely, Rubin & Vedrashko (2014) Review of Finance; IR Magazine summary https://www.irmagazine.com/reporting/friday-not-good-day-bury-bad-news
- **Horizon / schedule**: 1-5 sessions; on_event:earnings_date_confirmed.
- **Data needed**: announcement time-of-day and weekday (earnings events; check the vendor's time stamp field).
- **Individual fit**: Use as a covariate in earnings_date_advance_delay, not alone.
- **Decoys / overlap**: Overlaps earnings_date_advance_delay.
- **Verdict**: **Weak**; **Ready** as a covariate.

### conference_presentation_drift — Broker-hosted conference presentations and investor days
- **Thesis**: Firms presenting at broker conferences or hosting investor/analyst days earn positive abnormal returns around and after the event (information release + visibility).
- **Mechanism**: Selective disclosure migrated to conferences after Reg FD; attendees (buy side) trade first; small firms gain visibility.
- **Persistence**: Needs an event calendar; small firms; drift evidence modest.
- **Rule (source's own)**: Bushee, Jung & Miller (JAR 2011): positive abnormal returns and volume around presentations, larger for small, low-coverage firms **(from memory)**. Green, Jame, Markov & Subasi (JAE 2014): hosting-broker clients profit **(from memory)**. Kirk & Markov (TAR 2016): investor days: positive announcement reaction, more for lightly covered firms, with post-event drift **(from memory, not verified)**.
- **Evidence**: Pre-2015 samples; no recent replication found.
- **Sources**: Bushee, Jung & Miller (2011) JAR "Conference Presentations and the Disclosure Milieu"; Green, Jame, Markov & Subasi (2014) JAE; Kirk & Markov (2016) TAR "Come On Over: Analyst/Investor Days as a Disclosure Medium".
- **Horizon / schedule**: 20-60 sessions; on_event:conference_presentation / investor_day.
- **Data needed**: event calendar — **not stored**; 8-K Item 7.01 (Reg FD) filings with presentation exhibits are a free proxy (stored filings; needs item 7.01 tagging + text model).
- **Individual fit**: Fine; long-only; small caps.
- **Decoys / overlap**: Attention / volume; overlaps 8-K drift (7.01).
- **Verdict**: **Weak**; **Needs data** (7.01 exhibit classification is the cheap route).

### pdufa_decision_drift — FDA PDUFA decision dates (biotech)
- **Thesis**: Biotechs run up into PDUFA dates and sell off on approval ("sell the news"); the options market over-prices the event.
- **Mechanism**: Binary catalyst; retail speculation; no consensus "expected outcome" measure.
- **Persistence**: No rigorous event study found; vendor and trader lore only (run-ups of 20-100% quoted without a sample).
- **Rule (source's own)**: None published; would be ours.
- **Evidence**: None independent **(verified absence)**; the options angle (sell straddles into PDUFA) belongs to the volatility family and is dangerous (fat tails on CRLs).
- **Sources**: Wall Street Horizon blog https://www.wallstreethorizon.com/blog/why-investors-traders-need-to-track-prescription-drug-user-fee-act-pdufa-content ; trader guide (not a source of evidence) https://dansfera.com/how-to-trade-pdufa-dates
- **Horizon / schedule**: -60 to 0 sessions; on_event:pdufa_date.
- **Data needed**: PDUFA calendar — **not stored**; partially extractable from 8-K/press (text model); FDA calendars are scraped by vendors.
- **Individual fit**: Fine in size; binary risk.
- **Decoys / overlap**: Biotech beta, small-cap vol; event-vol premium (volatility family).
- **Verdict**: **Weak**; **Needs data**; low priority.

### uplisting_otc_to_nasdaq — OTC-to-Nasdaq/NYSE uplistings
- **Thesis**: Uplisting announcements earn a positive jump (visibility, institutional eligibility) followed by *underperformance* once the listing is effective.
- **Mechanism**: Listing standards force a reverse split and raise; promoters mark up before; institutions do not actually buy micro-caps.
- **Persistence**: Micro-cap, illiquid.
- **Rule (source's own)**: Sanger & McConnell (JFQA 1986): pre-listing run-up, negative returns after listing (OTC to NYSE 1966-1977) **(verified)**. No modern US uplisting study found.
- **Evidence**: Taiwan OTC-to-exchange: excess returns decline a year after listing **(verified, different market)**.
- **Sources**: Sanger & McConnell (1986) JFQA https://business.purdue.edu/faculty/mcconnell/publications/stock-exchange-listings-firm-value.pdf
- **Horizon / schedule**: 250 sessions; on_event:uplisting_effective.
- **Data needed**: exchange change per instrument (reference snapshots may record exchange; OTC names are outside the universe, so only the post-listing leg is observable).
- **Individual fit**: Exclusion filter (do not buy fresh uplistings).
- **Decoys / overlap**: IPO underperformance, issuance.
- **Verdict**: **Weak**; **Needs data**.

### name_change_fad — Corporate name changes toward a fad (dot-com, blockchain, AI)
- **Thesis**: Fad name changes jump on announcement and reverse over the following year.
- **Mechanism**: Retail buys the label; no fundamentals change.
- **Persistence**: Each fad is a new sample of ~20-60 names; reversal is reliable but the short is expensive.
- **Rule (source's own)**: Cooper, Dimitrov & Rau (JF 2001): dot-com additions +74% over 10 days (1998-99) **(from memory)**. Cooper et al. (JCF 2005): removing ".com" also positive after the crash. Cheng, De Franco, Jiang & Lin (2019) "Riding the Blockchain Mania": positive jump, reversal, SEC enforcement **(from memory)**.
- **Evidence**: Repeats every fad; AI renamings 2023-2025 not studied yet.
- **Sources**: Cooper, Dimitrov & Rau (2001) JF "A Rose.com by Any Other Name"; Cheng, De Franco, Jiang & Lin (2019) Review of Accounting Studies.
- **Horizon / schedule**: 250 sessions; on_event:name_change (8-K Item 5.03).
- **Data needed**: 8-K Item 5.03 (stored filings) + text model to flag the fad word.
- **Individual fit**: Exclusion filter / short with puts if listed.
- **Decoys / overlap**: Micro-cap lottery.
- **Verdict**: **Weak** (anti-signal filter); **Ready** if 5.03 is tagged.

---

## Rejected on sight (do not re-research)

- **SUE-based PEAD in large caps** — dead since ~2006 (Martineau 2022); keep only as the size-gate on the filed small-cap PEAD.
- **Analyst recommendation drift (upgrades/downgrades)** — zero post-2003 (Altinkilic-Hansen-Ye 2016); intraday now.
- **Friday "buried" bad news as a drift trade** — the market is not inattentive on Fridays (deHaan et al. 2015); only the notification carries information, already in earnings_date_advance_delay.
- **Ex-dividend capture** — drop ratio ~1 under equal tax rates; 2-session trade cannot pay costs.
- **Stock-split drift** — rare events, mega-cap winners, subsumed by 12-1 momentum.
- **Buyback *announcement* drift (US)** — shrunk since 2001-2003 (Fu-Huang; Lee-Park-Pearson); use realised share-count change instead.
- **SEO event underperformance** — subsumed by net share issuance.
- **Nasdaq-100 reconstitution** — 5-10 events/year, transitory, arbitraged.
- **S&P 500 additions** — already rejected (Greenwood-Sammon); the long-deletions variant is filed above as a different claim.
- **De-SPAC longs / IPO longs** — systematic underperformers; only usable as exclusion flags.
- **PDUFA "drift" as published** — no study exists; vendor lore; binary-risk; the options version belongs to the volatility family and has CRL fat tails.
- **Bankruptcy-emergence equity** — mean driven by the right tail, median zero, 10-30 events/year.
- **Merger-arb on stock deals for an individual** — needs shorting the acquirer; cash deals only (filed above).
- **Credit-rating upgrades** — no drift in any study.
- **Special dividends** — no drift evidence; tax/recap driven.
- **Analyst dispersion long/short** — insignificant post-SOX (Min-Qiu-Roh); keep as an exclusion covariate only.
- **Conference "attendance" without the 7.01 proxy** — no free calendar; weak evidence.
- **Earnings announcement premium (unconditional)** — already filed as not found.
