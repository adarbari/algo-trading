# Edge build plan (EB): every Strong and Promising idea

Owner ask 2026-10-17: build every Strong and Promising idea in the catalogue
([README.md](README.md)). Where data is missing, use the free source with the best quality. Add
features and measurement improvements as needed. Choose the model tier by the task. This file is
the shared spec the build sessions work from. `docs/roadmap.md` Now / Next tracks the
open item.

## Scope

**112 work items**, merged from 153 Strong and Promising ideas (the table at the end): 64 new
edges, 23 variants of a filed or new edge, 20 filters or overlays (tested as a variant of the edge
they filter), and 5 harness rules. By archetype:

| Archetype | Items | Harness support today |
| --- | --- | --- |
| Cross-sectional rank (XS_RANK) | 46 | yes |
| Event-triggered picks (EVENT_XS) | 22 | 2 of 5 event classes run; new classes needed (H4) |
| ETF allocation / TAA (ALLOCATION) | 14 | no (H10) |
| Calendar timing (CALENDAR_TS) | 10 | no (H5a, H5b) |
| Option-structure P&L (OPTION_PNL) | 6 | win rate only (H8, later H13) |
| Regime gate (REGIME_GATE) | 6 | as variants |
| Option data ranks stocks (OPTION_SIGNAL) | 5 | yes |
| Pair spread (PAIR_SPREAD) | 3 | no (H9) |

Out of scope, recorded so they are not re-filed: earnings-call transcripts (no licence-clean free
feed; the 8-K 2.02 press release is used instead), short-seller report lists (manual, few events),
prediction markets, SPAC trust yield and patents. Each one returns only if a source appears.

## Track H: harness and measurement (architect design, 2026-10-17)

PRs land in this order. Every PR except H0 and H5a gets an `architect` review.

| # | PR | Effort |
| --- | --- | --- |
| H0 | One folder per edge: `config/site/edges/<id>/edge.toml`, because the 12-file folder cap cannot hold 100+ edges. A `family` key. Fitness test `EVENT_CLASSES == EVENT_FIELDS`: 3 of the 5 declared classes validate but fail at run time (a bug found in this review), so add their fields | S |
| H1 | A t-statistic on the picks series, the trial count site-wide (the t > 3 bar in the literature), the published-size haircut shown beside `[published]`, and `[published] leg` | S |
| H2 | SEC acceptance time as the `knowledge_ts` of fundamentals. Today a 10-Q accepted after 16:00 counts one session early (a real lookahead). New raw facts version, `financials@v3`, `fundamentals@v4`, backfill | M |
| H3 | Outcome sides: `short` (bottom K, for avoid lists) and `long_short` (spread, no base rate), an assumed borrow cost, a side column in the ledger | M |
| H4 | An event-class framework with subtypes. Classes on stored tables: earnings-date shift, 8-K item, NT late filing, S&P deletion apart from addition, tender offer, lockup expiry | M |
| H5a | Calendar windows as schedules: turn of month, OPEX week, quarter end, pre-holiday | S |
| H5b | A time-series base (in-window vs out-of-window for a few named instruments). New ADR | M |
| H6 | Decoy battery: `factor_betas@v1`; IVOL, MAX, Amihud and beta presets; sector-stratified random draws | M |
| H7 | Buy/hold bands for turnover-aware cost (ships with H6: both bump `LEG_VERSION`, so one re-run) | M |
| H8 | Option model P&L (straddle, short put, delta-hedged, priced from stored IV) | S-M |
| H9 | Pair-spread outcome plus `share_classes@v1` | M |
| H10 | Portfolio and allocation outcomes: weights, blended benchmark, cash, parameter ensemble, out-of-sample haircut. New ADR | L |
| H11 | A residual-returns grain (factor-neutral outcome) | L |
| H13 | Chain P&L grain `outcomes/option/structure_pnl@v1`. Last: chains start 2026-10-02, after the frozen split | L |

Dependencies: H0 first. H1 before any verdict on a new edge is read. H2 before any fundamentals
edge. H3 before H9 and the short-leg ideas. H6 before H11. H7 before H10. H5b and H10 need the
Tiingo history (track D0).

## Track D: data (free first; add-data-source; architect reviews each `known_from`)

| # | Data | Source | Unlocks | Effort |
| --- | --- | --- | --- | --- |
| D0 | **Tiingo history from 2010, delisted names included, plus the outcomes backfill: by 2026-11-09, when Tiingo Power ends** | Tiingo (bought) | About 21 items: every ALLOCATION and CALENDAR_TS item, 52-week high, the avoid legs, statistical power for every edge | ops + M |
| D1 | 8-K items, NT 10-K/10-Q, SC TO-I, Form 25, 424B4 lockups, Form 10 spin-offs | SEC submissions JSON (`acceptanceDateTime`), full-index, EFTS (existing `sec`) | 8-K drift, late filer, tender offers, lockups, spin-offs, delistings | S-M |
| D2 | Nightly analyst estimate snapshots (our own point-in-time history; **start early, history accrues**) | FMP + Finnhub free tiers (existing) | revision momentum, target price, revenue surprise | S |
| D3 | VIX, VIX9D, VIX3M, VIX6M, VVIX and VX futures by expiry (2013 onward) | Cboe CDN CSVs | VIX roll yield, vol regime gates | S |
| D4 | ETF daily shares outstanding / flows | issuer files (existing `ishares`, `ssga`, `proshares`) | ETF flow pressure, leveraged-ETF crowding | S |
| D5 | CEF and BDC NAVs | Tiingo EOD on Nasdaq MFQS `X..X` NAV tickers (CEFConnect forbids automation) | CEF discounts, December muni CEF, distribution trap | S |
| D6 | Form 4 insider transactions | SEC bulk Form 345 sets plus per-filing XML for acceptance time | cluster insider buys (Strong) | M |
| D7 | Country CAPE | Barclays Shiller CSV (confirm the terms) | country value rotation, trend + carry + value | S |
| D8 | IPO calendar and lockup dates | Nasdaq IPO JSON + 424B4 | lockup expiry | S-M |
| D9 | FINRA short interest and daily short volume | FINRA API | days-to-cover. The terms ban ML use of the rows: rule screens only, never a learned scorer | M |
| D10 | 10-K / 10-Q text and sections | EDGAR per filing + Financial Statement and Notes sets | Lazy Prices (Strong), TNIC peers, risk-factor change, MD&A tone | L |
| D11 | Futures curves (**start early, history accrues**) | IBKR gateway (personal licence, read-only) | commodity and bond carry | M |

## Track E: features, screeners and edge documents

Each edge ships as one document plus its screener v1 (the source's own rule), with the features it
needs (add-feature) and its Guide entries in the same PR. Batched by family, about 5 to 8 edges per
PR, implementer (Sonnet). Documents are written from the catalogue page and its verified figures.
Waves follow the harness and data each family needs:

- **E1 (after H0, H1)**: XS_RANK and OPTION_SIGNAL items on stored data. That covers the momentum
  variants (residual, volatility-scaled, FIP, quality-conditioned, industry, short-term), low beta
  / low vol, residual reversal, high-volume premium, dividend month, the option-implied signals
  (call-put IV spread, smirk, IV change, O/S volume, lottery attention), earnings-neutral reversal
  and the composite mispricing score (also added to the decoy battery).
- **E2 (after H2)**: fundamentals: cash-based operating profitability, QMJ, net share issuance,
  asset growth, distress, composite value, BDC price-to-NAV from XBRL.
- **E3 (after H3, H4, D1)**: event edges and avoid lists: earnings-date shift (Strong), 8-K items,
  late filers, S&P deletions, tender offers, lockups, spin-offs, the short sides of IVOL/MAX,
  issuance and thematic ETFs.
- **E4 (after H5, H8, H9, D0, D3, D5)**: calendar, option P&L and pairs: turn of month, quarter-end
  rebalancing, OPEX week, Treasury month end, December losers, per-name VRP, pre-earnings
  straddles, IV crush, put-write, dual-class spreads, CEF discounts.
- **E5 (after H10, D0, D7, D11)**: allocation: multi-asset trend, dual momentum, Keller VAA / DAA,
  credit and curve timing, country momentum and value, volatility-managed equity, VIX roll, and
  trend + carry + value.
- **E6 (after D2, D6, D9, D10 accrue or land)**: insider buys, analyst revisions, days-to-cover,
  Lazy Prices, TNIC peers, ETF flow pressure.

Every new edge enters as `candidate` with `frozen_from = 2026-04-01`, the rule the existing edges
use. The harness, not the catalogue, decides each verdict.

## Sessions and models

- One Sonnet orchestrating session per track: **H** (harness), **D** (data, starting with D0, D2
  and D11, because their history accrues or the deadline is close) and **E** (edges, from E1 once
  H0 and H1 merge). At most two run at the same time (the shared-machine rule). E starts when H0
  and H1 merge.
- Inside each session: `scout` / `checker` (Haiku) do lookups, gates and CI logs; `implementer`
  (Sonnet) does scoped PRs; `architect` (Opus) designs and reviews H1-H13, every new
  `known_from` and any quant code; a Fable agent researches and writes edge-document prose where a
  source needs reading.
- Each PR follows rule 10 (push, PR, Auto-fix, auto-merge on green). An architect-area PR goes
  through review-and-release.

## Owner decisions (decided by the owner, 2026-10-17)

- O1 Verdict bar: Promising stays at t >= 2; Works needs t >= 3.
- O2 Sides: a `short` result on liquid names may be a verdict basis (an avoid list is
  actionable); `long_short` is diagnostic only.
- O3 No paid historical option chains: H8 model P&L ships now, and H13 accrues.
- O4 No new spend: the Tiingo history is pulled within the bought month, by 2026-11-09.

Full designs: [harness-design.md](harness-design.md) (architect, for each H PR) and the data
sources appendix below (Fable research, endpoints verified 2026-10-17).

## Work items (112)

| work_id | source_ids | strength | kind | archetype | new_event_class | features_new | data_missing | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| earnings_date_shift | earnings_date_shift,earnings_date_advance_delay | Strong | edge | EVENT_XS | date_shift (earnings_expected) | date_shift_days; date_shift_known_from |  | Earlier report signals good news; need known_from of date notice; extends earnings_expected class |
| net_share_issuance | net_share_issuance,net_share_count_change,share_issuance_dilution_drift | Strong | edge | XS_RANK |  | net_issuance_pct_12m; buyback_flag |  | One edge; issuance and buyback variants; slow, cheap to trade |
| mining_equity_beta_fade | mining_equity_beta_fade | Weak-Promising | variant_of:net_share_issuance | PAIR_SPREAD |  | miner_vs_metal_residual |  | Issuance-conditioned miner vs metal pair; needs short leg |
| c12_vrp_cross_section_iv_hv | c12_vrp_cross_section_iv_hv | Strong | variant_of:vrp_short_premium | OPTION_PNL |  | iv_minus_hv_30 |  | Per-name IV-HV rank; filed VRP variant or new screener |
| composite_mispricing_score | composite_mispricing_score | Strong | edge | XS_RANK |  | asset_growth; accruals; ohlson_o; net_op_assets; gross_profit_to_assets; composite_rank |  | 11-anomaly composite; also decoy benchmark for others |
| residual_momentum | residual_momentum | Strong | variant_of:momentum_12_1 | XS_RANK |  | resid_mom_12_1 (vs market/sector) |  | Residual vs beta-factor returns; cuts crash risk |
| volatility_scaled_momentum | volatility_scaled_momentum | Strong | variant_of:momentum_12_1 | XS_RANK |  | mom_12_1_vol_scaled; momentum_vol_scale |  | Barroso-Santa-Clara; scale by realised vol |
| momentum_x_quality_interaction | momentum_x_quality_interaction | Strong | variant_of:momentum_12_1 | XS_RANK |  | quality_score (see qmj) |  | Portfolio rule: momentum within quality; needs quality feature first |
| frog_in_the_pan | frog_in_the_pan | Promising | variant_of:momentum_12_1 | XS_RANK |  | information_discreteness |  | Smooth-path momentum beats lumpy |
| factor_momentum | factor_momentum | Promising | edge | ALLOCATION |  | factor_return_series; factor_trailing_return |  | Needs factor-return construction first; tilts among factors |
| industry_momentum | industry_momentum,industry_relative_mean_reversion_monthly | Promising | edge | XS_RANK |  | industry_ret_12m; industry_adj_ret_1m |  | Industry momentum plus industry-relative monthly reversal; needs industry map (sector ETF proxy exists) |
| cash_based_operating_profitability | cash_based_operating_profitability | Strong | edge | XS_RANK |  | cash_op_profitability |  | From SEC financials, filing time as knowledge_ts |
| quality_minus_junk | quality_minus_junk | Strong | edge | XS_RANK |  | qmj_score; profitability_z; safety_z |  | Quality tilt; reuse for momentum x quality |
| intangibles_adjusted_value | intangibles_adjusted_value | Promising | edge | XS_RANK |  | rd_capital; intangibles_adj_book_to_market | R&D expense history (SEC R&D not stored) | R&D stock needs history; classic B/M decayed |
| asset_growth | asset_growth | Promising | filter_overlay | XS_RANK |  | asset_growth_yoy; total_assets_year_ago |  | Avoid filter on high asset growth |
| idiosyncratic_volatility_and_max | idiosyncratic_volatility_and_max | Promising | filter_overlay | XS_RANK |  | idio_vol_60d; max_ret_21d |  | Avoid lottery stocks; options overlay |
| betting_against_beta_low_vol | betting_against_beta_low_vol,beta_anomaly_after_uptrend | Promising | edge | XS_RANK |  | low_beta_rank; mkt_uptrend_24m |  | Long low-beta only after 24m market uptrend; raw decayed |
| short_term_residual_reversal | short_term_residual_reversal,residual_reversal_sector_neutral | Promising | edge | XS_RANK |  | resid_ret_5d; resid_ret_21d |  | Large-cap residual reversal; raw version decayed |
| short_term_momentum_high_turnover | short_term_momentum_high_turnover | Promising | edge | XS_RANK |  | turnover_ratio |  | Short-term momentum in high-turnover names |
| stock_time_series_momentum | stock_time_series_momentum | Promising | filter_overlay | XS_RANK |  | stock_tsmom_sign |  | Own-trend filter on cross-sectional picks |
| distress_failure_probability | distress_failure_probability | Promising | filter_overlay | XS_RANK |  | ohlson_o; campbell_hilscher_shumway |  | Exclusion list for distressed names |
| analyst_coverage_conditioned_momentum | analyst_coverage_conditioned_momentum | Promising | variant_of:momentum_12_1 | XS_RANK |  | analyst_count_history | analyst coverage history (point-in-time) | Momentum stronger in low-coverage names; accumulate history |
| rd_intensity | rd_intensity,innovative_efficiency_patents | Promising | edge | XS_RANK |  | rd_to_sales; rd_ability; rd_capital | R&D expense and patents (not stored) | rd_ability from financials is Ready; patent efficiency Needs data |
| composite_value | composite_value | Promising | variant_of:cash_based_operating_profitability | XS_RANK |  | composite_value_rank; ev_ebit; fcf_yield |  | Only useful combined with profitability |
| double_surprise_pead_small | double_surprise_pead_small | Promising | variant_of:small_cap_earnings_drift | EVENT_XS |  | revenue_surprise_pct | Revenue consensus history | Double (EPS+revenue) surprise; small caps |
| sp500_deletions_long | sp500_deletions_long | Promising | variant_of:sp500_index_changes | EVENT_XS |  | deletion_rebound_flag |  | Mirror of additions edge; deletions rebound |
| eight_k_item_drift | eight_k_item_event_drift,eight_k_item_drift | Promising | edge | EVENT_XS | eight_k_item | eight_k_item_flag (4.02 5.02 4.01) | 8-K item text classification for 5.02/4.01 | Filing items stored; 4.02 Ready; short/filter side stronger |
| dividend_month_premium | dividend_month_premium | Promising | edge | XS_RANK |  | expected_div_month_flag |  | Stocks earn more in expected-dividend months |
| analyst_revision_momentum | analyst_revision_momentum | Promising | edge | XS_RANK |  | eps_revision_history | Point-in-time analyst revision history | Only snapshots stored; start accumulating |
| target_price_implied_return | target_price_implied_return | Promising | edge | XS_RANK |  | target_price_upside | Target-price history | Needs analyst target series |
| guidance_change_drift | guidance_change_drift | Promising | edge | EVENT_XS | guidance_change | guidance_change_dir | Guidance extraction from releases/transcripts | Needs text extraction via text-model seam |
| earnings_call_text_score | call_tone_change_drift,earnings_call_qa_evasiveness,llm_earnings_call_unusual | Promising | edge | EVENT_XS |  | call_tone_change; qa_evasiveness; llm_unusual_score | Earnings call transcripts | Shared transcript source; score via text seam |
| pre_earnings_runup_winners | pre_earnings_runup_winners | Weak-Promising | variant_of:earnings_announcement_premium | EVENT_XS |  | preearn_runup_20d |  | Winners run up into earnings |
| insider_opportunistic_cluster_buys | insider_opportunistic_cluster_buys,insider_10b5_1_plan_disclosure | Strong | edge | EVENT_XS | insider_filing (Form 4) | insider_cluster_buy_count; insider_opportunistic_flag; plan_10b5_1_flag | Form 4 insider filings (EDGAR XML) | About 82bp/mo original; 10b5-1 variant has few events |
| activist_13d_drift | activist_13d_drift,cef_activist_target_prediction | Weak-Promising | edge | EVENT_XS | activist_13d | activist_13d_flag | 13D filing ingestion | 13D drift; CEF target prediction also needs NAV |
| merger_arb_cash_deals | merger_arb_cash_deals,merger_arb_cash_deals_individual | Promising | edge | EVENT_XS | merger_deal | deal_spread_annualised; deal_terms | Deal terms extraction (8-K 1.01) | Modest steady spread; price outcome, not excess_return |
| spinoff_drift | spinoff_parent_and_spinco,spinoff_post_distribution_drift | Promising | edge | EVENT_XS | spinoff | spinoff_flag | Spin-off event list from filings | Parent and spinco legs; partly derivable from listing history |
| ipo_lockup_expiry | ipo_lockup_expiry,ipo_lockup_expiry_pressure | Weak-Promising | filter_overlay | EVENT_XS | ipo_lockup | days_to_lockup_expiry | Lockup dates (S-1/424B) | Avoid-list around lockup expiry; long leg weak |
| late_filer_nt_drift | late_filer_nt_drift | Promising | filter_overlay | EVENT_XS | nt_filing | nt_10k_10q_flag | NT 10-K/10-Q forms if not stored | Exclusion filter; check form coverage |
| lazy_prices_10k_change | lazy_prices_10k_change,risk_factor_section_change | Strong | edge | XS_RANK |  | filing_text_similarity; risk_factor_change | 10-K/10-Q full text | Cheapest big text win; risk-factor variant follows |
| tnic_text_peer_momentum | tnic_text_peer_momentum | Promising | variant_of:lazy_prices_10k_change | XS_RANK |  | tnic_peer_return; peer_table | 10-K text + peer table | Shares 10-K ingestion with Lazy Prices |
| conglomerate_pseudo_lead_lag | conglomerate_pseudo_lead_lag | Promising | edge | XS_RANK |  | segment_peer_return | Segment extraction | Cohen-Lou; subsumed by analyst links; decay unknown |
| customer_supplier_momentum | customer_supplier_momentum | Promising | edge | EVENT_XS | customer_earnings (peer) | customer_link_table; customer_ret | Customer links from 10-K (LLM) | Event-timed supplier drift on customer earnings day; peer class exists |
| sec_comment_letters | sec_comment_letters | Weak-Promising | filter_overlay | XS_RANK |  | comment_letter_flag | SEC CORRESP ingestion | Quality filter, not return signal |
| technology_links_momentum | technology_links_momentum | Weak-Promising | variant_of:tnic_text_peer_momentum | XS_RANK |  | tech_peer_return | Patents | Low priority; patent data |
| ml_cross_sectional_scorer | ml_cross_sectional_scorer | Promising | harness_rule | XS_RANK |  | ml_score | 2010+ history (Tiingo) | Tooling; ML proposes, harness judges; weak as edge |
| short_seller_report_drift | short_seller_report_drift | Promising | edge | EVENT_XS | short_seller_report | short_report_flag | Short-seller report list | Put-buying variant unique; manual list |
| earnings_gap_volume_drift | canslim_episodic_pivot_vcp,episodic_pivot_gap_volume | Promising | variant_of:small_cap_earnings_drift | EVENT_XS |  | gap_volume_flag |  | Testable CANSLIM/episodic-pivot variant of PEAD; EOD entry |
| turn_of_the_month | turn_of_the_month | Promising | edge | CALENDAR_TS |  | tom_window_flag | Tiingo history 2010+ (ED6) for power | Index timing vs rest; each month one event |
| quarter_end_rebalancing | quarter_end_rebalancing,pension_quarter_end_rebalancing | Promising | edge | CALENDAR_TS |  | qtr_end_window_flag; pension_rebalance_signal | Tiingo history 2010+ | 60/40 flows; 12 events/yr |
| option_expiration_week | option_expiration_week | Promising | edge | CALENDAR_TS |  | opex_week_flag | Tiingo history 2010+ for power | Large caps; OI-conditioned variant unpublished |
| overnight_vs_intraday_tug_of_war | overnight_vs_intraday_tug_of_war | Promising | harness_rule | XS_RANK |  | overnight_ret_20d; intraday_ret_20d |  | Decomposition tool for other edges, weak alone |
| december_losers_reversal | december_losers_reversal,tax_loss_selling_december_reversal | Promising | filter_overlay | CALENDAR_TS |  | december_loser_flag | CEF variant needs NAV | One event per year; skip loser leg overlay on momentum; equities Ready |
| muni_cef_december | muni_cef_december | Promising | edge | CALENDAR_TS |  | december_window_flag | CEF universe (instrument class) | Price-only test; count Decembers not funds |
| flow_induced_trading_lou | flow_induced_trading_lou | Promising | edge | XS_RANK |  | fund_flow_pressure | Fund holdings + flows (N-PORT) | N-PORT free on EDGAR |
| etf_flow_pressure | etf_flows_to_underlying,fund_flow_price_pressure,etf_flow_reversal_constituents | Promising | edge | XS_RANK |  | etf_shares_chg; constituent_flow_pressure | ETF shares outstanding history | iShares/SSGA subset Ready; reversal on constituents |
| etf_premium_discount_reversion | etf_premium_discount_reversion | Weak-Promising | edge | XS_RANK |  | etf_premium_discount | ETF NAV history | Needs NAV history |
| closed_end_fund_discounts | closed_end_fund_discounts,cef_discount_reversion | Strong | edge | XS_RANK |  | cef_discount_to_nav; cef_discount_zscore | CEF NAV (N-PORT or CEFConnect) | Long-only, individual-sized |
| cef_distribution_trap | cef_distribution_trap_premium_collapse | Promising | filter_overlay | XS_RANK |  | cef_distribution_coverage | CEF NAV | Filter on CEF discount edge |
| retail_options_lottery_attention | retail_attention_herding,meme_score_options,retail_options_lottery_share,retail_lottery_option_flow | Promising | edge | OPTION_SIGNAL |  | lottery_call_share; meme_score |  | Fade high retail-lottery option flow; put-based fade variant |
| high_volume_return_premium | high_volume_return_premium,volume_shock_with_no_news | Promising | edge | XS_RANK |  | high_volume_flag; no_news_flag |  | Needs no-news filter from event classes (ADR 0050) |
| news_conditioned_reversal | extreme_return_reversal,large_move_news_vs_no_news | Promising | variant_of:short_term_residual_reversal | XS_RANK |  | move_news_class | Historical event classification (8-K stored; headlines capped) | Reversal only on no-news moves |
| fifty_two_week_high | fifty_two_week_high,breakout_52w_high_trend_following | Promising | variant_of:momentum_12_1 | XS_RANK |  | high_52w_ratio_rank | Tiingo history incl. delisted (arriving) | Anchoring variant; trend-following breakout needs 10y+ |
| short_squeeze_days_to_cover | short_squeeze_days_to_cover | Promising | edge | XS_RANK |  | short_interest_ratio; days_to_cover | FINRA short interest | Needs correct known_from |
| earnings_neutral_reversal | earnings_neutral_reversal | Promising | edge | EVENT_XS |  | earnings_week_reversal |  | Reversal stronger just before earnings; 40+ events/quarter |
| option_cp_iv_signals | c01_call_put_iv_spread,c02_iv_smirk_skew,c03_iv_change_call_put | Promising | edge | OPTION_SIGNAL |  | cp_iv_spread; cp_iv_spread_change |  | Option prices predict stock; differentiated by chain data |
| pre_earnings_cp_iv_spread | pre_earnings_cp_iv_spread | Promising | variant_of:option_cp_iv_signals | OPTION_SIGNAL |  | cp_iv_spread_pre_earn |  | C/P IV spread ahead of earnings |
| c04_option_stock_volume_ratio | c04_option_stock_volume_ratio | Weak-Promising | filter_overlay | OPTION_SIGNAL |  | option_to_stock_volume |  | Filter not standalone |
| c13_iv_term_structure_straddles | c13_iv_term_structure_straddles | Promising | edge | OPTION_PNL |  | straddle_pnl_outcome |  | Needs straddle P&L outcome kind |
| c14_delta_hedged_characteristics | c14_delta_hedged_characteristics | Promising | filter_overlay | OPTION_PNL |  | delta_hedged_return_outcome |  | Selection overlay; needs delta-hedged P&L outcome |
| c16_pre_earnings_straddle_buy | c16_pre_earnings_straddle_buy | Promising | edge | OPTION_PNL |  | straddle_pnl_outcome |  | Buy straddle before earnings; opposite of crush trade |
| c17_earnings_iv_crush_sell | c17_earnings_iv_crush_sell | Promising | edge | OPTION_PNL |  | short_straddle_pnl_outcome |  | Large caps only; needs short-vol structure outcome and tail risk |
| c18_iv_rank_conditional_selling | c18_iv_rank_conditional_selling | Weak-Promising | variant_of:vrp_short_premium | REGIME_GATE |  | iv_rank_gate |  | Filter on filed VRP |
| c19_index_put_write | c19_index_put_write | Promising | edge | OPTION_PNL |  | put_write_pnl_outcome | Index option chain (SPX/XSP) if not stored | Beta-adjusted VRP harvest; weekly vs monthly |
| vix_roll_yield | c20_short_vix_roll_yield,vix_futures_basis_etp | Promising | edge | ALLOCATION |  | vix_futures_basis; roll_yield | VIX futures curve | Short-VIX ETP; tail risk |
| c26_weekend_option_timing | c26_weekend_nontrading_option_mispricing | Weak-Promising | filter_overlay | CALENDAR_TS |  | weekend_theta_flag |  | Execution timing for option sales, not a trade |
| c31_lottery_options_short | c31_lottery_options_short | Promising | filter_overlay | OPTION_SIGNAL |  | lottery_call_score |  | Covered-call selection only |
| oversold_in_uptrend_pullback | oversold_in_uptrend_pullback | Promising | variant_of:momentum_12_1 | XS_RANK |  |  |  | Momentum entry timing |
| trend_factor_ma_cross_section | trend_factor_ma_cross_section | Promising | edge | XS_RANK |  | ma_trend_factor | Long price history (Tiingo) | Needs new rollup kind |
| ibs_etf_mean_reversion | ibs_etf_mean_reversion | Weak-Promising | filter_overlay | ALLOCATION |  | ibs |  | ETF overlay; weak standalone |
| volatility_contraction_expansion | volatility_contraction_expansion | Weak-Promising | filter_overlay | REGIME_GATE |  |  |  | Entry filter; options version to C |
| volume_price_confirmation_obv_cmf | volume_price_confirmation_obv_cmf | Weak-Promising | variant_of:momentum_12_1 | XS_RANK |  | obv_trend |  | Lee-Swaminathan volume momentum |
| anchored_vwap_reversion_retest | anchored_vwap_reversion_retest | Promising | edge | XS_RANK |  | capital_gains_overhang | Multi-year turnover history | Earnings-anchored VWAP is weaker Ready proxy |
| dual_class_spread_reversion | dual_class_spread_reversion | Strong | edge | PAIR_SPREAD |  | dual_class_spread_z; pair_list |  | Tiny capacity; pair list is manual; needs two-leg outcome |
| bdc_price_to_nav_reversion | bdc_price_to_nav_reversion | Promising | edge | XS_RANK |  | bdc_price_to_nav | NAV from XBRL (feature, not new source) | Clean; NAV per share feature |
| tender_offer_drift | tender_offer_post_expiry_drift,odd_lot_tender_priority | Promising | edge | EVENT_XS | tender_offer | tender_offer_flag | SC TO-I form coverage | Odd-lot priority is an alert, not a screener |
| treasury_month_end_extension | treasury_month_end_extension | Promising | edge | CALENDAR_TS |  | month_end_window_flag |  | Index extension buying; Treasury ETF timing |
| treasury_auction_cycle | treasury_auction_cycle | Weak-Promising | edge | CALENDAR_TS |  | auction_cycle_flag | Treasury auction calendar | Weak; needs calendar |
| thematic_etf_launch_fade | thematic_etf_launch_underperformance,new_thematic_etf_fade | Promising | filter_overlay | XS_RANK |  | etf_age_days; thematic_flag | Thematic issuer holdings (short variant) | Avoid filter; new-ETF listing from universe snapshots |
| mnav_treasury_company_premium | mnav_treasury_company_premium | Promising | edge | PAIR_SPREAD |  | mnav_premium | Crypto holdings per company; coin price | MSTR only for now; cohort lacks 40 events |
| spac_trust_floor_yield | spac_trust_floor_yield | Weak-Promising | edge | EVENT_XS | spac | trust_per_share; spac_yield | SPAC list and trust data | Small yield; event driven |
| country_etf_momentum_value | country_etf_momentum_value,country_momentum_etf | Promising | edge | ALLOCATION |  | country_cape_rank | CAPE data; ETF history (Tiingo) | Momentum Ready after backfill; value needs CAPE |
| fx_etf_carry_momentum | fx_etf_carry_momentum | Weak-Promising | edge | ALLOCATION |  | fx_carry_rank |  | Currency ETF carry plus momentum |
| reverse_split_distress_filter | reverse_split_distress_filter | Promising | filter_overlay | XS_RANK |  | reverse_split_flag |  | Exclusion filter |
| natgas_etf_contango_drag | natgas_etf_contango_drag | Promising | edge | ALLOCATION |  | futures_curve_slope | Futures curve | Price-drift version Ready; avoid UNG/USO long |
| prediction_market_macro_signal | prediction_market_macro_signal | Weak-Promising | filter_overlay | REGIME_GATE |  | pm_macro_prob | Prediction market source | Feature rather than edge |
| tsmom_multi_asset_etf | tsmom_multi_asset_etf,cross_asset_tsmom_bonds_to_equities | Strong | edge | ALLOCATION |  | tsmom_signal; vol_target_weight | Tiingo ETF backfill (ED6) | Long-only ETF; Sharpe ~0.3-0.5 after decay |
| absolute_momentum_crash_filter | absolute_momentum_crash_filter,sma10_timing_faber,dual_momentum_gem,taa_keller_vaa_daa | Promising | variant_of:tsmom_multi_asset_etf | ALLOCATION |  | abs_mom_signal; canary_signal | Tiingo ETF backfill; IDX:SPX pre-ETF | Risk management not alpha; test canary rule alone; ensemble over lookbacks |
| commodity_roll_momentum | commodity_term_structure_roll,commodity_momentum_etf | Promising | edge | ALLOCATION |  | commodity_roll_yield | Futures curves (ETF-only momentum Ready after backfill) | Defensive rule on UNG/USO is Ready |
| credit_spread_trend | credit_spread_trend | Promising | edge | ALLOCATION |  | credit_trend_signal |  | FRED long history; ETF bars after backfill |
| bond_curve_timing | bond_curve_timing | Promising | edge | ALLOCATION |  | bond_carry_trend |  | Carry plus trend only; slope-only dead |
| vol_managed_equity | vol_managed_equity | Promising | harness_rule | ALLOCATION |  | vol_target_scale |  | Position-sizing for every edge; weak as alpha |
| macro_regime_conditioner | macro_regime_conditioner,dollar_regime_tilt | Promising | harness_rule | REGIME_GATE |  | dollar_index_trend (DTWEXBGS) |  | Run lift tests split by regime; dollar conditioner adds DTWEXBGS |
| vix_mean_reversion_entry | vix_mean_reversion_entry | Promising | edge | CALENDAR_TS |  | vix_spike_flag |  | Event-starved; VIX series already in market rollup |
| trend_carry_value_combo | trend_carry_value_combo | Strong | edge | ALLOCATION |  | carry_rank; value_rank | Futures curves; country CAPE | Strong gross; trend leg only Ready |
| taa_ensemble_overfitting_guard | taa_ensemble_and_overfitting_guard | Strong | harness_rule | ALLOCATION |  |  |  | Test every TAA edge as ensemble with deflated Sharpe |
| odte_dealer_gamma_regime | odte_gamma_vol_regime,dealer_gamma_regime | Promising | filter_overlay | REGIME_GATE |  | dealer_gamma_exposure |  | Conditioning feature; evidence on vol not return |
| vol_control_deleveraging_proxy | vol_control_deleveraging_proxy | Promising | filter_overlay | REGIME_GATE |  | vol_control_selling_proxy |  | Retire if no better than plain RV |
| benchmarking_intensity_switch | benchmarking_intensity_switch | Promising | variant_of:russell_reconstitution | EVENT_XS |  | benchmark_intensity | S&P 400/600 membership | Russell blocked; needs mid/small S&P lists |
| passive_share_reconstitution_volume | passive_share_reconstitution_volume | Promising | variant_of:russell_reconstitution | EVENT_XS |  | passive_share_proxy |  | As feature on reconstitution edge |
| tariff_exposure_overreaction | tariff_exposure_overreaction | Promising | edge | EVENT_XS | tariff_shock (macro) | foreign_segment_share | Geographic segment share | Needs macro event dates and segment feature |
| tdf_contrarian_flows | tdf_contrarian_flows | Promising | edge | CALENDAR_TS |  | tdf_flow_proxy | TDF ownership (index proxy Ready) | Index-level proxy first |

## Appendix: data sources (research 2026-10-17)

Method: every endpoint below was fetched today (curl / WebFetch) unless marked **unverified**.
"Known_from" = the timestamp we can honestly attach to a row as the moment the fact was public.
Existing adapters: `libs/sources/algotrade_sources/vendors/{cboe,finnhub,fmp,fred,ibkr,ishares,massive,nasdaq,proshares,published,sec,sp500_history,ssga,tiingo,treasury}`.
ToS verdicts are a non-lawyer reading of the pages cited; "OK" means personal, non-commercial, automated pulls are either expressly allowed or the data is a government publication.

Conventions used in `make changed`-style effort: S = a reader on an existing adapter (one PR), M = new adapter + dataset (ADR-free), L = new adapter + text parsing or a licensing decision.

---

### 1. SEC Form 4 insider transactions

**Recommended: SEC "Insider Transactions Data Sets" (bulk, quarterly) for history + per-filing XML via the existing `sec` source for the nightly.**

- Bulk: https://www.sec.gov/dera/data/form-345 . Files `https://www.sec.gov/files/dera/data/insider-transactions-data-sets/YYYYqN_form345.zip`, Q1 2006 to Q3 2026. Flattened "as filed" XML of Forms 3/4/5 (+/A): tables SUBMISSION, REPORTINGOWNER, NONDERIV_TRANS, NONDERIV_HOLDING, DERIV_TRANS, DERIV_HOLDING, FOOTNOTES, OWNER_SIGNATURE (table list from the readme PDF https://www.sec.gov/files/insider_transactions_readme.pdf , downloaded but not text-extracted here: no PDF tool on the machine; **field names below are from memory, confirm against the readme**: SUBMISSION has ACCESSION_NUMBER, FILING_DATE, PERIOD_OF_REPORT, ISSUERCIK, ISSUERTRADINGSYMBOL; NONDERIV_TRANS has TRANS_DATE, TRANS_CODE (P/S/A/M/F/G...), TRANS_SHARES, TRANS_PRICEPERSHARE, TRANS_ACQUIRED_DISP_CD, SHRS_OWND_FOLWNG_TRANS, DIRECT_INDIRECT_OWNERSHIP). Format: TSV inside ZIP. Cadence: quarterly; a filing accepted after 17:30 ET on the quarter's last business day rolls to the next ZIP, so the bulk set is 0-3 months stale.
- Per filing (the nightly): the per-CIK submissions JSON `https://data.sec.gov/submissions/CIK##########.json` lists every Form 4 with `filingDate` **and `acceptanceDateTime`** (verified today: `['accessionNumber','filingDate','reportDate','acceptanceDateTime',...,'items',...]`); the XML sits under `https://www.sec.gov/Archives/edgar/data/<cik>/<accession-no-dashes>/<primaryDocument>` (the `primaryDocument` field names the `.xml`). The daily form index (`sec/daily_index.py`) lists the day's Form 4 filers (69,799 "4" lines in 2026 QTR3 `form.idx`).
- **known_from**: the bulk set carries FILING_DATE only (no acceptance time) -> for the backfill use FILING_DATE 17:30 ET as a conservative `known_from` or join the accession to the submissions JSON for the exact `acceptanceDateTime` (a 4 accepted after 17:30 ET is disseminated next morning; treat as the next session's open). Form 4 is due within 2 business days of the transaction (TRANS_DATE != known date; never key on TRANS_DATE).
- Rate limits: 10 req/s with a `User-Agent` naming a contact (https://www.sec.gov/os/accessing-edgar-data); the shared `sec` limiter already does 0.2 s.
- ToS: US government data, free, no restriction. **OK.**
- Quality caveats: SEC disclaims accuracy ("as filed"; filer typos in price/shares are common: filter TRANS_PRICEPERSHARE = 0 or outside the day's range); amendments (4/A) must supersede by accession; derivative exercises (code M) paired with F/S sells are not open-market signals; 10b5-1 plan flag (AFF10B5ONE in SUBMISSION since July 2025) only exists for recent filings.
- Existing coverage: `sec/edgar.py` (submissions JSON, User-Agent, limiter), `sec/daily_index.py` (8-K only today; extend the form filter to "4"). No Form 4 XML parser yet.
- Fallback: FMP `/stable/insider-trading` and Finnhub `/stock/insider-transactions` (free tiers, symbol-gated and no acceptance time; both re-serve EDGAR). Not needed.

### 2. 10-K / 10-Q full text and section extraction

**Recommended: EDGAR full-text (per filing, free) + EDGAR-CRAWLER (GPL-3 toolkit) for item splitting; EDGAR-CORPUS (Apache-2.0) as the 1993-2020 pre-split history; the SEC "Financial Statement and Notes" set for the structured text of notes.**

- Per filing: the `primaryDocument` from the submissions JSON (inline-XBRL HTML). History: full index back to 1994 QTR3 (verified `full-index/1994/QTR3/form.idx` 200). `known_from` = `acceptanceDateTime` (verified field). 10 req/s.
- Full-text search: `https://efts.sec.gov/LATEST/search-index?q=...&forms=10-K&startdt=&enddt=` (verified 200 today; hit fields: `adsh, ciks, display_names, file_date, file_type, form, items, period_ending, root_forms, sics...`; 10 hits a page; covers 2001+; capped at 10,000 results a query, so slice by date). Good for finding filings with a phrase ("going concern", "material weakness"), not for bulk text.
- EDGAR-CORPUS: https://huggingface.co/datasets/eloukas/edgar-corpus , Apache-2.0, 10-K only, 1993-2020, 220,375 filings, 40.7 GB, 20 item fields (`section_1` ... `section_15`, 1A, 7, 7A, 9A...). Card says it "needs further cleaning"; section boundaries fail on non-standard headers. Static (no updates): history only.
- EDGAR-CRAWLER (https://github.com/lefterisloukas/edgar-crawler , GPL-3.0): parses 10-K, 10-Q and 8-K into item JSON. GPL means it runs as a separate tool/process, never imported into `algotrade_sources` (our package is not GPL): run it in ingestion as a subprocess or re-implement the item regexes (they are the well-known "Item 1A." header patterns).
- Financial Statement and Notes data sets: https://www.sec.gov/dera/data/financial-statement-and-notes-data-set , 2009 Q1 to Sept 2026, **monthly** ZIPs since Nov 2020 (consolidated into quarterly after a year), TSV tables `sub, num, txt, pre, tag, ren, cal, dim`; `txt.tsv` holds the text blocks of every note (XBRL TextBlock), so note-level text is available structured without HTML parsing. A filing accepted after 17:30 ET on the month's last day lands in the next month's file: up to ~1 month lag; `sub.accepted` carries the acceptance timestamp for `known_from`.
- ToS: all SEC = **OK**; EDGAR-CORPUS Apache-2.0 **OK**; EDGAR-CRAWLER GPL-3 **OK to run, not to vendor**.
- Caveats: inline XBRL HTML is 2-10 MB a 10-K; store extracted items, not raw HTML; the dataset must never be committed (repo is public; `var/` only).
- Existing coverage: `sec/edgar.py`, `sec/submissions.py`, `sec/company_facts.py`, `sec/statement_concepts.py` (XBRL numbers). No text reader.
- Fallback: FMP `/stable/sec-filings-...` (free tier re-serves EDGAR links only). Not needed.

### 3. FINRA short interest (bi-monthly) and daily short-sale volume

**Recommended: FINRA Query API `otcMarket/consolidatedShortInterest` for short interest; `cdn.finra.org` Reg SHO daily files for short volume.**

- Short interest: `https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest` answered **200 without credentials** today (CSV; fields `accountingYearMonthNumber, symbolCode, issueName, issuerServicesGroupExchangeCode, marketClassCode, currentShortPositionQuantity, previousShortPositionQuantity, stockSplitFlag, averageDailyVolumeQuantity, daysToCoverQuantity, revisionFlag, changePercent, changePreviousNumber, settlementDate`; earliest row seen 2020-04-15; FINRA says one rolling year online and older via archive download). Query API: 1,200 sync req/min/IP, 5,000 rows a request, 500,000 offset cap; POST with JSON filters (`settlementDate`). Register a free **Public** credential at developer.finra.org (an individual account is explicitly for non-commercial use) rather than rely on the anonymous 200.
- **known_from**: FINRA publishes on a fixed schedule: settlement on the 15th and last business day; firms report T+2 18:00 ET; **publication ~T+8 business days** (schedule verified: e.g. settlement 2026-09-30 -> published 2026-10-09; 2026-10-15 -> 2026-10-26; the full 2025-2027 table is at https://www.finra.org/filing-reporting/regulatory-filing-systems/short-interest). Publication is after the close (FINRA posts around 16:00 ET: **unverified**, treat as next session's open). Store `settlementDate` as the as-of and the schedule's publication date as `known_from`; `revisionFlag` marks restatements.
- Daily short volume: `https://cdn.finra.org/equity/regsho/daily/CNMSshvol{YYYYMMDD}.txt` (verified 200 for 2018-08-01 and 2026-10-16; pipe-delimited `Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market`; also FNQC/FNSQ/FNYX/FNRA/FORF per venue). Posted by 18:00 ET on the trade date; occasionally re-posted as "Updated" later. History: 2018-08-01 (consolidated); per-TRF files older. Layout PDF: https://www.finra.org/sites/default/files/DailyShortSaleVolumeFileLayout.pdf .
- ToS: Developer API Equity-data Specific Terms (Dec 2022): data "only for Developer's non-commercial personal or professional use", redistribution only non-commercial with FINRA attribution: **OK for us through a Public credential**. finra.org site Terms of Use (govern the cdn files): forbid "data mining, scraping or harvesting tools", "voluminous, excessive, or repetitive requests", building a database from the site, and **any use "in conjunction with machine learning, neural network" tools**. One file a day from the published download URLs is the intended use, but the ML clause means: never feed FINRA rows to the TextModel seam or any model-training step; flag it in `docs/data/vendors.md`.
- Quality: Reg SHO daily volume covers only off-exchange (TRF/ADF) prints, ~40-50% of volume, so "short volume ratio" is a venue-biased proxy, not short interest; short interest excludes positions below reporting thresholds? (no: all positions) but is only twice a month; days-to-cover uses FINRA's own ADV.
- Existing coverage: none. New vendor `finra` (M).
- Fallback: Nasdaq short-interest pages (ToS: scraping; no), FMP (premium). None free of equal quality.

### 4. Cboe VIX futures history and term-structure indices

**Recommended: Cboe CDN CSVs (free, no key).**

- Indices: `https://cdn.cboe.com/api/global/us_indices/daily_prices/{VIX|VIX9D|VIX3M|VIX6M|VVIX}_History.csv` (307 -> `cdn-api.cboe.com`, curl follows). Verified today: VIX from 1990-01-02 (9,296 rows), VIX9D from 2011-01-04, VIX3M from 2009-09-18, VIX6M from 2008-01-02, VVIX from 2006-03-06 (close only); columns `DATE,OPEN,HIGH,LOW,CLOSE` (VVIX: `DATE,VVIX`), `MM/DD/YYYY`. Last row = yesterday's close (2026-10-16 present on 2026-10-17): updated nightly; publication time **unverified** (fetch in the nightly after 20:00 ET and record the fetch instant as `known_from`; the index close itself is public at 16:15 ET).
- VX futures: per-expiry CSV `https://cdn.cboe.com/data/us/futures/market_statistics/historical_data/VX/VX_{YYYY-MM-DD}.csv` (verified 200 for 2013-01-16, 2014-01-22, 2026-11-18; 403 for 2008/2010: **history starts 2013**; columns `Trade Date,Futures,Open,High,Low,Close,Settle,Change,Total Volume,EFP,Open Interest`). The directory is not listable (403); generate expiry dates from the VIX settlement rule (the Wednesday 30 days before the third Friday of the following month; weeklies too) and skip 403s. Also `cfevoloi.csv` (volume/OI by product since 2004). Settlement files for SOQ: `vix_settlement_series`.
- **known_from**: settle rows are daily; VX daily settlement is published ~16:15 ET; Cboe files are EOD (fetch next morning, `known_from` = fetch).
- Rate limits: none published; these are static S3 objects; one request a file.
- ToS: https://www.cboe.com/terms/ : "You may view, print and download one copy of the Materials for your personal non-commercial use"; no anti-bot clause; redistribution not allowed. https://www.cboe.com/use-of-content/ says any *display/use of Cboe content* needs written approval, which targets republication. **OK for personal research, never redistribute (we never commit vendor data anyway).**
- Quality: pre-2013 VX history is not free (Cboe DataShop / FirstRate paid; IBKR has no expired VX contracts); contract rows before listing show 0 OHLC with a settle; TAS included; VVIX has no OHLC.
- Existing coverage: `cboe/option_chains.py` uses `cdn.cboe.com` delayed quotes (same host, same Http): add `cboe/index_history.py` and `cboe/vx_futures.py` (S/M).
- Fallback: FRED `VIXCLS`, `VXVCLS` (VIX3M), `VXNCLS` (fred adapter exists; daily, 1-day lag) for the indices; IBKR gateway for live VX curve (personal licence, no expired contracts).

### 5. Closed-end fund and BDC daily NAVs

**Recommended: Tiingo EOD on the Nasdaq MFQS NAV symbols (Power plan, adapter exists). Fallback: CEFConnect JSON (ToS forbids automation: no), N-PORT monthly (lagged).**

- CEFs with >= $75 M AUM disseminate daily NAV through Nasdaq's Mutual Fund Quotation Service under an `X<ticker>X` symbol (e.g. PHK -> `XPHKX`, Foxby -> `XFXBX`). Tiingo's `supported_tickers.csv` (already pulled by `tiingo/listings.py`) lists them with `exchange = NMFQS, assetType = Mutual Fund` (verified: `XPHKX,NMFQS,Mutual Fund,USD,2004-03-22,2026-10-15`; 49,880 "Mutual Fund" rows). So the NAV series is `https://api.tiingo.com/tiingo/daily/XPHKX/prices?startDate=` through `tiingo/prices.py`: same endpoint, same licence, history to 2004 for the older funds.
- Mapping CEF -> NAV symbol: the Nasdaq symbol directory `mfundslist.txt` (FTP `ftp.nasdaqtrader.com/symboldirectory/`, 550 today from this network; the HTTPS mirror `nasdaqtrader.com/dynamic/SymDir/mfundslist.txt` returned HTML: **mapping file unverified**); fallback rule: `X` + ticker + `X` and check it exists in Tiingo's listing.
- **known_from**: NAV is struck after the close and disseminated the same evening (MFQS cutoff ~18:00-19:00 ET: **unverified**); Tiingo shows the row the next day (the 2026-10-16 NAV was already `endDate` for XFXBX on 10-17). Use the nightly fetch instant; never use the NAV date.
- BDCs: no daily NAV (quarterly, 10-Q/10-K `NetAssetValuePerShare` via `sec/company_facts.py`; `known_from` = acceptance time). A "BDC premium/discount" edge is therefore quarterly-grained.
- CEFConnect: `https://www.cefconnect.com/api/v3/pricinghistory/ADX/1M` returns JSON NAV/price/discount (verified), but Nuveen's legal page forbids "software or any automatic device... to crawl, scrape, search or monitor" and "data mining, robots": **not OK**.
- N-PORT (`sec/nport_holdings.py` exists): monthly net assets per fund; under the 2024 amendments reports are filed within 30 days of month end and public 60 days after month end (large groups since 2025-11-17, small since 2026-05-18): useful only to audit NAV, 2 months late.
- ToS: Tiingo Power plan, personal: **OK**.
- Quality: MFQS NAVs are issuer-reported (occasional stale values on holidays, restated later); some small CEFs do not publish; Tiingo may lack a few NAV tickers (check `supported_tickers`).
- Existing coverage: `tiingo/prices.py`, `tiingo/listings.py` (asset type "Mutual Fund" currently mapped by `ASSET_TYPES`; confirm it is kept, not dropped). Effort S.

### 6. ETF daily shares outstanding / flows

**Recommended: issuer daily files already pulled (iShares CSV header `Shares Outstanding`, SSGA workbook), stored as a feature; fallback SEC N-CEN (annual) / N-PORT (monthly net assets, 60-day lag). No free API exists for all-issuer daily SO.**

- iShares: the holdings CSV `...ajax?fileType=csv&fileName=IVV_holdings&dataType=fund` carries a header block including `Shares Outstanding,"277,650,000.00"` (verified in the recorded fixture `tests/fixtures/sources/ishares/IVV_latest-holdings.csv`; the adapter `ishares/etf_holdings.py` currently skips those header lines). SSGA `holdings-daily-us-en-<ticker>.xlsx` header rows (`Fund Name:`, `Ticker Symbol:`, `Holdings: As of`): shares outstanding presence **unverified** (SSGA publishes it on the fund page; check the workbook). ProShares `psdlyhld.csv` similar. Vanguard/Invesco: no daily file (N-PORT fallback).
- Flow = delta(SO) x NAV; NAV from the same files (iShares header has `NAV`?: **unverified**) or from Tiingo's ETF NAV symbols (`X<ticker>X`? iShares NAV symbols are `IVV.NV`-style on Nasdaq: **unverified**; CEF-style X..X exists for many ETFs on MFQS).
- **known_from**: issuer files post the next morning (the "as of" date is T, published T+1 before the open); record the fetch instant. SO changes reflect creations settled T+1/T+2: the issuer SO on date T lags primary-market demand by 1-2 days.
- SEC N-CEN: https://www.sec.gov/dera/data/form-ncen-data-sets , quarterly ZIP, `ETF.tsv` (creation unit size, in-kind %, number of APs; creation-unit redemption field since 2024q1): annual, structural only. N-PORT: monthly net assets (see 5).
- Nasdaq: no free SO/flow endpoint found (the one on api.nasdaq.com is undocumented); commercial only (ETF Global, Intrinio, EODHD).
- ToS: issuer sites: already accepted for holdings (`ishares`, `ssga`, `proshares` adapters). **OK.**
- Quality: issuer SO is rounded to creation units; file gaps on issuer outages (carry forward with `carried_from`); a few funds report "as of" T-1.
- Existing coverage: `ishares/etf_holdings.py`, `ssga/workbook.py`, `proshares/etf_holdings.py`: extend the parsers to emit the header fields (S).

### 7. Historical analyst estimates / revisions, point in time

**Recommended: keep FMP (annual `analyst-estimates`, `price-target-consensus`, `grades-consensus`) + Finnhub (`stock/recommendation`) as already probed (ADR 0068) and build the point-in-time history ourselves by storing each nightly snapshot with `knowledge_ts` = fetch. No free source serves historical revisions point in time.**

- FMP Basic: 250 calls/day, EOD data, "150+ endpoints", **no history beyond the current window on Basic** (Starter $19/mo: 5 y; Premium $49: 30 y; transcripts and ETF holdings only on Ultimate $99) (pricing page verified). `period=quarter` is 402 on free (repo probe). Rate: `[fmp] daily_budget = 200`.
- Finnhub free: 60 calls/min (repo), docs show "30 API calls/second" for premium; the OpenAPI spec embedded in finnhub.io/docs/api marks 63 operations "Premium Access Required": a crude scan did **not** flag `/stock/recommendation`, `/stock/eps-estimate`, `/stock/revenue-estimate`, `/stock/earnings`, `/stock/transcripts`, `/stock/insider-transactions`, `/calendar/ipo`, `/stock/price-target`, `/stock/upgrade-downgrade` within 1,200 chars of their path, but the repo probe found `stock/price-target` DENIED and public reports say transcripts are premium: **trust the repo's `analyst/vendor_access` probe, not the scan**.
- **known_from**: the consensus a vendor shows today is the *current* consensus; vendors restate history, so a backfilled "estimate as of D" is not point in time. Only our own nightly snapshots are. Start the snapshots now; the revision features (`eps_rev_30d`, `n_up - n_down`) become usable after 1-3 months of history.
- Free alternative with some history: Finnhub `stock/earnings` (reported EPS vs estimate, surprise, 4+ quarters; the surprise is point-in-time by construction). Zacks/Yahoo pages: ToS forbid scraping.
- ToS: FMP / Finnhub free tiers, personal licence: **OK** (already in `sources.toml`).
- Quality: FMP annual estimates cover ~1,000 symbols on free (symbol-gated); Finnhub recommendation counts lag broker changes by days; neither gives analyst-level revisions.
- Existing coverage: `fmp/estimates.py`, `fmp/targets.py`, `finnhub/recommendations.py`, probe tasks. Effort S (snapshot table + features).

### 8. Earnings call transcripts

**Recommended: company IR webcasts / 8-K Item 2.02 exhibits (prepared remarks, free, PIT) for the nightly; the HF `kurry/sp500_earnings_transcripts` dump (MIT, "research and educational use only", 33,362 transcripts, 685 large caps, 2005-May 2025, speaker-segmented, `date` to the second) for research/backtest history. No free, licence-clean API for full Q&A text exists.**

- Legality: transcripts are copyrighted by the transcriber (Motley Fool, Seeking Alpha, S&P CapIQ). Motley Fool's US ToS URL 404s today; its CA/UK terms forbid bots/scrapers; Seeking Alpha likewise: **not OK to scrape**. The HF dump's `company_id` is a Capital IQ id, i.e. it is a redistribution of S&P content under an MIT label the uploader cannot grant: usable for a private research backtest, **never redistributed or committed**, and not a production feed.
- Free APIs: API Ninjas `/v1/earningstranscript` is **Premium only** (verified page: Developer tier 5 y, archive 2005+ on Business); Finnhub transcripts premium; FMP transcripts on Ultimate ($99/mo); EarningsCalls.dev paid from $24.99/mo; Alpha Vantage `EARNINGS_CALL_TRANSCRIPT` exists on the free key (25 req/day) but is the **cheapest licensed path if a feed is wanted (unverified today)**.
- What is free and point in time: the 8-K Item 2.02 exhibit (press release, `acceptanceDateTime` known) and the 10-Q MD&A; a text-model summary of those through the existing `TextModel` seam gives the "tone" features without transcripts.
- **known_from**: HF `date` is the call time; set `known_from` = call date + 1 day (transcripts post hours later) for backtests.
- Existing coverage: none for transcripts; `sec` source for 8-K/10-Q. Effort L (licensing decision + text pipeline).

### 9. 8-K item history to 2004, NT 10-K/10-Q, SC TO-I, Form 25, S-1 lockups

**Recommended: SEC EDGAR (existing `sec` source): submissions JSON for items + acceptance time; quarterly `full-index/form.idx` for the universe-wide form-type scan; full-text search for the lockup sentence.**

- 8-K items: `submissions` JSON has `items` per filing (verified: `('2026-07-30','2026-07-31T00:30:28Z','2.02,9.01')`), all filings back to the company's first; current item numbering since 2004-08-23 (older 8-Ks use the pre-2004 item numbers: map or cut at 2004). The repo already stores `events/filing` from this (EV1c). Bulk alternative for all CIKs: `https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip` (**unverified today**, documented on the accessing-edgar-data page).
- Form types in `full-index/YYYY/QTRn/form.idx` (verified counts 2026 QTR3: `8-K` 15,273; `NT 10-K` 57; `NT 10-Q` 252; `SC TO-I` 342; `25-NSE` 460; `25` 32; `10-12B` 17; `424B4` 114; `S-1` 247). Index gives form, CIK, filing date, path; acceptance time via submissions JSON or the filing's `-index-headers.html` (`<ACCEPTANCE-DATETIME>`), which the `nport_holdings.py` reader already parses.
- Lockup dates: not a field anywhere free. Derive: EFTS `q="lock-up"&forms=424B4` (verified: 33 hits Sep-Oct 2026, fields incl. `file_date`, `period_ending`), then regex the prospectus for "180 days after the date of this prospectus" (early-release clauses at 90 days on price conditions are common: store the clause, not just the date). stockanalysis.com/ipos/lockups lists derived dates but its ToS was not retrievable (404): do not scrape.
- **known_from**: `acceptanceDateTime` (after 17:30 ET -> next session). Index files are published nightly (`daily-index` 403 until posted; the adapter handles that).
- ToS: SEC **OK**. 10 req/s.
- Quality: NT filings are `NT 10-K` / `NT 10-Q` form types (12b-25); Form 25 is filed by the exchange (`25-NSE`) or issuer (`25`); SC TO-I is the issuer self-tender (exclude `SC TO-I/A` amendments or dedupe); `items` is empty for some 2004-2005 8-Ks.
- Existing coverage: `sec/submissions.py`, `sec/daily_index.py` (8-K only), full-index reader absent. Effort S-M.

### 10. Futures curves for commodity / bond carry

**Recommended: IBKR historical bars through the existing read-only gateway (`licence = "personal"`), for the listed contracts of each root (CL, NG, GC, ZN, ZF, ZB, ES...), settle = daily bar close with `whatToShow=TRADES` (**MIDPOINT** for thin months). Fallback: none free and automated.**

- CME: settlement pages and `CmeWS/mvc/Settlements/...` answered **403 "This IP address is blocked due to suspected web scraping... prohibited by CME Group's website Data Terms of Use"** on the first request: **not OK**. The FTP settle files (`ftp.cmegroup.com/settle`) are being retired to CME DataMine (free only after midnight CT, account required; FAQ page itself blocked for automated fetch).
- Nasdaq Data Link: `data.nasdaq.com/data/CHRIS-...` **404**; the free futures sets (CHRIS/OFDP/SCF) are gone or frozen (WIKI frozen since 2018): **no**.
- Stooq: served a JavaScript proof-of-work challenge to curl: **no**.
- FRED: has a few settlement series (e.g. `DCOILWTICO` spot, not curves): no.
- IBKR TWS API: historical data for futures incl. expired contracts (`includeExpired=True`) typically ~2 years back for expired months (**from the TWS docs, not re-fetched today**), pacing ~60 historical requests per 10 min; daily bars 1 year a request. Curves are rebuilt nightly (all listed months), so history accrues from the day we start; the deep backfill of expired months is limited.
- **known_from**: the settle is final ~17:00 CT; fetch after 18:00 ET; record the fetch instant.
- Quality: IBKR "close" is the last trade, not the exchange settle (differences of ticks on thin months; use `MIDPOINT` or the next day's `open` sanity check); roll adjustments are ours (ADR 0009 `parent_id`, `multiplier`).
- Existing coverage: `ibkr/gateway.py`, `ibkr/market_data.py` (vol history, option quotes; add `futures_bars` key). Effort M. Personal licence: features derived carry `licence = "personal"` (ADR 0028).

### 11. Country-level CAPE / valuation

**Recommended: Barclays Shiller CAPE CSV (free, monthly, 26 countries since 1981-12). Fallback: Siblis Research free tier (28 markets, monthly table from 2006, JSON API no key).**

- `https://indices.cib.barclays/file.app?action=shared&path=shiller/cape.csv` verified today: header `Date,Australia,Brazil,Canada,China,Europe,France,Germany,Hong Kong,Italy,India,Israel,Japan,Korea,Mexico,Netherlands,Poland,Russia,Singapore,South Africa,Spain,Sweden,Switzerland,Taiwan,Turkey,UK,USA`; 538 monthly rows from 31/12/1981 to 30/09/2026 (`DD/MM/YYYY`); 0 before a country's start; Russia `#VALUE!` now.
- Cadence: monthly, posted some days after month end (the 30/09/2026 row was present on 10/17; exact publication day **unverified**: set `known_from` = fetch; the first fetch after month end defines it).
- ToS: the page is a JS app whose terms were not retrievable; the QuantConnect strategy library has used this URL publicly for years. Barclays Indices site terms (**unverified**) are typically "personal, non-commercial": **probably OK, confirm on the site before shipping**; the `published/csv_series.py` adapter pattern fits.
- Siblis: https://siblisresearch.com/data/cape-ratios-by-country/ : 28 markets monthly (table from 2006, US from 1980 in the paid DB), "free API, no key", charts reusable with attribution, full history paid ($349 once / $768/yr). ToS text not retrieved.
- StarCapital: redirected to bellevue.ch (discontinued). Research Affiliates AAI: site now a splash to Syzygy/RAFI (discontinued). Shiller's own data: US only (`ie_data.xls`).
- Quality: Barclays CAPE uses MSCI country indices in local currency, 10-y real earnings; a monthly value is as-of month end; mapping to ETFs (EWA, EWZ...) is ours.
- Existing coverage: `published/csv_series.py` (generic CSV series reader): add the Barclays file as a published series (S).

### 12. IPO calendar with lockup expiry

**Recommended: Nasdaq IPO calendar JSON (already the host of our earnings adapter) for priced/upcoming/filed/withdrawn; lockup expiry derived from the 424B4 (dataset 9).**

- `https://api.nasdaq.com/api/calendar/ipo?date=YYYY-MM` (note: `/api/ipo/calendar` also answered 200 today with `data.priced/upcoming/filed/withdrawn`, rows `dealID, proposedTickerSymbol, companyName, proposedExchange, proposedSharePrice, sharesOffered, pricedDate, dollarValueOfSharesOffered, dealStatus`). Needs a browser-like `User-Agent` and `Accept: application/json` (the `nasdaq/earnings.py` adapter already does this). No lockup field.
- History: by month back several years (**depth unverified**; the earnings endpoint serves 2018). Cadence: intraday updates; fetch nightly; `known_from` = fetch.
- ToS: nasdaq.com terms page not retrievable today (404/timeout); the repo already relies on this host for earnings (ADR 0050 decision): same verdict, **OK by precedent**, keep one request a session.
- Lockup: 180 days from the 424B4 `file_date` (EFTS verified), with the early-release clause parsed; cross-check against the pricing date from Nasdaq. StockAnalysis lists the same derived dates (do not scrape).
- Quality: SPACs and direct listings have different lockups; "upcoming" rows change ticker; dedupe on `dealID`.
- Existing coverage: `nasdaq/earnings.py` (same host/headers). Effort S + the 424B4 parser (M).

### 13. Spin-offs and corporate-action announcements

**Recommended: SEC EDGAR: Form 10 registration (`10-12B`, `10-12B/A`) for spin-offs; 8-K Items 1.01 (agreement), 2.01 (completion of acquisition/disposition), 5.03 (splits via charter), 8.01; S-4 / DEFM14A for mergers; Massive splits/dividends (existing) for the effective data.**

- Sources and PIT: `full-index/form.idx` for `10-12B` (17 in 2026 QTR3), submissions `items` for 8-K item codes, both with `acceptanceDateTime`. When-issued trading and the record/distribution dates come from the Form 10 information statement (text) and the 8-K 8.01 press release; Nasdaq's `TradingSystemAddsDeletes.txt` (symbol directory, intraday) marks the new listing date.
- Existing coverage: `massive/corporate_actions.py` (splits, dividends: effective dates only, no announcement time), `sec/*`. Effort S for the filing flags (an `events/filing` filter), M for parsing dates from the Form 10.
- ToS: SEC **OK**; Massive per existing plan.
- Caveat: Item 2.01 fires on both sides (acquirer and seller) and on asset sales; the Form 10 can be withdrawn (`RW`); spin-off ratio and record date must be parsed from text (TextModel seam, `known_from` = acceptance).

### 14. Congress / political

Skipped per brief.

### 15. Short-seller activist report lists

**Recommended: no licence-clean free compilation exists; build our own ledger from (a) the activists' own sites' RSS/report pages (Muddy Waters, Citron, Fuzzy Panda, Culper, Grizzly, Viceroy, Spruce Point, Hunterbrook: their reports are free and public; Hindenburg closed Jan 2025 with its archive online), (b) 8-K Item 8.01 / press-release responses, (c) the weekly Bear Cave newsletter section "New Activist Reports" (Substack, partly free) read by hand. Fallback: paid (Breakout Point, Activist Insight Shorts / Diligent).**

- Verified: Activist Shorts Research was acquired by Activist Insight (paid); HBS Library holds Activist Insight Shorts data 2013-2018 for named users only; Diligent's 2026 review counts 166 campaigns in 2025 (list behind a download); The Bear Cave archive shows weekly issues "#340-#347" (Aug-Oct 2026) titled "New Activist Reports, Recent Resignations..." with no paywall marker on the archive page (per-issue access **unverified**).
- Academic lists: Brendel & Ryans (2021, JAR) and Appel/Bulka/Fos (2018, HLS forum: 280 campaigns 1996-2015) publish campaign lists in appendices: free, static history for a backtest.
- **known_from**: report publication timestamp (the firm's site/tweet); for a hand-kept ledger the entry time.
- ToS: the activists' sites are public and usually RSS-fed (each has its own terms; Muddy Waters and Hindenburg require a disclaimer click: **unverified per site**); Substack scraping is against Substack ToS: read by hand through the `dossier-import` path (ADR 0050).
- Quality: low volume (~150-170 US campaigns a year), survivorship (firms vanish), and the move is mostly intraday on day 0: an outcome edge needs the publication minute.
- Existing coverage: `dossier-import` skill (owner-run). Effort L (manual) or M (per-site RSS readers).

---

### Ranked table

Rank by (free + ToS clean) x (PIT quality) x (edge value) / effort.

| # | Dataset | Source (fallback) | Cost | Effort | ToS ok? | Ideas it unlocks |
|---|---|---|---|---|---|---|
| 1 | 9. 8-K items / NT / SC TO-I / Form 25 / 424B4 | SEC submissions JSON + full-index + EFTS (existing `sec`) | free | S-M | yes | late-filer (NT) drift, self-tender premium, delisting runoff, lockup-expiry supply, event-class attribution already planned |
| 2 | 1. Form 4 insider transactions | SEC bulk 345 + per-filing XML (`sec`) (FMP/Finnhub) | free | M | yes | cluster buys, CFO/CEO open-market purchases, 10b5-1 vs discretionary, insider-buy after drawdown |
| 3 | 4. VIX futures + VIX9D/3M/6M/VVIX | Cboe CDN CSVs (FRED, IBKR) | free | S | yes (personal) | term-structure regime (contango/backwardation), VVIX/VIX ratio, vol-of-vol hedging rules, VX roll yield |
| 4 | 3. FINRA short interest + daily short volume | FINRA Query API (Public credential) + cdn files | free | M | yes, non-commercial; **no ML use** of the rows | days-to-cover squeezes, short-interest change vs price, off-exchange short-volume ratio regime |
| 5 | 6. ETF shares outstanding / flows | issuer daily files (`ishares`, `ssga`, `proshares`) (N-CEN, N-PORT) | free | S | yes (in use) | flow momentum, sector-ETF creation bursts, crowding, leveraged-ETF rebalance pressure |
| 6 | 5. CEF NAVs (BDC quarterly) | Tiingo EOD on MFQS `X..X` symbols (N-PORT) | paid-already | S | yes | discount z-score mean reversion, year-end tax-loss CEF rebound, BDC premium regime |
| 7 | 11. Country CAPE | Barclays Shiller CSV (Siblis) | free | S | probably (confirm) | country-ETF value rotation, CAPE-regime position sizing |
| 8 | 12. IPO calendar + lockups | Nasdaq IPO JSON + 424B4 parser (none) | free | S+M | yes by precedent | lockup-expiry short / post-expiry rebound, IPO-first-earnings drift |
| 9 | 7. Analyst estimates PIT | FMP + Finnhub snapshots nightly (own history) | free | S | yes | revision breadth, post-earnings estimate drift (usable after ~3 months of snapshots) |
| 10 | 2. 10-K/10-Q text + sections | EDGAR per filing + Notes `txt.tsv` + EDGAR-CORPUS history (EDGAR-CRAWLER as a tool) | free | L | yes (GPL tool stays external) | risk-factor change (1A delta), going-concern / material-weakness flags, MD&A tone via TextModel |
| 11 | 13. Spin-offs / 8-K 2.01 | SEC `10-12B` + items (Massive for effective dates) | free | S-M | yes | spin-off parent/child drift, forced-selling after distribution, M&A completion arbitrage endpoints |
| 12 | 10. Futures curves (carry) | IBKR gateway (personal) (none free: CME/NDL/Stooq blocked) | free, personal licence | M | yes (personal) | commodity/bond carry and roll-yield signals; history accrues from go-live only |
| 13 | 15. Short-seller reports | activists' own sites + Bear Cave by hand (paid: Breakout Point) | free | L | mixed (per site) | day-0 reaction, post-report drift / rebuttal rebound; low volume |
| 14 | 8. Earnings transcripts | 8-K 2.02 exhibits + 10-Q text; HF MIT dump for research only (Alpha Vantage free key as a feed) | free | L | no clean free feed | guidance tone, Q&A hedging language; prefer the press-release path |

Unverified items to close before building: Form 345 readme field names; MFQS `mfundslist.txt` mirror URL; Cboe index CSV publication time; Barclays Indices terms; nasdaq.com terms text; IBKR expired-contract depth; Alpha Vantage transcript endpoint on the free key; Bear Cave per-issue paywall.
