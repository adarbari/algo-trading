> Plan part 4 of 4: sections 3 to 10 (relationships, ADRs, risks, build slices E0 to E16, owner decisions, timings). Start at [backend-plan.md](backend-plan.md); the decision is [ADR 0088](../adr/0088-setups-as-positions-and-rules.md).

## 3. Relationship sketch

```
macro/series (VIX family personal; PUT..CNDR) + rates/treasury + events (FOMC, earnings, dividends)
   |  ingestion market-rollups (nightly + backfill)
   v
market_conditions@v1 (leaf: VIX-family statistics personal; open verdicts, short_premium_allowed,
                   earnings season, FOMC distance, opex, weekday) [P2: conditions_label]
market_triggers@v2 (leaf: post-spike trigger);  regime@v3 and its inputs unchanged
   |  named by field, in one rule language (Rule / Group, evaluate_group; FieldCatalog use sites)
   +--> edge `gate` (a rule, site gate) -> the RegimeGate decision, applied by picks and harnesses (not via screening)
   +--> verdict.toml [slices] (display rows)
   v
edge.toml (setup): schedule, universe, screeners or named symbols, [outcome] position template +
                   entry / exit rule (+ entry, exit and case rules over catalogue fields), gate,
                   [[variants]] / [[variant_grid]], baselines, basis (#967), verdict_profile
   ^ catalogue fields at every level (instrument, market + calendar, event features; P2: fitted scores)
   v  at each decision session D
screeners (presets / user / Python, versioned; own pause_in) -> screener runs (screen_runs,
   rule_screen, rule_screen_values, screen_picks) -> the one pick rule per screener (edge gate off)
   -> setup gate (closed: paused; harness: tagged slice)   [named-symbol setups: no screener]
   v
   v  harness at each D: case values resolved (engines/selection/cases.py); entry condition D -> S
share legs: bars            | option legs: selector (wing_search) + engines/structures (mark, position
                            |   fields, one ordered exit-rule list, assign)
   v                          v
forward_returns@v2 (shares) | outcomes/option/structure_pnl@v2 (one source per S: history < 2026-10-02 <= Cboe)
   (unchanged)                ^ cboe nightly (open)   ^ option_history, owner-run, batch-locked (personal)
   v  harness: cross-section (screened names) | time-series with base delta_equivalent (named sleeves)
the common trade contract (apply_outcome -> TRADE_COLUMNS; price_source bars | cboe | option_history)
   v
evidence (one path, every setup): RoC at its cost levels (notional | collateral), paired excess,
          CVaR + n, block bootstrap, PSR / DSR, benchmarks (named sleeves: the book's slots weighting, Cboe
          tracking; drawdown and episodes read by edge_evidence),
          gate slices (closed = inverse decoy), state slices (display)
   v
verdict (profile: return | tails) -> results/edge_verdict (headline, unchanged grain)
   v  served session
results/edge_picks (picked / paused) + on read: example position, historical exit rule (both kinds)
   v
setup state v1 (read rule): ON / OFF / PAUSED / UNKNOWN -> Setups chip, idea card, Guide
```

---

## 4. Reused vs new

| Piece | Reused as is | Extended | New |
|---|---|---|---|
| Edge document, variants, trial log, `@standard` decoys | yes | keys `gate`, `variant_grid`, `position`, `verdict_profile`, `[outcome.exit]`, option outcome params (parsed in `config/edges/positions/`) | |
| Screeners and screener runs | rule-screen presets (all 92) and user screeners, `results/screen_runs`, `rule_screen`, `rule_screen_values`, `screen_picks`, `picks.long_picks` | a screener is a published rule (2.12, G14); `short_premium_liquidity` ported to a feature group and a rule preset (S5), its Python impl deleted | |
| Book, Base, Schedule, baselines (G16-G19) | `cross_section/portfolio/` (ADR 0074), `BASES`, the schedule vocabularies, `baselines` / `@standard` | the `slots` weighting; book series in the contract (`capital_basis = book`); `delta_equivalent`; calendar columns; `position:<template>` baselines | none (`evidence/book.py` dropped) |
| Picks (G20) | `results/edge_picks`, `picks.long_picks` | `pick_sides`, `pick_weights`, an orientation for shorts; the short example shape | |
| Stores (G24, G25) | the ADR 0084 roots; `option_outcomes.py` | `frame_and_publish` (new, extracted in E4) the one publisher; `edge_trades.licence` reused; the stored `events/earnings.time` (exists); price source `model`; `position_key` from resolved legs | D8, D9 data slices (D7 dropped: `time` exists) |
| Feature levels | instrument and market feature-group entities (`GROUP_TABLE_PREFIXES`) | | the `LEVELS` declaration (E2r); the portfolio provider (P2, E15) |
| Rules (the one entity, G14) | `Rule` / `Group`, `parse_group`, `evaluate_group`, `Criterion` and ADR 0071 groups, expression features | `FieldCatalog` built per use site from the declared levels, with market fields and a licence map (G9-M1); fail-closed rules at the four new sites (G9-M2); the `position.` field head | `config/strategy/levels.py` (`LEVELS`, G15); `engines/selection/cases.py` (case values); `config/edges/positions/fields.py` (`POSITION_FIELDS`) |
| Gate | ADR 0049 `RegimeGate` decision, PAUSED, pick status `paused`, "regime unknown" | a rule over open market and calendar fields, applied by picks and harnesses outside screening; the `gate` key typed in `config/strategy/regime.py` | |
| Market conditions | `regime@v3`, cards, `vix_term` card, trend and drawdown bands, `market_triggers@v1` | `market_triggers@v2` (leaf bump); `features/rollups/market/` split by kind | `market_conditions@v1` (leaf group, share and option setups) |
| Positions | `side` on return outcomes; the `structure` enum of the old option kinds | `config/edges/chain.py` moved to `config/edges/positions/`; `wing_search.py` generalised; `quant/edges/chain_pnl.py` multi-leg | templates `config/site/positions/templates.toml` (share and option legs); `position_of`; `engines/structures/` (absorbs `option_paths.py` marking) |
| Entry and exit rule | `start_offset_sessions`, `horizon_sessions`, `max_drawdown` filter | | `[outcome.exit]` (settings compiled to position rules, plus `when`; options in P1); `[outcome.entry]` (both kinds); case values; position-level features computed by the engine; the ADR 0083 historical exit rule for both kinds (`services/read/evaluation/positions/exit_rule.py`, `[exit_rule]`) |
| Outcomes | `forward_returns@v2` (share trades, unchanged); the `data/outcomes/chain.py` seam | the Cboe writer on the engine; the cutover constant | `structure_pnl@v2` (v1 removed); `tasks/options_history/outcomes.py` |
| Trades | `hit.py::apply_outcome` / `RESULT_COLUMNS`, `results/edge_trades`, `results/edge_paper` | ledger and paper columns from the contract | the common trade contract `TRADE_COLUMNS` (`services/evaluation/evidence/contract.py`) |
| Harnesses | cross-section, time-series, legs, DSR, PBO, random picks, `[edge_costs]` levels; `edge_evidence` page sections (drawdown, episodes, monthly map, cost sensitivity); the book code `cross_section/portfolio/` | option value; gate slices; time-series base `delta_equivalent` with variants (amends 0073); the book's `slots` weighting (G16) | `services/evaluation/evidence/` (every setup; no `book.py`); `quant/edges/tails.py` (in `quant-edge-statistics`) |
| Verdict | the judge, the stored headline, the fingerprint; the `return` criteria | the verdict profile (`return` default, `tails`) | `verdict.toml` sections; `verdict/state.py` |
| Picks | `results/edge_picks`, `pick_edges.py`; the Ideas rule (basis screener) is decided (ADR 0083), not built | the `gate_closed` status, `@named` rows | the example position (both kinds) computed on read |
| Models | ED7 `edge-scorer-fit`, `edge_score_<edge>` expression feature, `no-ml-tables` | judged after `fitted_through` when a rule reads a score (P2) | |
| Licence | ADR 0069 gate, ADR 0084 quarantine | outcome `licence`; trial licence; open regime verdict columns | |
| Data | VIX family, Cboe indexes, dividends 2002, earnings 2018 | FOMC 2002-2023 with `known_from`, bills 2002, vol-shock episodes | COR1M / DSPX / SKEW (P2) |
| Per-name features | `implied_move`, `iv_history`, `iv_term`, `term_ratio_next_30`, `ex_div_before_*`, `earnings_expected`, `momentum.atr_14` | `earnings_reaction@v2`; `vol_stats@v2.hv252` (P2) | history chain features (P2) |
| Dropped from the first design | | | `market_vol@v1`, `options_regime.toml`, `conditions.toml`, `[gate]` / `gate_state` / `stood_aside`, `config/edges/conditions/`, `results/edge_book` (deferred), `results/edge_pick_legs` (unless E9 measures > 0.2 s), per-slice verdict rows; the names `market_options@v1`, "chain source", "structure template", "example contract" (G1, G4, G5, G7); the gate's `{field, require}` form (G10) |

---

## 5. ADRs

Take the next free number right before the push (`make numbering`): **0088** (#968 holds 0087, 0086 is on main).

- **ADR 0088 (new): Setups as positions and rules. Share and option legs, every decision a rule over
  features, one entry and exit rule, one trade contract, the setup gate and setup state.**
  - *Rules.* Every part of a setup that decides something (screener, universe, gate, entry
    condition, exit condition, position parameters and choice) is a rule in the one criteria language
    selections and rule screens share (`Rule` / `Group`, three-valued, one evaluator), over catalogue
    fields at every level (instrument, market, session / calendar, event through its features) and,
    for exits only, position-level fields. One check per use site fixes the levels a rule may name, the
    session it reads, when it may act (a catalogue-field rule observed at a close acts at the next
    close) and its licence. A case value whose rule is UNKNOWN never takes the default. A formula is
    an expression feature, never a rule-level expression. Rule is the one entity: a screener is a
    published rule (instrument scope, a rank and an identity); setup-internal rules are the same
    language and can be promoted. At the gate, entry, case and exit sites the null tests are refused
    and string fields are read over their declared domain, so missing data never opens a gate.
  - *Feature levels.* Each level is declared once (key, provider, point-in-time rule, join path,
    scopes, licence); a new level adds a provider and a join path and never changes the language, the
    evaluator or the checks. A portfolio level describes the setup's own paper book or tonight's list,
    never a user's real holdings (ADR 0083).
  - *Positions.* A setup's position is a site template of legs. Each leg is shares or an option:
    option legs are chosen by our own delta from one session's chain through the one selector, and
    assigned and early-exercised by fixed rules. A share setup is one share leg. Existing stock edges
    map their `side` to it, with no document change.
  - *Entry and exit.* Its entry and exit rule (entry offset, optionally after an entry condition;
    exits by horizon, expiry, take profit, stop loss, DTE and an exit condition, at closes only) is one
    entity for both kinds; the three exit settings are rules over position-level fields, so the engine
    evaluates one ordered list. Position-level fields are declared in one typed list, computed by the
    structure engine at each close from that close's prices and the entry facts, and never stored as
    catalogue features. Share setups evaluate the horizon (and the entry condition) only until a
    path-aware share grain exists.
  - *Outcomes.* Option trades are stored per trade in `outcomes/option/structure_pnl@v2` with a price
    source (one per entry session, by a fixed cutover) and a licence. Share trades stay in
    `forward_returns@v2`. Both satisfy one trade contract (entry and exit session, exit kind, capital
    basis, return on capital by cost level, worst adverse move, price source, licence), and one
    evidence path reads only that contract.
  - *Evidence.* The harness reports for every setup: return on capital (notional for shares,
    collateral for options) at its cost levels, paired with its base (the same position on every
    eligible name, or the delta-equivalent stock for a named option sleeve), CVaR and its tail count,
    a block bootstrap, PSR and DSR. Drawdown, episodes and the monthly map stay with the evidence page
    (`edge_evidence`), read over the contract; a named option sleeve's ladder is the existing book
    (ADR 0074) with a `slots` weighting, plus Cboe tracking. A book's per-session series is a
    contract shape (`capital_basis = book`), so books get the same evidence.
  - *Entities named.* Book (one owner), Base, Schedule (the one reader of event rows), baselines
    including `position:<template>`, and picks with sides and weights (no size shown, ADR 0083).
    Price sources include `model`; `expires_otm` / `hit_target` have no capital basis.
  - *Verdict.* The judge picks its criteria by the setup's profile: `return` (today's, the default
    for share setups, so no stored stock verdict changes) or `tails` (option setups, and share setups
    only through a new version).
  - *Gate.* A setup may name a gate: a rule over open market and calendar fields read at D, decided
    open / closed / unknown by the ADR 0049 regime gate's decision. The picks task and both harnesses apply it outside screening and regardless of `[regime].enabled`,
    and a pick needs both the screener's own `pause_in` and the setup gate open. The market conditions
    are one leaf market group (`market_conditions@v1`), read by share and option setups, beside the
    unchanged `regime@v3`. The harness reports the open, closed and unknown slices (closed = the
    inverse decoy).
  - *Screeners.* Screeners stay the setup's implementations, baselines and decoys, one pick row per
    screener. Named-symbol setups have none.
  - *Read model.* The setup state, the example position (both kinds, with its case values resolved at
    the served session) and the historical exit rule are computed on read.
  - *Models (P2).* A learned scorer's output is a feature rules read (ED7's `edge_score_<edge>`); a
    setup whose rule reads one is judged only after its `fitted_through` plus a horizon; models propose
    and rank, never judge; inputs from `no_ml` tables are refused.
  - *FOMC.* Historical FOMC dates carry, per year, the schedule's announcement date as `known_from`
    (an ADR 0050 decision 3 exception).
  - *Retirements.* `option_model_pnl` and `expires_otm` (and their `structure` enum) are retired only
    after every filed edge is re-filed; v1 is removed now (it is empty).
  - **Amends:**
    - 0053: outcome kinds, the trade contract, measures, the verdict profile; rules over features as
      the setup's parts; a fitted score as a field, judged after `fitted_through`;
    - 0049: the gate as a rule over open market and calendar fields, applied at setup level outside
      screening; the screener's `pause_in` read as the same decision over the label's domain;
    - 0047: market fields may be named in per-name rules at the gate, entry, case and exit sites
      (expressions still cannot combine them);
    - 0069 decision 4 / 0047: the open verdict columns of `market_conditions@v1`;
    - 0073: base `delta_equivalent` for named option sleeves; it lifts decision 1's calendar-schedule,
      `excess_return` and no-variants limits for that base only;
    - 0081: named-symbol picks under the sentinel screener `@named`; the stored status `gate_closed`
      for a closed setup gate; `pick_sides` and `pick_weights`; the example position on read, or a
      table;
    - 0053 (schedules): the opt-in `on_event:earnings_reaction` class, the time known at D;
    - 0064: the ledger and paper columns of the contract, including the per-row `licence`;
    - 0074: the book as the one book entity, with a `slots` weighting and its series in the trade
      contract (`capital_basis = book`);
    - 0075: the `post_spike_contango` and `fomc` triggers;
    - 0050 decision 3: FOMC `known_from`;
    - 0083 decision 3 and 0081 decision 4, only if owner decision 11 chooses (a): short and book
      picks on Ideas (a short's stop UNKNOWN in P1; a book's exit its next rebalance date), lifting
      "long picks only";
    - 0083 decision 3: the historical exit rule over the contract's `max_adverse` for both kinds; an
      option setup publishes its own declared exits, with the percentile stop only when it declares
      none, and no ATR fallback.
- **ADR 0084 amendment: derivations from the bought history (G24).** **One rule for personal
  derived data:** a derived table whose licence can vary by row lives in the main store with a
  `licence` column on every row; a catalogue feature group, whose licence is per feature and cannot
  vary by row, stays in the history root. Two derivations follow it, both by tasks in
  `algotrade_ingestion.tasks.options_history`, both `personal`: (1) `structure_pnl@v2` rows in the
  main store (`price_source = option_history`, `licence = personal`, `knowledge_ts` = the history
  partitions' own), written through the table's one publisher (`frame_and_publish`), one IngestRun
  per session batch under the main lock for that batch only; (2) the chain feature groups for
  sessions before the cutover, on the history root under the same group names, read only through
  the `StoreReader` splice (`data/option_history/splice.py`), importable only by the cross-section
  harness. The amendment extends decision 3's import allowance to exactly these two (the outcome
  derivation and the splice); nothing else reads the history. There is no date rule (G16-M2): a
  trial's licence is the strictest licence of the rows and partitions it actually read (the E1 rule):
  `structure_pnl@v2` rows with `price_source = option_history`, and any partition read through the
  splice. Tests on both sides: a share trial over 2015 stays open; an option trial over 2015 is
  personal. Every row of `results/edge_trades` carries its own `licence` (the column exists).
- **Licence gate (ADR 0084 decision 1's PR; amends 0064, 0083).** An outcome row records its licence;
  a trial's licence includes the strictest licence of the rows it joined; a verdict on personal
  evidence is hidden from, and adds no Ideas picks for, a viewer without that licence.
- **ADR 0065 amendment, on top of PR #967 (owner decision 4).** History-backed paper-derived setups
  use #967's post-publication basis. A gate or threshold chosen in this research (R-A, R-B, the A5
  cut-offs) is judged only on data after the commit that fixes it (the Cboe forward record); its
  history slice is labelled in-sample. Written after #967 merges.
- **ADR 0083 amendment:** only if owner decision 5 chooses Ideas by state (recommended: not now).

---

## 6. Risks specific to this repo

1. **Survivorship in the tail.** v1 drops a window with no exit quote; v2's exit fallback keeps it.
   Property test: a name that stops quoting mid-window is kept and loses.
2. **`knowledge_ts` of history rows** must be the import instant; contract test.
3. **Licence leak.** HOD-derived numbers through a verdict (gate PR), a chart (history features stay
   off the main store), a pick (the example position reads `chains/*` only); VIX-derived states only
   through open stored verdict columns (fitness test on every gate field and slice label).
4. **Missing passing as a value.** A gate unknown pauses (fail closed) and its slice is `unknown`,
   never open or closed; gated vs ungated compared on known sessions only. A report date unknown fails
   the report skip (UNSELECTABLE) for a reporting type, never passes; a non-reporting type (ETF,
   index, closed-end fund) has no report and passes (N3). Missing bills make the cash benchmark UNKNOWN.
5. **Observation dates.** All VIX-family series are `release_lag_days = 1` (`macro.toml`), so mixed
   dates are rare; keep the rule that a ratio is null unless both inputs share the observation date.
6. **Earnings dates in history** are PRIOR_YEAR estimates (ADR 0050); actual dates would be lookahead;
   the "event captured" share is disclosed.
7. **FOMC dates in history:** a declared `known_from`, scheduled meetings only (M3); never the meeting
   day as known ahead without it, never an unscheduled meeting.
8. **Double counting** across sources: one source per S by the cutover constant (H6).
9. **Locks and partial writes.** The history writer holds the main lock per batch publish only, never
   waits on it, starts no batch in the nightly window (a nightly is delayed at most one hourly retry); one IngestRun
   per batch commits or not; a dropped history mount fails the batch (ADR 0084 sentinel).
10. **Universe point in time before the snapshots:** single-name history needs #968 (listing history)
    and, for option-feature screens, F7; until then single-name history evaluation is not run.
11. **Non-determinism:** selector ties, book slot order, bootstrap seeds, grid expansion order:
    property tests under `tests/property`.
12. **Layer violations:** `engines/structures` imports no `data` / `storage`; `features` never imports
    `engines` (the selector lives in `features`); `quant` stays numpy-only; only the splice module in
    `data/option_history` is importable by the harness.
13. **Size:** paths only for `book = true`; single-name structures on their edges' decision sessions;
    E5 measures one year first.
14. **Settlement stand-ins** (SPX AM settlement, Cboe midday roll, Saturday expiries before 2015): the
    PUT replication tolerance is fixed before the run; a miss is reported, not tuned away.
15. **Multiple testing and contamination:** grid points are trials; research-chosen gates are judged
    forward only (H7).
16. **Silent re-judging of stock verdicts (G6).** The new verdict settings change every fingerprint
    once. The `return` profile keeps the criteria; E6b re-stores the headlines and fails if a label or
    one-line result differs. A share setup changes profile only by a new version (a trial).
17. **The exit rule as lookahead or circularity.** The historical stop is computed from the canonical
    run's winners, read by run with `oos_hidden`, and never fed back into an evaluation. An evaluated
    share stop from `fwd_max_drawdown` is refused: the dip's session is unknown, so the fill would be
    a guess (P2: a path grain).
18. **Missing passing as a value, again.** No `atr_14` row, no bar, too few option winners: the stop
    or the example position's part is UNKNOWN with its reason, never 0 and never the share fallback
    on an option position. A share trade's `max_adverse` comes only from stored `fwd_max_drawdown` /
    `fwd_max_return`; null stays null.
19. **Contract drift.** The contract must not change a share edge's `value` or `hit`: golden-edge
    equality in E6a. A leg format lacking a contract column bumps the leg version, never fills a
    default.
20. **Rule lookahead (G9-G12).** A catalogue-field rule observed at close t acting at t (an exit at
    the same close, an entry at the trigger close) uses features computed after that close. Use-site
    check plus a past-session test: entry S >= t + 1; a catalogue-field exit fires at t + 1; only a
    position-only rule acts at t. Position fields read only t's quotes and the entry facts (property
    test: shifting later quotes leaves every earlier field unchanged).
21. **Missing choosing a branch (and G9-M2, G9-M4).** Null tests and out-of-domain labels at the gate,
    entry, case and exit sites are refused or read as missing; a field with no rows over the range is
    refused at run start, never a silent "exit never fires". An UNKNOWN case taking `default`, an UNKNOWN entry condition
    counted as "not triggered" on one side only, an UNKNOWN gate field read as open. Rules: an UNKNOWN
    case is UNSELECTABLE (`CASE_UNKNOWN`); entry UNKNOWN is not TRUE on both picks and base, and its
    count is reported; a gate UNKNOWN pauses. Unit test per site.
22. **A rule as a one-sided filter.** An entry condition or a case applied to the picks and not the
    base inflates lift. The harness applies them to both, per decision-session cohort (2.13); a test
    over a fixture where the rule alone explains the returns gives zero lift.
23. **Trial count.** Every distinct rule, threshold and case is a trial (identity through
    `identity_dict`); rule order is canonicalised so a reordered rule is not a new trial, and the
    trial log counts every rule variant in DSR and PBO.
24. **Fitted-score contamination (P2).** A rule reading `edge_score_<edge>` over sessions before its
    `fitted_through` is in-sample; judged only after it plus a horizon (2.14), fitness test.
25. **Licence by rule.** A personal field in an entry, exit or case rule makes the trial personal (E1);
    a gate field must be open; the example position shows a rule's field values under the viewer's
    licence only.
26. **Portfolio level reading real holdings (G15).** Refused by construction: its provider reads the
    setup's own trades, the paper record and tonight's list only (fitness test); real holdings need an
    ADR (ADR 0083).
27. **Order dependence (G15).** A portfolio rule makes decision sessions depend on earlier ones; the
    harness runs them in order only for such a setup, deterministically.

---

## 7. Build slices

"Review": `architect` for architect areas (new responsibility / folder / table / ADR, point in time,
`quant/` maths, locks, licence), else the implementer's checks.

### Workstream 0: the engine slice (prerequisite)

| id | slice | owner (files) | skill | acceptance | needs | review |
|---|---|---|---|---|---|---|
| E0 | ADR 0088 + amendments (0053, 0049, 0069 d4 / 0047, 0073, 0081, 0064, 0075, 0050 d3, 0083 d3, 0084; 0065 after #967) | `docs/adr/` | `write-adr` | `make numbering`; owner reads | owner decisions 1-9 and 11 (10 at P2) | architect |
| E1 | Licence gate (outcome licence -> trial licence -> verdict hidden, no Ideas picks) | `cross_section/detail/licences.py`, `verdict/`, `pick_edges.py` | extend owners | loader test: a personal-evidence setup absent for a trader | E0 (0084 part) | architect |
| E2 | Position templates (share and option legs) + `position_of` + spec typing + `baselines` accepting `position:<template id>` (G19; parse only) + `variant_grid` / `position` / `[outcome.exit]` / `verdict_profile` keys (`document.py` key lists only, ~12 lines; the `gate` key name too, parsed in E7) + `chain.py` move | `config/edges/positions/*`, `config/site/positions/templates.toml` | `add-responsibility` | every template parses; `position_of` maps every site return edge's `side` (fitness test over the site documents); `position` with `structure` refused; key round trip; yield rule refused; grid deterministic; an option outcome with `start_offset_sessions = 0` refused (G-H1); no site edge fingerprint changes, because `config/edges/identity.py:16` `identity_dict` drops absent new keys (tested); `ExitRuleSettings` typed in `config/edges/positions/exit_rule.py` and the one-line `[exit_rule]` skip in `config/edges/verdict.py`'s loader (its known-sections list, never a field of the hashed `VerdictSettings` class; moved here so E12a and E6b share no Python file, G-M4) | E0 | architect (folder) |
| E2r | **New, split in two (R-1 low): E2r-a** = `LEVELS`, the per-site catalogue, use sites, fail-closed rules, licence map (what E7 needs); **E2r-b** = position fields, case values, exit compilation, identity form (E3b needs both; E2r-b after E2r-a). (G9-G12, G15; resized by G9-M1, G9-M2.) The `LEVELS` declaration (`config/strategy/levels.py`, today's four rows, 2.15); `FieldCatalog` built per use site from `LEVELS[*].scopes`, with the market groups (`GROUPS` with `entity == "market"`) at `gate` / `entry` / `case` / `exit` and a licence map from `Feature.licence` (expressions inherit); the fail-closed rules of those sites (null tests refused, string fields over a declared domain, out-of-domain read as missing); `FieldCatalog.check(group, path, site)` (today's call unchanged as the `screener` / `universe` site); the `position.` field head in `core/model/fields.py`; `POSITION_FIELDS` in `config/edges/positions/fields.py`; parsing of `gate`, `[outcome.entry]` (`when`, `within_sessions`), `[outcome.exit] when` and case values (`config/edges/positions/cases.py`), with the three exit settings compiled to position rules; `engines/selection/cases.py::resolve_case` (pure); the canonical rule form in `identity_dict`; Guide entries for every position field; `engines/selection/cases.py` in `three-valued-predicate`'s `allowed` (later callers add theirs) | `config/strategy/catalog.py`, `config/strategy/levels.py`, `services/configs.py` (`catalog_of`), `core/model/fields.py`, `config/edges/positions/{fields,cases}.py`, `engines/selection/cases.py`, `config/edges/identity.py`, `architecture/core_ownership.toml`, `config/site/guide/` | `add-responsibility` (new: `rule-use-sites` on `catalog.py`, which has no entry today; `position-fields`; `case-values`), `add-guide-content` | per site: a disallowed level refused, `position.*` outside `exit` refused, a personal gate field refused, an unknown field refused, `market.*` still refused at `screener` / `universe`; `is_null` / `not_null` refused at the four new sites; `ne` / `not_in` on an out-of-domain label is UNKNOWN; `ne` / `not_in` on a string field without a domain refused (`eq` / `in` allowed); `LEVELS` names its computed providers by string, and an import-linter check keeps `config/` from importing `engines/` or `services/`; a fixture level declared only in a test is readable by a gate rule with no other change (G15); a case UNKNOWN before a TRUE one gives `CASE_UNKNOWN`, all FALSE gives `default`; `position` cases across kinds refused; a reordered `Group` has one identity; no site edge fingerprint changes; guide coverage test | E2 | architect (point in time, new responsibilities) |
| E3a | Selector generalised; engine marking, expiry, intrinsic, exit fallback, hedge, one- and two-leg; `option_paths.py` marking moved | `features/rollups/options/wing_search.py`, `engines/structures/*`, `quant/edges/chain_pnl.py` | `add-responsibility` | `put_wing` / `call_wing` unchanged on fixtures; delisting kept; determinism property test | E2 | architect (quant) |
| E3b | (resized by G11, G12) Exits of 2.4a as one ordered rule list (the three settings compiled, plus `when`), the position-level fields computed per close, the act-at rule (catalogue-field rules at t + 1, position-only at t), assignment, early exercise, report skip, `max_adverse` | `engines/structures/*` | | ex-date assignment test; take profit and stop loss at closes only, first exit in declared order wins; a catalogue-field exit fires at t + 1, a position-only one at t; an UNKNOWN rule never fires; every `POSITION_FIELDS` entry hand-computed on a fixture; later quotes shifted leave earlier fields unchanged (property); report skip on a stock fixture and passes on an ETF fixture (N3); `max_adverse` hand-computed on a fixture | E3a, E2r | architect |
| E4 | `structure_pnl@v2` with `position_key` built from the resolved legs, never the template id (G24); `frame_and_publish` (new: extracted from `compute_option_outcomes` / `_one`) the one publisher of the table (G24); Cboe writer on the engine, reading the catalogue fields an exit rule names per close of the window and writing the union of each setup's case points; reader with the cutover; `hit.py::_chain_pnl` and `check_chain` on v2; v1 removed | `tasks/derived/option_outcomes.py`, `storage/tables/schemas/outcomes.py`, `data/outcomes/chain.py`, `cross_section/hit.py` | `add-dataset` | storage contract test; `option-outcomes` acceptance on stored chains; cutover contract test; two exit rules give two `position_key`s; a field read per close comes from that session's partition only; a row's `licence` is the strictest of its price source and exit-rule fields; for an edge with `[outcome.entry]`, every S of the wait is written (G9-M3); an exit rule over a field with no rows in range refused, and each row stores `exit_unknown_closes` (a count; the harness classes UNMEASURED from `verdict.toml`, R-1); the per-close field read measured (estimated vs measured, §10) | E3b | architect (table) |
| E5 | (resized by G9-M3, G9-M4, G24, G25) History writer, computing frames and calling E4's `frame_and_publish` (no second writer); needs D8 and the 2002-2009 bars, bills and dividends on this store (coverage check at start); reads the exit rule's catalogue fields per close; writes every S of an entry condition's wait; `writes()` exemption, each batch computed with no IngestRun open, then its IngestRun opened, written and committed entirely under the main lock (N7), main lock per publish with `wait=False` and retry, `recover_unpublished` first, no batch in the nightly window; one year measured; PUT replication through the engine | `tasks/options_history/outcomes.py`, `cli/main.py` | `add-dataset` | tests: no batch holds the lock across two publishes, none starts in the nightly window; every S of a wait written; a rule over a field with no history rows refused at start, never run as "never fires"; replication within tolerance; PR states estimated vs measured | E4, E1, D1, D5 | architect (locks, PIT) |
| E6a | The common trade contract: `TRADE_COLUMNS` in `services/evaluation/evidence/contract.py` (new folder, responsibility `trade-evidence`); every shape maps to it (G16, G22): the book series with `capital_basis = book`, `expires_otm` / `hit_target` with `none` and null `return_on_capital`, `option_model_pnl` with price source `model`; `results/edge_trades`'s existing `licence` columns reused (G24, corrected); the book series feeds the evidence only, never `edge_trades` rows; `apply_outcome`'s return and `option_pnl` branches and the time-series valuation emit it; `results/edge_trades` and `results/edge_paper` gain the contract's columns | `services/evaluation/evidence/contract.py`, `cross_section/hit.py`, `cross_section/detail/trades.py`, `forward/results.py`, `forward/settle.py` (it reads `fwd_return`, :133), `time_series/evaluate.py`, `storage/tables/edge_schemas.py` | `add-responsibility` | golden edges: every `value`, `hit` and `edge_eval` row equal before and after; a share and an option fixture give the same contract columns; older ledger rows read as null; leg version bumped only if a column is missing (stated) | E4, E1 (verdict folder) | architect (schema, contract) |
| E6b | The judge's inputs for every setup: `tails.py` (CVaR + n, worst window), block bootstrap, PSR, `excess_roc`, option values, option cost levels in the existing cost rows, measures plumbing (`measures.py`, `results.py`); no drawdown, episode or monthly measures (they stay in `edge_evidence`, G-M5); the verdict profile (`return` for every kind but `option_pnl`, `tails`); headlines re-stored in this slice's deploy | `services/evaluation/evidence/*`, `quant/edges/tails.py`, `cross_section/measures.py`, `results.py`, `verdict/criteria.py`, `verdict/fingerprint.py` (`JUDGED_CODE`), `config/edges/verdict.py` (the `[tails_verdict]`, `[option_costs]`, `[option_quotes]` fields of `VerdictSettings`; after E2), `verdict.toml` | extend owners | hand-computed fixtures for CVaR / bootstrap; a `return` judge call gives the same headline before and after; fitness test: every site document's profile is `return` unless its kind is `option_pnl` (the 7 `expires_otm` / `option_model_pnl` edges included); after the edge-verdicts task, run in the deploy, every re-stored label and one-line result equals the stored one; golden edge in `make evaluate` | E6a | architect (quant, verdict) |
| E7 | (resized by G10) Setup gate as a rule: `gate` parsed by `parse_group` and checked at site `gate` in `config/strategy/regime.py`; the decision a pure function of `evaluate_group` over the session's market row (`session_market` reads every field the rule names); `pause_in` read as the same decision; harness screens with the edge gate off and tags open / closed / unknown; picks and time-series apply it regardless of `[regime].enabled`; composition with `pause_in` | `config/strategy/regime.py`, `engines/screening/gate.py`, `services/screening/regime.py`, `cross_section/measuring.py`, `reads/session.py`, `time_series/*` | extend `run-overlays` | a two-rule gate (contango AND `sessions_to_fomc gt 2`) decides open / closed / unknown on fixtures; null `sessions_to_fomc` is unknown; the label `"FOO"` is unknown for the ADR 0049 pause and for an edge gate (G9-M2); `engines/screening/gate.py` added to `three-valued-predicate`'s `allowed`; every existing screener's ADR 0049 pause gives the same PAUSED rows before and after; closed slice equals the inverse-gate edge; unknown excluded on both sides; gate applied with `[regime]` off; a screener-paused row is not a closed edge gate | E6b, F1, E2r | architect (PIT) |
| E8a | Time-series base `delta_equivalent`: option value, variants and gates allowed for it | `time_series/*`, `config/edges/named.py` | extend owners | a named SPY sleeve with a 2-point grid evaluates; `named.py` still refuses variants for `out_of_window` | E7 | architect |
| E8b | (changed by G16) Named option sleeves: `weighting = "slots"` added to the existing book code (fixed collateral slots, no leverage, its drawdown and worst month) and Cboe index tracking; benchmarks; no `evidence/book.py` | `cross_section/portfolio/weights.py` (+ `session.py`), `services/evaluation/evidence/benchmarks.py`, `config/edges/portfolio.py` (`slots`) | extend `edge-evaluation` | SPY 30-delta sleeve vs PUT tracking reported; an existing allocation edge's series unchanged (golden); one book owner (`make ownership`); no share setup gets a second drawdown | E8a | architect |
| E9 | Storage first (G-M1, G20): `results/edge_picks` gains `pick_sides` and `pick_weights` (a short ranked by its own score ascending; a book's weights) and the stored status `gate_closed` (`edge_picks/night.py` `STATUSES`, mapped to the `paused` read code in `pick_edges.py`) and the sentinel screener `@named` for named-symbol rows (`edge_schemas.py` key comment, ADR 0081 amendment). A book's picks are replayed from the paper record (its `hold_rank` / `vol_target` state depends on earlier holdings). Then named-symbol picks through the setup gate and the example position on read for both kinds (case values resolved at the served session by `resolve_case`; an UNKNOWN case shown UNKNOWN with its reason) (shares: reference close, stop price, exit date; options: legs, credit, collateral, declared exits), measured | `tasks/edges/picks.py`, `edge_picks/*`, `pick_edges.py`, `storage/tables/edge_schemas.py`, `services/read/evaluation/positions/example.py` | `add-domain-object` | picks acceptance check; a short, a long-short and a book edge leave `unjudged` with sides and weights stored (shown per owner decision 11); a book's picks replay the book from the paper record (`hold_rank`, `vol_target` depend on earlier holdings), tested on one allocation edge; a case value resolved at the served session matches the harness's at the same D; a closed gate stores `gate_closed` and reads `paused` with the gate's reason, a screener-paused name stays apart; a named setup writes `@named` rows; a share and an option pick each give their shape; UNKNOWN parts with reasons; read time measured (table only if > 0.2 s) | E3a, E7, E1, E12a, E2r | architect (schema) |
| E10 | Setup state rule + GraphQL fields (state, example position, exit rule) + Guide entries (positions, templates, exit kinds, profiles, screeners vs setups) | `verdict/state.py`, `graphql/types/evaluation/` | `add-graphql-field`, `add-guide-content` | loader test over the four states; schema snapshot; guide coverage test | E6b, E9 | review own |
| E11 | Ledger option columns; `edge_evidence` (owner `edge-evidence-read`) extended to read the contract's `return_on_capital` series for its existing drawdown, episodes (plus the vol shocks, the Cboe index and the Reg-T flag for options), monthly map and cost sensitivity | `cross_section/detail/trades.py`, `services/read/edge_evidence/*` | `add-domain-object` | ledger CSV test; a share setup's page unchanged on a golden edge; an option setup's sections on collateral | E6b, E8b | review own |
| E12a | The historical exit rule for share setups (ADR 0083 d3): the 80th percentile of `edge_trades.max_drawdown` (the `max_adverse` alias) over the basis's winners, 2 x ATR(14) fallback, hold = `basis_horizon`, long picks only; `[exit_rule]` values in `verdict.toml`; responsibility `pick-positions`; the trader-site track's exit-rule slice (one PR) | `services/read/evaluation/positions/exit_rule.py`, `verdict.toml` (`[exit_rule]` appended) | `add-domain-object`, `add-responsibility` | stop equals a hand-computed 80th percentile on a ledger fixture; fallback below `min_winners`; `oos_hidden` respected; a past-session test: only the canonical run with `range_to <= S` and trades with `exit_session <= S`; rows from before E6a read through the alias; a missing `atr_14` is UNKNOWN; fitness: `[exit_rule]` not in `settings_hash` | E2 (folder, settings), T-basis | architect (new responsibility, PIT) |
| E12b | The exit rule for option setups (decision 8): the declared `[outcome.exit]` rule published; the percentile over v2 `max_adverse` only without a declared stop; UNKNOWN below `min_winners`; hold = the earlier of expiry and the cap | `services/read/evaluation/positions/exit_rule.py`, `example.py` | extend `pick-positions` | a declared stop is published as is; the percentile only without one; UNKNOWN with too few winners | E3b, E6a, E9, E12a | architect (PIT) |
| E13 | **New slice (G11).** Rule-driven entry and parameters in both harnesses: the entry condition maps each (name, D) to S over the existing per-S rows (`forward_returns@v2`, `structure_pnl@v2`), `NOT_TRIGGERED` counted; case values resolved at D; both applied to picks and base, cohort = D | `cross_section/measuring.py`, `cross_section/hit.py`, `time_series/*` | extend owners | a past-session test (S >= t + 1, fields from t's partition only); an entry condition on `option_pnl` refused until E4 / E5 write the wait's sessions (G9-M3); a rule over a field with no rows in the range refused at run start (G9-M4); a fixture where the rule alone explains the returns gives zero lift (risk 22); UNKNOWN counts reported; determinism property test; the extra per-D reads measured (estimated vs measured, §10) | E7, E6a, E2r | architect (PIT) |
| E14 | **New slice, P2 (G13).** Rules reading a fitted score: the `fitted_through` + horizon bound (earlier sessions an `in_sample` slice), fitness test over the site documents, licence inherited | `cross_section/measuring.py`; `services/evaluation/training/*` read only | extend owners | a rule over `edge_score_<edge>` is judged only after `fitted_through` + horizon; the in-sample slice shown | E13, a fitted scorer, decision 10 | architect (PIT) |
| E15 | **New slice, P2 (G15).** The portfolio provider: `PORTFOLIO_FIELDS` and a `LEVELS` row; computed from the setup's own trades (harness) and the paper record plus tonight's ranked list (picks); in-order decision sessions for a setup that reads `portfolio.*` | `config/strategy/levels.py`, `services/evaluation/cross_section/` (a new module, folder cap checked by `make layout` first), `tasks/edges/picks.py` | `add-responsibility` (`portfolio-features`) | only trades with `entry_session <= D < exit_session`; no read of any user store or another setup's picks (fitness test); in-order evaluation deterministic (property); leg reuse (ADR 0063, `legs/key.py`) keys on the book state or is bypassed for such setups; a portfolio field over history-priced trades is personal, so a portfolio gate is not evaluable on the history range (as VIX-family values); no rule, evaluator or check file changed by the slice (G15 acceptance) | E13, E6a, E9 | architect (PIT, new responsibility) |
| E16 | **New slice (G19).** Position baselines: the harness values the setup's own picks with `position:<template>` and stores a baseline row beside the decoys | `cross_section/measuring.py`, `cross_section/results.py` | extend `edge-evaluation` | A3 against `position:long_shares` on a fixture; the baseline is not a trial (DSR count unchanged) | E6a, E4, E2 | architect |
| T-basis | (trader-site track, not this design) `results/edge_verdict` gains `basis_screener`, `basis_horizon` with a `JUDGE_VERSION` bump (ADR 0083 decision 2), re-stored in its deploy | `verdict/`, `edge_schemas.py` | | its own | its own | architect |

### Workstream 1: data sources

| id | slice | owner | skill | acceptance | needs |
|---|---|---|---|---|---|
| D1 | `rates/treasury` back to 2002 from the Treasury source (the rates task; not part of the Tiingo session, whose job is `bars-history --since 2002-01-01`) | rates task | `add-data-source` if code | curve stored on 2002-01-02 | none |
| D7 | (dropped by G16-M1: `events/earnings.time` already exists) | | | | |
| D8 | (G25) 2002-2009 prerequisites on this store: bars from the running Tiingo `bars-history --since 2002-01-01` session (reference, not redone), bills from D1 (Treasury source); `events/dividend` from #974 (check it ran here); then `run outcomes` and `residual_returns` for 2002-2009 (about 8.5 GB [I], detached per README "Long runs") | owner action; existing tasks | none | coverage check: bars, `forward_returns@v2`, `rates/treasury` and `events/dividend` on 2002-01-02 | the Tiingo session, #974 |
| D9 | (G25) Cboe chain growth check: 97 MB a session [M], about 24 GB a year [I]; review columns, sort and `cluster_by` of `chains/option_quotes` before a year accrues | `tasks/market/option_chains.py`, `storage/tables/schemas/` | | bytes a session measured before and after ("estimated X, measured Y") | none |
| D2 | Scheduled FOMC dates 2002-2023 with declared `known_from` per year | `config/site/events/releases.toml`, `tasks/macro/calendar.py` (`known_from` override) | config + small code | fitness: 8 scheduled a year, unscheduled excluded, `known_from` <= the year's first meeting | E0 (0050 d3 exception) |
| D3 | Episodes `aug_2015`, `volmageddon_2018`, `yen_carry_2024` + Guide entries | `config/site/regime/episodes.toml` | `add-guide-content` | guide coverage test | none |
| D4 | COR1M, COR3M, DSPX, SKEW series (P2) | `macro-ingestion` | `add-data-source` | recorded-CSV parser test | none |
| D5 | The option history import (owner action, ADR 0084 runbook) | owner | | per-session acceptance | purchase |
| D6 | PR #968 survivorship-free listing history (in flight elsewhere) | | | merged | |

### Workstream 2: features

| id | slice | owner | skill | acceptance | needs |
|---|---|---|---|---|---|
| F0 | Split `features/rollups/market/` by kind: subfolder `market/edges/` with `triggers.py` moved (no group version change) | `architecture/layout.toml`, `features/rollups/market/edges/` | `add-responsibility` (layout) | `make layout`, `make arch`, `make ownership`; triggers tests unchanged | none | architect (folder) |
| F1 | Leaf group `market_conditions@v1` (its own `tables.toml` entry, G24; calendar columns `last_before_weekend` and `fomc_cycle_week` too, G18): VIX-family statistics (personal), open verdict columns, `short_premium_allowed`, `y10_chg_63d`, `earnings_season_share`, `sessions_to_fomc`, `in_opex_week`, `weekday`; reuses `observations` and the `Card` / `compare` helpers | `features/rollups/market/edges/conditions.py` | `add-feature` | per-column tests incl. the same-date rule, nulls before series start, open licence asserted on verdict columns; `regime@v3` fingerprint unchanged | F0; D1 and D2 for their columns (null until then) |
| F2 | Guide entries for every `market_conditions@v1` verdict column; Regime-page cards (`cards.toml` reading the leaf group) only if owner decision 2 asks | `config/site/guide/`, optionally `config/site/regime/cards.toml` | `add-guide-content` | guide coverage test | F1 |
| F3 | `market_triggers@v2` (leaf): `post_spike_contango` (+ `fomc` later); `MARKET_TRIGGERS` | `market/edges/triggers.py`, `config/edges/schedules/markets.py` | `add-feature` | synthetic VIX path; stale = null | F0 |
| F4 | `earnings_reaction@v2` past moves + `earnings_move_*` in `earnings.toml` | `corporate/earnings_reaction.py` | `add-feature` | statistic uses only closed windows by S | none |
| F5 | (merged into F1: `earnings_season_share` lives in the leaf group, so `market_breadth` is not bumped) | | | | |
| F6 | `vol_stats@v2.hv252` (P2) | `activity/vol_stats.py` | `add-feature` | unit test | none |
| F7 | History chain features + `StoreReader` splice (P2) | `tasks/options_history/features.py`, `data/option_history/splice.py` | `add-feature`, `add-responsibility` | same compute on a Cboe day and its HOD day agree; import contract; licence recorded; recorded partitions | E1, E4 (cutover), D5, D6 |
| F8 | `realised_corr_ratio_21` (P2) | `breadth.py` or `cross_asset.py` | `add-feature` | unit test | none |
| F9 | `market_conditions@v2.conditions_label` R1-R12 (P2; a leaf bump only) | `market/edges/conditions.py` | `add-feature` | each label on fixture rows | F1 |
| F10 | (G21, G16-M1) An opt-in event class `on_event:earnings_reaction` anchored at the reaction session from `events/earnings.time` as known at D; existing classes unchanged | `config/edges/schedules/events.py` (+ `earnings_expected` only if the schedule needs the time as a feature) | extend `edge-documents` | pre-market and after-hours fixtures give the right reaction session; unknown skipped and counted; an 8-K `intraday` time known after D is never used; golden test: the 10 `on_event:earnings*` edges keep their windows, run hashes and verdicts | none |

### Workstream 3: screeners (reuse first)

| id | slice | owner | skill | needs |
|---|---|---|---|---|
| S1 | None for named sleeves (A1, A2, A3 on ETFs): the named symbols are the picks (E9) | | | E9 |
| S2 | B2: reuse `low_volatility` (puts) and `ivol_high` (calls); add `total_vol_high` only if the run shows the sort differs | presets | `add-screener` | none |
| S3 | `earnings_move_rich` (S&P 500, put / call tier A-B, ratio >= 1.3); `earnings_move_cheap` (P2, attention exclusion) | presets | `add-screener` | F4 |
| S4 | B4 characteristic sorts (P2) | presets | `add-screener` | F6, F7 |
| S5 | (G14) Port `short_premium_liquidity` from Python to a feature group plus a rule preset with the same id; `legacy_liquidity_csv` and the `algotrade-ingest screen --config` default read the preset's run; delete `strategies/screeners/short_premium_liquidity.py` and its registry entry; acceptance: the rule run's picked names equal the Python run's on recorded sessions | `features/rollups/options/` (the group), `config/site/presets/`, `strategies/screeners/registry.py`, `services/screening/exports.py` | `add-feature`, `add-screener` | none (architect review: the export's consumers) |

Single-name covered calls need no new screener: the report skip is in the position's selection.
Screeners as explicit entities (G8) need no code: the entities, the pick rule and the tables exist
(2.12); E9 adds the named-symbol rows and E10 the Guide words.

### Workstream 4: edges

| id | edge | needs |
|---|---|---|
| X1 | New `index_put_write` (A1 + A2 + A5 + R-A + R-B), named SPY / QQQ / IWM, base `delta_equivalent`, gate the rule `short_premium_allowed eq true` (variant: AND `sessions_to_fomc gt 2`), grid delta x tenor x take-profit | E8a, E8b, E9, F1, F3, E5 for history; decisions 3, 4, 6 |
| X2 | Re-file `vrp_short_premium` to `option_pnl short_put` (new version), gate, `iv_rank_high` as a second screener; drop `realised_below_implied` | E6b, E7; history single names after F7, D6 |
| X3 | New `covered_call_strike_tenor` (A3 + C4 via `skip_report_in_life`): named ETFs first, then `liquid_optionable_floored`; a tenor case variant (30 when IV rank is high, else 45); baseline `position:long_shares` | E8a, E3b, E13, E16; single names after D6 |
| X4 | New `high_vol_call_write`, `low_vol_put_write` (B2), each the other's baseline | E6b, S2, D6 |
| X5 | Re-file c17 as the conditional earnings sell (C2), `short_straddle` + `iron_fly`, gate on `regime@v3.label`, from 2018, entered across the report by the reaction-session anchor | E6b, E7, F4, S3, F7, D6, F10 |
| X6 | Re-file c12, c13, c14, c16; retire c18 (P2) | E6b, F6, F7 |
| X7 | The wheel book (P2) | E8b |
| X8 | Guide: setups, positions and templates, entry and exit rules, states, "why nothing is on today", "why we do not publish put-buying setups", the bootstrap caveat | E10 |
| X9 | Optional (owner decision 7): a share setup re-filed as a new version with `verdict_profile = "tails"`, judged beside its `return` version | E6b; decision 7 |

### Dependency map and parallel start

```
E0 ─┬─ E1 ──────────────────────────────────────────────┐ (before E6a, E9; with D1, D5 before E5)
    └─ E2 ─┬─ E3a ─ E3b ─ E4 ─┬─ E5 (E1, D1, D5)         │
           ├─ E2r ─ (before E3b, E7, E9, E13; beside E3a)
           │                  └─ E6a ─ E6b ─ E7 ─ E8a ─ E8b ─ X1 (also E9, E5 for history)
           │   F0 ─┬─ F1 ──────────────────┘
           │       │    └─ F2, F9 (P2)
           │       └─ F3
           └─ E12a (+ T-basis, trader-site track) ─┐
                         E7 + E3a + E1 + E12a ─ E9 ─┬─ E10 ─ X8
                         E3b + E6a + E9 ─ E12b      │
                         E6b + E8b ─ E11;   E6b ─ X9 (decision 7)
                         E7 + E6a + E2r ─ E13 ─ X3 (case variant);  E13 ─ E14 (P2, decision 10)
                         E13 + E9 ─ E15 (P2, portfolio level);  S5 any time (screeners only)
                         E6a + E4 + E2 ─ E16 (position baselines) ─ X3 (A3 vs the stock)
Tiingo `bars-history` session (bars to 2002) + D1 (bills) + #974 ─ D8 ─ E5;   F10 ─ X5 (C2);   D9 now
F4, D2, D3, D4, F6, F8 : start any time;  F4 ─ S3 ─ X5;  D6 + F7 ─ X2, X5 (history)
```

**Start together (file-disjoint):** after E0, these start together: E1, E2, D1, D2, D3, F0, F4.
Their files:
- E1: `verdict/` and `pick_edges.py`;
- E2: `config/edges/positions/`, `config/site/positions/` and the one-line `[exit_rule]` skip in
  `config/edges/verdict.py`'s loader (not in `VerdictSettings`);
- F0: the `features/rollups/market/` layout and `triggers.py`;
- F4: `earnings_reaction.py`;
- D2: `releases.toml` and `calendar.py`;
- D3: `episodes.toml`.

After E2, E2r (`config/strategy/catalog.py`, `core/model/fields.py`, `config/edges/positions/{fields,cases}.py`,
`engines/selection/cases.py`, `config/edges/identity.py`) and E3a (`wing_search.py`, `engines/structures/`,
`quant/edges/chain_pnl.py`) run in parallel.

After F0, F1 (`market/edges/conditions.py`) and F3 (`market/edges/triggers.py`) run in parallel. The
engine path E0 -> E4 does not depend on F0-F3. E12a waits only on E2 and T-basis, never on the
option engine (G-M3).

**Sequenced for shared files:**
- E1 -> E6a -> E6b -> E10, all in `verdict/` (E6a only adds the contract and the ledger columns; the
  profile is E6b's);
- E1 -> E9 (`pick_edges.py`);
- E4 -> E6a (`cross_section/hit.py`);
- E6b -> E7 (`measures.py`, `results.py`);
- E12a -> E9 -> E12b (the `positions/` folder);
- E12a and E6b both append to `config/site/verdict.toml` and share no other file (E2 took the
  `verdict.py` line): if both are open, E12a merges first and E6b runs `scripts/merge_main.sh`
  (G-M4);
- T-basis overlaps E1 and E6b (`verdict/`) and E9 (`edge_schemas.py`, `pick_edges.py`). Merge order
  E1 -> T-basis -> E6b, and T-basis -> E12a -> E9. A PR opened before its predecessor lands is
  labelled `no-automerge` until that predecessor merges; then it runs `scripts/merge_main.sh` and
  drops the label (R3);
- T-basis and E6b each shift every fingerprint once and each re-stores the headlines in its own
  deploy. They are never merged on the same night, so no night serves a mixed set (ADR 0083's Ideas
  drops a setup whose fingerprint differs);
- E4 -> E5 (`frame_and_publish`, the one publisher); D8 before E5's history run;
- E6a -> E16 (`cross_section/results.py`), and E7 -> E13 -> E16 if open together (`measuring.py`);
- E2 -> E2r (`config/edges/positions/`); E2r before E3b (the exit rule list), E7 (the `gate` site) and
  E9 (`resolve_case`);
- E4 -> E6a -> E13 (`cross_section/hit.py`) and E7 -> E13 (`cross_section/measuring.py`);
- F0 before F1 and F3 (the folder they live in);
- E7 after F1 (a real gate field to test with; a fixture field is enough to start).

**Critical path:** E0 -> E2 -> E3a (E2r beside it) -> E3b -> E4 -> E6a -> E6b -> E7 -> E8a -> E8b ->
X1 (picks after E9, which needs E12a and E2r). E13 (rule-driven entry and parameters) is off the
critical path for X1, whose P1 rules are its gate and its declared exits; X3's case variant waits on it. E1 -> E5 joins before X1's history run, with D1 and D5 before E5. The share
exit rule (E2 -> E12a) is off it.

---

## 8. Research ranking to site edges: re-file or create

| Research item (rank) | Site edge today | Action |
|---|---|---|
| A1 put-write 16-30 delta, + A2 weekly (P1) | none (idea c19) | **Create** `index_put_write` (named SPY, QQQ, IWM; SPX for the PUT check) |
| A5 VIX-curve / ex-ante VRP filter (P1) | the ADR 0049 gate pauses short vol in STRESS / CRISIS; `vix_roll_yield` is a VIX-ETP book | **Gate variants** (`vix_contango_on`, `index_vrp_rich_on`) of X1 and X2; not an edge |
| R-A stand-aside (P1) | none as a published rule | **The main gate** of X1 / X2 (`market_conditions@v1.short_premium_allowed`); evidence = the gate slices (forward-judged, decision 4); Guide entry |
| R-B post-spike re-entry (P1) | `vix_mean_reversion_entry` (SPY stock return after a spike; unchanged) | **Gate variant** `post_spike` of X1 with episode rows; trigger reused |
| A3 covered calls skipping earnings (P1) | none | **Create** `covered_call_strike_tenor` |
| B2 calls on high-vol, puts on low-vol (P1) | none | **Create** two edges, each the other's decoy |
| C2 conditional earnings sell (P1) | `c17_earnings_iv_crush_sell` (blocked) | **Re-file** c17 (new version) |
| C1 conditional buy (P2) | `c16_pre_earnings_straddle_buy` (blocked) | **Re-file** (P2) |
| single-name VRP flagship | `vrp_short_premium` (`expires_otm`) | **Re-file** to `option_pnl short_put` (new version) |
| B1 / B3 / B4 (P2) | c12, c13 (blocked), c14 | **Re-file** to `option_pnl` (c13 unblocked by F7) |
| G2 IV rank (P2) | `c18_iv_rank_conditional_selling` | **Retire**; `iv_rank_high` becomes a screener of X2 / X3 |
| VIX ETP roll | `vix_roll_yield` | Unchanged; sliced by the state labels automatically |

---

## 9. Owner decisions

### Owner answers (2026-11-01, in chat; these are final)

1. **Owner-only for now.** History-derived evidence is shown only to the owner until HOD's terms on
   derived statistics are read; the Cboe forward record and example positions stay open.
2. **Per-setup gates (owner's own framing, replaces the site-wide verdict question).** "Each setup can
   use different market features and decide if they want the gate to be switched on or off." So: no
   one site-wide `short_premium_allowed` verdict that every setup shares; each setup declares its own
   gate as a rule over the market features it chooses, and declares whether that gate is on (the
   gated / ungated pair stays a variant where a setup wants both judged). `market_conditions@v1`
   stores the inputs and `_on` states as catalogue features a gate may name; nothing is shared by
   default. Licence (my reading, flagged to the owner): a gate's fields count toward the setup's
   licence under answer 9 (the strictest field any of its rules read, gate included), which replaces
   H1's "gate open-only" rule. No Regime-page cards until the options setups have verdicts.
3. **(a)** New base `delta_equivalent` for named option sleeves, with variants and gates allowed for
   that base only.
4. **(a), with a minimum.** #967's post-publication basis for paper-derived structures; any gate or
   threshold chosen in this research is judged only on data the research did not see, and **no verdict
   is given until that holdout holds at least 3 months** (from the Cboe start 2026-10-02, the earliest
   is 2027-01-04; the verdict's own minimum-trade rules still apply on top). Open question to the
   owner: start the holdout earlier with the bought history for months the research did not read.
5. **(a)** Defer: Ideas stays as ADR 0083 says; the setup state is a chip.
6. **Gated** (recommended): A1 published gated by R-A, the ungated version a variant.
7. **(a)** The `tails` profile opt-in per setup by a new version; stored share verdicts stay.
8. **(d)** Publish the setup's own evaluated exit rule; the 80th-percentile rule only for a setup that
   declares no stop.
9. **(a)** A rule's licence is its strictest field; the trial is personal; such a setup is hidden from,
   and adds no Ideas picks for, a viewer without that licence.
10. **As recommended:** (b) owner-only until one scored setup has a forward record, then (a) (decide
    again at E14).
11. **(a)** Short picks shown as "short" (borrow assumed, stop UNKNOWN in P1); books in rank order with
    the next rebalance date as the exit; no weights or sizes. Amends ADR 0083 d3 and ADR 0081 d4.

### The questions as put to the owner

Policy (owner):
1. **History-derived evidence owner-only until you have read HOD's terms on derived statistics?**
   Recommend yes (ADR 0084 decision 1); the Cboe forward record and example positions stay open.
2. **The `market_conditions@v1` verdict columns (the `_on` states, `short_premium_allowed`, later the
   R1-R12 label) open as "our own aggregate", like `regime@v3`, though built from personal VIX inputs;
   and do they appear as cards on the Regime page?** Options: (a) open stored columns (amends ADR
   0069 d4 / 0047); (b) keep personal, so traders see "Paused" without the condition's state.
   Recommend (a), and no Regime-page cards until the options setups have verdicts (the Guide entries
   ship either way).
3. **Lift ADR 0073's limits for named option sleeves?** Options: (a) a new base `delta_equivalent`
   with variants and gates allowed for it only; (b) single-variant time-series edges, one edge per
   grid point. Recommend (a).
4. **Basis and holdout for history-backed setups.** Options: (a) PR #967's post-publication basis for
   paper-derived structures, plus a forward-only (Cboe) holdout for any gate or threshold chosen in
   this research; (b) a 2019-01-02 frozen period with the contamination disclosed. Recommend (a).
5. **Ideas by setup state?** Options: (a) defer: Ideas stays as ADR 0083 says, the state is a chip;
   (b) Ideas lists ON setups with an ADR 0083 amendment. Recommend (a).
6. **What A1 publishes:** gated by R-A (unconditional as a variant), or unconditional (gated as
   variants)? Recommend gated.
7. **Do share setups take the new tail-based verdict criteria (G6)?** The CVaR ratio, PSR and the
   block-bootstrap t would apply on top of today's criteria.
   - (a) Opt-in per setup by a new version (`verdict_profile = "tails"`, a new trial); every stored
     stock verdict stays as judged.
   - (b) All share setups at once by a judge version, which re-judges every stored verdict under new
     thresholds.
   - (c) Never: the measures are shown, the criteria stay.

   Recommend (a). The measures appear for every setup either way, and (b) changes published labels
   without a new trial.
8. **The published exit of option setups (G2; amends ADR 0083 decision 3).** ADR 0083 fixed the
   stop and its 2 x ATR(14) fallback for share picks. Option setups already have evaluated exits
   (`[outcome.exit]`: stop loss, take profit, DTE).
   - (a) The same 80th-percentile rule on the position's worst loss as a share of collateral, with no
     fallback (UNKNOWN with too few winners).
   - (b) A stop on the underlying's price, taken from the winners' underlying drawdown, with the ATR
     fallback.
   - (c) No stop for option setups: hold to expiry or the cap.
   - (d) Publish the setup's own evaluated exit rule (the declared stop loss, take profit and DTE the
     backtest used). Use (a) only when a setup declares no stop.

   Recommend (d). The trader sees the rule that was tested, never a second rule beside it, and (a)
   covers setups held to expiry.
9. **May a setup's entry, exit and case rules read personal-licence fields (IBKR-derived, VIX family
   values, option history) (G9)?** The gate stays open-only either way (H1).
   - (a) Yes: the rule's licence is its strictest field, the trial is personal, and by ADR 0084
     decision 1 (the E1 gate) the setup is hidden from, and adds no Ideas picks for, a viewer without
     that licence.
   - (b) Only open fields in any rule of a setup published to traders; personal fields only in the
     owner's own setups.

   Recommend (a): it is the existing licence machinery, with nothing new to enforce, and the owner
   still sees every setup; (b) adds a second licence rule beside ADR 0084's.
10. **(P2, decide when E14 is next) Publish setups whose rules read a fitted score?** ADR 0083's
    product rule says the site's model only translates a sentence into rules; a learned scorer (ED7)
    ranks names, which ADR 0053 allows for proposing.
    - (a) Yes, judged only after `fitted_through` plus a horizon, labelled "ranks with a fitted
      score" (an ADR 0083 amendment).
    - (b) Owner-only: a scored setup is evidence for the owner, never a trader's idea.

    Recommend (a) once one scored setup has a forward record, (b) until then.
11. **What Ideas shows for short, long-short and book setups (G20; ADR 0083: "publishes setups", no
    position size).** 27 edges on main (short, long-short, allocation books) can now store picks.
    - (a) Show short picks as "short" with "borrow assumed" and the **stop UNKNOWN** in P1 (a short
      `max_adverse` would bump `LEG_VERSION`; E12a may pay that bump instead), and a book's names in
      rank order with its **next rebalance date as the exit** (a book exits by rebalance, with
      `hold_rank` / `vol_target` state, not by stop and hold), no weights or sizes on screen. This
      **amends ADR 0083 decision 3 and ADR 0081 decision 4** ("long picks only").
    - (b) Long picks only on Ideas, as today (no amendment); short and book setups appear on their
      setup page.
    - (c) As (a), with the book's weights as percentages (also amends 0083's no-size rule).

    Recommend (a): the setup is published as tested, and showing no weight keeps ADR 0083's no-size
    rule; (c) reads as a position size.

Design calls (defaulted as recommended, logged, not owner decisions):
- one Book owner (`cross_section/portfolio/`), the option ladder its `slots` weighting (G16);
- the schedule is the one reader of event rows; calendar choices are rules (G18);
- `position_key` from resolved legs; one publisher for `structure_pnl@v2` (G24);
- 2002-2009 bars from the running Tiingo session, never a second backfill; bills from the Treasury source (D1) (G25);
- one rule language, the existing `Rule` / `Group`, with use sites in `FieldCatalog.check`; no
  rule-level formulas (G9);
- a catalogue-field rule acts at the next close, a position-only rule at its own close (2.4a);
- an UNKNOWN case is UNSELECTABLE, never the default; an UNKNOWN exit rule never fires;
- the gate's `{field, require}` form dropped for the rule form (G10);
- rows keyed by the resolved concrete point, never the case rule;
- share entry conditions in P1 (a harness mapping), share exit conditions in P2 (path grain);
- the two outcome grains stay separate under one trade contract (G3);
- position templates use a new `position` key, beside the old `structure` enum;
- share setups get no evaluated stop or take profit in P1 (they need a path grain);
- the example position and the exit rule are computed on read in a new `positions/` subfolder;
- the rename to `market_conditions@v1`;
- re-filed edges as new versions;
- the `tails` profile numbers (`full` cost for options, PSR 0.95 / 0.90, CVaR ratio <= 1.25, >= 5 tail
  windows);
- retire `option_model_pnl` / `expires_otm` after every edge is re-filed;
- retire c18;
- single-name earnings setups from 2018 with PRIOR_YEAR dates;
- keep FRED's one-day VIX lag;
- history chain features on the external drive (3-6 GB [I]).

---

## 10. Timing and size figures

All inferred unless marked; each one above 0.2 s is measured in its slice's PR ("estimated X,
measured Y").

- One HOD session partition is 10.8 MB zstd [M, ADR 0084]. Read + select + mark per session 0.3-1 s
  [I] -> 6,000 sessions 0.5-1.7 h per pass [I]; measured in E5 on one year first. With a 20-session
  batch, the main lock is held for one batch's publish, about 1-5 s [I] (measured in E5); a nightly
  that starts in that moment exits 3 and retries on its hourly schedule (worst case one hour late).
- `structure_pnl@v2` rows without paths about 100 bytes [I]; single-name month-end structures
  (290 x ~1,500 names x 10 structures = 4.4 M rows) about 0.5 GB [I]; measured in E5.
- Example position on read: one served-session chain read plus selection for at most 15 picks,
  0.1-0.5 s [I]; measured in E9; a table if over 0.2 s.
- History chain features: 9 groups x ~26 M rows, 3-6 GB [I]; measured in F7.
- Setup state on read: one stored-verdict lookup per setup, under 0.01 s [I] (below the 0.2 s bar).
- Example position for share picks: one served-session read of `price_stats` and `momentum` by
  catalogue name for at most 15 picks, plus the exit rule's percentile, under 0.05 s [I] (below the
  bar). E9 measures it anyway with the option shape.
- Historical exit rule: one ledger read by run id per listed setup, plus a percentile over at most a
  few thousand winners. 0.05-0.3 s [I] for a page of setups on a cold cache, so it is measured in
  E12a; above 0.2 s it is stored as an `edge_eval` measure by the edge-eval writer (ADR 0083's own
  fallback).
- Trade contract: column mapping inside `apply_outcome`, vectorised, adding under 1% to an edge-eval
  run [I]; E6a states the measured run time beside the golden equality check.
- Re-storing the verdict headlines after E6b: one edge-verdicts task run over 66 edges, the time of
  today's task [I] (no new reads).
- 2002-2009 share outcomes (D8): about 1.07 GB a year from the measured 18 GB [M basis], so about
  8.5 GB [I]; at about 1.3 s a session (roadmap ED2 [M there]) about 0.7 h for 2,000 sessions [I],
  run detached.
- Cboe chains: 97 MB a session [M], about 24 GB a year [I]; D9 states bytes per session before and
  after its change ("estimated X, measured Y").
- Rule evaluation itself (`evaluate_group` per row): microseconds per row [I]; the cost is the reads.
- Entry condition (E13): per decision session, `within_sessions` extra session reads of the named
  groups for the eligible names, 0.1-0.5 s per session read [I], so 0.5-2.5 s per D at a wait of 5
  [I], above the bar: measured in E13 on one edge-year ("estimated X, measured Y"); a cache per
  session across decision sessions shares overlapping waits.
- Case values at D (E13): one read of the named groups per D, usually already read by the screen,
  0-0.3 s [I]; measured in E13. At the served session for at most 15 picks (E9): under 0.05 s [I].
- Exit conditions over catalogue fields (E4): one read per named group per session of the window,
  cached per session across every trade of the batch, 0.05-0.3 s per session [I], so up to 1.5-9 s per
  30-session batch [I]; measured in E4. A setup with only position-field exits reads nothing extra.
- An entry condition's wait (G9-M3) multiplies an option edge's `structure_pnl@v2` rows by
  `within_sessions` for its screened names (5x at a wait of 5) [I]; counted in E4 and E5.
- Portfolio features (E15): a pass over the setup's own trades per decision session, under 0.05 s per
  D [I] (below the bar); the in-order evaluation removes per-session parallelism for such a setup,
  measured in E15.
- Case points multiply `structure_pnl@v2` rows by the number of distinct points a setup's cases can
  produce (2 for the tenor example) [I]; counted in E4 beside the 0.5 GB estimate.
