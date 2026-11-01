> **Plan document for [ADR 0088](../adr/0088-setups-as-positions-and-rules.md)** (the design as reviewed
> and answered by the owner on 2026-11-01). The ADR records the decision; this file is the spec the
> slices E0 to E16 are built from. Where they differ the ADR wins: in particular owner answer 2 (a
> per-setup gate, section 9) replaces the review finding H1's "gate open-only" rule, and the ADR number
> is 0088 (the text below says 0087 where it was written before #968 took that number). The research
> files named below are not in the repo.

# Options setups: backend design (2026-10-25, revised after the architect review;
generalised to share and option setups alike, 2026-10-31)

Design only. Built on the edge / screener / feature / outcome machinery as it is on `main` at
33918346b. Inputs: the four research files in this scratchpad (catalogue = `research-options-setups.md`,
part 2 = `research-options-setups-2.md`, regimes = `research-options-regimes.md`, AI regime =
`research-ai-regime-2026-10.md`) and the review `design-options-backend-review.md`. Owner rule applied
throughout: generalise the existing piece, never add a near-duplicate. Section 0 is the one-screen
summary; the Entities section lists every entity, each serving share (stock) and option setups alike
(owner ask 2026-10-31); section 1 is the coverage inventory (every structural concept in the research
and the owner's generalisation, with where it lands).

Words used throughout (defined once):
- **Setup / edge**: the same thing; `edge` in code, "setup" on screen (ADR 0083).
- **Position**: what a setup holds in one trade, a list of legs. **Leg**: either shares (a signed
  quantity) or one option contract (right, strike, expiry, signed quantity). A share setup holds one
  share leg; an option setup has at least one option leg (a covered call adds a share leg).
  **Position template**: a named site list of legs (`long_shares`, `short_put`, ...). **Structure**
  stays the code word for a position with an option leg (`structure_pnl`, `engines/structures/`).
- **Delta**: the option's price sensitivity to the stock; for a short put, |delta| is roughly the
  market's own probability it finishes in the money. **DTE**: days to expiry. **Tenor**: the
  calendar-day target used to choose the expiry.
- **Collateral**: the cash the trader posts. **Cash-secured**: collateral = strike x 100 for a short
  put. **Reg-T margin**: the broker's standard (smaller) margin rule. **Return on collateral (RoC)**:
  P&L / collateral for one trade window, the lead number. **Notional**: entry close x shares, the
  capital of a share leg; a share setup's return on capital is its share return.
- **VRP**: variance risk premium (implied volatility above the realised volatility that follows).
- **Contango / backwardation**: the VIX curve rising / falling with maturity (VIX / VIX3M < 1 / >= 1).
- **CVaR 5%**: the mean of the worst 1-in-20 windows. **PSR**: probabilistic Sharpe ratio, the
  chance the true Sharpe is above zero after the observed skew and fat tails (the existing
  `deflated_sharpe(x, 1, 0)`). **DSR**: the same against the best of N tried variants. **PBO**:
  probability of backtest overfitting.
- **Rule**: a three-valued condition (TRUE / FALSE / UNKNOWN) over named catalogue fields, written in
  the one criteria language that selections and rule screens already use (`all` / `any` / `not` of
  `{field, op, value}`, `core/model/predicates.py`). Every part of a setup that decides something is a
  rule, or later a model's output read by a rule (owner, 2026-10-31; 2.13).
- **Feature level**: what one value describes: instrument, market, session / calendar, event or
  position (Entities, "Feature levels").
- **Gate**: a rule over market and calendar fields read at the decision session D that lets a setup
  enter or pauses it. It reuses the ADR 0049 **regime gate**'s decision (open / closed / unknown).
  **Slice**: a subset of an evaluation's windows (a year, a regime label, gate open).
- **Cohort series**: one value per trade (entry session S, name). **Book**: the daily
  marked-to-market return of all trades open on each day (the quant review's second series).
- **Price source**: where a trade's prices come from: `bars` (daily bars, `bars/1d`, share legs, open
  licence), `cboe` (our nightly chains, `chains/*`, from 2026-10-02, open licence) or `option_history`
  (the bought HOD files, 2002 to the purchase date, personal licence, ADR 0084).
- **Entry and exit rule**: when a trade enters (an offset from the decision session D, optionally
  after an entry condition fires) and what ends it (horizon, expiry, take profit, stop loss, DTE, or an
  exit condition over catalogue and position-level fields). **Position-level feature**: a fact that
  exists only while a trade is open (days held, profit as a share of credit), computed by the
  structure engine at each close (2.4a). **Trade**: one entered position from entry to exit, in the
  one common trade contract (2.5a).

---

## Changes after review

| Finding | Resolution |
|---|---|
| **H1 (superseded by owner answer 2 and ADR 0088 decision 7: a gate's fields count toward the setup's licence)** licence: expression features inherit the strictest input, so the regime label and gates would be personal | Accepted. Every state, verdict and gate boolean a trader sees is a **stored column of a market rollup declared open** as our own aggregate (the `regime@v3` / `regime_indicators@v1` precedent); raw VIX-family values stay personal. No gate or state reads an expression feature over personal inputs. Reasons name the condition, never quote a VIX value. Fitness test: every market field an edge gate names, and the label stored on picks, is open. Amends ADR 0069 decision 4 / 0047 (owner decision 2). `options_regime.toml` is dropped (2.1, 2.2). |
| **H2** near-duplicate of the ADR 0049 regime gate | Accepted. No `[gate]` table of its own, no `gate_state`, no `stood_aside`, no `GATE_UNKNOWN`, no `config/edges/conditions/`. `RegimeGate` and `[regime]` are generalised (any open market field: a label with its allowed set, or a bool); an edge names its gate and it resolves to that one predicate; a closed gate is `PAUSED` / pick status `paused`; an unknown gate is the existing "regime unknown". Owner stays `run-overlays`. The harness tags each decision session open / closed / unknown for the slices by calling the same predicate. Amends ADR 0049 (2.2). |
| **H3** `market_vol@v1` and `options_regime.toml` duplicate `market_macro`, the regime cards and `regime@v3` | Accepted in the first revision by extending `market_macro`, `regime_indicators`, `regime` and `market_breadth`; **superseded by N1** below: one leaf group `market_conditions@v1` reusing the existing helpers (`observations`, the card `Card` / `compare` verdict helpers), so no logic is written twice and nothing in the headline regime changes. `options_regime.toml` stays dropped. |
| **H4** option sleeves contradict ADR 0073 decision 1 | Accepted. The new ADR adds a base `delta_equivalent` for named option sleeves (an `option_pnl` outcome on 1-10 named instruments, paired per decision session), with variants and gates allowed, and says which parts of ADR 0073 decision 1 it lifts for that base only; `config/edges/named.py`'s `check_variants` and `check_raw_returns` change with it. Owner decision 3. E8 split into E8a (base and option value) and E8b (book and stress measures). |
| **H5** the history writer and the main ingest lock | Accepted. `option-history-outcomes` runs **one IngestRun per session batch**, taking and releasing the main lock per batch; the mechanics are corrected by **N4** below. Test: no batch holds the main lock across two publishes (2.5, E5). |
| **H6** Cboe and history rows for the same trade both stored and read | Accepted. One source per entry session by a fixed cutover: history strictly before `FIRST_CBOE_CHAIN_SESSION` (2026-10-02), Cboe from it. One constant in `data/outcomes/chain.py`, also used by the history-feature splice; the reader drops the other source; contract test. The overlap rows serve only the owner's one-off comparison (2.5). |
| **H7** frozen period vs PR #967, and the research has looked at 2019-2025 | Accepted. The design's 2019-01-02 frozen period is withdrawn. Paper-derived structures (A1, A3, B2, C2) use #967's post-publication basis (split = end of the paper's sample). A gate or threshold taken from this research (R-A, R-B, the A5 cut-offs) is judged only on data after the commit that fixes it (the Cboe forward record); its history slice is labelled in-sample. ADR text written on top of #967 after it merges (owner decision 4). |
| **ADR number** | The new ADR takes the next free number at push: **0088** (#968 holds 0087, 0086 is on main); `make numbering` right before the push. |
| **M1** a third contract selector | Accepted. One selector: `features/rollups/options/wing_search.py` generalised to choose a template's legs (features layer, pure); `put_wing`, `call_wing`, the engine and the Cboe writer call it. `option_paths.py`'s marking and hedging move into `engines/structures/` in E3a and are deleted from the task. |
| **M2** per-name conditions duplicate existing features and are null in history | Accepted. `conditions.toml` dropped. The report skip is a structure parameter applied by the selector against the selected expiry (`skip_report_in_life`, UNSELECTABLE reason `REPORT_IN_LIFE`), read from `earnings_expected@v1`, which exists in history. The ex-div and front-kink concepts reuse `ex_div_before_*` and `term_ratio_next_30`. |
| **M3** FOMC history dates: lookahead or never known ahead | Accepted. D2 types scheduled meetings only, each year with a declared `known_from` (the schedule's publication; made per-year and sourced by **N5** below), an ADR 0050 decision 3 exception written into the new ADR; fitness test excludes the unscheduled dates (2008-01-22, 2020-03-03, 2020-03-15). |
| **M4** setup state mines slices; Ideas by state needs an ADR 0083 amendment | Accepted. v1 state = the gate + the whole verdict only (ON / OFF / PAUSED / UNKNOWN); per-regime rows are display only; no change to the `edge_verdict` grain, no JUDGE_VERSION bump for it. Ideas stays as ADR 0083 says; the state is a chip (owner decision 5). |
| **M5** missing prerequisites in the engine chain | Accepted. E4 switches `hit.py::_chain_pnl` and `check_chain` to v2 columns (no edge declares `option_pnl`, so nothing changes in results); E6 then only adds measures. E2 budgets the `document.py` key lists (`KEYS`, `OUTCOME_KEYS`, `VARIANT_KEYS`: about 10 lines; 963 now, cap 1000); parsing stays in `config/edges/positions/`. |
| **M6** slices not file-disjoint | Accepted. E1 before E9 (`pick_edges.py`); E1, E6, E10 in sequence for `verdict/`; E6 before E7 (`measures.py`, `results.py`). The parallel start lists only disjoint slices. |
| **M7** splice in the wrong reader; missing #968 | Accepted. The splice is a `StoreReader` wrapper the harness passes to `screen_session`; the `RecordingReader` records the history root's partitions for leg reuse. Single-name history needs PR #968's survivorship-free listing history (dependency of F7, X2, X4, X5). X4's screens are price-based: the engine's quote filters handle option liquidity, so X4 does not need the history features. |
| **M8** new responsibilities where an owner exists | Accepted. `quant/edges/tails.py` under `quant-edge-statistics`; PSR is `deflated_sharpe(x, 1, 0)`; drawdown reuses `analytics/metrics.py`; the state rule is `services/read/evaluation/verdict/state.py`; no `config/edges/conditions/`. |
| **L1** wrong statuses (rows 1, 21, 92, 100, 106, 108, 113) and risk 5 | Accepted, rows corrected below; risk 5 restated (VIX9D, VIX6M, VVIX are also `release_lag_days = 1`). |
| **L2** missing amendments | Accepted: the list now has 0049, 0069 d4 / 0047, 0073, 0050 d3, 0065 on #967; 0083 only if owner decision 5 chooses Ideas by state. |
| **L3** E3 too large | Accepted: E3a (selector, marking, expiry and intrinsic, exit fallback, one- and two-leg) and E3b (management, assignment, early exercise, report skip). |
| **N1** (re-review, high) extending `market_macro` / `market_breadth` / `regime_indicators` bumps their versions, which cascades into `regime@v4` and supersedes `market.regime@v3.label` (14 files, the ADR 0049 default, every fingerprint, a 1971 backfill) | Accepted, option (b): one new **leaf** group `market_conditions@v1` that nothing in the headline regime reads, holding the VIX-family statistics (personal), the open verdict columns, `short_premium_allowed`, `earnings_season_share`, `y10_chg_63d` and the calendar distances; it reads the series and stored rows directly with the existing helpers. F0 first splits `features/rollups/market/` by kind (subfolder `market/edges/` with the moved `triggers.py` and the new module). `market_triggers@v2` stays a leaf bump for the post-spike trigger only. Regime-page cards for the new verdicts become optional (owner decision 2). (2.1, F0-F3, F9) |
| **N2** the edge gate inside screening erases the closed slice, is off by default, and its composition with `pause_in` is undefined | Accepted. The harness screens with the edge gate off and tags each decision session with the predicate; the picks task and the time-series harness apply the edge gate regardless of `[regime].enabled`; a pick needs both the screener's own `pause_in` and the edge gate open, and the slices refer to the edge gate only; the `gate` key is typed in `config/strategy/regime.py` (owner `run-overlays`), not in `config/edges/positions/`. (2.2, E2, E7) |
| **N3** the report skip makes every ETF UNSELECTABLE (`earnings_expected@v1` has no row for an ETF) | Accepted. Non-reporting types by `instrument.security_type` (ETF, index, closed-end fund) have no report and pass; unknown fails only for a reporting type (the `no_earnings` variant's rule); unit test on an ETF fixture. (2.4, E3b, risk 4) |
| **N4** the per-batch lock cannot "yield to a waiting nightly" (a plain flock; the nightly exits 3 and retries hourly) | Accepted. `option-history-outcomes` joins the `writes()` exemption in `cli/main.py`; each batch takes the main lock with `locks.held(..., wait=False)` for its publish and retries after a pause when it is held; it runs `recover_unpublished` under the lock before its first batch; it starts no batch inside the nightly window (`config/site/nightly.toml`). Worst case: a nightly that starts during a publish is delayed one hourly retry. (2.5, E5, section 10) |
| **N7** pending main-store writes while the lock is free (from the N4 fix) | Accepted. Each batch is computed with no IngestRun open; its IngestRun is opened, written and committed entirely under the main lock, so a nightly starting between publishes finds nothing to abort. §2.5, E5. |
| **N5** FOMC `known_from` of 1 December of the prior year is conservative only if every schedule was public by then | Accepted. `releases.toml` records per year the schedule's announcement date and source, and `known_from` is that date; a meeting moved after publication takes the move's announcement date. (2.9, D2) |
| **N6** the state for a viewer without the licence | Accepted. A setup whose verdict rests on personal evidence is not listed at all for such a viewer (ADR 0084 decision 1), never shown as UNKNOWN. (2.3) |
| **Simplicity** | Accepted: templates limited to those a filed edge uses; `results/edge_book` deferred (book statistics stored as `edge_eval` measures); `results/edge_pick_legs` replaced by a read-time computation, measured in E9 (a table only if over 0.2 s); composite R1-R12 label to P2; per-slice verdicts deferred; effective bets, event clustering, vol-managed sizing and the wheel book deferred; retiring `option_model_pnl` / `expires_otm` deferred until every edge is re-filed. |
| **G1** (owner, 2026-10-31: every entity serves share and option setups) structure template -> **position template** | Accepted. A leg is shares or an option. `long_shares` and `short_shares` are one share leg, and `covered_call` is a share leg plus a short call (the old `stock = 100` key becomes that leg). Templates move to `config/site/positions/templates.toml`, typed in `config/edges/positions/` (was `config/edges/options/`). An outcome names one by a new key `position`; `structure` stays the enum of `expires_otm`, `option_model_pnl` and v1 `option_pnl`, and setting both keys is refused. Existing stock edges need not change: `position_of` maps their `side` to a share template for the read model and the trade contract, with no document, version or fingerprint change. `pair_spread` and `portfolio_return` keep their own shapes (a `pair` template is P2). (2.4, Entities, E2) |
| **G2** outcome settings -> **entry and exit rule** | Accepted, one entity. Entry is `start_offset_sessions` (exists for both kinds). Exits: `horizon_sessions` (exists), plus a new `[outcome.exit]` (replacing `[outcome.manage]`) with `take_profit`, `stop_loss` and `exit_dte`, expiry implied by an option leg. All act at closes and the first wins, giving `exit_kind`. Share setups evaluate the horizon only in P1: `forward_returns@v2` has the window's dip but not its session, so an evaluated share stop needs a path grain (P2). ADR 0083's historical exit rule (stop = the drawdown 80% of the basis's winners never exceeded, fallback 2 x ATR(14), hold = `basis_horizon`) is **not built** on main: there is no `[exit_rule]` and no code, and the trader-site track orders it after Ideas and Test. It is a published reading of the evidence, never an evaluated exit (that would be circular). E12 builds it once, for both kinds, over the contract's `max_adverse` (shares: today's `edge_trades.max_drawdown`; options: the worst mark loss / collateral), and it is the same PR as the trader-site exit-rule slice. Option setups get no ATR fallback (owner decision 8). (2.4a, E12) |
| **G3** one trade outcome | Accepted as one contract over two grains. `forward_returns@v2` (ADR 0053) stays. It has one row per (instrument, S, horizon, benchmark) for every eligible name, which is what the base rate and the deciles need (about 8,000 names a session [I]); it has fixed-horizon exits, an open licence and a 1970s backfill, and every stored leg is keyed to it. `structure_pnl@v2` is one row per (underlying, S, `position_key`) for optionable names with a chain, with path exits, a licence and a price source per row, and about 25 leg columns; its base is the same position on every eligible optionable name. Merging them would put those columns null on millions of stock rows and invalidate every stored leg. What is already shared: `hit.py::apply_outcome` turns every kind into `RESULT_COLUMNS`, which the harness, the paper record and the ledger read, and `results/edge_trades` holds every kind. `TRADE_COLUMNS` generalises them (entry and exit session, exit kind, capital basis, return on capital per cost level, `max_adverse`, price source, licence), and one evidence path reads only that. Golden-edge equality guards it. (2.5a, E6a) |
| **G4** chain source -> **price source** | Accepted. `price_source` takes `bars`, `cboe` or `option_history`. It is a column of the contract and of `structure_pnl@v2` (was `chain_source`); the cutover constant still picks between the two option sources. (Words, 2.5, 2.5a) |
| **G5** example contract -> **example position** | Accepted. One loader, with two shapes. Options: legs, net credit and collateral (plus Greeks and flags). Shares: the entry close, the stop price from the historical exit rule (or the labelled ATR fallback) and the exit date (the hold in exchange sessions). It lives in `services/read/evaluation/positions/` (responsibility `pick-positions`), since the parent folder is at its 10-module cap and the loader cannot sit "beside `pick_edges.py`". (2.8, E9, E12) |
| **G6** evidence for both | Accepted. CVaR with its count, the block bootstrap, PSR, the book drawdown, episode rows and cost levels are computed for every setup over `return_on_capital`. Only the denominator differs: notional for shares, collateral for options. Share cost levels stay `[edge_costs]` (ADR 0064). Stock verdicts are **not** re-judged. A verdict profile per setup chooses the criteria: `return` (today's criteria, the default for every return kind) or `tails` (adds PSR, the CVaR ratio and the bootstrap t; the default for `option_pnl`). A share setup moves to `tails` only by a new version, which is a new trial (owner decision 7). We rejected a `JUDGE_VERSION` bump, which would re-judge every stored verdict at once. Because `settings_hash` covers the typed `VerdictSettings`, the change shifts every fingerprint once. E6b therefore re-stores the headlines, and its acceptance check is that every label and one-line result is unchanged. (2.6, E6b, risk 16) |
| **G7** `market_options@v1` -> `market_conditions@v1` | Accepted. Nothing in it is options-specific, and share setups gate and slice on it too (`rate_shock_on`, `post_spike_recovery_on`, `vix_high_on`). The module is `market/edges/conditions.py`; P2 is `market_conditions@v2.conditions_label`; the folder note reads "market facts setups read: the triggers of ADR 0075 and the market conditions setups gate on". Every reference is renamed, earlier rows of this table included. (2.1, F1, F2, F9) |
| **G8** screeners as explicit entities | Accepted, with no new storage or code. A **Screener** is a rule-screen preset (`config/site/presets/screeners/<id>/v<n>.toml`, immutable, versioned by file), a user screener (`config/users/<id>/`) or a Python screener. In a setup it is an implementation (one is the basis), a baseline or a decoy (`@standard`), and it has its own ADR 0049 `pause_in`. A **Screener run** is `results/screen_runs`, `rule_screen`, `rule_screen_values` and `screen_picks`. Pick rule: per (setup, screener), `picks.long_picks` takes the qualified names (the screener's PAUSED excluded), inside the universe, the first `top_k`, then the setup gate. One `edge_picks` row per screener, never merged; Ideas shows the basis screener only (ADR 0083). Named-symbol setups skip screeners (E9). (2.12, Entities) |
| **G-H1** (review of G1-G8, high) an option setup entering at D's close (`start_offset_sessions = 0`) is lookahead, and `document.py:738-741` already refuses it | Accepted. The offset is >= 1 for both kinds. Legs are selected and filled from S's chain, as v1 `option_pnl` does, and the gate is read at D. The 2.4 sample, the 2.4a row and the Entities row are corrected, and the false "next close by default" is removed: the parser default 0 is refused, so every edge sets the offset. E2 test: an option outcome with offset 0 is refused. (2.4, 2.4a, Entities, E2) |
| **G-M1** `results/edge_picks` has no `paused` status (`night.py:39`), and its key needs a screener (`edge_schemas.py:335`) | Accepted. E9 adds a stored status `gate_closed` for a closed setup gate, which `pick_edges.py` maps explicitly to its `paused` read code, kept apart from the screener's per-name PAUSED. It also adds a declared sentinel screener `@named` for named-symbol rows. The schema comment and the ADR 0081 amendment say so, and the three "nothing new" lines are corrected. (2.2, 2.3, 2.12, Entities, §5, E9) |
| **G-M2** the verdict profile of the 7 site edges on `expires_otm` / `option_model_pnl` was undefined | Accepted. `return` is the default for every kind except `option_pnl`. E6b adds a fitness test over the site documents, and its label-equality check covers these 7 edges (`vrp_short_premium`, c12, c13, c14, c16, c17, c18). (2.6, E6b) |
| **G-M3** E12 rests on `basis_screener` / `basis_horizon`, which are not stored yet, and it tied the share exit rule to the option engine | Accepted. E12 is split. E12a (shares) reads `edge_trades.max_drawdown` and needs only E2 and the trader-site track's basis columns ("T-basis", ADR 0083 decision 2, a `JUDGE_VERSION` bump). E12b (options) runs after E3b, E6a and E9. T-basis and E6b each re-store the headlines once in their own deploy, never on the same night. The Entities Verdict row marks the basis columns as not stored yet. (2.4a, Entities, §7, map) |
| **G-M4** E12 and E6b shared `config/edges/verdict.py` and `verdict.toml`; `config/edges/` is at its cap | Accepted. `ExitRuleSettings` moves to `config/edges/positions/exit_rule.py`. E2 makes the one-line `[exit_rule]` skip in `verdict.py`, so E12a and E6b share no Python file. Both append to `verdict.toml`: if both are open, E12a merges first and E6b runs `scripts/merge_main.sh`. (2.4a, E2, map) |
| **G-M5** the new drawdown, worst-month, episode and cost measures duplicated `edge-evidence-read` | Accepted. The harness stores only the judge's inputs (CVaR with its count, worst window, bootstrap, PSR, `excess_roc`). Cost rows stay the existing `slice_kind` rows, with the option levels added. Drawdown, episodes (plus the Reg-T flag), the monthly map and cost sensitivity stay in `services/read/edge_evidence/`, which E11 extends to read `return_on_capital`. Only the named sleeve's fixed-slot book and Cboe tracking stay new (E8b). (2.6, E6b, E8b, E11) |
| **G-M6** the v2 row key had three names and omitted the exit rule | Accepted. The one name is `position_key`. It is canonical: template, leg overrides, selection parameters, entry offset, `[outcome.exit]` and the hold cap. E4 contract test: two grid points that differ only in `take_profit` write two rows. (2.5, 2.5a, Entities) |
| **G-M7** decision 8 framed wrong: option setups already have evaluated exits | Accepted. Option (d) is added and recommended: an option setup publishes its own declared exits (stop loss, take profit, DTE); the percentile stop applies only when it declares no stop, and is UNKNOWN below `min_winners`. (2.4a, 2.8, §5, §9, E12b) |
| **Lows** (review of G1-G8) | All applied:<br>- E12a's acceptance has ADR 0083's bounds (`range_to <= S`, `exit_session <= S`) and a past-session test.<br>- Share rows from before E6a read the `max_drawdown` alias.<br>- A short `max_adverse` and a short stop price stay null in P1: picks are long only, and a short column would bump `LEG_VERSION`.<br>- The share `capital` is null in P1.<br>- E2 names `config/edges/identity.py` `identity_dict`.<br>- E6a names `forward/settle.py:133`.<br>- 2.8 labels the served session's close as the reference close.<br>- §4 calls the Ideas rule decided, not built.<br>- Entities gains Universe and Episode.<br>- E6b's headline re-store runs in its deploy. |
| **R1-R3** (final review) leftovers | R1: §2.6 drops `stress.py`. The Entities row, the §3 sketch and ADR 0088 now match G-M5: drawdown and episodes are read by `edge_evidence`, and only a named option sleeve adds a fixed-slot book and Cboe tracking. R2: E6b lists `config/edges/verdict.py` for its new `VerdictSettings` fields. E2's `[exit_rule]` skip sits in the loader's known-sections list, never in the hashed class. R3: merge order is E1 -> T-basis -> E6b and T-basis -> E12a -> E9; a later PR stays `no-automerge` until its predecessor lands. (2.6, Entities, §3, §5, E2, E6b, map) |
| **G9** (owner, 2026-10-31: every part of a setup is the output of a rule, later a model, over the 700+ catalogue features at every level) **Rule** entity | Accepted, with no second language. The language is the one selections and rule screens already share: `Rule` / `Group` (`all` / `any` / `not` of `{field, op, value}`) in `core/model/predicates.py` (owner `three-valued-predicate`), parsed by `config/strategy/schema.py::parse_group`, evaluated by `evaluate_group` (Kleene: missing is UNKNOWN). Screeners keep their scored wrapper (`Criterion` with HARD / SOFT / SCORE, ADR 0071 groups by reference, `screen-spec`), whose criteria are the same `Rule`; a universe stays a `Selection` (`where` = a `Group`); expression features stay the way to name a formula. The one point-in-time check is `FieldCatalog.check` (`config/strategy/catalog.py`), extended with a **use site** (`gate`, `entry`, `case`, `exit`) that fixes the levels a rule may name, the session it reads and when it may act, and the licence it allows. Used by the screener (exists), universe (exists), gate (G10), entry condition, exit condition and position parameters (G11). New slice E2r. (2.13, Entities, E2r) |
| **G10** gate = a rule over market and calendar fields | Accepted. `gate` is a `Group` over `market.*` fields only (the calendar facts are columns of the market row: `sessions_to_fomc`, `in_opex_week`, `weekday`), read at D, open licence only (H1, now checked by the use site). TRUE = open, FALSE = closed, UNKNOWN = unknown (fail closed), the ADR 0049 `RegimeGate` decision unchanged, so the closed slice stays the inverse decoy. The `{field, require}` form is dropped; `pause_in` (the screener's own, `[regime.screeners]`) stays and is read as the rule `field not_in pause_in`. Example: VIX curve upward AND no FOMC within 2 sessions. (2.2, E7) |
| **G11** entry and exit rule as defaults plus conditions; position parameters by rule | Accepted. The settings stay as defaults. Added: `[outcome.entry] when` + `within_sessions` (enter after the first close at which the rule is TRUE; instrument and market fields; both kinds in P1, a harness mapping over the existing per-S rows); `[outcome.exit] when` (instrument, market and position-level fields; option setups P1, share setups P2 with the path grain). `take_profit`, `stop_loss` and `exit_dte` compile to position-level rules with their own `exit_kind`, so the engine evaluates one ordered list. A **case value** (`{ cases = [{ when, value }], default }`) may set `position` (same-kind templates only), `strike_delta`, `tenor_days`, `expiry_cycle` and the exit settings, read at D; an UNKNOWN case makes the name UNSELECTABLE (`CASE_UNKNOWN`), never the default. Rows stay keyed by the resolved concrete point. (2.4, 2.4a, E2r, E3b, E13) |
| **G12** position-level features | Accepted. One typed list `POSITION_FIELDS` in `config/edges/positions/fields.py` (days held, profit as a share of credit, position delta, distance to the nearest short strike, move since entry, days to expiry, mark loss as a share of collateral), named `position.<name>` (a new field head in `core/model/fields.py`), allowed only at the `exit` use site. Computed by `engines/structures/` at each close from that close's chain and bar and the entry facts; never stored as catalogue features; Guide entries per field. (2.4a, Entities, E2r, E3b) |
| **G13** model (P2 / P3) | Accepted as an extension of what exists. ED7's `edge-scorer-fit` already fits a scorer on an edge's `[scorer]` features and writes it as the expression feature `edge_score_<edge>` with `fitted_through`, refusing `no_ml` tables (`no-ml-tables`). Its output is a feature, so any rule may read it (rank, entry, case, exit) with no new seam. New rules: a setup whose rule reads a fitted score is judged only on sessions after `fitted_through` plus the horizon (earlier sessions are an in-sample slice); a score inherits its inputs' strictest licence; models propose and rank, never judge (ADR 0053). Other model kinds (a bucket for position choice, a market-level score) are P3. Owner decision 10 (P2). (2.14, E14) |
| **G9-M1** (review of G9-G13) `FieldCatalog` holds no market fields and no licences (`services/configs.py:32-38` builds it from instrument groups only, ADR 0047; `catalog.py:59-80` maps field to type) | Accepted. "One check" is built, not only extended. E2r builds the catalogue per use site: the default site keeps refusing `market.*`; `gate`, `entry`, `case` and `exit` add the market groups (types from `GROUPS` with `entity == "market"`). The catalogue gains a licence map from `Feature.licence`, expression features inheriting the strictest input. The callers merge the session's market row into each name's row (the heads differ, so no key collides). ADR 0047 is amended: market fields may be named in per-name rules at these sites (its line 58 still holds for expressions). Row 125 corrected. (2.13, E2r, §5) |
| **G9-M2** fail open: `is_null` / `not_null` pass on missing data, `ne` / `not_in` pass on an unknown label, and `pause_in` as `not_in` drops `RegimeGate.known` (`gate.py:41`) | Accepted; gates and exits stay fail closed. At the `gate`, `entry`, `case` and `exit` sites: `is_null` / `not_null` are refused; every string field named needs a declared domain (the regime labels, an expression feature's categories), and a value outside it is read as missing before evaluation, so `ne` / `not_in` on an unknown label is UNKNOWN; a string field without a domain is refused. This is `RegimeGate.known` generalised, so the ADR 0049 pause keeps "regime unknown". E7 test: the label `"FOO"` is unknown for the ADR 0049 pause and for an edge gate. (2.2, 2.13, E2r, E7) |
| **G9-M3** an entry condition moves S off the decision sessions, but the option writers store only decision sessions (§2.5, risk 13) | Accepted, writers follow entry sessions. For an edge with `[outcome.entry]`, E4 (Cboe) and E5 (history) write every S in [D + offset, D + `within_sessions` - 1 + offset] for the screened names; rows x `within_sessions` in §10. Until they do, E13 refuses an entry condition on an `option_pnl` outcome (test). Share setups need nothing: `forward_returns@v2` has every S. (2.4a, E4, E5, E13, §10) |
| **G9-M4** a field never stored over the evaluation range (chain features before F7, `ibkr_iv` history) makes an exit rule UNKNOWN at every close, so history trades silently run under a different rule | Accepted. (1) The harness refuses, at run start, a rule naming a field whose group has no rows over the evaluation range (the run fails with the field and range). (2) A trade whose exit rule was UNKNOWN on more than `[quality] exit_unknown_share` of its closes is UNMEASURED: counted, excluded from the evidence, never a normal exit. A run whose UNMEASURED share passes `[quality] unmeasured_share` gets no verdict (UNKNOWN). Tests in E4, E5 and E13. The threshold placement is superseded by R-1. (2.4a, 2.13, E4, E5, E13, risk 21) |
| **Lows** (review of G9-G13) | All applied:<br>- A `structure_pnl@v2` row's `licence` is the strictest of its price source and its exit rule's fields (2.5, E4 test).<br>- E5 resized: it reads the exit rule's catalogue fields per close and meets G9-M4.<br>- Each slice adds its own `three-valued-predicate` `allowed` entry (E2r only `engines/selection/cases.py`; E3b, E7 and E13 theirs). |
| **G14** (owner, 2026-10-31) every screener is a rule | Accepted. **Rule is the one entity.** A **screener** is a published rule at instrument scope with a rank (sort, tie-break, top N) and an identity (name, versions, Guide entry, stored runs, its own ADR 0049 pause). Setup-internal rules (universe, gate, entry, exit, position parameters) are the same language without the identity; one can be **promoted** to a screener (a preset version file), never re-written. Model outputs enter only as features that rules read. Repo: 92 site screener presets, all `impl = "rules"`. The one Python screener, `strategies/screeners/short_premium_liquidity.py`, is named by no screener preset and no edge, but it is a site config of kind `screener` (`presets/strategies/short_premium_liquidity.toml`, so the nightly runs it), the `--config` default of `algotrade-ingest screen`, and its `legacy_liquidity_csv` export (`services/screening/exports.py`) reads its run. New slice S5 ports it to a feature group plus a rule preset with the same id, keeping the export and the CLI default, then deletes the Python impl. (Entities, 2.12, 2.13, §4, S5) |
| **G15** (owner, 2026-10-31) feature levels as a declared extension point | Accepted. Each level is one entry of `LEVELS` (`config/strategy/levels.py`): key, provider (stored feature-group entity, reusing `GROUP_TABLE_PREFIXES`, or a computed producer with a typed field list), point-in-time rule, join path (`self`, `broadcast`, `through <key field>` as known at S), scopes and licence. Today's levels are its rows. The language, evaluator, use-site check, fail-closed rules and licence check read `LEVELS` and never change when a level is added (fixture-level test). Worked example: portfolio (P2, E15), the setup's own paper book and tonight's list, never real holdings (ADR 0083; real holdings need an ADR). The declaration is part of E2r. (Entities, 2.13, 2.15, §4, §5, inventory 133-134, E2r, E15) |
| **R-1** (re-check of G9 fixes) the UNMEASURED thresholds sat in ingestion's `[quality]` at write time and duplicated `excluded_coverage` | Accepted. Writers store `exit_unknown_closes` per row; the harness classes a trade UNMEASURED by `verdict.toml [exit_rules] exit_unknown_share`, typed outside `VerdictSettings`; run coverage reuses `excluded_coverage`; `unmeasured_share` dropped. Lows: domains only for `ne` / `not_in`; E15 leg reuse keyed on book state, portfolio gate personal on history; E2r split into E2r-a / E2r-b; import-linter check on `LEVELS` providers. (2.4a, 2.13, E2r, E4, E5, E15) |
| **G16** (entity fit EF-G1, EF-G10; owner approved 2026-10-31) **Book** as one entity | Accepted. A book is a weighted set of open positions valued once a session: `{weighting, slots or weights, cash, overlay}` on the existing `cross_section/portfolio/` code (ADR 0074: equal / inverse_vol / score weights, `vol_target`, `CASH`, `canary`, `hold_rank`; owner `edge-evaluation`). E8b's fixed-slot option sleeve becomes `weighting = "slots"` of that code; the planned `services/evaluation/evidence/book.py` is dropped, so there is one owner. A book's per-session return (already in `results/edge_series`) enters the evidence path as the contract's `return_on_capital` with `capital_basis = "book"`, so CVaR, the bootstrap and PSR cover the 14 allocation edges. Weights exist only on a book, never on a template or a case value; nothing published is sized (ADR 0083). `results/edge_book` stays deferred. (Entities, 2.5a, 2.6, E6a, E8b) |
| **G17** (EF-G2) **Base** as an entity | Accepted, text plus E8a. The base is one of `BASES` (`universe`, `event`, `out_of_window`, `benchmark` with `mix:`, none, and the new `delta_equivalent`), per setup or variant; the evaluation run pairs the setup with it. (Entities, E8a) |
| **G18** (EF-G3) **Schedule** as an entity; calendar columns | Accepted. Schedule providers: `every_session`, `month_end`, `calendar:` windows, `on_market:` triggers, `on_event:` classes. The level text is corrected: rules read events only through features; **the schedule alone reads event rows** (anchor, `ANNOUNCED_AHEAD`, `picks = event`, `known_from <= D`). Calendar choices become rules: `market_conditions@v1` gains `last_before_weekend` and `fomc_cycle_week` beside `weekday`, `in_opex_week` and `sessions_to_fomc`, so a weekday or FOMC-week choice is a gate or entry rule on an `every_session` setup and its variants are rule variants (no `schedule` variant key; the closed slice is the Mon-Thu base). Market-event windows with negative offsets (`on_market:fomc`) stay P3. (Entities, 2.1, 2.15, F1) |
| **G19** (EF-G4) **position baseline** | Accepted. `baselines` may name `position:<template id>`: the setup's own picks valued with another template, stored as a baseline row like a decoy (A3 against the stock alone). It is a paired base, not a trial. New slice E16. (Entities, 2.7, E2, E16) |
| **G20** (EF-G5) picks beyond one long list | Accepted for the model and the table. `results/edge_picks` gains `pick_sides` beside `pick_ids` and, for a book, `pick_weights`; the pick rule ranks a short by its own score ascending (`long_picks` with an orientation); the example position gains the `short_shares` shape (with "borrow assumed", EF-G21). Today 27 edges (short, long-short, book) are `unjudged`. Whether Ideas shows a short pick or a book's weights is owner decision 11 (ADR 0083: "publishes setups", no size shown; weights are never shown as a size). (Entities, 2.8, 2.12, E9, §9) |
| **G21** (EF-G12) earnings report time of day | Accepted, P1 for C2, as corrected by G16-M1: `events/earnings` already stores `time` (`pre_market` / `after_hours` / `unknown` / `intraday`), so no new column and no D7. F10 adds the opt-in class `on_event:earnings_reaction` (the report's session for `pre_market`, the next for `after_hours`), using the time known at D; unknown is skipped and counted; the existing `on_event:earnings*` classes are unchanged. Event-ended exits (merger arb) stay P3 as `exit` rules over event features. (Entities, 2.9, F10) |
| **G22** (EF-G19, EF-G20, EF-G11) price source `model`; shapes without capital; Ensemble; canary | Accepted, mechanical. `price_source` gains `model` (the 6 `option_model_pnl` edges, `MODEL_BASIS`). `expires_otm` and `hit_target` map to `capital_basis = "none"` with `return_on_capital` null: judged on hit rate as today, tail measures null. The Setup row names `[ensemble]` (10 edges: several implementations combined into one trial). `canary` is documented as a Book overlay; new cross-instrument references are market columns, never a "field of instrument X" rule syntax. (Entities, 2.5a, E6a) |
| **G23** (EF-G6..G11, G13..G15, G17; EF-G16, EF-G21) deferred extensions and out of scope | Listed in §2.16 with the smallest generalisation of each existing entity (template `hedge` key, `debit` / `worst_case` collateral, a share leg naming its instrument for pairs, path-aware share exits, book-level sizing, chained positions, a `select` site, `fill = open`, link levels via precomputed features first). Out of scope: futures traded as futures (via ETFs / ETPs and market features only); borrow availability (no source; `borrow_bps_annual` kept, "borrow assumed" stated). (2.16) |
| **G24** (stores §3e 1, 3, 4, 7, 8) store rules | Accepted. (1) **One rule for personal derived data**, written into the ADR 0084 amendment: a derived table whose licence varies by row lives in the main store with a `licence` column (`structure_pnl@v2`); a catalogue group whose licence is per feature and cannot vary by row stays in the history root, reached only by the harness's splice; test (as corrected by G16-M2, no date rule): a trial's licence is the strictest of the rows and partitions it read, so a share trial over 2015 stays open and an option trial over 2015 is personal. (3) **One publisher** for `structure_pnl@v2`: `frame_and_publish` in `tasks/derived/option_outcomes.py`; the history task computes frames and calls it (one `tables.toml` owner). (4) `results/edge_trades` already has `licence` (and `value_licence`, `score_licence`, `adv_licence`), which the contract reuses; `edge_picks` carries the evidence licence (E1). (7) `position_key` is built from the **resolved legs** (right, qty, strike rule, delta, tenor, collateral, selection parameters, exits), never the template id, so editing `templates.toml` cannot change a stored row's meaning. (8) Missing columns (G16-M1: `events/earnings.time` exists, so not this one; `edge_trades.licence` exists too): `edge_picks.pick_sides` / `pick_weights`, price source `model`, a `tables.toml` entry per new market group. (2.5, 2.5a, §5, Data stores, E1, E4, E5, E6a) |
| **G25** (stores §3e 5, 6, 9; Part 3) data prerequisites and growth | Accepted. 2002-2009 prerequisites are data slices before E5: `bars/1d` and `rates/treasury` to 2002 come from the Tiingo backfill session already running (referenced, not duplicated; D1 folds into it), `events/dividend` from #974 (check it ran on this store), then `forward_returns@v2` and `residual_returns@v1` for 2002-2009 (D8, `run outcomes`, about 8.5 GB [I]). Cboe chain growth, 97 MB a session [M] (about 24 GB a year [I], 9x HOD's file), is checked now (D9: columns, sort, `cluster_by`) before a year accrues. Small files are watched in E5. New "Data stores" section. |
| **G16-M1..M3** (review of G16-G25) | Accepted. **M1:** `events/earnings` already stores `time` (`pre_market` / `after_hours` / `unknown` / `intraday`), so D7 is dropped; F10 is an opt-in class `on_event:earnings_reaction` using the time on the calendar row known at D (never the 8-K's `intraday` time), and the 10 `on_event:earnings*` edges are unchanged (golden test). **M2:** no date rule in the ADR 0084 amendment: a trial's licence is the strictest of the rows and partitions it read; a share trial over 2015 stays open, an option trial over 2015 is personal. **M3:** decision 11 (a) amends ADR 0083 d3 and 0081 d4 ("long picks only"), stated in §5 and §9; a short pick's stop is UNKNOWN in P1 and a book's exit is its next rebalance. **Lows:** `edge_trades` already has `licence` (reused, text corrected); `frame_and_publish` is new, extracted in E4; bills to 2002 come from the Treasury source (D1), not the Tiingo `bars-history` session; `[ensemble]` is on 10 edges; book picks replay from the paper record (E9); the book series feeds the evidence only, never `edge_trades`. (2.5, 2.5a, 2.9, §5, §9, D1, D7, D8, E4, E6a, E9, F10) |

---

## 0. Summary

**One vocabulary for share and option setups (owner, 2026-10-31).** Every entity serves both kinds
(Entities section). An option setup differs from a share setup in four things only: its position
template has an option leg, its price source is a chain rather than bars, its trades come from the
option outcome grain, and its return is measured on collateral rather than notional. Screeners are
explicit entities (2.12).

**Every part of a setup is a rule over features (owner, 2026-10-31; G9-G13).** The screener, the
universe, the gate, the entry and exit conditions and the position's parameters are each a rule in
the one criteria language selections and rule screens already share (`core/model/predicates.py`,
three-valued, one evaluator), over the catalogue's fields at every level (instrument, market,
session / calendar, event through its features) plus position-level fields for exits. One check
(`FieldCatalog.check` with a use site) fixes, per use, which levels a rule may name, which session it
reads and when it may act. Later a model's output (ED7's fitted scorer, already an expression feature)
is just another field a rule reads; models rank, never judge (2.13, 2.14). Rule is the one entity:
a screener is a published rule with a rank and an identity, and the one Python screener is ported (S5,
G14). Feature levels are one declaration (`LEVELS`: key, provider, point in time, join path, scopes,
licence), so a new level such as the setup's own portfolio (P2, E15; never real holdings) adds a
provider, not a check (2.15, G15). At the gate, entry, case and exit sites missing data never passes
(G9-M2, G9-M4).

**Entity fit and stores (owner-approved, 2026-10-31; G16-G25).** The model now names every piece the
80 edges on main already use: the **Book** (one owner, `cross_section/portfolio/`; the option ladder
is its `slots` weighting), the **Base**, the **Schedule** (the one reader of event rows), position
**baselines** (`position:<template>`), picks with sides and weights (so 27 `unjudged` edges can
reach Ideas, owner decision 11), price source `model`, `capital_basis = none` and the Ensemble. C2
needs an opt-in reaction-session anchor over the stored report time (F10). Store rules: one rule for personal derived data (ADR 0084
amendment), one publisher for `structure_pnl@v2`, a `licence` column on `edge_trades`, `position_key`
from resolved legs. The 2002-2009 bars come from the running Tiingo backfill and bills from the
Treasury source (D1); forward returns follow (D8); Cboe chain growth is checked now (D9). Every entity's store: "Data stores".

**What exists and carries most of the load.** The edge document with variants, decoys and the trial
log; the screeners (rule-screen presets and user screeners, versioned) and their stored runs
(`results/screen_runs`, `rule_screen`, `rule_screen_values`, `screen_picks`); two harnesses
(cross-section `services/evaluation/cross_section/`, time-series `services/evaluation/time_series/`,
ADR 0073). `hit.py::apply_outcome` already turns every outcome kind into one result shape, and the
ledger `results/edge_trades` already holds every kind. Also on main: the stock outcome grain
`outcomes/instrument/forward_returns@v2`, read with `start_offset_sessions` and `horizon_sessions`; the
share cost levels `[edge_costs]`; the chain-P&L grain `outcomes/option/structure_pnl@v1` (empty) with
its nightly writer; the ADR 0049 regime gate (`engines/screening/gate.py`, PAUSED, pick status
`paused`); regime slices on `market.regime@v3.label`; the regime groups `market_macro@v3`,
`regime_indicators@v1` (cards, open verdicts) and `regime@v3` (open label); the trigger
`on_market:vix_spike`; the VIX family and Cboe strategy indexes as macro series; bills from
`rates/treasury`; `episodes.toml`; stored picks and verdicts; the contract selector `wing_search.py`;
the licence gate (ADR 0069) and the history quarantine (ADR 0084). **Decided but not built:** ADR
0083's historical exit rule (no `[exit_rule]` setting, no code).

**New or generalised pieces (P1):**
1. **Position templates** `config/site/positions/templates.toml`. A leg is shares or an option:
   `long_shares` and `short_shares` (one share leg), `short_put`, `put_spread`, `covered_call` (share
   leg plus short call), `short_straddle`, `iron_fly`. Typed in `config/edges/positions/`, with
   `chain.py` moved there. Existing stock edges are unchanged: their `side` maps to a share template
   (G1).
2. **The entry and exit rule**, one entity: the existing `start_offset_sessions` and
   `horizon_sessions` plus `[outcome.exit]` (take profit, stop loss, DTE; expiry implied), evaluated
   at closes, as defaults; plus an optional entry condition (`[outcome.entry] when`, within a wait of
   `within_sessions`) and exit condition (`[outcome.exit] when`, over catalogue and **position-level
   features**); position parameters (template, strike delta, tenor, exits) may be **case values**
   chosen by a rule at D. Also the **historical exit rule** of ADR 0083 (stop, hold), built once for
   both kinds over the trade contract (G2, G11, G12).
3. **One selector** (`wing_search.py` generalised) and **one structure engine**
   (`engines/structures/`: marking, exits, assignment, early exercise, exit fallback), taking over
   `option_paths.py`'s marking. It marks option legs and a share leg held with them.
4. **`outcomes/option/structure_pnl@v2`** (supersedes the empty v1) beside the unchanged
   `forward_returns@v2`: one row per trade, one price source per entry session by a fixed cutover,
   `licence` per row (G3, G4).
5. **The common trade contract** that both grains satisfy: entry and exit session, exit kind,
   capital basis, return on capital per cost level, worst adverse move, price source, licence. **One
   evidence path** reads it: `services/evaluation/evidence/` and `quant/edges/tails.py` (CVaR with
   n-in-tail, stationary block bootstrap) under `quant-edge-statistics`. The measures are computed for
   every setup. A **verdict profile** (`return`: today's criteria, the default for share setups;
   `tails`: for option setups, and for a share setup only through a new version) leaves every stored
   stock verdict as it is (G6).
6. **The setup gate**: a rule over open market and calendar fields read at D (e.g. VIX curve upward
   AND no FOMC within 2 sessions), decided open / closed / unknown by the ADR 0049 `RegimeGate`
   decision, applied by the picks task and both harnesses regardless of `[regime].enabled`. The
   harness screens ungated and reports open / closed / unknown slices (the closed slice is the
   inverse decoy) (G10).
7. **One leaf market group `market_conditions@v1`** (VIX-family statistics personal; open verdict
   columns, `short_premium_allowed`, `rate_shock_on`, `earnings_season_share`, calendar distances).
   Share and option setups read it alike. It comes after splitting `features/rollups/market/` by
   kind; `market_triggers@v2` adds `post_spike_contango`. The headline `regime@v3` and its inputs are
   untouched (G7).
8. **A `delta_equivalent` base** for named option sleeves on the time-series harness (amends ADR
   0073).
9. **Rules (G9):** no new language or evaluator; `FieldCatalog.check` gains use sites (`gate`,
   `entry`, `case`, `exit`), the field head `position.` and the typed list `POSITION_FIELDS`;
   `engines/selection/cases.py` resolves case values (E2r, E13).
10. **Computed on read, per pick:** the **example position** (options: contracts, credit, collateral;
   shares: entry close, stop price, exit date) and the historical exit rule in
   `services/read/evaluation/positions/`; the **setup state** v1 (ON / OFF / PAUSED / UNKNOWN) in
   `verdict/state.py`; named-symbol picks with no screener (G5, G8).

**P2:** history chain features (a `StoreReader` splice; needs PR #968), the composite R1-R12 label,
per-slice decisions, the book table, effective bets, the wheel, vol-managed sizing, an evaluated stop
and exit condition for share setups (needs a path-aware share grain), a `pair` template, P3
templates; rules reading a fitted score (E14, decision 10). **P3:** other model kinds (a bucket for
position choice, a market-level score).

**ADRs:** new **0088** (next free at push) and amendments of 0049, 0069 d4 / 0047, 0073, 0081,
0064, 0075, 0084, 0050 d3, 0083 decision 3 (the historical exit rule for option setups), 0065 (on top
of #967), 0053 (rules and models), plus the licence-gate PR that ADR 0084 decision 1 requires (amends 0064 / 0083).

**First slices (parallel, file-disjoint):** E0 (ADRs), then E1 (licence gate), E2 (templates and
spec), D1 (bills to 2002), D2 (FOMC dates), D3 (episodes), F0 (split `market/` by kind), F4
(`earnings_reaction@v2`). F1 (`market_conditions@v1`) and F3 (`market_triggers@v2`) start after F0.
E2r (rule use sites, position fields, case values) follows E2, runs beside E3a (file-disjoint) and
precedes E3b, E7 and E13 (the rule-driven entry and parameters in the harness).
Critical path: E0 -> E2 -> E3a (with E2r) -> E3b -> E4 -> E6a -> E6b -> E7 -> E8a / E8b -> E9 -> X1. E1 -> E5
(after D1, D5) joins before X1's history run. The exit rule is split: E12a (shares) needs only E2
and the trader-site track's basis columns; E12b (options) comes after E9. E9 first adds the
`gate_closed` status and the `@named` sentinel to `results/edge_picks`.

**Owner decisions (section 9):**
- history evidence owner-only;
- the open licence of stored regime verdicts;
- lifting ADR 0073's limits for named option sleeves;
- the basis rule on #967, with a forward holdout for research-chosen gates;
- Ideas unchanged (state as a chip);
- A1 published gated by R-A;
- share setups move to the `tails` profile only by a new version (7, new);
- an option setup publishes its own declared exits, with the percentile stop only when it declares
  none (8);
- rules may read personal-licence fields outside the gate, making that setup's evidence personal (9,
  new);
- (P2) publishing setups whose rules read a fitted score, judged after `fitted_through` (10, new);
- what Ideas shows for short, long-short and book picks (11, new).

---

## Entities

Every entity of the design in four layers, each serving share and option setups alike. Status:
**exists** (on main, unchanged), **extended** (on main, changed here), **new**. Examples are
illustrative: the share setup is a screener setup (screener `breakout`, `long_shares`, 20-session
hold); the option setup is X1 `index_put_write` (named SPY, `short_put` at 20 delta, 30 days).

### Feature levels (what a rule may name; a declared extension point, G9, G15)

Every level is one row of the declaration `LEVELS` (2.15): a key (what a row is about), a provider,
a point-in-time rule, a join path into the scope a rule evaluates in, the rule scopes allowed to read
it, and its licence. The rule language, the evaluator and the point-in-time and licence checks never
change when a level is added: a new level is a new provider and, for a new key, a join path.

| Level | Key (one row per) | Field head | Provider | Point-in-time rule | Join path into an instrument-scope rule | Scopes that may read it | Licence |
|---|---|---|---|---|---|---|---|
| Instrument | (instrument, session) | `rollup.<group>@v<n>.<col>`, `instrument.<col>`, `feature.<name>` (incl. a fitted score, 2.14) | stored: `rollups/instrument/*` groups, `instruments/reference` / `company` snapshots, expression features on read | the session's partition only, `knowledge_ts` by the read (ADR 0007); snapshots by ADR 0007's one rule | itself | screener, universe, entry, case, exit | each `Feature.licence`; expressions inherit the strictest input |
| Market | (market `MKT:US`, session) | `market.<group>@v<n>.<col>` | stored: `rollups/market/*` (ADR 0047) | that session's row only, never an older one (`session_market`); VIX family one session late | broadcast: the session's one market row merged into every name's row | gate, entry, case, exit (not screener or universe: ADR 0047 as today) | each `Feature.licence`; the gate reads open fields only (H1) |
| Session / calendar | (market, session): columns of the market row | `market.market_conditions@v1.<col>` | stored: `market_conditions@v1`, from `core/time/windows.py` and `events/macro_release` | an event counts only when `known_from <= D` (ADR 0050; FOMC per-year, N5); an unknown schedule is null, so UNKNOWN | as market | as market | open |
| Event | (event) | none for rules: they read its features (`earnings_expected@v1`, `ex_div_before_*`, the ADR 0050 sensitivity features, `sessions_to_fomc`); **the schedule alone reads event rows** (`on_event:` anchors, G18) | stored: `events/*`, consumed by feature groups and the schedule | `known_from <= D` for the schedule's anchor; statistics only over events complete by S | rules: through an instrument or market feature, never a row | rules through those features; the schedule | the features' / the event table's |
| Position | (trade, close) | `position.<name>`, typed list `POSITION_FIELDS` | computed: `engines/structures/` at each close | at close t from t's chain and bar and the entry facts only | the trade's own name (the exit rule evaluates per trade) | exit only | the price source's |
| Portfolio (P2, worked example of a new level, 2.15) | (setup, decision session) | `portfolio.<name>` | computed: the harness and the picks task from the setup's own trades and tonight's pick list | trades with entry S <= D still open at D's close; tonight's list as ranked at D | broadcast: the setup's row merged into each candidate name's row | gate, entry, case | the strictest of the trades' price sources |

A level not in the table (sector, pair) is added the same way (2.15). No level reads the user's real
holdings: ADR 0083 stores no account profile or positions, and a level that did would need an ADR.

### Market

| Entity | What it is | One row per | Main fields | Share setup example | Option setup example | Status | Stored in |
|---|---|---|---|---|---|---|---|
| Instrument | a listed name keyed by `instrument_id` (ADRs 0009, 0018); an option contract is a chain row, not an instrument | instrument per snapshot | `instrument_id`, symbol, `security_type`, `multiplier`, `parent_id`, `calendar`, optionable | NVDA (`EQ:<FIGI>`) | SPY, the underlying | exists | `instruments/reference`, `instruments/listing_history` (#968 extends) |
| Daily bars | split-adjusted OHLCV with a bar status | (instrument, session) | open, high, low, close, volume, `bar_status` | NVDA's entry and exit closes | SPY's spot path and the intrinsic fallback | exists | `bars/1d` |
| Option chain | one session's quotes of every listed contract of an underlying | (underlying, session, contract) | right, strike, expiry, bid, ask, volume, OI, vendor IV / delta (history) | not read | SPY's puts at D | exists (two sources) | `chains/*` (Cboe, open, from 2026-10-02); `option_history/*` (HOD, personal, history root, ADR 0084) |
| Price source | which prices value a trade; an enumeration, not a table | a column of each trade | `bars`, `cboe`, `option_history`, `model` (an IV field, the `option_model_pnl` edges, G22) | `bars` | `option_history` before 2026-10-02, `cboe` from it | new (was "chain source", options only) | a column of the trade contract and of `structure_pnl@v2` |
| Per-name feature | a catalogue feature `group.name@version`, point in time (ADRs 0007, 0023) | (instrument, session) per group | e.g. `momentum.atr_14@v1`, `earnings_expected@v1`, `iv_history@v2`, `ex_div_before_*` | the screen's fields; `atr_14` (stop fallback) | `earnings_expected` (report skip); `iv_rank_high`'s field | exists; `earnings_reaction@v2` extended | `rollups/instrument/*` |
| Market conditions | per-session market facts a setup gates or slices on | session | `regime@v3.label`; `market_conditions@v1`: the `_on` verdicts, `short_premium_allowed`, `rate_shock_on`, `sessions_to_fomc`, `in_opex_week`; `market_triggers@v2` | a variant gated on `rate_shock_on = false` | gate `short_premium_allowed = true` | `regime@v3` exists; `market_conditions@v1` new; `market_triggers@v2` extended | `rollups/market/*` |
| Event | a dated fact with `known_from` (ADR 0050) | event | earnings, dividends, FOMC meetings, macro releases | an earnings-schedule setup's events | ex-dividend (assignment), FOMC distance | exists; FOMC 2002-2023 extended (D2); `events/earnings.time` exists; the opt-in reaction anchor new (G21, F10) | `events/earnings`, `events/dividend`, `events/macro_release` |
| Benchmark series | market series a trade is compared with | (series, session) | bills, SPY, Cboe PUT / BXM, VIX family | bills (cash), SPY | bills, PUT tracking, delta-equivalent SPY | exists; bills to 2002 extended (D1) | `rates/treasury`, `macro/series`, `bars/1d` |

### Setup definition

| Entity | What it is | One row per | Main fields | Share setup example | Option setup example | Status | Stored in |
|---|---|---|---|---|---|---|---|
| Setup (edge) | the typed document: thesis, schedule, universe or named symbols, implementations, position, entry and exit rule, gate, variants, basis (ADRs 0053, 0065, 0083) | setup version | `id`, `version`, `schedule`, `universe` or named symbols, `screeners` (an `[ensemble]` of them is one trial, G22), `base`, `baselines`, `[outcome]` (a position or a book), `gate`, `[[variants]]`, `[[variant_grid]]`, `frozen_from`, `verdict_profile` | the breakout setup, profile `return` | `index_put_write`, profile `tails` | extended (`gate`, `variant_grid`, `verdict_profile`, option outcome keys) | `config/site/edges/<id>/edge.toml`; a user's own in `config/users/<id>/` |
| Screener | a **published rule** at instrument scope with a rank (sort, tie-break, top N) and an identity (name, versions, Guide entry, stored runs, its own ADR 0049 pause); a setup's implementation, baseline or decoy (2.12, G14) | screener version | `id`, `version`, `impl = "rules"`, criteria and groups, rank, base gates, its own `pause_in` | `breakout` v1 | `iv_rank_high` (X2); none for X1 (named symbols) | exists (all 92 site presets are rule screens; the one Python screener is ported by S5) | `config/site/presets/screeners/<id>/v<n>.toml`; `config/users/<id>/` |
| Rule | **the one entity** for every decision (G14): a three-valued condition over named fields in the one criteria language (`all` / `any` / `not` of `{field, op, value}`), checked for its use site (2.13, G9). With an identity and a rank it is a screener; without, a setup-internal rule (universe, gate, entry, exit, case), which can be promoted to a screener | where it is used (or, as a screener, a version file) | `Group` of `Rule`s; use site `gate` / `entry` / `case` / `exit`; its fields' levels and licence | the screener's criteria; `rollup.momentum@v1.rsi_14 lt 30` as an entry condition | `market.market_conditions@v1.vix_contango_on eq true` AND `sessions_to_fomc gt 2` | exists (`core/model/predicates.py`, `parse_group`, `FieldCatalog`); use sites new | inside the document that uses it (`edge.toml`, a preset, a selection) |
| Position template | a named list of legs, each shares or an option, with a collateral rule; a parameter may be a case value chosen by a rule at D (2.4) | template | `id`, legs (`kind` shares / option, `qty`, `right`, strike rule, `delta`, `tenor_days`), `collateral`; in the outcome, `position` / `strike_delta` / `tenor_days` / `expiry_cycle` as a literal or `{ cases, default }` | `long_shares`: +100 shares, capital = notional | `short_put`: one -1 put; tenor 30 when `iv_history@v2.iv_rank_252d gte 0.8`, else 45 | new (`long_shares` / `short_shares` map today's `side`; case values new) | `config/site/positions/templates.toml`; the case values in `[outcome]` |
| Entry and exit rule | when a trade enters and what ends it: the settings as defaults, plus optional entry and exit conditions (rules); plus the published historical stop and hold (2.4a) | setup outcome (and variant) | `start_offset_sessions`, `horizon_sessions`, `[outcome.entry]` (`when`, `within_sessions`), `[outcome.exit]` (`take_profit`, `stop_loss`, `exit_dte` compiled to position rules; `when`; expiry implied); `[exit_rule]` site settings | enter at the next close, or after the first close with RSI(14) < 30 within 5 sessions; exit 20 sessions later (an exit condition is P2); stop published from the winners | enter at S = D + 1, legs selected and filled from S's chain; exit at expiry, 50% take profit, 2 x credit stop, 21 DTE, or when `position.distance_to_strike_pct lt 2` | extended (`[outcome.entry]`, `[outcome.exit]` and `[exit_rule]` new; offset and horizon exist) | `[outcome]` in `edge.toml`; `[exit_rule]` in `verdict.toml`, typed apart |
| Position-level feature | a fact of an open trade at one close (G12) | (trade, close) | `days_held`, `profit_share_of_credit`, `position_delta`, `distance_to_strike_pct`, `move_since_entry_pct`, `dte`, `mark_loss_share_of_collateral` | `days_held`, `move_since_entry_pct` (P2, with the path grain) | all of them | new | not stored; declared in `config/edges/positions/fields.py`, computed by `engines/structures/` |
| Gate | a rule over open market and calendar fields read at D that pauses the setup; decided by ADR 0049's open / closed / unknown (G10) | setup (or variant) | `gate` = a `Group` at use site `gate` (market fields, open licence); the screener's own `pause_in` stays | none, or `regime@v3.label not_in [STRESS, CRISIS]` | VIX curve upward AND no FOMC within 2 sessions | extended | `gate` in `edge.toml`; the screener's own in `defaults.toml [regime.screeners.<id>]` |
| Schedule | when a setup decides: its decision sessions D (G18) | setup | `every_session`, `month_end`, `calendar:` windows, `on_market:` triggers, `on_event:` classes (anchor, `ANNOUNCED_AHEAD`, `picks = event`); calendar choices are gate / entry rules over `market_conditions@v1` (`weekday`, `last_before_weekend`, `fomc_cycle_week`) | `month_end` | `every_session` + gate; C2 `on_event:earnings` at the reaction session | exists (now an explicit entity); calendar columns new (F1) | `schedule` in `edge.toml`; vocabularies `config/edges/schedules/`, `core/time/windows.py` |
| Base | the population a setup's trades are paired with (G17) | setup (or variant) | one of `BASES`: `universe`, `event`, `out_of_window`, `benchmark` (+ `mix:`), none, `delta_equivalent` | `universe` (every eligible name, same position) | `delta_equivalent` (X1) | exists; `delta_equivalent` new (E8a) | `base` in `edge.toml` |
| Baseline and decoy | a paired comparison the setup is shown beside: another screener's picks with the setup's position (`baselines`, `@standard` decoys), or the setup's own picks with another template, `position:<template>` (G19) | setup | screener ids, `@standard`, `position:<template id>` | `momentum_12_1` baseline | A3 against `position:long_shares` | exists; `position:` new (E16) | `baselines` in `edge.toml`; `[decoys]` in `verdict.toml` |
| Book | a weighted set of open positions valued once a session (G16, ADR 0074) | (setup variant, session) | `weighting` (`equal`, `inverse_vol`, `score`, `slots`), slots or weights, `CASH`, overlays (`vol_target`, `canary`, `hold_rank`) | the 14 allocation edges (`portfolio_return`) | X1's fixed-slot ladder (`weighting = "slots"`) | exists (`cross_section/portfolio/`); `slots` new (E8b) | `[outcome]` in `edge.toml`; per-session series in `results/edge_series` |
| Universe | the names a setup may enter at D, and the base its picks are compared with | (setup, session) | a `Selection` over catalogue features, or named symbols; the listing history before the snapshots | S&P 500 + Nasdaq stocks over the liquidity floor | named SPY / QQQ / IWM; for single names, `liquid_optionable_floored` | exists | `universe`, `instruments/*`; the rule in `edge.toml` |
| Variant | an alternative rule, a trial; a grid expands to one per point | variant | `id`, overrides (outcome incl. its entry, exit and case rules; universe; gate; picks) (a rule's other threshold is another variant; grids stay over literal parameters) | 10-session hold; a gated variant; an entry-condition variant | `g_d20_t30_tp50` (delta x tenor x take profit); a tenor-by-IV-rank case variant | extended (`[[variant_grid]]` new; rule overrides) | `edge.toml`; trials in the edge-eval run records |
| Model | a learned scorer whose output is a feature (or a rank) rules read; proposes and ranks, never judges (ADR 0053; 2.14, G13) | (edge, fit) | `[scorer] features`, the fitted coefficients, `fitted_through`; output `feature.edge_score_<edge>` | a screener ranking by `edge_score_<edge>` (P2) | P3: a bucket feature a case value reads | exists (ED7, `edge-scorer-fit`; no fit written yet: the file does not exist on main); use by rules P2 | `config/site/features/scores/edge_scores.toml` (written by `fit-edge-scorer`); the fit's run record |
| Cost model | what a trade pays | site, plus the document's `cost_bps` | shares: `[edge_costs] levels_bps`, `borrow_bps_annual`; options: `[option_costs]` levels, commission | 0 / 15 / 30 / 50 bp round trip | mid / effective / full half-spread, $0.65 a contract | shares exist; options new | `config/site/verdict.toml` |

### Trades and evaluation

| Entity | What it is | One row per | Main fields | Share setup example | Option setup example | Status | Stored in |
|---|---|---|---|---|---|---|---|
| Share trade outcome | a fixed-horizon return from bars for every name and start session | (instrument, S, horizon, benchmark) | `fwd_return`, `fwd_excess_return`, `fwd_max_drawdown`, `fwd_max_return`, `outcome_status` | NVDA from S over 20 sessions | read only for the delta-equivalent base | exists | `outcomes/instrument/forward_returns@v2` (+ `residual_returns@v1`) |
| Option trade outcome | what a position with an option leg earned from the chain, path-dependent exits | (underlying, S, `position_key`) | legs, entry Greeks, collateral, path, `exit_kind`, P&L, `max_adverse`, `price_source`, `licence` | none | SPY 20-delta put from 2024-03-01 to its exit | new (v2 supersedes the empty v1) | `outcomes/option/structure_pnl@v2` |
| Trade (common contract) | one entered position in one shape, whatever the grain (2.5a) | (setup variant, screener or `@named`, decision session, name, horizon or `position_key`) | `entry_session`, `exit_session`, `exit_kind`, `capital_basis` (`notional`, `collateral`, `book`, `none` for `expires_otm` / `hit_target`, G22), `capital`, `return_on_capital` per cost level, `value`, `hit`, `max_adverse`, `price_source`, `licence` (also a column of `edge_trades`, G24) | +4.1% on notional, `HORIZON`, `bars` | +1.2% on collateral, `EXPIRED`, `option_history` | new (a contract over today's `RESULT_COLUMNS`) | not a table: framed into `results/edge_trades` and `results/edge_paper` (both extended) |
| Evaluation run | one harness run of a setup over a range | (setup, variant, horizon, slice) | counts, lift, decile t, DSR, PBO; now for every setup CVaR + n, bootstrap interval, PSR, `excess_roc`, cost rows (drawdown and episodes are read by `edge_evidence`; a named option sleeve's fixed-slot book is E8b's) | lift, decile spread, CVaR of share returns | RoC, excess RoC, CVaR | extended (measures) | `results/edge_eval`, `edge_series`, `edge_legs`, `edge_trades` |
| Verdict | the stored headline of the canonical run, judged by the setup's profile | (setup, judged run, fingerprint) | label, one-line result, basis words; `basis_screener`, `basis_horizon` (ADR 0083 d2, not stored yet: T-basis), profile, fingerprint | `return` profile, unchanged | `tails` profile | extended (profile; basis columns by T-basis) | `results/edge_verdict` |
| Episode | a named market window a setup's trades are replayed against | episode | id, start, end, description | 2020-03 crash rows of a momentum setup | `volmageddon_2018` with the Reg-T flag | exists; vol-shock episodes extended (D3) | `config/site/regime/episodes.toml` |
| Trial | every variant and grid point tried, counted in DSR and PBO | trial | edge, variant, hash, licence | each variant | each grid point | exists | the edge-eval run records (`storage/runs.py`; read by `services/read/evaluation/runs.py`) |

### Each night

| Entity | What it is | One row per | Main fields | Share setup example | Option setup example | Status | Stored in |
|---|---|---|---|---|---|---|---|
| Screener run | one run of one screener for one user at a session (2.12) | (user, screener config, session) | run id, version, decisions, picked, new / dropped; every row's decision and rank; criterion values; picked and PAUSED rows | `breakout`'s run at D | `iv_rank_high`'s run (X2); none for X1 | exists | `results/screen_runs`, `results/rule_screen`, `results/rule_screen_values`, `results/screen_picks` |
| Setup pick | what a setup took at a session by the one pick rule, per screener | (user, setup, screener or `@named`, session) | status (`picked`, `gate_closed` (new), `not_decision_day`, `unjudged`, `skipped`), `pick_ids`, `pick_sides` and `pick_weights` (new, G20: short, long-short and book setups leave `unjudged`), the evidence licence (E1) | `breakout`'s first `top_k` qualified names in the universe | SPY, QQQ, IWM (named, no screener), or `paused` | extended (the `gate_closed` status; `@named` rows) | `results/edge_picks` |
| Example position | the position the rule would open from the served session's prices (2.8) | pick | shares: entry close, stop price, exit date (a short pick: `short_shares`, "borrow assumed"; a book pick: its names, no size shown, G20); options: legs, net credit, collateral, Greeks, report and ex-div flags, stop as a loss, exit date | NVDA entry 182.40, stop 171.50, exit 2026-11-28 | SPY 19 Dec 560 put, credit 4.10, collateral 56,000 | new (computed on read) | not stored (a table only if E9 measures over 0.2 s) |
| Historical exit rule | the published stop and hold of a setup's pick (ADR 0083 d3, 2.4a) | (setup, served session) | stop distance, trades it rests on, fallback flag, hold | 6.0% (80th percentile of 140 winners), or 2 x ATR(14) | the declared 2 x credit stop and 50% take profit; the percentile only without a declared stop | new (decided, not built) | computed on read from `results/edge_trades` |
| Setup state | ON / OFF / PAUSED / UNKNOWN with a reason (2.3) | (setup, served session) | state, reason | ON | PAUSED: the VIX curve is inverted | new (computed on read) | not stored |
| Paper record | the forward record of every open setup (ADR 0064 amendment) | (record owner, setup, signal session, name) | signal, settlement, `return_on_capital`, `exit_kind`, `price_source`, licence | NVDA's forward 20-session return | the Cboe-priced put from the signal | extended (the contract's columns; option P&L is null today) | `results/edge_paper` |

---

## Data stores (every entity, G24, G25)

From the entity-fit review's Part 3 (`entity-fit-and-stores.md`, same folder): sizes [M] measured on
the local main store on 2026-10-31 (`du`, Parquet footers), the rest [I]. Roots: **main**
(`ALGOTRADE_DATA_URL`) and **history** (`ALGOTRADE_OPTION_HISTORY_URL`, ADR 0084). Configuration
entities (setup, screener, rule, template, gate, universe rule, variant, schedule, base, baseline,
book parameters, cost model, episode, model) are files, never tables; the design adds no rule, pick,
state or book table.

| Entity | Stored / computed | Table, grain (one row per) | Writer (owner) | Root | Licence | Size now [M]; with history [I] | Fix in this design |
|---|---|---|---|---|---|---|---|
| Instrument | stored | `instruments/reference` (instrument, snapshot), `instruments/listing_history` (interval) | universe and listing tasks | main | open | 141 MB; + < 0.1 GB (#968) | none |
| Daily bars | stored | `bars/1d` (instrument, session) | `tasks/market/bars.py`, `bars_history.py` | main | open | 1.6 GB from 2010-01-04; + 0.5-0.8 GB for 2002-2009 | 2002-2009 from the running Tiingo backfill (G25) |
| Option chain | stored | `chains/option_quotes` (underlying, session, contract) | `tasks/market/option_chains.py` | main | open | 97 MB a session; about 24 GB a year | D9 growth check (G25) |
| Option history | stored | `option_history/*` (contract, session) | `option-history-import` | history | personal | 70-90 GB | none |
| Per-name feature | stored | `rollups/instrument/<group>@v<n>` (instrument, session) | `rollup-computation` | main; history chain features in history (F7) | per feature | 24 GB; + 3-6 GB (history root) | one personal-data rule (G24) |
| Market conditions | stored | `rollups/market/<group>@v<n>` (`MKT:US`, session) | `market_rollups.py` | main | per feature | 1.1 GB, 88 k files; + < 0.1 GB | a `tables.toml` entry per new group (G24) |
| Event | stored | `events/<class>` (event) | one task per class | main | per source | 5.2 GB | `time` exists (G16-M1); dividends 2002 check (#974) |
| Benchmark series | stored | `rates/treasury`, `macro/series` | rates, macro tasks | main | open; Cboe indexes personal | rates from 2024-01-02 | bills to 2002 from the Tiingo session / D1 (G25) |
| Position-level feature | computed | per close in `engines/structures/`; paths only on `book = true` rows | - | - | price source's | - | none |
| Share trade outcome | stored | `forward_returns@v2` (instrument, S, horizon, benchmark); `residual_returns@v1` | `forward-outcomes` | main | open | 18 GB, 382 M rows from 2010; + about 8.5 GB for 2002-2009 | D8 backfill (G25) |
| Option trade outcome | stored | `structure_pnl@v2` (underlying, S, `position_key`) | one publisher `frame_and_publish`; Cboe nightly and the history task call it | main | per row | 0; about 0.5 GB single names, 0.2 GB sleeves, 0.4 GB a year Cboe | one publisher; key from resolved legs (G24) |
| Trade (contract) | framed | `results/edge_trades`, `results/edge_paper` | `edge-evaluation-detail`, `trade-evidence`; `edge-paper-trading` | main | per row (`licence` exists, reused) | 27 MB / 744 k rows; small | none (the licence columns exist) |
| Book | computed in run | series in `results/edge_series` | `cross_section/portfolio/` (one owner) | main | trial's | 6.9 MB | `slots` weighting, no `evidence/book.py` (G16) |
| Evaluation run, trial | stored | `edge_eval`, `edge_series`, `edge_legs`; run records | `edge-evaluation`, `edge-leg-reuse`, `run-records` | main | trial's | 13 MB; 1.8 GB legs in 55 k files; + 0.8 GB legs | watch small files in E5 |
| Verdict | stored | `results/edge_verdict` | the run's publish, `edge-verdicts` | main | trial's (E1) | 56 KB | profile, T-basis columns |
| Screener run | stored | `screen_runs`, `rule_screen`, `rule_screen_values`, `screen_picks` | `screen-execution` | main | per value row | 2.9 GB values (634 M rows) | none |
| Setup pick | stored | `results/edge_picks` (user, edge, screener or `@named`, session) | `edge-picks` | main | per viewer, plus the evidence licence (E1) | 16 KB | `gate_closed`, `@named`, `pick_sides`, `pick_weights` (G20) |
| Example position, published exit, setup state | computed on read | - | `positions/`, `verdict/state.py` | - | the run's / chains' | measured in E9, E12a | none |

---

## 1. Coverage inventory

Every structural concept the four research files use or imply, section by section, (1f) the
owner's generalisation to share setups and (1g) every part of a setup as a rule over features. Status:
**exists** (the proof is named), **partial** (what is there and what is not), **missing**.
"Lands in" names the design element (sections 2.x) and the build slice (section 7), or says
**REJECTED** / **DEFERRED** with the reason. Research ids: catalogue §n / A1..G2; part 2 N1..N10 and
(b); regimes D1..D12, R1..R12, R-A..R-H; AI regime §n.

### 1a. Cross-cutting rules (catalogue §1, part 2 (b))

| # | Concept | Research | Backend need | Today | Lands in |
|---|---|---|---|---|---|
| 1 | Three cost levels (mid; effective; full half-spread + $0.65/contract), verdict on the full level | §1.1, §7.9 | per-leg half-spread at entry and exit; levels applied in the harness | partial: `option_pnl` already pays the entry and the exit half-spread plus `cost_bps` (`cross_section/hit.py:347-353`), so "full" largely exists; no mid / effective rows, no commission per contract | 2.4 cost model, 2.6 cost rows; `[option_costs]`; E6b |
| 2 | Slippage factor by leg count (0.75 one leg, 0.53 four legs) | part 2 (b) | the "effective" level keyed by leg count | missing | `[option_costs] effective_share_by_legs`; E6b |
| 3 | Quote filters: two-sided, not crossed, spread cap, volume or OI > 0; P&L from mid | §1.2, §7.11 | one filter in the selector | partial: v1 needs two-sided quotes (`option_paths.py`); `wing_search.py` filters by OI | 2.4 selector; `[option_quotes]`; E3a |
| 4 | Weekend entry overlay (Thu/Fri close) | §1.3, A6 | an entry-day condition; base = Mon-Thu entries | missing (ADR 0075: weekend window skipped) | `market_conditions@v1.weekday` + a gate variant (closed slice = Mon-Thu); X1, P2 |
| 5 | Day / night split | §1.3 | open quotes | missing | REJECTED: needs intraday or open quotes |
| 6 | Premium at the front of the curve (short tenors) | §1.4 | tenor grid | missing as a grid | 2.7 variant grid; X1 |
| 7 | Unhedged P&L beside a daily delta-hedged diagnostic | §1.5, §7.4 | hedged P&L per trade | exists for straddles (`hedged_pnl_per_underlying`, `quant/edges/chain_pnl.py::hedged_pnl`) | generalised in v2 (`pnl_hedged_mid`); 2.6; E3a |
| 8 | Covered call = beta + short vol + reversal (decomposition) | §1.6 | stock-leg P&L apart from option-leg P&L | missing | v2 `stock_pnl`, `option_pnl`; 2.6 stock share; E3a |
| 9 | Strike by delta, never by target yield | part 2 (b) A3 | no yield strike rule | partial: `strike_delta` for `put_short` | 2.4 (no yield rule; fitness test); E2 |
| 10 | The wing priced as its own cost column | part 2 (b) A4 | leg-level entry mids | missing | v2 leg mids; 2.6 `wing_cost`; E6b |
| 11 | The wheel's stock share of return | part 2 (b) G1 | stock-leg P&L per cycle | missing | v2 `stock_pnl`; wheel book DEFERRED to P2 (2.11) |
| 12 | No hindsight capital; overlapping positions consume collateral | part 2 (b) | fixed collateral slots in the book | missing | 2.6 book (in-run, fixed slots); E8b |
| 13 | Management as a variant, at closes only; hold-to-expiry official | §7.8, A1, A4 | path-dependent exit; each rule a trial | missing (v1 holds to the horizon) | 2.4 `[outcome.exit]`; 2.7 grid; E3b |
| 14 | Never roll | brief | no roll rule | n/a | 2.4: no `roll` key; a closed trade ends |

### 1b. Setups (catalogue §2-§5, part 2 (a))

| # | Concept | Research | Backend need | Today | Lands in |
|---|---|---|---|---|---|
| 15 | Index / ETF cash-secured put write, delta x tenor grid | A1 | `short_put` on named ETFs; grid | missing (idea c19 only) | X1 `index_put_write`; 2.4, 2.7 |
| 16 | Weekly expiry selection | A2 | expiry cycle rule | missing | 2.4 `expiry_cycle`; X1 grid |
| 17 | Ladder (a fifth of collateral each week) | A2 | staggered slots | missing | 2.6 book (fixed slots); E8b |
| 18 | Covered call strike / tenor | A3 | `covered_call` template | missing | 2.4; X3 |
| 19 | Skip the cycle with earnings inside (C4) | A3, C4 | report test against the selected expiry | partial: `earnings_before_expiry` (Cboe chains only), `earnings_expected@v1` (history-safe), inline `no_earnings` in `vrp_short_premium` | 2.4 `skip_report_in_life` in the selector; E3b |
| 20 | Put spread, strangle, iron condor | A4 | multi-leg templates; `max_loss` collateral | partial: `strangle` as `expires_otm` only | `put_spread` now; strangle / condor templates when an edge names them (P2); X1 variants |
| 21 | Vol-timed overlay (i) contango, (iii) ex-ante VRP | A5 | open market verdicts; gate on edges | partial: the ADR 0049 gate pauses short volatility in STRESS / CRISIS inside the harness's screens (`config/site/defaults.toml:39-40`); `vix_term_on` card exists; no contango or VRP verdict | F1 open verdicts (`vix_contango_on`, `index_vrp_rich_on`); 2.2 edge gate; X1 variants |
| 22 | Vol-managed sizing (ii) | A5 | sized book | missing | DEFERRED to P2 (part 2 (c) demotes it) |
| 23 | Weekend overlay | A6 | as #4 | | #4 |
| 24 | Tail hedges, protective puts, risk reversal | A7 | none | n/a | REJECTED as setups (dead / weak); Guide entries (X8) |
| 25 | IV-HV straddles; 252-session realised vol | B1 / c12 | `hv252` | missing (`vol_stats@v1`: hv10 / hv60) | F6 `vol_stats@v2.hv252` (P2); X6 |
| 26 | Calls on high-vol, puts on low-vol, never the reverse | B2 | two sleeves, each the other's decoy | partial: screeners `low_volatility`, `ivol_high` | X4; S2 |
| 27 | Term slope 30 vs 180 days from chains | B3 / c13 | long-tenor ATM IV | partial: `iv_term@v1` (Cboe only) | F7 history features + `iv_term@v2.iv_180d` (P2); X6 |
| 28 | Characteristic sorts (profitability, cash, default, vol-of-vol) | B4 / c14 | sorts as screeners | partial: `profitability_z`, `balance_sheet.cash`, `ohlson_o`; vol-of-vol missing | S4 (P2); vol-of-vol via F7 (P2) |
| 29 | Overpriced puts on short-constrained names; borrow fee | B5 | delta-hedged put template | partial: `composite_rank`, `days_to_cover` | P3; borrow fee REJECTED: no source, short interest is the proxy |
| 30 | Option momentum (trailing straddle returns) | B6 / c15 | per-name past straddle returns as a feature | missing | P3, through F7's path from past chains, never from the outcomes grain (quarantined) |
| 31 | Illiquidity premium, order flow | B7 | signed trades | missing | REJECTED: intraday |
| 32 | No selling next month in opex week | B7 crumb | opex condition | partial: `calendar:` windows (`core/time/windows.py`) | `market_conditions@v1.in_opex_week` + gate variant (P3); F1 |
| 33 | Pre-earnings straddle buy on historical / implied move | C1 / c16 | ratio feature | partial: `implied_move@v1`; only the last reaction stored | F4; S3; X6 (P2) |
| 34 | Conditional earnings sell, iron fly, loss tail as the gate | C2 / c17 | ratio, bellwether screen, market gate, `iron_fly`, CVaR criterion | partial (see #33) | X5; 2.2 gate on the open `regime@v3.label` (pause in STRESS, CRISIS: the existing ADR 0049 rule); 2.6 `max_cvar_ratio` |
| 35 | Post-earnings entry | C3 | `on_event:earnings_reaction` | partial: event schedules exist; a schedule is not a variant key | P3, its own edge if built |
| 36 | FOMC straddle; pre-FOMC VIX drift (two windows) | C5, N10 | FOMC dates 2002+ with honest `known_from`; `on_market:fomc` | partial: FOMC 2024-2027 (`releases.toml`); ADR 0075 plans `on_market:fomc` | D2; F3; P3 edges |
| 37 | Risk-neutral skewness assets | D2 / c06 | smile moments | missing | REJECTED for now: needs model-free smile moments; overlaps D3 and `skew@v1` |
| 38 | Covered calls on lottery names | D3 / c31 | covered-call outcome on `lottery_max` picks | partial: `lottery_max` exists | X6 (P2) |
| 39 | Calendar spread | E1 / c30 | per-leg tenor | missing | leg schema supports it; template DEFERRED (P3) |
| 40 | Ex-dividend early assignment; deep-ITM put early exercise | F1, §7.10 | dividends in the engine | partial: `events/dividend` from 2002 (#974) | 2.4 assignment; E3b |
| 41 | The wheel | G1 / c29 | cycle state | missing | DEFERRED to P2: a book over v2 rows (2.11) |
| 42 | IV rank moved from an edge into variants | G2 / c18 | `iv_rank_high` as a screener of other edges | exists: screener `iv_rank_high`, `iv_history@v2` | X2 / X3 list it; c18 retired |
| 43 | Collar | N1 | long-put template | missing | DEFERRED (P3 display variant); REJECTED as a setup |
| 44 | Diagonal / PMCC | N2 | legs with own tenor and strike | missing | leg schema supports it; template DEFERRED (P3) |
| 45 | Jade lizard | N3 | template constraint | missing | DEFERRED (P3) |
| 46 | Put ratio 1x2; worst-case collateral | N4 | collateral rule | missing | DEFERRED (P3), with `worst_case` collateral |
| 47 | Single-name strangle vs condor: full spread, Reg-T row | N5 | cost by universe; margin denominator | missing | `[option_costs]` single names on `full`; v2 `regt_margin`; E6b |
| 48 | Covered strangle | N6 | template | missing | P2 template when X3's variant is filed |
| 49 | Embedded-leverage sort (contracts) | N7 | contract-level screener | missing | REJECTED as a screener (screeners pick names); the A1/A2 grid tests the index version; Guide |
| 50 | Retail-attention filter on earnings trades | N8 | attention criterion | partial: `retail_options_lottery_attention` edge, `retail_option_attention` screener | S3 criterion (P2) |
| 51 | Election-spanning options | N9 | election calendar | missing | REJECTED: about 7 events; Guide only |
| 52 | Re-file / retire the filed option edges | §5 | outcome kind change | n/a | section 8; X2, X5, X6 |
| 53 | ETF option universe | §3, A1 | named or ranked ETFs | partial: `liquid_optionable*`, named universes (`named.py`) | named lists for P1; a ranked preset after F7 |

### 1c. Evaluation (catalogue §6-§7)

| # | Concept | Research | Backend need | Today | Lands in |
|---|---|---|---|---|---|
| 54 | Per-contract fields; exercise style | §6 | one chain frame for both sources | partial: HOD has bid / ask / last / volume / OI / vendor IV and delta (ADR 0084 d4); Greeks computed by us | 2.4 chain frame (`chain_inputs.py`); exercise style by root table |
| 55 | Stale-quote filter (last-trade time) | §6 | trade time | missing (HOD has none) | REJECTED as a time test; replaced by #3 |
| 56 | Collateral first, notional beside, Reg-T deeper; never return on premium | §7.1 | three denominators | missing (v1: per premium, per underlying) | v2 `collateral`, `notional`, `regt_margin`; 2.6 |
| 57 | Delta-equivalent exposure | §7.1 | entry position delta | missing | v2 `position_delta`; 2.6; the `delta_equivalent` base (E8a) |
| 58 | Win rate only beside the chain's own probability | §7.2 | expired-OTM flag + quoted probability | partial: `expires_otm` `reference_rate` (model strike) | v2 `expired_otm`, `quoted_otm_prob`; 2.6 |
| 59 | Skew, kurtosis, CVaR 5% / 1% with n-in-tail, worst window / month, drawdown, Calmar, Sortino, Omega | §7.3 | tail statistics | partial: moments and DSR (`quant/edges/statistics.py`); drawdown (`analytics/metrics.py:31`) | `quant/edges/tails.py` (CVaR, n, worst); drawdown reused; Calmar / Sortino / Omega P2; E6b |
| 60 | PSR and DSR; N counts the grid | §7.3 | | partial: DSR; variants are trials | PSR = `deflated_sharpe(x, 1, 0)`; grid points are trials (2.7) |
| 61 | Haircut Sharpe, PBO | §7.3 | | exists: `haircut_sharpe`, `pbo_cscv` | reused |
| 62 | Greeks at entry; IV minus realised captured | §7.5 | entry Greeks; window realised vol | missing | v2 Greeks, `realised_vol_window`; averaged Greeks P2 |
| 63 | Benchmarks: cash, buy-and-hold, delta-equivalent, Cboe index tracking | §7.6 | | partial: bills (`reads/session.py::bill_yield`); Cboe series (`macro.toml`) | 2.6; E6b, E8b |
| 64 | Independent decision sessions; earnings clustered by session | §7.7 | | partial: spacing, `independent_sessions` | 2.6 block bootstrap; clustering DEFERRED (2.11) |
| 65 | Effective number of independent bets | §7.7, AI §3.4 | per-session pick correlation | missing (`corr_252d` per name exists) | DEFERRED to P2 (2.11) |
| 66 | Management at closes only, stated | §7.8 | | n/a | 2.4; Guide term |
| 67 | European index vs American ETF; ITM assigned at the close | §7.10 | | missing | 2.4 assignment; E3b |
| 68 | Survivorship: a name that stops quoting must not drop out | §7.11 | settle at intrinsic | partial: HOD keeps delisted symbols; v1 drops `NO_EXIT_QUOTE` | 2.5 exit fallback; E3a |
| 69 | Eligible set as of S; earnings dates known before the report | §7.11 | | partial: `known_from` (ADR 0050); history reads PRIOR_YEAR dates; listing history in #968 | 2.9; dependency #968; disclosed "event captured" share |
| 70 | P&L only from traded quotes | §7.11 | | exists: `option_pnl` basis `chain` | v2 keeps it |
| 71 | Stress replays as named rows; Reg-T forced-liquidation row | §7.12, regimes §4.1 | named windows | partial: `episodes.toml` lacks the short vol shocks | D3; 2.6 episode rows; E8b |
| 72 | Synthetic 2008 shock | §7.12 | | n/a | REJECTED: 2008 is in the bought history |
| 73 | Stationary block bootstrap; Ledoit-Wolf; the "cannot invent the crash" line | §7.13 | | missing | `quant/edges/tails.py`; Ledoit-Wolf P2; Guide term; E6b |
| 74 | Capacity: OI, spread %, names passing, collateral | §7.14 | | partial: stock `pick_adv_*` | v2 `entry_oi_min`, `entry_spread_share`; E6b |
| 75 | The setup page lead and the idea card fields | §7.15 | read objects | missing | E11; UI later |
| 76 | Return on notional and on Reg-T | §7.15 | | missing | v2 columns; 2.6 |

### 1d. Regimes (regimes file)

| # | Concept | Research | Backend need | Today | Lands in |
|---|---|---|---|---|---|
| 77 | D1 VIX band + 252-session percentile | D1 | rolling percentile | partial: `vix_band` (expression, personal) | F1 `market_conditions@v1.vix_pct_252`, `vix_low_on` / `vix_high_on` |
| 78 | D2 curve: three states; VIX9D/VIX kink; VIX3M/VIX6M slope | D2 | market-level VIX9D, VIX6M | partial: `vix_term_ratio`, card `vix_term` (on > 1.0); VIX9D / VIX6M only per fund (`etf_macro@v1`) | F1 columns `vix9d`, `vix6m`, `vix_contango_on`, `vix_front_kink_on` |
| 79 | D3 index VRP (VIX - SPX RV) | D3 | | partial: `spx_realised_vol_20d` | F1 `index_vrp_rich_on` / `index_vrp_cheap_on` (RV20 for RV21, said) |
| 80 | D4 trend bands | D4 | | exists: `spx_trend_200d_on`, `spx_death_cross`, `spx_drawdown_band` | reused |
| 81 | D5 narrow leadership | D5 | | partial: `breadth_200d_on` | F1 `breadth_narrow_on` (P2) |
| 82 | D6 correlation / dispersion; COR1M | D6, R-D | member RVs; COR1M | missing | F8 (P2); D4 series (P2) |
| 83 | D7 post-spike recovery | D7, R-B | 20-session high, 252 median | missing | F1 `post_spike_recovery_on`; F3 trigger |
| 84 | D8 rate shock | D8, R-F | 10y change | partial: curve from 2024-01-02 only | D1; F1 `y10_chg_63d`, `rate_shock_on` |
| 85 | D9 earnings season share | D9 | cross-sectional share | missing | F1 `earnings_season_share` |
| 86 | D10 event week | D10 | FOMC, opex | partial: FOMC 2024-2027 | D2; F1 `sessions_to_fomc`, `in_opex_week`; election REJECTED (#51) |
| 87 | D11 vol of vol | D11, R-H | market VVIX | partial: VVIX only in `etf_macro@v1` | F1 `vvix`, `vvix_high_on` |
| 88 | D12 macro / credit tier | D12 | | exists: `regime@v3.macro_risk`, `hy_oas_on` | reused |
| 89 | Composite R1-R12 label at entry since 2002 | §1-§2 | label with precedence | missing | DEFERRED to P2 (F9: an open `market_conditions@v2.conditions_label`); P1 slices by `regime@v3.label` and the curve card |
| 90 | Per-regime evidence (the grid) | §2 | slices | partial: `regime@v3.label` slices only | 2.2 `[slices]` (display rows); E7 |
| 91 | "Relative only" sign | §2, §5 | absolute and relative per slice | missing | 2.6 per-slice RoC and excess (display); per-slice decisions DEFERRED |
| 92 | R-A stand-aside as a published rule | R-A | an open gate + gated vs ungated evidence | partial: the ADR 0049 gate already pauses short volatility in STRESS / CRISIS (`defaults.toml:39-40`) inside the harness's screens | F1 `market_conditions@v1.short_premium_allowed` (open); 2.2 edge gate; X1; Guide |
| 93 | R-B post-spike re-entry; per-episode rows | R-B | state; episode rows | partial: `vix_spike` trigger | X1 gate variant on `post_spike_recovery`; 2.6 episode rows |
| 94 | R-C bear call side | R-C | `call_spread`; trend gate | missing | P2 template + gate variant |
| 95 | R-D dispersion-lite | R-D | correlation state | missing | F8 + slices (P2) |
| 96 | R-E low-vol grind; cheap-vol decoy | R-E | slice; long straddle | partial | slice (P2 label); decoy P3 |
| 97 | R-F rate-shock slice | R-F | slice | missing | `rate_shock` card as a slice |
| 98 | R-G reverse calendar in backwardation | R-G | template + gate | missing | DEFERRED (P3) |
| 99 | R-H vol-of-vol overlay | R-H | VVIX gate | missing | X1 gate variant on `vvix_high` (P3) |
| 100 | Inverse-rule decoys | R-A, R-B | decoys from conditions | partial: the ADR 0049 gate pauses (no inverse evaluation) | 2.2: the closed slice of every gate is its inverse decoy; R-B's two more decoys are gate variants |
| 101 | On / off table for the product | §5 | setup state | missing | 2.3 v1 state; the full table after per-slice decisions (P2) |
| 102 | Cederburg / Barroso caveat | part 2 (c) | | n/a | X1 quality bar; forward holdout for research-chosen gates (decision 4) |
| 103 | Series start dates (VIX9D 2011, VIX6M 2008, VVIX 2006, VIX3M 2007-12) | regimes §0 | unknown before the start | exists as series | 2.2 unknown handling; section 6 |

### 1e. The AI regime fortnight

| # | Concept | Research | Backend need | Today | Lands in |
|---|---|---|---|---|---|
| 104 | Several picks are one bet | §3.1, §3.4 | effective bets | missing | DEFERRED to P2 (2.11) |
| 105 | Event clustering inside one expiry | §3.2, §3.4 | events in the trade's life | partial: `earnings_before_expiry` | example position flags (2.8); cluster count DEFERRED (2.11) |
| 106 | IV inflated by events | §3.2 | expiry spans a report | partial: `implied_move@v1.move_basis`, `earnings_before_expiry` (`config/site/features/options/earnings.toml:8-14`) | the selector's `skip_report_in_life` (2.4); de-evented IV REJECTED (needs a term-structure jump model) |
| 107 | Skew steepening | §3.1 | | exists: `skew@v1`, `skew_history@v1` | reused |
| 108 | Front term kink at the report | §3.1, §3.3 | | exists: `term_ratio_next_30` (`config/site/features/options/positioning.toml:99-106`), `iv_term@v1` | reused; no new feature |
| 109 | Historical move ratio not computable | §2.3 | past moves | missing | F4 |
| 110 | Momentum drawdown vs crash state | §3.1 | | n/a | REJECTED: a stock-edge concern |
| 111 | Sector drawdown entry is not the index rule | §3.3 | | n/a | REJECTED as a rule; noted in X1's quality bar |
| 112 | VIX one session late | §2.3 | same observation date across ratios | exists (all VIX-family series `release_lag_days = 1`, `macro.toml`) | 2.1 same-date rule |
| 113 | IV rank over a short window | §3.2 | longer IV history | partial: `iv_history@v2` is over our own `iv30@v1` (`iv_history.py:1-5`), which starts with the Cboe chains; the 502-session IBKR history is `ibkr_iv@v1` / `ibkr_iv_history@v1` | F7 history features (P2) |
| 114 | Store vs web figures | §4 | | n/a | REJECTED: a report convention |

### 1f. Share and option setups in one vocabulary (owner, 2026-10-31)

| # | Concept | Source | Backend need | Today | Lands in |
|---|---|---|---|---|---|
| 115 | A share setup is a position of one share leg; a covered call is a share leg plus a call | owner G1 | a share leg kind in the template schema | partial: `side` long / short / long_short on return outcomes; the covered call's stock as `stock = 100` | 2.4 `long_shares`, `short_shares`, `position_of`; E2 |
| 116 | One entry and exit rule for both kinds | owner G2 | entry offset, horizon, take profit, stop, DTE, expiry | partial: `start_offset_sessions`, `horizon_sessions`; `max_drawdown` as a hit filter | 2.4a `[outcome.exit]`; E3b |
| 117 | ADR 0083 historical exit rule (stop = drawdown 80% of winners never exceeded, fallback 2 x ATR(14), hold) | owner G2, ADR 0083 d3 | percentile over the basis's winning trades | missing: decided, not built (no `[exit_rule]`, no code; roadmap "then exit rule"); the basis columns not stored yet | 2.4a; E12a (shares), E12b (options); owner decision 8 |
| 118 | One trade contract over both outcome grains | owner G3 | a shared trade shape, one evidence path | partial: `hit.py::RESULT_COLUMNS` and `results/edge_trades` already cover every kind | 2.5a; E6a |
| 119 | Price source for shares and options | owner G4 | `bars` / `cboe` / `option_history` | partial: `chain_source` planned for options only | 2.5, 2.5a |
| 120 | Example position for share picks (entry close, stop price, exit date) | owner G5, ADR 0083 | a read per pick | missing | 2.8; E9, E12a |
| 121 | Tails, bootstrap, PSR and cost levels on share setups, without re-judging them | owner G6 | the measures for every setup; a verdict profile | partial: share cost levels `[edge_costs]` (ADR 0064); DSR | 2.6; E6b; owner decision 7 |
| 122 | Market conditions are not options-specific | owner G7 | the leaf group's name | n/a | `market_conditions@v1` (2.1; F1) |
| 123 | Screeners and screener runs as explicit entities; named-symbol setups skip screeners | owner G8 | entity definitions; how picks combine with both gates | exists: presets, the four screener-run tables, `picks.long_picks`, `results/edge_picks` | 2.12; Entities; E9 |

### 1g. Every part of a setup as a rule over features (owner, 2026-10-31)

| # | Concept | Source | Backend need | Today | Lands in |
|---|---|---|---|---|---|
| 124 | One criteria language and evaluator for every part of a setup | owner G9 | reuse, plus a per-use check of levels, session and licence | exists: `Rule` / `Group`, `parse_group`, `evaluate_group` (selections, rule screens, filters); `Criterion` and ADR 0071 groups for screeners; `FieldCatalog.check` (no use site) | 2.13; E2r |
| 125 | Feature levels: instrument, market, session / calendar, event, position | owner G9 | each level's field head, store and point-in-time rule | partial: instrument fields are in `FieldCatalog`; market fields have a head (`fields.py`) but are not in the catalogue (ADR 0047), and no licence is; calendar facts are `market_conditions@v1` columns (F1); events only through features; position missing | Entities "Feature levels"; 2.13; F1; E2r |
| 126 | Gate as a rule over market and calendar features (VIX curve up AND no FOMC within 2 sessions) | owner G10 | a `Group` at use site `gate`, open licence, the ADR 0049 decision | partial: one label field (`[regime] label`) and `pause_in` | 2.2; E7 |
| 127 | Entry condition (enter after the first close a rule is TRUE, within a wait) | owner G11 | a harness mapping from D to S over existing per-S rows, the same rule on the base | missing | 2.4a; E13 |
| 128 | Exit condition over catalogue and position-level features | owner G11, G12 | the engine evaluates an ordered list of rules at each close; the writer supplies the named catalogue fields per close | missing (take profit, stop, DTE planned as fixed keys) | 2.4a; E3b, E4; shares P2 |
| 129 | Position parameters and position choice from a rule (tenor 30 when IV rank is high, else 45) | owner G11 | case values resolved at D; rows keyed by the resolved point | missing | 2.4; E2r, E13; E9 (picks) |
| 130 | Position-level features (days held, profit share of credit, delta, distance to strike, move since entry, DTE) | owner G12 | one typed list, the `position.` head, the engine's per-close computation | missing (the engine's marks exist in `option_paths.py`) | 2.4a; E2r, E3b |
| 131 | A model's output as a feature or rank rules read; ML-allowed sources only | owner G13 | the fitted score as a field; judged after `fitted_through`; licence inherited | exists: ED7 `edge-scorer-fit`, `edge_score_<edge>` expression feature, `no-ml-tables` guard | 2.14; E14 (P2); decision 10 |
| 132 | Every screener is a rule; Rule the one entity; promotion of setup-internal rules | owner G14 | the screener as a published rule; port the one Python screener | partial: 92 site presets `impl = "rules"`; `short_premium_liquidity.py` still runs nightly as a site config and feeds `legacy_liquidity_csv` | 2.12, 2.13; S5 |
| 133 | Feature levels as a declared extension point (key, provider, point in time, join path, scopes, licence) | owner G15 | one declaration the catalogue reads | partial: feature-group entities (`GROUP_TABLE_PREFIXES`) for stored levels only | 2.15; E2r |
| 134 | Portfolio features of the setup's own book and tonight's list (open positions, effective bets, sector exposure, open premium at risk, concentration) | owner G15, ADR 0083 | a computed provider over the setup's trades; never real holdings | missing | 2.15; E15 (P2) |

### 1h. Entity fit against every setup and the stores (entity-fit review, owner-approved 2026-10-31)

| # | Concept | Source | Backend need | Today | Lands in |
|---|---|---|---|---|---|
| 135 | Book as one entity (14 allocation edges, the A2 ladder) | EF-G1, EF-G10 | one owner; the book series in the evidence path | exists: `cross_section/portfolio/` (ADR 0074); a second book was planned | G16; Entities; E6a, E8b |
| 136 | Base as an entity | EF-G2 | the `BASES` vocabulary named | exists (`BASES`); `delta_equivalent` missing | G17; E8a |
| 137 | Schedule as an entity; event-row anchors; calendar columns | EF-G3 | providers named; `last_before_weekend`, `fomc_cycle_week` | exists except the two columns | G18; F1; market-event windows P3 |
| 138 | Position baseline (own picks, other template) | EF-G4 | `baselines = ["position:<template>"]` | missing | G19; E16 |
| 139 | Short, long-short and book picks reach Ideas | EF-G5 | `pick_sides`, `pick_weights`; short shape | missing: 27 edges `unjudged` | G20; E9; decision 11 |
| 140 | Earnings report time of day | EF-G12 | the stored `time`; an opt-in reaction-session anchor | exists: `events/earnings.time`; the anchor is missing | G21; F10 |
| 141 | Price source `model`; `capital_basis = none`; Ensemble; canary | EF-G19, G20, G11 | enum value, mapping, entity text | exists in code, missing in the model | G22; E6a |
| 142 | P2 / P3 extensions (hedge key, debit / worst-case collateral, pairs, path share exits, sizing, chains and rolls, a `select` site, open fills, link levels) | EF-G6..G11, G13..G15, G17 | the smallest generalisation of an existing entity | missing | DEFERRED: 2.16 |
| 143 | Futures as futures; borrow availability | EF-G16, EF-G21 | - | - | REJECTED (out of scope): via ETFs / market features; "borrow assumed" |
| 144 | One rule for personal derived data; one publisher; `edge_trades.licence`; `position_key` from resolved legs; missing columns | stores §3e 1, 3, 4, 7, 8 | store contracts | partial | G24; §5 (ADR 0084 text); E1, E4, E5, E6a |
| 145 | 2002-2009 prerequisites (bars, rates, dividends, forward returns); chain growth | stores §3e 5, 6 | data slices before E5; a growth check | missing on this store (bars and forward returns from 2010, rates from 2024) | G25; the Tiingo session, D8, D9 |

Every row lands in a design element, is deferred with its phase, or is rejected with a reason.

---


Parts: [concepts 1](backend-concepts-1.md) (section 2.1-2.4a), [concepts 2](backend-concepts-2.md) (2.5-2.16), [build](backend-build.md) (sections 3-10).
