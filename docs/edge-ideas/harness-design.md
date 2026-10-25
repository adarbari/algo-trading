# Edge harness: archetypes the catalogue needs (architect design, 2026-10-17)

Scope: what the harness (ADR 0053 + amendments, ADRs 0063-0065) must gain so the Strong and
Promising ideas in `docs/edge-ideas/` can be filed and judged faithfully. Screeners and catalogue
features per idea are NOT in this plan (they follow `add-screener` / `add-feature` per edge);
this is the harness only.

## 0. What already exists (so we do not rebuild it)

- `quant/edges/statistics.py`: lift, Hedges g, decile spread, Sharpe, deflated Sharpe, PBO,
  `haircut_sharpe` (Harvey-Liu Bonferroni: already returns `t`), random-pick sums, win-rate band.
- `SessionStat.deciles` / `spread` (`cross_section/measures.py:66-91`): the top-minus-bottom
  decile is already measured every session, and `config/site/verdict.toml` already gates Works
  on a decile-spread `t >= 3.0` (`works_t`). So a *diagnostic* long-short exists today; what is
  missing is a K-name short leg with costs, a short-only edge and a ledger for it.
- `core/time/calendar.py` (owner `session-calendar`): `monthly_expiry`, `last_session_of_month`,
  `holidays`. Calendar windows build on it; nothing new knows holidays.
- `Edge.baselines`: decoys are screeners already (`size_small`, `momentum_12_1`).
- `fwd_realised_vol` is in the grain (`data/outcomes/reading.py:18`); `expires_otm` is
  harness-side from IV at D and the price path (`cross_section/hit.py:87`), not from premiums.

## Blocking issues found while designing (fix first)

B1. **Folder cap.** `config/site/edges/` is flat (`<id>.toml`, 8 files) and config folders cap at
12 files (CLAUDE.md layout rule, no exceptions). ~140 ideas (fewer after merging variants) cannot
land there. Fix: one folder per edge, `config/site/edges/<id>/edge.toml`, exactly the
`config/site/presets/screeners/*` pattern (folders are not files). Loader
(`config/edges/loading.py:149+`) reads `<id>/edge.toml`; user layer
`config/users/<u>/edges/<id>.toml` unchanged (git-ignored, id is the key). Add `family = "A".."I"`
as a document key for `docs/edges.md` grouping. Layout entry `config/site/edges/*`.

B2. **Declared event classes that cannot run.** `EVENT_CLASSES` (`config/edges/document.py:101`)
declares five classes; `EVENT_FIELDS` (`cross_section/events.py:57`) declares two. A document on
`on_event:ex_dividend | index_change | macro_release` validates, then fails at run time with a
ConfigurationError. Fitness test: `set(EVENT_CLASSES) == set(EVENT_FIELDS)` (the test that would
have caught it, rule 4), plus the three missing fields (or remove the classes until built).

B3. **Chains start 2026-10-02**, after the frozen split (2026-04-01). Any outcome built on
`chains/option_quotes` has zero pre-frozen history: no exploration period, no basis fixable
before the frozen period in the ADR 0065 sense, and >= 40 independent events takes 10+ months.
OPTION_PNL below therefore splits into a model P&L (history now) and a chain P&L (accrues).

B4. **Tiingo Power ends 2026-11-09.** CALENDAR_TS and ALLOCATION need ETF and index-proxy history
from 2010 (bond, commodity, international ETFs included) and the outcomes backfill over it. The
pull must finish before the budget returns to the free tier: an ops item that gates H5/H8 data,
not code.

B5. **Site-wide multiple testing.** 140 edges x variants x horizons is the trial count the
literature's t > 3 bar is about. Today's deflated Sharpe counts one edge's trial log only.
Handled in H1.

---

## (1) LONG_SHORT

Change (smallest fit): `[outcome] side = "long" | "short" | "long_short"` (default `long`), in
`OUTCOME_KEYS` so a `[[variants]]` row can compare sides (each variant is a trial, as today).
- `short`: picks are the bottom K of the screener's ranked eligible names (`picks.py`: the same
  `RankedRun`, read worst-first); oriented value = minus the excess return; hit = the name
  underperforms. Serves the avoid-list ideas (thematic ETF fade, IVOL/MAX, issuance) honestly.
- `long_short`: session value = mean(top K) - mean(bottom K) of the ranked eligible; no base
  rate (hit rate / lift are served as not applicable, with a public reason, never 0); the trial
  value (ADR 0064 `trial_value`) is the spread.
- Requires a screener that ranks (nearly) the whole eligible set: validated at run time against
  the existing score-coverage rule (`excluded_score_coverage`); a rule screen that qualifies 30
  names cannot have a bottom leg (fail closed, not a short leg of the 30 worst passers).
- Costs: the short leg pays `cost_bps` plus `borrow_bps_annual` (new outcome key, default from
  `verdict.toml [edge_costs] borrow_bps_annual`, scaled by horizon). No borrow data exists:
  state it as an assumption in the report; a short leg is restricted to names over
  `capacity_adv_floor_usd` (the microcap short is not implementable for an individual).
- Random picks: same draws (seeded by leg key, ADR 0063); short = minus the draw; long_short =
  draw A - draw B (two seeded draws).
- Ledger (`results/edge_trades`) gains a nullable `side` column; legs gain `short_values`
  defaulting to empty, so legs of `long` trials are byte-identical and need no `LEG_VERSION`
  bump (the codec test must prove an absent field round-trips). `side` enters the leg key
  through the outcome (already part of the trial key).
- `[published] leg = "long_short" | "long" | "short"` so the decay read compares like with like
  (see 7b).
Files: `config/edges/document.py`, `cross_section/{picks,hit,measures,random_picks}.py`,
`cross_section/legs/rows.py`, `cross_section/detail/trades.py`, `services/read/evaluation/verdict/`
(basis may be a side), Guide entries for the three values (`guide_coverage.toml`).
ADR: amendment to 0053 ("outcome sides") and to 0065 (the basis names a side).
Risks: a bottom leg drawn from names with no score (UNKNOWN read as worst) is the classic
missing-as-zero leak: unscored names are excluded from both legs, counted; delisted shorts are a
gain only if the delisting return is measured (DELISTED rows exist in v2; a delisted short with
no return is excluded, not booked at -100%).
Effort M. Architect review (verdict semantics, legs).

## (2) CALENDAR_TS

Two parts; the first is nearly free.

(a) Calendar windows as a schedule, in the cross-section harness. `schedule = "calendar:<window>"`,
windows a closed set in code (like `EVENT_CLASSES`), each `(anchor rule, entry offset, length)`
computed from `core/time/calendar.py`:
`turn_of_month` (S = the session before the month's last, length 4: sessions -1..+3),
`opex_week` (monthly_expiry week, length 5), `quarter_end` (last 5 sessions of a quarter),
`pre_holiday` (the session before a holiday, length 1), `month_end` stays as is. A window has a
fixed length, so `horizon_sessions` must equal it (validated) and the existing grain serves it:
no outcome change. D = S - 1 as every schedule; windows never overlap by construction. This
covers "OPEX week large caps vs the rest" and "quarter-end rebalancing losers vs winners".
New module `core/time/windows.py` (pure, owned by `session-calendar`; extend its ownership
entry) or a function beside `monthly_expiry`; `cross_section/sessions.py` gains the schedule.

(b) A time-series base for one instrument (or a short list) timed by a window:
`base = "out_of_window"` (new `BASES` value, legal only with a `calendar:` schedule and a universe
of <= ~10 named instruments). Value per window = the instrument's raw (benchmark `none`) return
over the window; base = the same instrument's returns over every non-overlapping same-length
stretch outside any window in the same date range (tiled deterministically from the first
session after each window). Measures: mean in-window minus mean out-of-window, Welch t, share
of positive windows vs the base's share (hit vs base rate, so the existing verdict words apply),
Sharpe of "long in window, T-bill otherwise" vs buy-and-hold, year and regime slices, frozen
split by window date. Random robustness = 1,000 seeded random same-length window sets (the
random-pick analogue). Independence: one window = one session for every count.
Where: new subpackage `services/evaluation/time_series/` (new folder: `layout.toml`, `__init__`
docstring, tests mirror, ownership `edge-time-series-evaluation` owned by it, statistics in
`quant/edges/statistics.py`). It reuses the outcome reader only through `harness.py`'s seam:
the import contract "only cross_section/harness.py reads outcomes" must be widened to name
`time_series/harness.py` (an import-linter contract edit: architect).
Outcomes needs horizon 1 and the window lengths over `none` for the timed instruments; they
come from the documents (outcomes task reads horizons from edges), plus a backfill from the
Tiingo history (B4).
ADR: new ADR "calendar schedules and the time-series base" (the base is a new comparison, not a
variant of ADR 0053's cross-section base). Number taken at push time.
Risks: a window rule that peeks at the future (e.g. "last 5 sessions of the quarter" needs the
calendar, which is known ahead: fine; a "pre-FOMC" window needs the macro schedule as known at D:
use `on_event:macro_release`, never a calendar window). The one-session rule holds: each window
reads outcome partitions at its own S. Small samples: ~100 ToM windows since 2018, ~190 from
2010; report the t with the count.
Effort: (a) S, (b) M. Architect: (b) and the contract change; (a) implementer after the ADR.

## (3) OPTION_PNL

(a) Model P&L now (history back to the IBKR IV history and the bars): new outcome kind
`option_model_pnl` with `structure = "atm_straddle_long" | "atm_straddle_short" |
"delta_hedged_atm"` and the existing `iv_field`. Value from IV at D (as `expires_otm` reads it)
and the stored path: the delta-hedged straddle's P&L in vega units
`(fwd_realised_vol^2 - iv^2) * T / (2 iv)` (the standard approximation), the unhedged straddle as
`|fwd_return| - straddle_price(iv, T)` (Black-Scholes ATM, `quant/` pricing). Harness-side like
`expires_otm`, no grain change. Labelled `basis = "model"` in results and the UI, licence
inherited from the IV field (IBKR: `personal`). Answers c16 pre-earnings straddle (entry via
`on_event:earnings_expected` with negative offset, already allowed), short put P&L (put payoff
from strike-by-delta, already computed in `hit.py`), VRP size not only win rate.
Effort S-M. Architect review (pricing maths in `quant/`).

(b) Chain P&L (the real thing, accrues from 2026-10-02): new grain
`outcomes/option/structure_pnl@v1`: one row per (underlying, entry session S, structure,
tenor rule, horizon), `session_date = S`, `knowledge_ts` = the exit's chain knowledge time;
columns entry mid / ask, exit mid / bid (or intrinsic at expiry), contract ids, P&L per unit
premium and per underlying, the daily-hedged P&L (hedge with our own Greeks from each
session's chain), `status` COMPLETE | UNMEASURED with a reason (a missing or STALE chain on any
hedge session, `chains/status`, ADR 0054) and never a zero. Writer: ingestion
`tasks/derived/option_outcomes.py` (owner + `tables.toml` entry); reader: `data/outcomes`
(same import contract). Structures and horizons from the documents, like the price grain.
Outcome kind `option_pnl`. ADR: amendment to 0053 (a second outcomes grain) and 0065 (no
pre-frozen basis exists; the basis is declared at filing and every row is out-of-sample).
Risks: chain timing (Cboe EOD arrives ~315 min after close: knowledge_ts is the fetch, the
entry price is S's close snapshot, which is knowable only that evening: entry at S close means
the decision at D = S - 1, unchanged rule); stale chains silently filled is the main leak.
Effort L. Do last; forward-only until history exists (owner decision O3).

## (4) ALLOCATION (ETF rotation / TAA)

Stay in the harness (the trial log, frozen split and verdict live there; the backtest engine has
none). Smallest fit:
- `[outcome] kind = "portfolio_return"`, `base = "benchmark"` (new BASES value): session value =
  weighted pick returns minus the benchmark's over the same window; hit = beats the benchmark.
- `benchmark = "mix:SPY=0.6,AGG=0.4"` parsed into weights; computed in the harness from the
  constituents' benchmark-`none` rows at the same S (they are universe ETFs, so the grain has
  them; a missing constituent row excludes the session with a reason). `BENCHMARKS` stays the
  set the grain stores; mixes are harness-side only.
- `weighting = "equal" | "inverse_vol" | "score"`, the vol a declared feature read at D.
- Cash: a pick `CASH` earns the T-bill yield at D x h / 252 (`rates/treasury`, known at D),
  so a trend filter can go to cash; an empty pick set is a cash session, not an excluded one,
  only for this kind.
- `[ensemble] variants = [...]`: a pre-registered parameter grid (e.g. 3/6/9/12-month lookbacks)
  whose weights are averaged per session into ONE trial; members are reported but can never be
  the basis (ADR 0065). The trial log counts the ensemble once and the grid size beside it.
- OOS haircut: `verdict.toml [oos_haircut] trend = 0.45`; the report shows the in-sample Sharpe
  and the haircut expectation beside the out-of-sample one (display, not a gate).
- Decile spread and base rate are not applicable under ~20 eligible names (served as N/A).
- Turnover cost from H7 (rebalance only the weight change).
ADR: new ADR "portfolio outcomes" (weights, blended benchmark, cash, ensembles). Effort L.
Architect review. Depends on H7, B4, H1.

## (5) PAIR_SPREAD

Built on LONG_SHORT. `kind = "pair_spread"` with `pair_field` (a declared feature read at D giving
each name's sibling id, e.g. `rollup.share_classes@v1.sibling_id` derived from the reference
share-class FIGI / issuer CIK, never a hand list of `EQ:` strings, ADR 0018). The screener picks
the cheap leg (spread z-score feature, read at D); value = r(cheap) - r(sibling) over h from the
same outcome partition at S; borrow on the rich leg as (1). Base = the same spread over every
eligible pair at the session. A missing sibling row excludes the pair with a reason. Also serves
ETF-vs-NAV style two-leg ideas where the second leg is an instrument.
New feature group `share_classes@v1` (add-feature), outcome kind in document.py and hit.py.
Risks: few pairs (~15-25) -> sessions must be spaced a horizon apart and counts shown; a sibling
that changes (reclassification) must be read at D, never today's reference.
ADR: amendment to 0053 within the sides amendment. Effort M. Architect review of the outcome.

## (6) New event classes

How a class is added (one recipe; becomes a section of `add-feature` or a short skill note):
1. A stored event table with `known_from` (ingestion; `tables.toml`; ADR 0050 row contract).
2. A feature group read at D with `sessions_since_<event>` (or `sessions_to_` if announced ahead)
   and `<event>_date`, plus any subtype field (item, direction, form).
3. `EVENT_CLASSES` + `EVENT_FIELDS` entries (B2's fitness test keeps them equal);
   `ANNOUNCED_AHEAD` only when the date is public before the anchor.
4. Optional subtype: `on_event:<class>:<subtype>` where `EventField` declares a `subtype` field
   and its allowed values (fail closed on unknown); the base is the same class and subtype's
   names (so 8-K 4.02 is compared with other 4.02 filers or, with `base = "universe"`, everyone).
5. Guide entry per class and subtype (`guide_coverage.toml`).

`known_from` per class (anchor = the session of `known_from`, never the economic date):

| Class | Table / source | known_from | Notes |
| --- | --- | --- | --- |
| `earnings_date_shift` | `events/earnings` snapshots | session the confirmed date was first stored differing from the year-ago-quarter date | shift = confirmed - year-ago report date (both known). Vendor-backfilled confirmations without a stored time are unusable before we began storing: the history starts there (Needs a check of how far `events/earnings` history goes). |
| `filing_8k:<item>` | `events/filing` | acceptance session (after 16:00 NY -> next session; `filings.py` already does this) | exists; feature group + fields only. S. |
| `nt_late_filing` | `events/filing` extended to forms NT 10-K / NT 10-Q | acceptance session | extend the form filter of the filings task. S. |
| `tender_offer` | `events/filing` forms SC TO-I / SC TO-T | acceptance session | same extension. S. |
| `index_change:addition|deletion` | `events/index_change` + listing history (ED6) | first stored session (>= effective date); history: the effective date | later than the announcement: no lookahead; the deletion-rebound window starts after the effective date, which is what the idea trades. Document the lag. S. |
| `insider_buy` (Form 4) | new `events/insider_trade` from EDGAR Form 4 XML (add-data-source, `algotrade_sources`) | Form 4 acceptance session | never the transaction date (filed up to 2 business days later: the classic leak). Opportunistic vs routine (Cohen-Malloy-Pomorski) is a feature, not a class. M. |
| `lockup_expiry` | listing history first trade + 180 sessions-calendar days | first regular-way session (announced ahead) | the 180-day term is an assumption (varies, early releases): caveat. S. |
| `spin_off` | needs Form 10 / parent linkage | first regular-way session | Needs data; defer. |
| volume shock | NOT a class | - | a screener on `every_session` over `volume@v1.volume_z_20d` with a "no news" feature (`sessions_since_any_event`, from the class fields). A derived "event" whose known_from is its own D adds nothing over a screen. |

Also fix B2 (ex_dividend, index_change, macro_release fields). ADR: amendment to 0050/0053 listing
the classes (the class list is a contract). Effort: framework + subtypes M; each class on an
existing table S; Form 4 M. Architect: the framework and Form 4's knowledge rule; per-class
additions implementer-scoped with a review of each `known_from` rule.

## (7) Measurement improvements

a) **t > 3 beside deflated Sharpe.** `works_t = 3.0` already gates the decile-spread t. Add the
   picks-series t (the trial value's t: `haircut_sharpe(...).t`) per slice as a column in
   `results/edge_eval`, gate Works on both, and a **site-wide trial count** (every open site
   edge's trials, from the run records) passed to `haircut_sharpe` beside the per-edge count;
   the report shows both haircuts. Promising stays `promising_t = 2.0` unless the owner raises
   it (O1). Files: `quant/edges/statistics.py` (none new), `cross_section/results.py`,
   `services/read/evaluation/verdict/`, `config/site/verdict.toml`. ADR 0065 amendment.
   Effort S. Architect review (verdict).
b) **Published-size haircut.** `[published] leg` (from (1)) and `verdict.toml [published_haircut]
   long_short = 0.5, long_only = 0.333`; the edge page shows "published x, expect y" beside
   `[published]`; the decay read compares the realised figure with y. Display only. Effort S.
   Implementer (UI through the Guide + feature-table rules; Guide entry for the haircut).
c) **Decoy battery.** `baselines = ["@standard"]` expands to `verdict.toml [decoys] standard =
   [...]`: `size_small`, `momentum_12_1`, new rank presets `ivol_high`, `max_ret_high`,
   `amihud_illiquid`, `beta_low`, and `composite_mispricing` once filed. Each needs its catalogue
   feature (ivol from the factor regression of (d), MAX from bars, Amihud, beta: add-feature).
   Report per decoy: pick overlap (Jaccard at D) and the edge's spread minus the decoy's.
   Sector: sector-stratified random picks (draws matched to the picks' sector mix at D) as a
   second random baseline; changes the draws, so `LEG_VERSION` bump (all legs recompute once).
   Effort M. Features/presets implementer; the stratified draw architect.
d) **Residual returns.** New grain `outcomes/instrument/residual_returns@v1` (leave v2 untouched,
   no leg invalidation): per (instrument, S, horizon) the return minus sum(beta_k x factor_k
   return) over the window, betas estimated over the 252 sessions ending at D (known at D) on ETF
   factor proxies (SPY market, IWM-SPY size, MTUM-SPY momentum, VLUE-SPY value, the sector
   SPDR): free, point in time, no estimation from our survivorship-prone universe. A
   `factor_betas@v1` feature group (also the decoys' beta / IVOL). Outcome `measure =
   "residual_return"`. Writer ingestion `tasks/derived/outcomes.py` sibling; reader
   `data/outcomes`. ADR 0053 amendment. Risk: factor ETFs start 2013 (MTUM/VLUE): earlier windows
   UNMEASURED with a reason, never market-only silently. Effort L. Architect.
e) **Buy/hold bands.** Keep per-session picks and legs independent (ADR 0063). Add a turnover
   pass over the ordered sessions in reporting: enter at rank <= K, hold while rank <= K_hold
   (`[outcome] hold_rank`); cost charged on entries and exits only; the net series and the
   break-even cost use it. Held-by-band names need their values, so legs store the top K_hold
   (`LEG_VERSION` bump). Gross statistics unchanged. Effort M. Architect (legs, determinism).
f) **SEC acceptance as knowledge_ts.** `financials.py` counts a fact `filed <= session` (a date);
   10-Qs are often accepted after 16:00, so a fact is counted at the close of a session when it
   was not yet public: a one-session lookahead in every fundamentals feature (real leak).
   Join each fact's `accn` to the submission's `acceptanceDateTime` (the submissions endpoint the
   filings task already uses), store `accepted_ts`; rollups count facts accepted before the
   session's close (16:00 NY, early closes from the calendar). New version of the raw facts table
   and `financials@v3` / `fundamentals@v5`, backfill, retire the old. ADR 0067 amendment.
   Effort M. Architect (point in time). Do early: quality / issuance ideas depend on it.

---

## Ordered harness PRs

| # | PR | Effort | Review |
| --- | --- | --- | --- |
| H0 | Edge folder per edge (B1) + `family` key; `EVENT_CLASSES == EVENT_FIELDS` fitness test and the 3 missing fields (B2) | S | implementer; architect glance (new folder) |
| H1 | Picks-series t, site-wide trials, published haircut display, `[published] leg` (7a, 7b) | S | architect (verdict) |
| H2 | SEC acceptance knowledge_ts: facts table version, financials@v3, fundamentals@v5, backfill (7f) | M | architect (PIT) |
| H3 | Outcome sides: short and long_short, borrow, ledger side (1) | M | architect |
| H4 | Event-class framework + subtypes; 8-K item, NT, tender, index deletion, lockup, earnings-date shift (6) | M (+S each) | architect for framework and each known_from |
| H5a | Calendar windows as schedules in the cross-section harness (2a) | S | implementer after ADR |
| H5b | Time-series base, `services/evaluation/time_series/`, new ADR, contract change (2b) | M | architect |
| H6 | Decoy battery: factor_betas@v1, ivol/MAX/Amihud/beta presets, `@standard`, sector-stratified draws (7c) | M | features implementer; draws architect |
| H7 | Buy/hold bands turnover cost, legs K_hold (7e) | M | architect |
| H8 | Option model P&L kind (3a) | S-M | architect (quant) |
| H9 | Pair spread outcome + share_classes@v1 (5) | M | architect |
| H10 | Portfolio outcomes: weights, blended benchmark, cash, ensemble, OOS haircut, new ADR (4) | L | architect |
| H11 | Residual-returns grain (7d) | L | architect |
| H12 | Form 4 source + insider_buy class (6) | M | architect (new source, known_from) |
| H13 | Chain P&L grain `outcomes/option/structure_pnl@v1` (3b) | L | architect |

Dependencies: H0 first (unblocks filing). H1 before any verdict is read on new edges. H2 before
any fundamentals edge. H3 before H9 and before the short-leg ideas. H6's `factor_betas@v1` before
H11. H7 before H10. H5b and H10 need B4's Tiingo pull and outcomes backfill (deadline 2026-11-09).
H13 last (B3). Edge documents and screeners can be filed in parallel from H0 for every
idea whose archetype is already supported (plain top-K cross-section, existing event classes).

Every PR that changes what a leg holds bumps `LEG_VERSION` (H6, H7) and pays one full re-run of
every edge (~25-40 min per event edge today): batch H6 and H7 into the same release window.

## Owner decisions (policy, review-and-release section 2)

- O1 Verdict bar: keep Promising at t >= 2 with Works at t >= 3 on both series (recommended), or
  raise Promising to 3 per Harvey-Liu-Zhu. Changes what users see on existing edges.
- O2 Can a `long_short` or `short` result be an edge's verdict basis, given the broker is
  read-only and the owner may not short? Recommended: yes for `short` on liquid names (avoid
  lists are actionable), `long_short` diagnostic-only unless the owner shorts.
- O3 Historical option chains (paid vendor) to give H13 a pre-frozen history: spending, owner
  only. Recommended: not now; ship H8 (model P&L) and let H13 accrue.
- O4 Tiingo history pull before 2026-11-09 (or extend Power a month): spending if extended,
  owner only. Recommended: pull now within the bought month.
