# Event sensitivity: what moves a name, and what is coming (DRAFT requirements, 2026-10-06)

Status: **requirements settled 2026-10-06** (the owner's decisions in section 8; the three
assumptions at its end were accepted on the owner's delegation). The decision record is
[ADR 0050](adr/0050-event-sensitivity.md); the work items are the EV track in
[roadmap.md](roadmap.md).

## 1. The question

A short-put or wheel seller on a liquid, high-IV name (IV about 40% and up) is paid for the
risk of a sharp drop before expiry. Most sharp drops have a cause that was on a calendar:
the name's own earnings, a peer's earnings (MU reports, WDC and STX gap), a macro release
(jobs, CPI, FOMC), an index rebalance. Some do not (litigation, a guidance cut, a short
report, a tariff headline). The seller wants two things per name:

1. **Looking back:** which kinds of events have moved this name in a big way, how big, how
   often, and whether the move held or reverted.
2. **Looking ahead:** which of those events fall in the next ~90 days and on which dates, laid
   against the option expiries, so an expiry can be chosen to end before an event, or to span
   it knowingly when the premium pays for it.

Today the platform knows the next earnings date (`earnings@v1`, `feature.earnings_before_expiry`)
and nothing else about events: no peer read-across, no macro calendar, no measured reaction.

## 2. Who it is for and the job to be done

The owner (and later other traders) screening for cash-secured puts / the wheel. The job:
"for the names on my list, pick the expiry for each." The product succeeds when, for a name,
the trader can see in under a minute: the events ahead with dates, how much each kind has
moved the name before, and which expiries clear them. It does not pick the trade.

## 3. What counts as an event: the taxonomy

| Class | Examples | Date known in advance | Where the date comes from |
|---|---|---|---|
| **Own scheduled** | earnings (pre / post), ex-dividend, index add / drop and rebalance day, lock-up expiry (recent listings) | yes | `events/earnings` (Nasdaq), `events/dividend`, `events/index_change`; rebalance dates are rules (third Friday of Mar / Jun / Sep / Dec, Russell last Friday of June) |
| **Peer scheduled** | a peer's earnings (NVDA for the semis, JPM for the banks, LULU for apparel) | yes | the peers' rows in `events/earnings`; the peer map (section 4.3) |
| **Macro scheduled** | FOMC decision, CPI, employment report (NFP / unemployment), PCE, GDP, PPI, retail sales, ISM | yes, months ahead | FRED release calendar (`fred/releases/dates`, past and scheduled), FOMC dates from the Fed's published calendar (8 a year) |
| **Market structure** | monthly / quarterly options expiry, triple witching, index rebalances, quarter end | yes, by rule | the exchange calendar (`core/time/calendar.py`) |
| **Unscheduled** | litigation, guidance cut, M&A, analyst action, CEO exit, short report, geopolitics, tariffs, outage, product recall | no | the residual (a big move on a day with no scheduled event), **attributed** from SEC 8-K filings and headlines (section 4.5) and reviewed by the periodic deep dive (section 4.6) |
| **Factor-dated** | a driver found by the deep dive that has its own calendar: Samsung's and SK Hynix's results for MU, an FDA advisory committee or PDUFA date for MRNA / VKTX / SMMT, a court date, an OPEC meeting for UCO, the Bitcoin calendar for MSTR / COIN / the miners | some | the deep dive's dossier (4.6): dated where known, else a watch item with an expected window |

A seller cannot plan an expiry around a truly unscheduled move, but its **base rate** (how
often this name gaps more than X% with nothing on the calendar) is the part of the premium
that is pure jump risk, so it is measured and shown. The point of attribution is to move as
many of those moves as possible into a named factor whose next occurrence *can* be dated.

### 3.1 Leveraged and inverse funds inherit their reference's events

A leveraged or inverse fund has no events of its own and often only two or three years of
history. Its event profile is **its reference instrument's, scaled by its leverage** (the
reference already carries `is_leveraged`, `is_inverse`, `leverage`): a single-stock fund
(TSLL, NVDL, AAPU) reads the stock's events; an index fund (TQQQ, SOXL, DFEN) reads the macro
and market-structure events plus the earnings of the index's top holdings (the ETF holdings
table, ADR 0035, gives the weights; the three largest are the default "peers"); a commodity or
crypto futures fund (UCO, BITO, SLV) has macro events only in v1 (OPEC and EIA dates, the
Bitcoin calendar: v2). The link fund -> reference comes from the holdings table (the swap or
the stock it names) with a name rule as the fallback; it is a stored reference fact, not a
guess in the browser.

The owner's starting list (two batches, 2026-10-06), resolved; the holdings table and
`SymbolResolver` confirm each link once the scope list is seeded:

| In the list | Kind | Reference used for events |
|---|---|---|
| AAPU, AMZU, ASMU, AVL, AVGG, AVGU, AVGX, BRKU, GGLL, METU, MSFU, NVDL, TSLL, TSLQ, UBRL, UNHG | single-stock leveraged | AAPL, AMZN, ASML, AVGO (x4), BRK.B, GOOGL, META, MSFT, NVDA, TSLA (x2), UBER, UNH |
| SOXL, SOXS | semiconductor index, 3x | top 3 of the index: MU, AMD, MRVL (NVDA, AVGO close behind) |
| TQQQ, SQQQ, QLD | Nasdaq-100, 3x / 2x | NVDA, AAPL, MSFT |
| SSO, UPRO | S&P 500, 2x / 3x | NVDA, AAPL, MSFT |
| DFEN | aerospace and defence, 3x | GE, RTX, BA |
| NAIL | homebuilders, 3x | DHI, PHM, LEN |
| UTSL | utilities, 3x | the sector's top 3 by weight (holdings table) |
| NUGT | gold miners (via GDX), 2x | GDX's top 3 (Newmont, Agnico Eagle, then Barrick or Wheaton by weight) |
| IFRA, CLIX | thematic (US infrastructure; long online / short stores) | top 3 by weight (holdings table); CLIX is long AMZN against retailers |
| TNA | Russell 2000, 3x | an index: macro, the Russell reconstitution; no top-3 (largest weight under 1%) |
| EWZ | Brazil | US macro only in v1 (a Brazil calendar is v2) |
| QBUL, QBER, RFIX, SHRT, SLTY, UPAR | option-overlay, rates, long/short and risk-parity funds | macro only (FOMC, CPI, jobs drive them); no peers |
| BITO, BITX, ETHU, UCO, SLV | futures and bullion | macro only in v1; the Bitcoin and OPEC / EIA calendars come from the deep dive's dossier |
| AAPL, ACN, ACVA, AMD, AMAT, AMZN, APLD, APP, ARW, ASML, AVGO, AXTI, BRK.B, CART, CGC, CHWY, CIFR, COIN, CON, CPNG, CRWV, CVNA, DDOG, FLNC, FPS, GLOO, GM, HOOD, INTC, IREN, IRDM, KLAC, LQDA, LRCX, LUXE, MARA, MAT, MEDS, META, MRNA, MSFT, MSTR, MU, NFLX, NOW, NU, PLTR, ROOT, SMCI, SMMT, SMTC, SNAP, SNDK, SNOW, STX, TEM, TSLA, TSM, VKTX, VST, WING, WULF | stocks (62) | themselves; the crypto and AI-infrastructure names will find Bitcoin and NVDA as peers through the measurement; the biotechs (LQDA, MRNA, SMMT, VKTX) need the FDA dates the deep dive records |

FPS is Forgent Power Solutions, a stock (its 2x fund is FPSX). GLOO, LUXE, MEDS and CART are
2025 listings or small caps: short history, so the statistics are UNKNOWN until 250 sessions.

## 4. What we measure (the event study)

Every number below is a **catalogue feature at session grain** (ADR 0007, 0023, 0038): computed
nightly over a lookback, known as of the session, UNKNOWN with a reason when the history is
too short. Definitions, to be fixed in the ADR:

### 4.1 The reaction to one event

- **Reaction session**: the event date for a pre-market or intraday event; the next session for
  an after-close event (earnings `time = post`, or an 8-K accepted after the close) and for
  releases after 16:00 ET. The time comes from the source, never from which day moved more; an
  unknown time is counted but excluded from the multiples (`time_unknown`).
- **Move**: the reaction session's close-to-close log return (`ret`) and its overnight gap
  (prior close to open) when bars carry an open. Both signed.
- **Normal day**: the name's trailing 20-session ATR% (or `hv20` / sqrt(252)) as of the session
  before the event, so a reaction is read as a **multiple of a normal day** (MU's earnings day
  moved 3.4 normal days), comparable across names and over time.
- **Point in time**: every event row carries `known_from` (ADR 0050 decision 3) and a
  statistic as of session S uses only events whose inputs are complete by S (the reaction
  session; plus 5 for the reversal; plus 1 for the IV crush), with every window ending at S.
- **Idiosyncratic part**: `ret - beta_252d * ret_SPY` (we have `beta_252d`). Used for own and
  peer events, where the question is the name's own reaction; the raw move is used for macro
  events, where the market component is the point.
- **Held or reverted**: the sign of the 5-session return after the reaction session relative to
  the move (a drift continues it; a reversal gives half or more back).
- **A big move** (decision 7): beyond 5% **or** beyond 2 normal days; both flags are stored so a
  screen or the tab can use either.

### 4.2 Per name and event type, over the lookback

For each (name, event type), over all stored history (2018 on for the scoped names, decision
4; at least 250 sessions for any non-null statistic):

| Feature (working names) | Meaning |
|---|---|
| `n_events` | how many such events hit the name |
| `move_multiple_median`, `move_multiple_max` | typical and worst absolute move in normal days |
| `down_move_worst_pct` | the worst signed down move (what a short put eats) |
| `p_down_gt_5pct`, `p_down_gt_2atr` | share of events with a drop beyond the threshold |
| `share_of_top_moves` | of the name's 20 largest absolute moves in the lookback, the share this event type explains (the "what moves it" pie) |
| `revert_rate` | share of reactions half-reverted within 5 sessions |
| `iv_crush_pct` (own earnings only) | IV30 the session before vs after (`ibkr_iv@v1` has about 500 sessions); whether the premium paid for the move: implied move (from IV30 and days) vs realised |

The unscheduled type is the residual: a reaction session is unscheduled when no own, peer,
macro or market-structure event lands on it. Its `n_events` counts big moves only (there is
no event list to count), giving the jump-risk base rate per year.

### 4.3 Peer sensitivity (which peers matter)

Candidates for a name's peers: the other names in its SEC `industry` / `sic` (stored in the
company details), plus co-holdings of the sector and industry ETFs it belongs to (ADR 0035,
once the owner runs `etf-holdings`), plus the top return-correlated names over 252 sessions
(no vendor needed). Each candidate's **earnings days** are tested as events for the name, and
the peers kept are those whose median idiosyncratic multiple is above 1.5 over at least 4
reports (open decision 3). The result per name: an ordered list `peers_ranked` (peer id,
multiple, n), capped at 10, stored as a feature group row. The peer map is **measured, not
assumed**: a same-industry name that never moves the name is not a peer.

Cost bound: candidates are capped (say 40 per name) and the study runs only for the names in
scope (section 6). The correlation window and the report days tested both end at the session,
so the peer list as of a past session never knows later results.

### 4.4 Macro sensitivity

Each macro release type is an event for every name; `move_multiple_median` per (name, release)
tells which releases matter for it (banks and REITs on FOMC and CPI, discretionary on retail
sales, everyone on NFP in a stress regime). Also the market's own sensitivity per release
(`IDX:SPX` as an entity, ADR 0047), so a name's macro multiple can be read against the index's.

### 4.5 Attributing unscheduled moves (nightly, automatic)

A big move on a session with no calendared event gets a **cause** from two sources, in order:

1. **SEC 8-K filings** (EDGAR, free, point in time by filing timestamp; the SEC source exists).
   The item codes are a cause taxonomy of their own: 2.02 results, 1.01 / 1.02 material
   agreement, 5.02 officer or director change, 7.01 Reg FD (guidance, investor day), 8.01 other
   events (litigation, recalls, settlements), 2.01 acquisition or disposal, 3.01 delisting
   notice, 4.02 restatement. A filing on or just before the reaction session attributes the
   move with high confidence and no model.
2. **Headlines** from Massive's news endpoint (`/v2/reference/news`, on the free tier already in
   use; 5 requests a minute, so the nightly fetches headlines only for the names with a big
   move that session, a few dozen a night, like the descriptions cap). The headline set is
   classified through the existing `TextModel` seam (ADR 0041) into the cause taxonomy
   (litigation, guidance, M&A, analyst action, management, regulation / policy, macro / sector
   read-across, product, short report, other) with a confidence and the quoted headline as
   evidence. Off when the LLM is off: the move stays "unattributed".

Each attribution is one row in `events/attribution` (instrument, reaction session, cause
class, cause text, confidence, evidence refs, `source` = `filing` | `model` | `analyst_review`,
the model and prompt version for a model row, `known_from` = the session it was produced,
`run_id`). The read takes, per (instrument, session), the highest source, then the latest.
The `attributing` nightly step is non-critical (ADR 0039).

### 4.6 The deep dive (periodic, a skill the owner runs)

Finding the **true drivers** of a name is analyst work, not a nightly formula: for MU it is
DRAM and HBM pricing, NVDA's demand, export controls and the Korean memory makers' results;
for MRNA it is HHS vaccine policy and FDA dates; for MSTR it is Bitcoin and its own
financing. So the platform gets a skill, `.claude/skills/event-deep-dive`, that the owner runs
in Claude Code weekly or monthly (one name, a list, or every scoped name):

1. **Reads** the store through the CLI (`algotrade-ingest export ...` or the GraphQL API): the
   name's 20 largest moves with their current attribution, the event-study table, the peers,
   the open 8-K filings and fetched headlines, the previous dossier.
2. **Investigates** the unexplained and low-confidence moves (web, filings, transcripts),
   decides the cause of each, and names the name's **factors**: for each, a kind (peer,
   macro, policy / regulation, commodity, litigation, product cycle, financing, index /
   flows), a one-paragraph description, the past instances it explains (dated, with the
   move), its **next dated occurrences** (a results date of a foreign peer, an FDA date, a
   court date, an OPEC meeting) and undated watch items with an expected window.
3. **Writes a dossier file** (TOML, one per name, under `var/dossiers/<instrument_id>/<run>.toml`;
   reviewed by the owner in the diff against the previous run), then runs
   `algotrade-ingest run dossier-import --path ...`, which validates it (known instrument ids
   through `SymbolResolver`, dates, the cause taxonomy) and writes the rows: attributions with
   `source = analyst_review`, factors into `instruments/factors` (with a `status`, so a
   retired factor is marked, never deleted), dated occurrences into `events/factor_occurrence`
   (so they join the forward calendar), all with the import's `run_id` and the import session
   as `known_from` (a session before the import never sees them). Ingestion stays the only
   writer (ADR 0005); the skill never touches Parquet.
4. **Reports** what changed: moves newly explained, factors added or retired, dates added.

Every import is a run, so the history of the dossier is kept and the UI shows "reviewed on
<date>" per name. A name not reviewed in 90 days is flagged on the Admin screen.

## 5. What the product shows

### 5.1 Explore: an "Events" tab per instrument

1. **What has moved it** (looking back): a table by event type: count, median and worst
   multiple, worst down move, revert rate, share of the biggest moves. Below it the ranked
   peers with their multiples. Below that a timeline of the 20 largest moves in the lookback,
   each labelled with its event, its attributed cause (with the evidence on hover and the
   source: filing, model or reviewed) or "unattributed".
1b. **Its drivers**: the dossier's factors as cards (kind, description, the moves each
   explains, the next dated occurrence, the watch items), with the review date.
2. **What is ahead** (looking forward, next 90 calendar days): a dated list of events with the
   name's historical multiple for that type (own earnings Nov 19 post, 3.4x; NVDA earnings Nov
   20, 2.1x; CPI Nov 12, 1.3x; FOMC Dec 10, 1.6x; Dec 19 quarterly expiry) **and the dossier's
   dated occurrences** (SK Hynix results Oct 24; FDA advisory committee Nov 6), plus its undated
   watch items in a separate block. Unattributed risk as a line: "x unexplained moves beyond 5%
   a year".
3. **Expiry ladder**: the listed expiries from 7 to 90 DTE (weeklies where listed, monthlies
   always) as rows, each showing the events it spans and the summed expected multiple; the
   last clear expiry is marked: the longest expiry that still spans no own-earnings,
   reference-earnings or macro event (market-structure days ignored); none is marked when no
   expiry is clear.
   The chain data gives the listed expiries (`chains/status`, `nearest_expiry@v1`).

### 5.2 The price chart: event markers

The instrument's price chart (Explore) gets markers on the reaction sessions, coloured by
event class, with the move and the label on hover, and the upcoming events as markers past
the last bar. One design-system component (`add-ui-component`), used by the Events tab and
the Overview chart.

### 5.3 Cross-name calendar (v1)

One calendar for a set of names (the scope list, a screen's results, or a watchlist): the next
90 days, one row per day with the events of every name that day, each with its multiple; the
expiry Fridays as ruled lines. Answers "which of my names have something before the November
monthly" at a glance. It reads the same `event_calendar` rows as the tab (ADR 0038: the
browser derives nothing).

### 5.4 Ideas and screeners: features a rule screen can use

The per-name features of 4.2 and derived expression features (TOML, `add-feature`), for
example: `next_impact_event_date` and `days_to_next_impact_event` (the first scheduled event
with a multiple above a threshold), `impact_events_before_expiry` (at the target expiry, like
`earnings_before_expiry`), `unscheduled_gap_rate_1y`, `peer_earnings_multiple`,
`macro_multiple_fomc`. Each ships a field-guide entry (fitness test), so a Builder sentence
such as "liquid names with IV rank above 50 and no impact event before the November monthly"
drafts correctly.

### 5.5 Admin: the scope list and coverage

An Admin screen lists the names in the event-study scope (section 6) and lets an admin add or
remove a ticker (resolved through `SymbolResolver`, ADR 0018; a leveraged fund shows the
reference it maps to), shows each name's last deep-dive review date (stale after 90 days)
and the share of its big moves attributed. Coverage of the new tables appears in the
completeness view like any other group, and the macro calendar's next 90 days is visible so a
missing release is noticed.

## 6. Scope

**Names** (decision 1): the optionable names whose short-put side is tier A or B
(`short_put_ok`, about 1-2k) **plus a site scope list** managed from Admin (the owner's list in
3.1 is the first content), plus the references those names map to (a leveraged fund pulls its
reference in). The displayed selection in Ideas stays a rule screen.

**History** (decision 4): bars and earnings dates **from 2018-01-01 for the scoped names**;
the rest of the universe keeps its current two years and grows nightly.

**In v1**: own earnings, ex-dividend, index change and rebalance days, measured peer earnings,
all eight macro releases (decision 2: FOMC, CPI, employment, PCE, GDP, PPI, retail sales, ISM),
market-structure days; attribution of unscheduled moves from 8-K filings and headlines
(decision 5); the deep-dive skill, the dossier import and the factor tables; the Explore
Events tab with drivers, the chart markers, the cross-name calendar, the screener features and
field guide, the Admin scope list; the macro calendar source; the earnings-history and
bar-history backfills; the leveraged-fund reference link.

**In v2**: structured calendars the dossier can only hand-enter today (FDA / PDUFA, OPEC and
EIA, the Bitcoin calendar, a Brazil calendar for EWZ); headlines for every scoped name every
night (a paid news tier); analyst and investor days as a source.

**Non-goals**: predicting direction or size of the next reaction (we show the history, not a
forecast); intraday; any trade recommendation or order; news ingestion in v1.

## 7. Data: what we have, what we need

| Need | Have | Gap and the way to close it |
|---|---|---|
| Daily bars from 2018 for the scoped names | `bars/1d` 2024-10-03 to 2026-10-05 (about 500 sessions) | a backfill for the scope list, its references and the tier A / B names: **Tiingo** daily prices (the default, owner decision in EV1d; one request per symbol from 2018-01-01; unadjusted `open/high/low/close/volume` stored with `source = "tiingo"`, corporate actions applied at read time as for Massive (ADR 0016), its `splitFactor` checked against `events/split`; free tier 500 symbols a month, 50 requests an hour, 1,000 a day, the $10 a month Power tier lifts the symbol cap; licence `personal`). Stooq, the first choice, now answers its daily CSV with a JavaScript browser-verification page: unusable |
| Earnings dates with pre / post time from 2018 | `events/earnings` from 2026-10-02 only (upcoming calendars) | **backfill**: the Nasdaq calendar by past date (`algotrade-ingest earnings --from --to`, one request a session; Nasdaq serves 2018 dates, verified below), with SEC 8-K Item 2.02 filings (EDGAR, free, the exact date and acceptance time of every results release, back decades) as the authoritative source; both land in `events/earnings` with `known_from` = the report date (ADR 0050 decision 3; one confirmed report per quarter; folds in the deferred "Events point in time" item). Nasdaq history resolves tickers through the earliest reference snapshot (a reused ticker goes to today's holder); the CIK-keyed 8-K rows of EV1c are the authoritative history and supersede it (they now exist: the `filings` task writes `events/filing` and the Item 2.02 releases as `events/earnings` rows with `source = "sec_8k"`, `ts` the acceptance instant, `time` `pre_market` / `intraday` / `after_hours`; the per-quarter precedence over the Nasdaq rows is EV2's). A calendar day the nightly failed to fetch carries the previous snapshot's forecasts forward (`carried_from`), so a failed fetch never cancels knowledge. |
| Ex-dividend, splits, index changes | `events/dividend`, `events/split`, `events/index_change` | none |
| Peer map | SEC `sic` / `industry` / `sector` on company details; ETF holdings table (pending the owner's run); bars for correlation | a peer **selection** is new (4.3) |
| Leveraged fund -> reference link | `is_leveraged`, `is_inverse`, `leverage`; the holdings table names the swap / stock | a catalogue feature `fund_reference@v1.reference_instrument_id` (ADR 0038) with a name-rule fallback resolved through `SymbolResolver` |
| Macro release calendar, past and future | FRED adapter (observations only); `macro/series` | a new `fred/releases/dates` fetch into a new `events/macro_release` table (release id, name, date, time); the FOMC dates from FRED too (release 101, verified below), ISM by its rule |
| Listed expiries per name | `chains/status`, `nearest_expiry@v1` (chains stored from 2026-10-02) | none for the ladder; weekly listing is read from the chain |
| IV around earnings | `ibkr_iv@v1`, about 500 sessions | none (the crush statistic covers two years, not 2018) |
| The scope list, editable | nothing | a site-level config written by the API: the API writes only user configs today (ADR 0029), so an admin-owned site list is an ADR amendment with the same `services/authoring` seam |
| 8-K filings with item codes | SEC EDGAR source (company details, facts) | done (EV1c): per-CIK submissions JSON for the whole universe as the one-time backfill, EDGAR's daily form index (`sec_daily_index`) as the nightly that picks the CIKs to ask, into `events/filing` |
| Headlines | the Massive vendor (bars, descriptions) | its news endpoint, capped per night to the names with a big move; the text model classifies (`config/site/llm.toml` on) |
| Dossiers (factors, reviewed attributions, dated occurrences) | nothing | the deep-dive skill writes TOML; `dossier-import` writes `instruments/factors`, `events/factor_occurrence`, `events/attribution` |

Verified against the live sources on 2026-10-06 (probes, not tests):

- **Nasdaq** `api/calendar/earnings?date=D` serves 2018 dates (234 rows on 2018-10-25), so the
  earnings backfill reaches 2018 from one source.
- **SEC** `data.sec.gov/submissions/CIK##########.json` lists every filing with `form`,
  `filingDate`, `acceptanceDateTime` (UTC) and `items` ("2.02,9.01"); the recent block holds
  about 1,000 filings and `filings.files` names the older pages (Micron: back to 1994).
- **FRED** `fred/release/dates?release_id=N&include_release_dates_with_no_data=true` returns the
  scheduled future dates (CPI, id 10: 2026-10-14, 2026-11-10, 2026-12-10). Release ids: 9
  Advance Monthly Sales for Retail and Food Services, 10 Consumer Price Index, 46 Producer
  Price Index, 50 Employment Situation, 53 Gross Domestic Product, 54 Personal Income and
  Outlays (PCE), 101 FOMC Press Release (so the FOMC dates need no site file). ISM is not on
  FRED: its dates follow a rule (manufacturing the first business day of the month, services
  the third).

## 8. Decisions

Taken (owner, 2026-10-06):

1. **Names in scope**: tier A / B short-put names plus an Admin-managed scope list, seeded with
   the owner's two lists (3.1); ETFs in the list resolve to their reference and top holdings.
2. **Macro releases**: all eight.
3. **Peers are measured**, not assumed: candidates from the same industry, the same sector ETFs
   and the most correlated names; kept when the name moved more than 1.5 normal days on at
   least 4 of the candidate's report days (median).
4. **History**: 2018 on for the scoped names; the list is managed from the Admin UI.
5. **Unscheduled moves are attributed from news**, in v1: 8-K filings first, then headlines
   classified by the text model, then the periodic deep dive's review (4.5, 4.6). The goal is
   the true drivers of each name, and their future occurrences tracked in the UI.
6. **Surfaces**: the Events tab (with drivers), markers on the price chart, the cross-name
   calendar and the screener features, all in v1.
7. **Big move**: beyond 5% or beyond 2 normal days of the name's own volatility; both stored.
8. **Expiry ladder**: 7 to 90 DTE.
9. **The deep dive is a skill** the owner runs in Claude Code weekly or monthly; its output is
   stored through an ingestion import and shown in the UI (4.6).
10. **Development**: Opus for the design, storage, point-in-time and quant work; Sonnet for the
    scoped implementation (CLAUDE.md "Agents, models and tokens").

Assumptions to confirm (I proceed on them unless told otherwise):

- **Headline source**: Massive's news endpoint on the current free tier (already a vendor
  here; 5 requests a minute, so headlines are fetched for the names with a big move that
  session, not for every name every night).
- **8-K filings** as the first, model-free attribution source, with their item codes as the
  cause taxonomy's backbone.
- **Dossier format and flow**: TOML per name under `var/dossiers/`, reviewed as a diff, imported
  by `algotrade-ingest run dossier-import`; the skill reads through the CLI and the API, never
  the Parquet files.

## 9. Fit with the platform (becomes the ADR)

- **Tables** (`add-dataset`, each with its run mode): `events/macro_release`, `events/filing`
  (8-K items), `events/attribution`, `instruments/factors` (with `status`),
  `events/factor_occurrence`, all with `known_from`; backfilled rows in `events/earnings` and
  `bars/1d`. Owner: ingestion tasks (the dossier import included).
- **Sources** (`add-data-source`): a FRED release-calendar fetch in the existing FRED vendor;
  the Nasdaq calendar's past-date mode; an 8-K filing-index reader in the SEC source (Item
  2.02 doubles as the earnings-date fallback); Massive's news endpoint in the Massive vendor;
  Tiingo daily prices (a new vendor, EV1d; Stooq is unusable, section 7).
- **Text model**: a second use of the `TextModel` seam (ADR 0041), `services/attributing`:
  headlines in, a cause class with confidence and the quoted evidence out; off when the LLM
  is off.
- **The skill**: `.claude/skills/event-deep-dive` (steps in 4.6), with `scripts/` for the
  export and the import call; the dossier schema is documented in `docs/data/` and validated
  by the import.
- **Scope list**: a site config (`config/site/events/scope.toml`, kind `events`, typed in
  `config/site/events/scope.py`; EV0) written through `services/authoring` by an admin from
  the Admin UI (REST write, `add-api-endpoint`; EV8 amends 0029's "user configs only").
- **Feature groups** (`add-feature`): `event_reaction@v1` (per name, per event type: the 4.2
  statistics as columns per type), `peer_sensitivity@v1` (the ranked peers), `event_calendar@v1`
  (the next 90 days' events per name as a stored row: dates and multiples, so the web derives
  nothing, ADR 0038); expression features for the screener fields. Each with `applies_to`
  (own earnings: `operating_company`, ADR 0045; a leveraged fund reads its reference's row) and
  null statuses (ADR 0042, 0046).
- **Read model** (`add-domain-object`): `InstrumentEvents` (history with attributions, drivers,
  ahead, ladder, markers) and `EventCalendar` (cross-name) in `services/read/`, one loader
  each, GraphQL fields `Instrument.events` and `Query.eventCalendar(instrumentIds | screenId)`.
- **Web** (`add-ui-component`, `add-web-page`): an Events tab under Explore, chart markers, a
  Calendar page (TRADER workspace) and an Admin scope screen; design-system components for the
  timeline, the expiry ladder, the markers and the calendar grid, stories first.
- **Point in time**: one `known_from` date per event row, read as `known_from <= S`; a
  statistic uses only events whose inputs are complete by S, every window ending at S (ADR
  0050 decision 3, reviewed by `architect`; reviewed again with the groups before EV2).
- **Nightly**: the event study is a rollup group in `market-daily` after bars and earnings;
  the macro calendar refresh is a weekly `reference` step; the scope list change triggers a
  backfill job for the added names (`services/jobs`).

## 10. Sequence (each line one or two PRs; model per CLAUDE.md: Opus where marked, Sonnet otherwise)

1. **ADR + data** (Opus, `architect` review): macro release calendar source and table;
   earnings-date backfill (past-date mode and the 8-K Item 2.02 fallback); Tiingo bar backfill
   for the scoped names; the leveraged-fund reference link; the scope list config and its
   import of the owner's list. Owner actions: the backfills (detached; hours).
2. **`event_reaction@v1`** (Opus for the definitions and point-in-time rule, Sonnet for the
   group): own earnings, macro and market-structure events; the unattributed residual;
   `IDX:SPX` as a reference.
3. **`peer_sensitivity@v1`** and peer earnings as events (Opus: the selection rule; Sonnet).
4. **Attribution** (Opus for the tables and the text-model use; Sonnet for the readers): 8-K
   filing index, Massive headlines capped per night, `services/attributing`, `events/attribution`.
5. **The deep-dive skill and `dossier-import`** (Opus: the dossier schema and the import's
   validation; Sonnet: the skill's scripts); first run by the owner on the scope list.
6. **`event_calendar@v1`**, the screener expression features, field-guide entries, phrasebook
   (Sonnet).
7. **Read model + GraphQL; the Explore Events tab with drivers and the chart markers**
   (design-system components first; Sonnet, `add-ui-component` / `add-graphql-field`);
   `make web-build`.
8. **The cross-name Calendar page and the Admin scope screen** (the scope write endpoint;
   Sonnet).
9. v2 items as separate work.
