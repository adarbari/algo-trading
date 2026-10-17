# Edge ideas, family G. Stat arb, relative value and technical setups

Researched 2026-10-17 (deep-research agents; index and ranking: [README.md](README.md)). Ideas, not edges: nothing here is filed or tested. Figures marked *not verified*, *nv*, *recalled* or *from memory* must be checked against the source before an edge document cites them (quality bar item 5, [edges-plan.md](../edges-plan.md)).


**Family summary (5 lines).**
1. The only technical / relative-value ideas with a surviving, replicated, cost-robust edge are *cross-sectional* ones: short-term **residual** reversal (sector- / factor-neutral, large caps, 1-4 weeks), the **pre-earnings reversal** (So & Wang), the **high-volume return premium**, the **news-vs-no-news** conditioning of large daily moves, and long-horizon **52-week-high / trend-factor** continuation (which is mostly momentum, already filed).
2. Classic pairs trading (distance, cointegration, copula) is **decayed**: positive gross returns in the 1960s-90s fell to a few bps a month after 2002 and are unprofitable after realistic costs for most pairs; PCA / ETF-residual stat arb (Avellaneda-Lee) fell the same way and needs shorting plus daily turnover.
3. Short-term index/ETF mean reversion (RSI(2), IBS, Bollinger reversion, "oversold in uptrend") had a real post-1990s edge on SPY/QQQ-type ETFs that has shrunk sharply since ~2011; it remains a *timing overlay* rather than a stand-alone edge, and its 40-event history is easy to assemble.
4. Chart-reading rules (candlesticks, head & shoulders, cup-and-handle, MA crossovers on single stocks or indices, Bollinger bands as a stand-alone signal) **fail every data-snooping-aware test** (Sullivan-Timmermann-White 1999; Bajgrowicz-Scaillet 2012; Marshall-Young-Rose 2006); they can at most define *entry timing* or *risk placement* inside an edge whose mechanism lies elsewhere.
5. Our stored feature groups already compute most of the technical primitives (bands, candle, gaps, swing levels, pivot strength, retest, anchored VWAP, volume profile, relative strength, trend stats, `close_range_pos` = IBS, `stretch_*`, `pullback_to_sma20`, `breakout_*`); what is missing for this family is **residual returns vs sector/beta**, **pair/spread tables**, **ETF flows (shares outstanding of ETFs)**, **RSI(2) / ADX / OBV / Donchian-55**, and **chart-pattern detectors**.

**Research note.** The shared per-turn WebSearch budget was exhausted before this agent's first query, so the live evidence below comes from (a) pages fetched directly (Quantpedia strategy pages for pairs trading, country-ETF pairs, 52-week-high industry effect, pre-earnings reversal, large-cap short-term reversal, trend following on stocks; NBER abstract of Lo-Mamaysky-Wang) and (b) the author's knowledge of the literature. Numbers taken from memory are marked **(memory, not re-verified)**; nothing is invented, but the harness should re-check those before an edge document is written. SSRN, Alpha Architect and quantifiedstrategies.com returned 403 to the fetcher.

**How our features map onto the family (one glance).**

| Family idea | Stored today | Missing |
|---|---|---|
| IBS, close-location | `close_range_pos`, `strong_close`, `close_streak` | nothing |
| RSI(2)/Connors | `rsi_14`, `pct_vs_sma_200`, `sma_20`, `stretch_sma20_atr`, `pullback_to_sma20`, `price_z_20d`, `ret_z_20d`, `ret_3d/5d`, `ret_5d_pctile` | `rsi_2`, `rsi_4`, cumulative-RSI |
| Bollinger / Keltner | `bb_lower/upper/pct_b/width/width_pctile_252d/squeeze`, `kc_lower/upper/position`, `band_walk` | nothing |
| 52-week high / breakout | `high_52w`, `dist_52w`, `near_52w`, `pct_from_high_52w`, `pct_52w_range`, `breakout_20d/50d`, `breakout_level/date/magnitude/failed/retest_held`, `prior_high_*`, `donchian_pos_20d` | 55-day Donchian, all-time-high flag (history > 1y needed) |
| Vol contraction | `bb_squeeze`, `bb_width_pctile_252d`, `tight_range_sessions`, `range_20d_pct`, `atr_ratio_5_20`, `inside_day_breakout`, `hv_ratio_10_60` | NR7 flag (trivial expression over `range_sessions`?) |
| Gaps | `gap_open_pct`, `gap_above/below (+date, dist)`, `earnings_volume_ratio` | gap-fill outcome (an outcome grain), "unfilled gap" count |
| Candles | `candle`, `body_share`, `upper/lower_wick_share`, `body_vs_avg_20d`, `bar_relation` | multi-bar patterns beyond what `candle` encodes |
| Support / resistance / round numbers | `dist_to_support/resistance (+_atr)`, `support/resistance_touches/_age`, `pivot_structure`, `swing_high/low`, `retest_state`, `poc_252d`, `value_area_*`, `hvn/lvn_*` | round-number distance (expression over `close`) |
| MA crossovers / trend | `ema_10/20/50/200`, `sma_20/50/150/200`, `ema_stack`, `trend_state`, `trend_r2_90d`, `reg_slope_90d_ann`, `clenow_momentum_90d`, `sma200_slope_20d`, `ema20_slope_5d` | ADX/DMI |
| Volume confirmation | `rel_volume`, `volume_z_20d`, `volume_pctile_252d`, `cmf_20d`, `up_volume_share_20d`, `pocket_pivot`, `volume_dry_up`, `volume_climax`, `volume_trend_20_60`, `volume_near_close_share` | OBV (cumulative; expressible), accumulation/distribution line |
| Relative strength | `rs_spy_63d/252d`, `rs_spy_trend_20d`, `rs_line_high_252d`, `rs_sector_63d`, `sector_rank_63d`, `sector_leader`, `rs_improving`, `mom_12_1`, `mom_pctile_*` | IBD-style weighted 12m RS rank (expression) |
| Anchored VWAP | `avwap_earnings`, `avwap_swing_high/low`, `avwap_anchor_date` | nothing |
| Residual / pairs / lead-lag | `beta_252d`, `corr_252d`, `sector_etf`, `sector_ret_63d`, ETF holdings | residual return vs sector ETF & beta (1d/5d/20d), pair tables, cointegration stats, ETF shares outstanding / flows |

---

### residual_reversal_sector_neutral — Short-term residual reversal (large caps, industry- and factor-neutral)
- **Thesis**: a large-cap stock that fell last week *relative to its sector and its beta* bounces over the next 1-4 weeks; the raw "losers bounce" effect is dead, the residual one is alive.
- **Mechanism**: liquidity provision. Uninformed order imbalance (fund flows, index trades, forced sellers) pushes a name away from where its sector and factor exposures say it should be; market makers and stat-arb desks are paid to lean against it. Stripping out sector/factor moves removes the part of last week's return that is *informed* (industry and factor momentum), leaving the part that is noise.
- **Persistence**: costs. The return is a few tens of bps a week, so it only survives in liquid large caps and with low turnover; shorting the winners' leg and weekly rebalancing deter most mandated capital; it is "short volatility" (losses in crashes, gains after them), which allocators dislike.
- **Rule (source's own)**: Blitz, Huij, Lansdorp & van Vliet (2013): each month, regress the past 36 months of returns on Fama-French factors, take last month's residual, go long the lowest decile / short the highest, hold one month. Groot, Huij & Zhou (2012): 100 largest US stocks, weekly, long the 10 worst prior-week, short the 10 best, rebalance weekly. Blitz et al. (2020, "enhanced" version): neutralise short-term *industry* momentum and factor momentum before sorting; also Hameed & Mian (2015) intra-industry reversal.
- **Evidence**: Groot-Huij-Zhou: 1990-2009, 29 bps/week net of Nomura cost estimates in the 100-stock universe (Sharpe ~1.1); negative net in a 1,500-stock universe (verified via Quantpedia). Blitz et al. 2013: residual reversal roughly doubles the Sharpe of conventional reversal and is stable through time (memory). Blitz et al. 2020: the classic effect "has steadily weakened over time" and vanished in most regions, while the industry/factor-neutral version keeps working (Quantpedia summary, verified). Quantpedia's own OOS test of the simple large-cap version is described as deteriorating. Chen-Zimmermann OSAP lists STreversal as still significant gross but it is a costly signal.
- **Sources**: Blitz, Huij, Lansdorp, van Vliet, "Short-term residual reversal", JFM 2013; de Groot, Huij, Zhou, "Another look at trading costs and short-term reversal profits", JBF 2012; Blitz, Hanauer, Honarvar, Huisman, van Vliet, "Beyond Fama-French factors: the enhanced short-term reversal", 2020/2021; Hameed & Mian, "Industries and stock return reversals", JFQA 2015; Quantpedia https://quantpedia.com/strategies/short-term-reversal-in-stocks/ .
- **Horizon / schedule**: 5-20 sessions; every_session (or weekly rebalance).
- **Data needed**: daily bars (have), sector ETF or GICS sector (have `sector_etf`, `sector_ret_63d`), `beta_252d`; **missing**: a residual-return feature (1d/5d/20d return minus beta × sector-ETF return, or minus SPY+sector), ideally an industry level finer than 11 sectors (ETF holdings of sector SPDRs can give it). Point in time: known at close T, act at open T+1.
- **Individual fit**: long-only variant (buy the residual losers in the S&P 500, hold 5-10 sessions) keeps most of the long-leg return; shorting winners is optional. Capacity ample in large caps; cost is the whole story: spreads and slippage must be < 10 bps round trip.
- **Decoys / overlap**: bid-ask bounce (use midpoint or next-open entry), earnings reactions (exclude names within ±3 sessions of earnings, or route them to `earnings_neutral_reversal`), the filed "small-cap post-earnings drift" (opposite sign for news-driven moves). The long leg is a dip-buy on beta; benchmark against sector ETF, not SPY.
- **Verdict**: **Promising**; feasibility **Ready** once a residual-return feature exists (`add-feature`, expression over `ret_5d` and sector-ETF `ret_5d` × `beta_252d`).

### earnings_neutral_reversal — Pre-earnings reversal (So & Wang)
- **Thesis**: among large caps, the names that fell in the 3 sessions before an earnings date outperform the ones that rose, over the announcement window, by ~1.5% long-short.
- **Mechanism**: liquidity providers demand higher compensation for holding inventory into a known information event; price pressure before the event is reversed as the event resolves the risk (So & Wang 2014). Nobody "fixes" it because the compensation is for a real risk (the announcement).
- **Persistence**: it is a risk premium for inventory risk around scheduled news; it needs daily rebalancing across ~1,000 announcers and short positions, so it is unattractive to large funds.
- **Rule (source's own)**: largest size quintile; rank by average return over t-4..t-2 (t = announcement day); long the bottom quintile, short the top; hold t-1, t, t+1; equal-weighted (verified via Quantpedia).
- **Evidence**: 1996-2011: LOW-HIGH 3-day return 1.45% vs 0.22% in pseudo-announcement windows; Q5 158.8 bps; Sharpe 1.73 as annualised by Quantpedia; **no costs deducted**; Quantpedia's OOS backtest "slightly negative", alpha deteriorating (verified). Jansen & Nikiforov report profitability in 40 of 42 years with >1.3% two-day abnormal return (Quantpedia summary).
- **Sources**: So & Wang, "News-driven return reversals: liquidity provision ahead of earnings announcements", JFM 2014 (SSRN 2275982); Jansen & Nikiforov, "Fear and greed: a returns-based trading strategy around earnings announcements"; Quantpedia https://quantpedia.com/strategies/reversal-during-earnings-announcements/ .
- **Horizon / schedule**: 3 sessions; on_event:earnings (enter at close t-2 or open t-1).
- **Data needed**: `earnings_schedule` (`next_earnings_date`, `date_confirmed`, `earnings_time`), `ret_3d`, `market_cap`; all stored. Must use *confirmed* dates known at t-2 (no lookahead on the date).
- **Individual fit**: long-only version (buy pre-earnings losers in large caps, hold through the print) captures the long leg but takes event risk; 3-day holding, ~5-30 names a night in earnings season, fine for a retail account; options overlay: the filed "earnings announcement premium" found no premium, so do not expect that part.
- **Decoys / overlap**: bid-ask bounce; overlaps the filed *momentum at earnings* (opposite sign: that one is longer-horizon) and the *small-cap PEAD* (different size bucket). Decoy: pre-announcement drift from early leaks (would predict continuation, not reversal: test it).
- **Verdict**: **Promising**; feasibility **Ready** (40+ events every quarter).

### large_move_news_vs_no_news — Reversal after large moves without news, continuation with news
- **Thesis**: a stock that moved >=5-10% in one day *without* a filing or headline reverses part of it in the next 1-20 sessions; the same move *with* a disclosed cause continues (drift).
- **Mechanism**: no-news moves are liquidity shocks (block trades, forced flows, fat fingers) that market makers absorb and reverse; news moves are under-reaction to hard information (Chan 2003; Pritamani & Singal 2001). Investors lump both together and under-differentiate.
- **Persistence**: classifying news in real time is work; the reversal leg is a liquidity-provision premium; the continuation leg is the usual slow-diffusion story (overlaps PEAD).
- **Rule (source's own)**: Pritamani-Singal (2001): daily moves beyond ±3 std dev (or ±10%) on NYSE/AMEX; with WSJ news and/or volume shock, 20-day abnormal return ~+2% for winners / continuation for losers; without news, reversal. Chan (2003): monthly sorts; losers with news drift down ~2-3%/month further; no-news extreme movers reverse (memory, not re-verified). Bremer & Sweeney (1991): after a -10% day, +1.8% over the next two days (memory). Cox & Peterson (1994) showed the two-day bounce shrank through the 1980s (bid-ask bounce component).
- **Evidence**: effects were sizable in 1980s-90s samples; the no-news reversal has shrunk with decimalisation (bid-ask bounce was part of it); the news-continuation leg is the robust part and is the one closest to the filed PEAD. Recent replications (Chen-Zimmermann include "Mom1m" and "AnnouncementReturn"/"EarnSupBig", but not this exact split) — not verified.
- **Sources**: Pritamani & Singal, "Return predictability following large price changes and information releases", JBF 2001; Chan, "Stock price reaction to news and no-news: drift and reversal after headlines", JFE 2003; Bremer & Sweeney, "The reversal of large stock-price decreases", JF 1991; Cox & Peterson, JF 1994.
- **Horizon / schedule**: 1-20 sessions; on_event:large_move (`one_day_move`, `ret_1d` beyond k × `hv20`).
- **Data needed**: `ret_1d`, `one_day_move`, `hv20`, `rel_volume`, 8-K items and capped headlines through the text-model seam (brief: events/filing stored; headline feed is capped). ADR 0050 unscheduled-move attribution already classifies "own-news vs none": reuse it. Missing: full news feed (partial coverage will mislabel some news moves as no-news; bias is toward *weaker* measured reversal, acceptable).
- **Individual fit**: long-only on no-news drops in liquid names is natural; 5-20 events a week across the universe; costs modest because holding 2-10 days.
- **Decoys / overlap**: earnings-day moves (exclude; filed PEAD), index rebalances, dividend/split adjustments, bid-ask bounce in illiquid names (restrict to `liquidity_class` high), the 2026 universe is too short for the 8-K-classified history unless Tiingo backfill + EDGAR history are joined.
- **Verdict**: **Promising**; feasibility **Needs data** (historical event classification; the stored 8-K history solves the filing leg; headline history is capped).

### high_volume_return_premium — Volume shock premium (Gervais-Kaniel-Mingelgrin)
- **Thesis**: a stock whose daily volume is extremely high relative to its own recent history earns a positive abnormal return over the following 20-100 sessions, especially if small-mid cap.
- **Mechanism**: visibility (Miller 1977 / Merton 1987): a volume shock puts the stock on more screens; with short-sale constraints the extra attention brings net buying. The sellers (those providing the volume) are not wrong, they just do not price the attention effect.
- **Persistence**: small per-event, works best in smaller names where capacity is low; attention is a behavioural constant.
- **Rule (source's own)**: on the last day of a 50-day reference period, classify the day's volume as "high" if it is in the top 10% (or top 5%) of the previous 49 days; long high-volume stocks (or long high / short low) and hold 20-100 trading days; equal weight. Zero-investment high-minus-low 20-day returns of 0.94% / 1.07% / 0.50% per dollar long for small / medium / large NYSE firms, 1963-1996, daily sample, Table 2 (corrected; was "around +0.5%/month", the large-firm figure); international confirmation in Kaniel, Ozoguz & Starks (2012).
- **Evidence**: original 1963-1996 NYSE; Kaniel-Ozoguz-Starks 2012 JFE confirm in 41 countries, strongest where information is scarcer. Post-publication decay in the US: Chen-Zimmermann's OSAP has no GKM high-volume-premium signal; its volume predictors are Haugen-Baker's VolMkt and VolumeTrend (1979-1993) and Lee-Swaminathan's MomVol (corrected; was "high volume premium variants"); no post-publication US figure for GKM is tabulated there (figure dropped: not stated in OSAP's SignalDoc).
- **Sources**: Gervais, Kaniel & Mingelgrin, "The high-volume return premium", JF 56(3) 2001 877-919 (working paper read: https://rodneywhitecenter.wharton.upenn.edu/wp-content/uploads/2014/04/9901.pdf); Kaniel, Ozoguz & Starks, "The high volume return premium: cross-country evidence", JFE 103(2) 2012; Chen & Zimmermann, Open Source Asset Pricing, https://github.com/OpenSourceAP/CrossSection (SignalDoc.csv).
- **Horizon / schedule**: 20 sessions (up to 100); every_session (or weekly).
- **Data needed**: `volume_z_20d`, `volume_pctile_252d`, `rel_volume`, `session_volume`; a 50-day percentile is a trivial expression. All stored.
- **Individual fit**: long-only is the paper's natural form; capacity limited in small caps but a retail account is small; 20-day hold keeps costs low.
- **Decoys / overlap**: earnings-day volume (filed PEAD; exclude or test separately), index additions (rejected edge), the `episodic_pivot` below is this idea plus a gap and news filter. Benchmark vs size-matched peers.
- **Verdict**: **Promising**; feasibility **Ready**.

### episodic_pivot_gap_volume — Qullamaggie "episodic pivot" (big gap on news + volume, after a dormant base)
- **Thesis**: a stock gapping up >=10% on a fundamental catalyst with 3x+ relative volume, after months of nothing, keeps going for weeks; buy the first day (or the first pullback) and trail.
- **Mechanism**: it is PEAD + the high-volume premium + a liquidity trap for shorts: a neglected name re-rates in steps as analysts, funds and momentum screens catch up; the first day under-reacts because the news is bigger than the pre-event holders.
- **Persistence**: a discretionary playbook, not a fund strategy; capacity small (mid/small caps); needs same-day action.
- **Rule (source's own)**: no published rule with numbers; practitioner (Kullamägi) description: gap up >=10% on earnings/guidance/news, volume on day 1 far above average, stock had gone sideways or down for months (not already extended), buy the day-1 opening-range high break or day-2 continuation, stop at day-1 low, trail on 10/20-day MA. Academic cousins: the news-continuation leg of Pritamani-Singal; PEAD with "neglected" interaction; "earnings surprise with large volume" (Lerman, Livnat & Mendenhall 2007 memory).
- **Evidence**: no peer-reviewed test of the exact template. Overlapping academic evidence (PEAD, high-volume premium, news continuation) is positive; the filed small-cap PEAD already carries the earnings subset.
- **Sources**: Pritamani & Singal 2001; Gervais-Kaniel-Mingelgrin 2001; Bernard & Thomas 1989 (PEAD); practitioner material by Kristjan Kullamägi (public talks/blog, not a study).
- **Horizon / schedule**: 10-40 sessions; on_event:gap_up (`gap_open_pct` >= 0.10 and `rel_volume` >= 3 and `pct_52w_range` / `dist_to_high_50d` showing a prior base).
- **Data needed**: gaps, volume, 52w-range, earnings/8-K link (have); entry is EOD day 1 (we cannot do the intraday opening-range entry; test the close-of-day-1 entry).
- **Individual fit**: long-only; 1-5 events a week; big single-name variance; needs stops.
- **Decoys / overlap**: filed *small-cap PEAD* and *momentum at earnings* cover the earnings subset; what is new is the non-earnings catalyst subset (FDA, contracts, M&A) and the "dormant base" filter. Decoy: it is just PEAD with a volume filter; test the increment.
- **Verdict**: **Promising** as a *variant of the filed PEAD* (say so in the filing); feasibility **Ready** for the EOD-entry version.

### ibs_etf_mean_reversion — Internal Bar Strength on equity index ETFs
- **Thesis**: when an index ETF closes near its daily low (IBS = (C-L)/(H-L) < 0.2), the next session's return is positive on average; near the high, flat or negative.
- **Mechanism**: end-of-day order imbalance (MOC flows, hedging, futures-cash arbitrage) over-shoots into the close and is mean-reverting overnight; index-level, so no stock-specific information to lose.
- **Persistence**: tiny per-trade (tens of bps), holding one day, which rules out capacity-seeking funds; it is also partly the overnight premium in disguise.
- **Rule (source's own)**: Pagonidis (2013): buy at close when IBS < 0.2 (or lowest quintile), exit next close; or long IBS<0.2 / short IBS>0.8; across ~20 equity index ETFs since 1993 the low-IBS day returns dominated total returns (memory, not re-verified).
- **Evidence**: strong pre-2010; practitioner follow-ups (Quantified Strategies, Alvarez) report a diminished but still positive SPY/QQQ effect through the 2010s and a weak one since 2020 (memory). It shares fate with RSI(2): the whole "short-term index mean reversion" cluster faded after ~2011.
- **Sources**: Pagonidis, "The IBS effect: mean reversion in equity ETFs", SSRN 2013 (not fetched: 403); Connors & Alvarez, *Short Term Trading Strategies That Work* (2009); quantifiedstrategies.com IBS articles (not fetched).
- **Horizon / schedule**: 1 session; every_session.
- **Data needed**: `close_range_pos` (= IBS) on ETFs: stored. Nothing missing.
- **Individual fit**: long-only, one-day holds in SPY/QQQ/IWM/sector ETFs, near-zero spread cost; the issue is that the edge is a few bps per trade now.
- **Decoys / overlap**: the overnight premium (close-to-open), VIX regime (works when `vix` elevated), the filed VRP (same short-vol flavour). It is a *timing overlay* for other edges' entries rather than a stand-alone edge.
- **Verdict**: **Weak** stand-alone / **Promising as overlay**; feasibility **Ready**.

### rsi2_connors_etf_pullback — RSI(2) / Connors short-term mean reversion above the 200-day
- **Thesis**: buy an index ETF (or liquid large cap) when RSI(2) < 5-10 while the close is above its 200-day SMA; sell when the close is back above the 5-day SMA.
- **Mechanism**: same as IBS: short-horizon over-shoots inside an uptrend are liquidity-driven and get bought; the 200-day filter avoids catching knives in bear regimes.
- **Persistence**: the published record is the problem: after the 2008-09 books the SPY edge shrank; what remains is the regime filter (buy dips in uptrends), a mild, widely known behaviour.
- **Rule (source's own)**: Connors & Alvarez (2008/2009): close > SMA200, RSI(2) < 5 (variants: < 10; cumulative RSI(2) over 2 days < 35; "Double 7s" = 7-day low entry / 7-day high exit; "%b" variants), exit close > SMA5 or RSI(2) > 65-70. SPY 1993-2008 roughly 75-80% winners, average trade ~+0.5-1% (memory, not re-verified).
- **Evidence**: in-sample 1993-2008 strong; Alvarez's own post-publication tests (blog, 2016-2023) show the SPY edge falling to a fraction after 2010 and essentially gone in some variants after 2017 (memory; the page returned 404 on fetch); independent reproductions (Quantified Strategies, QuantStart posts) agree on the direction. On single stocks the raw RSI(2) rule is noise once costs are included.
- **Sources**: Connors & Alvarez, *Short Term Trading Strategies That Work* (TradingMarkets 2009); Connors, *How Markets Really Work* (2004/2012); Alvarez Quant Trading blog (RSI2 tests, 2016-2023; not fetched); Zakamulin (2014) on the general OOS failure of index-timing rules.
- **Horizon / schedule**: 3-7 sessions; every_session.
- **Data needed**: `rsi_14` stored, **RSI(2) not stored** (add as a window feature to `momentum`); `sma_200`, `sma_20`, `pct_vs_sma_200` stored; `pullback_to_sma20`, `stretch_sma20_atr`, `price_z_20d`, `ret_z_20d` are usable substitutes today.
- **Individual fit**: perfectly sized for one person; costs trivial on SPY/QQQ; the issue is the size of the edge.
- **Decoys / overlap**: overnight premium; it is the same cluster as IBS and `oversold_in_uptrend_pullback`; include only one filing with variants.
- **Verdict**: **Decayed** (still a usable entry-timing overlay); feasibility **Ready** (RSI(2) is a one-line feature).

### oversold_in_uptrend_pullback — Pullback to the 20/50-day in a strong trend (single stocks)
- **Thesis**: a stock in a confirmed uptrend (above rising 50/200-day, `ema_stack` bullish) that pulls back 1-2 ATR below its 20-day EMA or to the 50-day resumes the trend within 5-20 sessions.
- **Mechanism**: combination of medium-term momentum (12-1 filed) and short-term reversal (residual reversal above): the two signals have opposite horizons and positive diversification; a pullback is the point where both agree. Forced sellers are short-horizon momentum chasers who are stopped out; buyers are slow trend followers.
- **Persistence**: as long as momentum and short-term reversal both persist, their intersection persists; it is capacity-rich in large caps.
- **Rule (source's own)**: no single canonical paper; practitioner (Connors "pullback" systems, Minervini, Clenow *Stocks on the Move* uses MA filter + ranking, not pullbacks). Academic: combining 12-1 momentum with 1-month reversal (Asness 1994; Novy-Marx 2012 "intermediate momentum"); Han, Yang & Zhou 2013 MA timing by volatility deciles; Han, Zhou & Zhu 2016 "trend factor" (cross-section of MA signals at several horizons, 1.6%/month 1930-2014 memory).
- **Evidence**: the ingredient evidence is strong (momentum, STR, trend factor); the pullback template as such has only practitioner backtests (TradingMarkets, Alvarez, quantifiedstrategies) with positive but unaudited results. Han-Zhou-Zhu's trend factor survived a long sample and later tests (Jensen-Kelly-Pedersen include a trend-factor variant; not verified).
- **Sources**: Han, Zhou & Zhu, "A trend factor: any economic gains from using information over investment horizons?", JFE 2016; Han, Yang & Zhou, "A new anomaly: the cross-sectional profitability of technical analysis", JFQA 2013; Novy-Marx, "Is momentum really momentum?", JFE 2012; Connors & Alvarez 2009.
- **Horizon / schedule**: 5-20 sessions; every_session.
- **Data needed**: `ema_stack`, `trend_state`, `pct_vs_ema_20`, `stretch_sma20_atr`, `pullback_atr_20d`, `pullback_to_sma20`, `sma200_slope_20d`, `rs_spy_252d`: all stored.
- **Individual fit**: long-only, large-cap, few trades a week; costs small.
- **Decoys / overlap**: it is momentum (filed 12-1) with an entry-timing rule; the test is whether the pullback entry *adds* to a momentum portfolio (better entry, lower vol), not whether it beats cash.
- **Verdict**: **Promising as momentum entry-timing**; feasibility **Ready**.

### trend_factor_ma_cross_section — Han-Zhou-Zhu trend factor (cross-sectional MA signals)
- **Thesis**: rank stocks by the fitted expected return from a cross-sectional regression of returns on normalised moving averages of several lengths (3 to 1000 days); long the top decile, short the bottom.
- **Mechanism**: short, intermediate and long MA signals carry reversal, momentum and long-run reversal respectively; the regression weights them optimally each month; it exploits the same slow-diffusion / over-reaction mix as the three underlying anomalies.
- **Persistence**: same as momentum/reversal; higher turnover than 12-1 momentum; performed well in 2008-09 when momentum crashed (memory).
- **Rule (source's own)**: monthly; MA lengths 3, 5, 10, 20, 50, 100, 200, 400, 600, 800, 1000 days normalised by price; cross-sectional regression of next-month return on the MA ratios, coefficients averaged over the past 12 months; sort on fitted value; decile L/S, value- or equal-weighted.
- **Evidence**: 1.63%/month trend-factor return 1930-2014, roughly twice momentum with lower crash risk (memory, not re-verified); replicated internationally (Liu, Zhou, Zhu 2020s papers in China). Post-publication US performance: reportedly weaker but positive (not verified).
- **Sources**: Han, Zhou & Zhu, JFE 2016; Jensen, Kelly & Pedersen, "Is there a replication crisis in finance?", JF 2023 (global factor data).
- **Horizon / schedule**: 20 sessions; month_end.
- **Data needed**: all MAs up to 200 stored; MA 400-1000 need >4 years of bars (Tiingo backfill). Cross-sectional regression is a new rollup (features over the cross-section), not an expression.
- **Individual fit**: long-only top decile with monthly rebalance is fine; it is a factor portfolio (50+ names).
- **Decoys / overlap**: overlaps filed 12-1 momentum and `residual_reversal`; file as a *variant* if at all.
- **Verdict**: **Promising**; feasibility **Needs data** (long history) and a new rollup kind.

### breakout_52w_high_trend_following — Buy new 52-week / all-time highs with an ATR trailing stop (Wilcox-Crittenden)
- **Thesis**: buying every stock closing at an all-time high (or 52-week high) and exiting on a 10-ATR trailing stop produced a fat right tail and ~19% a year 1983-2004.
- **Mechanism**: anchoring on the prior high (George & Hwang 2004): traders are reluctant to buy at a high, so good news is incorporated slowly; the ATR stop lets the few huge winners run (skewness, not win rate).
- **Persistence**: the payoff is a long-right-tail with a <50% win rate and long drawdowns, which most managers cannot hold; daily turnover of entries makes the base version unviable at small size after costs (Zarattini et al. 2024).
- **Rule (source's own)**: Wilcox & Crittenden (2005): US stocks above a minimum price and liquidity; buy when close >= highest close in history; exit on a 10-period ATR trailing stop; long-only, equal weight, 0.5% round-trip cost; 1983-2004: 19.3% annual, 15.6% vol, -33.7% MDD, Sharpe 1.24 (verified via Quantpedia). Zarattini, Pagani & Wilcox (2024): 1991-2024 gross CAGR 15.19%; "modest decline in average trade profitability" post-2005; base approach not viable under ~$1M after costs; a turnover-controlled variant fixes it (verified via Quantpedia summary).
- **Evidence**: as above; George & Hwang 2004 (nearness to 52-week high predicts returns, ~0.5%/month L/S 1963-2001, memory); Hong, Jordan & Liu industry-level 52-week-high: 0.60%/month 1963-2009, Sharpe ~0.7, Quantpedia OOS slightly negative (verified). Chen-Zimmermann's High52 shows a notable post-publication decline (direction verified by memory, magnitude not).
- **Sources**: Wilcox & Crittenden, "Does trend following work on stocks?", Blackstar 2005; Zarattini, Pagani & Wilcox, 2024, SSRN 5084316; George & Hwang, "The 52-week high and momentum investing", JF 2004; Hong, Jordan & Liu, "Industry information and the 52-week high effect", 2015; Quantpedia pages (fetched).
- **Horizon / schedule**: 60-250 sessions (stop-based); every_session.
- **Data needed**: `high_52w`, `near_52w`, `dist_52w`, `atr_14`, `atr_20`, `breakout_level`; all-time high needs the full Tiingo history (coming). Delisted names essential (survivorship): Tiingo backfill includes them.
- **Individual fit**: long-only by design; the turnover-controlled variant (cap entries per week, or weekly entry only) is what a retail account should test; wide stops mean 20-50 open positions.
- **Decoys / overlap**: it *is* momentum (filed 12-1) with a different entry and a stop; the increment to test is skewness and drawdown profile, not mean return. Decoy: beta and small-cap exposure in the 1990s sample.
- **Verdict**: **Promising**; feasibility **Needs data** (10+ years of history incl. delisted; arriving).

### nearness_52w_high_cross_section — George-Hwang 52-week-high ratio (monthly cross-section)
- **Thesis**: stocks whose price is close to their 52-week high outperform those far from it over the next 6-12 months, more reliably than past-return momentum.
- **Mechanism**: anchoring (traders use the 52w high as a reference and under-react near it); the long leg is the surviving part.
- **Persistence**: the usual momentum arguments; but it decayed post-publication like most price-based anomalies.
- **Rule**: monthly, rank on P / 52w-high; long top 30% / short bottom 30%; hold 6 months with overlapping portfolios; skip January.
- **Evidence**: 1963-2001 L/S ~0.45-0.5%/month and dominates JT momentum in horse races (memory); later work: Bhootra & Hur 2013 (recency of the high matters), Hong-Jordan-Liu industry version (verified above). McLean-Pontiff style decay: post-publication roughly half or less (direction verified, magnitude not).
- **Sources**: George & Hwang JF 2004; Bhootra & Hur, "The timing of 52-week high price and momentum", JBF 2013; Chen & Zimmermann OSAP (High52).
- **Horizon / schedule**: 120 sessions; month_end.
- **Data needed**: `near_52w`, `pct_from_high_52w`, `sessions_since_high_20d` (a 52w analogue for recency would be an easy feature). Stored.
- **Individual fit**: long-only top tercile; low turnover.
- **Decoys / overlap**: overlaps filed 12-1 momentum heavily; file only as a variant ("52w-high ranking instead of 12-1 return") and test the increment.
- **Verdict**: **Weak as a new edge** (variant of momentum); feasibility **Ready** (12 months of history already; 40 monthly events need 4+ years: Tiingo backfill).

### etf_flow_reversal_constituents — ETF non-fundamental demand predicts reversal in its holdings
- **Thesis**: when an ETF takes in heavy creations (flows), its constituents are pushed up by arbitrage and reverse over the next weeks; redemptions do the opposite.
- **Mechanism**: ETF arbitrage transmits non-fundamental demand (retail / allocator flows) to the basket; APs hedge by trading constituents; the price pressure is temporary (Ben-David, Franzoni & Moussawi 2018; Brown, Davies & Ringgenberg 2021).
- **Persistence**: ETF flows are growing, not shrinking; the reversal is spread across many stocks and horizons, which is costly to harvest fully, so it persists in smaller / less liquid baskets.
- **Rule (source's own)**: Brown-Davies-Ringgenberg: monthly ETF flows (shares outstanding changes × NAV) aggregated to stock-level "ETF flow pressure"; long low-flow-pressure stocks, short high; 1-3 month horizon; returns of several percent a year L/S (memory, not re-verified). Ben-David et al.: stocks with higher ETF ownership have more volatility and more reversal.
- **Evidence**: 2000s-2010s samples; both papers in top journals; no public decay study yet.
- **Sources**: Ben-David, Franzoni & Moussawi, "Do ETFs increase volatility?", JF 2018; Brown, Davies & Ringgenberg, "ETF arbitrage, non-fundamental demand, and return predictability", Review of Finance 2021; Staer 2017 "Fund flows and underlying returns: the case of ETFs".
- **Horizon / schedule**: 20-60 sessions; month_end or weekly.
- **Data needed**: ETF holdings (have for iShares/SSGA); **missing**: ETF shares outstanding / NAV history to compute flows (iShares daily files include shares outstanding; worth storing as a feature), and ETF ownership per stock (sum of holdings across ETFs). Needs 40 monthly events (4 years: with the Tiingo history for prices, but holdings history only from 2024-10 unless the vendor archives are pulled).
- **Individual fit**: long-only on low-flow-pressure names is possible; the short side is where most of the return is in these papers; capacity fine.
- **Decoys / overlap**: size and momentum (inflows go to recent winners); the rejected "leveraged ETF rebalancing" is intraday and different; the filed 12-1 momentum.
- **Verdict**: **Promising**; feasibility **Needs data** (ETF shares outstanding / flows history).

### etf_constituent_residual_statarb — Avellaneda-Lee PCA / ETF-residual mean reversion
- **Thesis**: regress each stock's daily return on its sector ETF (or 15 PCA factors), fit an Ornstein-Uhlenbeck process to the cumulative residual, trade the s-score (short at +1.25, long at -1.25, exit at ±0.5), hedged with the ETF.
- **Mechanism**: idiosyncratic order flow pushes a stock away from its factor-implied price and reverts within days; the hedge removes market/sector risk; it is systematic liquidity provision.
- **Persistence**: it did *not* persist well: Sharpe fell after 2002 as the strategy became crowded (the August 2007 quant meltdown is the canonical episode); it survives only for players with low costs and fast execution.
- **Rule (source's own)**: Avellaneda & Lee (2010): 60-day window; residual against ETF or PCA factors (eigenportfolios explaining ~55% of variance); OU mean-reversion speed must imply a half-life under ~30 days; thresholds 1.25/0.5 (s-score), 2% leverage per position; daily rebalance; PCA version Sharpe ~1.44 and ETF version ~1.1 over 1997-2007, but about 0.9 after 2002; using "trading time" (volume-adjusted) signals restored some of it (memory, not re-verified; PDF fetched but not text-extractable here).
- **Evidence**: as above; later replications (e.g. Krauss 2017 review; ML extensions by Krauss, Do & Huck 2017 with deep learning on S&P 500: strong pre-2001, then falling to near zero after costs post-2010, memory).
- **Sources**: Avellaneda & Lee, "Statistical arbitrage in the US equities market", Quantitative Finance 2010 (NYU preprint fetched: https://math.nyu.edu/~avellane/AvellanedaLeeStatArb20090616.pdf); Krauss, "Statistical arbitrage pairs trading strategies: review and outlook", J. Econ. Surveys 2017; Krauss, Do & Huck, "Deep neural networks, gradient-boosted trees, random forests: statistical arbitrage on the S&P 500", EJOR 2017.
- **Horizon / schedule**: 3-20 sessions; every_session.
- **Data needed**: daily bars, sector ETF membership (have), `beta_252d`; a residual feature + OU fit (new rollup); daily turnover; shorting of both stocks and ETFs.
- **Individual fit**: poor: daily rebalancing across 50-200 positions, shorts, margin; a long-only "buy s-score < -1.25 in large caps, hedge nothing" is the retail reduction and collapses into `residual_reversal_sector_neutral`.
- **Decoys / overlap**: identical ingredient to `residual_reversal_sector_neutral` at higher frequency; bid-ask bounce.
- **Verdict**: **Decayed** (for an individual); feasibility Ready in principle, **Out of scope** by cost structure. Keep its *residual feature* for the sector-neutral reversal.

### pairs_distance_ggr — Pairs trading, distance method (Gatev-Goetzmann-Rouwenhorst)
- **Thesis**: pick the 20 pairs with the smallest sum of squared differences of normalised prices over 12 months; trade when the spread exceeds 2 historical std devs; close on convergence; 6-month trading window.
- **Mechanism**: the law of one price for close substitutes; convergence is provided by relative-value traders when idiosyncratic flow separates the two.
- **Persistence**: it did not. Profit ~1.2%/month pre-1988, ~0.3%/month 1989-2002, ~0.2%/month 2003-2009 (Do & Faff 2010, memory); unprofitable after costs for the typical pair after 2002 (Do & Faff 2012); remaining profit concentrated in bear markets / high-vol episodes (Fil 2020 1990-2020; Rad-Low-Faff 2016 36 bps/month net over 1962-2014 for distance, verified via Quantpedia).
- **Rule**: as in thesis; equal weight pairs; one-day wait after the signal to avoid bid-ask bounce (GGR's "wait one day" halved returns: a bounce warning).
- **Evidence**: 1962-2002 ~11% annual excess, Sharpe ~1.2 (verified via Quantpedia); post-pub as above; Quantpedia's country-ETF pairs version (Schizas et al.) shows "significantly negative" OOS (verified).
- **Sources**: Gatev, Goetzmann & Rouwenhorst, RFS 2006; Do & Faff, "Does simple pairs trading still work?", FAJ 2010; Do & Faff, "Are pairs trading profits robust to trading costs?", J. Fin. Research 2012; Rad, Low & Faff, "The profitability of pairs trading strategies: distance, cointegration and copula methods", Quant. Finance 2016; Quantpedia https://quantpedia.com/strategies/pairs-trading-with-stocks/ .
- **Horizon / schedule**: 5-60 sessions; every_session with semi-annual formation.
- **Data needed**: 10+ years of bars (Tiingo backfill), a pair table (new grain). Shorting mandatory.
- **Individual fit**: poor: dollar-neutral shorts, long drawdowns when a pair breaks (fundamental divergence), and a few bps a month.
- **Decoys / overlap**: short-term reversal in disguise (Chen, Chen & Li show GGR profits are largely reversal within industry); bid-ask bounce.
- **Verdict**: **Decayed**; feasibility Needs data (history, pair grain). Not worth a filing except as a bear-market overlay study.

### pairs_cointegration_copula — Cointegration and copula pairs
- **Thesis**: pick pairs by Engle-Granger / Johansen cointegration (or model dependence with copulas) instead of distance, trade the spread's z-score.
- **Mechanism / Persistence**: as GGR; the better pair selection was supposed to reduce "false pairs" but in the only large horse race the three methods are similar gross and copula is worst net (Rad-Low-Faff: distance 36, cointegration 33, copula 5 bps/month after costs, 1962-2014; distance numbers verified via Quantpedia, the other two from memory).
- **Rule**: Vidyamurthy (2004) cointegration; Krauss 2017 taxonomy (distance, cointegration, time-series, stochastic control, other); Liew & Wu / Xie et al. copula.
- **Evidence**: as above; all methods decline over time.
- **Sources**: Rad, Low & Faff 2016; Krauss 2017; Vidyamurthy, *Pairs Trading* 2004; Huck & Afawubo 2015 (cointegration beats distance in S&P 500 2000-2011, memory).
- **Horizon / schedule**: 5-60 sessions; every_session.
- **Data needed**: as GGR + cointegration tests (new rollup).
- **Individual fit**: poor (shorts, drawdowns, model risk).
- **Decoys / overlap**: reversal; GGR.
- **Verdict**: **Decayed**; **Out of scope** for the first year.

### share_class_pairs — Dual-class and dual-listed share pairs (GOOG/GOOGL, BRK.A/B, Siamese twins)
- **Thesis**: two share classes with identical cash flows trade at a spread that wanders and reverts; buy the cheap class / short the rich one when the spread is extreme.
- **Mechanism**: segmented demand (index membership, voting premium, retail preference, liquidity), with arbitrage limited by borrow, noise-trader risk and no convergence date.
- **Persistence**: Froot & Dabora (1999) showed Royal Dutch/Shell and Unilever twins deviated 10-30% for years, driven by the location of trade (sentiment and flows), so the spread can keep widening; Schultz & Shive (2010) found US dual-class spreads *do* revert within days and the deviations were profitable gross, mostly from very liquid pairs (memory, not re-verified).
- **Rule**: Schultz-Shive: trade when the class price ratio deviates > X% from its rolling mean, exit on reversion; one-day lag kills part of the profit.
- **Evidence**: positive gross returns in 1993-2006 (memory); narrowed after decimalisation and with GOOG/GOOGL-type arbs crowded; a few dozen US pairs exist (Alphabet, Berkshire, News Corp, Fox, Zillow, Under Armour, Liberty entities...).
- **Sources**: Froot & Dabora, "How are stock prices affected by the location of trade?", JFE 1999; Schultz & Shive, "Mispricing of dual-class shares: profit opportunities, arbitrage, and trading", JFE 2010; De Jong, Rosenthal & van Dijk, "The risk and return of arbitrage in dual-listed companies", RoF 2009.
- **Horizon / schedule**: 1-20 sessions; every_session.
- **Data needed**: a curated list of class pairs (reference data; `parent_id` in instruments can carry it), daily closes (have). Shorting needed on one leg; borrow on the illiquid class can be scarce.
- **Individual fit**: capacity tiny (a handful of liquid pairs), returns a few bps; options on GOOG vs GOOGL could express it but slippage eats it.
- **Decoys / overlap**: bid-ask bounce (A-class is often illiquid), ex-dividend / buyback timing differences, index-inclusion events (GOOGL in S&P, GOOG added later).
- **Verdict**: **Weak**; feasibility **Ready** data-wise, likely fails the cost test; low priority.

### lead_lag_large_to_small — Large caps lead small caps / sector leaders lead followers
- **Thesis**: last week's return of large caps (or the sector's biggest names) predicts this week's return of small caps in the same sector.
- **Mechanism**: slow information diffusion (Lo & MacKinlay 1990; Hou 2007): fewer analysts and less attention on small names.
- **Persistence**: it has shrunk with faster markets; Chordia-Sarkar-Subrahmanyam and later work find cross-autocorrelations much lower after 2000 (memory).
- **Rule**: Hou (2007): weekly; within each industry, the big-firm portfolio return this week predicts small-firm portfolio returns next week; long small firms in industries whose big firms rose, short the rest.
- **Evidence**: 1963-2001 significant at weekly horizon (memory); post-2000 much weaker (direction verified by memory).
- **Sources**: Lo & MacKinlay, "When are contrarian profits due to stock market overreaction?", RFS 1990; Hou, "Industry information diffusion and the lead-lag effect in stock returns", RFS 2007; Cohen & Frazzini 2008 (customer-supplier links: a different, stronger lead-lag that belongs to a fundamentals family).
- **Horizon / schedule**: 5 sessions; weekly.
- **Data needed**: sector membership and size (have), weekly returns (have); nothing missing except history.
- **Individual fit**: long-only small-cap leg is possible; costs high in small caps.
- **Decoys / overlap**: industry momentum (Moskowitz-Grinblatt), non-synchronous trading in illiquid names (a statistical artefact).
- **Verdict**: **Decayed**; feasibility Ready; file only if the economic-links variant is researched elsewhere.

### etf_to_holdings_lead_lag — ETF price leads its constituents (end of day)
- **Thesis**: a sector/thematic ETF's close-to-close move that is not matched by its holdings' aggregate move predicts the holdings' next-day move (ETF as price discovery venue).
- **Mechanism**: ETFs are the venue where macro/sector news is traded first; constituents, especially illiquid ones, catch up (Hasbrouck 2003 on index products; Glosten-Nallareddy-Zou 2021 on ETF trading and information efficiency).
- **Persistence**: small and mostly intraday; EOD remnants are in illiquid holdings only.
- **Rule**: compute ETF return minus holdings-weighted return (needs holdings weights, have); long holdings when the gap is positive; hold 1-5 sessions.
- **Evidence**: price-discovery share of ETFs is documented; a tradable EOD lead-lag in US large caps is not established (not verified).
- **Sources**: Glosten, Nallareddy & Zou, "ETF activity and informational efficiency of underlying securities", Mgmt Science 2021; Hasbrouck, "Intraday price formation in US equity index markets", JF 2003; Israeli, Lee & Sridharan 2017 ("Is there a dark side to ETFs?").
- **Horizon / schedule**: 1-5 sessions; every_session.
- **Data needed**: ETF holdings weights (have) and closes (have); straightforward feature.
- **Individual fit**: long-only on laggards is possible; costs in illiquid names.
- **Decoys / overlap**: stale prices / non-synchronous closes in thinly traded holdings (would create a spurious lead-lag); overlaps `etf_flow_reversal_constituents` (opposite sign over longer horizons).
- **Verdict**: **Weak**; feasibility **Ready**; a cheap test once holdings-weighted returns exist.

### volatility_contraction_expansion — NR7 / Bollinger squeeze / tight range then breakout
- **Thesis**: after an unusually narrow range (NR7, lowest Bollinger width in a year, N inside days), the next move is large; trade the breakout direction.
- **Mechanism**: volatility clustering means contraction is followed by expansion (a GARCH fact); the *direction* is not predictable from the squeeze alone. The tradable part is for options (buy cheap gamma) or as an *entry filter* on a directional edge (momentum names in a tight base break out more cleanly: the O'Neil / Minervini "VCP").
- **Persistence**: vol clustering is permanent; direction never had an edge.
- **Rule (source's own)**: Crabel (1990) NR7 = today's range smallest of the last 7, trade the next day's breakout of the day's range (intraday); Bollinger "squeeze" = `bb_width` at a 6-month low, trade the first close outside the band; Minervini VCP = successive contractions of pullback depth then a pivot buy.
- **Evidence**: academic direct tests are scarce; Bollinger-band breakout rules are among those killed by data-snooping tests (Bajgrowicz-Scaillet covered channel breakouts; Lento 2007 found BB underperform); options evidence that low `bb_width_pctile_252d` plus low IV rank is a cheap-straddle condition is practitioner-level (Sinclair).
- **Sources**: Crabel, *Day Trading with Short Term Price Patterns and Opening Range Breakout* (1990); Bollinger, *Bollinger on Bollinger Bands* (2001); Lento, "Tests of technical trading rules in the Asian-Pacific equity markets", 2007; Bajgrowicz & Scaillet, JFE 2012; Sinclair, *Volatility Trading* (2013).
- **Horizon / schedule**: 5-20 sessions; every_session.
- **Data needed**: `bb_squeeze`, `bb_width_pctile_252d`, `tight_range_sessions`, `range_20d_pct`, `atr_ratio_5_20`, `inside_day_breakout`, `hv_ratio_10_60`, `iv_rank`, `vrp_iv30`: all stored (NR7 is a trivial expression).
- **Individual fit**: as a filter: free; as a long-straddle trigger: feasible via our chains.
- **Decoys / overlap**: the filed VRP (short vol) is the mirror; filing it as "long gamma when realised and implied are both compressed" belongs to the options family.
- **Verdict**: **Weak** as a directional edge, **Promising as an options/entry filter**; feasibility **Ready**. Hand the options version to the options family.

### donchian_turtle_breakout_stocks — 20/55-day channel breakouts with ATR stops on stocks
- **Thesis**: buy a 55-day (Turtle) or 20-day high, exit on a 10/20-day low or 2-ATR stop; the few big trends pay for many small losses.
- **Mechanism**: as 52-week high / trend following (under-reaction, anchoring); on single stocks the signal-to-noise is poorer than on futures.
- **Persistence**: trend following on stocks is documented (Wilcox-Crittenden above) but the 20/55-day versions have shorter horizons and more whipsaws; Clenow (*Stocks on the Move*) argues single-stock breakouts work only with a market-regime filter and ranking.
- **Rule**: Turtle rules (Faith 2007): entry 20-day high (skip if last trade was a winner) or 55-day high; stop 2N; exit 10-day low (System 1) / 20-day low (System 2); position size by N (ATR).
- **Evidence**: on futures, robust; on US stocks, practitioner tests (Clenow 2015; Zarattini-Pagani-Wilcox 2024 for the all-time-high version) show positive gross with heavy turnover; academic channel-breakout rules on DJIA fail OOS (STW 1999; Bajgrowicz-Scaillet 2012).
- **Sources**: Faith, *Way of the Turtle* 2007; Clenow, *Stocks on the Move* 2015; Sullivan, Timmermann & White, JF 1999; Bajgrowicz & Scaillet 2012.
- **Horizon / schedule**: 20-120 sessions; every_session.
- **Data needed**: `breakout_20d/50d`, `high_20d/50d/100d/200d`, `atr_14/20`, `sessions_since_breakout`, `breakout_failed`, `failed_breakouts_252d`: stored; 55-day is a one-line addition.
- **Individual fit**: long-only; many small losses; needs 20-40 positions.
- **Decoys / overlap**: momentum (filed); it is `breakout_52w_high_trend_following` at a shorter lookback.
- **Verdict**: **Weak** (shorter lookbacks lose to the 52w/all-time-high version); feasibility **Ready**. Test as a *parameter* of the 52w-high filing, not separately.

### gap_fill_vs_gap_and_go — Overnight gaps: fill or continue
- **Thesis**: small gaps (< 1-2%) in large caps without news fill the same or next day; large gaps with news and volume continue (gap-and-go).
- **Mechanism**: small gaps are overnight order imbalance (liquidity); large gaps are information (PEAD-type under-reaction). The split is the same as `large_move_news_vs_no_news`, measured at the open.
- **Persistence**: the fill part is tiny and intraday-dominated; the go part is PEAD.
- **Rule**: practitioner (Connors "gap" studies; Fosback): fade gaps < 1% against the prior trend in index ETFs, buy gaps > 4% with volume > 2x in uptrends. No peer-reviewed rule with numbers that survives costs for EOD traders (not verified).
- **Evidence**: practitioner backtests only; the academic literature (overnight vs intraday returns: Lou, Polk & Skouras 2019 "A tug of war: overnight versus intraday expected returns") says overnight returns carry the risk premium and intraday reverses it, which is about *when* returns accrue, not about individual gaps. Intraday entry (fade at the open) is out of scope for us.
- **Sources**: Lou, Polk & Skouras, JFE 2019; Connors Research gap studies (practitioner); Pritamani & Singal 2001 (large gaps with news).
- **Horizon / schedule**: 1-5 sessions; on_event:gap.
- **Data needed**: `gap_open_pct`, `gap_above/below` (+dates/distances), `rel_volume`, 8-K; stored; a "gap filled by session k" outcome would be a new outcome grain.
- **Individual fit**: fade entries need the open (we act at the next close at best), which kills the fill trade; the go trade is `episodic_pivot`.
- **Decoys / overlap**: `episodic_pivot_gap_volume`, filed PEAD, overnight premium.
- **Verdict**: **Weak** (fill) / covered elsewhere (go); feasibility **Out of scope** for the fill leg (intraday).

### opening_range_breakout — ORB (noted; intraday)
- **Thesis**: buy the break of the first 5-30 minutes' range with a stop at the other side; Zarattini & Aziz (2023) report large leveraged returns on QQQ and (2024) on "stocks in play" (large relative volume at the open).
- **Mechanism**: early-session order flow after overnight news sets the day's direction; stops are tight, winners trail.
- **Persistence**: intraday capacity limited; requires 1-minute bars and live execution.
- **Rule / Evidence**: Zarattini & Aziz, "Can day trading really be profitable?" (2023, SSRN) and "A profitable day trading strategy for the US equity market" (2024, SSRN): 5-minute ORB with ATR stops, leverage, 2016-2023; very high reported Sharpe; independent replications dispute the realism of fills and costs (not verified).
- **Sources**: Zarattini & Aziz 2023, 2024 (SSRN; not fetched, 403); Crabel 1990.
- **Data needed**: intraday bars (NOT stored).
- **Verdict**: **Out of scope** (intraday). Its EOD relative: the `rel_volume` + gap filter of `episodic_pivot`.

### candlestick_patterns — Single- and multi-bar candlesticks (hammer, engulfing, doji, stars)
- **Thesis**: reversal candles at the end of a move predict the next 1-10 days.
- **Mechanism**: claimed: exhaustion of one side visible in the bar's shape. In practice a candle encodes the same information as the close location and the day's return, which the short-term reversal literature already covers.
- **Persistence**: n/a: the rules do not work on US stocks.
- **Rule (source's own)**: Marshall, Young & Rose (2006): 28 bullish/bearish single and multi-bar patterns on the 35 DJIA stocks 1992-2002 (daily data, 10-day holding, trend defined by a 10-day MA), bootstrap (GARCH-M, AR) null: no pattern is profitable; Marshall-Young-Cahan (2008) repeat on Japan with the same result; Horton (2009) "Stars, crows and doji" on US stocks: no value; Caginalp & Laurent (1998) found 8 reversal patterns predictive on S&P 500 stocks 1992-1996 (~+1% over 2 days, memory) but it did not replicate on later data; Lu, Shiu & Liu (2012) found some patterns work in Taiwan.
- **Evidence**: negative in the two cleanest US studies; isolated positive results in Asian markets or short early samples.
- **Sources**: Marshall, Young & Rose, "Candlestick technical trading strategies: can they create value for investors?", JBF 2006; Marshall, Young & Cahan, "Are candlestick technical trading strategies profitable in the Japanese equity market?", RQFA 2008; Caginalp & Laurent, "The predictive power of price patterns", Applied Math. Finance 1998; Horton, "Stars, crows, and doji: the use of candlesticks in stock selection", QRFA 2009.
- **Horizon / schedule**: 1-10 sessions; every_session.
- **Data needed**: `candle`, `body_share`, wick shares, `bar_relation`, `prev_bar_relation`: stored.
- **Individual fit**: n/a.
- **Decoys / overlap**: anything a candle "finds" is `close_range_pos` + `ret_1d` + `rel_volume` (the IBS and reversal edges).
- **Verdict**: **Dead** as an edge; our `candle` feature stays a *description* for the Guide, not a signal.

### chart_patterns_hs_cup_handle — Head & shoulders, double tops/bottoms, cup-and-handle, flags
- **Thesis**: completed geometric patterns predict direction and magnitude (the "measured move").
- **Mechanism**: claimed self-fulfilling coordination of chartists at the neckline / pivot.
- **Persistence**: unestablished.
- **Rule (source's own)**: Lo, Mamaysky & Wang (2000): kernel-regression smoothing, 10 patterns on US stocks 1962-1996; conditional return distributions differ from unconditional for several patterns ("may have some practical value"; abstract verified via NBER), but they do not show trading profits. Osler (1998): head-and-shoulders on US stocks is not profitable (noise-trader behaviour); Chang & Osler (1999): H&S in FX profitable for DM and yen, not others; Savin, Weller & Zvingelis (2007): H&S on US stocks 1990-1999 has predictive power for 1-3 month returns, modest (memory, not re-verified); Bulkowski's *Encyclopedia of Chart Patterns* reports success rates without any snooping control. Cup-and-handle (O'Neil) has no peer-reviewed test.
- **Evidence**: "informative but not shown profitable"; a handful of studies, mixed, with the strongest positive in FX.
- **Sources**: Lo, Mamaysky & Wang, "Foundations of technical analysis", JF 2000 (NBER w7613 fetched); Osler, "Identifying noise traders: the head-and-shoulders pattern in US equities", FRBNY 1998; Chang & Osler, "Methodical madness", Economic Journal 1999; Savin, Weller & Zvingelis, Journal of Financial Econometrics 2007; Bulkowski 2005.
- **Horizon / schedule**: 20-60 sessions; on_event:pattern_complete.
- **Data needed**: a pattern detector (kernel smoothing of closes, then the LMW geometric rules) is a new rollup; `swing_high/low`, `pivot_structure`, `support/resistance_touches` give the swing points.
- **Individual fit**: long-only on bottoms; event counts fine.
- **Decoys / overlap**: a completed bottom pattern is a 20-50 day breakout from a base, i.e. `breakout_*` + `tight_range_sessions`; test the increment over the breakout features before building a detector.
- **Verdict**: **Weak**; feasibility **Needs data** (detector). Low priority; the breakout + base + volume features already approximate "cup-and-handle".

### support_resistance_round_numbers — Swing levels, pivot touches and round-number levels
- **Thesis**: prices stall and reverse at prior swing levels and at round numbers ($50, $100), and break-outs through them with volume continue.
- **Mechanism**: limit orders cluster at salient prices (Osler 2003 showed stop-loss and take-profit order clustering at round numbers in FX); retail buy/sell imbalance at round numbers (Bhattacharya, Holden & Jacobsen 2012: excess buying just above and selling just below round numbers, with short-term return predictability of a few bps).
- **Persistence**: salience is behavioural; the effect per event is small; it is useful for *where* to place stops and limits rather than as a directional edge.
- **Rule (source's own)**: Osler (2000, FRBNY): S/R levels published by six FX dealers predicted intraday trend interruptions better than chance; Bhattacharya-Holden-Jacobsen (2012, Mgmt Sci): 24-hour returns differ by a few bps depending on the position relative to round numbers (memory for magnitude). For stocks EOD, no published rule with numbers.
- **Evidence**: intraday effects documented; EOD tradable edge not established.
- **Sources**: Osler, "Support for resistance: technical analysis and intraday exchange rates", FRBNY Econ Policy Review 2000; Osler, "Currency orders and exchange rate dynamics", JF 2003; Bhattacharya, Holden & Jacobsen, "Penny wise, dollar foolish: buy-sell imbalances on and around round numbers", Mgmt Science 2012.
- **Horizon / schedule**: 1-10 sessions; every_session.
- **Data needed**: `dist_to_support/resistance`, `*_touches`, `*_age`, `pivot_structure`, `retest_state`, `swing_*`, volume profile (`poc_252d`, `value_area_*`, `hvn/lvn`): stored; round-number distance is a one-line expression.
- **Individual fit**: cost-free as a stop/limit placement rule.
- **Decoys / overlap**: `pivot_strength` and `retest` already exist; the only test worth running is "breakout retest held" (`breakout_retest_held`) as an increment to the breakout filing.
- **Verdict**: **Weak** as an edge; **Ready** as a risk-placement convention.

### ma_crossover_single_stocks — Golden/death cross and MA(50/200) timing on single stocks and indices
- **Thesis**: buy when the 50-day crosses above the 200-day (or price above the 200-day), sell on the reverse.
- **Mechanism**: trend following / under-reaction; on indices it mostly cuts drawdowns (a vol-timing effect), not returns.
- **Persistence**: as an index risk-control overlay it keeps "working" in the sense of lowering drawdown; as an alpha source it fails out of sample.
- **Rule (source's own)**: Brock, Lakonishok & LeBaron (1992): 26 MA and trading-range-break rules on the DJIA 1897-1986, profitable vs bootstrap nulls. Sullivan, Timmermann & White (1999): reality check over 7,846 rules: the best in-sample rule survives in-sample snooping but shows **no** out-of-sample value in 1987-1996 (and none on S&P futures). Bajgrowicz & Scaillet (2012): false-discovery-rate control on the same universe 1897-2011: the rules that look good in one period do not persist, and after costs an investor could not have earned a profit by picking them in real time. Zakamulin (2014): MA and TSMOM timing rules on indices have far worse real-life (OOS) performance than in-sample; Hsu, Hsu & Kuan (2010): rules show predictive power in young markets/ETFs, not in S&P 500.
- **Evidence**: dead as alpha on US indices and single stocks; the surviving relatives are the *cross-sectional* uses (Han-Yang-Zhou 2013: MA timing on volatility-sorted portfolios; Han-Zhou-Zhu 2016 trend factor) and the risk-control use (Faber 2007; Moskowitz-Ooi-Pedersen TSMOM, another family).
- **Sources**: Brock, Lakonishok & LeBaron, JF 1992; Sullivan, Timmermann & White, "Data-snooping, technical trading rule performance, and the bootstrap", JF 1999; Bajgrowicz & Scaillet, "Technical trading revisited: false discoveries, persistence tests, and transaction costs", JFE 2012; Zakamulin, "The real-life performance of market timing with moving average and time-series momentum rules", J. Asset Management 2014; Hsu, Hsu & Kuan, J. Empirical Finance 2010.
- **Horizon / schedule**: 20-250 sessions; every_session.
- **Data needed**: all stored (`sma_50`, `sma_200`, `ema_stack`, `spx_death_cross`, `spx_trend_200d`).
- **Individual fit**: as a *regime filter* on other edges (we already compute `trend_state`, `spx_trend_200d`, `regime`): free.
- **Decoys / overlap**: our regime label already carries this; do not file as an edge.
- **Verdict**: **Dead** as alpha; Ready as a regime filter (already built).

### adx_trend_filter — ADX / DMI as a trend-strength filter
- **Thesis**: take breakouts only when ADX(14) > 20-25 and rising; fade only when ADX < 20.
- **Mechanism**: ADX is a smoothed measure of directional range share, i.e. a trend-vs-chop classifier; no mechanism of its own.
- **Persistence**: n/a.
- **Rule**: Wilder (1978); practitioner thresholds 20/25/40.
- **Evidence**: no peer-reviewed test on US stocks with snooping control (not verified); it is highly collinear with `trend_r2_90d` and `clenow_momentum_90d` (regression R² is the academic analogue of "trend strength").
- **Sources**: Wilder, *New Concepts in Technical Trading Systems* 1978; Clenow 2015 (uses regression slope × R² instead).
- **Data needed**: ADX not stored; `trend_r2_90d`, `reg_slope_90d_ann`, `clenow_momentum_90d`, `band_walk` substitute.
- **Verdict**: **Weak**; use the stored regression trend stats instead; add ADX only if a filing explicitly needs the Wilder definition for faithful replication.

### volume_price_confirmation_obv_cmf — OBV / accumulation-distribution / CMF confirmation
- **Thesis**: a breakout or uptrend "confirmed" by rising OBV or positive Chaikin Money Flow continues; divergence (price up, OBV down) precedes reversal.
- **Mechanism**: signed volume proxies net buying pressure (Lee-Ready-style imbalance at daily grain); the academic version is order-imbalance predictability (Chordia & Subrahmanyam 2004: daily imbalance predicts next-day returns, mostly reversal of the *price* component) and the volume-momentum interaction (Lee & Swaminathan 2000: high-volume winners' momentum reverses faster; low-volume winners persist).
- **Persistence**: imbalance predictability is short-lived and small; the Lee-Swaminathan "momentum life cycle" effect is a published cross-sectional anomaly with some persistence (not verified recently).
- **Rule (source's own)**: Lee & Swaminathan (2000): sort on past 6-month return and past 3-month turnover; low-volume winners / high-volume losers earn higher subsequent momentum profits; Chordia-Subrahmanyam (2004): daily order imbalance.
- **Evidence**: Lee-Swaminathan robust in the 1965-1995 sample; replications (OSAP includes "VolMkt", "ShareVol" variants) show weaker but present effects (not verified exactly); OBV/CMF as such: no academic support.
- **Sources**: Lee & Swaminathan, "Price momentum and trading volume", JF 2000; Chordia & Subrahmanyam, "Order imbalance and individual stock returns", JFE 2004; Granville (OBV) 1963; Chaikin (CMF).
- **Horizon / schedule**: 20-120 sessions; month_end.
- **Data needed**: `cmf_20d`, `up_volume_share_20d`, `turnover_20d`, `volume_trend_20_60`, `mom_12_1`: stored; OBV is an easy cumulative feature.
- **Individual fit**: low-volume-winner momentum is long-only friendly.
- **Decoys / overlap**: it is momentum conditioned on turnover: file as a variant of 12-1 ("low-turnover winners").
- **Verdict**: **Weak** stand-alone / **Promising as a momentum variant** (Lee-Swaminathan); feasibility **Ready**.

### ibd_relative_strength_ranking — IBD-style RS rank (12-month, last quarter double-weighted)
- **Thesis**: stocks in the top 10-20% of 12-month relative strength (weighting the last 3 months double) keep outperforming over 3-12 months.
- **Mechanism**: momentum.
- **Persistence**: as momentum.
- **Rule (source's own)**: IBD RS Rating ≈ 0.4 × ret_3m + 0.2 × ret_6m + 0.2 × ret_9m + 0.2 × ret_12m, percentile-ranked 1-99; CAN SLIM requires RS >= 80. Academic analogue: 12-1 momentum (filed) and the 52w-high ratio.
- **Evidence**: Jegadeesh-Titman momentum; the AAII CAN SLIM screen reported strong hypothetical returns 1998-2010s without costs (memory); no peer-reviewed test of the exact weighting; the double-weighted recent quarter makes it closer to 6-1 momentum, which has somewhat higher turnover and similar returns.
- **Sources**: O'Neil, *How to Make Money in Stocks*; Jegadeesh & Titman 1993; AAII screens (practitioner).
- **Horizon / schedule**: 60-120 sessions; month_end.
- **Data needed**: `ret_60d`, `ret_120d`, `ret_252d`, `rs_spy_63d/252d`, `mom_pctile_252d`: stored; the weighted rank is a one-line expression.
- **Individual fit**: long-only, low turnover.
- **Decoys / overlap**: filed 12-1 momentum. **Covered.**
- **Verdict**: **Covered by filed momentum** (variant only); Ready.

### minervini_trend_template — Minervini Trend Template / Stage-2 screen
- **Thesis**: a stock satisfying all of (price > 150 & 200-day MA; 150 > 200; 200-day rising >= 1 month; 50 > 150 > 200; price >= 30% above 52w low; within 25% of 52w high; RS rank >= 70) is in "stage 2" and should be bought on a volatility-contraction pivot.
- **Mechanism**: it is a momentum + trend-quality + proximity-to-high composite (Weinstein stage analysis); the ingredients are George-Hwang, momentum and MA alignment.
- **Persistence**: as momentum.
- **Rule**: as thesis (Minervini 2013, *Trade Like a Stock Market Wizard*).
- **Evidence**: no peer-reviewed test; practitioner backtests (e.g. by Quantpedia-type blogs) show returns in line with momentum and 52w-high portfolios with higher drawdowns in 2022 (not verified). Minervini's own audited US Investing Championship results are discretionary and not a test of the template.
- **Sources**: Minervini 2013; Weinstein, *Secrets for Profiting in Bull and Bear Markets* 1988; George & Hwang 2004.
- **Horizon / schedule**: 60-250 sessions; every_session screen, monthly rebalance.
- **Data needed**: `sma_50/150/200`, `pct_vs_sma_150/200`, `sma200_slope_20d`, `ema_stack`, `pct_from_low_52w`, `pct_from_high_52w`, `rs_spy_252d`, `mom_pctile_252d`, `tight_range_sessions`: all stored; the template is a TOML expression screen already.
- **Individual fit**: long-only, exactly how it is used.
- **Decoys / overlap**: filed 12-1 momentum + `nearness_52w_high_cross_section`; file as *the retail-practitioner implementation* of momentum and measure the increment of the quality filters (MA alignment, 52w-low distance) over plain 12-1.
- **Verdict**: **Covered by filed momentum** (test the filter increment); Ready.

### anchored_vwap_reversion_retest — Anchored VWAP from earnings / swing points as a level
- **Thesis**: price returning to the VWAP anchored at the last earnings gap (or major swing low) finds buyers (holders' average cost); a loss of that VWAP flips the regime.
- **Mechanism**: average-cost anchoring and disposition effect: holders' aggregate cost basis acts as a reference point (Grinblatt & Han 2005 "capital gains overhang": stocks trading above holders' aggregate cost have higher subsequent returns because of under-reaction induced by disposition selling).
- **Persistence**: the disposition effect is one of the most persistent behavioural regularities; Grinblatt-Han's CGO predictor subsumes part of momentum.
- **Rule (source's own)**: Grinblatt & Han (2005): capital-gains overhang = (P - reference price) / P where the reference price is a turnover-weighted average of past prices (an anchored VWAP across the cross-section!); monthly long high-CGO / short low-CGO; ~1%/month in 1963-1996 and it explains momentum (memory). Practitioner (Brian Shannon) anchored VWAP from earnings or IPO.
- **Evidence**: CGO is a replicated anomaly (OSAP includes it; An 2016 extends with unrealised gains/losses asymmetry); post-publication strength: reduced, still present (not verified exactly).
- **Sources**: Grinblatt & Han, "Prospect theory, mental accounting, and momentum", JFE 2005; An, "Asset pricing when traders sell extreme winners and losers", RFS 2016; Shannon, *Maximum Trading Gains with Anchored VWAP* 2023.
- **Horizon / schedule**: 20-60 sessions; month_end or every_session.
- **Data needed**: `avwap_earnings`, `avwap_swing_high/low`, `turnover_20d`: stored; a turnover-weighted reference price over 1-5 years (CGO proper) is a new window feature once history exists.
- **Individual fit**: long-only ("buy above cost basis" is the CGO long leg).
- **Decoys / overlap**: momentum (CGO explains much of it); `nearness_52w_high`. File the *CGO* form (academic) with anchored VWAP as its practitioner expression.
- **Verdict**: **Promising** (as CGO); feasibility **Needs data** (multi-year turnover history) — the earnings-anchored VWAP version is Ready as a weaker proxy.

### overbought_shorts — Shorting stretched / overbought names
- **Thesis**: short stocks that are >3 ATR above the 20-day or RSI(2) > 95 / RSI(14) > 80 expecting a snap-back.
- **Mechanism**: short-term reversal of winners.
- **Persistence**: weak: the winner leg of short-term reversal is the less profitable half (momentum fights it), borrow costs and squeezes are real, and the big winners are often news-driven (continuation).
- **Rule**: Connors' short versions (RSI(2) > 95 below the 200-day MA); the residual-reversal short leg.
- **Evidence**: the short leg of STR contributes less than the long leg in most studies; in the enhanced residual version both legs matter but only in large caps (Blitz et al.).
- **Sources**: as `residual_reversal_sector_neutral`; Connors & Alvarez 2009.
- **Data needed**: stored (`stretch_sma20_atr`, `price_z_20d`, `rsi_14`, `band_walk`).
- **Individual fit**: shorting single stocks is costly and unlimited-risk; an options version (bear call spreads on stretched names with high IV rank) is the retail form and overlaps the filed VRP.
- **Decoys / overlap**: momentum continuation; filed VRP.
- **Verdict**: **Weak**; feasibility Ready; only as the short leg of the residual-reversal filing or as a VRP overlay.

### bollinger_keltner_reversion — Band reversion (close below lower band, re-entry) and %b extremes
- **Thesis**: a close below the lower Bollinger band (or `bb_pct_b` < 0) in a non-trending market reverts to the middle band.
- **Mechanism**: a z-score of price vs its 20-day mean, i.e. short-term reversal with a vol normaliser.
- **Persistence**: as STR/IBS: shrinking.
- **Rule**: Bollinger (2001): buy %b < 0 with `band_walk` absent and confirm with volume; Leung & Chong (2003) compared MA envelopes vs BB (BB not better); Lento, Gradojevic & Wright (2007): BB contrarian rules beat buy-and-hold in some markets, not US indices (memory).
- **Evidence**: no snooping-robust evidence; redundant with `price_z_20d`.
- **Sources**: Bollinger 2001; Leung & Chong, Applied Economics Letters 2003; Lento, Gradojevic & Wright, Applied Financial Economics Letters 2007.
- **Data needed**: stored (bands group).
- **Verdict**: **Weak**; redundant with RSI(2)/IBS/`price_z_20d`; do not file separately.

### industry_relative_mean_reversion_monthly — Intra-industry reversal and inter-industry momentum (Hameed & Mian)
- **Thesis**: within an industry, last month's relative losers beat relative winners next month (strong reversal); across industries, last month's winning industries continue (momentum); do both.
- **Mechanism**: industry returns carry information (slow diffusion -> industry momentum); the deviation of a firm from its industry is largely noise -> reversal (same logic as residual reversal, at the monthly grain).
- **Persistence**: the intra-industry reversal is stronger in illiquid names and periods of high volatility (liquidity provision premium); the industry-momentum leg is Moskowitz-Grinblatt.
- **Rule (source's own)**: Hameed & Mian (2015): monthly; industry-adjusted return = stock return minus its industry's return; decile L/S on last month's industry-adjusted return, hold one month; the industry-adjusted reversal is roughly double the raw reversal and is not explained by bid-ask bounce (memory for magnitude).
- **Evidence**: 1963-2010-ish; survives costs in large caps; weaker since 2000 like all reversal (not verified exactly).
- **Sources**: Hameed & Mian, JFQA 2015; Moskowitz & Grinblatt, "Do industries explain momentum?", JF 1999; Da, Liu & Schaumburg, "A closer look at the short-term return reversal", Mgmt Science 2014 (decomposes reversal into cash-flow news vs discount-rate; the non-news part reverses).
- **Horizon / schedule**: 20 sessions; month_end.
- **Data needed**: industry classification finer than sector (ETF holdings of sector SPDRs and industry ETFs can give it; SIC from SEC filings is stored as part of company reference? check `is_financial` hints a classification exists); `ret_20d`, `sector_ret_63d` (a 20d version is trivial).
- **Individual fit**: long-only intra-industry losers in large caps, monthly: fine.
- **Decoys / overlap**: it is the monthly version of `residual_reversal_sector_neutral`; file them together as one edge with two horizons.
- **Verdict**: **Promising**; feasibility **Ready** once industry-adjusted returns exist.

### low_volume_pullback_pocket_pivot — O'Neil / Morales-Kacher pocket pivot and volume dry-up
- **Thesis**: in a base, a day whose up-volume exceeds the largest down-volume of the prior 10 days (pocket pivot), after a volume dry-up, marks institutional accumulation; buy it.
- **Mechanism**: footprint of patient institutional buying (Lee-Swaminathan "low-volume winners"); the dry-up marks seller exhaustion.
- **Persistence**: practitioner lore; no published test.
- **Rule**: Morales & Kacher, *Trade Like an O'Neil Disciple* (2010).
- **Evidence**: none peer-reviewed; the stored `pocket_pivot` and `volume_dry_up` features let us test it cheaply as an increment to `breakout_*`.
- **Sources**: Morales & Kacher 2010; Lee & Swaminathan 2000.
- **Data needed**: stored.
- **Verdict**: **Weak**; Ready; test as an entry filter inside the breakout / momentum filing.

### short_term_reversal_classic — Baseline: raw 1-week / 1-month reversal (Jegadeesh 1990, Lehmann 1990)
- **Thesis**: last month's losers beat last month's winners next month.
- **Mechanism**: liquidity provision + bid-ask bounce.
- **Persistence**: did not: the raw effect has weakened steadily and "vanished in most regions" (Blitz et al. 2020, via Quantpedia); it is swamped by costs outside large caps (de Groot et al.).
- **Rule**: monthly decile L/S on last month's return (skip no month); weekly version Lehmann.
- **Evidence**: ~1-2%/month in 1934-1987 samples (memory); near zero net after 2000.
- **Sources**: Jegadeesh, "Evidence of predictable behavior of security returns", JF 1990; Lehmann, "Fads, martingales, and market efficiency", QJE 1990; Avramov, Chordia & Goyal 2006 (reversal concentrated in illiquid stocks after turnover shocks).
- **Verdict**: **Decayed**; listed only as the control for the residual version.

### long_term_reversal_debondt_thaler — 3-5 year losers (noted)
- **Thesis**: 3-5 year losers outperform winners over the next 3-5 years (De Bondt & Thaler 1985).
- **Evidence**: largely subsumed by value / size and January effects; OSAP shows weak post-publication returns (not verified); needs 10+ years of history and belongs to the value family.
- **Verdict**: **Weak**; Out of scope here (value family).

### correlation_breakdown_cross_asset_pairs — Sector ETF vs commodity / rate pairs (XLE-USO, XLU-TLT, KRE-yields)
- **Thesis**: when a sector ETF decouples from the macro series it normally tracks (energy stocks vs oil, utilities vs long bonds, regional banks vs the curve), it reconverges.
- **Mechanism**: cross-asset relative value; equity sectors lag their macro driver's price (slow diffusion) or over-react to flows.
- **Persistence**: unclear; these relationships break structurally (energy vs oil decoupled 2021-24 by capital discipline).
- **Evidence**: no clean published test (not verified); our `market_cross_asset` rollups (`cper_vs_gld`, `xlu_vs_spy`, `hyg_vs_lqd` ...) give the series.
- **Verdict**: **Weak**; Needs data (futures or commodity ETF history) — hand to the macro family.

---

## Which technical rules survive data-snooping tests (the meta-evidence)

- **Sullivan, Timmermann & White (1999, JF)**: 7,846 rules (filters, MAs, support/resistance, channel breakouts, OBV) on DJIA 1897-1996: the best rule survives in-sample snooping adjustment, but out of sample (1987-1996) and on S&P futures there is nothing.
- **Bajgrowicz & Scaillet (2012, JFE)**: same universe through 2011 with false-discovery-rate control and persistence tests: no persistence; an investor picking rules in real time would not have beaten costs. Rules "work" in short sub-periods then stop.
- **Hsu, Hsu & Kuan (2010, J. Empirical Finance)**: stepwise SPA over 16,000 rules on ETFs: predictive power in young / emerging-market ETFs, none in S&P 500 / DJIA.
- **Marshall, Young & Rose (2006)**: candlesticks: no.
- **Lo, Mamaysky & Wang (2000)**: chart patterns carry some information but no profitability claim (verified abstract).
- **What survives**: (1) *cross-sectional* technical signals with an economic story: short-term residual/industry reversal in large caps, the 52w-high / trend factor (momentum), the high-volume premium, CGO; (2) *conditioning* on information (news vs no-news, earnings dates); (3) *risk control* uses of MAs (drawdown, not alpha). What does not: time-series rules on a single series (MA crossovers, channel breakouts, bands, candles, chart patterns) once snooping and costs are counted.
- **Decay rule of thumb (McLean & Pontiff 2016, JF)**: anomaly returns are ~26% lower out of sample and ~58% lower post-publication; price-based, low-cost anomalies decay most. Expect half of the published number at best, and plan the 40-event test on post-2015 data.

## What the stored features already cover (summary for the orchestrator)

Covered as signals or primitives today: IBS (`close_range_pos`), Bollinger/Keltner (`bands@v2`), 52-week-high nearness and 20/50-day breakouts with retest/failure tracking (`price_stats`, `momentum`, `swing_levels`, `retest`), volatility contraction (`bb_squeeze`, `tight_range_sessions`, `atr_ratio_5_20`), gaps (`gaps@v1`), candlesticks (`candle@v1`: Guide material, not a signal), support/resistance strength (`pivot_strength`, `volume_profile`), MA alignment / trend quality (`trend_stats@v2`), volume confirmation (`volume@v1`: `cmf_20d`, `pocket_pivot`, `volume_dry_up`, `volume_climax`, `volume_z_20d`), relative strength incl. sector rank and RS-line highs (`relative_strength@v1`), anchored VWAPs, pullback/stretch (`price.toml`), beta and correlation to SPY (`vol_stats`).

Missing for this family's top ideas: (a) **residual returns** vs sector ETF and beta at 1d/5d/20d, and industry-adjusted returns (one feature group unlocks `residual_reversal_sector_neutral`, `industry_relative_mean_reversion_monthly`, and the stat-arb residual); (b) **ETF shares outstanding / flows** and per-stock ETF ownership (`etf_flow_reversal_constituents`); (c) a 50-day **volume percentile** (trivial) for the high-volume premium; (d) **news/no-news classification history** for large moves (reuse ADR 0050 attribution); (e) **RSI(2)**, **OBV**, **ADX**, **55-day Donchian**, **round-number distance** (all one-liners, low value); (f) **CGO** (turnover-weighted reference price) once multi-year history lands; (g) a **pattern detector** (only if the breakout features prove insufficient; low priority); (h) 10+ years of history incl. delisted names for the 52w/all-time-high trend-following test (in progress).

## Rejected on sight
- **Pure MA crossover timing on SPY / single stocks as alpha**: dead OOS (STW 1999; Bajgrowicz-Scaillet 2012; Zakamulin 2014); keep only as the regime filter we already have.
- **Candlestick patterns as signals**: Marshall-Young-Rose 2006/2008, Horton 2009: nothing on US/Japan stocks.
- **Bollinger band / %b stand-alone**: redundant with `price_z_20d`; no snooping-robust evidence.
- **Opening range breakout, intraday gap fades, NR7 day trades**: need intraday bars and execution; out of scope.
- **Copula pairs trading**: worst of the three methods net of costs (Rad-Low-Faff 2016).
- **Country/sector ETF pairs (distance method)**: Quantpedia OOS "significantly negative".
- **Fibonacci retracements, Elliott waves, Gann, point-and-figure**: no peer-reviewed evidence with snooping control; untestable definitions.
- **"Death cross" as a sell signal for single stocks**: the lag makes it a late momentum exit; subsumed by trend stats.
- **Leveraged / inverse ETF decay pairs (short both)**: borrow cost and squeeze risk; and already rejected under leveraged-ETF rebalancing.
- **Price-level effects (low-priced stocks, "penny stocks" bounce)**: microstructure noise + delisting bias; not a tradable edge for EOD.
- **Chart-pattern "measured move" targets (Bulkowski)**: no snooping control, survivorship in pattern selection.
- **Weekly lead-lag large->small as stand-alone**: cross-autocorrelation collapsed post-2000; economic-links lead-lag (customers/suppliers, Cohen-Frazzini) is the surviving relative and belongs to a fundamentals family.
- **Dual-listed ADR vs home-share arbitrage**: needs FX, home-market prices and borrow; a handful of names; another family if at all.
