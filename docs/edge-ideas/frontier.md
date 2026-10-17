# Edge ideas, family I. Frontier sweep (2023-2026 research)

Researched 2026-10-17 (deep-research agents; index and ranking: [README.md](README.md)). Ideas, not edges: nothing here is filed or tested. Figures marked *not verified*, *nv*, *recalled* or *from memory* must be checked against the source before an edge document cites them (quality bar item 5, [edges-plan.md](../edges-plan.md)).


**Family summary.** The frontier literature of 2023-2026 is mostly about *flows and inelastic demand* (Gabaix-Koijen style): who is forced to trade (passive trackers, pass-through funds, target-date funds, pensions, vol-control and leveraged products, 0DTE dealers), and how price pressure from those trades shows up as run-up-then-reversal rather than as a stable characteristic premium. The second theme is *text and LLM signals* (headlines, call transcripts, 10-K changes) whose returns are already decaying as the tools spread. The sobering meta-result is Chen & Welch (2026, "What Useful Alphas?"): the median published long-short anomaly earns about 7 bp/month post-2005 in non-micro stocks, so anything we test in our S&P 500 / Nasdaq / ETF universe needs a *forced-flow or event* mechanism, not a characteristic sort. Best fits for our EOD data: earnings-date shifts (we store expected vs actual dates), an options-feature "meme score" (Cboe chains), flow-induced pressure from ETF holdings, beta-after-uptrend, pension quarter-end rebalancing, 0DTE / dealer-gamma regimes for VRP sizing, and 8-K / 10-K text signals through the text-model seam. Research note: the shared WebSearch budget was exhausted mid-sweep (about 16 searches + 16 fetches landed); items marked **not verified** are from memory and need the number checked before an edge document is written.

---

### earnings_date_shift — Earnings-date advance / delay signal
- **Thesis**: Firms that move a scheduled earnings date earlier than expected deliver good news; firms that delay deliver bad news, and the market only partly prices the timing cue when it is announced.
- **Mechanism**: Managers choose timing; good news is released promptly, bad news is delayed to prepare messaging. Investors anchor on the historical date and treat the scheduling notice as administrative.
- **Persistence**: The cue is small, scattered across thousands of firms and arrives in low-attention press releases / IR calendars; it is a scheduling datum, not a financial one, so most screens never see it.
- **Rule (source's own)**: Johnson & So (2018): expected date = same weekday/week as last year's announcement; advance (actual earlier than expected by >= 1 day) vs delay. Long advancers / short delayers from the date-notice day through the announcement (roughly 2-4 weeks). Boulland & Dessaint (2017) use the length of the advance-notice period itself.
- **Evidence**: Johnson & So report advancers beat delayers by a few percent cumulatively over the window (magnitude **not verified**, order of 1.5-3% per event window, t > 3, 2006-2015 sample). Boulland & Dessaint: short notice periods -> lower announcement returns. No failed replication found; post-2018 out-of-sample **not verified**.
- **Sources**: Johnson, T. L. & So, E. C. (2018), "Time Will Tell: Information in the Timing of Scheduled Earnings News", JFQA. Boulland, R. & Dessaint, O. (2017), "Announcing the Announcement", J. Banking & Finance. Related: Noh, So & Weber (2019) "Voluntary and mandatory disclosures: do managers view them as substitutes?" (not verified).
- **Horizon / schedule**: 10-25 sessions; on_event:earnings_date_confirmed (first session after the date notice).
- **Data needed**: We store expected and confirmed earnings dates and reactions. Need the *confirmation timestamp* (when the date became known) to avoid lookahead; check that the earnings-events table carries `known_from` for the date itself, not just the result.
- **Individual fit**: Long-only (advancers) works; large/mid caps fine; a few dozen events per week in earnings season; low costs.
- **Decoys / overlap**: Momentum (advancers tend to be winners), size. Overlaps "momentum at earnings" filed candidate; propose as its own edge, with momentum as a control.
- **Verdict**: **Strong** (clean mechanism, data in hand) + **Ready** once the date-notice timestamp is confirmed in our store.

### meme_score_options — Options-feature "memeness" classifier, weekly
- **Thesis**: Stocks that look like meme-ETF holdings (high option volume vs stock volume, high short-dated share, high IV, high retail turnover) run up for 1-2 weeks after entering the cohort, then reverse.
- **Mechanism**: Coordinated retail/options demand pushes prices; dealers hedge; arbitrage is limited by crash risk, borrow and "continued appreciation" risk.
- **Persistence**: Short-horizon, high-turnover and crash-prone, so institutions avoid it; the signal inverts at monthly rebalancing, hiding it from standard anomaly tests.
- **Rule (source's own)**: Schmerling (2025): ML classifier trained to recognise Roundhill MEME ETF holdings from market + options features; value-weighted long top-decile / short bottom-decile, weekly rebalance.
- **Evidence**: FF5+MOM alpha 11.5%/yr (t = 6.8) 1963-2025 weekly; 9.3% among above-NYSE-median caps; monthly version 2.2% and insignificant. Frozen-model OOS Apr 2023 - Aug 2025: top-25 weekly portfolios ~130-138% annualised, Sharpe 1.8-1.9, negative beta, gross of costs, turnover 21-22%/week, drawdowns 37-40%. Single-author SSRN paper; no independent replication.
- **Sources**: Schmerling, C. (2025), "A Century of Meme Stocks and the Price of Coordination", SSRN 7103138; Quantpedia summary https://quantpedia.com/a-century-of-meme-stocks-and-the-price-of-coordination/. Background: Bryzgalova, Pavlova & Sikorskaya (2023), "Retail Trading in Options and the Rise of the Big Three Wholesalers", J. Finance.
- **Horizon / schedule**: 5-10 sessions; every_session (weekly rebalance).
- **Data needed**: Cboe chain volume/OI by expiry (have), IV30 (have), stock volume/turnover (have), shares outstanding (have). Missing: institutional ownership (13F) — paper says it adds little once options features are in.
- **Individual fit**: Long leg (fresh entrants to the cohort, held 1-2 weeks) is tradable; the short leg is where most of the alpha and the crash risk sits — treat as long-run-up then *avoid/exit*, or as a vol-selling overlay after week 2.
- **Decoys / overlap**: Short-term reversal, MAX/lottery, idiosyncratic vol, short-interest. Overlaps the options family's lottery-demand items; our variant is "a catalogue feature meme_score from chain features, tested as entry-into-cohort event".
- **Verdict**: **Promising** + **Ready** (features exist; needs our own classifier or a simple composite rank).

### fund_flow_price_pressure — Flow-induced trading from fund/ETF holdings ("Ponzi funds")
- **Thesis**: Inflows into concentrated funds mechanically buy their existing holdings, inflating those stocks' prices; about half of the impact reverses within ~10 sessions, half sticks, and return-chasing flows make the cycle self-reinforcing until it unwinds.
- **Mechanism**: Investors cannot separate self-inflated from fundamental returns, so they chase; funds must deploy flows pro-rata; price elasticity is low (inelastic markets).
- **Persistence**: Mandate (pro-rata deployment) and investor behaviour; the reversal is partial and slow enough that it is not a free lunch for arbitrageurs.
- **Rule (source's own)**: Flow-induced trade per stock = sum over funds of (fund flow x fund weight in stock) / stock market cap (Lou 2012 FIT). van der Beck-Bouchaud-Villamaina decompose fund returns into price-pressure vs fundamental; stocks with high FIT reverse over ~10 days (about 50% of impact remains after 10 days). Chasing of self-inflated returns predicts ETF "bubbles" and crashes.
- **Evidence**: arXiv 2405.12768 (May 2024), estimated daily wealth reallocation of ~500 million from ETFs alone (currency unspecified on page). Earlier: Lou (2012) FIT predicts returns and reversals; Ben-David, Franzoni & Moussawi (2018) ETF ownership raises volatility; a 2022 EFMA paper (Wang, Yao, Yelekenova) finds ETF trades negatively predict future stock returns even net of flow-driven trades. Post-publication OOS not available.
- **Sources**: van der Beck, P., Bouchaud, J.-P. & Villamaina, D. (2024), "Ponzi Funds", arXiv:2405.12768. Lou, D. (2012), "A Flow-Based Explanation for Return Predictability", RFS. Gabaix, X. & Koijen, R. (2021), "In Search of the Origins of Financial Fluctuations: The Inelastic Markets Hypothesis", NBER.
- **Horizon / schedule**: 10-20 sessions reversal; every_session.
- **Data needed**: ETF holdings (iShares, SSGA: have) + daily ETF shares outstanding / AUM to get flows (partially have via ETF holdings files; ProShares data; **missing** for ARK, Global X, Direxion). Mutual-fund flows: not stored.
- **Individual fit**: Long-only variant: avoid/trim names with large positive FIT; buy names after large negative FIT (outflow-forced selling). Capacity fine in mid caps.
- **Decoys / overlap**: Short-term reversal, momentum (inflows chase winners). Overlaps thematic_etf_launch_underperformance below and the structural-niche family's ETF items.
- **Verdict**: **Promising** + **Needs data** (daily ETF shares outstanding for the thematic/active ETF complex; iShares/SSGA subset is Ready).

### beta_anomaly_after_uptrend — Low-risk anomaly conditional on 24-month market trend
- **Thesis**: High-beta stocks underperform only after sustained market uptrends, because return-chasing flows into high-beta "pass-through" funds have pushed them up.
- **Mechanism**: Investors chase returns into funds tilted to high beta; the funds pass the money through to inelastic high-beta stocks; the overpricing then mean-reverts.
- **Persistence**: Fund flows are mandate-driven; the conditioning variable (trend) is slow, so the mispricing builds over quarters.
- **Rule (source's own)**: Lee & Linn (2024): uptrend = cumulative 24-month market return above its median. After uptrends the CAPM-implied price of risk exceeds the estimated one by 0.94%/month (t = 3.44); after downtrends 0.06%/month (t = 0.2). Flow-induced trading (FIT) shocks lift high-beta returns then slowly reverse; no effect on low beta.
- **Evidence**: SSRN 4993876 (2024), US stocks, long sample (period **not verified**). No independent replication yet; consistent with Frazzini-Pedersen BAB and with Baker-Bradley-Wurgler attention stories.
- **Sources**: Lee, S. & Linn, M. (2024), "Pass-through Mutual Funds, Flow of Funds, and Low-Risk Anomaly", SSRN 4993876; Quantpedia summary https://quantpedia.com/how-can-we-explain-the-low-risk-anomaly/.
- **Horizon / schedule**: 1-3 months; month_end.
- **Data needed**: Stock betas (daily bars: have), market 24-month return (have), regime label (have). FIT itself optional.
- **Individual fit**: Long low-beta / avoid high-beta only when the 24-month trend is positive; long-only tilt; large caps; low turnover.
- **Decoys / overlap**: Size, value, the plain BAB factor; overlaps the classic-factor family's low-vol item — this is its *conditioning* variant.
- **Verdict**: **Promising** + **Ready**.

### thematic_etf_launch_underperformance — Avoid what new thematic ETFs hold
- **Thesis**: Stocks overweighted in newly launched thematic / specialised ETFs are launched at peak attention and underperform substantially over the following years.
- **Mechanism**: Issuers launch products on themes with recent hype to capture attention-driven retail flows; the holdings are already overvalued at launch.
- **Persistence**: Issuer incentives (fees on hot themes) and retail attention are structural; shorting the baskets is costly.
- **Rule (source's own)**: Ben-David, Franzoni, Kim & Moussawi (2023): specialised ETFs underperform broad-based ETFs by about 30% risk-adjusted over the five years after launch (figure from memory, **not verified**), with most of the loss in the first years; holdings have high valuations, media coverage and positive past returns at launch.
- **Evidence**: RFS 2023, US ETFs 1993-2019; practitioner confirmations (ARK complex 2021-2023, GLP-1 and AI-theme ETFs 2024-2025 anecdotal). OOS 2020-2025 not formally published.
- **Sources**: Ben-David, I., Franzoni, F., Kim, B. & Moussawi, R. (2023), "Competition for Attention in the ETF Space", RFS. Related: Brown, Davies & Ringgenberg (2021), "ETF Arbitrage, Non-Fundamental Demand, and Return Predictability", Review of Finance (ETF mispricing predicts reversals).
- **Horizon / schedule**: 6-24 months; on_event:etf_launch and month_end.
- **Data needed**: ETF launch dates and first holdings (universe snapshots give new ETF listings: have; holdings only for iShares/SSGA: **missing** for the thematic issuers). Partial proxy: count of thematic ETFs holding a stock from available holdings.
- **Individual fit**: Long-only use is as an *exclusion* / underweight screen and as a short-vol-avoid flag; shorting the stocks directly is expensive.
- **Decoys / overlap**: Momentum reversal, high valuation, lottery; overlaps fund_flow_price_pressure.
- **Verdict**: **Promising** + **Needs data** (thematic issuer holdings/launch list; a new-ETF-listing event from our universe snapshots is Ready as a weak proxy).

### pre_earnings_cp_iv_spread — Call-put IV spread and chain flow into earnings
- **Thesis**: The rise in call-minus-put implied-volatility spread (and call-heavy volume) over the sessions before an earnings date predicts the announcement return.
- **Mechanism**: Informed traders take leverage in options ahead of the event; market makers move IVs; the stock lags because the information is in the options market.
- **Persistence**: Requires options data and event alignment; the edge is in the *change* of the spread into the event, which is noisy and only a few days wide.
- **Rule (source's own)**: Lei, Wang & Yan (2020): monotonic rise of the call-put IV spread into the announcement; the abnormal spread predicts announcement returns, strongest when pre-earnings option volume is elevated. Gao, Gu & Zhang (2021): call-minus-put volume change predicts next-day excess return, stronger pre-earnings (5,419 events, 2004-2018).
- **Evidence**: JBF 2020 (sample ~1996-2015, magnitude **not verified**); the effect is sharper in firms with earnings-management flags. Post-2020 replication not found. Hu (2014) and Jin, Livnat & Zhang (2012) are the foundation (options volume and IV skew predict announcement returns).
- **Sources**: Lei, Q., Wang, X. W. & Yan, Z. (2020), "Volatility spread and stock market response to earnings announcements", J. Banking & Finance. Gao, Gu & Zhang (2021), Pacific Accounting Review. Jin, Livnat & Zhang (2012), "Option Prices Leading Equity Prices: Do Options Lead?", J. Accounting Research.
- **Horizon / schedule**: 1-3 sessions (announcement + first day); on_event:earnings (signal computed D-5..D-1).
- **Data needed**: Cboe EOD IV per strike (have), chain volume/OI (have), earnings dates (have). Fully in hand.
- **Individual fit**: Directional into earnings; or as a filter on which earnings events to hold through; small per-event size; works long-only (positive spread).
- **Decoys / overlap**: Pre-announcement drift, momentum, implied-move overpricing. Overlaps the options-signal family (they likely file IV skew into earnings); this is the *change-in-spread + volume* variant.
- **Verdict**: **Promising** + **Ready**.

### odte_gamma_vol_regime — 0DTE / short-dated OI gamma as a realised-vol dampener
- **Thesis**: When short-dated (0DTE) open-interest gamma on SPX/SPY is high, intraday realised volatility is lower, so index volatility-risk-premium sales are safer; 0DTE options carry the largest VRP of any tenor.
- **Mechanism**: Dealers long short-dated gamma hedge against the move (sell rallies, buy dips), dampening intraday ranges; the dampening does not persist overnight.
- **Persistence**: Retail/structured demand for 0DTE is structural (about half of SPX volume by 2024); dealers are forced hedgers.
- **Rule (source's own)**: Dim, Eraker & Vilkov (2024): higher 0DTE and short-term OI gamma -> lower same-day realised vol; no spillover to overnight or lagged intraday vol; 0DTE volume shocks have economically negligible return effects (about 0.1 sd). Adams et al. (SSRN 5641974): 0DTE activity dampens rather than amplifies index vol; effect comes from longer options rolling into 0DTE status.
- **Evidence**: Two SSRN papers 2024-2025 agree on dampening; a University of Utah study (press coverage) finds more intraday swings — conflicting. None reports a trading rule; no OOS.
- **Sources**: Dim, C., Eraker, B. & Vilkov, G. (2024), "0DTEs: Trading, Gamma Risk and Volatility Propagation", SSRN (summary https://harbourfrontquant.substack.com/p/impact-of-zero-dte-options-on-the). Adams et al., "Do S&P500 Options Increase Market Volatility? Evidence from 0DTEs", SSRN 5641974 (Quantpedia summary https://quantpedia.com/do-sp500-0dtes-options-increase-market-volatility/). Cboe research on 0DTE volume share (not fetched).
- **Horizon / schedule**: 1 session; every_session (sizing input for VRP positions).
- **Data needed**: Cboe EOD OI per strike/expiry for SPY/QQQ (have); dealer-gamma convention (compute); intraday RV **missing** (daily high-low Parkinson range as proxy).
- **Individual fit**: Overlay only: scale short-vol / short-strangle size by the short-dated gamma regime; no capacity issue.
- **Decoys / overlap**: VIX level, term structure; overlaps filed VRP edge (variant: *regime-conditioned* VRP) and the options family's dealer-gamma item.
- **Verdict**: **Promising** + **Ready** (as a conditioning feature; evidence is on vol, not return).

### pension_quarter_end_rebalancing — Conditional quarter-end rebalancing pressure
- **Thesis**: After a quarter in which equities beat bonds by a wide margin, pensions and balanced funds sell equities into quarter end (and buy after a bad quarter), producing a predictable last-days dip and first-days rebound in the index.
- **Mechanism**: Fixed-weight mandates (60/40, DB plans) rebalance at quarter end; the trade size is a known function of the quarter's equity-bond gap.
- **Persistence**: Mandate-driven; sell-side desks publish estimates (JPMorgan, Goldman) and the flow still happens because the owners cannot deviate.
- **Rule (source's own)**: Bikker, Broeders & de Dreu (2010): Dutch pension funds rebalance about 39% of the quarter's excess equity return each quarter, more after negative equity returns. Practitioner rule: signal = (quarter-to-date SPY return - AGG/TLT return); when large positive, expect selling over the last 3 sessions and a rebound over the first 3 of the new quarter. Goldman (Sept 2026, via aggregator): ~$33bn expected equity selling, 98th percentile since 2000.
- **Evidence**: Academic evidence is on *flows* (Dutch, 2010) not on tradable returns; US return evidence is sell-side and news (JPMorgan "up to $316bn selling by quarter end" 2021; Credit Suisse $30bn buying June 2020). Month-end "Dash for Cash" (Etula et al. 2020, RFS) documents similar last-days selling / first-days reversal at month ends. No formal OOS of the conditional quarter-end rule.
- **Sources**: Bikker, J., Broeders, D. & de Dreu, J. (2010), "Stock market performance and pension fund investment policy: rebalancing, free float, or market timing?", Int. J. Central Banking. Etula, Rinne, Suominen & Vaittinen (2020), "Dash for Cash: Monthly Market Impact of Institutional Liquidity Needs", RFS. Press: CNBC 2020-06-23; Khaleej Times/JPMorgan 2021; roic.ai/Goldman 2026-09-30.
- **Horizon / schedule**: 3-6 sessions; on_event:quarter_end (signal known at Q-end minus 5 sessions).
- **Data needed**: SPY, AGG/TLT daily bars (have). ~60 quarter ends since 2010 with Tiingo history.
- **Individual fit**: Index ETF timing; long-only (buy the dip into the new quarter); tiny costs.
- **Decoys / overlap**: Turn-of-month effect (calendar family), window dressing; this is the *conditional* (size-of-gap) variant, which is what distinguishes it.
- **Verdict**: **Promising** + **Ready**.

### vol_control_deleveraging_proxy — Estimated vol-target fund de/re-leveraging
- **Thesis**: When realised volatility jumps, vol-targeting and risk-parity funds must sell equities over the following sessions in a predictable size; when vol collapses they re-lever, creating multi-day drift that an EOD rule can follow.
- **Mechanism**: Mandated leverage = target vol / realised vol; the funds cannot wait. Sell-side (Nomura McElligott, Goldman, JPM) publish daily estimates of "vol-control selling if the market moves x%".
- **Persistence**: Mandate-driven, slow (1-month realised vol windows), and the owners accept the cost as the price of the risk budget.
- **Rule (source's own)**: Practitioner: estimated exposure E_t = min(1, target / RV_1m); flow_t = AUM x (E_t - E_{t-1}); negative flow for several sessions after a vol spike. Academic inverse: Moreira & Muir (2017) volatility-managed portfolios (scale by 1/RV) earn alpha — the mirror of the flow.
- **Evidence**: Public bank estimates (2018 "Volmageddon", March 2020, Aug 2024) describe the mechanism; academic *return-predictability* evidence of the deleveraging path is thin (**not verified**). Moreira & Muir alpha replicated by Cederburg et al. (2020) with much weaker OOS — the inverse edge is itself contested.
- **Sources**: Moreira, A. & Muir, T. (2017), "Volatility-Managed Portfolios", J. Finance. Cederburg, O'Doherty, Wang & Yan (2020), "On the performance of volatility-managed portfolios", JFE. Nomura/Goldman flow notes as reported in Bloomberg/Reuters (not fetched).
- **Horizon / schedule**: 3-10 sessions; every_session.
- **Data needed**: SPX/SPY realised vol (have), VIX (have via Cboe/FRED). AUM of vol-control complex: not stored (constant assumption).
- **Individual fit**: Index-level; long-only "buy after the deleveraging wave ends" or "step aside while estimated selling is heavy".
- **Decoys / overlap**: Short-term index reversal, VIX mean reversion, trend/TAA family's vol-targeting.
- **Verdict**: **Promising** + **Ready** (as a cross-asset rollup feature; retire if it adds nothing over plain RV).

### benchmarking_intensity_switch — Benchmarking intensity and index-switch demand shocks
- **Thesis**: Stocks held heavily by funds benchmarked to the indices they belong to have lower expected returns and inelastic demand; a switch between indices (e.g. Russell 2000 -> 1000) changes benchmarked demand sharply and moves the price in a predictable direction.
- **Mechanism**: Benchmarked managers hold index weights regardless of value; demand is inelastic; moving from a small-cap index (high benchmarked AUM per dollar of cap) to a large-cap one reduces forced demand.
- **Persistence**: Growth of benchmarking/passive AUM; Chinco & Sammon (2024, JFE) show passive ownership is ~33.5% of the US market (double the index-fund figure), measured from reconstitution-day closing volume.
- **Rule (source's own)**: Pavlova & Sikorskaya (2023): BMI_i = sum over indices of (AUM benchmarked to index / index cap) x weight; high-BMI stocks earn lower returns; index switches (R2000->R1000) are negative demand shocks (magnitudes **not verified**).
- **Evidence**: RFS 2023; Chinco-Sammon JFE 2024 (passive share). Index-switch samples are small per year (~50-100 Russell switches), and our Russell membership is **blocked**.
- **Sources**: Pavlova, A. & Sikorskaya, T. (2023), "Benchmarking Intensity", RFS. Chinco, A. & Sammon, M. (2024), "The Passive-Ownership Share Is Double What You Think It Is", JFE (summary https://alphaarchitect.com/is-passive-ownership-bigger-than-estimated/). Haddad, Huebner & Loualiche (2025), "How Competitive Is the Stock Market?" (not fetched).
- **Horizon / schedule**: 1-12 months; on_event:index_change and month_end.
- **Data needed**: S&P 500/400/600 membership and changes (S&P 500: have; 400/600 **missing**), index weights (ETF holdings: have), AUM per index (ETF AUM: partial).
- **Individual fit**: Long-only tilt away from high-BMI mega caps is a factor bet; the switch event is the tradable piece.
- **Decoys / overlap**: Size, passive-share conditioning (next item), the rejected S&P-additions edge. Variant: S&P 500 -> 400 demotions (we have the 500 side).
- **Verdict**: **Promising** + **Needs data** (S&P 400/600 membership; Russell blocked).

### passive_share_reconstitution_volume — Stock-level passive share from reconstitution-day volume
- **Thesis**: The share of a stock's volume on index-reconstitution closes measures how much passive capital tracks it; high-passive-share stocks are less elastic, so every other flow edge (ETF flows, earnings surprises, inclusion events) has larger and slower-reverting price impact in them.
- **Mechanism**: Passive trackers trade at the reconstitution close; their size is revealed by abnormal closing volume. Low elasticity amplifies demand shocks.
- **Persistence**: Passive growth; a measurement, not a mispricing per se.
- **Rule (source's own)**: Chinco & Sammon (2024): passive ownership share proxied by abnormal volume on Russell/S&P reconstitution days relative to normal volume; aggregate 33.5% in 2021.
- **Evidence**: JFE 2024; the aggregate is validated against index-fund holdings; stock-level use as a conditioning variable is our extension (**not verified** in the paper).
- **Sources**: Chinco & Sammon (2024) as above; Rational Reminder ep. 322 interview with Sammon.
- **Horizon / schedule**: annual feature; used as a conditioner on other edges.
- **Data needed**: Daily volume (have) + reconstitution dates (Russell: 4th Friday of June; S&P: quarterly 3rd Friday) — no membership needed.
- **Individual fit**: Not a trade; a catalogue feature `passive_share_proxy`.
- **Decoys / overlap**: Size and index membership explain most of it; test that it adds beyond them.
- **Verdict**: **Promising (as a feature)** + **Ready**.

### tariff_exposure_overreaction — Trade-exposure and uncertainty-sensitivity on tariff shocks
- **Thesis**: Stocks with high trade exposure and high sensitivity to policy uncertainty overshoot on tariff announcements and rebound most on pauses/deals; a long-run trade-policy-uncertainty premium exists for exposed industries.
- **Mechanism**: Investors demand a premium for policy risk nobody can hedge; headline shocks are priced in days with little firm-level discrimination, then corrected.
- **Persistence**: Policy uncertainty is recurring; exposure data are costly to assemble.
- **Rule (source's own)**: Bianconi, Esposito & Sammon (2021): long-short on TPU exposure (China MFN-vote variation) earns 3.6-6.2%/yr risk-adjusted (1990-2001 identification). IMF WP 2026/070 (Beyer, Tong, Zhou): 2025 event study; trade-exposure + uncertainty channels explain ~20% of the post-April-2 decline and ~10% of the rebound among tradable firms.
- **Evidence**: JIMF 2021; IMF 2026 working paper (one episode, 2025). Event count small (a handful of regimes); the cross-sectional premium is the testable part.
- **Sources**: Bianconi, Esposito & Sammon (2021), "Trade policy uncertainty and stock returns", J. Int. Money & Finance. Beyer, Tong & Zhou (2026), IMF WP/26/70 https://www.imf.org/-/media/files/publications/wp/2026/english/wpiea2026070-source-pdf.pdf. Baker, Bloom & Davis (2016) EPU/TPU indices (FRED).
- **Horizon / schedule**: 5-20 sessions after a tariff headline; on_event:policy_announcement; premium version month_end.
- **Data needed**: Foreign revenue share (SEC XBRL geographic segments: partial; text model over 10-K: feasible), TPU index (FRED: have). Event tagging via capped headlines + text model.
- **Individual fit**: Long-only rebound trade after shocks in exposed names; moderate size.
- **Decoys / overlap**: Beta, cyclicality, sector; overlaps macro family's policy-uncertainty items.
- **Verdict**: **Promising** + **Needs data** (geographic segment share feature).

### tdf_contrarian_flows — Target-date-fund contrarian rebalancing
- **Thesis**: Target-date funds mechanically sell equities after market rises and buy after falls (monthly/quarterly), creating contrarian flows concentrated in the broad-index stocks they hold; those stocks show more reversal after large market months.
- **Mechanism**: Glide-path targets are fixed; TDFs hold ~$3-4tn and rebalance to weights; the trades are mechanical and predictable from the month's return.
- **Persistence**: Default retirement plan structure (auto-enrolment); flows grow with 401(k) assets.
- **Rule (source's own)**: Parker, Schoar & Sun (2023): stocks with higher TDF ownership have lower return autocorrelation / stronger reversal following market moves; aggregate TDF trades are contrarian at ~monthly frequency (magnitudes **not verified**).
- **Evidence**: J. Finance 2023; novel, no independent replication yet.
- **Sources**: Parker, J., Schoar, A. & Sun, Y. (2023), "Retail Financial Innovation and Stock Market Dynamics: The Case of Target Date Funds", J. Finance.
- **Horizon / schedule**: 5-20 sessions after month end; month_end.
- **Data needed**: TDF ownership per stock: **missing** (proxy: S&P 500 / total-market index membership and weight — have).
- **Individual fit**: Index-level: expect contrarian pressure on SPY/VTI in the first sessions after a +/-5% month; long-only buy after a down month.
- **Decoys / overlap**: pension_quarter_end_rebalancing (same mechanism, different owner), turn-of-month.
- **Verdict**: **Promising** + **Needs data** (TDF ownership; index-level proxy Ready).

### llm_headline_score — LLM sentiment on news headlines
- **Thesis**: An LLM's good/bad-news score on a headline predicts the next-day return and the drift after it, mostly for small stocks and negative news.
- **Mechanism**: Underreaction to complex text; LLMs read it faster and better than keyword dictionaries.
- **Persistence**: Weak — returns decline as LLM adoption rises (the paper's own finding).
- **Rule (source's own)**: Lopez-Lira & Tang (2023, v6 Oct 2025): prompt GPT-4 on each headline for "good / bad / unknown" for the stock; long good / short bad next day. GPT-4 reaches ~90% portfolio-day hit rate for the initial reaction; drift predicted especially for small stocks and negative news.
- **Evidence**: arXiv 2304.07619, sample Oct 2021 onward; headline Sharpe figures were in early versions (**not verified** here); explicit decay with adoption reported in v6. Several replications on other corpora (e.g. Chen, Kelly, Xiu 2023 "Expected returns and large language models") find similar but decaying effects.
- **Sources**: Lopez-Lira, A. & Tang, Y. (2023-2025), "Can ChatGPT Forecast Stock Price Movements?", arXiv:2304.07619. Chen, Kelly & Xiu (2023), "Expected Returns and Large Language Models", SSRN.
- **Horizon / schedule**: 1-5 sessions; every_session.
- **Data needed**: A news feed — we store only capped headlines; text-model seam exists. **Missing** at scale.
- **Individual fit**: Small stocks and negative news = shorts and illiquidity; long-only variant weak.
- **Decoys / overlap**: Short-term reversal, earnings news; overlaps alt-data/text family.
- **Verdict**: **Weak** (decaying) + **Needs data** (news feed).

### llm_earnings_call_unusual — Unusual management communication on calls
- **Thesis**: When management's answers in the Q&A diverge from what an LLM would answer (or are flagged "unusual" on tone/evasiveness dimensions), the stock subsequently underperforms.
- **Mechanism**: Evasive or scripted answers signal withheld bad news; analysts under-react to tone.
- **Persistence**: Transcript parsing at scale is new; the measure is subtle; decay likely as adoption spreads.
- **Rule (source's own)**: Bai, Boyson, Cao, Liu & Wan: "Human-AI Difference" between executives' answers and LLM answers, 104,932 calls 2004-2020; tested against abnormal future returns and volume (results **not verified**, fetch blocked). Xiamen seminar paper: GPT flags unusual communication on 25 dimensions for S&P 500 calls; negative reaction to unusual communications.
- **Evidence**: Working papers 2024-2025; S&P Global (Fortune, Sept 2025) reports an LLM-signal long-short at 8.4%/yr vs 4.2% for traditional text (vendor study). No peer-reviewed OOS.
- **Sources**: Alpha Architect summary https://alphaarchitect.com/earnings-conference-q-a/ (403 on fetch). Fortune 2025-09-23 https://fortune.com/2025/09/23/how-ai-changing-earnings-call-analysis-stock-picks. Earlier: Loughran & McDonald (2011) tone; Mayew & Venkatachalam (2012) vocal cues.
- **Horizon / schedule**: 20-60 sessions; on_event:earnings_call.
- **Data needed**: Transcripts **missing** (free sources exist: Motley Fool pages, SEC 8-K exhibits sometimes); text-model seam (have).
- **Individual fit**: Mostly a short/avoid signal; long-only as "clean call" filter on PEAD longs.
- **Decoys / overlap**: Earnings surprise, guidance; overlaps text/ML family.
- **Verdict**: **Promising** + **Needs data** (transcripts).

### retail_options_lottery_share — Retail option-demand share from chain data
- **Thesis**: Stocks where a large share of option volume is in short-dated, OTM, small-premium calls (retail lottery demand) earn low subsequent returns and high realised-minus-implied gaps; retail option traders lose on average.
- **Mechanism**: Retail buys lottery calls through wholesalers; dealers hedge by buying stock, pushing it up; the pressure reverses; retail pays wide spreads.
- **Persistence**: PFOF economics and gamification; the "big three" wholesalers internalise the flow; dealers are forced.
- **Rule (source's own)**: Bryzgalova, Pavlova & Sikorskaya (2023): identify retail options trades via single-leg, small-size wholesaler prints (OPRA trade data); retail buys short-dated OTM options, loses ~$2bn+ in 2019-2021 (figure **not verified**), concentrated in meme periods. Our proxy: share of chain volume in <= 2-week OTM calls.
- **Evidence**: J. Finance 2023. Return predictability of the retail share is documented at weekly horizons (**not verified**). Related: Eaton, Green, Roseman & Wu (2022) Robinhood outages.
- **Sources**: Bryzgalova, Pavlova & Sikorskaya (2023), "Retail Trading in Options and the Rise of the Big Three Wholesalers", J. Finance. Eaton et al. (2022), "Retail trader sophistication and stock market quality", JFE.
- **Horizon / schedule**: 5-10 sessions; every_session.
- **Data needed**: Cboe EOD volume by strike/expiry (have); trade-level/wholesaler flags **missing** (proxy only).
- **Individual fit**: Avoid/short list; vol-selling overlay in those names (overpriced short-dated calls).
- **Decoys / overlap**: meme_score_options (sister item), MAX/lottery, idiosyncratic vol.
- **Verdict**: **Promising** + **Ready (proxy)**.

### quarter_end_markup_reversal — Last-day-of-quarter mark-up and next-day reversal
- **Thesis**: Stocks concentrated in fund portfolios are marked up at the quarter-end close and give it back the next session, most visibly in small/illiquid names.
- **Mechanism**: Funds' incentive to report higher NAV/performance at period end ("leaning for the tape"); concentrated active funds have the most to gain (Ponzi-fund mechanism).
- **Persistence**: Agency incentive; enforcement is sporadic; the reversal is small per name.
- **Rule (source's own)**: Carhart, Kaniel, Musto & Reed (2002): last-day quarter-end abnormal returns of fund-held stocks reverse next day; Ben-David, Franzoni, Landier & Moussawi (2013): hedge-fund-held stocks show end-of-quarter price inflation of ~0.3% (small caps more), reversing the next day (magnitudes **not verified**).
- **Evidence**: J. Finance 2002 and 2013; practitioner note from Flirting with Models on quarter-end effects (not fetched). Post-2013 OOS **not verified**; likely weakened but still present in micro/small caps.
- **Sources**: Carhart, Kaniel, Musto & Reed (2002), "Leaning for the Tape", J. Finance. Ben-David, Franzoni, Landier & Moussawi (2013), "Do Hedge Funds Manipulate Stock Prices?", J. Finance.
- **Horizon / schedule**: 1-2 sessions; on_event:quarter_end.
- **Data needed**: Daily closes (have); fund-ownership concentration **missing** (13F) — proxy by small-cap + low ADV.
- **Individual fit**: Short the mark-up is hard; long-only variant: buy the reversed names on day +1 for a few days (weak).
- **Decoys / overlap**: Turn-of-month (calendar family), illiquidity.
- **Verdict**: **Weak** + **Ready** (proxy); likely small after costs.

### dealer_gamma_regime — Aggregate dealer gamma (GEX) as a vol/return-pattern regime
- **Thesis**: When dealers are net long gamma the index mean-reverts intraday and realised vol is low; when net short gamma, moves extend and vol is high — a regime label for sizing vol and trend positions.
- **Mechanism**: Delta-hedging by dealers who are forced to trade with (short gamma) or against (long gamma) the move.
- **Persistence**: Structural demand for puts and covered-call overwriting; dealers hedge mechanically.
- **Rule (source's own)**: SqueezeMetrics (2017): GEX = sum over strikes of OI x gamma x 100 x spot, calls positive / puts negative (dealer-long-call, dealer-short-put convention). Barbon & Buraschi (2021): "gamma fragility" — negative aggregate gamma predicts higher realised vol and intraday momentum; stock-level version too.
- **Evidence**: Barbon & Buraschi SSRN 2021 (sample ~2010s, **not verified** magnitudes); SpotGamma/Nomura daily notes as practitioner confirmation. Return predictability (direction) is weak; vol predictability is the robust part.
- **Sources**: SqueezeMetrics (2017), "Gamma Exposure (GEX)" white paper. Barbon, A. & Buraschi, A. (2021), "Gamma Fragility", SSRN. Baltussen, Da, Lammers & Martens (2021), "Hedging demand and market intraday momentum", JFE.
- **Horizon / schedule**: 1-5 sessions; every_session (regime feature).
- **Data needed**: Cboe EOD OI and Greeks per strike (have; we compute Greeks). Intraday **missing** (use daily range).
- **Individual fit**: Overlay/regime only; no capacity issue.
- **Decoys / overlap**: VIX, odte_gamma_vol_regime (sister); the options family likely files GEX — treat as shared feature.
- **Verdict**: **Promising (as regime feature)** + **Ready**.

### lazy_prices_10k_change — Year-over-year 10-K/10-Q text change
- **Thesis**: Firms whose annual/quarterly filings change materially vs the prior year underperform over the following months; investors do not read the changes.
- **Mechanism**: Managers alter risk factors and MD&A when trouble brews; the change is buried in long documents and under-reacted to.
- **Persistence**: Reading costs; the signal is slow and low-attention; LLMs are now eroding it (**not verified**).
- **Rule (source's own)**: Cohen, Malloy & Nguyen (2020): cosine / Jaccard similarity between consecutive 10-K (10-Q) filings; long "non-changers" quintile / short "changers", monthly rebalance held 3 months; alpha roughly 30-60 bp/month (magnitude from memory, **not verified**), concentrated in risk-factor and legal sections and in the quarters after the filing.
- **Evidence**: J. Finance 2020, 1995-2014; post-publication decay plausible; Open Source AP includes a version (**not verified**).
- **Sources**: Cohen, L., Malloy, C. & Nguyen, Q. (2020), "Lazy Prices", J. Finance. Chen & Zimmermann (2022), Open Source Cross-Sectional Asset Pricing, CFR (https://www.openassetpricing.com).
- **Horizon / schedule**: 60-120 sessions; on_event:filing (10-K/10-Q acceptance timestamp).
- **Data needed**: EDGAR filing text (we store filing events, not text — fetchable from EDGAR full text; large), text-model seam optional (similarity needs no LLM).
- **Individual fit**: Long-only "non-changers" tilt works; low turnover.
- **Decoys / overlap**: Earnings surprise, distress; overlaps the alt-data/text family — flagged as frontier because the LLM-section variant (which sections changed, classified by the text model) is new.
- **Verdict**: **Promising** + **Needs data** (filing text ingestion).

### insider_10b5_1_plan_disclosure — Mandatory 10b5-1 plan adoption/termination disclosure (2023 rule)
- **Thesis**: Since 2023 firms must disclose in 10-Q/10-K (Item 408) when officers adopt or terminate Rule 10b5-1 trading plans; plan *terminations* and new sale plans by top insiders predict weaker returns, adoptions of purchase plans the opposite.
- **Mechanism**: Insiders time plan adoption (the SEC's cooling-off period was added for that reason); termination is a discretionary act that reveals a view.
- **Persistence**: New dataset (2023+), few parsers; small events.
- **Rule (source's own)**: No settled academic rule yet; pre-rule evidence: Jagolinzer (2009) 10b5-1 sales earn abnormal profits; Larcker, Lynch, Quinn, Taylor & Zhu (2021) "Gaming the system" — short cooling-off plans and single-trade plans are informed (**not verified** magnitudes).
- **Evidence**: Pre-2023 evidence is on Form 4 data (we do not store Form 4). Post-rule studies 2024-2026 exist in working-paper form (**not verified**).
- **Sources**: SEC Final Rule 33-11138 (Dec 2022) on Rule 10b5-1 and insider trading disclosures. Jagolinzer, A. (2009), "SEC Rule 10b5-1 and insiders' strategic trade", Management Science. Larcker et al. (2021), SSRN.
- **Horizon / schedule**: 20-60 sessions; on_event:filing.
- **Data needed**: 10-Q/10-K Item 408 text (EDGAR; text model to extract), **missing**; Form 4 **missing**.
- **Individual fit**: Avoid list; long-only on purchase-plan adoptions (rare).
- **Decoys / overlap**: Insider trading classic (events family); frontier because the disclosure is new.
- **Verdict**: **Promising** + **Needs data** (filing text + extraction); event count may be < 40 for purchases.

### single_stock_letf_flows — Single-stock leveraged ETF rebalancing demand
- **Thesis**: 2x single-stock ETFs (TSLL, NVDL, MSTU, etc.) must buy into closes after up days and sell after down days in proportion to AUM x return; in names where their AUM is large relative to ADV this amplifies close-to-close moves and adds predictable next-day reversal.
- **Mechanism**: Daily reset leverage; swap counterparties hedge near the close; flows are a known function of the day's return.
- **Persistence**: Product growth since 2022 (tens of billions in AUM in 2024-2025); retail buy-and-hold despite decay.
- **Rule (source's own)**: Cheng & Madhavan (2009) for index LETFs: rebalancing demand = sum (L^2 - L) x AUM x r_t; impact grows with AUM, leverage and volatility. Single-stock version: no published paper found (**not verified**); practitioner notes (SpotGamma, Bloomberg) on NVDL/TSLL flows.
- **Evidence**: Index-level LETF rebalancing was *rejected* in our list (intraday, weak after costs); single-stock concentration is far higher (AUM/ADV), so the effect may be material, but there is no academic evidence yet.
- **Sources**: Cheng, M. & Madhavan, A. (2009), "The Dynamics of Leveraged and Inverse ETFs", J. Investment Management. Bai, Bond & Hatch (2015), Real Estate Economics (LETFs raise end-of-day vol). Press on single-stock LETF AUM (not fetched).
- **Horizon / schedule**: 1 session; every_session.
- **Data needed**: Daily AUM/shares outstanding of single-stock LETFs: **missing** (ProShares has none in this space; Direxion/GraniteShares/REX/T-Rex not stored); daily bars (have).
- **Individual fit**: Next-day reversal in TSLA/NVDA/MSTR after large moves is tradable at EOD but small; mostly a conditioning feature for vol selling in those names.
- **Decoys / overlap**: Short-term reversal, meme_score_options; the rejected index-LETF edge.
- **Verdict**: **Weak** + **Needs data** (LETF AUM feed).

### scheduled_corporate_event_drift — Developer-conference / scheduled non-earnings event drift
- **Thesis**: Large tech names drift up into and through their scheduled flagship events (WWDC, Google I/O, Build) and, by extension, scheduled investor days, product launches and PDUFA dates attract pre-event buying.
- **Mechanism**: Attention and positioning ahead of a known catalyst; options demand pulls the stock (gamma); no forced seller.
- **Persistence**: Weak — attention effects decay and are widely known; sample is tiny.
- **Rule (source's own)**: Dujava (Quantpedia, 2025): long AAPL/GOOGL/MSFT from D-2 to D+2 around their developer conferences, 2011-09 to 2025-06: 6.67%/yr, vol 6.88%, Sharpe 0.97, max DD -12.8%; MSFT and GOOGL better than AAPL; no costs, no OOS.
- **Evidence**: Blog backtest, 3 stocks x ~14 years = ~42 events, selected from several variants (data-mining risk). Academic analogue: investor-day / product-announcement drift literature is thin (**not verified**).
- **Sources**: https://quantpedia.com/an-empirical-analysis-of-conference-driven-return-drift-in-tech-stocks/.
- **Horizon / schedule**: 4-5 sessions; on_event:scheduled_corporate_event.
- **Data needed**: An events calendar for non-earnings corporate events: **missing** (8-K Item 7.01/8.01 and press releases via text model could build one).
- **Individual fit**: Trivial to trade; capacity unlimited; edge small.
- **Decoys / overlap**: Mega-cap momentum 2011-2025; earnings/corporate events family (variant).
- **Verdict**: **Weak** + **Needs data** (event calendar); borderline on the 40-event floor.

### leveraged_etf_low_vol_regime — Hold leveraged index ETFs only in low-vol regimes
- **Thesis**: Volatility decay of daily-reset leveraged ETFs is a function of realised variance, so holding 2x/3x index ETFs only when realised/implied vol is low (and trend positive) captures most of the upside with far less decay.
- **Mechanism**: Compounding drag ~ L(L-1)/2 x variance; it is mechanical, not a mispricing; the edge is in regime timing of a known cost.
- **Persistence**: Arithmetic; the regime signal (vol) is persistent at monthly horizons.
- **Rule (source's own)**: Beluska (Quantpedia, 2025) "Leveraged ETFs in Low-Volatility Environments": hold leveraged ETF when a vol measure is below threshold (rule details **not verified**, page not fetched).
- **Evidence**: Blog backtest; consistent with the "volatility-managed" literature (Moreira-Muir 2017) and its weaker OOS (Cederburg et al. 2020).
- **Sources**: Quantpedia September 2025 roundup https://quantpedia.com/quantpedia-in-september-2025/; Moreira & Muir (2017), J. Finance; Cheng & Madhavan (2009).
- **Horizon / schedule**: 20 sessions; month_end or every_session with hysteresis.
- **Data needed**: SPY/QQQ/TQQQ/UPRO bars (have), VIX (have).
- **Individual fit**: Long-only, index-level, trivial costs; a position-sizing rule more than an edge.
- **Decoys / overlap**: Trend/TAA family's vol targeting; plain market beta.
- **Verdict**: **Weak (as alpha; useful as sizing)** + **Ready**.

### early_inclusion_runup_reversal — Fast-tracked index inclusions
- **Thesis**: Stocks added to a major index unusually early (large IPOs/spin-offs fast-tracked, mega-cap additions with short notice) run up ~5 pp into the effective date and give most of it back within three weeks, because arbitrageurs had less time to pre-position and passive demand hits at once.
- **Mechanism**: Passive trackers must buy at the close of the effective date; a short notice period concentrates the demand shock.
- **Persistence**: Index committees' discretion; passive share keeps growing (Chinco-Sammon).
- **Rule (source's own)**: Sammon (as reported in press on SpaceX early inclusion, 2026): early-included stocks earn ~5 pp excess return into inclusion and reverse within ~3 weeks (primary paper **not verified**; press report only). Greenwood & Sammon (2025): the average S&P 500 addition effect fell from 7.4% in the 1990s to < 1% in the last decade; deletions likewise.
- **Evidence**: J. Finance 2025 for the disappearance; the "early inclusion" subset is from a press report; Sandifer, Smith & Impink (Morningstar coverage) find post-inclusion underperformance vs matched peers over 3 years.
- **Sources**: Greenwood, R. & Sammon, M. (2025), "The Disappearing Index Effect", J. Finance 80(2) 657-698, SSRN 4294297. Press: https://sbsstar.net/article/N1008603570/ (SpaceX early inclusion). Morningstar https://www.morningstar.com/funds/sp-500-bump-that-doesnt-last.
- **Horizon / schedule**: 10-15 sessions after effective date; on_event:index_change.
- **Data needed**: S&P 500 changes with announcement and effective dates (have); notice-period length (compute); Nasdaq-100 changes (**missing** but public).
- **Individual fit**: Post-inclusion fade is a short; long-only variant is "do not chase additions in the first 3 weeks".
- **Decoys / overlap**: Rejected S&P-additions edge — this is explicitly a *variant* (short-notice subset + reversal, not the addition premium); event count since 2010 likely < 40 for "early".
- **Verdict**: **Weak** + **Ready** (as a variant; expect to fail the 40-event floor).

### overnight_return_persistence — Overnight vs intraday "tug of war"
- **Thesis**: A stock's past overnight returns predict its future overnight returns (and past intraday predicts intraday), and momentum profits accrue overnight; clientele with opposite beliefs trade at different times of day.
- **Mechanism**: Retail/attention traders act at the open, institutions during the day; persistent clienteles create persistent components.
- **Persistence**: Holding overnight only is costly (two trades per day), so the pattern is left alone.
- **Rule (source's own)**: Lou, Polk & Skouras (2019): sort on past 12-month overnight return; the overnight component persists; momentum, size, value premia are earned overnight vs intraday asymmetrically. Bogousslavsky (2021): cross-section of intraday vs overnight returns.
- **Evidence**: JFE 2019 and 2021; practitioner (Bespoke "overnight vs intraday SPY") shows aggregate overnight dominance 1993-2024; costs kill a two-trades-a-day retail implementation.
- **Sources**: Lou, D., Polk, C. & Skouras, S. (2019), "A tug of war: Overnight versus intraday expected returns", JFE. Bogousslavsky, V. (2021), "The cross-section of intraday and overnight returns", JFE.
- **Horizon / schedule**: 1 session (overnight); every_session.
- **Data needed**: Daily OHLC (have: overnight = open / prior close).
- **Individual fit**: Poor: requires trading the open and close every day; usable only as a *conditioning* feature (overnight share of momentum) on other edges.
- **Decoys / overlap**: Momentum, retail attention; stat-arb/technical family.
- **Verdict**: **Weak** (fit) + **Ready** as a feature.

### ai_exposure_amh — Generative-AI labour-exposure portfolio
- **Thesis**: Firms whose workforces are more exposed to generative AI gained after ChatGPT's release; exposure is a theme beta, not a persistent premium.
- **Mechanism**: One-off repricing of expected labour-cost savings and data complementarities.
- **Persistence**: None expected after the repricing; it is an event, not a mandate.
- **Rule (source's own)**: Eisfeldt, Schubert & Zhang (2023): occupation-task exposure scored by ChatGPT over 19,265 O*NET tasks, aggregated to 2,518 firms; "Artificial Minus Human" long high-exposure / short low-exposure earned ~0.4%/day in the two weeks after release.
- **Evidence**: NBER WP 31222 (2023); covers only the post-release window; no 2024-2025 return evidence found.
- **Sources**: Eisfeldt, A., Schubert, G. & Zhang, M. B. (2023), "Generative AI and Firm Values", NBER 31222 https://www.nber.org/papers/w31222.
- **Horizon / schedule**: event; not schedulable.
- **Data needed**: Firm exposure scores (not stored; constructible from the paper's public occupation scores + employee data we lack).
- **Individual fit**: As a theme/regime label only.
- **Decoys / overlap**: Growth/tech beta; momentum.
- **Verdict**: **Weak** (decoy / regime variable) + **Out of scope** as an edge.

### tech_sector_leadership — Industry momentum concentrated in tech eras
- **Thesis**: Buying the best 12-month industry (of 12 FF industries) and shorting the rest, held one month, has alpha but it is episodic (1970s, 1990s, 2020s) and timing filters do not help.
- **Mechanism**: Industry momentum (Moskowitz-Grinblatt) with a leadership concentration.
- **Persistence**: Episodic; flat for decades between tech eras.
- **Rule (source's own)**: Beluska (Quantpedia, 2025): rank 12 FF industries by 1-12m momentum; long top, short 11, equal weight, 1-month hold; 1926-2025; 8-12 month lookbacks best; 12-month-high and MA filters did not improve.
- **Evidence**: Blog backtest; long-short risk-adjusted metrics below long-only benchmarks.
- **Sources**: https://quantpedia.com/can-technology-sector-leadership-be-systematically-exploited/. Moskowitz & Grinblatt (1999), J. Finance.
- **Horizon / schedule**: 20 sessions; month_end.
- **Data needed**: Sector ETFs (have).
- **Individual fit**: Sector ETF rotation, long-only version is standard industry momentum.
- **Decoys / overlap**: Trend/TAA family (industry momentum) — overlap, not new.
- **Verdict**: **Weak / Decayed** + Ready (but belongs to the TAA family).

### election_uncertainty_collapse — Post-election-day short of risk-premium legs
- **Thesis**: The session after a US federal election, a basket of risk legs (XLK-SPY, EEM-SPY, IYR-SPY spreads, HYG, GLD, USO, UDN) tends to fall as the political-uncertainty premium collapses; 7-10Y Treasuries weaken into the election and rebound after.
- **Mechanism**: Uncertainty hedges unwind once the result is known.
- **Persistence**: Only 13 elections (9 with full data); each is one observation.
- **Rule (source's own)**: Quantpedia (2025/26): short equal-weight 7-leg basket close D+1 (2008-2024): 1.86%/yr, Sharpe 0.31, max DD -4.2%; IEF short D-4..D-1 then long D0..D+2 (2002-2024): 0.43%/yr, Sharpe 0.48.
- **Evidence**: Blog, in-sample, no costs; best in 2008/2016/2024.
- **Sources**: https://quantpedia.com/trading-the-multi-asset-drift-around-u-s-elections/.
- **Horizon / schedule**: 1-3 sessions; on_event:us_election (biennial).
- **Data needed**: ETFs (have).
- **Individual fit**: Trivial, but n = 13.
- **Decoys / overlap**: Calendar family's election cycle; EPU shocks.
- **Verdict**: **Weak** + **Out of scope** (fails the 40-event floor).

### retail_order_imbalance_decay — BJZZ retail order imbalance (documented decay)
- **Thesis**: Marketable retail order imbalance (identified from sub-penny prints) predicted next-week returns 2010-2015; it no longer does for large caps in 2016-2021.
- **Mechanism**: Retail flow was informative (or price-pressure) in the earlier period; internalisation changes and the rise of wholesaler competition altered the print signature.
- **Persistence**: Gone, per replication.
- **Rule (source's own)**: Boehmer, Jones, Zhang & Zhang (2021): sub-penny price improvement identifies retail trades in TAQ; weekly order-imbalance long-short. Ardia, Aymard & Cenesizoglu (2024): replication 2016-2021 — ROI loses predictive power for large caps; long-short no longer profitable; the QMP identification disagrees with BJZZ in the later period.
- **Evidence**: J. Finance 2021; arXiv 2403.17095 (GERAD G-2024-25) replication. Barber et al. (2024) BHJOS algorithm is an improved identifier (still TAQ).
- **Sources**: Boehmer, E., Jones, C., Zhang, X. & Zhang, X. (2021), "Tracking Retail Investor Activity", J. Finance. Ardia, D., Aymard, C. & Cenesizoglu, T. (2024), "Revisiting Boehmer et al. (2021)", arXiv:2403.17095.
- **Horizon / schedule**: 5 sessions; every_session.
- **Data needed**: TAQ **missing**; no EOD proxy exists (odd-lot share needs intraday prints).
- **Individual fit**: None.
- **Decoys / overlap**: Short-term reversal.
- **Verdict**: **Decayed** + **Needs data** (TAQ). Listed so it is not re-researched.

### treasury_refunding_equity — Quarterly refunding announcement as an equity event
- **Thesis**: The Treasury's quarterly refunding statement (coupon-size and bills/coupons mix) moves long yields (Aug 2023 +15 bp over two days; Nov 2023 relief rally) and therefore duration-sensitive equities (small caps, REITs, long-duration growth) in a direction knowable from the issuance surprise.
- **Mechanism**: Supply shocks to duration; equity duration proxies reprice with term premium.
- **Persistence**: Only when fiscal supply is the dominant macro story (2023-2025); weak otherwise.
- **Rule (source's own)**: No academic equity study found (search exhausted); practitioner: StoneX "Treasury refunding playbook from 2023" (yields fell after the bills-tilt announcement).
- **Evidence**: Anecdotal, 2023-2024 episodes; ~60 refunding announcements since 2010 is enough for a test.
- **Sources**: https://www.stonex.com/en-us/insights/treasury-refunding-playbook-from-2023-meets-a-new-surge-in-yields/; Treasury refunding statements https://home.treasury.gov/news/press-releases; Bloomberg 2024-01-31 coverage.
- **Horizon / schedule**: 1-5 sessions; on_event:treasury_refunding (first Wednesday of Feb/May/Aug/Nov, 08:30 ET; first tradable session is the same day's close).
- **Data needed**: Announcement dates (public), Treasury rates (have), style ETFs (have); the *surprise* needs the prior consensus (sell-side; **missing**) — proxy with the 10y move on the day.
- **Individual fit**: Index/style ETF timing; trivial costs; small expected size.
- **Decoys / overlap**: Macro family's rate-shock items; FOMC drift (decayed).
- **Verdict**: **Weak** + **Ready** (as a macro event tag).

### cta_positioning_proxy — Replicated trend-follower positioning as a flow signal
- **Thesis**: Replicating the standard CTA trend signals on equity index futures (via SPY/QQQ history) estimates the complex's position; when signals are near flipping, forced CTA selling/buying over the following sessions is predictable (the "CTA trigger levels" sell-side desks publish).
- **Mechanism**: Trend funds hold a few hundred billion in equity-index futures and trade on signal flips; the flip levels are computable in advance.
- **Persistence**: Mandate (systematic) — but the complex is smaller relative to the market than in 2008-2015, and signal heterogeneity blurs the flips.
- **Rule (source's own)**: Practitioner (Nomura, Goldman, Société Générale CTA index): ensemble of 1-3-12 month momentum / MA crossovers; estimated flow = change in aggregate signal x AUM. Academic: Hurst, Ooi & Pedersen (2017) "A Century of Evidence on Trend-Following"; crowding/flow effects of CTAs on index returns **not verified**.
- **Evidence**: No peer-reviewed evidence that CTA-flip proxies predict next-week index returns; sell-side back-tests only.
- **Sources**: Hurst, Ooi & Pedersen (2017), J. Portfolio Management; Baltas & Kosowski (2020), "Demystifying time-series momentum strategies: volatility estimators, trading rules and pairwise correlations" (capacity); Top Traders Unplugged podcasts (practitioner, not fetched).
- **Horizon / schedule**: 3-10 sessions; every_session.
- **Data needed**: SPY/QQQ/IWM bars (have); futures history via IBKR possible; CTA AUM constant assumption.
- **Individual fit**: Index timing overlay; tiny edge.
- **Decoys / overlap**: Plain trend (TAA family), vol_control_deleveraging_proxy.
- **Verdict**: **Weak** + **Ready**.

### green_flows_esg — Flow-driven green/ESG outperformance and its reversal
- **Thesis**: Green stocks' 2012-2020 outperformance was entirely unexpected climate-concern shocks and ESG fund inflows, not a premium; with ESG outflows (2022-2025) the expected return of brown over green is positive.
- **Mechanism**: Non-pecuniary demand (mandates) lowers green expected returns; flows into ESG funds pushed prices up transiently.
- **Persistence**: The *expected* brown premium is a slow factor; the flow effect reverses as flows stop.
- **Rule (source's own)**: Pastor, Stambaugh & Taylor (2022): green-minus-brown realised return explained by climate-concern shocks; expected green premium negative. van der Beck (2021): ESG outperformance fully accounted for by ESG fund flows (price pressure), implying reversal absent flows.
- **Evidence**: JFE/J. Finance-level 2021-2022; 2022-2024 ESG underperformance and outflows consistent; no clean OOS test of a trading rule.
- **Sources**: Pastor, L., Stambaugh, R. & Taylor, L. (2022), "Dissecting Green Returns", JFE. van der Beck, P. (2021), "Flow-Driven ESG Returns", Swiss Finance Institute WP.
- **Horizon / schedule**: 6-12 months; month_end.
- **Data needed**: ESG scores **missing**; ESG ETF flows (iShares ESGU etc. holdings/AUM: partial).
- **Individual fit**: Long-only brown tilt (energy, utilities) is a sector bet.
- **Decoys / overlap**: Energy sector beta, value; classic-factor family.
- **Verdict**: **Decayed (as a green premium) / Weak (brown tilt)** + **Needs data** (ESG scores).

### buyback_window_support — Open-window repurchase intensity after earnings
- **Thesis**: Heavy repurchasers can only execute after the post-earnings blackout lifts; their buying over weeks 1-6 after the report supports the stock, so the drift after earnings is stronger for high-repurchase-intensity firms.
- **Mechanism**: Corporate buying is mechanical (10b5-1 plans, ASR programmes) and concentrated in the open window.
- **Persistence**: Legal structure of blackouts; buyback volumes are large (~$900bn/yr S&P 500) but spread across many names.
- **Rule (source's own)**: Alpha Architect (2019) tested the *blackout* hypothesis (heavy buyback firms do worse during blackouts) and found no significant difference in any period — the mirror claim. Repurchase intensity itself (quarterly repurchases / market cap, from the cash-flow statement) predicts returns in the "net payout yield" literature (Boudoukh et al. 2007). New since 2023: issuers disclose daily repurchases by month in 10-Q/10-K tables (Item 703), enabling an open-window intensity measure (**no paper verified**).
- **Evidence**: Blackout effect: none (Alpha Architect 2019, S&P 500, period **not verified**). Net payout yield: positive, classic.
- **Sources**: https://alphaarchitect.com/2019/01/buyback-blackout-periods-do-not-negatively-impact-market-performance/; Boudoukh, Michaely, Richardson & Roberts (2007), "On the Importance of Measuring Payout Yield", J. Finance; SEC Share Repurchase Disclosure Modernization (2023, later vacated by the Fifth Circuit — check current status).
- **Horizon / schedule**: 20-30 sessions after earnings; on_event:earnings.
- **Data needed**: SEC cash-flow repurchases (have), shares outstanding (have), earnings dates (have); monthly Item 703 tables (text; **missing**).
- **Individual fit**: Long-only filter on PEAD longs; large caps.
- **Decoys / overlap**: Net payout yield (classic family), small-cap PEAD (filed). This is the *timing* variant.
- **Verdict**: **Weak** + **Ready** (quarterly version); blackout-timing version likely null.

### gold_miners_vs_bullion — Structural underperformance of gold shares vs gold
- **Thesis**: Gold-mining equities underperform bullion over long horizons despite operating leverage, so long-GLD / short-GDX is a slow carry on management, cost inflation and dilution.
- **Mechanism**: Miners dilute, hedge badly, face cost inflation and jurisdiction risk; investors pay for optionality that rarely pays.
- **Persistence**: Agency and industry structure.
- **Rule (source's own)**: Baur, Tay & Trench (2025), "Gold Shares Underperform Gold Bullion" (details **not verified**; Quantpedia Sept 2025 post).
- **Evidence**: Long-sample paper, 2025; 2024-2025 rally saw miners catch up strongly, so timing matters.
- **Sources**: Quantpedia https://quantpedia.com/quantpedia-in-september-2025/ ("Gold's Rally and the Gold Mining Stocks Trap").
- **Horizon / schedule**: months; month_end.
- **Data needed**: GLD, GDX bars (have).
- **Individual fit**: Pairs trade; short leg borrow easy (GDX).
- **Decoys / overlap**: Equity beta of miners; commodity/TAA family.
- **Verdict**: **Weak** + **Ready**; low priority for a US-equity platform.

---

## Rejected on sight (do not re-research)
- **Government shutdown effects**: no study found; 4-5 events since 2010; fails the 40-event floor.
- **Buyback blackout drawdown** (market weaker in blackout weeks): Alpha Architect 2019 found no effect; folded into buyback_window_support as a null.
- **Robinhood herding / Robintrack attention** (Barber-Huang-Odean-Schwarz 2022): data feed ended Aug 2020; not reproducible.
- **Pre-FOMC announcement drift** (Lucca-Moench 2015): decayed after 2015 per multiple replications; macro family's item.
- **Google Trends attention reversal** (Da-Engelberg-Gao 2011): needs a Trends feed; effect small post-publication.
- **Mutual-fund fire sales** (Coval-Stafford 2007): needs 13F/fund holdings; Wardlaw (2020) shows the standard measure is mechanically contaminated.
- **Short-squeeze / days-to-cover signals**: no short-interest or borrow data stored.
- **S&P 500 additions premium** and **index-level leveraged ETF rebalancing**: already rejected in the brief (variants filed above).
- **Russell reconstitution**: blocked (no membership data).
- **CPI-day announcement premium** (post-2021): macro family's item; evidence is a few dozen releases.
- **Options-expiration-week effect** (Stivers-Sun 2013): options/calendar family's item.
- **Macro "anomaly zoo" risk premia** (O'Doherty-Wang-Yan 2025): asset-pricing explanation, not a trade.
- **MicroStrategy valuation, crypto lessons, FX hedging, centuries-of-real-estate** (Quantpedia 2025 posts): out of our asset scope.
- **Classic characteristic sorts in large caps**: Chen & Welch (2026) median 7 bp/month post-2005 in non-micro stocks; do not add new characteristic-sort edges without a forced-flow or event mechanism.
