# Edge idea catalogue

On 2026-10-17 we ran a deep-research pass over the academic literature (JF, JFE, RFS, JFQA,
RAPS, NBER, SSRN, the replication studies), practitioner research (AQR, Alpha Architect, Quantpedia,
Robeco, Research Affiliates, Man, Cboe) and the standard books (Pedersen, Ilmanen, Chan,
Clenow, Antonacci, Carver, Lopez de Prado, Sinclair). It produced **about 300 graded ideas** across
nine families. These are **ideas, not edges**: none is filed in `config/site/edges/` or tested. An
idea becomes an edge document when it is picked up and answers the nine-point quality bar in
[edges-plan.md](../edges-plan.md). The harness then judges it. A verdict in this catalogue is
only the published evidence.

| Family | Page | Ideas |
| --- | --- | --- |
| A. Cross-sectional factors and anomalies | [cross-sectional.md](cross-sectional.md) | 31 |
| B. Earnings, analyst and corporate events | [events.md](events.md) | 36 |
| C. Options signals and volatility trading | [options-volatility.md](options-volatility.md) | 31 |
| D. Calendar, forced flows, EOD microstructure | [calendar-flows.md](calendar-flows.md) | 36 |
| E. Trend, macro and cross-asset (ETFs) | [trend-macro.md](trend-macro.md) | 30 |
| F. Alternative data, text, LLM and ML | [altdata-text-ml.md](altdata-text-ml.md) | 31 |
| G. Stat arb, relative value, technical setups | [statarb-technical.md](statarb-technical.md) | 36 |
| H. Structural niches and other asset classes | [structural-niches.md](structural-niches.md) | 33 |
| I. Frontier sweep (2023-2026 research) | [frontier.md](frontier.md) | 33 |

Each idea has the same fields: thesis, mechanism, persistence, the source's own rule, evidence
(the published number, then post-publication and recent evidence), sources, horizon and schedule,
the data needed (mapped to our store), fit for an individual, decoys and overlap, and a verdict
(Strong / Promising / Weak / Decayed / Dead; Ready / Needs data / Out of scope). Each family page
ends with a "Rejected on sight" list.

**Verification.** The agents shared one web-search quota, and it ran out partway through. Each page
marks figures recalled from memory (*not verified*, *nv*, *recalled*, *from memory*). Before an
edge document cites a number, check it against the source. That check is quality bar item 5.
A second pass on 2026-10-17 checked every marked figure in the pickup-order and Strong ideas
against its source and replaced the marker with *(verified)*, the corrected number
*(corrected; was ...)*, or *(figure dropped: ...)* where the source states no number. Each of
those ideas' Sources line gives author, year, venue and URL. Markers remain on the other ideas.

## Pickup order (Ready now, strongest first; duplicates across families merged)

Each idea below is Strong or Promising and needs only data we already store. A variant
of a filed edge is filed as `[[variants]]` or a new screener under that edge, not as a new edge.

| # | Idea (families) | Why first | Source |
| --- | --- | --- | --- |
| 1 | `earnings_date_shift` (B, I) | A company that moves its report earlier signals good news; a delay signals bad news. We store both expected and confirmed dates. Before filing, confirm when each date notice became known (`known_from`). | Johnson and So 2018 |
| 2 | `net_share_issuance` (A, B, H) | Net issuance predicts low returns and net buybacks high returns. It runs on shares outstanding from SEC data, is slow-moving (cheap to trade) and is one of the most robust anomalies after costs. One edge; the variants are issuance and buyback. | Pontiff and Woodgate 2008; Daniel and Titman 2006 |
| 3 | `c12_vrp_cross_section_iv_hv` (C) | Rank names by implied minus historical vol (per-name VRP), not only by IV level. A variant or new screener of `vrp_short_premium`. | Goyal and Saretto 2009 |
| 4 | `composite_mispricing_score` (F) | Combine about 11 anomalies into one rank. It survives in replication. It also becomes the decoy benchmark every other cross-sectional edge has to beat. | Stambaugh, Yu and Yuan 2015 |
| 5 | `residual_momentum`, `volatility_scaled_momentum`, `momentum_x_quality_interaction` (A) | Three variants of `momentum_12_1` that cut momentum's crash risk and roughly double its Sharpe in the literature. | Blitz, Huij and Martens 2011; Barroso and Santa-Clara 2015 |
| 6 | `cash_based_operating_profitability`, `quality_minus_junk` (A) | Quality as a slow tilt. Built from SEC financials, with the filing acceptance timestamp as `knowledge_ts`. | Ball et al. 2016; Asness, Frazzini and Pedersen 2019 |
| 7 | `eight_k_item_event_drift` (B, F) | Prices keep drifting after 8-K items such as 4.02 non-reliance, auditor changes and executive departures. We already store the 8-K items. | per-item studies in [events.md](events.md) |
| 8 | `c01_call_put_iv_spread`, `c02_iv_smirk_skew`, `pre_earnings_cp_iv_spread` (C, I) | Option prices predicting the stock. Our chain data sets us apart here: few retail platforms compute these signals. | Cremers and Weinbaum 2010; Xing, Zhang and Zhao 2010 |
| 9 | `high_volume_return_premium`, `volume_shock_with_no_news` (D, G) | Unusually high volume with no news predicts a positive drift. Uses bars only, plus our event classes for the no-news filter (ADR 0050). | Gervais, Kaniel and Mingelgrin 2001 |
| 10 | `c16_pre_earnings_straddle_buy` (C) | Buy straddles a few days before earnings. Implied vol rises into the report, which runs opposite to the IV-crush trade. | Gao, Xing and Zhang 2018 |
| 11 | `earnings_neutral_reversal` (G) | Short-term reversal is stronger just before earnings. | So and Wang 2014 |
| 12 | `quarter_end_rebalancing`, `pension_quarter_end_rebalancing` (D, I) | Predictable 60/40 rebalancing flows at month and quarter end. | Harvey, Mazzoleni and Melone 2025 (NBER w33554) |
| 13 | `dual_class_spread_reversion` (H) | Two share classes with the same cash flows; the spread between them mean-reverts. Capacity is tiny, which suits an individual. | Schultz and Shive 2010 |
| 14 | `sp500_deletions_long` (B) | The other side of the rejected additions edge: deletions rebound. | Research Affiliates |
| 15 | `dividend_month_premium` (B) | Stocks earn more in months when a dividend is expected. We store the dividend schedule. | Hartzmark and Solomon 2013 |
| 16 | `beta_anomaly_after_uptrend` (I) | The low-beta premium, only after a 24-month market uptrend. Conditioned on our regime label. | Lee and Linn 2024 |
| 17 | `turn_of_the_month` (D) | The equity premium concentrates in the turn of the month. Needs the Tiingo history for statistical power. | Etula et al. 2020 (RFS) |
| 18 | `bdc_price_to_nav_reversion` (H) | Business development company (BDC) prices revert to NAV, and NAV can be read from the XBRL we already store. | [structural-niches.md](structural-niches.md) |
| 19 | `new_thematic_etf_fade` (H) | Newly launched thematic ETFs lag after launch. Use it as an avoid filter. | Ben-David et al. 2023 (RFS) |
| 20 | `option_expiration_week` (D) | Large caps earn a premium in option expiration week. Our OI data allows a variant nobody has published. | Stivers and Sun 2013 |

## Data that would unlock the most ideas

| Data | Ideas it unblocks | Cost and notes |
| --- | --- | --- |
| Tiingo history from 2010, delisted names included (the ED6 work) | about 21, including every trend and asset-allocation idea (`tsmom_multi_asset_etf`, Strong), the 52-week-high breakouts, turn of the month, and the avoid-list legs, which survivorship otherwise overstates | Already bought (Tiingo Power). The biggest single unlock. |
| Form 4 insider filings (EDGAR XML) | `insider_opportunistic_cluster_buys`: Strong, about 82 bp a month in the original | Cheap: public EDGAR, one new source |
| 10-K and 10-Q full text | `lazy_prices_10k_change` (Strong historically), `tnic_text_peer_momentum`, risk-factor changes, MD&A tone, conglomerate lead-lag | EDGAR; similarity and LLM scoring through the text-model seam |
| VIX futures and term-structure indices, futures curves | short-VIX roll yield, `trend_carry_value_combo` (Strong gross), commodity carry | Cboe and IBKR |
| Closed-end fund NAVs (N-PORT or CEFConnect) | `cef_discount_reversion` (Strong), muni CEF in December, CEF activism | A daily NAV source |
| ETF shares outstanding history, short interest (FINRA), point-in-time analyst history | ETF flow pressure, days-to-cover, analyst revision momentum | Each a small source |

## Rules for the harness that came out of the research

- **Haircut**: file a published US anomaly's expected size at about 50% of its in-sample number,
  and at about a third for the long-only leg. Most anomaly return sits in the short leg
  (McLean and Pontiff 2016; Chen and Zimmermann 2020). The median anomaly nets only a few
  basis points a month after 2000–2005 (Chen and Velikov 2023; Chen and Welch 2026).
- **Bar for a new signal**: t > 3, not 2 (Harvey, Liu and Zhu 2016), with the deflated Sharpe and
  probability of overfitting (PBO) we already report, and at least 40 independent events.
- **Decoy battery**: size, 12-1 momentum, idiosyncratic vol / MAX, Amihud illiquidity, beta,
  sector, and `composite_mispricing_score` once it exists.
- **Point-in-time fundamentals**: `knowledge_ts` is the SEC acceptance timestamp, never the fiscal
  period end plus a lag.
- **Trend and asset-allocation edges**: test them as an ensemble of parameter choices, never as
  one tuned rule. Expect a 40–50% out-of-sample Sharpe haircut.
- **Costs**: prefer slow signals (quarterly or annual, with buy/hold bands). Daily text and attention
  signals are classifiers inside events, not strategies (Novy-Marx and Velikov 2016).
- **Crowding**: a signal sold in a vendor product is assumed harvested in the Russell 1000. Test it in
  small and mid caps first.

## Dead ends (do not re-file; the full lists are on each family page)

Large-cap PEAD; accruals; the Piotroski F-score after 2000; Amihud illiquidity; raw size; raw
1-month reversal after costs; stock-split drift; same-month seasonality; recommendation drift
after 2003; buyback-announcement drift; ex-dividend capture; the Friday-burying effect; pre-FOMC drift
after 2015; Monday, pre-holiday and Halloween effects; intraday momentum, gap fills and pinning (not
tradable from EOD data); max-pain targeting; tail hedging as alpha; covered calls as "income"; the
public put/call ratio; Fed net liquidity; the copper/gold ratio; CAPE or curve inversion as standalone
timing; sector-ETF momentum; distance-method pairs and PCA stat arb for an individual;
candlesticks, moving-average crossovers and chart patterns; customer-supplier momentum; copying
Congress members' trades; the LLM headline strategy (decaying as it is adopted); alternative-data
panels such as satellite, card and app data (out of reach for an individual).

## Full index

Sorted by evidence, then by whether the data is ready. Ideas filed under two families appear twice.
The merged entry is in the pickup order above.

| Idea | Name | Family | Evidence | Data |
| --- | --- | --- | --- | --- |
| `volatility_scaled_momentum` | Risk-managed / crash-managed 12-1 momentum (variant of filed 12-1) | [A](cross-sectional.md) | Strong | Ready |
| `residual_momentum` | Idiosyncratic (factor-residual) momentum | [A](cross-sectional.md) | Strong | Ready |
| `quality_minus_junk` | Composite quality (profitability + growth + safety) as a characteristic | [A](cross-sectional.md) | Strong | Ready |
| `net_share_issuance` | Net share issuance / buyback characteristic | [A](cross-sectional.md) | Strong | Ready |
| `momentum_x_quality_interaction` | Quality-conditioned momentum / momentum-conditioned value | [A](cross-sectional.md) | Strong | Ready |
| `earnings_date_advance_delay` | Earnings-date advances vs delays (Johnson & So) | [B](events.md) | Strong | Ready |
| `net_share_count_change` | Net share issuance / net buyback yield (actual repurchases, not announcements) | [B](events.md) | Strong | Ready |
| `c12_vrp_cross_section_iv_hv` | Per-name VRP ranking: IV−HV straddles / delta-hedged options (Goyal-Saretto) | [C](options-volatility.md) | Strong | Ready |
| `taa_ensemble_and_overfitting_guard` | What is known about overfitting in TAA backtests (the meta-edge: ensembles beat the best single rule) | [E](trend-macro.md) | Strong | Ready |
| `eight_k_item_event_drift` | Item-coded 8-K drift (restatements, auditor changes, exec departures, impairments) | [F](altdata-text-ml.md) | Strong | Ready |
| `composite_mispricing_score` | Anomaly combination (Stambaugh-Yu-Yuan) | [F](altdata-text-ml.md) | Strong | Ready |
| `dual_class_spread_reversion` | Same-cash-flow dual-class share spread | [H](structural-niches.md) | Strong | Ready |
| `share_issuance_dilution_drift` | Net share issuance (ATM/secondaries) predicts negative returns [adjacent] | [H](structural-niches.md) | Strong | Ready |
| `earnings_date_shift` | Earnings-date advance / delay signal | [I](frontier.md) | Strong | Ready |
| `cash_based_operating_profitability` | Cash-based operating profitability (Ball-Gerakos-Linnainmaa-Nikolaev) | [A](cross-sectional.md) | Strong | Needs data |
| `insider_opportunistic_cluster_buys` | Opportunistic / clustered insider purchases (Form 4) | [B](events.md) | Strong | Needs data |
| `tsmom_multi_asset_etf` | Time-series momentum across asset classes (trend following) in ETFs | [E](trend-macro.md) | Strong | Needs data |
| `trend_carry_value_combo` | Trend + carry + value across asset classes (the diversified "alternative risk premia" book) | [E](trend-macro.md) | Strong | Needs data |
| `lazy_prices_10k_change` | Filing-text change ("Lazy Prices") | [F](altdata-text-ml.md) | Strong | Needs data |
| `conglomerate_pseudo_lead_lag` | Complicated firms (Cohen-Lou 2012) | [F](altdata-text-ml.md) | Strong | Needs data |
| `shared_analyst_coverage_momentum` | Connected-firm momentum via shared analysts | [F](altdata-text-ml.md) | Strong | Out of scope |
| `llm_news_embeddings_expected_returns` | Chen-Kelly-Xiu | [F](altdata-text-ml.md) | Strong | Out of scope |
| `cef_discount_reversion` | Closed-end fund discount mean reversion (with the December/January kicker) | [H](structural-niches.md) | Strong | Needs data |
| `odd_lot_tender_priority` | Odd-lot priority in oversubscribed tenders | [H](structural-niches.md) | Strong | Needs data |
| `new_thematic_etf_fade` | New specialized/thematic ETFs underperform after launch | [H](structural-niches.md) | Strong | Needs data |
| `frog_in_the_pan` | Information discreteness (continuous-information momentum) | [A](cross-sectional.md) | Promising | Ready |
| `intangibles_adjusted_value` | Value with capitalised intangibles (iHML / intangible value) | [A](cross-sectional.md) | Promising | Ready |
| `asset_growth` | Investment / asset growth anomaly | [A](cross-sectional.md) | Promising | Ready |
| `industry_momentum` | Industry / sector momentum | [A](cross-sectional.md) | Promising | Ready |
| `fifty_two_week_high` | Nearness to the 52-week high | [A](cross-sectional.md) | Promising | Ready |
| `stock_time_series_momentum` | Time-series (absolute) momentum on single stocks | [A](cross-sectional.md) | Promising | Ready |
| `idiosyncratic_volatility_and_max` | IVOL puzzle and MAX (lottery) stocks (short leg: avoid-list) | [A](cross-sectional.md) | Promising | Ready |
| `betting_against_beta_low_vol` | Low beta / low volatility | [A](cross-sectional.md) | Promising | Ready |
| `short_term_residual_reversal` | 1-month (residual) reversal | [A](cross-sectional.md) | Promising | Ready |
| `short_term_momentum_high_turnover` | Medhat-Schmeling short-term momentum in liquid names | [A](cross-sectional.md) | Promising | Ready |
| `distress_failure_probability` | Financial distress / failure probability (short-leg avoid-list) | [A](cross-sectional.md) | Promising | Ready |
| `rd_intensity` | R&D-to-market (and R&D growth) as a characteristic | [A](cross-sectional.md) | Promising | Ready |
| `composite_value` | Classic multi-metric value (B/M, E/P, CF/P, EV/EBITDA, S/P) | [A](cross-sectional.md) | Promising | Ready |
| `sp500_deletions_long` | Buy S&P 500 deletions (demotions), fade additions | [B](events.md) | Promising | Ready |
| `dividend_month_premium` | Dividend-month premium (Hartzmark & Solomon) | [B](events.md) | Promising | Ready |
| `pre_earnings_runup_winners` | Pre-earnings run-up in past winners (attention) and the post-announcement give-back | [B](events.md) | Promising | Ready |
| `late_filer_nt_drift` | NT 10-K / NT 10-Q late-filing notices (negative drift) | [B](events.md) | Promising | Ready |
| `c01_call_put_iv_spread` | Call-put implied volatility spread (put-call parity deviation) | [C](options-volatility.md) | Promising | Ready |
| `c02_iv_smirk_skew` | Individual option volatility smirk (OTM put IV − ATM call IV) | [C](options-volatility.md) | Promising | Ready |
| `c03_iv_change_call_put` | Changes in call and put implied volatility (An-Ang-Bali-Cakici) | [C](options-volatility.md) | Promising | Ready |
| `c04_option_stock_volume_ratio` | O/S option-to-stock volume ratio | [C](options-volatility.md) | Promising | Ready |
| `c13_iv_term_structure_straddles` | IV term-structure slope predicts straddle returns (Vasquez) | [C](options-volatility.md) | Promising | Ready |
| `c14_delta_hedged_characteristics` | Delta-hedged option returns predicted by stock characteristics (Zhan-Han-Cao-Tong; Cao-Han) | [C](options-volatility.md) | Promising | Ready |
| `c16_pre_earnings_straddle_buy` | Buy ATM straddles 3 days before earnings (Gao-Xing-Zhang) | [C](options-volatility.md) | Promising | Ready |
| `c17_earnings_iv_crush_sell` | Sell the earnings move (IV crush) in large liquid names | [C](options-volatility.md) | Promising | Ready |
| `c18_iv_rank_conditional_selling` | IV-rank / IV-percentile conditional premium selling | [C](options-volatility.md) | Promising | Ready |
| `c19_index_put_write` | Index put-writing / covered-call (PUT, BXM, WPUT) as a return source | [C](options-volatility.md) | Promising | Ready |
| `c26_weekend_nontrading_option_mispricing` | Option over-pricing across weekends / holidays (Jones-Shemesh) | [C](options-volatility.md) | Promising | Ready |
| `c31_lottery_options_short` | Short OTM calls on lottery-like stocks (Boyer-Vorkink) | [C](options-volatility.md) | Promising | Ready |
| `quarter_end_rebalancing` | Predictable 60/40 rebalancing flow at month / quarter end | [D](calendar-flows.md) | Promising | Ready |
| `option_expiration_week` | Option-expiration week premium (large caps) | [D](calendar-flows.md) | Promising | Ready |
| `overnight_vs_intraday_tug_of_war` | Overnight premium and session-split anomaly returns | [D](calendar-flows.md) | Promising | Ready |
| `december_losers_reversal` | Tax-loss-selling reversal of December losers | [D](calendar-flows.md) | Promising | Ready |
| `high_volume_return_premium` | High-volume return premium (Gervais-Kaniel-Mingelgrin) | [D](calendar-flows.md) | Promising | Ready |
| `volume_shock_with_no_news` | Volume shock without an identifiable event | [D](calendar-flows.md) | Promising | Ready |
| `extreme_return_reversal` | One-day extreme-return reversal (non-news) | [D](calendar-flows.md) | Promising | Ready |
| `fifty_two_week_high` | 52-week-high proximity (George-Hwang) | [D](calendar-flows.md) | Promising | Ready |
| `sma10_timing_faber` | Faber 10-month SMA timing (GTAA) | [E](trend-macro.md) | Promising | Ready |
| `dual_momentum_gem` | Antonacci Global Equities Momentum (relative + absolute) | [E](trend-macro.md) | Promising | Ready |
| `taa_keller_vaa_daa` | Keller's Vigilant / Defensive Asset Allocation (breadth momentum + canary) | [E](trend-macro.md) | Promising | Ready |
| `credit_spread_trend` | HY vs IG / Treasuries timing by spread trend | [E](trend-macro.md) | Promising | Ready |
| `bond_curve_timing` | Duration timing from term spread / curve steepness and carry+roll | [E](trend-macro.md) | Promising | Ready |
| `vol_managed_equity` | Volatility-managed / volatility-targeted equity exposure | [E](trend-macro.md) | Promising | Ready |
| `country_momentum_etf` | Country ETF momentum (relative + absolute) | [E](trend-macro.md) | Promising | Ready |
| `macro_regime_conditioner` | Macro-regime gating of risk (our regime label; NFCI / FCI / EBP / Sahm) | [E](trend-macro.md) | Promising | Ready |
| `cross_asset_tsmom_bonds_to_equities` | Bond returns lead equity returns (cross-asset time-series momentum) | [E](trend-macro.md) | Promising | Ready |
| `dollar_regime_tilt` | Dollar strength regime for EM / commodities / foreign equities | [E](trend-macro.md) | Promising | Ready |
| `residual_reversal_sector_neutral` | Short-term residual reversal (large caps, industry- and factor-neutral) | [G](statarb-technical.md) | Promising | Ready |
| `earnings_neutral_reversal` | Pre-earnings reversal (So & Wang) | [G](statarb-technical.md) | Promising | Ready |
| `high_volume_return_premium` | Volume shock premium (Gervais-Kaniel-Mingelgrin) | [G](statarb-technical.md) | Promising | Ready |
| `episodic_pivot_gap_volume` | Qullamaggie "episodic pivot" (big gap on news + volume, after a dormant base) | [G](statarb-technical.md) | Promising | Ready |
| `ibs_etf_mean_reversion` | Internal Bar Strength on equity index ETFs | [G](statarb-technical.md) | Promising | Ready |
| `oversold_in_uptrend_pullback` | Pullback to the 20/50-day in a strong trend (single stocks) | [G](statarb-technical.md) | Promising | Ready |
| `volatility_contraction_expansion` | NR7 / Bollinger squeeze / tight range then breakout | [G](statarb-technical.md) | Promising | Ready |
| `volume_price_confirmation_obv_cmf` | OBV / accumulation-distribution / CMF confirmation | [G](statarb-technical.md) | Promising | Ready |
| `industry_relative_mean_reversion_monthly` | Intra-industry reversal and inter-industry momentum (Hameed & Mian) | [G](statarb-technical.md) | Promising | Ready |
| `ipo_lockup_expiry_pressure` | IPO lockup expiration | [H](structural-niches.md) | Promising | Ready |
| `treasury_month_end_extension` | Month-end Treasury index duration extension and the "dash for cash" | [H](structural-niches.md) | Promising | Ready |
| `retail_lottery_option_flow` | Retail lottery-option buying predicts negative stock and option returns | [H](structural-niches.md) | Promising | Ready |
| `fx_etf_carry_momentum` | G10 FX carry and momentum via currency ETFs | [H](structural-niches.md) | Promising | Ready |
| `reverse_split_distress_filter` | Reverse splits and the Nasdaq penny-delisting cycle | [H](structural-niches.md) | Promising | Ready |
| `mining_equity_beta_fade` | Bitcoin miners vs BTC (short miners / long IBIT) | [H](structural-niches.md) | Promising | Ready |
| `muni_cef_december` | Muni CEF December discount widening (variant of cef_discount_reversion) | [H](structural-niches.md) | Promising | Ready |
| `beta_anomaly_after_uptrend` | Low-risk anomaly conditional on 24-month market trend | [I](frontier.md) | Promising | Ready |
| `pre_earnings_cp_iv_spread` | Call-put IV spread and chain flow into earnings | [I](frontier.md) | Promising | Ready |
| `odte_gamma_vol_regime` | 0DTE / short-dated OI gamma as a realised-vol dampener | [I](frontier.md) | Promising | Ready |
| `pension_quarter_end_rebalancing` | Conditional quarter-end rebalancing pressure | [I](frontier.md) | Promising | Ready |
| `vol_control_deleveraging_proxy` | Estimated vol-target fund de/re-leveraging | [I](frontier.md) | Promising | Ready |
| `passive_share_reconstitution_volume` | Stock-level passive share from reconstitution-day volume | [I](frontier.md) | Promising | Ready |
| `retail_options_lottery_share` | Retail option-demand share from chain data | [I](frontier.md) | Promising | Ready |
| `dealer_gamma_regime` | Aggregate dealer gamma (GEX) as a vol/return-pattern regime | [I](frontier.md) | Promising | Ready |
| `factor_momentum` | Momentum in factor (characteristic-portfolio) returns | [A](cross-sectional.md) | Promising | Needs data |
| `analyst_coverage_conditioned_momentum` | Low analyst coverage amplifies momentum (Hong-Lim-Stein) | [A](cross-sectional.md) | Promising | Needs data |
| `customer_supplier_momentum` | Economic-link lead-lag (customer momentum) | [A](cross-sectional.md) | Promising | Needs data |
| `double_surprise_pead_small` | Double surprise (earnings AND revenue beat) small-cap drift | [B](events.md) | Promising | Needs data |
| `eight_k_item_drift` | Drift after specific 8-K items (4.02 non-reliance, 4.01 auditor change, 5.02 forced CEO exit, 1.01 material agreement) | [B](events.md) | Promising | Needs data |
| `analyst_revision_momentum` | Earnings-estimate revision momentum (and revision breadth) | [B](events.md) | Promising | Needs data |
| `target_price_implied_return` | Analyst target-price implied return, within industry | [B](events.md) | Promising | Needs data |
| `guidance_change_drift` | Management guidance changes (raise / cut), bundled with earnings | [B](events.md) | Promising | Needs data |
| `call_tone_change_drift` | Earnings-call tone and tone *change* | [B](events.md) | Promising | Needs data |
| `activist_13d_drift` | Activist Schedule 13D filings | [B](events.md) | Promising | Needs data |
| `merger_arb_cash_deals` | Merger arbitrage spreads on announced cash deals | [B](events.md) | Promising | Needs data |
| `spinoff_parent_and_spinco` | Spin-offs: spinco and parent after the distribution | [B](events.md) | Promising | Needs data |
| `ipo_lockup_expiry` | IPO lockup expiration (short / avoid; re-entry after) | [B](events.md) | Promising | Needs data |
| `c20_short_vix_roll_yield` | VIX futures contango roll yield / short VIX ETPs with a term-structure filter | [C](options-volatility.md) | Promising | Needs data |
| `c22_dispersion_trade` | Dispersion: short index vol, long single-name vol (implied correlation premium) | [C](options-volatility.md) | Promising | Out of scope |
| `c28_zero_dte_premium` | 0DTE SPX option selling | [C](options-volatility.md) | Promising | Out of scope |
| `turn_of_the_month` | Turn-of-the-month equity premium | [D](calendar-flows.md) | Promising | Needs data |
| `intraday_momentum_last_half_hour` | Market intraday momentum (first half-hour predicts last half-hour) | [D](calendar-flows.md) | Promising | Out of scope |
| `flow_induced_trading_lou` | Mutual-fund flow-induced price pressure (Lou 2012) | [D](calendar-flows.md) | Promising | Needs data |
| `etf_flows_to_underlying` | ETF flow pressure on constituents and its reversal | [D](calendar-flows.md) | Promising | Needs data |
| `etf_premium_discount_reversion` | ETF premium / discount mean reversion | [D](calendar-flows.md) | Promising | Needs data |
| `closed_end_fund_discounts` | CEF discount mean reversion and activism | [D](calendar-flows.md) | Promising | Needs data |
| `retail_attention_herding` | Retail attention and Robinhood-style herding (contrarian) | [D](calendar-flows.md) | Promising | Needs data |
| `short_squeeze_days_to_cover` | Short-interest squeeze / days-to-cover | [D](calendar-flows.md) | Promising | Needs data |
| `absolute_momentum_crash_filter` | Absolute (12-month) momentum as an exit rule on core holdings | [E](trend-macro.md) | Promising | Needs data |
| `carry_multi_asset_etf` | Carry across asset classes via ETFs | [E](trend-macro.md) | Promising | Out of scope |
| `commodity_term_structure_roll` | Commodity basis / roll yield (backwardation long, contango avoid) | [E](trend-macro.md) | Promising | Needs data |
| `commodity_momentum_etf` | Commodity cross-sectional and time-series momentum | [E](trend-macro.md) | Promising | Needs data |
| `vix_mean_reversion_entry` | VIX spike / IV term-structure inversion as an equity entry | [E](trend-macro.md) | Promising | Needs data |
| `betting_against_correlation_etf` | Betting against correlation / low-risk via ETFs | [E](trend-macro.md) | Promising | Out of scope |
| `stock_bond_correlation_regime` | Inflation regime / stock-bond correlation as a hedging and sizing switch | [E](trend-macro.md) | Promising | Out of scope |
| `risk_factor_section_change` | Item 1A risk-factor additions | [F](altdata-text-ml.md) | Promising | Needs data |
| `tnic_text_peer_momentum` | Text-based (10-K product description) peer momentum | [F](altdata-text-ml.md) | Promising | Needs data |
| `customer_supplier_momentum` | Economic links (Cohen-Frazzini 2008) and the 10-K "principal customer" variant | [F](altdata-text-ml.md) | Promising | Needs data |
| `sec_comment_letters` | SEC review comment letters as a negative screen | [F](altdata-text-ml.md) | Promising | Needs data |
| `technology_links_momentum` | Patent-class proximity momentum | [F](altdata-text-ml.md) | Promising | Needs data |
| `earnings_call_qa_evasiveness` | Management non-answers / low question-answer similarity | [F](altdata-text-ml.md) | Promising | Needs data |
| `innovative_efficiency_patents` | Patents / citations per R&D dollar | [F](altdata-text-ml.md) | Promising | Needs data |
| `ml_cross_sectional_scorer` | Gu-Kelly-Xiu-style ML over firm characteristics | [F](altdata-text-ml.md) | Promising | Needs data |
| `short_seller_report_drift` | Activist short reports | [F](altdata-text-ml.md) | Promising | Needs data |
| `employee_reviews_glassdoor` | Crowdsourced employer ratings | [F](altdata-text-ml.md) | Promising | Out of scope |
| `web_traffic_app_downloads` | Similarweb traffic, app downloads | [F](altdata-text-ml.md) | Promising | Out of scope |
| `large_move_news_vs_no_news` | Reversal after large moves without news, continuation with news | [G](statarb-technical.md) | Promising | Needs data |
| `trend_factor_ma_cross_section` | Han-Zhou-Zhu trend factor (cross-sectional MA signals) | [G](statarb-technical.md) | Promising | Needs data |
| `breakout_52w_high_trend_following` | Buy new 52-week / all-time highs with an ATR trailing stop (Wilcox-Crittenden) | [G](statarb-technical.md) | Promising | Needs data |
| `etf_flow_reversal_constituents` | ETF non-fundamental demand predicts reversal in its holdings | [G](statarb-technical.md) | Promising | Needs data |
| `anchored_vwap_reversion_retest` | Anchored VWAP from earnings / swing points as a level | [G](statarb-technical.md) | Promising | Needs data |
| `bdc_price_to_nav_reversion` | BDC price/NAV mean reversion (NAV from XBRL) | [H](structural-niches.md) | Promising | Needs data |
| `cef_distribution_trap_premium_collapse` | Premium CEFs that over-distribute (short / avoid) | [H](structural-niches.md) | Promising | Needs data |
| `cef_activist_target_prediction` | Front-running CEF activism (13D-able discounts) | [H](structural-niches.md) | Promising | Needs data |
| `tender_offer_post_expiry_drift` | Fixed-price and Dutch-auction self-tender drift | [H](structural-niches.md) | Promising | Needs data |
| `spinoff_post_distribution_drift` | Spin-offs after the forced-selling window | [H](structural-niches.md) | Promising | Needs data |
| `treasury_auction_cycle` | Treasury auction cycle (price dip into auctions, rebound after) | [H](structural-niches.md) | Promising | Needs data |
| `mnav_treasury_company_premium` | Crypto treasury-company premium to NAV (MSTR-type) | [H](structural-niches.md) | Promising | Needs data |
| `spac_trust_floor_yield` | SPAC trust arbitrage (post-2022) | [H](structural-niches.md) | Promising | Needs data |
| `merger_arb_cash_deals_individual` | Merger arbitrage in announced cash deals | [H](structural-niches.md) | Promising | Needs data |
| `tax_loss_selling_december_reversal` | December tax-loss selling in losers and the January rebound (incl. CEFs) | [H](structural-niches.md) | Promising | Needs data |
| `country_etf_momentum_value` | Country ETF/ADR momentum and value | [H](structural-niches.md) | Promising | Needs data |
| `vix_futures_basis_etp` | VIX futures basis / roll-yield via ETPs | [H](structural-niches.md) | Promising | Needs data |
| `natgas_etf_contango_drag` | Short the roll in natural gas ETPs (UNG, BOIL) | [H](structural-niches.md) | Promising | Needs data |
| `prediction_market_macro_signal` | Kalshi/Polymarket probabilities as macro and event features [adjacent] | [H](structural-niches.md) | Promising | Needs data |
| `meme_score_options` | Options-feature "memeness" classifier, weekly | [I](frontier.md) | Promising | Needs data |
| `fund_flow_price_pressure` | Flow-induced trading from fund/ETF holdings ("Ponzi funds") | [I](frontier.md) | Promising | Needs data |
| `thematic_etf_launch_underperformance` | Avoid what new thematic ETFs hold | [I](frontier.md) | Promising | Needs data |
| `benchmarking_intensity_switch` | Benchmarking intensity and index-switch demand shocks | [I](frontier.md) | Promising | Needs data |
| `tariff_exposure_overreaction` | Trade-exposure and uncertainty-sensitivity on tariff shocks | [I](frontier.md) | Promising | Needs data |
| `tdf_contrarian_flows` | Target-date-fund contrarian rebalancing | [I](frontier.md) | Promising | Needs data |
| `llm_earnings_call_unusual` | Unusual management communication on calls | [I](frontier.md) | Promising | Needs data |
| `lazy_prices_10k_change` | Year-over-year 10-K/10-Q text change | [I](frontier.md) | Promising | Needs data |
| `insider_10b5_1_plan_disclosure` | Mandatory 10b5-1 plan adoption/termination disclosure (2023 rule) | [I](frontier.md) | Promising | Needs data |
| `same_month_seasonality` | Heston-Sadka same-calendar-month return seasonality | [A](cross-sectional.md) | Weak | Ready |
| `size_conditional_on_quality` | Small caps, but only quality ones | [A](cross-sectional.md) | Weak | Ready |
| `long_term_reversal` | 3-5 year losers beat winners (De Bondt-Thaler) | [A](cross-sectional.md) | Weak | Ready |
| `low_turnover_premium` | Share turnover as a characteristic | [A](cross-sectional.md) | Weak | Ready |
| `dividend_initiation_omission_drift` | Dividend initiations / omissions as events and dividend yield as a characteristic | [A](cross-sectional.md) | Weak | Ready |
| `stock_split_drift` | Post-split drift | [A](cross-sectional.md) | Weak | Ready |
| `low_priced_stocks` | Nominal price level (low-priced stocks) | [A](cross-sectional.md) | Weak | Ready |
| `fifty_two_week_low_proximity` | Nearness to the 52-week low | [A](cross-sectional.md) | Weak | Ready |
| `earnings_and_margin_stability` | Earnings stability / gross-margin stability as quality sub-signals | [A](cross-sectional.md) | Weak | Ready |
| `earnings_streak_drift` | "Street beat" streaks and streak breaks | [B](events.md) | Weak | Ready |
| `pead_large_vs_small_since_2010` | Where does PEAD still live? (size-conditioned drift as a research check) | [B](events.md) | Weak | Ready |
| `ipo_long_run_underperformance` | IPOs underperform for 3-5 years (exclusion rule) | [B](events.md) | Weak | Ready |
| `dividend_initiation_omission` | Dividend initiations (long) and omissions / cuts (short) | [B](events.md) | Weak | Ready |
| `dividend_change_at_earnings` | Dividend increases bundled with earnings (and surprise interaction) | [B](events.md) | Weak | Ready |
| `special_dividend_announcement` | Special dividends | [B](events.md) | Weak | Ready |
| `earnings_timing_afterhours_friday` | After-hours / Friday / busy-day announcers (bad-news timing) | [B](events.md) | Weak | Ready |
| `name_change_fad` | Corporate name changes toward a fad (dot-com, blockchain, AI) | [B](events.md) | Weak | Ready |
| `c07_iv_minus_realized_stock` | Realised-minus-implied volatility spread for stock returns | [C](options-volatility.md) | Weak | Ready |
| `c08_iv_term_structure_slope_stock` | IV term-structure slope as a stock-return signal | [C](options-volatility.md) | Weak | Ready |
| `c23_skew_risk_reversal_trade` | Selling index skew (risk reversals) / skew premium | [C](options-volatility.md) | Weak | Ready |
| `c25_iron_condor_etf` | Iron condors / CNDR on index ETFs | [C](options-volatility.md) | Weak | Ready |
| `c27_opex_week_effect` | Option-expiration week equity returns (Stivers-Sun) | [C](options-volatility.md) | Weak | Ready |
| `c29_wheel_strategy` | The "wheel" (cash-secured puts -> covered calls) | [C](options-volatility.md) | Weak | Ready |
| `c30_calendar_spread_term_kinks` | Calendar spreads on term-structure kinks (incl. earnings) | [C](options-volatility.md) | Weak | Ready |
| `fomc_cycle_even_weeks` | FOMC-cycle even-week premium | [D](calendar-flows.md) | Weak | Ready |
| `macro_announcement_days` | Macro announcement-day premium (Savor-Wilson), CPI / NFP days | [D](calendar-flows.md) | Weak | Ready |
| `overnight_momentum` | Persistence of overnight returns in the cross-section | [D](calendar-flows.md) | Weak | Ready |
| `day_of_week` | Day-of-the-week / Monday effect | [D](calendar-flows.md) | Weak | Ready |
| `halloween_sell_in_may` | Halloween indicator | [D](calendar-flows.md) | Weak | Ready |
| `all_time_high_breakout` | All-time-high / 52-week-high breakout continuation | [D](calendar-flows.md) | Weak | Ready |
| `dividend_capture_and_month_premium` | Dividend capture / dividend-month premium | [D](calendar-flows.md) | Weak | Ready |
| `share_class_arbitrage` | Dual-class share spread mean reversion | [D](calendar-flows.md) | Weak | Ready |
| `sector_etf_lead_lag` | Sector / size ETF lead-lag and cross-asset lead-lag | [D](calendar-flows.md) | Weak | Ready |
| `breadth_thrust` | Market-wide breadth thrusts (Zweig, Whaley) | [D](calendar-flows.md) | Weak | Ready |
| `index_option_expiry_pinning` | Pinning to strikes at option expiry | [D](calendar-flows.md) | Weak | Ready |
| `yield_curve_inversion_equity` | Yield-curve inversion / re-steepening as an equity de-risk trigger | [E](trend-macro.md) | Weak | Ready |
| `breadth_thrust_entry` | Breadth thrust / washout-recovery as an equity entry signal | [E](trend-macro.md) | Weak | Ready |
| `oil_shock_equity_lag` | Oil price changes predict equity returns (Striking Oil) and oil-sensitive industries | [E](trend-macro.md) | Weak | Ready |
| `geographic_lead_lag` | Same-metro firm lead-lag | [F](altdata-text-ml.md) | Weak | Ready |
| `canslim_episodic_pivot_vcp` | Discretionary growth-breakout setups (O'Neil, Minervini, Qullamaggie) | [F](altdata-text-ml.md) | Weak | Ready |
| `nearness_52w_high_cross_section` | George-Hwang 52-week-high ratio (monthly cross-section) | [G](statarb-technical.md) | Weak | Ready |
| `share_class_pairs` | Dual-class and dual-listed share pairs (GOOG/GOOGL, BRK.A/B, Siamese twins) | [G](statarb-technical.md) | Weak | Ready |
| `etf_to_holdings_lead_lag` | ETF price leads its constituents (end of day) | [G](statarb-technical.md) | Weak | Ready |
| `donchian_turtle_breakout_stocks` | 20/55-day channel breakouts with ATR stops on stocks | [G](statarb-technical.md) | Weak | Ready |
| `support_resistance_round_numbers` | Swing levels, pivot touches and round-number levels | [G](statarb-technical.md) | Weak | Ready |
| `overbought_shorts` | Shorting stretched / overbought names | [G](statarb-technical.md) | Weak | Ready |
| `low_volume_pullback_pocket_pivot` | O'Neil / Morales-Kacher pocket pivot and volume dry-up | [G](statarb-technical.md) | Weak | Ready |
| `gasoline_seasonality_etf` | Gasoline (UGA) spring seasonality | [H](structural-niches.md) | Weak | Ready |
| `quarter_end_markup_reversal` | Last-day-of-quarter mark-up and next-day reversal | [I](frontier.md) | Weak | Ready |
| `leveraged_etf_low_vol_regime` | Hold leveraged index ETFs only in low-vol regimes | [I](frontier.md) | Weak | Ready |
| `early_inclusion_runup_reversal` | Fast-tracked index inclusions | [I](frontier.md) | Weak | Ready |
| `overnight_return_persistence` | Overnight vs intraday "tug of war" | [I](frontier.md) | Weak | Ready |
| `tech_sector_leadership` | Industry momentum concentrated in tech eras | [I](frontier.md) | Weak | Ready |
| `treasury_refunding_equity` | Quarterly refunding announcement as an equity event | [I](frontier.md) | Weak | Ready |
| `cta_positioning_proxy` | Replicated trend-follower positioning as a flow signal | [I](frontier.md) | Weak | Ready |
| `buyback_window_support` | Open-window repurchase intensity after earnings | [I](frontier.md) | Weak | Ready |
| `gold_miners_vs_bullion` | Structural underperformance of gold shares vs gold | [I](frontier.md) | Weak | Ready |
| `acquirer_stock_deal_underperformance` | Avoid / short acquirers in stock-financed deals | [B](events.md) | Weak | Needs data |
| `nasdaq100_reconstitution` | Nasdaq-100 annual reconstitution additions/deletions | [B](events.md) | Weak | Out of scope |
| `sp400_600_additions_from_outside` | S&P 400/600 additions of names *not* previously in an S&P index | [B](events.md) | Weak | Needs data |
| `credit_rating_downgrade_drift` | Credit rating downgrades (negative drift), upgrades (none) | [B](events.md) | Weak | Needs data |
| `bankruptcy_emergence_equity` | Post-reorganisation equity | [B](events.md) | Weak | Needs data |
| `conference_presentation_drift` | Broker-hosted conference presentations and investor days | [B](events.md) | Weak | Needs data |
| `pdufa_decision_drift` | FDA PDUFA decision dates (biotech) | [B](events.md) | Weak | Needs data |
| `uplisting_otc_to_nasdaq` | OTC-to-Nasdaq/NYSE uplistings | [B](events.md) | Weak | Needs data |
| `c06_risk_neutral_skewness` | Option-implied (BKM) risk-neutral skewness | [C](options-volatility.md) | Weak | Needs data |
| `c09_unusual_options_activity` | Unusual options activity / OI surges | [C](options-volatility.md) | Weak | Needs data |
| `c10_dealer_gamma_pinning` | Dealer gamma / GEX and max-pain pinning at expiry | [C](options-volatility.md) | Weak | Out of scope |
| `c11_option_implied_expected_return` | Option-implied cost of capital / expected return (Martin-Wagner) | [C](options-volatility.md) | Weak | Needs data |
| `c15_option_momentum` | Option (straddle) return momentum | [C](options-volatility.md) | Weak | Needs data |
| `c21_vix_futures_basis_signal` | VIX futures basis as a *stock market* timing signal | [C](options-volatility.md) | Weak | Needs data |
| `month_end_index_rebalancing` | Month-end / quarter-end index rebalance day flow | [D](calendar-flows.md) | Weak | Needs data |
| `close_to_open_gap_reversal` | Gap-fill / overnight-gap reversal in single names | [D](calendar-flows.md) | Weak | Out of scope |
| `quarter_end_window_dressing` | Window dressing at quarter end | [D](calendar-flows.md) | Weak | Needs data |
| `leveraged_etf_decay_pairs` | Shorting both legs of leveraged ETF pairs (volatility decay) | [D](calendar-flows.md) | Weak | Out of scope |
| `risk_parity_etf` | Risk parity (equal risk contribution) as the base allocation | [E](trend-macro.md) | Weak | Out of scope |
| `country_cape_value` | Country rotation on CAPE (Shiller P/E10) | [E](trend-macro.md) | Weak | Needs data |
| `erp_timing_cape` | Equity risk premium timing by CAPE / cross-asset valuation | [E](trend-macro.md) | Weak | Out of scope |
| `defensive_cyclical_rotation` | Defensive vs cyclical sector rotation by regime / growth momentum | [E](trend-macro.md) | Weak | Needs data |
| `gold_real_rate_trend` | Gold vs real yields (and gold trend) as a tactical holding | [E](trend-macro.md) | Weak | - |
| `llm_headline_score_drift` | LLM-scored headlines, next-day/next-week drift | [F](altdata-text-ml.md) | Weak | Needs data |
| `earnings_call_vocal_cues` | Voice stress / affect (Mayew-Venkatachalam) | [F](altdata-text-ml.md) | Weak | Out of scope |
| `mdna_tone_change` | MD&A tone change and drift | [F](altdata-text-ml.md) | Weak | - |
| `wikipedia_pageviews_attention` | Wikipedia page-view spikes | [F](altdata-text-ml.md) | Weak | Needs data |
| `google_svi_attention` | Google search volume (Da-Engelberg-Gao) | [F](altdata-text-ml.md) | Weak | Needs data |
| `reddit_stocktwits_sentiment` | Social sentiment vs attention | [F](altdata-text-ml.md) | Weak | Out of scope |
| `lobbying_intensity` | Lobbying spend / market cap | [F](altdata-text-ml.md) | Weak | Needs data |
| `government_contract_dependency` | Share of revenue from government | [F](altdata-text-ml.md) | Weak | Needs data |
| `political_connections_pac` | PAC contribution breadth (Cooper-Gulen-Ovtchinnikov) | [F](altdata-text-ml.md) | Weak | Needs data |
| `job_postings_growth` | Online job postings | [F](altdata-text-ml.md) | Weak | Out of scope |
| `gap_fill_vs_gap_and_go` | Overnight gaps: fill or continue | [G](statarb-technical.md) | Weak | Out of scope |
| `chart_patterns_hs_cup_handle` | Head & shoulders, double tops/bottoms, cup-and-handle, flags | [G](statarb-technical.md) | Weak | Needs data |
| `adx_trend_filter` | ADX / DMI as a trend-strength filter | [G](statarb-technical.md) | Weak | Needs data |
| `bollinger_keltner_reversion` | Band reversion (close below lower band, re-entry) and %b extremes | [G](statarb-technical.md) | Weak | - |
| `long_term_reversal_debondt_thaler` | 3-5 year losers (noted) | [G](statarb-technical.md) | Weak | Out of scope |
| `correlation_breakdown_cross_asset_pairs` | Sector ETF vs commodity / rate pairs (XLE-USO, XLU-TLT, KRE-yields) | [G](statarb-technical.md) | Weak | Needs data |
| `post_bankruptcy_equity` | Post-Chapter-11 new equity | [H](structural-niches.md) | Weak | Needs data |
| `leveraged_pair_decay_short` | Short both legs of a 2x/-2x or 3x/-3x pair (multi-month) | [H](structural-niches.md) | Weak | Needs data |
| `btc_cme_basis_carry` | CME bitcoin cash-and-carry via ETF + futures | [H](structural-niches.md) | Weak | Needs data |
| `preferred_call_and_exdiv` | Preferred stocks: call-date traps and ex-dividend capture | [H](structural-niches.md) | Weak | Needs data |
| `etf_closure_liquidation` | ETF closure/liquidation announcements | [H](structural-niches.md) | Weak | Needs data |
| `stub_holdco_sotp_discount` | Holdco / stub discounts (sum-of-parts) | [H](structural-niches.md) | Weak | Needs data |
| `bitcoin_etf_flow_and_dow` | Spot BTC ETF flows and day-of-week effects | [H](structural-niches.md) | Weak | Needs data |
| `llm_headline_score` | LLM sentiment on news headlines | [I](frontier.md) | Weak | Needs data |
| `single_stock_letf_flows` | Single-stock leveraged ETF rebalancing demand | [I](frontier.md) | Weak | Needs data |
| `scheduled_corporate_event_drift` | Developer-conference / scheduled non-earnings event drift | [I](frontier.md) | Weak | Needs data |
| `ai_exposure_amh` | Generative-AI labour-exposure portfolio | [I](frontier.md) | Weak | Out of scope |
| `election_uncertainty_collapse` | Post-election-day short of risk-premium legs | [I](frontier.md) | Weak | Out of scope |
| `green_flows_esg` | Flow-driven green/ESG outperformance and its reversal | [I](frontier.md) | Weak | Needs data |
| `piotroski_f_score` | F-score fundamental screen within value stocks | [A](cross-sectional.md) | Decayed | Ready |
| `accruals` | Sloan accruals anomaly | [A](cross-sectional.md) | Decayed | Ready |
| `amihud_illiquidity_premium` | Illiquidity (Amihud) premium | [A](cross-sectional.md) | Decayed | Ready |
| `despac_underperformance` | De-SPAC post-merger underperformance | [B](events.md) | Decayed | Ready |
| `c05_put_call_ratio_volume` | Put/call volume ratio (Pan-Poteshman style) | [C](options-volatility.md) | Decayed | Ready |
| `pre_holiday` | Pre-holiday effect | [D](calendar-flows.md) | Decayed | Ready |
| `january_effect_small_caps` | January small-cap premium | [D](calendar-flows.md) | Decayed | Ready |
| `post_split_drift` | Post-stock-split drift | [D](calendar-flows.md) | Decayed | Ready |
| `sector_momentum_rotation` | Sector ETF relative-strength rotation | [E](trend-macro.md) | Decayed | Ready |
| `rsi2_connors_etf_pullback` | RSI(2) / Connors short-term mean reversion above the 200-day | [G](statarb-technical.md) | Decayed | Ready |
| `lead_lag_large_to_small` | Large caps lead small caps / sector leaders lead followers | [G](statarb-technical.md) | Decayed | Ready |
| `analyst_dispersion_short` | Analyst forecast dispersion (high dispersion underperforms) | [B](events.md) | Decayed | Needs data |
| `stock_split_announcement_drift` | Stock split announcements | [B](events.md) | Decayed | Out of scope |
| `seo_announcement_underperformance` | Seasoned equity offerings (avoid) | [B](events.md) | Decayed | - |
| `etf_constituent_residual_statarb` | Avellaneda-Lee PCA / ETF-residual mean reversion | [G](statarb-technical.md) | Decayed | Out of scope |
| `pairs_distance_ggr` | Pairs trading, distance method (Gatev-Goetzmann-Rouwenhorst) | [G](statarb-technical.md) | Decayed | Needs data |
| `pairs_cointegration_copula` | Cointegration and copula pairs | [G](statarb-technical.md) | Decayed | Out of scope |
| `short_term_reversal_classic` | Baseline: raw 1-week / 1-month reversal (Jegadeesh 1990, Lehmann 1990) | [G](statarb-technical.md) | Decayed | - |
| `retail_order_imbalance_decay` | BJZZ retail order imbalance (documented decay) | [I](frontier.md) | Decayed | Needs data |
| `c24_tail_hedge_cost_benefit` | Tail hedging with OTM puts: cost vs benefit | [C](options-volatility.md) | Dead | Ready |
| `pre_fomc_drift` | Pre-FOMC announcement drift | [D](calendar-flows.md) | Dead | Ready |
| `ma_crossover_single_stocks` | Golden/death cross and MA(50/200) timing on single stocks and indices | [G](statarb-technical.md) | Dead | Ready |
| `recommendation_change_drift` | Analyst recommendation upgrades/downgrades and initiations | [B](events.md) | Dead | Out of scope |
| `ex_dividend_capture` | Ex-dividend day capture | [B](events.md) | Dead | Out of scope |
| `circuit_breaker_price_limits` | LULD halts and market-wide circuit breakers | [D](calendar-flows.md) | Dead | Out of scope |
| `copper_gold_yield_lead` | Copper/gold ratio as a lead on 10-year yields and cyclicals | [E](trend-macro.md) | Dead | - |
| `fed_net_liquidity_equity` | Fed net liquidity (balance sheet − TGA − RRP) driving equities | [E](trend-macro.md) | Dead | - |
| `congress_trades_copycat` | STOCK Act disclosures (NANC / KRUZ) | [F](altdata-text-ml.md) | Dead | - |
| `candlestick_patterns` | Single- and multi-bar candlesticks (hammer, engulfing, doji, stars) | [G](statarb-technical.md) | Dead | - |
| `adr_country_lead_lag` | US close predicting Asia-listed ADRs next day | [H](structural-niches.md) | Dead | Out of scope |
| `quantpedia_sweep_misc` | Quantpedia / Alpha Architect / book families not elsewhere in F | [F](altdata-text-ml.md) | Other | Ready |
| `ibd_relative_strength_ranking` | IBD-style RS rank (12-month, last quarter double-weighted) | [G](statarb-technical.md) | Other | Ready |
| `minervini_trend_template` | Minervini Trend Template / Stage-2 screen | [G](statarb-technical.md) | Other | Ready |
| `etf_creation_redemption_arbitrage` | ETF creation / redemption arbitrage | [D](calendar-flows.md) | Other | Out of scope |
| `satellite_cardpanel_nowcasting` | Satellite imagery and card-transaction panels | [F](altdata-text-ml.md) | Other | Out of scope |
| `opening_range_breakout` | ORB (noted; intraday) | [G](statarb-technical.md) | Other | Out of scope |
