# Edge ideas, family H. Structural niches and other asset classes

Researched 2026-10-17 (deep-research agents; index and ranking: [README.md](README.md)). Ideas, not edges: nothing here is filed or tested. Figures marked *not verified*, *nv*, *recalled* or *from memory* must be checked against the source before an edge document cites them (quality bar item 5, [edges-plan.md](../edges-plan.md)).


**Family summary.** This family is where an individual's smallness is the edge: trades too small for a fund, too operationally fiddly for an index, or in wrappers (CEFs, BDCs, preferreds, SPACs, dual-class shares, leveraged/volatility ETPs) whose holders are forced by mandate, tax or redemption mechanics. The evidence is strongest where a *same-cash-flow* spread exists (dual-class pairs, CEF/BDC price vs NAV, SPAC trust floor, Treasury-company mNAV) and where a *scheduled forced flow* exists (tender-offer proration, lockup expiry, month-end bond index extension, December tax-loss selling in CEFs); it is weakest for calendar lore in crypto and commodities. The binding constraints for us are (a) NAV series are not stored (CEFs, BDCs only via SEC XBRL), (b) corporate-action event lists (tenders, spin-offs, deals, lockups) must be built from the SEC filing feed we already have, (c) shorting is needed for half the ideas, so each has a long-only or options variant. Realistic individual capacity ranges from $5k per event (odd-lot tenders) to effectively unlimited (country/ETF-level trades); most sit at $20k–$200k per position. Web-search quota was exhausted mid-research (shared budget); numbers marked **(nv)** are from memory and not verified this session.

Ordering is by (evidence strength × feasibility now).

---

### dual_class_spread_reversion — Same-cash-flow dual-class share spread
- **Thesis**: When two share classes of one company with identical dividend rights trade at a spread that is wide versus its own history, the spread closes; hold the cheap class (and short the rich one if you can).
- **Mechanism**: Index membership and ETF demand hit one class (e.g. the voting class in the S&P 500, the other not), option-hedging and retail flow concentrate in the ticker with the options chain; nobody is paid to arbitrage a 1–3% spread with a 6–18-month half-life.
- **Persistence**: Capacity is small (tens of pairs), the carry is negative (borrow) for arbitrageurs, and the convergence date is uncertain, so arbitrage capital stays away (Schultz & Shive's point: round-trip arbitrage is profitable but slow).
- **Rule (source's own)**: Schultz & Shive (2010): when the relative price deviation of the two classes exceeds a threshold vs its moving average, long the cheap / short the rich class, exit on reversion to the mean; they report profits even after bid-ask and borrow for the more liquid pairs **(nv on magnitude)**.
- **Evidence**: Schultz & Shive (2010, JFE) document frequent, exploitable mispricing in US dual-class pairs 1993-2006; Lamont & Thaler (2003, JPE) for the extreme negative-stub cases. Recent: GOOG/GOOGL spread has oscillated roughly ±2% since 2014 and mean-reverts (practitioner observation, nv); conversions/collapses of class structures (e.g. several 2022-2024 recapitalisations) deliver the spread in one jump.
- **Sources**: Schultz, P. & Shive, S. (2010) "Mispricing of dual-class shares: Profit opportunities, arbitrage, and trading", JFE 98(3). Lamont, O. & Thaler, R. (2003) "Can the market add and subtract?", JPE 111(2). Practitioner coverage of the GOOG/GOOGL spread (various, nv).
- **Horizon / schedule**: 20–120 sessions; every_session signal on z-score of the log price ratio.
- **Data needed**: daily bars for both classes (have), a class-pair map (derive from reference/company data: same issuer, both listed; we have FIGI + company snapshots). Nothing missing for the signal; dividend parity should be checked from our dividend table.
- **Individual fit**: capacity $50k–$500k per pair on the liquid pairs; long-only variant = own the cheap class whenever you own the name, and switch when the spread flips (zero extra risk). Shorting the rich class: borrow is cheap on mega-caps.
- **Decoys / overlap**: liquidity premium on the thin class; voting premium around proxy fights or takeover rumours (control events legitimately widen the spread). No overlap with filed edges.
- **Verdict**: Strong / Ready (a pair list is a one-day job).

### bdc_price_to_nav_reversion — BDC price/NAV mean reversion (NAV from XBRL)
- **Thesis**: Business development companies trading at a deep discount to last-reported NAV, with NAV stable or rising, outperform those at premiums over the next quarter.
- **Mechanism**: Retail-dominated holder base buys on yield and sells on dividend cuts; no institutional arbitrage because BDCs are excluded from most indexes (acquired-fund-fee rule drove them out of Russell/S&P in 2014) and are hard to borrow; NAV is only published quarterly so the price drifts away from it.
- **Persistence**: Index exclusion and the 2014 rule are structural; quarterly NAV cadence is regulatory; small sector (~50 listed BDCs, ~$70bn).
- **Rule (source's own)**: No canonical academic rule; practitioner rule (e.g. BDC Buzz / Closed-End Fund Advisors, nv): rank by price/NAV relative to the name's own 3-year average and to peers, long bottom quintile, rebalance quarterly after 10-Q.
- **Evidence**: Closed-end fund literature transfers (Pontiff 1995: a 20% discount predicts ~6%/yr higher 12-month return). BDC-specific published evidence is thin; sector results 2014-2024 show discount dispersion is persistent and discount changes dominate total return differences (nv). Treat the published number as absent.
- **Sources**: Pontiff, J. (1995) "Closed-end fund premia and returns: Implications for financial market equilibrium", JFE 37. Patro, Piccotti & Wu (2017) "Exploiting closed-end fund discounts: a systematic examination of alphas", J. Financial Research **(nv venue)** (Quantpedia summary: 18.2% ann. long-short quintile 1998-2011, Sharpe 1.9, gross). SEC rule background on acquired-fund fees (ICI, nv).
- **Horizon / schedule**: 60 sessions; on_event:10-Q filing (quarterly), re-scored every_session on price.
- **Data needed**: NAV per share = total net assets / shares outstanding from **SEC financial statements** (balance sheet) with `knowledge_ts` = filing date — we store both. BDC list: SIC/filer type from SEC or a hand list. Nothing external required.
- **Individual fit**: long-only is the natural form; capacity $20k–$200k per name; dividends large (QDI/ordinary mix). Shorting premium BDCs is impractical (borrow, dividend owed).
- **Decoys / overlap**: discounts cluster in credit-quality losers (non-accruals rising) — the signal must be conditioned on NAV change; interest-rate beta (floating-rate assets) and small-cap/value exposure.
- **Verdict**: Promising / Ready (needs the NAV-from-XBRL feature; architecturally clean).

### cef_discount_reversion — Closed-end fund discount mean reversion (with the December/January kicker)
- **Thesis**: Buy CEFs at discounts wide versus their own history (and peers), especially in December; discounts narrow over the following months independent of NAV.
- **Mechanism**: Retail holders (CEFs are ~95% retail-held) tax-loss sell in December, buy on yield, and overpay for distribution rate; the discount is a sentiment and liquidity premium (Lee-Shleifer-Thaler 1991; Cherkes-Sagi-Stanton 2009). Fund sponsors do not fix it because the fee base is NAV, not price.
- **Persistence**: Sponsor incentives, retail base, limited borrow on CEFs; arbitrage requires activism (Saba, Bulldog, Karpus) which only reaches a few dozen funds a year.
- **Rule (source's own)**: Pontiff (1995): sort on discount; a 20-point discount implies ~6% higher 12-month return. Patro et al: long top-quintile discount / short bottom-quintile, monthly rebalance, 18.2% ann. gross (1998-2011, Quantpedia). Brauer & Chang (1990): CEF *prices* show a January effect their NAVs do not (tax-loss selling in the wrapper).
- **Evidence**: Pontiff 1995; Patro et al 2017; Brauer & Chang 1990 JF. Post-publication: still present but smaller; UK evidence shows discounts revert within a band rather than to zero (Nottingham DP 03-16). ICI (2024) reports ~three-quarters of CEFs trade at a discount in any month and activism is concentrated in three firms. Recent 2020-2024 academic out-of-sample tests were not found this session.
- **Sources**: Pontiff (1995) JFE. Brauer, G. & Chang, E. (1990) "Return seasonality in stocks and their underlying assets: Tax-loss selling versus information explanations", RFS 3(2). Patro/Piccotti/Wu via Quantpedia (https://vvv.quantpedia.com/?p=563). ICI (2024) "CEF activism" (https://ici.org/files/2024/cef-activism.pdf). Cherkes, Sagi & Stanton (2009) RFS "A liquidity-based theory of closed-end funds".
- **Horizon / schedule**: 60–250 sessions; month_end rebalance; a December-entry variant on_event:tax-year-end.
- **Data needed**: **NAV series not stored.** Sources: fund sponsor sites, CEFConnect (Nuveen, free, scrape terms unclear), SEC Form N-PORT (monthly NAV, public ~60 days later — point-in-time safe but slow). Prices: have. Distribution history: our dividend table.
- **Individual fit**: excellent (retail-sized, no shorting needed, discounts of 10-15% common 2023-2024). Capacity $20k–$100k per fund, hundreds of funds. Costs: spreads 0.3-1% on small funds.
- **Decoys / overlap**: leverage (most CEFs 30% levered) → rate/credit beta; distribution-rate traps (see next idea); interest-rate duration for muni/bond CEFs. Overlaps tax-loss harvesting idea below.
- **Verdict**: Strong / Needs data (NAV: N-PORT or CEFConnect).

### cef_distribution_trap_premium_collapse — Premium CEFs that over-distribute (short / avoid)
- **Thesis**: CEFs trading at a large premium to NAV with distributions exceeding earned income collapse in price when the distribution is cut; avoid or short them, and the premium itself predicts negative price returns.
- **Mechanism**: Retail buys headline yield; return of capital masks NAV erosion; the cut is inevitable when NAV falls far enough (PIMCO PGP/PHK historically at 40-70% premiums; cuts produced -20% to -40% price days, nv).
- **Persistence**: Yield-chasing is behavioural and sponsor-encouraged; shorting premium CEFs is costly (borrow + distribution owed), so arbitrageurs don't lean on it.
- **Rule (source's own)**: Practitioner (Morningstar/CEFA, nv): premium > 10% and distribution coverage < 90% → negative expected price return; exit on any distribution reduction announcement.
- **Evidence**: Case series rather than panel evidence; premium quintile in Patro et al delivers the short leg of the 18% spread (gross). No independent 2018-2025 panel found.
- **Sources**: Patro et al (above). Morningstar CEF research (various, nv). Section 19(a) notices (SEC) as the return-of-capital disclosure.
- **Horizon / schedule**: 60–250 sessions; month_end.
- **Data needed**: NAV (missing, as above), distribution history (have), Section 19(a) notices (SEC filings feed — check we ingest 19a-1 notices; probably not).
- **Individual fit**: long-only = avoidance filter on the CEF idea; short variant small, borrow heavy. Capacity irrelevant for the filter.
- **Decoys / overlap**: it is the mirror of the discount idea; only file as a filter.
- **Verdict**: Promising (as a filter) / Needs data (NAV).

### cef_activist_target_prediction — Front-running CEF activism (13D-able discounts)
- **Thesis**: CEFs with wide discounts, small sponsors, weak takeover defences and approaching term/tender triggers are the ones activists (Saba, Bulldog, Karpus) target; buying the profile ahead of a 13D earns the discount narrowing plus the tender premium.
- **Mechanism**: Boards resist; activists accumulate to 5-25%, force tenders at 98-100% of NAV for 25-50% of shares, liquidations or open-endings; non-activist holders ride along.
- **Persistence**: The activists' own capacity is limited and they move slowly (campaigns run 1-3 years); they publish nothing before the 13D.
- **Rule (source's own)**: No published rule; ICI 2024 describes the pattern (discount is the primary stated reason; three firms dominate). Observable triggers: 13D filing (we have SEC filings), proxy fights (DEF 14A/N-PX), tender announcements.
- **Evidence**: Case evidence (Clough funds tenders for 37.5% of shares, discounts narrowed; BlackRock/Saba settlements 2024-2025 with tenders at ~NAV). Investec/QuotedData criticise value leakage for illiquid funds. No systematic return study found.
- **Sources**: ICI (2024) cef-activism.pdf. Investment News "Activists add tailwinds to closed-end funds" (https://investmentnews.com/?p=71758). QuotedData (2025) Deutsche Numis review (https://quoteddata.com/2025/07/deutsche-numis-where-activist-saba-is-winning-after-taking-less-brash-approach-in-1-3bn-trusts-campaign/).
- **Horizon / schedule**: 250+ sessions; on_event:13D filing for the reactive variant (acts the session after the filing).
- **Data needed**: NAV (missing), 13D/13D-A filings by CEF (SEC filings — have if the feed covers 13D), tender terms (SC TO-I).
- **Individual fit**: perfect for individuals; capacity $10k–$50k per fund; tender participation is a brokerage corporate action.
- **Decoys / overlap**: this is a subset of the discount idea; the incremental alpha is the tender premium. n: ~20-40 campaigns/year → 40 events in 2-3 years.
- **Verdict**: Promising / Needs data (NAV + 13D parsing).

### tender_offer_post_expiry_drift — Fixed-price and Dutch-auction self-tender drift
- **Thesis**: Firms that complete a self-tender (fixed-price or Dutch auction) outperform for 1–3 years after expiry; the cheap entry is the post-expiry dip when arbitrageurs dump un-tendered shares.
- **Mechanism**: Management signals undervaluation with its own money; arbitrageurs who bought for the tender sell the pro-rated remainder at expiry; long-horizon investors are slow to re-rate.
- **Persistence**: Peyer & Vermaelen (2009) show the anomaly survived its 1990 publication; the events are small-cap and infrequent (~20-40 US self-tenders a year), so funds ignore them.
- **Rule (source's own)**: Lakonishok & Vermaelen (1990): buy at the first close after expiry, hold 2 years; abnormal return ~9% for the full sample, ~23% for small firms **(nv)**. Peyer & Vermaelen (2009): 1991-2001 sample confirms positive long-run abnormal returns after tender offers and open-market repurchase announcements, concentrated in firms whose repurchase followed a price drop ("overreaction" hypothesis).
- **Evidence**: Lakonishok & Vermaelen (1990, JF); Peyer & Vermaelen (2009, RFS). Open-market buyback anomaly decayed post-2010 in several studies (Fu & Huang 2016 "The persistence of long-run abnormal returns following stock repurchases and offerings", Management Science: largely gone after 2003). Tender-specific post-2010 evidence not found; assume halved.
- **Sources**: Lakonishok, J. & Vermaelen, T. (1990) "Anomalous price behavior around repurchase tender offers", JF 45(2). Peyer, U. & Vermaelen, T. (2009) "The nature and persistence of buyback anomalies", RFS 22(4). Fu, F. & Huang, S. (2016) Mgmt Sci 62(4).
- **Horizon / schedule**: 250–500 sessions; on_event:tender expiry (SC TO-I/A "final results" filing; first actionable session = the next open).
- **Data needed**: SC TO-I filings and amendments from the SEC filings feed (check coverage: we store 8-K items; need form-type list), shares outstanding drop (have), prices (have).
- **Individual fit**: long-only, small/mid caps, capacity $20k–$100k; combine with the odd-lot idea for the same event.
- **Decoys / overlap**: size and value; momentum reversal; overlaps any "buyback" idea another family may file (variant: tender-only).
- **Verdict**: Promising / Needs data (form-type coverage for SC TO-I).

### odd_lot_tender_priority — Odd-lot priority in oversubscribed tenders
- **Thesis**: Hold ≤99 shares of a company running a tender with odd-lot priority; you are cashed out in full at the tender price while round-lot holders are pro-rated (often <30%).
- **Mechanism**: Issuers pay to eliminate small holders (servicing cost); the priority is written into Rule 13e-4 offers; institutions cannot hold 99-share lots meaningfully.
- **Persistence**: Hard cap on size per account; the SEC has allowed continuous/extended odd-lot offers since 1996; nobody can scale it.
- **Rule (source's own)**: Buy ≤99 shares after the offer announcement when market price < tender price (or low end of a Dutch range) by more than the spread, tender all shares. Historical practitioner tallies: ~38% annualised on tiny capital **(blog estimate, nv)**; J&J/Kenvue 2023 exchange offer: round lots pro-rated at ~23%, odd lots in full (MyMoneyBlog).
- **Evidence**: Mechanism is contractual; realised spreads 1-10% per event, occasionally 20%+ (XBiotech 2020 ~30% projected). Failure mode: issuer amends or cancels; price falls below cost if not tendered.
- **Sources**: SEC Release 34-38068 (1996) odd-lot tender offer amendments (https://www.sec.gov/rules/final/34-38068.txt). MyMoneyBlog, J&J/Kenvue results (https://mymoneyblog.com/johnson-and-johnson-kenvue-odd-lot-arbitrage-deal.html). Old School Value explainer (https://oldschoolvalue.com/investing-strategy/profit-from-special-situations-stock-tenders). The Diff, "Hand-crafted artisanal liquidity provision" (https://www.thediff.co/p/hand-crafted-artisanal-liquidity).
- **Horizon / schedule**: 10–30 sessions; on_event:SC TO-I filing with odd-lot clause.
- **Data needed**: SC TO-I filings parsed for "odd lot" (SEC filings feed + text-model seam), prices (have).
- **Individual fit**: ideal and only for individuals; capacity $1k–$10k per event (99 × price), 10-30 events/year → a few thousand dollars a year. Not a harness edge in the portfolio sense; a free lunch to log.
- **Decoys / overlap**: none; it is a corporate-action rebate, not alpha.
- **Verdict**: Strong (mechanical) / Needs data; worth a small automated alert, not a screener.

### spinoff_post_distribution_drift — Spin-offs after the forced-selling window
- **Thesis**: Buy spun-off entities 1–3 months after distribution (after index deletions and mandate-driven selling), hold 1–3 years; parents also tend to outperform.
- **Mechanism**: Index funds and mandate-constrained holders of the parent receive shares they cannot hold (wrong index, size, sector, dividend) and sell indiscriminately; coverage is thin; incentives of spun-off management improve.
- **Persistence**: Documented since 1993 and still reported in 2000-2022 samples; but spin-off indexes (Bloomberg/S&P US Spin-Off) have had lean stretches (2016-2023, nv), so the premium is lumpy and concentrated.
- **Rule (source's own)**: Cusatis, Miles & Woolridge (1993): spin-offs earn ~+33% 3-year matched-firm excess return, parents ~+18% **(nv exact)**; McConnell, Sibley & Xu (2015): 2001-2013 sample, spin-offs still outperform, parents no longer. CBS thesis (2023): 609 spin-offs 2000-2022, -1.7% in the first 14 trading days, then CAR +12.9% at 12 m, +19.7% at 24 m, +28.5% at 36 m.
- **Evidence**: Cusatis et al (1993) JFE; Desai & Jain (1999) JFE (focus-increasing spin-offs drive it); McConnell, Sibley & Xu (2015) JPM "Spin-offs: still a surprising anomaly?"; Copenhagen Business School master's thesis (2023) (https://research-api.cbs.dk/ws/portalfiles/portal/98732383/1643122_Spin_off_performance_An_unrelenting_anomaly.pdf). Chen-Zimmermann OSAP lists "Spinoff" as a replicated predictor **(nv current t-stat)**. Swedish evidence (2026 thesis) insignificant.
- **Sources**: as above.
- **Horizon / schedule**: 250–750 sessions; on_event:spin-off distribution date + 20 sessions.
- **Data needed**: spin-off event list: Form 10 / 8-K Item 2.01 and new listings in universe snapshots (first bar); we have splits/dividends (a spin-off appears as a special dividend in some vendors). Tiingo history back to 2010 will give ~40+ events.
- **Individual fit**: long-only, capacity unlimited at the large end; ~20-40 US spin-offs/year.
- **Decoys / overlap**: small-cap value tilt; momentum (post-dip reversal); conglomerate discount release. Variant of nothing filed.
- **Verdict**: Promising / Needs data (event list from filings; otherwise Ready once Tiingo history lands).

### ipo_lockup_expiry_pressure — IPO lockup expiration
- **Thesis**: Share prices fall into and on the lockup expiration (~180 days after IPO) as insiders and VCs become free to sell; avoid holding through it, or short/put into it.
- **Mechanism**: A known, dated supply shock; VC funds must distribute; the market under-reacts because the date is in the prospectus but no one is paid to pre-sell.
- **Persistence**: Field & Hanka (2001) → still measurable in 2010s samples (nv); the effect is small (-1% to -3%), so after borrow on fresh IPOs the short is marginal; the *avoidance* is free.
- **Rule (source's own)**: Field & Hanka (2001): -1.5% abnormal return over the 3 days around expiry, volume +40%, larger for VC-backed firms **(nv)**. Ofek & Richardson (2000): similar.
- **Evidence**: Field, L. & Hanka, G. (2001) "The expiration of IPO share lockups", JF 56(2). Ofek, E. & Richardson, M. (2000) NYU WP. Brav & Gompers (2003) RFS on lockup contracting. Recent: 2020-2021 IPO cohort showed large expiry drops (anecdotal, nv).
- **Horizon / schedule**: -10 to +5 sessions; on_event:IPO date + 180 calendar days (known from the S-1; first bar in our universe gives the IPO date).
- **Data needed**: IPO date (first bar; we have universe snapshots), lockup length (default 180 d; exact from 424B4 prospectus text via text-model seam), prices (have).
- **Individual fit**: long-only = avoidance/timing of IPO entries; short via puts on liquid IPOs. Capacity fine.
- **Decoys / overlap**: IPO long-run underperformance in general (Ritter); momentum. Belongs here only as a timing rule.
- **Verdict**: Promising (small, reliable) / Ready for the avoidance version.

### treasury_month_end_extension — Month-end Treasury index duration extension and the "dash for cash"
- **Thesis**: Treasuries rally into month end (and equities sag) as bond index funds extend duration and institutions raise cash for month-end payments; long TLT/IEF the last 2-3 sessions, flat otherwise (equity leg optional).
- **Mechanism**: Index duration jumps at month end when new issues enter and short bonds drop out; passive trackers buy duration mechanically; pension/insurance payments force equity sales and bond purchases before month end (Etula et al).
- **Persistence**: Index rules are public and mechanical; the flow is non-discretionary; Etula et al show it in 1980-2016 data for both equities and Treasuries.
- **Rule (source's own)**: Etula, Rinne, Suominen & Vaittinen (2020, JF) "Dash for cash": equities fall in the last days before month end and rebound in the first days after; Treasuries show the mirror image around the turn of the month. Schwarz (Wharton WP 17-19): end-of-month Treasury coupon strategy with a Sharpe near 1 after transaction costs **(from search summary; paper not read)**.
- **Evidence**: Etula et al (2020) JF 75(1). Schwarz (2017/2019) Wharton Rodney White WP 17-19 (https://rodneywhitecenter.wharton.upenn.edu/wp-content/uploads/2019/12/17-19.Schwarz.pdf). Johnston, Kracaw & McConnell (1991) JF turn-of-month in T-bond futures.
- **Horizon / schedule**: 3-5 sessions; month_end (enter T-3, exit T+1).
- **Data needed**: TLT/IEF/SHY daily bars (have), Treasury rates (have FRED). Nothing missing.
- **Individual fit**: unlimited capacity via TLT; no shorting; cost = 2 ETF trades a month.
- **Decoys / overlap**: equity turn-of-the-month effect (other family may file); Fed-meeting drift; rate trend 2022-2024 dominates the small daily effect.
- **Verdict**: Promising / Ready.

### treasury_auction_cycle — Treasury auction cycle (price dip into auctions, rebound after)
- **Thesis**: Treasury prices dip in the days before a scheduled auction and recover after; buy duration ETFs the day before a 10y/30y auction, sell 2-3 days later.
- **Mechanism**: Primary dealers with limited balance sheet hedge anticipated inventory by shorting the secondary market pre-auction; end-investor capital is slow to absorb supply.
- **Persistence**: Dealer capacity is constrained by regulation (SLR), auctions are scheduled; Collin-Dufresne's discussion questions tradability (repo specialness, microstructure).
- **Rule (source's own)**: Lou, Yan & Zhang (2013, RFS): yields rise 9-18 bp-equivalent into the auction and reverse after; the implied strategy has a Sharpe ~1.5 since 1980 (per discussion). Quantpedia backtest 1998-2008 ~5.7% ann. (secondary). TradeMachine blog: TLT average 0.06%/day in the hold window vs 0.02% random (undisclosed windows, overfit risk).
- **Evidence**: Lou, D., Yan, H. & Zhang, J. (2013) "Anticipated and repeated shocks in liquid markets", RFS 26(8). Collin-Dufresne discussion (https://www.epfl.ch/labs/sfi-pcd/wp-content/uploads/2021/07/Discussion-of-Anticipated-and-Repeated-Shocks-in-Liquid-Markets-2011.pdf). Beetsma et al (2018) ECB WP "Trading ahead of treasury auctions" (https://ideas.repec.org/p/ecb/ecbwps/20182208.html). Ahmad & Steeley UK evidence 1992-2004.
- **Horizon / schedule**: 2-5 sessions; on_event:Treasury auction (calendar published quarterly by Treasury — add to macro calendar).
- **Data needed**: auction calendar (not stored; TreasuryDirect publishes; cheap to add), TLT/IEF bars (have).
- **Individual fit**: unlimited; ETF-level effect is a few bp per event, so spreads matter; realistic net maybe 1-3%/yr on the duration sleeve (nv).
- **Decoys / overlap**: overlaps month-end extension (auctions cluster mid-month, so separable); rate trend.
- **Verdict**: Weak-to-Promising / Needs data (auction calendar).

### new_thematic_etf_fade — New specialized/thematic ETFs underperform after launch
- **Thesis**: Avoid, or short via puts, newly launched specialized/thematic ETFs; their holdings are hyped at launch and lose ~30% risk-adjusted over five years.
- **Mechanism**: Sponsors launch funds on themes at peak attention; the holdings are overvalued at launch (high past returns, media coverage, sentiment); the fund captures extrapolating retail flows.
- **Persistence**: Sponsor economics (fees on hype) and retail extrapolation do not change; the paper is published (RFS 2023) but shorting thin ETFs is costly, so decay should be slow.
- **Rule (source's own)**: Ben-David, Franzoni, Kim & Moussawi (2023, RFS): specialized ETFs earn about -30% risk-adjusted over the first five years after launch (sample ~1993-2019, nv exact); not explained by fees or hedging demand.
- **Evidence**: Ben-David, Franzoni, Kim & Moussawi (2023) "Competition for Attention in the ETF Space", RFS 36(3), 987-1042 (NBER w28369, https://www.nber.org/papers/w28369). 2021-2024 cohort (ARK clones, crypto-equity, AI themes) consistent anecdotally.
- **Sources**: as above; Alpha Architect summary (https://alphaarchitect.com/competition-for-attention-in-the-etf-space/).
- **Horizon / schedule**: 250-1250 sessions; on_event:ETF first bar (we see new listings in universe snapshots), classification "specialized" by holdings concentration/name via text-model seam.
- **Data needed**: ETF universe with first-bar date (have from 2024-10; Tiingo history extends), holdings (iShares/SSGA only — thematic launches are mostly other sponsors; need a classification proxy, e.g. ETF name keywords + sector concentration of top holdings where available).
- **Individual fit**: long-only version = never buy an ETF younger than 3 years with a theme name (a filter); short version via puts where listed; capacity small on the short.
- **Decoys / overlap**: it is largely "short recent winners / high-sentiment stocks" (overlaps a sentiment/momentum-crash family); size.
- **Verdict**: Strong evidence, Promising feasibility / Ready as a filter; short variant Needs data (holdings beyond iShares/SSGA).

### retail_lottery_option_flow — Retail lottery-option buying predicts negative stock and option returns
- **Thesis**: Single names whose short-dated OTM call volume spikes relative to open interest (retail lottery demand) have negative subsequent stock and delta-hedged call returns; sell those calls / avoid the stock.
- **Mechanism**: Retail buys lottery-like OTM short-dated calls through PFOF wholesalers; market makers hedge, pushing the stock up transiently (gamma), then unwind; the options are overpriced (Byun & Kim).
- **Persistence**: Retail preference for skewness is stable; wholesalers internalise, so institutions see the flow only indirectly; capacity per name is small.
- **Rule (source's own)**: Byun & Kim (2016, JFE): calls with lottery-like features (high IV, OTM, short maturity) earn significantly lower returns; Bryzgalova, Pavlova & Sikorskaya (2023, JF): retail option volume (identified by the wholesaler's "price improvement" prints) rose to >60% of small trades 2019-2021 and retail lost money in aggregate (nv number). Pan & Poteshman (2006, RFS): put-call volume ratios predict stock returns.
- **Evidence**: Byun, S.-J. & Kim, D.-H. (2016) "Gambling preference and individual equity option returns", JFE 122(1). Bryzgalova, Pavlova & Sikorskaya (2023) "Retail trading in options and the rise of the big three wholesalers", JF 78(6). Pan & Poteshman (2006) RFS 19(3). Ni, Pearson & Poteshman (2005) JFE on pinning/hedging effects.
- **Horizon / schedule**: 5-20 sessions; every_session from EOD chain volume/OI.
- **Data needed**: Cboe EOD chain volume/OI, IV, skew (have): build "OTM short-dated call volume / OI" and "call volume share" features. Trade-level data not needed for a proxy.
- **Individual fit**: short calls/sell call spreads on liquid names; capacity $10k–$50k per name; long-only = avoid names in the top decile.
- **Decoys / overlap**: short-term reversal; momentum; overlaps the filed VRP (short options) — this is a *cross-sectional* selector for it, propose as a variant.
- **Verdict**: Promising / Ready (features from existing chain data).

### mnav_treasury_company_premium — Crypto treasury-company premium to NAV (MSTR-type)
- **Thesis**: Companies whose value is mostly a crypto treasury (MSTR and 2025 imitators) trade at a premium to the mark-to-market value of their coins (mNAV) that mean-reverts; long IBIT / short the company when mNAV is high, unwind near 1.
- **Mechanism**: Retail and some institutions pay for leverage and index inclusion (MSTR in Nasdaq-100 since Dec 2024), and for the convertible-issuance "yield"; the company issues equity at the premium (ATM) which pulls it back; shorts are constrained by borrow and volatility.
- **Persistence**: Supply response (ATM issuance) is the reversion mechanism and is the company's stated policy; premium regimes last months; a stable niche since 2021.
- **Rule (source's own)**: Practitioner (mNAV dashboards, nv): mNAV = market cap / (BTC held × price); long/short when mNAV > its 1-year z-score of +1, exit at the mean. Peer cases: GBTC premium/discount (collapsed from +40% to -45% 2021-2023, closed at ETF conversion Jan 2024).
- **Evidence**: No academic study yet; the GBTC episode is the structural precedent (NAV arbitrage closed only when the wrapper changed). Numbers of MSTR premium history not verified this session.
- **Sources**: MSTR 8-K filings (BTC holdings, we store 8-K items); Grayscale GBTC history (various, nv); Volmex Labs (2024) "The Impact of Spot Bitcoin ETFs" (https://volmex.finance/The%20Impact%20of%20Spot%20Bitcoin%20ETFs.pdf) for ETF-era microstructure.
- **Horizon / schedule**: 20-120 sessions; every_session (mNAV from latest 8-K holdings × spot price); knowledge_ts = 8-K filing.
- **Data needed**: BTC holdings per company from 8-K items (have 8-K items; extract with text-model seam), BTC price via IBIT/BTC daily (have ETFs; spot BTC series needed — FRED has CBBTCUSD), market cap (have shares outstanding).
- **Individual fit**: shorting MSTR is feasible (large cap, borrow usually cheap but volatile), or buy puts; capacity $20k–$200k. Long-only variant: hold IBIT instead of MSTR when mNAV is high.
- **Decoys / overlap**: it is partly a short-vol/short-momentum bet; convertible issuance dynamics; the n of independent episodes is small (one dominant name until 2025).
- **Verdict**: Promising / Ready for MSTR only; the cohort needs 2025-2026 history to reach 40 events.

### spac_trust_floor_yield — SPAC trust arbitrage (post-2022)
- **Thesis**: Buy SPAC common below trust value per share and redeem (or sell on deal announcement); the floor is cash in T-bills, so the return is T-bill yield plus the discount, with a free option on deal pops.
- **Mechanism**: Sellers are IPO funds and arbs cycling capital; buyers are scarce for sub-$10 shares of a shell; the redemption right is contractual.
- **Persistence**: 2021-2022 glut collapsed; 2023-2024 issuance near zero, 2025 revival (nv count); the trade's yield compresses whenever arbs return. Structural but cyclical.
- **Rule (source's own)**: Practitioner (CMC Markets/Opto explainer; Yusko): buy at < trust/share, redeem at the vote; yield = (trust − price)/price annualised over months to deadline. Spamann & Guo (Yale JREG): buyers at ≥$10 who do not redeem lose systematically — the edge is the redemption.
- **Evidence**: Klausner, Ohlrogge & Ruan (2022, Yale J. on Reg.) "A sober look at SPACs": pre-deal arbs earn ~11.6% annualised 2019-2020 cohort **(nv)**; post-merger holders lose. 2023-2025 realised data not found this session.
- **Sources**: Klausner, Ohlrogge & Ruan (2022). Spamann & Guo "The SPAC Trap" (https://www.yalejreg.com/wp-content/uploads/Spamann-Guo-Essay_Final.pdf). CFA Institute comment letter 2022 (https://rpc.cfainstitute.org/-/media/documents/comment-letter/2020-2024/20220210.pdf). CMC/Opto "Demystifying SPAC arbitrage" (https://cmcmarkets.com/en/opto/demystifying-the-art-of-spac-arbitrage).
- **Horizon / schedule**: 60-500 sessions; every_session screen on price vs trust/share; on_event:redemption deadline.
- **Data needed**: trust value per share from 10-Q balance sheet (we store SEC financials: "cash held in trust" / shares subject to redemption), SPAC identification (SIC 6770), redemption dates (8-K / DEF 14A). Mostly derivable from stored SEC data.
- **Individual fit**: long-only, no shorting; capacity $10k–$100k per SPAC; redemption through the broker is a corporate action; warrants add asymmetric upside.
- **Decoys / overlap**: it is a T-bill with a call option; the alpha is the discount (0.5-3%/yr over bills in normal times, more in dislocations like 2022).
- **Verdict**: Weak-to-Promising (yield small, event-driven) / Needs data (trust/share feature, SPAC list).

### merger_arb_cash_deals_individual — Merger arbitrage in announced cash deals
- **Thesis**: Buy targets of announced all-cash deals at a spread, hold to close; diversified across deals the spread exceeds break losses.
- **Mechanism**: Target holders sell on announcement (mandate, risk aversion); arbitrage capital is limited and regulatory risk is unpriceable by most; spreads widen in stress (2008, 2020, 2022-2023 FTC era).
- **Persistence**: HFRI ED Merger Arb has lived on for 30 years; alpha has eroded (Mitchell & Pulvino 2001 found ~4%/yr alpha 1963-1998; FactorResearch finds 1.0-2.6% CAGR across vehicles 2009-2020); 2025 YTD +8.2% to September (AllianceBernstein) on faster closes and fewer breaks.
- **Rule (source's own)**: Mitchell & Pulvino (2001, JF): long target, (short acquirer in stock deals), hold to resolution; returns resemble a short put on the market. Individual version: cash deals only, size by spread/annualised and by deal risk (regulatory, financing, vote), max 5% per deal.
- **Evidence**: Mitchell & Pulvino (2001) "Characteristics of risk and return in risk arbitrage", JF 56(6). Baker & Savaşoglu (2002) JFE. FactorResearch (2020) via hedgefundalpha (https://hedgefundalpha.com/strategies/merger-arbitrage-arbitraged-away/). AllianceBernstein (Dec 2025) "Merger arbitrage: riding the wave into 2026" (https://www.alliancebernstein.com/americas/en/institutions/insights/investment-insights/merger-arbitrage-riding-the-wave-into-2026.html). LPL (2025) "Merger arbitrage rebound".
- **Horizon / schedule**: 60-250 sessions; on_event:8-K Item 1.01 (merger agreement) + press release; first actionable = next session's open.
- **Data needed**: deal terms (price, consideration type, expected close) — from 8-K 1.01 text and DEFM14A via the text-model seam (we store 8-K items; need the text); prices (have). Completion outcome labels from 8-K 2.01/delisting (have universe snapshots).
- **Individual fit**: long-only in cash deals; capacity $20k–$500k per deal in mid/large caps; costs low; the risk is a 20-40% break loss, hence diversification (need ~15 live deals).
- **Decoys / overlap**: short-put market exposure (spreads blow out in crashes); the 2025 spread narrowing partly reflects lower rates (spreads are rate-plus). No filed overlap.
- **Verdict**: Promising (modest, rate-plus 2-5%) / Needs data (deal-term extraction).

### tax_loss_selling_december_reversal — December tax-loss selling in losers and the January rebound (incl. CEFs)
- **Thesis**: Stocks (and CEFs) with large year-to-date losses are sold in the last weeks of December by taxable investors and rebound in early January; buy the losers in the last 5-10 sessions of December.
- **Mechanism**: Taxable individuals and advisors (direct-indexing/tax-loss-harvesting programmes are now huge) realise losses before year end; the wash-sale rule delays repurchase 31 days; mutual funds' October fiscal year-end adds an October wave.
- **Persistence**: Tax law; the effect migrated to microcaps and to the last trading days; Grinblatt & Moskowitz (2004) show it is a tax-loss effect in losers, not a generic January effect; still visible in small/micro losers post-2010 (nv); larger in CEFs where NAV does not move (Brauer & Chang 1990).
- **Rule (source's own)**: Grinblatt & Moskowitz (2004, JFE): past-year losers earn high January returns driven by December tax-loss selling; Sikes (2014, JAE) institutional window dressing/tax-loss by quarter-end; Brauer & Chang (1990): CEF prices show January effect, NAVs do not.
- **Evidence**: Grinblatt & Moskowitz (2004) "Predicting stock price movements from past returns: the role of consistency and tax-loss selling", JFE 71. Sikes, S. (2014) J. Accounting & Economics 57. Brauer & Chang (1990) RFS. Chaudhuri, Burnham & Lo (2020, FAJ) estimate tax-loss-harvesting alpha ~1%/yr for harvesters — the growth of harvesting programmes should strengthen December selling (nv). Recent decay evidence for large caps: strong; for micro caps: weak decay (nv).
- **Horizon / schedule**: 10-20 sessions; on_event:calendar (Dec 15 → Jan 10).
- **Data needed**: daily bars (have), YTD return (have), market cap/liquidity (have); CEF NAV for the CEF variant (missing). The 2024-10 start gives one December; Tiingo history gives ~15.
- **Individual fit**: long-only, small/micro caps, capacity $5k–$50k per name; spreads 1-2%.
- **Decoys / overlap**: short-term reversal and illiquidity; "January effect" generically; overlaps the CEF discount idea (December entry).
- **Verdict**: Promising / Ready (equities), Needs data (CEF variant).

### country_etf_momentum_value — Country ETF/ADR momentum and value
- **Thesis**: Rank single-country ETFs on 12-1 momentum and on CAPE/value; hold the top third, rebalance monthly; both factors work at the country level and are reachable via US-listed ETFs.
- **Mechanism**: Slow diffusion of macro information across borders, home bias, benchmark-hugging institutions; ETF wrapper lets an individual hold what institutions hold through mandates.
- **Persistence**: Asness, Liew & Stevens (1997) → Asness, Moskowitz & Pedersen (2013) "Value and momentum everywhere" (country indices Sharpe ~0.4-0.6 each, higher combined, nv exact) → Faber (2012) global CAPE. Post-publication decay modest; country momentum crashes in reversals (2009, 2020).
- **Rule (source's own)**: Asness et al (2013): monthly, 12-1 month return rank and book-to-price rank across country indices, long top third/short bottom third; long-only variant top third vs equal-weight.
- **Evidence**: Asness, Moskowitz & Pedersen (2013) JF 68(3). Asness, Liew & Stevens (1997) JPM. Faber, M. (2012) "Global value" (Cambria WP). Rapach, Strauss & Zhou (2013, JF) US returns lead other countries monthly (gradual diffusion).
- **Horizon / schedule**: 20 sessions; month_end.
- **Data needed**: country ETF daily bars (have, iShares country ETFs), CAPE per country (not stored; Barclays/Research Affiliates publish, or compute from MSCI earnings — missing). Momentum version: Ready.
- **Individual fit**: unlimited capacity, long-only fine, costs tiny.
- **Decoys / overlap**: FX moves (country ETFs are unhedged); overlaps the filed 12-1 momentum (variant: country level; say so).
- **Verdict**: Promising / Ready (momentum), Needs data (CAPE).

### vix_futures_basis_etp — VIX futures basis / roll-yield via ETPs
- **Thesis**: When the VIX futures curve is in steep contango, short VIX ETNs/ETFs (VXX, VIXY) or hold SVIX; when in backwardation, step aside or go long; the basis predicts the ETP's return.
- **Mechanism**: Insurance demand keeps front VIX futures above spot most of the time; long-vol ETPs roll daily at a loss (VXX lost >99.9% since 2009, split-adjusted, nv); their holders are retail and hedgers who accept the carry.
- **Persistence**: Structural variance risk premium (already filed as short puts); the *ETP* form is persistent because the products exist for hedgers and gamblers; tail risk (Feb 2018 XIV -96%, Mar 2020) is the price.
- **Rule (source's own)**: Simon & Campasano (2014, J. Derivatives) "The VIX futures basis: evidence and trading strategies": short front VIX futures when basis (front minus spot) > threshold (e.g. +0.1 points/day of roll), long when strongly negative, with hedging in ES; Sharpe > 1 in 2007-2011 **(nv)**. Alexander & Korovilas (2013) on ETN roll losses.
- **Evidence**: Simon & Campasano (2014) JOD 21(3). Alexander & Korovilas (2013) "Volatility exchange-traded notes: curse or cure?", J. Alternative Investments. Whaley (2013) "Trading volatility: at what cost?" JPM. Post-2018: SVXY delevered to -0.5x; SVIX (2022) -1x returned; carry remained positive 2023-2024 ex-Aug 2024 spike (nv).
- **Horizon / schedule**: 5-20 sessions; every_session on the basis.
- **Data needed**: VIX futures term structure (not stored; Cboe publishes free daily CSVs — small add). Our SPX IV term structure is a partial proxy (IV30 vs IV90 slope). ETP bars: have.
- **Individual fit**: short VXX borrow is usually available but can spike; SVIX long is the retail-safe form; capacity $10k–$100k; options on VXX/UVXY for defined risk.
- **Decoys / overlap**: this IS the filed VRP in another wrapper; file as a variant whose selector is the basis, not IV-HV.
- **Verdict**: Promising (as a VRP variant) / Needs data (VIX futures curve).

### fx_etf_carry_momentum — G10 FX carry and momentum via currency ETFs
- **Thesis**: Hold the high-yield currency ETFs (FXA, FXC historically; now mostly USD vs funders) and avoid/short low-yield ones (FXY, FXF); add 12-month momentum; rebalance monthly.
- **Mechanism**: Forward-rate bias (UIP failure): crash-risk and capital-flow premia paid by hedgers and central banks who are not profit-maximising.
- **Persistence**: Carry has worked for 40 years with crashes (2008); post-2010 returns weak in G10 (near-zero rate dispersion); 2022-2025 rate dispersion revived it (nv). ETF wrapper costs 0.40% and tracks poorly on the yield component.
- **Rule (source's own)**: Menkhoff, Sarno, Schmeling & Schrinko (2012, JF): sort on forward discount, long top/short bottom, monthly; carry Sharpe ~0.6-0.9 pre-2008 **(nv)**; momentum (Menkhoff et al 2012 JFE): 1-12 month returns, monthly.
- **Evidence**: Menkhoff, Sarno, Schmeling & Schrinko (2012) "Carry trades and global foreign exchange volatility", JF 67(2); (2012) "Currency momentum strategies", JFE 106(3). Lustig, Roussanov & Verdelhan (2011) RFS. Post-publication: Jensen-Kelly-Pedersen factor data show FX carry weak 2010-2020 (nv).
- **Horizon / schedule**: 20 sessions; month_end.
- **Data needed**: FX ETF bars (have: FXE, FXY, FXB, FXA, FXC, FXF, UUP), policy rates/short rates (FRED, have). Nothing missing.
- **Individual fit**: capacity unlimited; long-only = overweight high-carry ETFs vs UUP; shorting FXY cheap. The ETF fee drag is material relative to ~2-4% carry.
- **Decoys / overlap**: dollar beta; equity beta of carry (risk-on). No filed overlap.
- **Verdict**: Weak-to-Promising / Ready.

### reverse_split_distress_filter — Reverse splits and the Nasdaq penny-delisting cycle
- **Thesis**: Stocks that reverse-split to cure a sub-$1 bid-price deficiency underperform for 1-3 years; exclude them from any long screen and consider them a short/put basket.
- **Mechanism**: Compliance-driven splits signal distress, continued dilution (ATMs resume once the price is above $1), and index/retail abandonment; Nasdaq rule changes (2024-2025) tightened cures for repeat offenders, accelerating delistings.
- **Persistence**: Firms must split or delist; the dilution machine (ATM equity lines) is the business model of micro-cap biotech/SPAC remnants; shorting is costly so prices stay too high.
- **Rule (source's own)**: Kim, Klein & Rosenfeld (2008, Financial Review): reverse-split firms earn ~-15% to -20% 3-year abnormal returns, worse for those near delisting thresholds **(nv exact)**; Han (1995) JFQA liquidity effects; Neuhauser & Thompson (2016) on compliance splits.
- **Evidence**: Kim, S., Klein, A. & Rosenfeld, J. (2008) "Return performance surrounding reverse stock splits: can investors profit?", Financial Management 37(2) **(nv journal)**. Nasdaq Listing Rule 5810(c)(3)(A) amendments 2024-2025 (nv details). Record counts of reverse splits in 2023-2024 (practitioner tallies, nv).
- **Horizon / schedule**: 250-750 sessions; on_event:split with ratio < 1 (we store splits).
- **Data needed**: splits (have), prices (have), shares outstanding (have — detects post-split dilution). Nothing missing.
- **Individual fit**: long-only = exclusion filter (free); short/puts: borrow often 20-100%+, so mostly infeasible except via puts on the few with options.
- **Decoys / overlap**: it is distress/low-price/high-issuance; overlaps any share-issuance anomaly another family files; size.
- **Verdict**: Promising (as filter) / Ready.

### share_issuance_dilution_drift — Net share issuance (ATM/secondaries) predicts negative returns [adjacent]
- **Thesis**: Firms with large increases in shares outstanding over the past 12 months underperform; firms shrinking share count outperform (composite issuance).
- **Mechanism**: Managers issue when overvalued and buy back when cheap; retail and index buyers absorb issuance without demanding a discount.
- **Persistence**: One of the most robust anomalies in Chen-Zimmermann and Hou-Xue-Zhang; decayed but alive post-2005 (McLean-Pontiff shrinkage ~50%, nv).
- **Rule (source's own)**: Pontiff & Woodgate (2008, JF): 12-month log change in split-adjusted shares; Daniel & Titman (2006, JF): 5-year composite issuance; annual/monthly rebalance; long low issuance / short high.
- **Evidence**: Pontiff & Woodgate (2008) JF 63(2); Daniel & Titman (2006) JF 61(4); Fama & French (2008) "Dissecting anomalies" JF; Chen & Zimmermann OSAP "ShareIss1Y"/"ShareIss5Y" replicated.
- **Horizon / schedule**: 250 sessions; month_end.
- **Data needed**: shares outstanding (have), splits (have). Ready.
- **Individual fit**: long-only (low/negative issuance) works; capacity unlimited.
- **Decoys / overlap**: not in this family's list — included as adjacent because it is the mechanism behind reverse splits, SPAC remnants and SEOs; another family (fundamentals/quality) may file it — coordinate.
- **Verdict**: Strong / Ready (if not filed elsewhere).

### post_bankruptcy_equity — Post-Chapter-11 new equity
- **Thesis**: Newly issued equity of firms emerging from Chapter 11 is dumped by creditors who received it and thereafter outperforms (or, per other studies, continues to fail): the evidence is mixed, so test both.
- **Mechanism**: Distressed-debt holders receive equity they are not mandated to hold and sell into thin, uncovered markets; no analyst coverage for months.
- **Persistence**: Creditor mandates persist; sample is small (10-30 emergences/year listed), so funds specialising are few.
- **Rule (source's own)**: Eberhart, Altman & Aggarwal (1999, JF): 131 firms 1980-1993, large positive abnormal returns in the 200 days after emergence (median ~+25%, mean much higher, nv) ; Hotchkiss (1995, JF): post-emergence operating underperformance; Jory & Madura (2010): mixed long-run returns (nv).
- **Evidence**: Eberhart, A., Altman, E. & Aggarwal, R. (1999) "The equity performance of firms emerging from bankruptcy", JF 54(5). Hotchkiss, E. (1995) "Postbankruptcy performance and management turnover", JF 50(1). Jory & Madura (2010) "The long-run performance of firms emerging from Chapter 11 bankruptcy", Applied Financial Economics (nv).
- **Horizon / schedule**: 200 sessions; on_event:emergence (8-K Item 1.03 / plan effectiveness; relisting first bar).
- **Data needed**: 8-K items (have), relistings (universe snapshots), prices (have; many trade OTC first — OTC not in scope).
- **Individual fit**: long-only, capacity $10k–$50k, illiquid; n reaches 40 only with the Tiingo history.
- **Decoys / overlap**: distress beta, size, illiquidity; mixed evidence.
- **Verdict**: Weak / Needs data (emergence list; OTC coverage).

### natgas_etf_contango_drag — Short the roll in natural gas ETPs (UNG, BOIL)
- **Thesis**: UNG and 2x BOIL bleed from contango roll and (for BOIL) volatility decay; short them, or hold puts, especially in seasonal contango windows (post-winter).
- **Mechanism**: Natural gas has steep seasonal contango; the ETP must roll monthly; its holders are retail speculators on weather; storage economics ensure contango most of the year.
- **Persistence**: UNG has lost ~95%+ since 2007 (split-adjusted, nv); the structure is unchanged; borrow on UNG/BOIL is available but spikes; February/December cold snaps cause +50% rallies (the risk).
- **Rule (source's own)**: Quantpedia-type "term structure effect in commodities" (Gorton, Hayashi & Rouwenhorst 2013; Erb & Harvey 2006): short contango contracts, long backwardated; applied via the single ETP: short when the front-second spread is in contango beyond cost of carry.
- **Evidence**: Erb & Harvey (2006) FAJ "The strategic and tactical value of commodity futures"; Gorton, Hayashi & Rouwenhorst (2013) RF; Guedj, Li & McCann (2011) "Futures-based commodity ETFs" JIndex Investing on roll losses in UNG/USO; UNG long-run drawdown (nv).
- **Horizon / schedule**: 20-60 sessions; month_end around roll dates; seasonal (Mar-Oct).
- **Data needed**: UNG/BOIL/KOLD bars (have), Henry Hub futures curve (not stored; IBKR possible; EIA/FRED has spot only). Proxy: UNG vs spot NG from FRED (DHHNGSP) drift.
- **Individual fit**: shorts need borrow (UNG 1-5%, BOIL higher, nv); puts on UNG are liquid; capacity $10k–$100k.
- **Decoys / overlap**: it is short commodity vol + short carry; overlaps the leveraged-pair decay idea; gasoline/crude versions weaker (USO curve flatter post-2020).
- **Verdict**: Promising / Needs data (futures curve for the trigger; price-drift version Ready).

### gasoline_seasonality_etf — Gasoline (UGA) spring seasonality
- **Thesis**: Gasoline futures rally from February to April/May ahead of driving season and the summer-blend switch; long UGA in that window.
- **Mechanism**: Refinery maintenance and the RVP specification change tighten supply predictably; hedgers (refiners, airlines) are not seasonal-return maximisers.
- **Persistence**: Reported in Quantpedia's gasoline seasonality and in practitioner seasonals (MRCI); modest Sharpe; 2020 and 2022 outliers.
- **Rule (source's own)**: Quantpedia "Gasoline seasonal strategy": long RBOB from ~Feb 1 to ~Apr 30 (nv dates), flat otherwise; backtest ~8-12% ann. (nv).
- **Evidence**: Quantpedia (nv); Mitchell & Thompson type seasonality studies on energy futures (nv); UGA's roll cost erodes part of it.
- **Horizon / schedule**: 60 sessions; on_event:calendar (Feb 1).
- **Data needed**: UGA bars (have). Ready, but n = 1 so far in our data; Tiingo history gives ~15 seasons (well under 40 events).
- **Individual fit**: long-only, capacity unlimited for an individual.
- **Decoys / overlap**: crude oil trend; one event per year → cannot reach 40 events for decades.
- **Verdict**: Weak / Ready but fails the n ≥ 40 bar.

### leveraged_pair_decay_short — Short both legs of a 2x/-2x or 3x/-3x pair (multi-month)
- **Thesis**: Both legs of a leveraged bull/bear pair lose to volatility drag; shorting equal dollars of both earns the drag minus borrow in range-bound, high-vol regimes.
- **Mechanism**: Daily reset: drag ≈ -0.5·N·(N-1)·σ² per period; retail holds these products for weeks; the sponsor's rebalancing is mechanical.
- **Persistence**: Structural, but the bear leg's borrow (often 5-30%+ on SQQQ/SOXS, nv) and trending markets (one leg explodes) take most of it; CXO: +46% (SSO/SDS) and +16% (QLD/QID) over Jul 2006–Oct 2011 assuming zero net borrow, no rebalancing.
- **Rule (source's own)**: CXO Advisory (LeCompte): short equal dollars of 2x and -2x at inception, hold; returns positive when realised vol is high, negative when low (quintile analysis), R² vs VIX ~0.
- **Evidence**: CXO (https://www.cxoadvisory.com/short-selling/shorting-leveraged-etf-pairs/). Cheng & Madhavan (2009) JII "The dynamics of leveraged and inverse ETFs". Avellaneda & Zhang (2010) SIAM J. Fin. Math. IBKR notes that inverse leveraged ETFs usually carry borrow fees. Frenzy Capital dashboard (https://www.frenzycap.com/leveraged-etfs) lists 655 products; "borrow rates on the bear leg are usually the binding constraint".
- **Horizon / schedule**: 60-250 sessions; every_session monitoring; rebalance when one leg exceeds 2x the other.
- **Data needed**: ETF bars (have), realised vol (have). Borrow fees: **not stored** (IBKR could supply).
- **Individual fit**: borrow-constrained; margin on short leveraged ETFs is heavy (100%+ at IBKR, nv); capacity $10k–$50k. Options alternative: sell straddles on the underlying — which is just the filed VRP.
- **Decoys / overlap**: short gamma/variance = filed VRP; the already-rejected intraday LETF rebalancing is a different (intraday) effect.
- **Verdict**: Weak after costs / Needs data (borrow fees); file as a VRP variant at most.

### mining_equity_beta_fade — Bitcoin miners vs BTC (short miners / long IBIT)
- **Thesis**: Listed BTC miners (MARA, RIOT, CLSK) are 1.5-3x beta to BTC but underperform BTC over time because of dilution, halving-driven margin compression and operating leverage; pair long IBIT / short a miner basket beta-neutral.
- **Mechanism**: Miners fund capex with ATM equity (dilution); the halving halves revenue every ~4 years; retail buys miners as "levered BTC" and overpays for the beta.
- **Persistence**: Dilution is the business model; shorts are costly (borrow 5-20%, nv) and squeezes are violent, so the discount persists.
- **Rule (source's own)**: Practitioner (nv): beta-hedged pair rebalanced monthly; condition on net issuance (our shares outstanding). No academic source found.
- **Evidence**: Anecdotal 2021-2025: miners lagged BTC after the 2024 halving while BTC made new highs (nv); counterexamples when AI-datacenter pivots re-rated some miners (2024-2025). Not verified.
- **Horizon / schedule**: 20-120 sessions; month_end.
- **Data needed**: bars (have), shares outstanding (have), BTC price (IBIT bars / FRED). Ready.
- **Individual fit**: shorting miners is possible but expensive; long-only = own IBIT instead of miners (an avoidance rule). Capacity $20k–$100k.
- **Decoys / overlap**: it is the share-issuance anomaly plus a sector; momentum crashes.
- **Verdict**: Weak-to-Promising / Ready (as issuance-conditioned pair).

### btc_cme_basis_carry — CME bitcoin cash-and-carry via ETF + futures
- **Thesis**: Long IBIT/FBTC and short CME (micro) BTC futures captures the futures premium (annualised 5-15% in 2024 bull phases, near zero in bear phases, nv) with no price risk.
- **Mechanism**: Leverage demand from longs who cannot or will not hold spot pushes futures above spot; balance sheet for arbitrage is limited (the 2021-2024 "basis trade" in GBTC/ETFs).
- **Persistence**: Cyclical with speculative demand; well known; compresses quickly when arbs enter (early 2024 ETF launch saw 15-20% annualised then <5%, nv).
- **Rule (source's own)**: Practitioner: enter when annualised basis > T-bill + 3%, roll quarterly; exit when basis < T-bill.
- **Evidence**: Cboe/CME research notes and NYDIG commentary (nv); Schmeling, Schrimpf & Todorov (2023, BIS WP) "Crypto carry" documents a large, time-varying crypto futures basis driven by speculative demand (perpetuals on offshore venues, with CME lower).
- **Horizon / schedule**: 60-90 sessions (to expiry); on_event:basis threshold.
- **Data needed**: CME BTC futures settlement (not stored; IBKR possible), spot (FRED/IBIT). Needs data.
- **Individual fit**: feasible with IBKR micro BTC futures ($0.1 BTC) + IBIT; margin and roll operations; returns are carry, not alpha; capacity $10k–$500k.
- **Decoys / overlap**: it is a money-market substitute; the "edge" is a liquidity premium with blow-up risk at the broker (margin calls on the short futures leg in a spike).
- **Verdict**: Weak (carry, not alpha) / Needs data (futures).

### prediction_market_macro_signal — Kalshi/Polymarket probabilities as macro and event features [adjacent]
- **Thesis**: Market-implied probabilities for CPI/Fed/jobs prints and earnings outcomes (Kalshi) are better calibrated than consensus and move earlier; use the gap between prediction-market probability and economist consensus as a surprise-direction feature for macro-day positioning.
- **Mechanism**: Contracts aggregate dispersed information continuously; economist surveys are stale (collected days before) and herd.
- **Persistence**: Markets are thin (hundreds of thousands of dollars per contract, nv), so informed traders cannot move them much, and price discovery leaks.
- **Rule (source's own)**: No published rule yet for Kalshi macro contracts; election-market literature (Berg, Nelson & Rietz 2008) shows IEM beat polls ~74% of the time (nv). For CPI: compare Kalshi implied distribution to Bloomberg consensus.
- **Evidence**: Berg, Nelson & Rietz (2008) "Prediction market accuracy in the long run", Int. J. Forecasting. Wolfers & Zitzewitz (2004) JEP. Kalshi/Polymarket 2024-2025 macro calibration: not peer reviewed; not verified.
- **Horizon / schedule**: 1-2 sessions; on_event:macro release.
- **Data needed**: Kalshi API (free, public), Polymarket Gamma API (free); not stored; would be a new vendor (add-data-source). History short (Kalshi CPI markets since ~2022).
- **Individual fit**: as a *feature*, not a trade; individuals can also trade the contracts (regulated, Kalshi) — capacity tiny.
- **Decoys / overlap**: overlaps the macro-surprise family; the gap vs consensus may just be a later snapshot of the same information.
- **Verdict**: Weak as an edge, Promising as a data feature / Needs data (new source).

### preferred_call_and_exdiv — Preferred stocks: call-date traps and ex-dividend capture
- **Thesis**: (a) Preferreds trading above par within 12 months of first call have negative expected return (yield-to-call < 0 after the drop to par); exclude them and prefer sub-par "busted" preferreds with high yield-to-call. (b) Preferred ex-dividend price drops are less than the dividend, so holding across ex-dates earns a small premium.
- **Mechanism**: Retail buys on current yield and ignores call risk; issuers call rationally when rates fall; PFF (the dominant ETF) buys mechanically on index rules. Ex-div: tax clienteles and illiquidity.
- **Persistence**: Retail base and ETF mechanics are stable; academic evidence is thin; the ex-div capture margin is sub-1% per event and spread-eaten.
- **Rule (source's own)**: Practitioner (Quantum Online / Innovative Income Investor, nv): rank by yield-to-worst, exclude YTC < 0; dividend capture: buy T-1 close, sell T+1 (nv). No peer-reviewed rule.
- **Evidence**: Bildersee (1973) JF on preferred pricing; Linn & Pinegar (1988) JFE on preferred issuance; ex-dividend literature for common (Elton & Gruber 1970) with weak preferred extensions (nv). Little recent.
- **Horizon / schedule**: ex-div: 2 sessions, on_event:ex-date; call trap: filter.
- **Data needed**: do our Tiingo bars include preferred tickers (e.g. "BAC-PL" conventions)? **Unknown — verify.** Call dates and par from prospectuses (not stored). Dividends (have if the tickers are covered).
- **Individual fit**: excellent for income portfolios; capacity $10k–$100k per issue; spreads 0.2-1%.
- **Decoys / overlap**: rates and credit; tax-adjusted ex-div is near zero. Mostly a hygiene filter.
- **Verdict**: Weak / Needs data (preferred coverage, call dates).

### adr_country_lead_lag — US close predicting Asia-listed ADRs next day
- **Thesis**: The US session's move predicts next-day returns of Asian markets and hence Asian ADRs' overnight component.
- **Mechanism**: Time-zone sequencing and gradual information diffusion (Rapach et al 2013 monthly; daily cross-correlations strongest at lag 1 for Asia after US).
- **Persistence**: But the ADR itself trades in US hours and already embeds the US close; Kang & Leung (2016) show ADR intraday returns reflect US conditions and overnight returns reflect the home market — the predictable part is already in the ADR price by the US close. Country-ETF studies find predictability of *NAV* returns, not of ETF price returns after costs; a Japan-sector replication found daily turnover costs consumed the alpha.
- **Rule (source's own)**: Regress next-day Nikkei/HSI on today's S&P (positive coefficient); trade via EWJ/ADRs at the US close — the same close that already contains the signal.
- **Evidence**: Kang & Leung (2016) "Information diffusion of Asian ADRs" (nv venue). Rapach, Strauss & Zhou (2013) JF. arXiv cond-mat/0103397 cross-correlations. Asia-Pacific country ETF prediction study (2023, Investment Analysts Journal, https://www.informahealthcare.com/doi/abs/10.1080/10293523.2023.2208904).
- **Horizon / schedule**: 1 session.
- **Data needed**: ADR/ETF bars (have).
- **Individual fit**: daily turnover kills it; capacity fine, costs fatal.
- **Decoys / overlap**: stale-NAV illusions; this is the classic "international mutual fund timing" that was arbitraged (2003 scandals) and then closed by fair-value pricing.
- **Verdict**: Dead for ETF/ADR prices (alive only for unhedgeable local closes) / Out of scope.

### etf_closure_liquidation — ETF closure/liquidation announcements
- **Thesis**: Announced ETF liquidations force the sale of holdings and cause the ETF to trade at a discount during wind-down; buy the discounted ETF (redeemed at NAV) or the pressured holdings.
- **Mechanism**: Holders sell on the news; market makers widen spreads; the final NAV distribution is contractual.
- **Persistence**: ~100-250 US ETF closures a year (2023-2025, nv) but almost all are tiny (< $50m), so capacity is trivial; Romero-Pérez (2013) finds market makers created shares just before liquidation to capture a premium — i.e. the mispricing is small and already harvested by APs.
- **Rule (source's own)**: none published; practitioner guidance only.
- **Evidence**: Romero-Pérez (2013) Forum Empresarial (https://dialnet.unirioja.es/descarga/articulo/6230252.pdf); U. Alabama dissertation "Three essays on ETFs" (https://ir.ua.edu/handle/123456789/2957); practitioner explainers.
- **Horizon / schedule**: 10-30 sessions; on_event:liquidation press release.
- **Data needed**: closure announcements (not stored; press releases/497 filings), NAV (iNAV not stored).
- **Individual fit**: capacity $1k–$20k; discounts 0.5-3% at best.
- **Verdict**: Weak / Needs data; not worth building.

### stub_holdco_sotp_discount — Holdco / stub discounts (sum-of-parts)
- **Thesis**: Holding companies trade at 15-40% discounts to the market value of their listed stakes; buy the holdco / short the stakes when the discount is wide vs history; extreme negative stubs close fast.
- **Mechanism**: Tax on unrealised gains, governance discount, no catalyst; the extreme cases (Palm/3Com 2000) are short-sale-constrained.
- **Persistence**: Discounts persist for decades (Berkshire excepted); reversion is slow and catalyst-driven (spin, buyback, liquidation); US listed-holdco universe is small (Loews, Icahn Enterprises, Liberty complex, Brookfield BN/BAM, Jefferies/others), so n < 40 pairs.
- **Rule (source's own)**: Lamont & Thaler (2003): negative stubs revert when the lockup/spin completes; Mitchell, Pulvino & Stafford (2002, JF) "Limited arbitrage in equity markets": 82 negative-stub cases 1985-2000, most close within months but with large interim risk and ~30% terminated before convergence (nv exact).
- **Evidence**: Mitchell, Pulvino & Stafford (2002) JF 57(2). Lamont & Thaler (2003) JPE. Cornell & Liu (2001) JCF.
- **Horizon / schedule**: 120-500 sessions; every_session on discount z-score.
- **Data needed**: cross-holding stakes (13D/13G, 10-K text — needs the text-model seam over filings we have), prices (have).
- **Individual fit**: long holdco only is fine; shorting the stakes is cheap for large caps; capacity $20k–$200k.
- **Decoys / overlap**: value; conglomerate discount; n too small for the harness.
- **Verdict**: Weak (n) / Needs data (stake map).

### muni_cef_december — Muni CEF December discount widening (variant of cef_discount_reversion)
- **Thesis**: Municipal bond CEFs' discounts widen into late December on retail tax-loss selling and leverage fears and narrow in January; buy the last week of December.
- **Mechanism**: Pure retail holder base; NAV is stable so the price move is all discount; brokers push tax swaps in December.
- **Persistence**: Tax calendar; sponsors (Nuveen, BlackRock) do not buy back meaningfully.
- **Rule (source's own)**: Brauer & Chang (1990) seasonality in CEF prices vs NAV; practitioner (Nuveen/CEF Advisors, nv): average muni CEF discount widens ~1-3 points in December and recovers by February (nv).
- **Evidence**: Brauer & Chang (1990) RFS; Starks, Yong & Zheng (2006, JF) "Tax-loss selling and the January effect: evidence from municipal bond closed-end funds" — the cleanest test: muni CEFs show a January effect in prices tied to tax-loss selling, with the magnitude related to the prior-year loss **(venue/claims from memory, nv)**.
- **Horizon / schedule**: 20 sessions; on_event:calendar (Dec 20 → Jan 20).
- **Data needed**: muni CEF list (derive from names), bars (have), NAV (missing but not strictly needed for the price-return test).
- **Individual fit**: long-only, capacity $10k–$50k per fund, ~100 funds; tax-exempt income.
- **Decoys / overlap**: rate moves in December (FOMC); subset of cef_discount_reversion.
- **Verdict**: Promising / Ready (price-only test; ~15 Decembers with Tiingo history, each with ~100 funds — events are not independent across funds, so count Decembers).

### bitcoin_etf_flow_and_dow — Spot BTC ETF flows and day-of-week effects
- **Thesis**: (a) Spot ETF net flows predict next-day BTC/IBIT returns; (b) BTC has day-of-week/weekend effects an IBIT holder can exploit (Monday open gap).
- **Mechanism**: (a) ETF flows are a demand shock settled T+1, visible after the close; (b) weekend liquidity thinness.
- **Persistence**: (a) NYDIG (2024) shows flows are largely explained by prior-day turnover (≈29% of prior-day turnover), i.e. flows follow volume/price — a momentum proxy, and the direction is the unknown; (b) 2011-2019 DOW effects (Monday, Tuesday, Sunday) were marginal (10%/5% significance) and weekend volume share has collapsed to ~16% (Fineqia H1 2024), so the weekend-gap story is weakening; CXO's 2014-2025 DOW results are paywalled.
- **Rule (source's own)**: none robust.
- **Evidence**: NYDIG (2024) "Predicting bitcoin ETF fund flows" (https://www.nydig.com/research/predicting-bitcoin-etf-fund-flows). Applied Finance Letters (2020) crypto anomalies (https://ojs.aut.ac.nz/applied-finance-letters/article/view/266). CXO Advisory bitcoin DOW (paywalled, https://cxoadvisory.com/calendar-effects/bitcoin-day-of-the-week-effects). Volmex Labs (2024).
- **Horizon / schedule**: 1-5 sessions.
- **Data needed**: ETF flows (shares outstanding × NAV daily — we may have shares outstanding for ETFs via ProShares/iShares data; otherwise Farside), spot BTC (FRED CBBTCUSD).
- **Individual fit**: IBIT is unlimited capacity; daily turnover costs.
- **Verdict**: Weak / Needs data (flows); the DOW variant Dead.

---

## Rejected on sight

- **Convertible arbitrage for individuals** — needs bond access, cheap borrow, delta-hedging and financing; Mitchell-Pedersen-Pulvino (2007) show it is a hedge-fund capital trade; individuals get the ETF (CWB) beta only. Out of scope.
- **ADR premium vs home market (BABA/9988, A-H premium)** — HK/US fungible ADRs trade within fees; the A-H premium is not tradable from the US (no A-share shorts); individuals get nothing.
- **OTC uplistings** — OTC prices not in our universe; event n small; evidence anecdotal.
- **ETF fee wars** — fee cuts move flows, not returns; no return edge; the only effect (cheaper holding) is not an edge.
- **REIT index inclusion / dividend aristocrat additions and removals** — index-addition effects are below 1% since 2010 (Greenwood & Sammon, already rejected for the S&P); aristocrat index AUM too small to move prices; removal = dividend cut, which is its own event.
- **Nasdaq-100 December reconstitution** — same mechanism as the rejected S&P 500 additions; QQQ demand pre-announced; no distinct evidence.
- **MLP / K-1 avoidance structures** — a tax-drag story (AMLP's C-corp tax), not a return anomaly; MLP-to-C-corp conversion events n < 40.
- **Rights offerings in equities** — rare in the US; CEF rights offerings are dilutive negatives already captured by the CEF discount idea.
- **Dutch-auction tenders as a separate idea** — folded into tender_offer_post_expiry_drift (same filings, same drift).
- **Bitcoin halving cycles** — four events; cannot reach 40; narrative-fitted.
- **IBIT premium/discount** — creation/redemption keeps it within a few bp; nothing to trade.
- **TIPS breakeven timing and coupon reinvestment** — breakeven mean reversion is a macro call with ~monthly independence and no published individual-level edge; coupon reinvestment is not a return anomaly.
- **Crack spreads via ETFs** — no crack-spread ETP exists (CRAK is refiner equities); needs futures.
- **US-close → Asia next-day via ETFs/ADRs** — see adr_country_lead_lag: the signal is already in the US price; fair-value pricing killed the fund-timing version in 2003.
- **Weekend BTC gap via IBIT** — IBIT's Monday open already reflects the weekend; the gap is not a return.
- **Spin-off "forced selling day-one short"** — the -1.7% first-two-weeks dip is too small after borrow on a newly listed name; use the post-dip long only.
- **Intraday leveraged-ETF rebalancing** — already rejected (intraday, weak after costs).
- **Grayscale trust discounts (GBTC-era)** — closed by ETF conversion Jan 2024; the surviving small trusts (ETC/GSOL/GDLC) are too small and premium-driven; n tiny.
- **CEF IPO fade (buy never at IPO)** — strong historical evidence (Weiss 1989; Peavy 1990) but CEF IPOs have nearly stopped since 2022; n in the test window < 10.
