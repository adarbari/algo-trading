# ADR 0088: Setups as positions and rules: share and option legs, every decision a rule over features, one entry and exit rule, one trade contract, a per-setup gate

**Status:** proposed (2026-11-01; design architect-reviewed three times and judged fit to build; the
owner answered the 11 decisions in chat on 2026-11-01, written below as decisions 12-22). Plan and
build slices: [options/backend-plan.md](../options/backend-plan.md). Extends
[0053](0053-edges-hypotheses-outcomes-and-one-harness.md) (edges, outcomes, one harness),
[0049](0049-run-overlays-and-the-regime-gate.md) (the regime gate), [0029](0029-rule-screener.md) (the one
criteria language), [0081](0081-stored-edge-picks.md) (picks), [0083](0083-workflow-first-trader-site.md)
(Ideas, the historical exit rule) and [0084](0084-bought-option-history.md) (the bought history).
**Amends** 0053, 0049, 0047, 0069 decision 4, 0073, 0081, 0064, 0074, 0075, 0050 decision 3, 0083
decision 3, 0084 and, 0065 (#967, merged) (list under Amendments). Takes number 0088: 0087 is
PR #968's, 0086 is on main.

## Context
ADR 0083 made the site workflow-first and ADR 0084 bought end-of-day option history, so option setups
(cash-secured puts, spreads, covered calls, sleeves on indexes) are the next kind of setup. The edge
machinery on `main` is built for shares: one outcome grain of forward returns, one `side`, a regime gate
that is a screener overlay, a verdict judged on return. Adding options by copying that machinery would
give two harnesses, two evidence paths and two vocabularies; the owner's rule (2026-10-25) is to
generalise the existing piece, and on 2026-10-31 to make share and option setups one vocabulary and every
part of a setup that decides something a rule over features. The design (the plan file) covers 36
entities in four layers (market; setup definition; trades and evaluation; each night), reviewed three
times (findings G1-G25 and later, in the plan). The 2002-2009 share outcomes backfill runs on the SSD
store; the Cboe chains are stored from 2026-10-02 and the bought history is personal-licence.

## Decision
1. **Rules.** Every part of a setup that decides something (screener, universe, gate, entry condition,
   exit condition, position parameters and choice) is a rule in the one criteria language that
   selections and rule screens share (`Rule` / `Group`, three-valued, one evaluator), over catalogue
   fields at every level (instrument, market, session / calendar, event through its features) and, for
   exits only, position-level fields. One check per use site (`FieldCatalog.check` with a site: `gate`,
   `entry`, `case`, `exit`; today's calls are the `screener` / `universe` sites) fixes the levels a rule
   may name, the session it reads, when it may act (a catalogue-field rule observed at a close acts at
   the next close; a position-only rule at its own) and its licence. A case value whose rule is UNKNOWN is
   unselectable, never the default; an UNKNOWN exit rule never fires. A formula is an expression feature,
   never a rule-level expression. At the gate, entry, case and exit sites the null tests are refused and
   string fields are read over their declared domain, so missing data never opens a gate. A screener is a
   published rule (instrument scope, a rank, an identity); setup-internal rules are the same language and
   can be promoted.
2. **Feature levels** are declared once (key, provider, point-in-time rule, join path, scopes, licence):
   instrument, market, session, event, position; portfolio later (P2). A new level adds a provider and a
   join path and never changes the language, the evaluator or the checks. A portfolio level describes the
   setup's own paper book or tonight's list, never a user's holdings (ADR 0083).
3. **Positions.** A setup's position is a site template of legs (`config/site/positions/templates.toml`).
   A leg is shares or an option; option legs are chosen by our own delta from one session's chain through
   the one selector and assigned and early-exercised by fixed rules. A share setup is one share leg; an
   existing edge's `side` maps to it with no document change and no fingerprint change. The new `position`
   key sits beside the old `structure` enum.
4. **Entry and exit.** One entity for both kinds: an entry offset, optionally after an entry condition
   (`within_sessions`), and exits by horizon, expiry, take profit, stop loss, DTE and an exit condition,
   evaluated at closes only as one ordered list (the first in declared order wins). Position-level fields
   are one typed list, computed by the structure engine at each close from that close's prices and the
   entry facts, never stored as catalogue features. Share setups evaluate the horizon (and the entry
   condition) only until a path-aware share grain exists (P2).
5. **Outcomes and the trade contract.** Option trades are stored per trade in
   `outcomes/option/structure_pnl@v2` (supersedes the empty v1), keyed by the resolved legs' `position_key`
   (never the template id), with a price source (one per entry session, by a fixed cutover at
   `FIRST_CBOE_CHAIN_SESSION`, 2026-10-02: history strictly before, Cboe from it) and a `licence` per row.
   A row's `knowledge_ts` is the latest `knowledge_ts` of every partition it read (chain or history, and the catalogue fields an exit rule names), never the window close; "closed by S" reads `window_end`. A trade entered before 2026-10-02 whose window runs past the bought history's last session is UNMEASURED with a reason (history ended) and counted, never priced by the intrinsic fallback or a Cboe exit. Share trades stay in `forward_returns@v2`. Both satisfy one trade contract (entry and exit session, exit
   kind, capital basis, return on capital by cost level, worst adverse move, price source, licence) in
   `services/evaluation/evidence/`; one evidence path reads only that contract. Price sources are `bars`,
   `cboe`, `option_history` and `model`; `expires_otm` / `hit_target` have no capital basis. One publisher
   writes `structure_pnl@v2` (`frame_and_publish`).
6. **Evidence and verdict.** For every setup the harness reports return on capital (notional for shares,
   collateral for options) at its cost levels against its base, CVaR with its tail count, a block bootstrap,
   PSR and DSR; drawdown, episodes and the monthly map stay with `edge_evidence`, read over the contract.
   The judge picks its criteria by the setup's **profile**: `return` (today's; the default, so no stored
   verdict changes) or `tails` (option setups, and a share setup only through a new version).
7. **Gate (a per-setup rule; owner decision 13).** A setup may declare a gate: a rule over the market and
   calendar fields it chooses, read at D, decided open / closed / unknown by the ADR 0049 regime gate's
   decision, and whether that gate is on. There is no site-wide verdict every setup shares. The picks task
   and both harnesses apply it outside screening and regardless of `[regime].enabled`; a pick needs the
   screener's own `pause_in` and the setup gate both open; a closed gate is `PAUSED` / stored pick status
   `gate_closed`, read as `paused`. A setup that wants both judged declares the gated and ungated pair as
   a variant; the harness reports open, closed and unknown slices (closed = the inverse decoy).
   `market_conditions@v1`, one leaf market group beside the unchanged `regime@v3`, stores the inputs and
   `_on` states as catalogue features a gate may name; nothing in it is shared by default. Its stored state columns (`_on`, `short_premium_allowed`) are declared **open** as our own thresholded booleans, the `regime@v3.label` precedent of ADR 0069 decision 4, while raw VIX-family values stay personal; a reason names the condition, never a VIX figure. Reversible by flipping `Feature.licence` with no recompute (0069 decision 3 re-gates at read). Decided by Fable for the owner, pending owner confirmation (decision A below). A gate's fields
   count toward the setup's licence under decision 20 (this replaces the review finding H1's rule that a
   gate may only read open stored verdict columns).
8. **Base `delta_equivalent`** for named option sleeves on the time-series harness (decision 14), with
   variants and gates allowed for that base only. A named sleeve's ladder is the existing book (0074) with
   a `slots` weighting, plus Cboe index tracking; a book's per-session series is a contract shape
   (`capital_basis = book`) feeding evidence only.
9. **Picks and read model.** `results/edge_picks` gains `pick_sides` and `pick_weights`, the stored status
   `gate_closed` and the sentinel screener `@named` for named-symbol setups. The example position (both
   kinds, case values resolved at the served session, an UNKNOWN case shown UNKNOWN with its reason), the
   historical exit rule and the setup state (ON / OFF / PAUSED / UNKNOWN, a chip) are computed on read in
   `services/read/evaluation/positions/` and `verdict/state.py`; stored only if measured over 0.2 s.
10. **Models (P2).** A learned scorer's output is a feature rules read (ED7's `edge_score_<edge>`); a
    setup whose rule reads one is judged only after its `fitted_through` plus a horizon, the earlier
    sessions an `in_sample` slice; models propose and rank, never judge; inputs from `no_ml` tables are
    refused.
11. **Personal derived data (ADR 0084 amendment).** One rule: a derived table whose licence can vary by
    row lives in the main store with a `licence` column on every row; a catalogue feature group, whose
    licence is per feature, stays in the history root. Two derivations follow, both by tasks in
    `algotrade_ingestion.tasks.options_history`, both `personal`: `structure_pnl@v2` rows (through
    `frame_and_publish`, one IngestRun per session batch under the main lock for that batch only, none in
    the nightly window) and the pre-cutover chain feature groups, read only through the `StoreReader`
    splice importable only by the cross-section harness. Decision 3 of 0084 is extended to exactly these
    two. A trial's licence is the strictest licence of the rows and partitions it actually read (no date
    rule): an option trial over 2015 is personal, a share trial over 2015 stays open. Every row of
    `results/edge_trades` carries its own `licence`. The setup's open verdict reads a trial over `price_source = cboe` rows only; a slice that reads history rows is a separate trial, owner-only (decision 12), so the Cboe forward record stays open.

### Owner decisions (2026-11-01, in chat; final)
12. **History-derived evidence is owner-only for now**, until HOD's terms on derived statistics are read;
    the Cboe forward record and example positions stay open.
13. **Gates are per setup** (the owner's framing: "each setup can use different market features and
    decide if they want the gate to be switched on or off"): decision 7. No Regime-page cards until the
    option setups have verdicts.
14. **Base `delta_equivalent` (a)** for named option sleeves, variants and gates allowed for that base
    only. Lifts ADR 0073 decision 1's calendar-schedule, `excess_return` and no-variants limits for that
    base only.
15. **Paper-derived structures use PR #967's post-publication basis (a), with a minimum and an early
    start.** A gate or threshold chosen in this research is judged only on data the research did not
    see, and **no verdict is given until that holdout holds at least 3 months**; the verdict's own
    minimum-trade rules apply on top. The holdout may start before the Cboe start (owner: "Yes, start
    earlier"), on the bought history:
    - *Where it starts:* the first session after the latest data the research read for that gate or
      threshold, not 2026-10-02. The history slice before it is labelled in-sample.
    - *Declared per item:* each research-chosen gate or threshold declares a `holdout_from` and the
      research source it came from; a fitness test checks `holdout_from` is after that source's data
      cut-off. Thresholds from the October 2026 AI study (data through 2026-10-23) start no earlier than
      2026-11-02. The dates are in decision D below.
    - *The holdout* is the sessions after both the research source's data cut-off and the commit that fixes the rule (a threshold tuned later restarts it), counted over trades whose window has closed. *The minimum* of 3 months is measured across the joined history and Cboe stretch. This decision has no basis unless #967 is accepted.
    - *The joint is disclosed:* the history's prices are HistoricalOptionData's 16:00 New York snapshot,
      the Cboe stretch's the Cboe close (the fixed cutover of decision 5, 2026-10-02); an evidence page
      over the joined holdout says so, and the price source is a column of every trade.
    - *Cut-off dates:* decision D below. For the research-file items the bought history adds no
      holdout time, and the 3-month minimum stands.
16. **Ideas stays as ADR 0083 says (a); the setup state is a chip.** No 0083 amendment for Ideas by state.
17. **A1 (the first option setup) is published gated** by the research gate R-A; the ungated version is a
    variant.
18. **The `tails` profile is opt-in per setup by a new version (a)**; stored share verdicts stay.
19. **A setup publishes its own evaluated exit rule (d)**: the 80th-percentile stop of ADR 0083 decision 3
    only for a setup that declares no stop; no ATR fallback for option setups.
20. **A rule's licence is its strictest field (a)**, at the gate, entry, case and exit sites; the screener and universe stay under 0064 decision 10 and 0069 decision 3, so no existing setup disappears and 0064 decision 10 is not amended (decided by Fable for the owner, pending owner confirmation, decision B below); the gate is a rule, so its fields are recorded in the trial licence (decision C below); the trial is personal if any rule read a personal
    field; such a setup is hidden from, and adds no Ideas picks for, a viewer without that licence. The
    gate is a rule, so its fields count too (reading recorded for owner confirmation: it is the proposer's,
    not stated by the owner).
21. **Rules reading a fitted score (P2):** owner-only until one scored setup has a forward record, then
    shown as any setup; decided again at slice E14.
22. **Short picks are shown as "short" (borrow assumed, stop UNKNOWN in P1); books in rank order with the
    next rebalance date as the exit; no weights or sizes (a).** Lifts "long picks only".

### Design calls (defaulted as recommended; logged, not owner decisions)
One Book owner (`cross_section/portfolio/`), the option ladder its `slots` weighting; the schedule is the
one reader of event rows and calendar choices are rules; `position_key` from resolved legs and one
publisher for `structure_pnl@v2`; the 2002-2009 bars come from the running Tiingo session (never a second
backfill) and bills from the Treasury source; one rule language with use sites in `FieldCatalog.check`, no
rule-level formulas; a catalogue-field rule acts at the next close, a position-only rule at its own; an
UNKNOWN case is unselectable and an UNKNOWN exit never fires; the gate's `{field, require}` form dropped
for the rule form; rows keyed by the resolved concrete point, never the case rule; share entry conditions
in P1 (a harness mapping) and share exit conditions in P2 (path grain); the two outcome grains stay
separate under one trade contract; position templates use a new `position` key beside `structure`; share
setups get no evaluated stop or take profit in P1; the example position and exit rule computed on read;
the rename to `market_conditions@v1`; re-filed edges as new versions; the `tails` profile numbers (`full`
cost for options, PSR 0.95 / 0.90, CVaR ratio <= 1.25, >= 5 tail windows); retire `option_model_pnl` and
`expires_otm` (and the `structure` enum) only after every filed edge is re-filed, and `structure_pnl@v1`
now (it is empty); retire c18; single-name earnings setups from 2018 with PRIOR_YEAR dates; keep FRED's
one-day VIX lag; history chain features on the external drive. FOMC dates carry the schedule's
announcement date as `known_from` per year (decision 3 of 0050 exception).

### Decided by Fable for the owner, pending owner confirmation (2026-11-01, owner asleep; all reversible)
- **A. The stored `market_conditions@v1` states are open.** The `_on` states and `short_premium_allowed` are thresholded booleans we compute, the `regime@v3.label` precedent (0069 decision 4); reasons name the condition; reversible by flipping `Feature.licence`.
- **B. Decision 20 covers the gate, entry, case and exit sites only.** Screener and universe fields keep 0064 decision 10's per-column redaction; `vrp_short_premium` and `c18` are unchanged; 0064 decision 10 is not amended.
- **C. Confirmed, with a flag.** A gate is a rule, so the strictest-field rule applies to it; with A open, a gate over the `_on` states stays open. H1's fitness test becomes "a gate's fields are recorded in the trial licence". Flag: question 9's text said the gate stays open-only either way, so it is answer 2 that revokes H1, not answer 9.
- **D. `holdout_from`** is the first session after the latest data the item's cited sources read: the stated data end where a source gives one, else its publication month; for an item set by the researcher's judgement, the file's date. Default for the three option-setups research files: **2026-10-26**, so the earliest verdict is 2027-01-26. Exceptions, only where every source has an explicit end: Spintwig 2007-2024 (A4 variants) 2025-01-02; Lambda 2010-2025 2026-01-02; ORATS-only earnings items 2026-03-02. The regimes file has no exceptions (its thresholds were set on the full record to April 2025). The October 2026 AI study: 2026-11-02. The owner may reverse any of A-D; `needs-owner` stays on.

## Amendments (each ADR gets a pointer to this one)
- **0053:** outcome kinds, the trade contract, measures and the verdict profile; rules over features as a
  setup's parts; a fitted score as a field, judged after `fitted_through`; schedules gain the opt-in
  `on_event:earnings_reaction` class, the time known at D.
- **0049:** the gate as a rule over market and calendar fields, applied at setup level outside screening;
  the screener's `pause_in` read as the same decision over the label's domain.
- **0047 / 0069 decision 4:** market fields may be named in per-name rules at the gate, entry, case and
  exit sites (expressions still cannot combine them); a market field's licence is its feature's own, a
  gate's fields count toward the setup's licence (decision 20), and no site-wide open verdict column is
  required.
- **0073:** base `delta_equivalent` (decision 14).
- **0081:** named-symbol picks under `@named`; the stored status `gate_closed`; `pick_sides`,
  `pick_weights`; decision 4's "long picks only" lifted for short and book picks (decision 22).
- **0064:** the ledger and paper columns of the trade contract, including the per-row `licence`.
- **0074:** the book is the one book entity, with a `slots` weighting and its series in the trade contract.
- **0075:** the `post_spike_contango` and `fomc` triggers.
- **0050 decision 3:** FOMC `known_from` (above).
- **0083 decision 3:** the historical exit rule over the contract's `max_adverse` for both kinds; an
  option setup publishes its own declared exits (decision 19); short and book picks shown (decision 22).
- **0084:** derivations from the bought history (decision 11); decision 3's import allowance extended to
  the outcome derivation and the splice; the licence gate it requires (slice E1) is this ADR's reading of
  decisions 12 and 20.
- **0065, on top of the post-publication basis from #967 (merged):** decision 15.

## Consequences
- Option setups reuse the edge document, harness, verdict, picks and Ideas; share setups gain the
  contract and the new measures without any stored verdict, fingerprint or headline changing (golden
  equality tests in slices E2, E6a, E6b).
- New responsibilities, folders and tables (`positions/`, `evidence/`, `structure_pnl@v2`, rule use sites,
  position fields, case values, `trade-evidence`, `pick-positions`) get owners in the slices that add them
  (`add-responsibility`); this ADR adds no code.
- A gate is per setup, so there is no shared verdict to keep open; the cost is that a setup reading a
  VIX-family field is personal and hidden from viewers without the licence (decisions 12, 20).
- No option verdict is published before a gate's or threshold's 3-month unseen holdout; with the
  history the holdout can start before the Cboe stretch, so the earliest date is per item (its
  `holdout_from`), not fixed. The first option setups show as "Unproven" meanwhile.
- Slices D2, E1 and later start from this ADR; E1 needs the 0084 part accepted.
