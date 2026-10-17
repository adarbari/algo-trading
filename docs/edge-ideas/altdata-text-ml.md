# Edge ideas, family F. Alternative data, text, LLM and ML

Researched 2026-10-17 (deep-research agents; index and ranking: [README.md](README.md)). Ideas, not edges: nothing here is filed or tested. Figures marked *not verified*, *nv*, *recalled* or *from memory* must be checked against the source before an edge document cites them (quality bar item 5, [edges-plan.md](../edges-plan.md)).


Research date 2026-10-17. Web search budget for the session was exhausted part-way (shared cap); items marked
"(recalled, not verified)" come from memory of the paper and need a citation check before an edge document is
written. Numbers without that tag were read from the abstract, an NBER/arXiv page, the Chen-Zimmermann signal
documentation CSV, or a secondary summary found in this session (source given).

**Family summary (5 lines)**
1. The best-evidenced, individual-feasible ideas in this family are *filing-text* and *economic-link* lead-lags built
   from EDGAR filings we already store or can fetch free: 10-K/10-Q change ("Lazy Prices"), text-based peer momentum
   (TNIC-style), conglomerate / customer links extracted from 10-K text, 8-K item-coded drift, SEC comment letters.
2. Analyst-link and news/LLM ideas are strong in the literature (shared-analyst momentum alpha 1.68%/mo; LLM headline
   scores) but need data we lack (per-analyst coverage, a news feed, call transcripts) and the LLM ones are decaying
   fast with adoption; they are "Needs data" at best.
3. Alternative data proper (satellite, card panels, web traffic, app downloads, Glassdoor, job postings) is priced
   for institutions, licensed against redistribution, and its alpha is short-horizon and crowded: Out of scope
   except as a lesson about what institutions already know before earnings.
4. ML cross-sectional prediction (Gu-Kelly-Xiu and successors) works as a *composite scorer over known signals*, not a
   new edge; after costs and ex-microcaps most of its spread vanishes (Avramov-Cheng-Metzker). Use ML as a ranking
   tool inside the harness, never as a thesis.
5. Meta-literature is unanimous: expect 26% out-of-sample / 58% post-publication decay (McLean-Pontiff), demand
   t > 3 (Harvey-Liu-Zhu), and keep one-sided monthly turnover under ~50% or costs eat it (Novy-Marx-Velikov);
   for an individual the surviving set is low-turnover, small-cap-tilted, long-only-able signals.

---

## Ideas (ordered by evidence strength x feasibility)

### lazy_prices_10k_change — Filing-text change ("Lazy Prices")
- **Thesis**: Firms that quietly rewrite their 10-K/10-Q (especially risk factors, litigation, executive language) underperform firms whose filing is nearly unchanged from last year's; the market ignores the change until a later event reveals it.
- **Mechanism**: Investors and analysts do not read 200-page filings diff-wise; managers change language only when something changed (legal, operational, management), so an edit is costly-to-see bad news. No one is forced — it is inattention plus processing cost.
- **Persistence**: Reading every filing diff is tedious; the signal is slow (returns accrue over the following quarters, no announcement-day effect), so fast money is uninterested; the long leg (non-changers) is boring and un-crowded.
- **Rule (source's own)**: Each quarter compute a document similarity (cosine / Jaccard / minimum-edit, on the full text or Item 1A/Item 3/Item 7) between the firm's current 10-K/10-Q and the same form one year earlier. Sort into quintiles; long the most similar (non-changers), short the least similar (changers); hold 3 months (quarterly rebalance, portfolio formed after the filing date).
- **Evidence**: Cohen, Malloy, Nguyen, *JF* 2020 (NBER w25084): sample 1995-2014, long non-changers / short changers earns up to 188 bp/month alpha (>22%/yr); returns accrue only when the information surfaces later (news, earnings), no filing-day reaction; changes also predict earnings, profitability, news and bankruptcy. Post-publication: Harvard Magazine (2019) quotes the authors saying it has been replicated several times; a QuantConnect note (Sun, 2024, Brain Language Metrics data) builds a long-only version but reports no decay estimate; I found no independent post-2014 decay number — **unknown decay** (assume the McLean-Pontiff 58% haircut => ~70-80 bp/mo gross, still large). Vendors (Brain, Snowflake Cortex write-ups) sell the signal, which argues for some crowding at the large-cap end.
- **Sources**: NBER w25084 https://www.nber.org/papers/w25084 ; Harvard Magazine 2019 https://www.harvardmagazine.com/2019/04/stock-market-efficiency-investors ; QuantConnect research 20966 https://www.quantconnect.com/research/20966/filing-language-stability-as-a-selection-signal/ .
- **Horizon / schedule**: 60 sessions (one quarter); on_event:filing (10-K/10-Q acceptance date, act next session) with quarterly portfolio refresh.
- **Data needed**: Full text of 10-K/10-Q (EDGAR full-text, free; we store filing events but not bodies -> add a filings-text table), a similarity feature per filing (`filing_similarity_1y@v1`); daily bars (have). Section parsing (Item 1A/3/7) optional but is where the paper says the signal lives.
- **Individual fit**: Long-only variant (top-similarity quintile) is explicitly reported as earning positive abnormal returns; quarterly turnover is low (survives costs by the Novy-Marx-Velikov < 50%/mo rule); capacity irrelevant for us. Shorting changers is the bigger half of the spread but needs borrow in small names.
- **Decoys / overlap**: Changers are smaller, more volatile, more distressed and more likely to have had bad momentum: control for size, momentum, volatility, and the 8-K count. Overlaps with `risk_factor_section_change` (below, a sub-signal) and with our 8-K event-sensitivity work.
- **Verdict**: **Strong** historically, decay unknown; feasibility **Needs data (10-K/10-Q full text ingestion + similarity feature)** — the cheapest big win in this family.

### risk_factor_section_change — Item 1A risk-factor additions
- **Thesis**: New or expanded risk factors in the 10-K predict lower returns and higher volatility; dropped risks predict the reverse.
- **Mechanism**: Lawyers force disclosure of newly material risks (SEC Reg S-K Item 105), so an *added* risk factor is a legally vetted, under-read bad-news signal; boilerplate growth hides it.
- **Persistence**: Same inattention as Lazy Prices; the boilerplate makes diffs look noisy, so most readers stop.
- **Rule (source's own)**: Campbell, Chen, Dhaliwal, Lu, Steele, *RAST* 2014 (recalled, not verified): count/length and novelty of Item 1A risk factors vs prior year; higher unexpected risk disclosure -> higher subsequent return volatility and beta; Cohen-Malloy-Nguyen say the risk-factor section is one of the three sections where their change signal concentrates. Trade as a filter inside Lazy Prices: among "changers", those whose change is in Item 1A / litigation / executive language.
- **Evidence**: Information-content evidence is solid (market reacts, volatility rises); stand-alone return predictability is weaker than the full-document signal (recalled). Treat as a refinement rather than its own edge.
- **Sources**: Campbell et al. 2014 *Review of Accounting Studies* (not fetched); Cohen-Malloy-Nguyen 2020 (above); Loughran-McDonald 2011 *JF* word lists (background).
- **Horizon / schedule**: 60 sessions; on_event:filing.
- **Data needed**: Item 1A text parsed per 10-K (same ingestion as above) + LLM classification of added paragraphs (our text-model seam: "new material risk vs boilerplate").
- **Individual fit**: Same as Lazy Prices.
- **Decoys / overlap**: Bigger firms write more risk factors; control for filing length; overlap with Lazy Prices (sub-signal).
- **Verdict**: **Promising** as a refinement; **Needs data** (section parsing). Do not file separately until Lazy Prices is in.

### tnic_text_peer_momentum — Text-based (10-K product description) peer momentum
- **Thesis**: When a firm's *hidden* product-market peers (similar 10-K business descriptions but a different SIC code) rally, the firm follows over the next month.
- **Mechanism**: Investors see SIC/GICS peers; they do not see that a software firm's real competitor is classified as "business services". Shocks to low-visibility peers diffuse slowly.
- **Persistence**: Requires building a text network from 10-Ks; the peers with the most alpha are exactly the ones that classification data misses; the spread is 1-month so turnover is high (cost-heavy) which keeps big money out.
- **Rule (source's own)**: Hoberg-Phillips, *JFQA* 2018 "Text-Based Industry Momentum": build TNIC peers from 10-K Item 1 cosine similarity (annual), keep peers *outside* the firm's SIC-3; signal = prior-month return of those peers; long top / short bottom decile; monthly rebalance.
- **Evidence**: Shocks to less visible text peers generate economically large momentum profits and dominate own-firm momentum; SIC-based peers give only small, short-lived profits (abstract). Original profit magnitude not read in this session (recalled as ~1%/mo for the low-visibility peer portfolio, not verified). A 2024 *Financial Markets and Portfolio Management* paper ("Hidden Neighbours", price-correlation + text networks) reports 18.16%/yr, Sharpe 0.85 for 2013-2022 out of sample — a different construction, but evidence the family survived post-publication.
- **Sources**: Hoberg & Phillips 2018 https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/textbased-industry-momentum/6E04891A7AD30C24C21CBDE37EC06BF4 ; Hidden Neighbours 2024 https://link.springer.com/article/10.1007/s11408-024-00455-4 ; TNIC data (academic, free) https://hobergphillips.tuck.dartmouth.edu/ ; Alpha Architect summary https://alphaarchitect.com/industry-momentum/ .
- **Horizon / schedule**: 20 sessions; month_end.
- **Data needed**: 10-K Item 1 text per firm per year (same ingestion as Lazy Prices) + an embedding/cosine peer table (could reuse our text-model seam or plain TF-IDF); daily bars (have). Hoberg-Phillips publish TNIC pairs free for research use (check licence for a personal platform).
- **Individual fit**: Long-only top decile works (peer momentum is a positive-skew long signal); monthly turnover ~ near 100% one-sided -> costs matter (Novy-Marx-Velikov: high-turnover anomalies rarely survive); use a buy/hold band (enter top decile, exit below median).
- **Decoys / overlap**: Industry momentum (Moskowitz-Grinblatt 1999), own 12-1 momentum (filed), size lead-lag (Hou 2007: big firms lead small within industry). Test peer-momentum residual to own and SIC-industry momentum.
- **Verdict**: **Promising**; **Needs data (10-K text + peer table)**. Shares ingestion with Lazy Prices, so cheap once that exists.

### conglomerate_pseudo_lead_lag — Complicated firms (Cohen-Lou 2012)
- **Thesis**: A multi-segment firm's return follows, with a one-month lag, the return of a portfolio of single-segment firms in its segments' industries (its "pseudo-conglomerate").
- **Mechanism**: Information about industry shocks is processed first for simple, pure-play firms; analysts/investors in complicated firms are slower to aggregate the segment-level news.
- **Persistence**: Needs segment data and a bespoke benchmark per firm; profits concentrate in the more complicated firms where coverage is thin.
- **Rule (source's own)**: For each conglomerate, build the pseudo-conglomerate return = segment-sales-weighted average of the single-segment-firm industry portfolio returns; sort conglomerates on last month's pseudo-conglomerate return; long top / short bottom quintile; monthly rebalance.
- **Evidence**: Chen-Zimmermann SignalDoc `retConglomerate`: Cohen & Lou 2012 *JFE*, 1977-2009, 1.18%/mo EW (t = 5.51), also works VW (t = 3.2). Post-publication: Ali-Hirshleifer 2020 report that this factor's alpha becomes insignificant after controlling for shared-analyst-coverage momentum (i.e. it is one face of a broader connected-firm momentum). Decay otherwise not measured in this session.
- **Sources**: Cohen & Lou 2012 *JFE* "Complicated Firms"; Chen-Zimmermann SignalDoc https://raw.githubusercontent.com/OpenSourceAP/CrossSection/master/SignalDoc.csv ; Ali & Hirshleifer 2020 https://www.nber.org/papers/w25201 .
- **Horizon / schedule**: 20 sessions; month_end.
- **Data needed**: Business segment sales by industry (Compustat Segments is paid; XBRL 10-K segment footnotes via SEC Financial Statement data sets are free but messy; LLM extraction from Item 1 is an alternative through our text seam); industry classification (SIC from EDGAR header, free). Daily bars (have).
- **Individual fit**: Long-only top quintile viable; monthly turnover high; conglomerates are mostly mid/large caps so liquidity fine.
- **Decoys / overlap**: Industry momentum, size lead-lag, shared-analyst momentum (subsumes it per Ali-Hirshleifer). Variant worth filing: use it as one of several "connected-firm momentum" legs rather than alone.
- **Verdict**: **Promising** (strong original, subsumed by analyst links, decay unknown); **Needs data (segment extraction)**.

### customer_supplier_momentum — Economic links (Cohen-Frazzini 2008) and the 10-K "principal customer" variant
- **Thesis**: After a big move in a firm's disclosed major customer, the supplier moves the same way next month.
- **Mechanism**: Suppliers disclose customers >= 10% of sales (SFAS 131) in the 10-K; investors in the supplier do not watch the customer's stock; analysts update with a lag.
- **Persistence**: Weak now — the signal is published, Compustat ships the linkage table, and several funds trade it; Pinchuk (2023) finds it statistically insignificant post-discovery.
- **Rule (source's own)**: Monthly, for suppliers with a disclosed principal customer, signal = customer's prior-month return (sales-weighted if several); long top / short bottom quintile; hold 1 month.
- **Evidence**: Original: Chen-Zimmermann `CustomerMomentum`, Cohen & Frazzini 2008 *JF*, 1980-2004, 1.578%/mo VW (t = 3.79). Pinchuk, "Customer Momentum", arXiv 2301.11394 (2023): full sample 122 bp/mo EW (t > 4), 106 bp VW (t ~ 2.8), but in the post-discovery sample the magnitude is smaller and *loses significance*; partly driven by small-large lead-lag. Menzly-Ozbas 2010 *JF* industry-level (BEA I-O) versions: t = 4.11 (customer) / 5.03 (supplier), 1986-2005.
- **Sources**: AQR summary https://www.aqr.com/Insights/Research/Journal-Article/Economic-Links-and-Predictable-Returns ; Pinchuk 2023 https://arxiv.org/abs/2301.11394 ; SignalDoc (above).
- **Horizon / schedule**: 20 sessions; month_end.
- **Data needed**: Customer names from 10-K text (we have filing events, not bodies; LLM extraction of "customers accounting for >10% of revenue" from Item 1 / revenue footnote is a good fit for our text seam) + name->ticker resolution via `SymbolResolver`; daily bars (have).
- **Individual fit**: Suppliers are small caps (good for us, bad for funds); long-only variant exists; monthly turnover high.
- **Decoys / overlap**: Industry momentum, size lead-lag (small suppliers lag big customers = Hou 2007 effect), own momentum. The *supply-chain news-day* variant (act the session after a customer's earnings surprise rather than month-end) is the version that may still carry alpha and is untested here.
- **Verdict**: **Decayed** as published; a **Promising variant**: event-timed (customer earnings-day) supplier drift. **Needs data (customer extraction)**.

### eight_k_item_event_drift — Item-coded 8-K drift (restatements, auditor changes, exec departures, impairments)
- **Thesis**: Specific 8-K items carry predictable multi-week drift: Item 4.02 (non-reliance / restatement) and 4.01 (auditor change with disagreement) negative; 2.06 (material impairment) negative; 5.02 (unexpected CEO/CFO exit) negative; 8.01 repurchase authorisations positive.
- **Mechanism**: Small firms' 8-Ks are unread the day they drop (filed after the close, no analyst coverage); the item code is a cheap, structured, legally mandated classifier of bad news, and subsequent accounting consequences (restated numbers, delayed 10-K, going-concern) arrive over months.
- **Persistence**: Microcap coverage is nil; institutions cannot size positions in them; 8-K text is semi-structured so parsing is cheap for us but not worth a large fund's attention.
- **Rule (source's own)**: No single source rule; the components: Palmrose, Richardson, Scholz 2004 *JAE* (403 restatements 1995-1999, average abnormal return about -9% over the two-day announcement window **(verified)**) with weak subsequent drift; Hennes-Leone-Miller 2008 on irregularities vs errors; Peyer-Vermaelen 2009 *RFS*: the long-run buyback anomalies of Lakonishok-Vermaelen 1990 and Ikenberry et al. 1995 persist in recent data, read as overreaction to bad news **(verified: abstract; no magnitude stated there)**. Our own rule: for each item class, hold from the session after the filing for 20-60 sessions, long/short by item sign, within size tercile.
- **Evidence**: The drift evidence is class-specific and mostly 1990s-2000s; the one well-replicated piece is buyback-announcement drift (Ikenberry-Lakonishok-Vermaelen 1995; Quantpedia #0271 "Earnings announcements combined with stock repurchases" shows 25.2%/yr, 11.1% vol on its page — Quantpedia backtest, not peer-reviewed). Restatement drift is contested. **Our platform already codes 8-K items (event-sensitivity track) so this is the cheapest edge to test point in time.**
- **Sources**: Quantpedia strategies list https://quantpedia.com/strategies/ ; Palmrose, Richardson & Scholz 2004 *JAE* 37(1) "Determinants of market reactions to restatement announcements", https://doi.org/10.1016/j.jacceco.2003.06.003 ; Peyer & Vermaelen 2009 *RFS* 22(4) "The Nature and Persistence of Buyback Anomalies", https://doi.org/10.1093/rfs/hhn024 ; our `docs/event-sensitivity-plan.md`.
- **Horizon / schedule**: 20-60 sessions; on_event:8-K item (first actionable session = next open after acceptance).
- **Data needed**: SEC filings events with 8-K items (have); daily bars (have); for 4.02 the restatement magnitude from the later 10-K/A (have financials).
- **Individual fit**: Excellent: small names, event-driven, low capacity; long side (8.01 buybacks, 5.02 *planned* successions) and put-buying for the negative items where borrow is impossible.
- **Decoys / overlap**: Post-earnings drift (filed) when the 8-K is Item 2.02; momentum; the filing coincides with a price drop, so "drift" may be delayed reaction to the known drop (test vs same-size-drop controls). Overlaps with the other families' corporate-event list — flag to the orchestrator.
- **Verdict**: **Promising** (mechanism strong, published magnitude per item weak/old); **Ready** (data in place).

### sec_comment_letters — SEC review comment letters as a negative screen
- **Thesis**: Firms receiving substantive SEC comment letters (revenue recognition, non-GAAP, going concern) underperform / are more likely to restate; the letters become public on EDGAR (UPLOAD / CORRESP) ~20 business days after resolution.
- **Mechanism**: Investors do not read correspondence filings; the letter is an expert regulator's free forensic read; its disclosure is delayed and unannounced.
- **Persistence**: Tiny, dull filings; no vendor packaging for retail; institutions treat as compliance noise.
- **Rule (source's own)**: Cassell, Dreher, Myers 2013 *TAR* "Reviewing the SEC's Review Process" (recalled): letter receipt associated with low profitability, high complexity, weak governance; Johnston & Petacchi 2017 *CAR* (recalled, not verified): negative abnormal returns around public release, improved information environment afterwards; Bozanic, Dietrich, Johnson 2017 *JAE* (recalled): letters predict later restatements. No published long-short rule; our rule: exclude from long screens / short-list for 60-250 sessions any firm with a comment letter raising revenue recognition, segment, impairment or non-GAAP issues (LLM classification of CORRESP text through our seam).
- **Evidence**: Information content yes; standalone return spread not established -> **a filter, not an edge**.
- **Sources**: Cassell-Dreher-Myers 2013 *The Accounting Review*; Johnston & Petacchi 2017 *Contemporary Accounting Research*; EDGAR CORRESP/UPLOAD form types (free).
- **Horizon / schedule**: 60-250 sessions; on_event:CORRESP/UPLOAD publication.
- **Data needed**: Ingest UPLOAD/CORRESP filings (free, EDGAR), LLM topic tag; daily bars (have).
- **Individual fit**: Long-only usable as an exclusion; shorting the flagged names is the alpha half.
- **Decoys / overlap**: Letters hit larger, more complex, more acquisitive firms; control for size, accruals, M&A.
- **Verdict**: **Weak** as a return signal, **Promising** as a quality filter; **Needs data (CORRESP ingestion)**.

### shared_analyst_coverage_momentum — Connected-firm momentum via shared analysts
- **Thesis**: Firms covered by the same sell-side analysts move together with a lag; buy firms whose "analyst-connected" peers did well last month.
- **Mechanism**: Analysts update coverage of linked firms sluggishly; shared coverage proxies for every kind of economic link (industry, customer, geography, technology) at once.
- **Persistence**: The paper shows it subsumes six other link-momentum factors; the strength is in *complex, indirect* linkages, which take effort to see; monthly rebalance and reliance on analyst-identity data (I/B/E/S) keep it semi-institutional.
- **Rule (source's own)**: Ali & Hirshleifer 2020 *JFE*: for each firm, connected-firm return = coverage-weighted average prior-month return of all firms sharing >= 1 analyst in the past 12 months; long top / short bottom decile; monthly.
- **Evidence**: Monthly alpha 1.68% (t = 9.67) over 1980s-2015ish sample (NBER w25201 abstract); industry, geographic, customer, I-O, conglomerate and technology momentum factors have insignificant alpha after controlling for it. Post-publication decay: not measured in this session (published 2020; expect the standard haircut).
- **Sources**: https://www.nber.org/papers/w25201 ; SSRN 3015582; Internet appendix SSRN 3395415.
- **Horizon / schedule**: 20 sessions; month_end.
- **Data needed**: Analyst identities per covered firm (I/B/E/S — paid; FMP/Finnhub give consensus counts but not analyst IDs: **missing**). Possible free proxy: co-mention in the same sell-side initiation press release (poor), or substitute the TNIC/conglomerate/customer legs we can build.
- **Individual fit**: Long-only decile fine; high turnover; large-cap heavy so costs small.
- **Decoys / overlap**: Industry momentum, 12-1 momentum (filed), size lead-lag.
- **Verdict**: **Strong** evidence, **Out of scope (needs I/B/E/S analyst identities)**; file the implementable legs instead (TNIC, conglomerate, customer).

### technology_links_momentum — Patent-class proximity momentum
- **Thesis**: Firms whose technology-similar peers (overlapping patent classes) rallied last month outperform.
- **Mechanism**: Tech links cut across industries and are invisible without patent data; shocks propagate slowly.
- **Persistence**: Requires patent-portfolio similarity (Jaffe 1986 measure); annual reconstruction; subsumed by shared-analyst momentum (Ali-Hirshleifer), implying the residual after other link-momentums is small.
- **Rule (source's own)**: Lee, Sun, Wang, Zhang 2019 *JFE* "Technological links and predictable returns" (recalled): tech-peer-weighted prior-month return; long/short deciles; monthly. Magnitude recalled as ~1%/mo alpha (not verified).
- **Evidence**: Original significant; Ali-Hirshleifer: insignificant after shared-analyst control. Decay unmeasured.
- **Sources**: Lee et al. 2019 *JFE* 132(3); Ali & Hirshleifer 2020; USPTO PatentsView (free) https://patentsview.org/ .
- **Horizon / schedule**: 20 sessions; month_end.
- **Data needed**: Patent assignee -> ticker mapping (PatentsView free; mapping is the hard part), CPC class vectors; daily bars (have).
- **Individual fit**: Long-only ok; tech-heavy universe; costs as other monthly momentum variants.
- **Decoys / overlap**: Industry momentum, TNIC peer momentum (text and patents overlap heavily).
- **Verdict**: **Weak-Promising**; **Needs data (patents)**; lower priority than TNIC which uses the same 10-K ingestion.

### geographic_lead_lag — Same-metro firm lead-lag
- **Thesis**: Returns of a firm predict next-month returns of other firms headquartered in the same city/metro area, beyond industry links (local economic shocks diffuse slowly).
- **Mechanism**: Local shocks (labour market, regional demand) are learned first by local investors and show up in the most-traded local names first.
- **Persistence**: Needs HQ geocoding; low glamour; subsumed by shared-analyst momentum per Ali-Hirshleifer.
- **Rule (source's own)**: Parsons, Sabbatucci, Titman 2020 *RFS* "Geographic Lead-Lag Effects": signal = prior-month return of other firms in the same MSA (excluding same industry); long/short; monthly. Magnitude recalled as roughly 0.5-0.6%/mo (not verified).
- **Evidence**: Significant in original; Ali-Hirshleifer show geographic momentum alpha is absorbed by shared-analyst momentum. No independent decay number found.
- **Sources**: Parsons-Sabbatucci-Titman 2020 *RFS* 33(10); Ali & Hirshleifer 2020.
- **Horizon / schedule**: 20 sessions; month_end.
- **Data needed**: HQ city/state from EDGAR company headers (free; we may already store business address in reference snapshots) -> MSA; daily bars (have).
- **Individual fit**: Long-only; monthly; large and small caps.
- **Decoys / overlap**: Industry and state-level economic exposure; firms in the same city share industries (exclude same SIC-2).
- **Verdict**: **Weak** (small, subsumed); **Ready-ish** (HQ data nearly free). Low priority.

### llm_headline_score_drift — LLM-scored headlines, next-day/next-week drift
- **Thesis**: Ask an LLM whether a headline is good or bad for the stock; positive scores predict positive next-day returns, especially for small caps and bad news.
- **Mechanism**: Underreaction to news that needs context to interpret; small stocks have few readers; negative news is harder to arbitrage (short constraints).
- **Persistence**: Weak and shrinking — the paper's own latest version (v6, Oct 2025) says strategy returns *decline as LLM adoption rises*; what remains is the non-tradable initial reaction (~90% portfolio-day hit rate) and a drift concentrated in small/negative-news names.
- **Rule (source's own)**: Lopez-Lira & Tang (2023-2025): for each headline after the model's knowledge cutoff, prompt GPT-4 for "good / bad / unknown"; long positive / short negative at next open, hold one day; equal weight; daily.
- **Evidence**: v1 (2023): long-short Sharpe highest for GPT-4 (Oct 2021-Dec 2022 sample, numbers recalled, not verified in this session); v6 (2025): ~90% hit rate on initial reaction, drift "especially for small stocks and negative news", returns declining with adoption. Related: Kirtac & Germano 2024 (LSE) OPT model on 965k US news 2010-2023: 74.4% directional accuracy, long-short Sharpe 3.05 after 10 bp costs — in-sample-ish, vendor-grade news, one-day holding: treat as upper bound and probably overfit.
- **Sources**: arXiv 2304.07619 (v1-v6) https://arxiv.org/abs/2304.07619v6 ; Kirtac & Germano 2024 https://arxiv.org/abs/2412.19245 ; Chen-Kelly-Xiu discussion slides https://jacobslevycenter.wharton.upenn.edu/wp-content/uploads/2024/09/Kelly-WhartonJL.pdf .
- **Horizon / schedule**: 1-5 sessions; every_session (on_event:headline).
- **Data needed**: A full, time-stamped headline feed (we only have capped headlines) — **missing**; text-model seam (have). Headline timestamps vs close are the lookahead hazard.
- **Individual fit**: Daily turnover => costs dominate; small-cap bad-news leg needs shorting. Realistic use: a *filter* on our 8-K / earnings events, not a standalone daily strategy.
- **Decoys / overlap**: Post-earnings drift (filed), 8-K drift (above), short-term reversal; most "news" is earnings.
- **Verdict**: **Decayed / Weak** as a daily strategy; **Needs data (news feed)**; use the LLM scoring as a classifier inside event edges instead.

### llm_news_embeddings_expected_returns — Chen-Kelly-Xiu
- **Thesis**: LLM embeddings of full news articles, fed to a return model, out-predict word-count sentiment and technical signals, especially where negation matters.
- **Mechanism**: Dictionary methods misread negation and context; embedding models do not.
- **Persistence**: Requires licensed full-text news (Dow Jones/Refinitiv), GPU inference and daily rebalancing; firmly institutional.
- **Rule (source's own)**: Embed each article (ChatGPT / LLaMA), ridge-regress next-day return on embedding, long-short deciles daily; 16 markets, 13 languages (abstract).
- **Evidence**: The abstract (SSRN 4416687; seminar copies) reports that prices respond slowly to news, that LLM-embedding predictions improve significantly over past-return and word-based benchmarks (most where negation or complex narratives matter), with net-of-cost Sharpe ratios across 16 markets **(verified: abstract)**; the headline Sharpe **(figure dropped: not stated in the abstracts read; the discussant's slides (S. Z. Li, Wharton Jacobs Levy 2024) put the net annual Sharpe near 1.5 at 10-20 bp daily costs)**.
- **Sources**: Chen, Kelly & Xiu (2022, rev. Feb 2026) SSRN working paper "Expected Returns and Large Language Models", https://papers.ssrn.com/abstract=4416687 (abstract also at https://acem.sjtu.edu.cn/academic/82735.html ); discussion slides, S. Z. Li (2024) https://jacobslevycenter.wharton.upenn.edu/wp-content/uploads/2024/09/ExpectedReturnAndLLM_Discussion_SophiaZhengziLi_NoPause.pdf .
- **Horizon / schedule**: 1 session; every_session.
- **Data needed**: Licensed news corpus — **missing**.
- **Individual fit**: None (daily turnover, data cost).
- **Decoys / overlap**: Same as headline drift.
- **Verdict**: **Strong** academically, **Out of scope** for us.

### earnings_call_qa_evasiveness — Management non-answers / low question-answer similarity
- **Thesis**: Calls where executives dodge analyst questions (semantic mismatch, non-answers) precede weaker next-quarter earnings and lower post-call returns; well-aligned answers precede outperformance.
- **Mechanism**: Managers with bad private information evade rather than lie (litigation risk); listeners detect it only impressionistically; a systematic score harvests it.
- **Persistence**: Needs transcripts for the whole universe plus NLP; S&P Global now sells an "on-topic alignment" score (Jan 2025 whitepaper) so large-cap alpha is being commercialised; small-cap calls remain unread.
- **Rule (source's own)**: Barth, Mansouri, Wöbbeking 2023 *Management Science*: ML-classified non-answer share per call -> lower CARs and higher implied vol after the call. *J. Behavioral Finance* (2026, Univ. of Limerick): LLM-embedding cosine similarity between each question and its answer, averaged per call; top-similarity portfolio earns ~3.9%/yr alpha; low-similarity answers are rated evasive by humans 67% vs 22%. Chen-Rui-Whinston (HICSS 2023, S&P 500 2006-2018): evasiveness and incoherence forecast weaker next-quarter earnings; incoherence predicts lower next-day abnormal return.
- **Evidence**: Consistent direction across four studies; magnitudes modest (3.9%/yr long-only alpha; event-window CARs). EvasionBench (arXiv 2601.09142, 2026) provides a 22.7M Q&A-pair labelled benchmark with Kappa 0.835 — useful for our seam. Alpha Architect summarises the "HAID" measure (executive answer vs LLM-generated answer distance) predicting liquidity and abnormal returns.
- **Sources**: Barth et al. 2023 https://ideas.repec.org/a/inm/ormnsc/v69y2023i10p6333-6348.html ; Limerick https://pure.ul.ie/en/publications/the-language-of-evasion-how-semantic-similarity-between-questions/ ; EvasionBench https://arxiv.org/abs/2601.09142 ; S&P Global QRS 2025 https://spglobal.com/content/dam/spglobal/global-assets/en/documents/general/QuestioningTheAnswers_GoLive.pdf ; Alpha Architect HAID https://alphaarchitect.com/?p=88404 .
- **Horizon / schedule**: 60 sessions (to next call); on_event:earnings call (transcript available same/next day).
- **Data needed**: Call transcripts — **missing** (free sources exist: Motley Fool / Seeking Alpha pages with ToS limits; some issuers attach transcripts to 8-K Exhibit 99 — rare); text-model seam (have).
- **Individual fit**: Long-only (high-alignment calls) works; quarterly turnover; small caps where it is strongest.
- **Decoys / overlap**: Earnings surprise and guidance tone drive both evasiveness and drift (filed PEAD); control for surprise, guidance change and call-day return.
- **Verdict**: **Promising**; **Needs data (transcripts)**. Second-cheapest text edge after filings if a transcript source is found.

### earnings_call_vocal_cues — Voice stress / affect (Mayew-Venkatachalam)
- **Thesis**: Vocal affect (measured from call audio) predicts future earnings and returns beyond the words.
- **Mechanism / Persistence**: Emotion leaks in voice; nobody runs audio analytics at scale except a few funds.
- **Rule / Evidence**: Mayew & Venkatachalam 2012 *JF* "The Power of Voice" (recalled, not verified): positive/negative affect from LVA software predicts analyst revisions and returns around and after the call. Few replications; software proprietary.
- **Sources**: Mayew & Venkatachalam 2012 *Journal of Finance* 67(1).
- **Data needed**: Call audio — **missing**; audio ML — out of our stack.
- **Verdict**: **Weak** (one-paper literature), **Out of scope**.

### mdna_tone_change — MD&A tone change and drift
- **Thesis**: A quarter-on-quarter deterioration in MD&A tone (Loughran-McDonald negative words) predicts lower returns over the next quarter, incremental to the earnings surprise and accruals.
- **Mechanism**: Managers soften bad news in numbers but hedge in words; readers anchor on EPS.
- **Persistence**: Dictionary tone is now a vendor commodity (every NLP shop sells 10-K tone), so large-cap alpha should be gone; LLM-based tone on small caps is the residual.
- **Rule (source's own)**: Feldman, Govindaraj, Livnat, Segal 2010 *RAST* (recalled): change in net tone (positive minus negative word share) of MD&A vs prior filing, quintile sort, hold to next filing; significant drift after controlling for SUE and accruals (magnitude recalled as a few % per quarter spread, not verified).
- **Evidence**: 2010 publication; Loughran-McDonald 2011 confirm finance-specific lists work and generic lists do not; no recent replication located in this session. Expect heavy decay.
- **Sources**: Feldman et al. 2010 *Review of Accounting Studies* 15(4); Loughran & McDonald 2011 *JF*; L-M word lists https://sraf.nd.edu/loughranmcdonald-master-dictionary/ (free).
- **Horizon / schedule**: 60 sessions; on_event:10-Q/10-K.
- **Data needed**: Filing text (same ingestion as Lazy Prices); word lists free.
- **Individual fit**: Long-only on tone-improvers; quarterly.
- **Decoys / overlap**: PEAD (filed) and Lazy Prices; tone change correlates with surprise.
- **Verdict**: **Weak / Decayed** standalone; include as a feature in the filing-text group rather than its own edge.

### innovative_efficiency_patents — Patents / citations per R&D dollar
- **Thesis**: Firms producing more patents (or citations) per dollar of past R&D earn higher returns; the market under-values innovation productivity.
- **Mechanism**: R&D is expensed, patents are not capitalised; investors anchor on accounting earnings; the efficiency ratio is a slow-moving quality signal.
- **Persistence**: Needs patent data joins; annual rebalance; large-cap tech dominated.
- **Rule (source's own)**: Hirshleifer, Hsu, Li 2013 *JFE*: IE = patents granted in year t / R&D spent in t-2 (or citations / R&D); annual sort at June; long high / short low tercile, hold 12 months.
- **Evidence**: SignalDoc `PatentsRD`: 1982-2008, 0.41%/mo VW FF3 alpha (t = 4.13); `CitationsRD` 0.26%/mo (t = 2.6). Cohen-Diether-Malloy 2013 *RFS* `RDAbility` (R&D-to-sales-growth ability) 1.35%/mo EW (t = 2.61). Hou-Xue-Zhang 2020 "Replicating Anomalies" generally kept innovation signals (recalled). Post-publication decay not measured here.
- **Sources**: SignalDoc CSV (above); Hirshleifer-Hsu-Li 2013 *JFE* 107(3); Cohen-Diether-Malloy 2013 *RFS* "Misvaluing Innovation"; PatentsView (free).
- **Horizon / schedule**: 250 sessions; annual (June) or month_end with 12-month hold.
- **Data needed**: Patents by assignee (PatentsView, free; assignee->ticker mapping needed), R&D expense (SEC financials, have).
- **Individual fit**: Very low turnover => survives costs trivially; long-only top tercile fine; it is a quality tilt.
- **Decoys / overlap**: Profitability / quality factor, R&D intensity, size, growth. `RDAbility` is computable from our financials alone (no patents) — a cheaper variant.
- **Verdict**: **Promising** (modest, low-turnover, replicated); **Needs data (patents)**; file `rd_ability` (financials only) as **Ready** variant.

### composite_mispricing_score — Anomaly combination (Stambaugh-Yu-Yuan)
- **Thesis**: Averaging a firm's percentile ranks across many published anomalies produces a composite that predicts returns far better than any one signal, with most of the spread in the short (overpriced) leg.
- **Mechanism**: Each anomaly is a noisy mispricing measure; averaging reduces noise; the short leg persists because of shorting frictions and sentiment-driven overpricing.
- **Persistence**: Post-publication decay applies to each component, but composites decay less (JKP 2023: factors remain significant out of sample and in 93 countries); costs limit the monthly version.
- **Rule (source's own)**: Stambaugh, Yu, Yuan 2015 *JFE* / Stambaugh-Yuan 2017 *RFS*: 11 anomalies (net stock issues, composite equity issues, accruals, NOA, asset growth, investment-to-assets, distress, O-score, momentum, gross profitability, ROA); monthly percentile rank average; long bottom decile (underpriced) / short top decile; monthly. Novy-Marx-Velikov 2016 show composites with buy/hold bands keep net alpha.
- **Evidence**: Stambaugh-Yu-Yuan (JF 2015): VW decile long-short on the composite earns 1.48%/month FF3-adjusted, 8/1965-1/2011 **(verified)**, 62 bp more than averaging the 11 single-anomaly spreads (0.86%), and 58 of those 62 bp come from the short leg **(corrected; was "short leg ~2/3 of it")**; sentiment-dependent. JKP 2023 *JF* ("Is there a replication crisis"): >80% of factors replicate; 13 themes; work out of sample internationally; post-publication premia lower but alive. Chen-Zimmermann: publication bias explains only ~12% shrinkage; decay ~50% after sample end (Chen podcast, 2024).
- **Sources**: Stambaugh, Yu & Yuan (2015) *JF* 70(5) "Arbitrage Asymmetry and the Idiosyncratic Volatility Puzzle", https://www.nber.org/papers/w18560 ; JKP *JF* 2023 https://www.nber.org/papers/w28432 ; Alpha Architect summary https://alphaarchitect.com/is-there-a-replication-crisis-in-finance/ ; Chen on Rational Reminder 2024 https://rationalreminder.ca/podcast/316 ; Novy-Marx-Velikov 2016 *RFS* https://www.nber.org/papers/w20721 .
- **Horizon / schedule**: 20-60 sessions; month_end (or quarterly with bands).
- **Data needed**: SEC financials (have: issuance via shares outstanding, accruals, NOA, asset growth, profitability), daily bars (have), distress proxies (have fundamentals). **Ready** from 2024-10 and back to 2010 once Tiingo history lands.
- **Individual fit**: Long-only bottom-decile composite is the realistic form (smaller alpha); use quarterly rebalance with bands to cut turnover; the short leg is where the money is and needs borrow.
- **Decoys / overlap**: It *is* the overlap: contains momentum (filed) and profitability; the real question is whether the composite beats our best single filed edge after costs.
- **Verdict**: **Strong** (meta-robust), **Ready**. Also the natural benchmark for every other edge's "decoy" test.

### ml_cross_sectional_scorer — Gu-Kelly-Xiu-style ML over firm characteristics
- **Thesis**: Nonlinear models (trees, shallow nets) over ~90 characteristics + macro states predict monthly returns better than linear factor models, giving higher long-short Sharpe.
- **Mechanism**: Interactions (e.g. momentum x volatility x size) and regime dependence that linear sorts miss.
- **Persistence**: Everyone with the data can fit it; the gain concentrates in microcaps, high-friction and distressed names (Avramov-Cheng-Metzker 2023 *Mgmt Sci*, recalled): ML profits largely vanish after excluding microcaps / after costs, so it is persistent only where big money cannot go — which is our niche.
- **Rule (source's own)**: Gu, Kelly, Xiu 2020 *RFS* (DOI 10.1093/rfs/hhaa009): 94 characteristics x 8 macro predictors, 1957-2016, rolling train/validate/test; NN3-NN5 best; decile long-short monthly. Out-of-sample R^2 ~0.4% monthly for NN (recalled); VW long-short Sharpe for NN ~1.35 and EW ~2.4 vs ~0.6-0.8 for OLS-3 (recalled, **not verified** — PDF could not be text-extracted in this session).
- **Evidence**: Widely replicated in-method (hundreds of follow-ups); Jensen-Kelly-Malamud-Pedersen "Machine Learning and the Implementable Efficient Frontier" (SSRN 4187217, blocked in this session): once trading costs are inside the objective, the optimal portfolio loads on *slow* signals and much of the gross ML Sharpe is not implementable (recalled). Kelly-Malamud-Zhou 2024 *JF* "Virtue of Complexity" (market timing, random features): big models beat small ones out of sample; critiqued by Nagel (2025, "Seemingly virtuous complexity", recalled) as equivalent to volatility-scaled momentum timing — not a cross-sectional edge for us.
- **Sources**: GKX 2020 https://dachxiu.chicagobooth.edu/download/ML.pdf ; KMZ 2024 *JF* (SSRN 3984925); JKMP (SSRN 4187217); Avramov, Cheng, Metzker 2023 *Management Science* "Machine Learning vs. Economic Restrictions".
- **Horizon / schedule**: 20 sessions; month_end.
- **Data needed**: Our feature catalogue already holds most characteristics; needs 2010+ history (Tiingo backfill in progress) to train; a `quant/`-side model with strict walk-forward.
- **Individual fit**: As a *ranker* for long-only screens in small caps, fine; as a standalone daily/monthly L/S, costs kill it.
- **Decoys / overlap**: It is a repackaging of the composite above plus momentum; run it as a challenger to `composite_mispricing_score`, not as an edge with a thesis (an edge document needs a mechanism; "the net found it" is not one).
- **Verdict**: **Promising as tooling**, **Weak as an edge**; **Needs data (2010+ history)**.

### short_seller_report_drift — Activist short reports
- **Thesis**: Stocks targeted by named activist short sellers fall ~11% in three days and keep falling for months; buying puts / shorting after the first day still pays.
- **Mechanism**: Reports contain costly forensic work; the target's defence takes weeks; borrow dries up; index funds cannot sell; retail buys the dip.
- **Persistence**: Reputation of the publisher matters; underreaction persists because fully pricing fraud allegations means believing them; litigation risk for the publisher caps supply.
- **Rule (source's own)**: Studies (383 reports / 171 firms from six prominent activists, period not shown in the summary): -11.2% market-adjusted 3-day, -14.5% at two months, -22.6% at six months cumulative (secondary summary; original paper not fetched — see sources). Another event study: 247 firms / 17 US activists, 2010-2020, CAR about -14.8%, strongest in small caps. Firm response rate 31%; internal-investigation launches predict delisting and SEC action (Brendel-Ryans, *JAR* 2021 "Responding to Activist Short Sellers", LBS).
- **Evidence**: Direction consistent across samples; the drift is large but the Hindenburg era (2020-2024) is under-studied in what I found; Hindenburg closed in Jan 2025 — supply of reports fell.
- **Sources**: Brendel & Ryans 2021 https://lbsresearch.london.edu/id/eprint/1699/1/1475-679X.12356.pdf ; HU Berlin dissertation https://edoc.hu-berlin.de/items/5f296028-5dc2-478e-80f4-5b8b59a00af3/full ; SSE Riga paper https://www.sseriga.edu/sites/default/files/2020-05/1Paper_Ogorodniks_Sirbu.pdf ; CXO summary https://cxoadvisory.com/?p=29141 .
- **Horizon / schedule**: 40-120 sessions; on_event:report (public on the activist's site, first actionable session = next open; day-1 move is not capturable).
- **Data needed**: A report feed (activist sites / Breakout Point / Activist Insight — not stored; a small curated list is buildable by hand, ~30-60 reports a year), daily bars (have), options chains (have) for the put variant, IV (have — IV spikes on report day, so puts are expensive: test IV-adjusted).
- **Individual fit**: Needs short or puts; small caps with hard borrow; capacity tiny (good); event count ~40/yr meets the >=40 bar in ~1-2 years.
- **Decoys / overlap**: Day-1 drop; high short interest (not stored); momentum; most targets are already down.
- **Verdict**: **Promising**; **Needs data (report list)**; the put-buying variant is unique to this family.

### wikipedia_pageviews_attention — Wikipedia page-view spikes
- **Thesis**: A jump in a company's Wikipedia page views signals retail attention; the next week sees continuation (Pyun) or reversal (vendor tests) — sign unsettled.
- **Mechanism**: Attention-driven buying (Barber-Odean) pushes prices then reverts; or views proxy for news not yet priced.
- **Persistence**: Free data, so none at the large-cap end; conflicting signs suggest little.
- **Rule (source's own)**: Pyun 2025 (SSRN): 2016-2023 NYSE/Nasdaq, Quiver Quantitative data; rising page views -> higher subsequent returns; weekly rebalance beats monthly; H-M-L alpha under CAPM/FF3/FF5/FF6. Moat et al. 2013 *Sci. Rep.* (DJIA, 2007-2012) view changes timed the index. fffinstill (2026 blog): >3x view spikes -> weak next-week returns.
- **Evidence**: Mixed and thin; magnitudes not read.
- **Sources**: Pyun 2025 (via https://alphainacademia.substack.com/p/recent-academic-research-fd2 ); Moat et al. 2013 https://www.nature.com/articles/srep01801 ; https://fffinstill.com/blog/wikipedia-pageviews-stock-predictor-viral-searches-returns .
- **Horizon / schedule**: 5 sessions; every_session.
- **Data needed**: Wikimedia pageviews API (free, daily) + page->ticker map; not stored.
- **Individual fit**: Weekly turnover; cost-heavy; long-only version is just an attention chaser.
- **Decoys / overlap**: News/earnings days, retail attention reversal, Google SVI.
- **Verdict**: **Weak**; **Needs data (cheap)**. Low priority.

### google_svi_attention — Google search volume (Da-Engelberg-Gao)
- **Thesis**: A rise in ticker search volume predicts a ~2-week price rise then reversal within the year; retail attention.
- **Mechanism**: Retail buys what they look up (attention), creating temporary pressure.
- **Persistence**: Google Trends is relative, sampled, rate-limited and noisy for tickers that are words; the 2011 result is famous and the short-horizon part is arbitraged.
- **Rule (source's own)**: Da, Engelberg, Gao 2011 *JF*: abnormal SVI (log SVI minus log median of prior 8 weeks) for Russell 3000, 2004-2008; long high-ASVI; two-week horizon; reversal within 12 months; strongest for small stocks and IPO first-day returns.
- **Evidence**: arXiv 2101.03239 claims SVI explanatory power *rose* after 2009 (unvetted). No 2020s decay study found; expect decay. Cookson et al. 2022 (StockTwits/Twitter): attention-induced retail imbalance predicts strongly *negative* next-day returns, sentiment-induced imbalance positive — i.e. attention alone is a short signal.
- **Sources**: DEG 2011 working paper https://www.ou.edu/dam/price/Finance/files/Paul%20Gao%20Paper.pdf ; arXiv 2101.03239 https://arxiv.org/pdf/2101.03239 ; Cookson, Lu, Mullins, Niessner 2022 (via https://www.neudata.co/literature-reviews/retail-trading-how-r-wallstreetbets-shapes-investor-decisions ).
- **Horizon / schedule**: 10 sessions; weekly.
- **Data needed**: Google Trends (free, unofficial API, quota) — not stored.
- **Individual fit**: Poor: weekly turnover, small caps, noisy.
- **Decoys / overlap**: News, earnings, Wikipedia views, Reddit.
- **Verdict**: **Decayed / Weak**; **Needs data**. Not worth building.

### reddit_stocktwits_sentiment — Social sentiment vs attention
- **Thesis**: Bullish social sentiment predicts small next-day gains; raw attention predicts reversal; OTC/meme names reverse after hype, fall and stay down after negative sentiment.
- **Mechanism**: Coordinated retail flow; herding then exhaustion.
- **Persistence**: Reddit/StockTwits APIs are restricted/paid since 2023; the 2021 regime (WSB) was special; effects are a day long.
- **Rule (source's own)**: Semenova & Winkler (2021, MPRA): WSB bullish day -> ~+0.2 pp excess log return then -0.05 pp reversal next day. Cookson et al. 2022: separate sentiment- vs attention-induced imbalance. Watanabe 2025 (Keio): StockTwits on OTC stocks: positive sentiment -> spike and reversal; negative -> drop without reversal.
- **Evidence**: Working papers and theses; tiny magnitudes; daily horizon.
- **Sources**: https://mpra.ub.uni-muenchen.de/118602/8/wsb.pdf ; https://ies.keio.ac.jp/upload/20250708econo_Watanabe_WP.pdf ; CFR Cologne WP 25-02 https://cfr-cologne.de/download/workingpaper/cfr-25-02.pdf .
- **Horizon / schedule**: 1-2 sessions; every_session.
- **Data needed**: Social feeds — **missing** and now expensive.
- **Individual fit**: Daily turnover; no.
- **Decoys / overlap**: Short-term reversal, attention (SVI), news.
- **Verdict**: **Weak**; **Out of scope**. Only the *negative-sentiment-no-reversal* OTC finding hints at an edge, and OTC is outside our universe.

### congress_trades_copycat — STOCK Act disclosures (NANC / KRUZ)
- **Thesis**: Copy Congress members' disclosed purchases.
- **Mechanism**: Alleged informational advantage from legislative access.
- **Persistence**: Disclosure lag up to 45 days, ranges not amounts, and the newest evidence shows no post-disclosure alpha.
- **Rule (source's own)**: Ziobrowski et al. 2004 (Senators 1993-98 beat the market ~12%/yr, recalled) vs Eggers & Hainmueller 2013 *JPolitics* "Capitol Losses" (members underperform, recalled). Gothenburg thesis (2025, House purchases Jan 2020-Dec 2024): post-disclosure CARs significantly *negative* at 20 and 40 days, concentrated in Democratic members' purchases. Belmont et al. 2020: no consistent outperformance.
- **Evidence**: NANC (Democrat-copy ETF) 1-yr 18.66% vs S&P 500 TR 17.88%, since-inception 23.63% vs 20.96% annualised (Lambda Finance table as of 2025-12-31) — a tech-tilted large-cap fund, within noise of beta; Kennesaw State (Oct 2025) says returns are not out of the norm; Morningstar covers the two ETFs' tech concentration.
- **Sources**: https://gupea.ub.gu.se/items/0e1aeba3-3354-493e-b192-bee7df3c107c ; https://www.lambdafin.com/articles/congressional-returns-holding-period ; https://www.morningstar.com/funds/2-etfs-that-track-congressional-stock-trades ; https://www.kennesaw.edu/coles/centers/markets-economic-opportunity/docs/2025-october-commentary.pdf ; Alpha Architect 2013 https://alphaarchitect.com/2013/11/congress-is-insider-trading/ .
- **Horizon / schedule**: 20-40 sessions; on_event:disclosure.
- **Data needed**: House/Senate PTR filings (free; Quiver/Capitol Trades aggregate) — not stored.
- **Individual fit**: Fine mechanically, but there is nothing to harvest.
- **Decoys / overlap**: Beta, large-cap tech momentum.
- **Verdict**: **Dead** (as a copy strategy). Possible niche: *sells* by committee members in sector-specific small caps — untested, no evidence found.

### lobbying_intensity — Lobbying spend / market cap
- **Thesis**: Firms with the highest lobbying intensity outperform benchmarks for three years after formation.
- **Mechanism**: Lobbying yields regulatory rents (contracts, tax, tariffs) that investors under-price because the link is indirect and slow.
- **Persistence**: Senate LDA data are free but ugly; a 3-year horizon and "political" framing deter quants; Strategas ran a lobbying index (performance claims are vendor marketing, not verified here).
- **Rule (source's own)**: Chen, Parsley, Yang (*JBFA* 2015; MPRA 2010): lobbying intensity = lobbying expense / assets (or sales); annual portfolios of top-intensity firms outperform benchmarks for three years; popular write-ups quote ~8 pp/yr for the top portfolio vs non-lobbying peers (1998-2005 sample, recalled). Kim 2008 (S&P 500, 1998-2004): positive effect on excess returns vs market, less vs industry.
- **Evidence**: Two older studies with positive results; Borisov-Goldman-Gupta (2016 *RFS*, "The Corporate Value of (Corrupt) Lobbying") show lobbying-heavy firms lost value after the Abramoff plea, i.e. part of the value is fragile. No post-2015 out-of-sample test found.
- **Sources**: https://mpra.ub.uni-muenchen.de/21114 ; https://news.vanderbilt.edu/2008/04/16/corporate-lobbying-pays-off-for-firms-58160/ ; Kim 2008 https://dx.doi.org/10.2202/1469-3569.1193 ; ECGI WP https://www.ecgi.global/sites/default/files/working_papers/documents/ssrn-id2443104.pdf ; Senate LDA API (free) https://lda.senate.gov/api/ .
- **Horizon / schedule**: 250-750 sessions; annual.
- **Data needed**: LDA filings (free) + registrant->ticker mapping; market cap (have).
- **Individual fit**: Long-only, annual turnover, large caps: trivially cheap; small expected alpha.
- **Decoys / overlap**: Size (big firms lobby), regulated-industry exposure (defence, pharma, utilities), quality.
- **Verdict**: **Weak** (old, small, possibly a defence/pharma sector bet); **Needs data (cheap)**.

### government_contract_dependency — Share of revenue from government
- **Thesis**: Firms highly dependent on government revenue earn abnormal returns because of limited attention and valuation uncertainty.
- **Mechanism / Persistence**: Government customers are disclosed in 10-Ks and USAspending; investors under-weight the stability (or the risk) of that revenue; evidence is one preliminary paper.
- **Rule (source's own)**: AEA 2020 preliminary paper: government sales dependency (from 10-K customer disclosures) sorts predict the cross-section; details not read.
- **Evidence**: Contract-award event studies mixed: positive CARs concentrated in aerospace & defence (2024 US/Canada study); nulls in pharma and in a 4-firm NPS thesis. Not an established anomaly.
- **Sources**: https://topcat.aeaweb.org/conference/2020/preliminary/paper/hSEN75b4 ; https://anserpress.org/journal/jea/3/1/43/html ; USAspending API (free) https://api.usaspending.gov/ .
- **Horizon / schedule**: 250 sessions; annual, or on_event:contract award (daily USAspending / DoD 5 pm announcements) for the event variant.
- **Data needed**: USAspending awards -> ticker (recipient DUNS/UEI mapping needed); 10-K customer text (as for customer momentum).
- **Individual fit**: Long-only, low turnover; the DoD 5 pm daily contract announcement is an under-studied small-cap event for an EOD trader (first actionable session = next open).
- **Decoys / overlap**: Defence sector beta, low-vol / quality.
- **Verdict**: **Weak** (one prelim paper); **Needs data**. The *contract-award event* variant for small defence contractors is an unresearched gap worth a quick look.

### political_connections_pac — PAC contribution breadth (Cooper-Gulen-Ovtchinnikov)
- **Thesis**: Firms supporting more candidates (especially winners, home-state, powerful committees) earn higher future returns.
- **Mechanism / Persistence**: Political access as an unpriced intangible; FEC data free but mapping painful.
- **Rule / Evidence**: Cooper, Gulen, Ovtchinnikov 2010 *JF* "Corporate Political Contributions and Stock Returns" (recalled, not verified): 1979-2004, a one-SD increase in the number of supported candidates associated with ~0.2-0.3%/mo higher abnormal returns (recalled). No replication found in this session.
- **Sources**: Cooper-Gulen-Ovtchinnikov 2010 *JF* 65(2); FEC bulk data (free).
- **Horizon / schedule**: 250 sessions; annual.
- **Data needed**: FEC PAC contributions -> ticker; not stored.
- **Individual fit**: Long-only, annual, cheap; small alpha.
- **Decoys / overlap**: Size, regulated sectors, lobbying (same firms).
- **Verdict**: **Weak**; **Needs data**. Merge with lobbying into one "political capital" feature if ever built.

### employee_reviews_glassdoor — Crowdsourced employer ratings
- **Thesis**: Improving Glassdoor ratings (current employees, career opportunities, senior management) predict outperformance.
- **Mechanism**: Employees see demand and management quality first; investors do not read reviews.
- **Persistence**: Data are behind Glassdoor's ToS / paid licences (Thinknum etc.); star-rating drift over time (later paper) weakens the raw measure.
- **Rule (source's own)**: Green, Huang, Wen, Zhou 2019 *JFE*: quarterly change in average rating; long improvers / short decliners; ~0.6-0.7%/mo long-short abnormal return reported in a related 2012-2016 study (Sheng).
- **Evidence**: One JFE paper plus theses; no formal replication; indirect evidence of measurement drift.
- **Sources**: https://faculty.georgetown.edu/qw50/EmpReviews.pdf ; CFA Digest https://rpc.cfainstitute.org/research/cfa-digest/2020/05/dig-v50-n5-3 ; Neudata review https://www.neudata.co/intelligence/crowdsourced-employee-reviews-predictor-of-stock-returns .
- **Data needed**: Review data — **missing / not licensable to individuals**.
- **Verdict**: **Promising** academically, **Out of scope**.

### job_postings_growth — Online job postings
- **Thesis**: Growth in a firm's job postings predicts sales/earnings growth and short-window returns; labour-market-linked firms' returns lead-lag (Liu & Wu "Labor Links" 9.36%/yr).
- **Mechanism**: Hiring intentions precede revenue; postings are public but unaggregated.
- **Persistence**: Aggregated data (LinkUp, Lightcast/Burning Glass, Revelio) are institutional products.
- **Rule (source's own)**: Gutierrez, Lourie, Nekrasov, Shevlin (*Mgmt Sci*): change in posting count -> one-year-ahead employee, SG&A, sales, earnings growth; returns over two days around the change. Liu-Wu 2019 WP: labour-competitor network lagged returns, 9.36%/yr long-short.
- **Evidence**: Mostly fundamentals-prediction; direct return predictability modest; vendor case studies are marketing.
- **Sources**: https://www.linkup.com/insights/research/what-a-job-posting-tells-us-about-a-company ; https://www.neudata.co/literature-reviews/the-link-between-hiring-pools-and-stock-returns ; *J. Financial Markets* 2023 "Job postings and aggregate stock returns" (aggregate, not firm-level).
- **Data needed**: Postings panel — **missing**. Free proxy: 10-K employee headcount change (Item 1 / XBRL `dei:EntityNumberOfEmployees` where tagged) — the "employee growth" anomaly (Belo-Lin-Bazdresch 2014 *JPE*: hiring rate negatively predicts returns, i.e. the *opposite* sign to posting growth — a warning about decoys).
- **Verdict**: **Weak**, **Out of scope**; file `employee_growth_10k` (financials/text only, sign negative per Belo et al.) as a cheap variant for the fundamentals family.

### web_traffic_app_downloads — Similarweb traffic, app downloads
- **Thesis**: Growth in website traffic / app downloads during the quarter predicts the earnings surprise and post-announcement return.
- **Mechanism**: Real-time demand proxy for digital businesses; analysts under-use it.
- **Persistence**: Data cost (Similarweb, Sensor Tower, data.ai) and institutional licensing; the alpha is harvested by funds before the print; Chen-Liu-Wu find firm *disclosure* of app metrics kills the predictability.
- **Rule (source's own)**: Armstrong, Konchitchki, Zhang, *TAR* Nov 2025: Similarweb visits for ~1,000 large firms (90% of US cap); long top traffic-growth / short bottom earns substantial risk-adjusted returns; one month of a quarter's traffic forecasts the quarter. Chen, Liu, Wu 2024 WP: abnormal app downloads -> next-quarter earnings, forecast errors, returns; ~12%/yr EW long-short.
- **Evidence**: Recent, credible, but gross and institutional.
- **Sources**: https://newsroom.haas.berkeley.edu/companies-website-traffic-proves-powerful-predictor-of-financial-performance-and-stock-returns/ ; https://afajof.org/management/viewp.php?n=114548 .
- **Data needed**: **missing / unaffordable** for an individual (Similarweb enterprise; Sensor Tower). Free crumbs: Google Play install bands, Apple chart ranks — too coarse.
- **Verdict**: **Promising** academically, **Out of scope**.

### satellite_cardpanel_nowcasting — Satellite imagery and card-transaction panels
- **Thesis**: Parking-lot counts / card spend nowcast retailer sales; informed funds trade it before earnings.
- **Mechanism**: Real demand data ahead of the print.
- **Persistence / why individuals cannot get it**: Katona, Painter, Patatoukas, Zeng (*Mgmt Sci* 2025, "On the Capital Market Consequences of Big Data: Evidence from Outer Space", recalled): after satellite data became commercially available, sophisticated investors' trades became more informed and *retail* trades lost money around earnings for covered retailers — the data widened the gap. Card panels (Earnest, Consumer Edge, Facteus) cost six-figure annual licences, prohibit redistribution and require entity mapping; the alpha is a few days before earnings and is crowded (Zhu 2019 *RFS* "Big Data as a Governance Mechanism": alt-data coverage raises price informativeness and reduces mispricing).
- **Evidence**: Solid that the data are informative; equally solid that the rents go to the licensees.
- **Sources**: Katona et al. (Management Science, 2025; earlier SSRN 3222741); Zhu 2019 *RFS* 32(5); Froot, Kang, Ozik, Sadka 2017 *JFE* "What do measures of real-time corporate sales say about earnings surprises and post-announcement returns?" (recalled).
- **Verdict**: **Out of scope**. Lesson for us: expect *less* PEAD in large retailers/consumer names covered by alt data, and more in names without card/satellite coverage — a testable conditioning variable for the filed PEAD edge.

### canslim_episodic_pivot_vcp — Discretionary growth-breakout setups (O'Neil, Minervini, Qullamaggie)
- **Thesis**: Buy strong-earnings-growth leaders breaking out of tight bases on volume (CAN SLIM / SEPA / VCP), or gapping up >10% on an earnings/news catalyst with huge volume ("episodic pivot"), hold while the trend persists.
- **Mechanism**: Institutions accumulate over weeks (capacity), so after a catalyst the first day's move is incomplete; growth leaders exhibit earnings and price momentum.
- **Persistence**: The academic analogues (12-1 momentum, 52-week-high, PEAD, earnings-revision momentum) persist via under-reaction; the discretionary overlays (base shape, "tightness") add rules nobody has validated.
- **Rule (source's own)**: AAII's CAN SLIM screen (quantified O'Neil rules: EPS growth, relative strength, institutional sponsorship, new highs): since 1998 the original screen's hypothetical EW monthly-rebalanced portfolio shows 19.2%/yr price gain vs 5.7% for the S&P 500 price index (AAII, June 2023), with 0 passing stocks that month; variants 15.4% and 12.2%; risk index 1.5-1.9x the S&P. Minervini "trend template" = price above rising 50/150/200-day MAs, within 25% of 52-week high, >30% above 52-week low; VCP = successive contractions in pullback depth before breakout. Qullamaggie episodic pivot = gap > ~10% on earnings/news with volume multiple, buy the opening range high, trail by 10/20-day MA. **No peer-reviewed test of VCP or episodic pivots exists** (none found).
- **Evidence**: AAII screens overall: 12.1% gross CAGR vs 7.0-8.5% benchmarks (60 screens, 1998-2018), 9.4% after 0.5% frictions, with outperformance deteriorating over time (independent review); North & Stevens 2015 *Financial Services Review*: >30% of AAII screens show significant alpha after costs and factors. CAN SLIM's result is gross, EW, monthly, small-cap heavy — a momentum + growth + small-size tilt. Episodic pivots overlap the filed "momentum at earnings" and PEAD; the 52-week-high effect (George-Hwang 2004 *JF*) is the academic VCP cousin.
- **Sources**: AAII 2023 https://www.aaii.com/journal/article/68036-a-tribute-to-william-o-neil-revisiting-the-can-slim-strategy ; AAII risk/return review https://www.aaii.com/stockideas/article/10937-examining-the-risk-and-return-characteristics-of-the-aaii-stock-screens ; North & Stevens 2015 https://openjournals.libs.uga.edu/fsr/article/download/3239/2874/9314 ; CXO on CAN SLIM https://www.cxoadvisory.com/?p=4199 .
- **Horizon / schedule**: 20-120 sessions; on_event:earnings gap (episodic pivot) or every_session (breakout screen).
- **Data needed**: Daily bars + volume (have), earnings events/surprises (have), EPS growth from financials (have), 52-week high (feature). **Ready**.
- **Individual fit**: Designed for individuals; long-only; concentrated; high turnover in the breakout version; the gap-up event version is EOD-executable (buy next open after the gap day — tests whether day-2+ drift exists after a >10% earnings gap with volume >3x).
- **Decoys / overlap**: 12-1 momentum and momentum-at-earnings (filed), PEAD (filed), 52-week high, small-cap tilt. The only non-redundant hypothesis is "volume-confirmed large gaps have *more* drift than same-size gaps without volume" — test that.
- **Verdict**: **Weak** as described by its authors (no independent evidence), **Promising** as the testable variant `earnings_gap_volume_drift`; **Ready**.

### quantpedia_sweep_misc — Quantpedia / Alpha Architect / book families not elsewhere in F
- **Thesis**: A sweep for edge families missing from the standard academic lists.
- **Findings** (Quantpedia strategies page, stated gross performance, not peer-reviewed): #0238 Reversal in PEAD (40.3%/yr claimed — suspicious; variant of filed PEAD); #0271 Earnings announcements + repurchases (25.2%, vol 11.1% — see `eight_k_item_event_drift`); #0046 Short-interest long-only (26.8% — **blocked**, no short interest data); #0037 NCAV (31.2% — deep value, other family); #0162 momentum in small portfolios (32%); #0108 soccer-club arbitrage (irrelevant). Tags include "alternative data" and "machine learning" categories mostly populated by the papers above. Alpha Architect: value+momentum combos, "trading costs destroy factor investing" (Novy-Marx-Velikov summary), industry momentum via TNIC. AQR "Fact, Fiction" series: momentum, value, size, low-risk — size has no premium without the junk filter (Asness et al. 2018 "Size Matters, If You Control Your Junk"), relevant decoy for every small-cap-tilted idea here. Pedersen *Efficiently Inefficient*: the edge classes an individual can hold are event-driven and liquidity provision, both needing patience. Ilmanen: expected returns are low, harvest many small premia, cost discipline. Lopez de Prado: deflated Sharpe / probability of backtest overfitting — belongs in the harness (see Meta). Chan: mean reversion / pairs (other family). Clenow *Stocks on the Move*: momentum ranked by exponential regression slope x R^2, 100-day MA gap filter, regime filter on the index — a price-family variant. Carver *Systematic Trading*: forecast scaling and combination, position sizing by vol — tooling. Zuckerman: RenTec's edge is thousands of tiny short-horizon signals and execution — explicitly *not* replicable by us.
- **Verdict**: No new family found that is not already in A-E or above; the three transferable items are the junk-controlled size decoy, the buyback-event variant and the deflated-Sharpe gate.

---

## Meta: decay, costs, multiple testing — what to hard-code into the harness

- **Out-of-sample and post-publication decay**: McLean & Pontiff 2016 *JF*, 97 predictors: returns 26% lower out of sample, 58% lower post-publication (32 pp attributed to publication-informed trading). Chen & Zimmermann (2020 *RAPS* "Publication Bias"): bias-adjusted returns only 12.3% (s.e. 1.7 pp) smaller than in-sample, so most decay is *trading*, not bias; Chen (2024): about 50% decline after the sample ends; an ASU 2025 study of 177 anomalies 1926-2023 finds post-publication alphas lower but still significant. JKP 2023 *JF*: >80% of ~150 factors replicate, 13 themes, work in 93 countries. **Rule for us**: expected size = published x 0.5 for US published anomalies; x 0.3 if the paper is pre-2010 and the signal is in a vendor product.
- **Multiple testing**: Harvey, Liu, Zhu 2016 *RFS*: with ~316 published factors a new factor needs t > 3.0, not 2.0. Lopez de Prado: report the deflated Sharpe ratio and PBO per edge. **Rule**: t > 3 on the harness's point-in-time test *and* >= 40 independent events.
- **Costs and turnover**: Novy-Marx & Velikov 2016 *RFS*: anomalies with one-sided monthly turnover < 50% mostly survive costs when built to mitigate them; higher-turnover ones rarely do; buy/hold bands are the single most effective mitigation; capacity falls with turnover. Avramov-Cheng-Metzker 2023: ML/anomaly profits concentrate in microcaps, distressed, high-friction names — which for a fund is a bug and for us is the point, provided the names are tradable at our size. JKMP: cost-aware optimisation shifts weight to slow signals. **Rule**: prefer quarterly/annual signals (filing text, patents, composite with bands); daily text signals are classifiers inside events, never strategies.
- **Which anomalies survive costs for a small account**: low-turnover value/quality/composite tilts (trivially), event drifts with 20-60 session holds (PEAD, 8-K items, buybacks, short reports), filing-text change (quarterly). Not: daily sentiment, weekly attention, monthly link-momentum without bands.
- **Crowding**: a signal sold by a vendor (Brain Lazy-Prices scores, S&P call-alignment, Similarweb) should be assumed harvested in the Russell 1000; test everything in the small/mid residual first.

## Gaps: edge families suited to an individual that none of the standard lists cover

1. **Odd-lot priority in tender offers / Dutch auctions** — issuer tenders and odd-lot provisions (SC TO-I filings) pay holders of < 100 shares in full without proration; capacity is literally 99 shares per account, so institutions cannot touch it; events ~20-40/yr; data: EDGAR SC TO-I/SC TO-T (we store filing events) + daily bars. No academic paper quantifies the retail odd-lot return; it is a structural, not statistical, edge. **Ready-ish**.
2. **Index-exclusion / price-floor constraints**: stocks under $5 (many mandates and margin rules), under $300m cap, or with no analyst coverage ("neglected firms", Arbel-Strebel 1983 recalled) carry premia that funds cannot harvest; combine with the composite score in that segment only. Related: post-reverse-split and post-uplisting (OTC -> Nasdaq) names, where our universe starts covering them.
3. **DoD 5 pm contract announcements and USAspending awards for micro-cap contractors** — daily, public, time-stamped after the close, no literature; a clean EOD event test.
4. **SEC correspondence and non-timely filings (NT 10-K / NT 10-Q)**: late-filing notices predict negative drift (recalled literature, not verified) and are free EDGAR events we may already store as filing types.
5. **LLM over micro-cap 8-K press releases (Exhibit 99.1)**: Lopez-Lira-Tang's alpha is "small stocks + bad news"; our 8-K store plus text seam gives exactly that slice without a news licence; the first actionable session is unambiguous (acceptance time).
6. **Index-fund and ETF holder constraints on hard-to-borrow names after short reports** (tie-in with `short_seller_report_drift`): our ETF holdings data can show which targets are held mostly by passive funds that will not sell — a conditioning variable.
7. **Alt-data coverage as a conditioning variable**: PEAD should be weaker in names covered by card/satellite panels (large consumer/retail) and stronger elsewhere (Katona et al.; Zhu 2019). Costless to test with filed PEAD.
8. **Post-report "fraud dossier" deep dives**: our owner-run deep-dive skill + dossier import can produce manual forensic reads for tiny names at a cadence no fund bothers with — a process edge rather than a signal; keep the harness honest by logging each as an event.
9. **Missing-data edges to unblock**: Form 4 insider clusters, short interest / borrow fees and 13F-based "crowded hedge-fund longs" are all free-ish (EDGAR Form 4, FINRA short interest twice monthly, EDGAR 13F) and sit behind well-evidenced anomalies in other families; this family's text/LLM tooling (entity extraction, name->ticker) is what they need.

## Rejected on sight
- Satellite / card-panel nowcasting as our own strategy: unlicensable at individual scale; alpha crowded and pre-earnings (use only as a conditioning variable).
- Chen-Kelly-Xiu full-news embeddings: needs a licensed news corpus and daily turnover.
- Earnings-call vocal cues: audio data and one-paper literature.
- Glassdoor / job-posting / web-traffic / app-download panels: institutional data products; retail cannot licence.
- Reddit / StockTwits / Twitter sentiment: day-long effects, API now paid, 2021 regime.
- Google SVI and Wikipedia attention as standalone strategies: weekly turnover, conflicting signs, free-data crowding.
- Congress-trade copying (NANC/KRUZ): no post-disclosure alpha in 2020-2024 data; fund returns are beta.
- Kelly-Malamud-Zhou "virtue of complexity" market timing: not cross-sectional; critiqued as vol-scaled momentum; nothing for us to hold.
- Daily LLM-headline long-short: decaying with adoption; headline timestamps vs close = lookahead trap; keep the classifier, drop the strategy.
- Quantpedia "soccer clubs arbitrage", "overnight Bitcoin seasonality": out of universe.
- Short-interest effect (Quantpedia #0046): blocked — no short interest stored.
- Lobbying / PAC "political capital" as a standalone edge: old, small, sector bet; at most a feature.
- Dictionary-based 10-K tone (MD&A, readability/file size): commoditised; keep only as features inside the filing-text group.
- Shared-analyst-coverage momentum as filed: needs I/B/E/S analyst identities; file the TNIC / conglomerate / customer legs instead.
