# Edge ideas, family D. Calendar, forced flows and EOD microstructure

Researched 2026-10-17 (deep-research agents; index and ranking: [README.md](README.md)). Ideas, not edges: nothing here is filed or tested. Figures marked *not verified*, *nv*, *recalled* or *from memory* must be checked against the source before an edge document cites them (quality bar item 5, [edges-plan.md](../edges-plan.md)).


**Family summary (5 lines).**
1. The calendar ideas that still have a plausible *forced-flow* mechanism (turn-of-the-month payroll / pension cash, quarter-end 60/40 rebalancing, index rebalance days, option-expiration week, December tax-loss reversal) are the ones with post-2015 evidence; the pure "date" anomalies (Monday, pre-holiday, sell-in-May, January small-cap) are decayed or indistinguishable from noise after costs.
2. The famous Fed-calendar effects split: the pre-FOMC drift (Lucca-Moench) is **Dead since ~2015** (Kurov-Wolfe-Gilbert 2021), while the FOMC-cycle even-week pattern (Cieslak et al.) has no clean post-2016 out-of-sample test and should be treated as Weak until we run one.
3. Flow / attention ideas on single names (Lou 2012 flow-induced trading, Barber et al. Robinhood herding, high-volume premium, extreme-return reversal) are the strongest *cross-sectional* candidates here, and most are EOD-actionable (signal at close, act next open), but several need data we do not store (fund holdings, retail order flow, short interest).
4. Overnight-vs-intraday ("tug of war") is real and large in the data but is a *session-split* fact, not an EOD edge: it needs the open price to be traded (we have OHLC so a close-to-open leg is measurable) and its post-2020 cross-sectional persistence is not verified.
5. Intraday momentum (Gao-Han-Li-Zhou last half-hour) is **out of scope** without intraday bars; the MOC version cannot be formed from EOD data. Pinning, circuit breakers, ETF creation/redemption arbitrage and leveraged-ETF pairs are also out of scope or rejected for an individual.

Research note: web search was rate-limited and then exhausted during this task; items marked **(not verified)** rely on background knowledge and need a citation check before an edge document is written. No number below is invented; where a published number could not be confirmed it is stated as such.

Legend for "EOD-actionable": **Yes** = the trigger is fully known at close T and the first action is next open (T+1 open) or a MOC order on T+1; **Partial** = the trigger is EOD-known but the published return accrues in a window we cannot hit exactly; **No** = needs intraday data or intraday execution.

---

### turn_of_the_month — Turn-of-the-month equity premium
- **Thesis**: Hold broad equities only over the last trading day of the month and the first three of the next; most of the market's return is earned there.
- **Mechanism**: Month-end cash arrives in payroll / 401(k) / pension accounts and is invested on a schedule; settlement conventions (T+2, now T+1) make the pre-month-end selling and post-month-end buying predictable (Etula, Rinne, Suominen, Vaittinen, "Dash for Cash", RFS 2020). Ogden (1990) attributed it to month-end payment timing.
- **Persistence**: Flow is mandated (contribution schedules), not discretionary; the effect is small per day so arbitrage capital does not fully absorb it; found in ~30 markets (Quantpedia).
- **Rule (source's own)**: Long the index from close of the last trading day (or T-1) through the first 3 sessions of the new month; cash otherwise (McConnell & Xu 2008: TOM days = last day + first 3). Etula et al.: returns are *negative* in the days before month end (T-3..T-1 roughly) and positive T0..T+3.
- **Evidence**: McConnell & Xu (FAJ 2008): 1926-2005, essentially all of the equity premium accrues in the 4 TOM days; Etula et al. (2020): a 7-day-around-TOM portfolio since 1926 matched buy-and-hold with far less volatility (Validea summary). Post-2010 US-only updates: not found in this session; practitioner backtests (Quantpedia, CXO) report the effect weaker but positive in recent decades **(not verified)**.
- **Sources**: McConnell & Xu, "Equity Returns at the Turn of the Month", FAJ 2008; Etula, Rinne, Suominen, Vaittinen, "Dash for Cash: Monthly Market Impact of Institutional Liquidity Needs", RFS 2020 (https://aaltodoc.aalto.fi/items/00fea0ae-963b-444c-8221-912121905b98 thesis summary); Quantpedia, "Turn of the Month in Equity Indexes" (https://quantpedia.com/strategies/turn-of-the-month-in-equity-indexes); Choi, Hong, Lou, Mukherjee working paper on 401(k) flows (AEA 2022, https://aeaweb.org/conference/2022/preliminary/paper/iQikdBKZ).
- **Horizon / schedule**: 4-7 sessions; `month_end` (enter at close of T-1 or T0; exit close of T+3).
- **Data needed**: Daily index/ETF bars (SPY, IWM) — have; trading calendar — have. Tiingo history to 2010 gives ~190 month-ends; from 2024-10 only ~24.
- **Individual fit**: Unlimited capacity; 24 round trips a year in SPY; cost ~1-2 bp per side; long-only, no shorting. EOD-actionable: **Yes** (MOC on T-1 or open of T0).
- **Decoys / overlap**: Overlaps month-end index rebalancing, quarter-end pension rebalancing and the Dec/Jan effects (all sit on the same dates); beta exposure concentrated in ~20% of days. Test against the "any 4-day window" null.
- **Verdict**: Promising / Ready (needs the Tiingo history for >= 40 events with power; a 2010-2025 US re-estimate is the first job).

### quarter_end_rebalancing — Predictable 60/40 rebalancing flow at month / quarter end
- **Thesis**: When equities have beaten bonds over the month/quarter, balanced funds and pensions must sell equities (buy bonds) into the last sessions; fade the overweight asset at period end and expect a reversal.
- **Mechanism**: Calendar and threshold rebalancing by target-date, balanced and DB pension funds is mandated and large; the sign and rough size are public information once the month's relative performance is known (Harvey, Mazzoleni, Melone, "The Unintended Consequences of Rebalancing", NBER w33554, 2025).
- **Persistence**: Mandates (IPS bands, calendar policies) are slow to change; the authors estimate the cost at ~$16bn/yr, which front-runners capture; the funds bear the cost, not the trader.
- **Rule (source's own)**: Compute the drift of a 60/40 portfolio from its target over the month/quarter; when equities are overweight, next-day equity returns around rebalancing dates are lower (−17 bp per the paper's headline). Trade: short equities / long bonds into the last 1-2 sessions when equity is overweight, reverse after; or simply avoid being long equities on those days.
- **Evidence**: Harvey et al. 1997-2023: the predictable rebalancing flow moves equities and bonds; the −17 bp next-day effect when equities are overweight (press coverage of the paper). Sell-side desks (JPM, UBS) have published quarter-end flow estimates for a decade; price impact estimates vary. Bikker et al. (IJCB 2010) show Dutch pensions rebalance only ~39% of excess equity returns per quarter, so the flow is partial.
- **Sources**: Harvey, Mazzoleni, Melone, NBER w33554 (https://www.nber.org/papers/w33554); Duke Fuqua summary (https://www.fuqua.duke.edu/duke-fuqua-insights/what-do-pensions-lose-from-rebalancing); CXO Advisory, "Exploiting predictable institutional portfolio rebalancing" (https://cxoadvisory.com/calendar-effects/exploiting-predictable-institutional-portfolio-rebalancing); Bikker, Broeders, de Dreu, IJCB 2010.
- **Horizon / schedule**: 1-3 sessions; `month_end` and quarter-end (signal = month-to-date SPY minus TLT/AGG return known at T-2 close).
- **Data needed**: Daily bars for SPY and a bond ETF (TLT/AGG/IEF) — have; FRED Treasury total-return proxy for pre-ETF years — partial.
- **Individual fit**: Index-ETF capacity unlimited; 12-24 trades a year; needs shorting SPY or using SH/inverse ETF for the sell leg, or long-only version (step aside / tilt to bonds). EOD-actionable: **Yes**.
- **Decoys / overlap**: Overlaps turn-of-the-month (opposite sign in the last days, same sign at T0+); month-end reversal of the month's trend is also the generic 1-month index reversal. Separate "equity overweight" from "equity was up".
- **Verdict**: Promising / Ready (index-level; event count 12/yr so Tiingo 2010+ needed for power).

### month_end_index_rebalancing — Month-end / quarter-end index rebalance day flow
- **Thesis**: On the few sessions when major indices (S&P quarterly share/float updates, MSCI semi-annual, Russell annual, Nasdaq-100 December) rebalance, affected names show predictable abnormal volume and close-to-close moves that partly revert.
- **Mechanism**: Passive funds must trade at the close of the effective date; the trades are public days or weeks ahead; liquidity providers pre-position and unwind, leaving a run-up then reversal.
- **Persistence**: The flow is mandated and dated; however the size of the predictable component has shrunk as more capital pre-positions (Greenwood & Sammon showed S&P addition effect < 1% since 2010 — already **rejected** in this project).
- **Rule (source's own)**: For MSCI/Nasdaq-100 rebalances, buy announced additions at the announcement close, sell at the effective close; short deletions symmetrically. Nasdaq-100 reconstitution: announcement ~2nd Friday of December, effective after 3rd Friday. **(published numbers not verified this session)**.
- **Evidence**: Index-effect literature shows large 1990s-2000s effects shrinking toward zero for S&P 500 (Greenwood & Sammon 2022, cited in brief). For Nasdaq-100 and MSCI, effects remained larger (less pre-positioning, more constrained passive share) **(not verified)**. Russell is blocked (no membership data).
- **Sources**: Greenwood & Sammon, "The Disappearing Index Effect" (brief); Nasdaq-100 methodology (nasdaq.com); Chang, Hong, Liskovich, "Regression Discontinuity and the Price Effects of Stock Market Indexing", RFS 2015 (Russell).
- **Horizon / schedule**: 5-10 sessions; `on_event:index_change` (we store index changes).
- **Data needed**: Index change records (have for S&P 500; Nasdaq-100 and MSCI announcements would need to be added), daily bars — have.
- **Individual fit**: Mid/large caps, fine for an individual; both legs need shorting for the full version; long-only additions version feasible. EOD-actionable: **Yes** (the announcement is after the close; act next open).
- **Decoys / overlap**: Momentum (additions are recent winners); the filed "S&P 500 additions" rejection. Only a Nasdaq-100 / MSCI *variant* is worth testing.
- **Verdict**: Weak / Needs data (Nasdaq-100 + MSCI change calendars). Low priority given the S&P result.

### option_expiration_week — Option-expiration week premium (large caps)
- **Thesis**: Large-cap stocks earn abnormally high returns in the week of the monthly third-Friday expiration, and modestly weak returns the following week.
- **Mechanism**: Delta-hedge rebalancing by option market makers as time decay accelerates into expiry, plus implied-vol decline over the week (Stivers & Sun, JBF 2013).
- **Persistence**: Dealer hedging is mechanical; the effect is concentrated in optionable large caps and is a few tens of bp, below what large arbitrage capital pursues.
- **Rule (source's own)**: Long S&P 100 / large-cap optionable stocks from the close of the Friday before expiration week through the close of expiration Friday; the paper's sample 1983-2008 and 1996-2008 (significant in both halves). The paper's high-option-volume-ratio filter is hard to replicate.
- **Evidence**: Stivers & Sun 2013: expiration-week returns high for S&P 100 stocks, fourth-Friday week weak. Practitioner backtests (Quantpedia #102, QuantifiedStrategies) report the S&P 500 effect most prominent from 1990 and still positive in 2010s **(magnitudes not verified)**; no independent academic replication after 2008 found.
- **Sources**: Stivers & Sun, "Option Expiration Week Effect", JBF 37(11) 2013 (https://ideas.repec.org/a/eee/jbfina/v37y2013i11p4226-4240.html); Quantpedia (https://quantpedia.com/strategies/option-expiration-week-effect); CXO drill-down (https://cxoadvisory.com/calendar-effects/option-expiration-week-stock-return-drill-down).
- **Horizon / schedule**: 5 sessions; `on_event:opex_week` (monthly; 12 events/yr, ~180 since 2010).
- **Data needed**: Daily bars and the opex calendar — have; our chain data (OI, gamma walls) could condition it (names with large near-the-money OI). Triple witching (Mar/Jun/Sep/Dec) is a subset with S&P rebalance overlap.
- **Individual fit**: Large-cap, unlimited capacity, long-only, 12 trades/yr. EOD-actionable: **Yes**.
- **Decoys / overlap**: Overlaps the FOMC cycle (FOMC often lands in opex week), turn-of-month in some months; large-cap beta. Triple-witching weeks overlap S&P quarterly rebalance.
- **Verdict**: Promising / Ready (index + cross-section conditioned on our OI data is a differentiated variant).

### fomc_cycle_even_weeks — FOMC-cycle even-week premium
- **Thesis**: Since 1994 the US equity premium has been earned in weeks 0, 2, 4 and 6 of the inter-meeting FOMC cycle; be long in even weeks only.
- **Mechanism**: Systematic informal Fed communication (board meetings, leaks to media and the financial sector) on a bi-weekly schedule tied to the FOMC calendar; federal-funds volatility peaks in even weeks (Cieslak, Morse, Vissing-Jorgensen, JF 2019).
- **Persistence**: Debated; the mechanism is institutional but the rule lacks a theory of why it should not be arbitraged; the pattern uses a public calendar.
- **Rule (source's own)**: Week 0 = the week of the FOMC announcement (day −1 to +3); count weeks in cycle time; long in even weeks, flat in odd. Sample 1994-2016.
- **Evidence**: Cieslak et al.: entire premium in even weeks over 1994-2016. Post-2016 out-of-sample test: none found; CIRANO 2024 builds a capital-allocation rule on it but does not test 2020-24. Pre-FOMC drift (week 0's core) is dead post-2015, which undermines part of the pattern.
- **Sources**: Cieslak, Morse, Vissing-Jorgensen, "Stock Returns over the FOMC Cycle", JF 2019 (https://stern.nyu.edu/sites/default/files/assets/documents/cycle_paper_cieslak_morse_vissingjorgensen.pdf); CIRANO 2024s-02 (https://cirano.qc.ca/en/summaries/2024s-02); CFA Digest (https://rpc.cfainstitute.org/research/cfa-digest/2020/05/dig-v50-n5-2).
- **Horizon / schedule**: 5 sessions on/off; `every_session` with the FOMC calendar (have via macro calendar).
- **Data needed**: SPY bars + FOMC dates — have.
- **Individual fit**: Trivial to run, long-only; 8 switches per cycle. EOD-actionable: **Yes**.
- **Decoys / overlap**: Pre-FOMC drift, opex week, macro-announcement days. Decoy: any alternating-week rule on a long bull sample.
- **Verdict**: Weak / Ready (cheap to test 2017-2025; retire if no even/odd spread).

### pre_fomc_drift — Pre-FOMC announcement drift
- **Thesis**: Buy the index 24 hours before scheduled FOMC statements, sell at the announcement.
- **Mechanism**: Resolution of monetary-policy uncertainty priced in advance (Lucca & Moench, JF 2015).
- **Persistence**: Did not persist.
- **Rule (source's own)**: Long from 2pm the day before to 2pm announcement day (1994-2011: ~49 bp average, most of the equity premium).
- **Evidence**: Kurov, Wolfe, Gilbert, "The Disappearing Pre-FOMC Announcement Drift", FRL 2021: extended to Dec 2019, the drift essentially vanished after 2015 with or without press conferences. Martello & Ribeiro: the drift lives in high-uncertainty periods only. Cujean 2023: switches on/off in equilibrium.
- **Sources**: Lucca & Moench, JF 2015; Kurov, Wolfe, Gilbert, FRL 2021 (https://www.skidmore.edu/economics/documents/KurovWolfeGilbert-TheDisappearingPre-FOMC-Announce-Drift-200914.pdf); Quantpedia summary (https://quantpedia.com/fomc-equity-drift-occurs-in-periods-of-high-uncertainty/).
- **Horizon / schedule**: 1 session; `on_event:fomc`.
- **Data needed**: Have (SPY, FOMC calendar). Note the published window is 2pm-2pm; the EOD proxy is close T-1 to close T.
- **Individual fit**: Trivial; 8 events/yr. EOD-actionable: **Partial** (close-to-close proxy only).
- **Decoys / overlap**: Even-week FOMC cycle; VIX-conditioned regime.
- **Verdict**: Dead (post-2015) / Ready as a conditional (high-VIX-only) variant at most; do not file on its own.

### macro_announcement_days — Macro announcement-day premium (Savor-Wilson), CPI / NFP days
- **Thesis**: The market earns most of its excess return on scheduled macro-release days (CPI, employment, FOMC); be long only on those days.
- **Mechanism**: Compensation for bearing macro-news risk concentrated on known dates (Savor & Wilson, JFQA 2013); also a beta-is-priced-on-announcement-days result (Savor & Wilson, JFE 2014).
- **Persistence**: Risk-based, so should persist in expectation, but the per-day premium is small (~10 bp) and the FOMC component has decayed (above).
- **Rule (source's own)**: Long the index on days with scheduled CPI, employment or FOMC releases (1958-2009: announcement-day excess return ~11 bp vs ~1 bp on other days **(numbers from memory, not verified)**).
- **Evidence**: Savor & Wilson 2013/2014 in-sample; post-2015 US re-tests not found this session; the FOMC leg's decay suggests the CPI/NFP legs carry the remaining weight **(not verified)**. Our own data (macro calendar + SPY) can re-estimate quickly.
- **Sources**: Savor & Wilson, "How Much Do Investors Care About Macroeconomic Risk?", JFQA 2013; Savor & Wilson, "Asset Pricing: A Tale of Two Days", JFE 2014.
- **Horizon / schedule**: 1 session; `on_event:macro_release` (~30 days/yr).
- **Data needed**: Macro release calendar — have; SPY bars — have.
- **Individual fit**: Trivial, long-only; the premium per day is far below the bid-ask of switching every day, so only a "hold through announcement days, hedge others" tilt makes sense. EOD-actionable: **Yes** (hold close T-1 to close T).
- **Decoys / overlap**: Even-week FOMC; opex week; the beta-on-announcement-days result is a cross-sectional variant (high-beta names on CPI/NFP days) that overlaps low-beta/BAB.
- **Verdict**: Weak / Ready (cheap test; likely too small after costs for an individual).

### overnight_vs_intraday_tug_of_war — Overnight premium and session-split anomaly returns
- **Thesis**: Nearly all of the US equity premium accrues close-to-open; anomaly (momentum, reversal) profits accrue in one session only, so hold anomaly longs overnight and avoid the intraday leg.
- **Mechanism**: Different clienteles trade at the open vs the close (retail/overnight news vs institutional intraday); arbitrageurs with margin and lending-fee constraints unwind before the close, pushing mispricing factors down at day end (Bogousslavsky, JFE 2021; Lou, Polk, Skouras, JFE 2019).
- **Persistence**: Structural (who trades when) and constraint-based; Bogousslavsky reports the end-of-day pattern *strengthened* in the second half of his sample.
- **Rule (source's own)**: Lou-Polk-Skouras: for 14 strategies, decompose returns into close-to-open and open-to-close; momentum and reversal profits are earned overnight, with opposite-signed intraday components. "Overnight momentum": stocks with high past overnight returns continue overnight.
- **Evidence**: LPS 2019 (1993-2013): profits entirely in one session; LPS 2022 working paper: tech boom, Covid, meme stocks were overnight phenomena; Bogousslavsky 2021: mispricing factor positive during the day, negative at the close. Post-2020 cross-sectional decay: no study found.
- **Sources**: Lou, Polk, Skouras, "A Tug of War: Overnight vs Intraday Expected Returns", JFE 2019 (https://personal.lse.ac.uk/polk/research/TugOfWar.pdf); Bogousslavsky, "The Cross-Section of Intraday and Overnight Returns", JFE 2021 (https://academicnewsletter.sufe.edu.cn/info/355295); Polk working papers (https://personal.lse.ac.uk/POLK/research/work.htm).
- **Horizon / schedule**: 1 session per leg, held repeatedly; `every_session`.
- **Data needed**: Daily OHLC (open and close) — have, so overnight (open_t/close_{t-1}) and intraday legs are computable; adjusted for dividends/splits — have.
- **Individual fit**: Trading every open and close is impractical for one person (2 trades/day/name, spread costs eat a ~5 bp/day premium); the usable form is a *conditioning* rule (e.g., hold reversal/momentum longs, know the profit arrives at the open, enter MOC). EOD-actionable: **Partial** (enter MOC, exit next open; both legs are known times but costs dominate).
- **Decoys / overlap**: Overlaps filed 12-1 momentum and the extreme-return reversal below (it decomposes them rather than adding to them). Decoy: dividends and index-futures gap mechanics.
- **Verdict**: Promising as a *decomposition tool* for other edges, Weak as a standalone / Ready.

### overnight_momentum — Persistence of overnight returns in the cross-section
- **Thesis**: Stocks that have outperformed close-to-open over the past month keep outperforming close-to-open.
- **Mechanism**: Persistent clientele demand at the open (retail buying at open; Lou-Polk-Skouras) and attention; firm-specific overnight returns reflect a stable "who trades this name" imbalance.
- **Persistence**: Same as the tug of war; the return exists only overnight so it is not harvested by intraday capital.
- **Rule (source's own)**: Sort on past 1-month cumulative overnight return; long top decile / short bottom; hold overnight only, rebalance monthly (LPS 2019, 1993-2013) **(published spread not verified)**.
- **Evidence**: LPS 2019 report strong overnight persistence; later evidence (Akbas et al., Hendershott-Livdan-Rösch 2020 "Asset pricing: a tale of night and day") confirms night/day beta differences **(not verified)**.
- **Sources**: Lou, Polk, Skouras 2019; Hendershott, Livdan, Rösch, "Asset Pricing: A Tale of Night and Day", JFE 2020 **(citation from memory)**.
- **Horizon / schedule**: 20 sessions; `every_session` (overnight holds) or `month_end` sort.
- **Data needed**: OHLC — have.
- **Individual fit**: Impractical as a pure overnight-only book; the long-only "hold through the open" variant is just the tug-of-war conditioning. EOD-actionable: **Partial**.
- **Decoys / overlap**: Filed momentum; retail attention.
- **Verdict**: Weak for an individual / Ready to measure as a decomposition.

### close_to_open_gap_reversal — Gap-fill / overnight-gap reversal in single names
- **Thesis**: Large overnight gaps not caused by scheduled news partially fill intraday or over the next sessions.
- **Mechanism**: Overnight thin liquidity and retail-at-open imbalance overshoot; the intraday session corrects (LPS 2019's negative intraday component of reversal).
- **Persistence**: Costs and the need to trade at the open limit arbitrage; however it is heavily traded by prop desks.
- **Rule (source's own)**: No single canonical academic rule; practitioner literature (Quantpedia / Chan) buys/sells gaps of >1 ATR against the gap and exits at the close or the gap fill **(no verified published number)**.
- **Evidence**: Anecdotal / practitioner; academic support is indirect (session decomposition). Earnings gaps show *drift*, not fill (filed small-cap PEAD); non-news gaps show partial fill **(not verified)**.
- **Sources**: Chan, "Algorithmic Trading" (gap strategies chapter); Lou-Polk-Skouras 2019.
- **Horizon / schedule**: 1 session; `every_session`.
- **Data needed**: OHLC — have; an "unscheduled news" filter (8-K items, earnings dates) — have.
- **Individual fit**: Requires acting *at the open* and often exiting intraday; capacity small. EOD-actionable: **No** (the gap is only known at the open; the fade is intraday).
- **Decoys / overlap**: Overnight tug-of-war; one-day reversal.
- **Verdict**: Weak / Out of scope (intraday execution).

### intraday_momentum_last_half_hour — Market intraday momentum (first half-hour predicts last half-hour)
- **Thesis**: The SPY return in the first 30 minutes (and the 30 minutes before the last) predicts the last 30 minutes' return.
- **Mechanism**: Late-informed traders, and infrequent rebalancers who trade near the close in the direction of the day (Gao, Han, Li, Zhou, JFE 2018).
- **Persistence**: Rebalancing-at-close is structural (MOC flow, leveraged ETFs), but the effect is small and heavily traded.
- **Rule (source's own)**: Sign of first-half-hour return (and of the 12th half-hour) -> position in the last half-hour; SPY 1993-2013; stronger on volatile, high-volume and macro-news days; out-of-sample R^2 ~1.8% and 6.3% vs −0.5% gross annual return in one replication (1999-2012).
- **Evidence**: GHLZ 2018 in-sample and out-of-sample through 2013; no 2020-24 replication found; the leveraged-ETF rebalancing channel was already **rejected** in this project as intraday/weak after costs.
- **Sources**: Gao, Han, Li, Zhou, "Market Intraday Momentum", JFE 129 (2018) 394-414; Alpha Architect summary (https://alphaarchitect.com/2014/08/attention-prop-traders-the-first-half-hour-of-trading-predicts-the-last-half-hour/); CXO (https://cxoadvisory.com/calendar-effects/first-and-last-half-hours-of-trading-linked).
- **Horizon / schedule**: 30 minutes; intraday.
- **Data needed**: Intraday bars — **missing**. Can it be traded EOD/MOC? **No**: the signal (first half-hour) and the trade (last half-hour, or a MOC order placed at ~3:30pm) both need intraday prices; a MOC order could be placed by hand if one had the 10am price, but we store none. An EOD proxy (open-to-close sign as a predictor of the *next* day's close) is a different, weaker claim.
- **Individual fit**: Requires being at the screen at 15:30; capacity fine. EOD-actionable: **No**.
- **Decoys / overlap**: Leveraged-ETF rebalancing (rejected); overnight tug-of-war.
- **Verdict**: Promising in the literature but Out of scope (no intraday data; not EOD-actionable).

### day_of_week — Day-of-the-week / Monday effect
- **Thesis**: Returns differ systematically by weekday (historically negative Mondays).
- **Mechanism**: Mood (Birru, JFE 2018: speculative stocks underperform on Mondays and outperform on Fridays), settlement and news-timing stories.
- **Persistence**: Mostly gone at the index level since the mid-1990s (Morey & Rosenberg: Monday returns insignificant by mid-1990s; effect reversed in some samples).
- **Rule (source's own)**: Birru: long speculative (high-vol, lottery, young, unprofitable) stocks Friday-to-Monday... actually short them into Monday and long into Friday; sample 1963-2013 **(spread not verified)**.
- **Evidence**: Index Monday effect: Dead. Birru's cross-sectional mood version: in-sample through 2013; post-publication: unknown.
- **Sources**: Birru, "Day of the week and the cross-section of returns", JFE 130 (2018) 182-214; Morey & Rosenberg, "The Monday effect: dissipated" (Bearworks Missouri State, https://bearworks.missouristate.edu/articles-cob/412); review in Management Review Quarterly 2020 (https://ideas.repec.org/a/spr/manrev/v70y2020i2d10.1007_s11301-019-00167-4.html).
- **Horizon / schedule**: 1 session; `every_session`.
- **Data needed**: Have.
- **Individual fit**: Daily turnover makes it uneconomic; the cross-sectional version is a conditioning rule for when to enter speculative longs (Friday close vs Monday close). EOD-actionable: **Yes** (but tiny).
- **Decoys / overlap**: Lottery / idiosyncratic-vol anomalies; overnight effects (Friday-to-Monday is a long "overnight").
- **Verdict**: Dead (index) / Weak (cross-section) / Ready; low priority.

### pre_holiday — Pre-holiday effect
- **Thesis**: The session before an exchange holiday earns an abnormally high return.
- **Mechanism**: Short covering before the long close, positive mood, low volume (Ariel 1990; Lakonishok & Smidt 1988).
- **Persistence**: Weak; a few days a year; decayed since the 1990s in most US re-tests **(not verified)**.
- **Rule (source's own)**: Long the index from close T-2 to close T-1 before each market holiday (Ariel: 1963-1982, pre-holiday day ~9-14x the normal day's return **(from memory)**).
- **Evidence**: In-sample strong pre-1990; later US evidence mixed / insignificant (Quantpedia, CXO) **(not verified)**. ~9 events/yr: 2010-2025 gives ~140 events but with very noisy single days.
- **Sources**: Ariel, "High Stock Returns before Holidays", JF 1990; Lakonishok & Smidt, RFS 1988; Quantpedia "Pre-holiday effect".
- **Horizon / schedule**: 1 session; `on_event:exchange_holiday`.
- **Data needed**: Have (calendar + SPY).
- **Individual fit**: Trivial; long-only. EOD-actionable: **Yes**.
- **Decoys / overlap**: Turn-of-month (several holidays fall near month ends), low-volume days.
- **Verdict**: Decayed / Ready; test once with the TOM dates excluded, then retire.

### halloween_sell_in_may — Halloween indicator
- **Thesis**: Equities earn their premium November-April; be out (or hedged) May-October.
- **Mechanism**: No agreed mechanism (vacations, SAD, seasonal risk appetite); Jacobsen & Zhang document it in 89 of 114 markets over 320 years.
- **Persistence**: Robust across history but the May-Oct return is positive on average in the US, so "sell" is a relative, not absolute, call; post-2010 US summers (2013, 2017, 2020, 2021, 2023, 2024) were strong **(not verified)**.
- **Rule (source's own)**: Long index Nov-Apr, T-bills May-Oct; Jacobsen & Zhang: avg Nov-Apr advantage 4.52% (1693-2011), 6.3% over the last 50 years; beats buy-and-hold in >80% of 5-year windows.
- **Evidence**: In-sample strong; out-of-sample 2012-2025 US: not updated in a found study; the effect is 2 observations per year so a point-in-time harness cannot reach 40 independent events in our history (Tiingo 2010+: 15 pairs).
- **Sources**: Jacobsen & Zhang, "The Halloween Indicator, 'Sell in May and Go Away': Everywhere and All the Time" (https://www.bnains.org/backtest/periode/The_Halloween_Indicator_everywhere_and_all_the_time_-_Ben_Jacobsen_%26_Cherry_Y._Zhang.pdf); CXO (https://cxoadvisory.com/calendar-effects/halloween-effect-pervasiveness); Bouman & Jacobsen, AER 2002.
- **Horizon / schedule**: 6 months; semi-annual.
- **Data needed**: Have.
- **Individual fit**: Trivial; long-only. EOD-actionable: **Yes**.
- **Decoys / overlap**: Pure seasonality; too few events.
- **Verdict**: Weak / Ready but fails the >=40-event bar; file only as a regime covariate for other edges.

### january_effect_small_caps — January small-cap premium
- **Thesis**: Small caps outperform in January, especially the first week.
- **Mechanism**: Tax-loss selling in December reversing, window dressing, year-end bonus cash.
- **Persistence**: Largely arbitraged away since the 1990s in large/mid caps; survives, if at all, in micro-caps where we cannot trade.
- **Rule (source's own)**: Long smallest-decile stocks, short largest, in January (Keim 1983; Reinganum 1983).
- **Evidence**: Keim 1963-1979 ~ half of the size premium in January; post-2000 US evidence: insignificant or confined to micro-caps (Kozlowski & Lytle 2023 find turn-of-year reversal and momentum sign flips, stronger after bad years).
- **Sources**: Keim, JFE 1983; Kozlowski & Lytle, "The January Anomaly and Anomalies in January", Applied Finance Letters 2023 (https://ojs.aut.ac.nz/applied-finance-letters/article/view/615).
- **Horizon / schedule**: 20 sessions; `month_end` (December).
- **Data needed**: Have (size from shares outstanding x price).
- **Individual fit**: Micro-cap illiquidity. EOD-actionable: **Yes**.
- **Decoys / overlap**: Size, illiquidity, December-loser reversal (below), TOM.
- **Verdict**: Decayed / Ready; fold into december_losers_reversal.

### december_losers_reversal — Tax-loss-selling reversal of December losers
- **Thesis**: Stocks that fell most over the year are sold for tax reasons in December and rebound in the first sessions of January; buy the year's losers in the last week of December.
- **Mechanism**: Individual investors and some funds realise losses before year end (Grinblatt & Keloharju, NBER w8745: selling pressure on the year's largest decliners disappears at the new year); Poterba & Weisbenner (JF 2001) tie it to tax-regime changes.
- **Persistence**: Tax incentives are permanent; the selling is predictable but holders cannot defer it past 31 Dec; the rebound is a few percent in small losers and arbitrage capital is scarce in late December.
- **Rule (source's own)**: Sort on YTD (or 12-month) return at ~Dec 20; long the bottom decile from the last ~5 sessions of December to mid-January; Kozlowski & Lytle 2023: short-term reversal strengthens and momentum flips sign at the turn of the year, more after recession / poor-market years.
- **Evidence**: Long literature in-sample; recent: Kozlowski & Lytle 2023 (sample through ~2021 **(not verified)**); strong anecdotal 2022->2023 reversal in the hardest-hit growth names. Only 1 event per year -> 15 events since 2010; the cross-section inside each year gives power but the events are not independent.
- **Sources**: Grinblatt & Keloharju, NBER w8745 (https://www.nber.org/papers/w8745.pdf); Poterba & Weisbenner, "Capital Gains Tax Rules, Tax-loss Trading, and Turn-of-the-Year Returns", JF 2001; Kozlowski & Lytle 2023 (above).
- **Horizon / schedule**: 10-15 sessions; `on_event:year_end` (enter ~Dec 24 close, exit ~Jan 15).
- **Data needed**: Have (daily bars, universe snapshots); better with liquidity filter.
- **Individual fit**: Long-only, 10-30 names, small/mid caps, once a year. EOD-actionable: **Yes**.
- **Decoys / overlap**: Short-term reversal, size, filed 12-1 momentum (this is its seasonal inverse), window dressing.
- **Verdict**: Promising / Ready (annual event; the harness must treat each year as one event, so expect low statistical power; useful as a seasonal overlay on the momentum edge: skip the short/loser leg in January).

### quarter_end_window_dressing — Window dressing at quarter end
- **Thesis**: Funds buy recent winners and sell losers / embarrassing names into quarter-end reporting dates, reversing in the first days of the next quarter.
- **Mechanism**: Portfolio disclosure incentives (Lakonishok, Shleifer, Thaler, Vishny 1991; Ng & Wang 2004 for small-cap losers; Agarwal, Gay, Ling 2014 "Window dressing in mutual funds").
- **Persistence**: Agency problem; but the price footprint is small and overlaps TOM / tax effects.
- **Rule (source's own)**: Long winners / short losers in the last days of the quarter, reverse after; Ng & Wang: year-end small-cap loser selling by institutions and January rebound **(numbers not verified)**.
- **Evidence**: Mixed; the mark-up at quarter end (Carhart et al. 2002 "Leaning for the Tape": equity funds' quarter-end last-day returns abnormally high and reversed next day) is the best-documented footprint; post-2010 evidence that it shrank with regulation **(not verified)**.
- **Sources**: Carhart, Kaniel, Musto, Reed, JF 2002; Ng & Wang, JFE 2004; Agarwal, Gay, Ling, RFS 2014.
- **Horizon / schedule**: 2-3 sessions; quarter `month_end`.
- **Data needed**: Daily bars — have; fund holdings (13F) — **missing** for a holdings-based version.
- **Individual fit**: Needs shorting for the full version; long-only "buy the last-day dip of small losers" variant. EOD-actionable: **Yes**.
- **Decoys / overlap**: TOM, december_losers_reversal, quarter-end rebalancing, momentum.
- **Verdict**: Weak / Ready for the price-only variant; Needs data (13F) for the holdings version.

### flow_induced_trading_lou — Mutual-fund flow-induced price pressure (Lou 2012)
- **Thesis**: Stocks held by funds receiving inflows are bought mechanically (and vice versa); expected flow-induced trading predicts returns over the next year and reverses after.
- **Mechanism**: Managers scale existing positions with flows (sell $1 per $1 of redemptions, buy ~$0.62 per $1 of inflows); flows chase past performance so the trading is forecastable (Lou, RFS 2012).
- **Persistence**: Agency and mandate (open-end structure); the price pressure is uninformed; it explains fund-performance persistence and part of momentum. Later work finds separate accounts have no such impact (contrast confirms the open-end channel).
- **Rule (source's own)**: FIT_i = sum over funds of (flow x holding) / shares outstanding; expected FIT from the flow-performance relation; long top / short bottom decile; 1980-2006; one-year positive, then reversal over years 2-3. One extension: 1 sd of quarterly FIT -> 2.9-3.8% contemporaneous factor return, fully reversed in 1-2 years.
- **Evidence**: Lou 2012 in-sample; Wardlaw 2020 (JF) criticised the FIT construction (mechanical price dependence) and found the predictability weaker after correction **(from memory, not verified)**; recent papers still use FIT as an instrument (2024-2026 working papers on flow spirals).
- **Sources**: Lou, "A Flow-Based Explanation for Return Predictability", RFS 25(12) 2012 (https://ideas.repec.org/a/oup/rfinst/v25y2012i12p3457-3489.html); LSE eprint (https://researchonline.lse.ac.uk/id/eprint/29310); "Same Dollar Different Impact" 2026 working paper (https://hkujcesgri.hku.hk/wp-content/uploads/2026/04/Same-Dollar-Different-Impact.pdf); arXiv 2405.12768 on flow-driven spirals.
- **Horizon / schedule**: 60-250 sessions; quarterly rebalance after holdings disclosure.
- **Data needed**: Mutual-fund holdings and flows (CRSP MF / Morningstar / N-PORT) — **missing**; ETF holdings (iShares, SSGA) and ETF flows could give a partial ETF-only version (see etf_flows_to_underlying).
- **Individual fit**: Long-only top decile feasible; capacity large (mid/large caps). EOD-actionable: **Yes** (quarterly).
- **Decoys / overlap**: Momentum (flows chase winners) — filed 12-1 momentum; size.
- **Verdict**: Promising / Needs data (fund holdings + flows; N-PORT is free from SEC EDGAR and may be addable).

### etf_flows_to_underlying — ETF flow pressure on constituents and its reversal
- **Thesis**: Large ETF creations push constituents up (redemptions down) in proportion to the ETF's weight x flow / stock float; the move reverts over weeks.
- **Mechanism**: APs hedge/create by buying the basket; ETF flows are partly non-fundamental (Ben-David, Franzoni, Moussawi, JF 2018 on ETF-induced volatility; Brown, Davies, Ringgenberg, Review of Finance 2021: ETF flows as a measure of non-fundamental demand predict return reversals **(citation from memory)**).
- **Persistence**: Passive flow is mandated; ETF-implied demand on small constituents of sector/thematic ETFs can be large relative to float; arbitrage is slow because the fundamental value is unknown.
- **Rule (source's own)**: Brown-Davies-Ringgenberg: ETF-level flows (shares-outstanding changes) predict negative subsequent ETF returns; stock-level: aggregate implied flow / market cap, long low / short high, monthly **(spreads not verified)**.
- **Evidence**: BFM 2018: stocks with higher ETF ownership have higher volatility; BDR 2021: flow-induced reversal at the ETF level; a growing 2022-2025 literature on "ETF ownership and price pressure".
- **Sources**: Ben-David, Franzoni, Moussawi, "Do ETFs Increase Volatility?", JF 2018; Brown, Davies, Ringgenberg, "ETF Arbitrage, Non-Fundamental Demand, and Return Predictability", Review of Finance 2021 **(not verified this session)**.
- **Horizon / schedule**: 20-60 sessions; `every_session` or `month_end`.
- **Data needed**: ETF holdings (iShares, SSGA) — have; ETF shares outstanding / daily flows — **partial** (need shares outstanding history per ETF; Tiingo may supply volume only); stock float — have (shares outstanding).
- **Individual fit**: Long/short on mid caps; long-only "buy heavy redemption names" variant. EOD-actionable: **Yes**.
- **Decoys / overlap**: Short-term reversal; sector momentum; flow_induced_trading_lou (same channel through a different vehicle).
- **Verdict**: Promising / Needs data (ETF shares-outstanding history for flows). Good fit with our holdings data.

### etf_premium_discount_reversion — ETF premium / discount mean reversion
- **Thesis**: ETFs trading at a premium to NAV at the close underperform the next day, discounts outperform; strongest in illiquid-underlying ETFs (bonds, international).
- **Mechanism**: Stale NAVs and AP arbitrage costs let the ETF price wander from NAV; it reverts as APs create/redeem (Petajisto, FAJ 2017, "Inefficiencies in the Pricing of Exchange-Traded Funds").
- **Persistence**: Arbitrage is bounded by creation costs and basket illiquidity; in liquid equity ETFs the premium is a few bp and not tradable.
- **Rule (source's own)**: Petajisto: sort ETFs on premium relative to a peer-group-implied NAV; long discounted / short premium ETFs; 2007-2014; ~1.5-2% of mispricing on average in illiquid categories **(from memory, not verified)**.
- **Evidence**: In-sample through 2014; post-2016 US: the March 2020 bond-ETF discount episode is the famous case; no systematic recent replication found.
- **Sources**: Petajisto, FAJ 73(1) 2017 **(not verified this session)**.
- **Horizon / schedule**: 1-5 sessions; `every_session`.
- **Data needed**: Daily NAV per ETF — **missing** (iShares/SSGA holdings files include NAV; general NAV history would need a source); ETF close — have.
- **Individual fit**: Fixed-income / international ETFs; needs shorting for the premium leg; long-only discount leg feasible. EOD-actionable: **Yes** (premium known at close; act next open).
- **Decoys / overlap**: Stale-NAV artefact (international ETFs' NAV is at foreign close): the "premium" is partly fair; must use the peer-implied NAV.
- **Verdict**: Weak-to-Promising / Needs data (NAV history).

### closed_end_fund_discounts — CEF discount mean reversion and activism
- **Thesis**: Buy closed-end funds at unusually wide discounts to NAV (relative to their own history); discounts mean-revert and attract activists.
- **Mechanism**: Retail-held, no creation/redemption, sentiment-driven (Lee, Shleifer, Thaler 1991); activists (Saba, Bulldog) force tender offers / open-ending that halve discounts (Bradley, Brav, Goldstein, Jiang, JFE 2010).
- **Persistence**: Small, retail, illiquid market that institutions avoid; the discount is a real cash-flow drag (fees) so part of it is fair; activism is capacity-limited.
- **Rule (source's own)**: Patro, Piccotti, Wu: long widest-discount / short narrowest-discount quintile relative to history; annualised 18.2%, Sharpe 1.9 (1998-2011). Activism: discount size is the main determinant of being targeted; open-ending attempts cut discounts to about half.
- **Evidence**: In-sample strong; 2015-2024 systematic study not found; 2024 press: AQR and others "piling in" on wide discounts; Saba campaigns (e.g., a fund tendering 70% of units).
- **Sources**: Patro, Piccotti, Wu (Quantpedia summary, https://hedgefundalpha.com/strategies/closed-end-fund-discounts/); Bradley, Brav, Goldstein, Jiang, "Activist Arbitrage" (https://drupalgsb-test.paas.cc.columbia.edu/sites/default/files-efs/pubfiles/4118/activist_arb.pdf); Gasbarro, Johnson, Zumwalt 2003; FA-mag 2024 (https://www.fa-mag.com/news/wall-street-managers-pile-into-closed-end-funds-on-discounts-75385.html).
- **Horizon / schedule**: 60-250 sessions; `month_end`.
- **Data needed**: CEF universe and daily NAVs — **missing** (CEFs are listed stocks so prices are in our bars; NAV needs CEFConnect / fund sponsors); 13D filings for activism — partially via SEC filings (have events/filing).
- **Individual fit**: Excellent for an individual (small, illiquid, long-only); the classic retail edge; capacity $1-10m. EOD-actionable: **Yes**.
- **Decoys / overlap**: Discount reflects fees / leverage / distribution policy; sentiment beta; the short leg is unnecessary.
- **Verdict**: Promising / Needs data (NAV history; a CEF instrument class). Owner-relevant: long-only, individual-sized.

### retail_attention_herding — Retail attention and Robinhood-style herding (contrarian)
- **Thesis**: Names with extreme retail buying / attention spikes (herding episodes) earn negative abnormal returns over the next week to month; fade them.
- **Mechanism**: Attention-induced buying by individuals who can only buy what they notice (Barber & Odean, RFS 2008); Robinhood users herd into the same few names; the top-bought stocks each day average about −3% 5-day abnormal returns, −6% in extreme herding (Barber, Huang, Odean, Schwarz, JF 2022).
- **Persistence**: Behavioural and structural (zero-commission, gamified apps, "top movers" lists); short-selling constraints and borrow costs in meme names limit arbitrage; persisted through 2020-2021 and is documented in Reddit-era data.
- **Rule (source's own)**: BHOS: daily top-N stocks by change in Robinhood user holdings; short-horizon returns over the next 5-20 days negative; sample 2018-2020 (Robintrack). Barber & Odean 2008: attention proxies = abnormal volume, extreme prior-day return, news.
- **Evidence**: BHOS 2022 strong; Robintrack data ended Aug 2020 so the exact signal is not reproducible; proxies (abnormal volume + extreme return + small/lottery characteristics) remain available. Post-2021 meme behaviour (2024-2025 GME/AMC/retail-favourite episodes) is anecdotally consistent **(not verified)**.
- **Sources**: Barber, Huang, Odean, Schwarz, "Attention-Induced Trading and Returns: Evidence from Robinhood Users", JF 2022 (https://profiles.wustl.edu/en/publications/attention-induced-trading-and-returns-evidence-from-robinhood-use/; SSRN 3715077); Barber & Odean, "All That Glitters", RFS 2008; UC Davis summary (https://gsm.ucdavis.edu/news/what-effect-brokerage-robinhood-having-stock-market).
- **Horizon / schedule**: 5-20 sessions; `every_session` (signal at close; act next open).
- **Data needed**: Attention proxies from daily bars (volume shock, |return|) — have; options chain flow (retail call buying: small-lot call volume / OI surge) — have (chain flow); Robinhood holdings / retail order imbalance (Boehmer-Jones-Zhang-Zhang algorithm needs TAQ) — **missing**; short interest / borrow fee — **missing**.
- **Individual fit**: Short side is hard-to-borrow and squeeze-prone (the GME lesson); the long-only version is "avoid / exit names in a herding episode" or buy puts (we have chains). Capacity fine. EOD-actionable: **Yes**.
- **Decoys / overlap**: Short-term reversal after extreme returns; lottery / high-IV anomalies; volume shock (below) has the *opposite* sign at 1-month in Gervais et al. — must reconcile horizon.
- **Verdict**: Promising / Ready with proxies (the pure signal needs retail flow data we lack). A put-based fade using our chain data is a differentiated variant.

### high_volume_return_premium — High-volume return premium (Gervais-Kaniel-Mingelgrin)
- **Thesis**: A stock with unusually high volume on a day (or week) outperforms over the following 1-3 months; unusually low volume underperforms.
- **Mechanism**: Visibility: a volume shock raises investor awareness and subsequent demand (Merton 1987 recognition); not explained by return autocorrelation, announcements, risk or liquidity (GKM, JF 2001).
- **Persistence**: Behavioural / attention; the effect is strongest in small caps and is modest per event; later work finds it robust to liquidity, price level and earnings-announcement filters, with magnitude varying by market conditions.
- **Rule (source's own)**: Reference period = 50 days; formation day's volume in top (bottom) 10% of the reference period -> long (short); hold 20 or 50 days; 1963-1996; the high-volume minus low-volume portfolio earned roughly 0.5% over 20 days in the paper **(magnitude from memory, not verified)**.
- **Evidence**: GKM 2001; Kaniel, Ozoguz, Starks (JFE 2012) find it in 41 countries; Chen-Zimmermann's open-source catalogue includes a volume-shock style predictor (VolumeTrend / "AbnormalVolume"?) — **not verified**; no 2020-23 US out-of-sample found. The conflict with retail-herding (negative 5-day returns after attention spikes) implies the sign depends on horizon and on whether the shock comes with an extreme return.
- **Sources**: Gervais, Kaniel, Mingelgrin, "The High-Volume Return Premium", JF 2001 (https://sites.duke.edu/sgervais/?p=64); Kaniel, Ozoguz, Starks, JFE 2012; 2025 Managerial Economics paper on robustness (https://journals.agh.edu.pl/manage/article/download/7831/3300/37077).
- **Horizon / schedule**: 20-50 sessions; `every_session` (signal daily, hold 20).
- **Data needed**: Daily volume and bars — have (volume shock is a natural catalogue feature).
- **Individual fit**: Long-only high-volume leg feasible; small/mid caps; many signals per day so position limits and a liquidity filter are needed. EOD-actionable: **Yes**.
- **Decoys / overlap**: Earnings-announcement volume (exclude announcement days: filed PEAD overlaps); short-term reversal; retail attention (opposite sign at short horizon).
- **Verdict**: Promising / Ready.

### volume_shock_with_no_news — Volume shock without an identifiable event
- **Thesis**: An abnormal-volume day with no earnings, no 8-K and no large return signals informed accumulation and predicts drift.
- **Mechanism**: Informed trading leaks through volume before public news; attention (GKM) adds to it; the no-news filter removes the reversal-prone attention spikes.
- **Persistence**: Same as above; the filter is a variant proposed by practitioners rather than a published rule.
- **Rule (source's own)**: Variant of GKM: top-decile volume relative to 50-day reference, |return| below 1 sd, no earnings within +/-5 sessions, no 8-K that day -> long 20 sessions. **(no published number)**.
- **Evidence**: Indirect (GKM; the 8-K literature on pre-announcement volume). Must be treated as a hypothesis.
- **Sources**: GKM 2001; our own event store.
- **Horizon / schedule**: 20 sessions; `every_session`.
- **Data needed**: Volume, 8-K items, earnings dates — all have.
- **Individual fit**: Same as GKM. EOD-actionable: **Yes**.
- **Decoys / overlap**: high_volume_return_premium (it is a filter on it); options chain flow (dealers' hedging of block option trades creates volume).
- **Verdict**: Promising / Ready (file as a variant of high_volume_return_premium, not a separate edge).

### extreme_return_reversal — One-day extreme-return reversal (non-news)
- **Thesis**: Stocks with extreme one-day returns not explained by news reverse over the next 1-5 sessions; news-driven extremes drift.
- **Mechanism**: Liquidity provision: large uninformed order flow moves prices; liquidity providers are compensated by the reversal (Nagel, RFS 2012 "Evaporating Liquidity"; Da, Liu, Schaumburg, "A Closer Look at the Short-Term Return Reversal", MS 2014: the reversal is strongest in the component of returns not tied to cash-flow news). Tetlock (2010): no-news extreme returns reverse, news-driven ones do not.
- **Persistence**: It is a risk premium for liquidity provision; it grows when VIX is high and arbitrage capital is scarce; costs eat most of it for small accounts.
- **Rule (source's own)**: Monthly reversal (Jegadeesh 1990): long last month's losers / short winners, ~1-2%/month historically, much lower after 2000 in large caps; Da-Liu-Schaumburg: decompose into cash-flow news vs discount-rate component; the residual reverses. Daily version: bottom-decile 1-day return -> long next day.
- **Evidence**: Monthly reversal decayed post-2000 for large caps but remains in small caps and in high-VIX periods (Nagel 2012); daily reversal profits are almost entirely overnight (LPS 2019). Post-2020 evidence: not verified.
- **Sources**: Jegadeesh, JF 1990; Nagel, RFS 2012; Da, Liu, Schaumburg, Management Science 2014; Tetlock, "Does Public Financial News Resolve Asymmetric Information?", RFS 2010.
- **Horizon / schedule**: 1-20 sessions; `every_session`.
- **Data needed**: Bars, 8-K items, earnings dates, capped headlines (text-model seam to tag "news") — have.
- **Individual fit**: Costly (daily turnover); the long-only "buy no-news losers" leg is feasible with a small book; works best when VIX is high. EOD-actionable: **Yes** (MOC entry on day T or next open; LPS say the profit arrives overnight so MOC entry is the right form).
- **Decoys / overlap**: Bid-ask bounce (use midpoint / next-open entry); illiquidity; retail herding; gap-fill (intraday twin).
- **Verdict**: Promising / Ready (conditional on no-news filter and a VIX regime).

### fifty_two_week_high — 52-week-high proximity (George-Hwang)
- **Thesis**: Stocks near their 52-week high keep outperforming; nearness to the high predicts better than past returns and does not reverse long-term.
- **Mechanism**: Anchoring: investors treat the high as a ceiling and under-react to good news near it (George & Hwang, JF 2004); Hong, Jordan, Liu tie it to industry under-reaction.
- **Persistence**: Behavioural anchor; works in 17-18 of 20 international markets (Liu, Liu, Ma; Spina); but it is highly correlated with 12-1 momentum.
- **Rule (source's own)**: Ratio = price / 52-week high; long top 30% / short bottom 30%; 6-month hold; 1963-2001 ~0.45%/month after controlling for momentum **(from memory, not verified)**.
- **Evidence**: Broad international confirmation; index-level power weak; US post-2004 performance tracks momentum's (including the 2009 crash) **(not verified)**; Chen-Zimmermann replicate "52-week high" as a significant predictor **(not verified)**.
- **Sources**: George & Hwang, "The 52-Week High and Momentum Investing", JF 2004; Liu, Liu, Ma (2011) international; Quantpedia (https://quantpedia.com/strategies/52-weeks-high-effect-in-stocks); Griffith working paper on indexes (https://research-repository.griffith.edu.au/items/23ba37fb-49e1-4bad-9a77-eabd4bc7661d).
- **Horizon / schedule**: 120 sessions; `month_end`.
- **Data needed**: Have (a catalogue feature).
- **Individual fit**: Long-only, large capacity. EOD-actionable: **Yes**.
- **Decoys / overlap**: Filed 12-1 momentum (the main decoy); the harness must show incremental lift over momentum.
- **Verdict**: Promising / Ready as a *variant* of the filed momentum edge (anchoring flavour), not standalone.

### all_time_high_breakout — All-time-high / 52-week-high breakout continuation
- **Thesis**: A stock (or index) closing at a new all-time or 52-week high continues to outperform over the following weeks; "new highs are bullish".
- **Mechanism**: No overhead supply (every holder is in profit, so fewer sellers); anchoring under-reaction (as above); trend-following flows.
- **Persistence**: Behavioural; heavily used by practitioners (Clenow, Minervini, Weinstein) so the simple version is crowded.
- **Rule (source's own)**: Practitioner: buy the first close above the 52-week / all-time high; index-level studies (e.g., Allocate Smartly, Alpha Architect posts) show forward 12-month returns after an ATH are about the unconditional average **(not verified)**.
- **Evidence**: At the index level, forward returns after new highs ~ unconditional (Dead as an index timing signal); at the stock level, it is the 52-week-high effect with a breakout trigger (George-Hwang) plus momentum.
- **Sources**: George & Hwang 2004; Clenow, "Stocks on the Move" (2015); practitioner studies **(not verified)**.
- **Horizon / schedule**: 20-120 sessions; `every_session` trigger.
- **Data needed**: Have.
- **Individual fit**: Long-only, cheap. EOD-actionable: **Yes**.
- **Decoys / overlap**: Momentum, 52-week high.
- **Verdict**: Weak / Ready; fold into fifty_two_week_high.

### post_split_drift — Post-stock-split drift
- **Thesis**: Firms that announce a split outperform over the following year (under-reaction to the signal).
- **Mechanism**: Managers split when confident; the market under-reacts (Ikenberry, Rankine, Stice, JFQA 1996: 7.9% first-year, 12.2% three-year excess returns on 1,275 2-for-1 splits; Ikenberry & Ramnath 2002: ~9% first-year drift).
- **Persistence**: Weakened: Boehme & Danielsen (1950-2000) find the drift does not persist after the ex-date; Gharghori & Nguyen (1975-2011) not robust across sub-periods / size; Chan, Li, Lin: short-term and partly earnings-management driven. Splits became rare 2010-2019 and returned with mega-caps 2020-2024.
- **Rule (source's own)**: Long from the announcement (or ex-date) for 12 months; 2-for-1 or larger.
- **Evidence**: In-sample strong; later evidence weaker / conditional; no 2020s US replication found. Event count since 2010 is small for the S&P universe (~20-40 splits/yr, dropping to a handful some years).
- **Sources**: Ikenberry, Rankine, Stice 1996; Ikenberry & Ramnath, RFS 2002 (https://ideas.repec.org/a/oup/rfinst/v15y2002i2p489-526.html); Boehme & Danielsen, Financial Review 2007; survey (https://mpra.ub.uni-muenchen.de/53888/1/MPRA_paper_53888.pdf); Gharghori & Nguyen, JBF 2019 (https://ideas.repec.org/a/eee/jbfina/v101y2019icp136-146.html).
- **Horizon / schedule**: 250 sessions; `on_event:split_announcement` (we store splits, probably ex-dates; the announcement date is in the 8-K — have).
- **Data needed**: Splits — have; announcement dates via 8-K — have.
- **Individual fit**: Long-only, few events, large caps. EOD-actionable: **Yes**.
- **Decoys / overlap**: Momentum (splitters are winners); earnings quality.
- **Verdict**: Decayed / Ready but low priority (few events, momentum decoy).

### dividend_capture_and_month_premium — Dividend capture / dividend-month premium
- **Thesis**: Stocks earn abnormal returns in the month they are expected to pay a dividend (run-up into the ex-date), and the ex-day price drop is smaller than the dividend.
- **Mechanism**: Price pressure from dividend-seeking investors (income funds, retirees) buying before the ex-date, selling after (Hartzmark & Solomon, JFE 2013: +53 bp/month vs non-payers, +37 bp vs the same firms in non-dividend months, 1927-2009); ex-day drop < dividend from tax clienteles (Elton & Gruber 1970) and transaction costs.
- **Persistence**: Clientele demand is persistent; but the premium is small, the ex-day gap is mostly arbitraged in US large caps, and dividend-capture funds exist.
- **Rule (source's own)**: Predict the dividend month from last year's schedule (we have expected dividend dates); long predicted payers from month start to the ex-date, exit after; HS 2013 1927-2009.
- **Evidence**: US post-2013: no direct re-test found; Japan: no premium (1991-2014); Germany: robust; 11-market study mixed. Ex-day studies 2015-2024 are mostly non-US and show small positive capture returns.
- **Sources**: Hartzmark & Solomon, "The Dividend Month Premium", JFE 2013 (https://academicnewsletter.sufe.edu.cn/info/356769); Alpha Architect (https://alphaarchitect.com/2011/10/dividends-can-pay-without-paying); CXO (https://www.cxoadvisory.com/fundamental-valuation/dividend-month-premium); Alpha Architect on capture execution (https://alphaarchitect.com/dividend-capture-strategy-trade-execution-matters/).
- **Horizon / schedule**: 10-20 sessions; `on_event:expected_ex_dividend` (we store dividends and expected dates).
- **Data needed**: Have (dividends, ex-dates).
- **Individual fit**: Long-only; large caps; the gross premium (~40 bp/event) is close to round-trip costs; tax treatment (qualified dividends need a 61-day hold) matters for a taxable individual. EOD-actionable: **Yes**.
- **Decoys / overlap**: Low-vol / quality tilt of payers; TOM (payment dates cluster at month ends).
- **Verdict**: Weak / Ready; the ex-day capture itself is Decayed in US large caps.

### short_squeeze_days_to_cover — Short-interest squeeze / days-to-cover
- **Thesis**: High short interest with high days-to-cover and a positive catalyst produces forced covering and sharp upside; conversely high short interest predicts low returns on average.
- **Mechanism**: Shorts are constrained by borrow cost and recall risk; high days-to-cover means covering takes many sessions (Hong, Li, Ni, Scheinkman, Yan, "Days to Cover and Stock Returns", 2016); high short interest is informed and predicts negative returns (Boehmer, Huszar, Jordan 2010; Rapach, Ringgenberg, Zhou 2016 for the aggregate).
- **Persistence**: Real constraints on arbitrage; the squeeze side is a tail event.
- **Rule (source's own)**: Days-to-cover = short interest / avg volume; long low DTC / short high DTC: ~1.2%/month (Hong et al., 1988-2012) **(from memory, not verified)**.
- **Evidence**: Robust pre-2016; the 2021 meme squeezes show the tail; post-publication: the aggregate predictor (RRZ) weakened **(not verified)**.
- **Sources**: Hong, Li, Ni, Scheinkman, Yan, RFS 2016 **(not verified)**; Boehmer, Huszar, Jordan, JFE 2010; Rapach, Ringgenberg, Zhou, JFE 2016.
- **Horizon / schedule**: 20 sessions; bi-monthly (FINRA short-interest settlement dates).
- **Data needed**: Short interest — **missing** (FINRA publishes it twice a month with a ~9-day lag, free); borrow fees — missing. Options skew / put OI from our chains are weak proxies for short demand.
- **Individual fit**: Long-only "avoid high short interest" or "buy low DTC"; squeeze trading is a lottery. EOD-actionable: **Yes** once SI is stored (publication date is the knowledge date).
- **Decoys / overlap**: Lottery / high-IV; retail attention; momentum.
- **Verdict**: Promising / Needs data (FINRA short interest; cheap to add with correct `known_from`).

### circuit_breaker_price_limits — LULD halts and market-wide circuit breakers
- **Thesis**: Stocks that hit limit-up/limit-down halts show predictable continuation (magnet effect) or reversal afterwards.
- **Mechanism**: Halts truncate price discovery; literature (mostly China / Korea price limits) finds a magnet effect and delayed price discovery.
- **Persistence**: Structural but intraday.
- **Rule (source's own)**: Not applicable to US EOD; LULD halts are intraday events with 5-minute pauses; market-wide breakers triggered 4 times in March 2020 only.
- **Evidence**: US-specific EOD evidence: none meaningful.
- **Sources**: Chen, Gao, He, Jiang, Xiong, "Daily Price Limits and Destructive Market Behavior" (China), JoE 2019 **(not verified)**.
- **Horizon / schedule**: intraday.
- **Data needed**: Halt records — missing; intraday — missing.
- **Individual fit**: n/a. EOD-actionable: **No**.
- **Decoys / overlap**: Extreme-return reversal covers the EOD footprint.
- **Verdict**: Dead for our purposes / Out of scope.

### share_class_arbitrage — Dual-class share spread mean reversion
- **Thesis**: Price spreads between economically equivalent share classes (GOOG/GOOGL, BRK.A/B, FOX/FOXA, NWS/NWSA, LBTYA/K) mean-revert; buy the cheap class, short the rich one.
- **Mechanism**: Index inclusion differences, liquidity and voting premium produce temporary deviations; arbitrage is limited by borrow and the risk of a persistent voting-rights premium.
- **Persistence**: Few pairs (<15 liquid US pairs), small spreads (tens of bp), well-arbitraged by stat-arb desks.
- **Rule (source's own)**: z-score of the log price ratio vs its 60-day mean; enter at |z|>2, exit at 0 **(practitioner rule, no verified published number)**.
- **Evidence**: Practitioner; academic work on the voting premium (Zingales 1995) and on GOOG/GOOGL spread dynamics; returns small.
- **Sources**: Zingales, "What Determines the Value of Corporate Votes?", QJE 1995; practitioner blogs **(not verified)**.
- **Horizon / schedule**: 5-20 sessions; `every_session`.
- **Data needed**: Have (bars); a pairs table needs to be declared.
- **Individual fit**: Needs shorting; spreads below retail costs. EOD-actionable: **Yes**.
- **Decoys / overlap**: None.
- **Verdict**: Weak / Ready; too small for an individual; file only as a sanity benchmark for the harness.

### leveraged_etf_decay_pairs — Shorting both legs of leveraged ETF pairs (volatility decay)
- **Thesis**: Short both the 3x bull and 3x bear ETF on the same index; daily rebalancing makes both decay in a volatile sideways market.
- **Mechanism**: Daily compounding of leveraged returns produces a variance drag proportional to realised variance (Cheng & Madhavan 2009; Avellaneda & Zhang 2010).
- **Persistence**: Mathematical, but the gain is a short-volatility payoff: a trending market makes one leg explode; borrow fees on inverse/leveraged ETFs are high; margin on shorts of volatile ETFs is punitive.
- **Rule (source's own)**: Short equal dollar amounts of the +3x and −3x, rebalance to equal weights periodically; expected drift ~ (L^2 − L) sigma^2 / 2 per leg **(formula standard, published strategy returns not verified)**.
- **Evidence**: Well understood; returns after borrow (often 5-30% p.a. on inverse ETFs) and margin are marginal; the leveraged-ETF rebalancing edge was already **rejected** in this project.
- **Sources**: Cheng & Madhavan, "The Dynamics of Leveraged and Inverse ETFs", 2009; Avellaneda & Zhang, "Path-Dependence of Leveraged ETF Returns", SIAM JFM 2010.
- **Horizon / schedule**: months; `month_end`.
- **Data needed**: ProShares data — have.
- **Individual fit**: Needs shorting hard-to-borrow ETFs; margin heavy; our platform executes nothing. EOD-actionable: **Yes** but not suited.
- **Decoys / overlap**: It is short variance: compare with the filed volatility risk premium edge (same payoff, cleaner via options).
- **Verdict**: Weak / Out of scope (borrow + short volatility already filed as VRP).

### sector_etf_lead_lag — Sector / size ETF lead-lag and cross-asset lead-lag
- **Thesis**: Returns of large, liquid portfolios (large caps, leading sectors) lead those of small/illiquid ones by a few days (Lo & MacKinlay 1990); industry returns predict the market (Hong, Torous, Valkanov, JFE 2007).
- **Mechanism**: Gradual information diffusion across markets; limited attention to sector news by market-wide investors.
- **Persistence**: Lead-lag at the daily horizon has shrunk to near zero with ETF arbitrage (Hou 2007 finds within-industry lead-lag; later work finds the daily effects mostly gone post-2000) **(not verified)**; monthly industry->market predictability (HTV) weakened out-of-sample.
- **Rule (source's own)**: HTV: regress next-month market return on this month's industry returns (e.g., metals, petroleum, retail, financials); 1946-2002; 14 of 34 industries significant.
- **Evidence**: HTV in-sample; out-of-sample forecasts weak (Rapach et al. 2019 found some industry/commodity-sector leads persist for other countries) **(not verified)**.
- **Sources**: Lo & MacKinlay, RFS 1990; Hong, Torous, Valkanov, JFE 2007; Hou, RFS 2007.
- **Horizon / schedule**: 1-20 sessions; `every_session` / `month_end`.
- **Data needed**: Sector ETFs, cross-asset rollups — have.
- **Individual fit**: Index-level; cheap. EOD-actionable: **Yes**.
- **Decoys / overlap**: Market momentum; regime label (already have).
- **Verdict**: Weak / Ready (as a regime covariate at most).

### breadth_thrust — Market-wide breadth thrusts (Zweig, Whaley)
- **Thesis**: When the 10-day ratio of advancing to total issues jumps from below 40% to above 61.5% within 10 sessions (Zweig Breadth Thrust), forward 6-12 month index returns are strongly positive.
- **Mechanism**: A sudden broad buying wave after a washout signals a shift in risk appetite and institutional re-risking (a flow event); rare and noisy.
- **Persistence**: ~15-20 signals since 1950, so the evidence is anecdotal; the signal is a mechanical re-expression of "the market rallied hard after a decline", which is 12-month momentum of the index.
- **Rule (source's own)**: Zweig: 10-day EMA of advances/(advances+declines) from <0.40 to >0.615 within 10 days; buy and hold 6-12 months. Practitioner backtests report ~100% positive 12-month returns on historical signals **(hit rates from memory, not verified)**; 2023 and 2024 signals were positive.
- **Evidence**: Practitioner only (Zweig 1986; Whaley; Ned Davis); no peer-reviewed study; event count far below 40.
- **Sources**: Zweig, "Winning on Wall Street" (1986); practitioner backtests (Quantifiable Edges, Carson/Detrick) **(not verified)**.
- **Horizon / schedule**: 120-250 sessions; `on_event:breadth_thrust`.
- **Data needed**: Market breadth — have (advance/decline over our universe from daily bars).
- **Individual fit**: Trivial, long-only. EOD-actionable: **Yes**.
- **Decoys / overlap**: Index momentum / mean reversion after drawdowns; regime label.
- **Verdict**: Weak / Ready but fails the >=40-event bar; use as a regime feature, not an edge.

### etf_creation_redemption_arbitrage — ETF creation / redemption arbitrage
- **Thesis**: Capture the ETF-vs-basket spread by creating/redeeming.
- **Mechanism**: AP privilege.
- **Persistence**: n/a for individuals.
- **Rule / Evidence / Sources**: Only authorised participants can create/redeem; the retail-visible footprint is the premium/discount reversion above.
- **Verdict**: Out of scope (not accessible); see etf_premium_discount_reversion.

### index_option_expiry_pinning — Pinning to strikes at option expiry
- **Thesis**: Optionable stocks close near a strike on expiration Fridays more often than chance (Ni, Pearson, Poteshman, JFE 2005), and large indices pin to high-OI strikes.
- **Mechanism**: Delta-hedging by long-gamma dealers pushes the price toward the strike; manipulation by option writers.
- **Persistence**: Weekly options and 0DTE increased dealer gamma but also arbitrage; the pinning magnitude is a few tens of bp on one day.
- **Rule (source's own)**: NPP 2005: clustering of closing prices at strikes on expiration Fridays, 1996-2002; a trade would short straddles into the pin or fade moves away from the max-OI strike intraday.
- **Evidence**: Documented; subsequent work (Golez & Jackwerth 2012 for index futures) confirms; exploitable return for a next-day EOD trader: unclear, probably zero (the pin resolves at the close).
- **Sources**: Ni, Pearson, Poteshman, "Stock Price Clustering on Option Expiration Dates", JFE 2005; Golez & Jackwerth, JFE 2012.
- **Horizon / schedule**: 1 session (expiration Friday); `on_event:opex`.
- **Data needed**: OI by strike — have (OI walls); intraday — missing.
- **Individual fit**: An options trade (sell the expiring straddle at the max-OI strike on Thursday close) is EOD-placeable; the stock version is intraday. EOD-actionable: **Partial** (options variant only; overlaps the filed VRP).
- **Decoys / overlap**: Filed volatility risk premium (short gamma into expiry is just VRP at the shortest horizon).
- **Verdict**: Weak / Ready as a VRP variant (expiry-week short straddle at the OI wall); not a stock edge.

---

## Rejected on sight
- **Leveraged-ETF rebalancing flow at the close** — already rejected (intraday, weak after costs); the pairs-decay variant above is short volatility with borrow drag.
- **ETF creation/redemption arbitrage** — AP-only; not accessible.
- **Market-wide circuit breakers / LULD halts** — intraday events, four market-wide triggers in history.
- **Index-level all-time-high timing** — forward returns after an ATH ~ unconditional; it is index momentum.
- **Monday effect (index)** — insignificant since the mid-1990s (Morey & Rosenberg).
- **Pre-FOMC drift as a standalone** — vanished after 2015 (Kurov, Wolfe, Gilbert 2021); only a high-uncertainty conditional variant is worth one look.
- **Pre-holiday effect** — one noisy day a few times a year, decayed; test once inside the TOM study then drop.
- **Halloween / sell-in-May and breadth thrusts as edges** — two or fewer events per year; cannot reach 40 independent events; keep as regime covariates.
- **Gap-fill day trading** — needs the open price and an intraday exit; not EOD-actionable.
- **Intraday momentum (last half-hour) and MOC-imbalance trading** — no intraday bars; the signal and the trade are both intraday.
- **Share-class spread arbitrage** — spreads below retail costs, <15 pairs, needs shorting.
- **Dividend capture around the ex-day in US large caps** — the ex-day drop ~ dividend after taxes and costs; the dividend-month run-up is the only part worth a test and it is small.
- **Russell reconstitution** — already blocked (no membership data).
- **S&P 500 additions** — already rejected (<1% since 2010).
- **Meme-stock long momentum (ride the herd)** — the documented effect is *negative* 5-20 day returns after herding (Barber et al.); the long side is a lottery with no positive published expectation.
- **Stock-level "ATH breakout" as separate from the 52-week-high effect** — same anchor, same momentum decoy; folded in.
- **Post-split drift as a standalone** — a handful of events per year in our universe, momentum decoy, weakened after the 1990s.
