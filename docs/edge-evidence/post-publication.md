# Which setups can be judged on a post-publication basis

Inputs and result for the ADR 0065 amendment 2026-10-25 ("a post-publication basis for setups taken
from published research"; owner decision 2026-10-24). Hand-written, not generated. Written
2026-10-24 from the edge documents, the store of 2026-10-19 / 2026-10-21 (`results/edge_series`, the
official run of each setup, read only) and the papers (a Fable agent per half of the 80 documents,
tables in [part 1](papers-absolute-to-industry.md) and [part 2](papers-insider-to-vrp.md)). No
edge document is edited by this change: `[post_publication]` is added only after the amendment is
accepted, one PR for the setups below.

## How the counts were made

For each setup: the paper's sample end (from the part tables), the declared basis (the screener that
implements the paper's rule, at the horizon nearest the paper's hold), and, from the store's
per-session series of the official run, the **independent sessions measured with at least one pick**
(status `measured`, picks above 0, each weighted by `window_weights` over the slice's own sessions),

- **post**: decision sessions after the sample end and before `frozen_from` (2026-04-01): the
  post-publication window;
- **forward**: decision sessions from 2026-04-01 (the existing forward record, never added to post);
- **first**: the first session with a measurement (the store's own start, or the feature's: bars from
  2010-01-04, statements from about 2020, earnings events from 2018-12, chains from 2026-10).

`min_oos_trades = 40` is the bar. Where the paper's sample ended before `first`, the exact end date
does not change the count (marked "any": the sample-end check can be loose for these).

## The basis is mechanical

`screen` = the document's first `screeners` entry; `horizon` = the horizon of the main variant's `[outcome]`
nearest the paper's holding period (the shorter on a tie). Match levels
(ADR amendment, item 2): `exact`; `one_leg` (one leg of the paper's long-short spread, or the top of its
extreme decile or quintile, same signal, ranking and horizon; equal weighting is never a difference); `close`
(any other named difference: a substituted or partial measure, a window, a proxy, an added filter). `one_leg`
setups are eligible by rule; `close` setups only on the owner's word for that setup and difference.

## A. One leg of the paper's rule: eligible by rule (2)

| Setup (basis screen, horizon) | Paper (sample, confidence) | Paper rule vs ours | post | forward | first |
|---|---|---|---|---|---|
| `c31_lottery_options_short` (`lottery_max`, 20) | Bali, Cakici, Whitelaw 2011, J. Financial Economics (1962-07 to 2005-12, verified; any) | MAX decile spread, 1-month hold vs short the 30 highest | 171 | 5 | 2010-03 |
| `short_squeeze_days_to_cover` (`short_squeeze_dtc`, 20) | Hong, Li, Ni, Scheinkman, Yan 2015, NBER WP (1988-2012, verified) | days-to-cover deciles vs short the 30 highest | 86 | 5 | 2018-01 |

Doubts: `c31`'s thesis source is Boyer and Vorkink but its screener, `[published]` figure and the
registration `source` are Bali, Cakici and Whitelaw's MAX (`source = 0`); its screener is also a trial in
`idiosyncratic_volatility_and_max` (read once); `short_squeeze_dtc` is a short and a working paper; neither has
the trial-log check yet (run at registration).

## B. `close`: eligible if the owner confirms the named difference (12)

| Setup (basis screen, horizon) | Paper (sample, confidence) | The named difference | post | forward | first |
|---|---|---|---|---|---|
| `momentum_12_1` (`momentum_12_1`, 20) | Jegadeesh and Titman 1993, J. Finance (1965-1989, recalled; any) | the paper's formation is 12 months with a 3-month hold and no skip month; ours 12-1, held 20 sessions; top 50 vs decile | 161 | 5 | 2011-01 |
| `net_share_issuance` (`net_share_issuance`, 20) | Pontiff and Woodgate 2008, J. Finance (1970-2003, end recalled; any) | net issuance deciles; ours falls back to the weighted-average share count where the cover count is missing: a different measure; long the 50 most negative | 171 | 5 | 2010-03 |
| `lazy_prices_10k_change` (`lazy_prices_similar`, 20) | Cohen, Malloy, Nguyen 2020, J. Finance (1995-2014, verified) | one of four similarity measures, selected filing items and a 150-day carry, long the 100 most similar vs the quintile of non-changers | 118 (in-sample 44) | 5 | 2010-12 |
| `pre_earnings_runup_winners` (`pre_earnings_runup`, 5) | Aboody, Lehavy, Trueman 2010, Rev. Accounting Studies (1971 to 2005-Q3, verified; any) | ranks by 12-1 momentum, the paper by 12-month return; top 20 vs top decile (one summary says top 1%: verify) | 339 | 25 | 2018-12 |
| `earnings_neutral_reversal` (`pre_earnings_reversal`, 3) | So and Wang 2014, J. Financial Economics (1996-2011, secondary) | the signal is read one session earlier than the paper's days -4..-2; long 20 vs quintile; the document names the wrong journal | 515 | 40 | 2018-12 |
| `earnings_announcement_premium` (`eap_all`, 6) | Frazzini and Lamont 2007, NBER WP (1972-2004, verified; any) | a 6-session window around the expected date vs the paper's calendar month | 286 | 20 | 2018-12 |
| `short_term_residual_reversal` (`residual_reversal`, 20) | Blitz, Huij, Lansdorp, Verbeek 2013, J. Financial Markets (1926-2008, verified) | market-only 20-session residual vs a 36-month Fama-French residual; top 50 | 164 | 5 | 2010-10 |
| `insider_opportunistic_cluster_buys` (`insider_cluster_buys`, 20) | Cohen, Malloy, Pomorski 2012, J. Finance (1986-2007, verified; any) | adds a cluster of 3 filter and ranks by buyer count: a different signal | 148 | 5 | 2012-01 |
| `cash_based_operating_profitability` (`cash_op_profitability`, 60) | Ball, Gerakos, Linnainmaa, Nikolaev 2016, J. Financial Economics (1963-2013 or -2014, secondary) | a stored-line proxy, not the paper's measure; annual signal, 60 sessions | 49 (in-sample 15) | 1 | 2010-04 |
| `composite_mispricing_score` (`mispricing_composite`, 20) | Stambaugh, Yu, Yuan 2015, J. Finance (1965-2011, recalled) | 7 of the 11 anomalies | 160 (in-sample 9) | 5 | 2010-03 |
| `quality_minus_junk` (`qmj`, 20) | Asness, Frazzini, Pedersen 2019, Rev. Accounting Studies (US 1957-2016, verified) | no growth part, three safety parts missing; top 50 vs 30% | 96 (in-sample 72) | 5 | 2010-03 |
| `earnings_date_shift` (`earnings_date_early`, 20) | Johnson and So 2018, J. Financial and Quantitative Analysis (years not found) | scheduled not confirmed date; top 20 advancers; sample years to be found first | 76 | 5 | 2018-12 |

## C. Store too thin today (9: match level assessed when the data is there)

| Setup | Why not now | When it changes |
|---|---|---|
| `asset_growth` (`asset_growth`, 60: an annual signal) | 23 post decisions at the paper's 12-month hold (54 at 20 sessions, which the mechanical rule does not pick); statements only from 2020 | statements backfill to 2010 |
| `small_cap_earnings_drift` (`pead_small_cap`, 60) | 35 post decisions at the paper's 60-day drift (104 at 20); sample unknown; the $2B cap was set the night of the first runs | the sample years, a reading of the cap |
| `turn_of_the_month` (exact), `treasury_month_end_extension` (the rule paper is Hartley and Schwarz, 1990-2018) | calendar edges: outcomes not stored (D0 backfill due 2026-11-09) | after D0: about 190 monthly decisions each from 2010 |
| `dividend_month_premium` (6), `high_volume_return_premium` (2), `short_term_momentum_high_turnover` (0), `reverse_split_distress_filter` (13; 250-session hold) | a feature or its coverage starts late | the backfill or the coverage |
| `c04_option_stock_volume_ratio` | chains only from 2026-10-02: every measured session is forward | never: the window before 2026-04-01 is empty |

## D. Held (2)

`risk_factor_change`: one section of the Lazy Prices paper, not independent evidence from
`lazy_prices_10k_change` (owner decision 5: one setup per paper). `closed_end_fund_discounts`: the closed-end
fund universe was survivors-only before 2026-10-02 ("flatters a discount strategy"): wait for the
survivorship-free universe.

## E. Not eligible (the other 55 of 80)

Forward-only by rule: our own or practitioner setups (`bdc_price_to_nav_reversion`,
`momentum_at_earnings` (built from a harness result, 2026-10-08), `natgas_etf_contango_drag`,
`bond_curve_timing`, `credit_spread_trend`, `dual_momentum_gem`, `earnings_gap_volume_drift`,
`ibs_etf_mean_reversion`, `c17_earnings_iv_crush_sell`, `c18_iv_rank_conditional_selling`, `cef_distribution_trap`, `vix_mean_reversion_entry`,
`volatility_contraction_expansion`, `eight_k_item_drift` (a vendor blog), `sp500_deletions_long`
(a white paper)); a rule that is only loosely the paper's (`absolute_momentum_crash_filter`,
`analyst_revision_momentum`, `anchored_vwap_reversion_retest`, `betting_against_beta_low_vol`,
`commodity_roll_momentum`, `composite_value`, `country_etf_momentum_value`,
`december_losers_reversal`, `distress_failure_probability`, `dual_class_spread_reversion`,
`factor_momentum`, `fx_etf_carry_momentum`, `idiosyncratic_volatility_and_max`, `industry_momentum`,
`late_filer_nt_drift`, `news_conditioned_reversal`, `option_cp_iv_signals` (three papers, three
sample ends, one proxy), `option_expiration_week` (names chosen with hindsight),
`pre_earnings_cp_iv_spread`, `quarter_end_rebalancing`, `retail_options_lottery_attention`,
`target_price_implied_return`, `tender_offer_drift`, `trend_carry_value_combo`,
`tsmom_multi_asset_etf`, `vix_roll_yield`, `vol_managed_equity`, `vrp_short_premium`);
no history at all (`etf_flow_pressure`, `ipo_lockup_expiry`, `thematic_etf_launch_fade`: at most 5
decisions before 2026-04-01); rejected or blocked (`leveraged_etf_rebalancing`, `sp500_index_changes`,
`russell_reconstitution`, `spinoff_drift`, `tdf_contrarian_flows`, `c13_iv_term_structure_straddles`,
`c16_pre_earnings_straddle_buy`, `c12_vrp_cross_section_iv_hv` and `c14_delta_hedged_characteristics`
(IBKR IV from 2024-10: under 20 decisions)). Per-row reasons are in the part tables.

## What the numbers say

- 2 setups are eligible by rule now and 12 more on an owner decision: 86 to 171 independent post-publication
  sessions for the monthly setups, 286 to 515 for the event setups. 9 more meet the rules and wait on data.
- Most paper samples end before the store starts (2010), so the post-publication window is the store's whole
  history up to March 2026. Only `lazy_prices_10k_change`, `quality_minus_junk`, `cash_based_operating_profitability` and `composite_mispricing_score` have an in-sample slice.
- Every post-publication result is affected by the decay the literature measures (McLean and Pontiff); the
  existing haircut display stays beside it, never in the verdict.
- The architect's reviews of the first two drafts found that the setups first listed as eligible did not meet
  the amendment's own definition of a match (a substituted measure, a subset of a paper's measures, a carry
  rule, an added filter); the sort follows the definitions, so only two are eligible by rule.

## Facts the checks found (to fix in the registration PR, not here)

- `earnings_neutral_reversal` names "Journal of Financial Markets" for So and Wang; it is the Journal
  of Financial Economics, 114(1), 20-35.
- The stored verdict rows count decision sessions with no pick as trades (`analyst_revision_momentum`:
  177 sessions, 0 picks). On the post-publication basis that would pass the bar of 40 with no
  evidence; the amendment requires the measured count (ADR item 4).
- `momentum_12_1`'s basis today is chosen in-sample and is a variant; a declared basis is the paper's
  screener.
- Sample ends marked recalled (Jegadeesh and Titman, Pontiff and Woodgate, and others in the part
  tables) are checked against the paper before any `sample_end` is written.
