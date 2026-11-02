> Plan part 3 of 4: sections 2.5 to 2.16 (outcomes, trade contract, evidence, rules, models, feature levels). Start at [backend-plan.md](backend-plan.md); the decision is [ADR 0088](../adr/0088-setups-as-positions-and-rules.md).

### 2.5 Option trade outcomes: `structure_pnl@v2`

**Definition.** One row per trade of a position with an option leg (underlying, entry session S,
`position_key`): what the position earned from its entry close to its exit, no cost applied. Share-only
positions never write here: their trades come from `forward_returns@v2` (2.5a).

**Table** `outcomes/option/structure_pnl@v2` (supersedes the empty v1, removed in E4). Partition =
S, runs merge per key. Owner `option-outcomes`; read only through `data/outcomes/chain.py`, importable
only from `services/evaluation`. **One publisher (G24):** `frame_and_publish`, a new function extracted in E4
from `tasks/derived/option_outcomes.py` (today `compute_option_outcomes` and `_one`), is the only function that writes the table; the history task
(`tasks/options_history/outcomes.py`) computes frames and calls it, so `tables.toml` keeps one
owner. **`position_key` from resolved legs (G24):** the key is built from each leg's resolved spec
(kind, right, qty, strike rule, delta, tenor) plus collateral, selection parameters, entry offset,
the exit rule list and the hold cap, never from the template id, so an edit of `templates.toml`
cannot change what a stored row means (a changed template writes new keys).

| group | columns |
|---|---|
| key and stamps | `instrument_id`, `session_date` (S), `position_key` (canonical, round-trips to the spec: template + leg overrides + selection parameters (`strike_delta`, `tenor_days`, `expiry_cycle`, `skip_report_in_life`) + entry offset + `[outcome.exit]` + hold cap; two grid points that differ only in `take_profit` are two keys), `price_source`, `licence` (the strictest of the price source and the exit rule's fields, G9 low), `ts`, `knowledge_ts`, `source`, `run_id`, `window_end` |
| legs (aligned lists, the share leg included) | `leg_kinds` (`option` / `shares`), `leg_contract_ids` (null for a share leg), `leg_rights`, `leg_strikes`, `leg_expiries`, `leg_qty`, `leg_entry_mid`, `leg_entry_half_spread`, `leg_entry_delta`, `leg_entry_iv` |
| entry | `entry_spot`, `entry_net_mid`, `position_delta`, `position_gamma`, `position_vega`, `position_theta`, `quoted_otm_prob`, `collateral`, `notional`, `regt_margin`, `entry_oi_min`, `entry_spread_share` |
| path (`book = true` only) | `mark_mid` float32[], `spot_path` float32[] |
| exit | `exit_session`, `exit_kind` (`EXPIRED`, `ASSIGNED`, `EARLY_ASSIGNED_DIVIDEND`, `TAKE_PROFIT`, `STOP_LOSS`, `EXIT_DTE`, `HORIZON`, `DELISTED`; 2.4a), `exit_basis` (`QUOTE`, `INTRINSIC`, `INTRINSIC_FALLBACK`), `exit_net_mid`, `exit_half_spread`, `dividend_forgone`, `expired_otm` |
| P&L (per unit, $, mid) | `pnl_mid`, `option_pnl`, `stock_pnl`, `pnl_hedged_mid`, `path_min`, `max_adverse` (the worst mark loss / collateral, always stored; the contract's column and the exit rule's input, 2.4a), `realised_vol_window` |
| status | `outcome_status`, `outcome_reason` |

`price_source` is `cboe` or `option_history` (G4; `bars` is the share trades' value in the contract).

**One source per S (H6).** `FIRST_CBOE_CHAIN_SESSION = 2026-10-02` in `data/outcomes/chain.py`:
history rows are read only for S before it, Cboe rows only from it; the reader drops the other
source (contract test). The same constant drives the history-feature splice (2.10). Overlap rows
exist only for the owner's one-off comparison.

**Writers.**
- **Cboe, nightly:** `tasks/derived/option_outcomes.py` calls the selector and the engine and
  writes `price_source = cboe`, `licence = open`; `knowledge_ts` = the latest chain partition read.
- **History, owner-run (H5):** `tasks/options_history/outcomes.py`
  (`option-history-outcomes --from --to [--structure]`), in the one package allowed to import
  `data.option_history`. It is added to the `writes()` exemption in `cli/main.py` (as
  `option-history-import` is) and runs **one IngestRun per session batch** (default 20 sessions): it
  computes the batch under the history store's own lock (ADR 0084) with **no IngestRun open** (rows
  held in memory or in the history root's scratch, nothing pending in the main store), then takes the
  main ingest lock with `locks.held(..., wait=False)` and, entirely inside that hold, opens the
  batch's IngestRun, writes its rows and commits it (N7: no pending main-store writes ever exist
  while the lock is free, so a nightly can never abort a half-published batch); on a held lock it
  pauses and retries; it runs `recover_unpublished` under the main lock before its first batch; it starts no
  batch inside the nightly window (`config/site/nightly.toml`). The lock is a plain flock, so a
  nightly that starts during a publish exits 3 and retries on its hourly schedule: the worst case is
  a nightly delayed one hour. Rows: `price_source = option_history`, `licence = personal`. Structures: those
  the open edge documents declare; sessions: every session for `book = true`, else the naming edges'
  decision sessions. Resumable by stored key and history run id; a dropped mount fails the batch, not
  the run. Runs detached (README "Long runs"). Tests: no batch holds the main lock across two
  publishes; no batch starts inside the nightly window.

**`knowledge_ts` for history bought later.** The latest `knowledge_ts` of the history partitions read
(the import instant), never the window close; `window_end` serves "closed by S". A re-import is a
newer run, so leg reuse (ADR 0063) invalidates what joined the old row.

**Exit fallback (survivorship).** A missing exit quote takes the next two-sided quote within 3
sessions, else intrinsic on the underlying's close (`INTRINSIC_FALLBACK`, counted); a delisting
settles at intrinsic on the last price. UNMEASURED only when no entry existed.

**Quarantine.** Only `tasks/options_history/` imports `data.option_history`; the example position and
the paper record read only `chains/*`.

### 2.5a The common trade contract (share and option setups)

**Every outcome shape maps to it (G16, G22).** Position trades (share or option) map as below. A
**book** (`portfolio_return`, ADR 0074, and the fixed-slot option ladder) maps its per-session series
from `results/edge_series` with `capital_basis = "book"`, so the tail measures cover it. `expires_otm`
and `hit_target` map with `capital_basis = "none"` and `return_on_capital` null: judged on hit rate as
today, tail measures null. `option_model_pnl` maps with `price_source = "model"`. `results/edge_trades`
already has `licence`, `value_licence`, `score_licence` and `adv_licence` (`detail/trades.py:106-109`):
the contract reuses them (G24, corrected). The book series enters the evidence path only; it is never
framed into `edge_trades` rows, since a session is not a trade.

**Why the two grains stay separate (G3).** The stock grain and the option grain differ in what one
row is, how many rows there are and what a base rate is drawn from:
- `outcomes/instrument/forward_returns@v2` (ADR 0053) is one row per (instrument, S, horizon,
  benchmark), for every name and every session, from bars. That breadth is what the base rate and the
  deciles need: every eligible name, about 8,000 a session [I], at each declared horizon. Its exits
  are fixed horizons with no path decisions, its licence is open, it is backfilled from the 1970s,
  and every stored leg (ADR 0063) is keyed to its partitions.
- `structure_pnl@v2` is one row per (underlying, S, `position_key`) for optionable names with a usable
  chain, about 25 leg and Greek columns wide. Its exits depend on the path, and it carries a licence
  and a price source per row. Its base is the same position on every eligible optionable name.

One table would carry those columns null on millions of stock rows, rewrite the stock backfill and
invalidate every stored leg.

**What is already shared.** `cross_section/hit.py::apply_outcome` is the one place every outcome
kind becomes the harness's `RESULT_COLUMNS` (value, orientation, hit, excluded reason, delisted):
excess return, `hit_target`, `expires_otm`, `option_model_pnl`, `option_pnl` and `pair_spread`. The
harness, the paper record (`forward/`) and the ledger framer (`detail/trades.py`) read only that
frame, and `results/edge_trades` is already one ledger for every kind. The contract generalises it;
it is not a new layer.

**The contract.** One frozen column set, `TRADE_COLUMNS`, defined in
`services/evaluation/evidence/contract.py` (owner `trade-evidence`; a new folder, because
`cross_section/` is at its module cap). It is built by one pure mapping, `evidence/shapes.py`
(`trade_frame`, `series_trades`, `book_trades`), called **right after `apply_outcome`, which is not
edited** (E6a, decided there): `value`, `hit` and `excluded` stay byte-identical by construction, and
the ~8,000 eligible names of a session are never given ten more columns; only picks become trades.
The harness's picks, the paper settlement and the time-series valuation call it. `pair_spread` maps
its two legs as one row. A `portfolio_return` book stays outside the ledger: it is one value per
session, not trades (`book_trades` feeds the evidence only).

| column | share setup (from `forward_returns@v2`) | option setup (from `structure_pnl@v2`) |
|---|---|---|
| `value`, `higher_is_better`, `hit`, `excluded`, `delisted` | today's `RESULT_COLUMNS`, unchanged (an `excess_return` edge: the excess return net of `cost_bps`) | today's `option_pnl` value, read from v2 |
| `entry_session`, `exit_session` | S, and the h-th exchange session after S | S, and the engine's exit session |
| `exit_kind` | `HORIZON` or `DELISTED` | the kinds in 2.4a |
| `capital_basis`, `capital` | `notional`; `capital` null in P1 (neither `forward_returns` nor the legs hold the entry close; the return is enough) | the template's rule (`cash_secured`, `max_loss`, `regt`, `notional`), from v2 `collateral` |
| `return_on_capital_gross`, `underlying_return`, `outcome_licence` (E6a) | the raw `fwd_return` (a short: its negative) before cost; the name's own `fwd_return` | `pnl_mid` / collateral before cost; null (the chain grain's return is the option's); v2 `licence` |
| `return_on_capital` by `cost_level` | `fwd_return` less each `[edge_costs] levels_bps` level and the document's `cost_bps` | `pnl_mid` / collateral at `mid`, `effective` and `full` (`[option_costs]`) |
| `max_adverse` | `fwd_max_drawdown` (long picks; a short's stays null in P1, no leg column) | v2 `max_adverse` |
| `price_source` | `bars` | `cboe` or `option_history` |
| `licence` | the row's (open for bars) and the trial's (ADR 0069) | v2 `licence` and the trial's |

**One evidence path.** Everything after `apply_outcome` reads only the contract, never a grain's
column: `cross_section/measures.py`, `services/evaluation/evidence/` (2.6), the ledger framer and
the paper record.
- `results/edge_trades` gains `exit_kind`, `capital_basis`, `return_on_capital` (at the document's
  `cost_bps`, the level `value` is net of; E6b adds the levels), `max_adverse` and `price_source`,
  all nullable. Rows written earlier read them as
  null. Its `max_drawdown` stays as the share alias until its readers move.
- `results/edge_paper` gains `exit_kind`, `return_on_capital` and `price_source`; today its raw return
  is null for an option P&L. The settlement change is in `forward/settle.py:133` (it reads
  `fwd_return`), beside the frame in `forward/results.py`.
- The stored legs (ADR 0063) lacked the share `fwd_return` and every option field, and a default is
  never filled: E6a bumps `LEG_VERSION` 4 -> 5 (each pick stores `pick_exit` .. `pick_adverse`),
  one full run, stated in the PR. The key also seeds the random draws, so every draw is re-drawn
  once (screeners', baselines' and the ledger's values are unchanged).
- A share's `max_adverse` is the window's intraday dip, an option's the worst close mark: do not
  pool them without saying so. `value_licence` is now per row (the strictest of the trial's and
  the outcome row's); a reader exposing the new columns extends `runs.LICENSED` (E11 / E12b).
- Acceptance: on the golden edges, every existing `value`, `hit` and `edge_eval` row is equal before
  and after.

### 2.6 Evidence for a setup (share and option alike)

**Where.** `services/evaluation/evidence/` is a new folder, responsibility `trade-evidence`. It reads
only the trade contract, and the two harness seams stay the only importers of `data.outcomes`. Its
modules:
- `contract.py` (2.5a);
- `values.py`: return on capital at a cost level, and the paired excess against the base. Option-only
  values: won vs quoted, the hedged split, the wing cost, the share leg's part of the return;
- (no `book.py`, G16): the in-run ladder of a named option sleeve (fixed collateral slots, no
  leverage, no hindsight capital) is `weighting = "slots"` of the existing book code
  `cross_section/portfolio/` (ADR 0074, owner `edge-evaluation`); episode rows and share drawdowns
  stay in `edge_evidence` (G-M5);
- `benchmarks.py`: bills, buy-and-hold, the delta-equivalent stock, Cboe index tracking;

Statistics are in `quant/edges/tails.py` under `quant-edge-statistics`: `cvar(values, alpha) ->
(value, n_in_tail)`, `stationary_bootstrap(values, mean_block, draws, seed)` and `worst(values)`. PSR
is `deflated_sharpe(x, 1, 0)`; drawdown reuses `analytics/metrics.py`.

**What applies to both kinds (G6), and who computes it (G-M5).** All of these are over
`return_on_capital`. The harness stores only what the judge reads; the page sections stay with their
existing owner, `edge-evidence-read` (`services/read/edge_evidence/`, `read_ownership.toml:62-64`),
which already computes the drawdown, the deepest episodes, the monthly map, the cost sensitivity and
the regime split from the basis series. E11 extends it to read the contract's `return_on_capital`
series, so a share setup never shows two drawdowns.
- Harness (`edge_eval` measures): CVaR 5% / 1% with the count in the tail, the worst window, the
  stationary block bootstrap interval and t, PSR, `excess_roc`; cost rows stay the existing
  `slice_kind` cost rows (ADR 0064), with the option levels added.
- `edge_evidence` (read, extended in E11): drawdown, worst month, episodes (plus D3's vol shocks and,
  for options, the matching Cboe index and a Reg-T margin-exceeded flag), monthly map, cost
  sensitivity.
- New, because `edge_evidence` cannot produce them: the `slots` weighting of the existing book for a
  named option sleeve and Cboe index tracking (E8b, G16).

Only the denominator differs: notional for a share leg, the template's collateral for a position with
an option leg. Share setups already have cost rows (`[edge_costs] levels_bps`, ADR 0064), which map
onto the contract's `cost_level`; option setups add the `[option_costs]` levels. Option-only measures
are null for share setups.

**Measures** (on `edge_eval`, for every setup):
- `mean_roc` at the verdict's cost level, before bill interest, with a 90% stationary-bootstrap
  interval (mean block 3 decision sessions, seeded by the leg key);
- `excess_roc`, paired per decision session with the base, and its bootstrap t. The base is:
  - cross-section: the same position on every eligible name (for shares, today's base);
  - named option sleeve: the delta-equivalent stock;
- `cvar_5`, `cvar_5_n`, `cvar_1`, `worst_window`;
- `psr`;
- cost rows (the existing `slice_kind` rows);
- benchmark rows;
- for named option sleeves only: the fixed-slot book's `max_drawdown` and `worst_month` and the Cboe
  tracking error (E8b; a share setup's drawdown is `edge_evidence`'s);
- gate and state slices;
- capacity;
- options only: `won_rate` beside `quoted_rate` (the `hit_rate` / `reference_rate` columns),
  `hedged_mean_roc`, `stock_share`, `wing_cost`.

**Stock verdicts do not change (G6).** The measures are stored for every setup, but the judge picks
its criteria by a **verdict profile**, an edge document key `verdict_profile`:
- `return` is the default for **every kind except `option_pnl`** (G-M2): the return kinds and the
  older option kinds `expires_otm` and `option_model_pnl`, which 7 site edges use today
  (`vrp_short_premium`, c12, c13, c14, c16, c17, c18). It keeps today's criteria unchanged: decile
  t, DSR, PBO, trade minimums and the random-pick beat. A fitness test over the site documents
  asserts every profile resolves to `return` unless the kind is `option_pnl`.
- `tails` is the default for `option_pnl`. It adds PSR, the CVaR ratio and the bootstrap t (in the
  verdict's `decile_t` slot: "Return on capital vs base, block bootstrap t"). It judges at the cost
  level of the kind: `full` for options, the document's `cost_bps` for shares.

A share setup moves to `tails` only through a new edge version, which is a new trial (owner decision
7). We rejected a `JUDGE_VERSION` bump, because it would re-judge every stored stock verdict under new
criteria at once, silently.

The change still has one side effect. `settings_hash` hashes the typed `VerdictSettings`, so the new
sections and the profile change every fingerprint once. Until the edge-verdicts task re-stores the
headlines, every one is judged live, to the same label by construction. ADR 0083's Ideas never
judges live and drops a setup whose fingerprint differs, so the re-store runs **in E6b's deploy**,
not later. Its acceptance check: every re-stored label and one-line result equals the stored one,
the 7 older-option-kind edges included, plus a unit test that a `return`-profile judge call gives
the same headline before and after.

**`verdict.toml`:**
```toml
[tails_verdict]            # the `tails` profile (option setups; share setups by a new version)
option_cost_level = "full" # share setups judge at the document's cost_bps
promising_psr = 0.90
works_psr = 0.95
max_cvar_ratio = 1.25      # setup CVaR 5% / base CVaR 5%
min_tail_windows = 5
bootstrap_draws = 2000
bootstrap_mean_block = 3
[option_costs]   # 2.4
[option_quotes]  # 2.4
[slices]         # 2.2
[exit_rule]      # 2.4a; typed apart from VerdictSettings, not a judge input
```
The judge (`verdict/criteria.py`) picks the criteria by the setup's profile. The t bounds, DSR, PBO,
trade minimums and the random-pick beat stay shared.

**Product.** The §7.15 lead line and deeper rows through E11; UI later.

### 2.7 Decoys and variants

- **Inverse-rule decoys:** the closed slice of every gate (2.2). R-B's two decoys are gate variants.
- **Opposite-sleeve decoys:** B2's other sleeve in `baselines`; R-C's put spread as a gate variant
  (P2). The `@standard` battery applies (the edge's structure on the decoy screeners' picks).
- **Position baselines (G19):** `baselines` may name `position:<template id>`: the setup's own
  picks valued with that template, stored as a baseline row beside the decoys (A3 against
  `position:long_shares`). A paired base, not a trial (E16).
- **Variant grids:** `[[variant_grid]]` expands to one variant per point (ids like
  `g_d20_t30_tp50`), each a trial in the DSR and PBO; the trial log is append-only. Parsed in
  `config/edges/positions/grid.py`; `document.py` gains the key only.
  ```toml
  [[variant_grid]]
  prefix = "g"
  strike_delta = [0.16, 0.20, 0.30]
  tenor_days = [7, 30, 45]
  take_profit = [0.0, 0.5]
  ```

### 2.8 The pick's example position

**Definition.** For each pick of a setup at the served session, the position the setup's rule would
open from that session's stored prices. Entry is the next close by `start_offset_sessions`, and the
card says so. It is one read object with two shapes, chosen by the template's legs (`position_of`,
2.4):
- **Share setup** (G5):
  - the reference close: the served session's close, by catalogue name `price_stats.close`,
    labelled as the reference (the entry is the next close);
  - the stop price: reference close x (1 - stop), long picks only (ADR 0083 d3), from the historical
    exit rule (2.4a), with its basis and trade count, or the labelled 2 x ATR(14) fallback;
  - the exit date: the hold counted in exchange sessions from the entry session, by the exchange
    calendar;
  - licence: the fields' own (open).
- **Option setup:**
  - the legs: contract, strike, expiry, qty, bid, ask, mid, our delta and IV, OI, volume, plus a
    share leg's entry close;
  - net credit, collateral, quoted ITM probability, theta per day, a one-sigma-day loss;
  - `report_in_life` (null when unknown) and `ex_div_before_expiry`;
  - the exit rule: the setup's declared stop loss, take profit and DTE as dollar marks (2.4a,
    decision 8 (d)), else the percentile stop as a dollar loss, else UNKNOWN; a declared exit
    condition shown by its fields' Guide terms, with today's values only under the viewer's licence;
  - the parameters its case values chose at the served session (e.g. "tenor 30: IV rank high"), or
    UNKNOWN (`CASE_UNKNOWN`);
  - the exit date: the earlier of expiry and the hold cap;
  - `chain_asof`, and licence (`open`).

A part that cannot be computed (no bar, no `atr_14` row, no chain) is UNKNOWN with its reason, never
filled.

**Where.** Computed on read for at most 15 picks, in `services/read/evaluation/positions/example.py`,
beside `exit_rule.py` (responsibility `pick-positions`). The parent folder is at its 10-module cap, so
it cannot sit beside `pick_edges.py`. It reads the picks through `pick_edges.py` (owner
`edge-picks-decision`), the option legs through the same selector (which owns the selection) and the
share fields by catalogue name (ADR 0038). E9 measures the read; above 0.2 s it becomes a table
written with `edge_picks` (an ADR 0081 amendment). Personal history never reaches it: `services`
cannot import `data.option_history`, and the loader reads `chains/*` only (fitness test).

**Named-symbol setups** (A1 on SPY / QQQ / IWM): their picks are the named symbols eligible at D,
through the same gate (an ADR 0081 amendment; today only screener edges have rows). They have no
screener (2.12).

### 2.9 Event schedules and inputs

- **Report time of day (G21, corrected by G16-M1):** `events/earnings` already stores `time`
  (`pre_market` / `after_hours` / `unknown`, and `intraday` for an 8-K acceptance;
  `vendors/nasdaq/earnings.py`), so no new column. F10 adds an **opt-in** reaction-session anchor (a
  new event class `on_event:earnings_reaction`): the report's session for `pre_market`, the next for
  `after_hours`; unknown is skipped and counted, never guessed. Point in time: the anchor uses the
  `time` on the calendar row known at D (`known_from <= D`), never the 8-K's `intraday` acceptance
  time, known only after the event. The existing `on_event:earnings*` classes are unchanged, so the
  10 site edges on them keep their windows, run hashes and verdicts (golden test). C2 opts in.
- **Earnings past moves:** `earnings_reaction@v2` adds `abs_move_mean_8`, `abs_move_median_8`,
  `abs_moves_counted` (reports with closed windows by S); expressions `earnings_move_ratio`,
  `earnings_move_rich`, `earnings_move_cheap` in the existing `config/site/features/options/earnings.toml`
  (open inputs, so open). History from 2018; PRIOR_YEAR expected dates in history; the harness
  reports the share of earnings trades whose window caught the report.
- **FOMC (M3):** scheduled meetings 2002-2023 typed into `releases.toml`, each year with a declared
  `known_from` = the date that year's schedule was announced (recorded per year with its source in
  `releases.toml`; a meeting moved after publication takes the move's announcement date), an ADR 0050
  decision 3 exception in the new ADR; unscheduled meetings excluded (fitness test);
  `market_conditions@v1.sessions_to_fomc`;
  `on_market:fomc` (P3) with offsets for N10's two windows.
- **Opex week, weekday:** from `core/time/windows.py` into `market_conditions@v1`.
- **Post-spike trigger:** `market_triggers@v2.post_spike_contango_date`, thresholds fixed per version.
- **Dividends:** `events/dividend` from 2002, read by the engine and the example position.

### 2.10 History chain features (P2)

The existing chain groups (`iv30@v1`, `iv_history@v2`, `implied_move@v1`, `option_liquidity@v1`,
`iv_term@v1`, `skew@v1`, `nearest_expiry@v1`, `put_wing@v1`, `call_wing@v1`) recomputed for sessions
before `FIRST_CBOE_CHAIN_SESSION` by the same pure computes, by a task in
`tasks/options_history/features.py` that adapts the history's quotes into the chain-input frame and
writes the groups to the **history root** (personal). The harness passes `screen_session` a
`StoreReader` wrapper (`data/option_history/splice.py`, importable only by
`services/evaluation/cross_section/`, an import-linter amendment) that sends a chain group's partition
read for such a session to the history root; the `RecordingReader` records those partitions for leg
reuse; a trial that read through it records `personal`. Needs PR #968's listing history for
single-name eligibility. Not on X4's path (price-based screens; option liquidity is the engine's quote
filter).

### 2.11 Deferred (P2): books, concentration, the wheel

- **Effective bets** per decision session (`1 / sum w^2` after removing the market factor from the
  picks' 63-session returns) on `edge_series` and on the pick list.
- **Event clustering**: picks sharing a report day or an FOMC inside one expiry.
- **The wheel**: a book over v2 rows (an `ASSIGNED` put hands its shares to the next covered call),
  showing the stock share of return.
- **Vol-managed sizing**: slot weights from trailing realised variance (rolling, real-time only).
- **`results/edge_book`**: a stored daily book series, when a page charts it.
- **Evaluated share exits** (stop, take profit): a path-aware share grain from the bars (2.4a).

### 2.12 Screeners and screener runs (explicit entities, G8)

**Screener (G14).** A **published rule**: a rule (2.13) at instrument scope, plus a rank (sort,
tie-break, top N) and an identity (name, versions, Guide entry, stored runs, its own ADR 0049 pause).
Rule is the one entity; a screener is the kind of rule that has those two additions. It is one of:
- a site rule-screen preset: `config/site/presets/screeners/<id>/v<n>.toml`, immutable, where a
  change is a new version file (`architecture/preset_versions.toml`). All 92 are `impl = "rules"`;
- a user screener: `config/users/<id>/`, saved from Test.

The one Python screener, `strategies/screeners/short_premium_liquidity.py`, is named by no screener
preset and no edge. It is still a site config of kind `screener`
(`presets/strategies/short_premium_liquidity.toml`, run by the nightly through `nightly_screeners`),
the `--config` default of `algotrade-ingest screen`, and the source of the `legacy_liquidity_csv`
export (`services/screening/exports.py`). S5 ports it: its computed facts become a feature group, its
selection a rule preset with the same id, and the export and the CLI default read that preset's run;
then the Python impl and its registry entry are deleted. After S5, no screener is code.

**Promotion.** A setup-internal rule (universe, gate, entry, exit, case: the same language without
an identity) becomes a screener only by being written as a preset version file with a rank and a
Guide entry; the setup then names it. It is the same rule text, never re-written in another form.
Model outputs reach a screener only as features its criteria or rank read (2.14).

Owners: `screen-spec` (parse), `rule-screen-evaluation` (evaluate) and `screen-execution` (run).

A screener plays one of two roles in a setup:
- an **implementation** (`screeners`): the names the setup enters. One of them is the verdict's basis
  (ADR 0065).
- a **baseline** or **decoy** (`baselines`, with `@standard` expanding from `verdict.toml [decoys]`):
  the setup's own position, taken on the decoy's picks.

A screener knows nothing of positions, so one screener can implement a share setup and an option
setup (`iv_rank_high` is a screener of X2 and X3).

Its **own pause** is ADR 0049's `[regime.screeners.<id>] pause_in` (e.g. `vrp_scanner` in STRESS /
CRISIS). It is applied inside screening when `[regime]` is enabled: the paused rows are PAUSED, never
QUALIFIED.

**Screener run.** One run of one screener for one user at one session, written in one publish by
`services/screening/run.py`, nightly or on request (ADR 0033). It is stored in four tables:
- `results/screen_runs`: one row per run, with the version, the decisions, the picked count, and new
  / dropped against the previous run;
- `results/rule_screen`: every row with its decision and rank;
- `results/rule_screen_values`: each criterion's value, under its licence;
- `results/screen_picks`: the picked and PAUSED rows.

It is read by run id for the served session only. A screener with no run is NOT_RUN (ADR 0036).

**How a setup's picks combine the matches and both gates.** Per (setup, screener), by the one rule
`picks.long_picks`:
1. Take the run's QUALIFIED names best first. Names paused by the screener's own pause are not
   qualified.
2. Keep those inside the setup's universe (and an event schedule's names).
3. Keep the first `top_k`.
4. Apply the setup gate (2.2): closed -> status `gate_closed` (read as `paused`); unknown ->
   `skipped`, "regime unknown".

So a pick needs both gates open. Each (user, setup, screener) gets its own `results/edge_picks` row.
Screeners are never merged into one list, because each implementation is measured apart. Ideas shows
only the basis screener's row (ADR 0083). The harness screens with the setup gate off and the
screener's own pause as configured (2.2).

**Named-symbol setups** have no screener: A1 on SPY / QQQ / IWM, and the time-series sleeves. Their
picks are the named symbols eligible at D, through the setup gate (E9). The `results/edge_picks` key
has `screener string!` (`storage/tables/edge_schemas.py:335`), so their rows carry a declared
sentinel screener `@named` (a constant in the schema module, refused as a screener id by the preset
loader).

**Stored and owned:** no new table. `results/edge_picks` gains the `gate_closed` status and the
`@named` sentinel screener (E9; the schema comment and the ADR 0081 amendment say so). The read model
already names the entities (`Screener`,
`ScreenerRun`, `services/read/screens/`); the Entities section and the Guide use the same words.

### 2.13 Rules: one criteria language over catalogue features (G9, G14)

**Rule is the one entity (G14).** Every decision in a setup is a rule. A **screener** is a published
rule: instrument scope, plus a rank (sort, tie-break, top N) and an identity (name, versions, Guide
entry, stored runs, its own ADR 0049 pause), 2.12. The setup-internal rules (universe, gate, entry,
exit, case) are the same language without the identity, and any of them can be promoted to a
screener. Model outputs enter only as features rules read (2.14).

**Definition.** A rule is a `Group` (`all` / `any` / `not`, nested) of `Rule`s `{field, op, value}`
(ops `eq`, `ne`, `in`, `not_in`, `gt`, `gte`, `lt`, `lte`, `between`, `is_null`, `not_null`), evaluated
three-valued: a missing, NaN or wrong-typed value is UNKNOWN, never a pass (Kleene AND / OR / NOT).
This is the language selections and rule screens already share; nothing new is invented.
- **Syntax:** `config/strategy/schema.py::parse_rule` / `parse_group` (the selection `where` form).
- **Evaluator:** `core/model/predicates.py::evaluate_group` (owner `three-valued-predicate`); each new
  caller joins its `allowed` list in the slice that adds it (E2r `engines/selection/cases.py`, E3b
  `engines/structures/`, E7 `engines/screening/gate.py`, E13 the harness's entry mapping), so no
  entry names a path that does not exist yet.
- **Formulas, thresholds, ranks:** a formula is a TOML expression feature (`feature.<name>`), never a
  rule-level expression; a cross-sectional rank is a stored percentile feature (e.g.
  `iv_rank_252d_pct_universe`); ranking names stays the screener's (`rank`, `order_by`).
- **Screeners** keep their scored wrapper: a `Criterion` (HARD / SOFT / SCORE with tolerance) wraps
  the same `Rule`, and ADR 0071's groups by reference combine criteria verdicts (owners `screen-spec`,
  `rule-screen-evaluation`). The scored wrapper is for ranking; every other use site is HARD-only, so
  a plain `Group`.

**Use sites: the one point-in-time check (G9-M1: built, not only extended).** Today
`FieldCatalog` maps an instrument field to its type and nothing else: `services/configs.py::catalog_of`
builds it from instrument groups only ("market-entity features are not selectable per instrument",
ADR 0047), and it holds no licence. E2r makes it scope-aware:
- `FieldCatalog.build` takes the declared levels (`LEVELS`, 2.15) and builds one catalogue per use
  site from the levels that site may read: the `screener` and `universe` sites stay instrument-only
  (today's behaviour, `market.*` still refused there); `gate`, `entry`, `case` and `exit` add the
  market groups (types from `GROUPS` with `entity == "market"`), and `exit` adds `POSITION_FIELDS`.
- It gains a licence map from `Feature.licence`; an expression feature takes the strictest licence of
  its inputs.
- The callers merge the session's market row (and, at `exit`, the position row) into each name's row
  before `evaluate_group`; the field heads differ, so no key collides.
- ADR 0047 is amended: market fields may be named in per-name rules at these four sites. Its line 58
  (an expression cannot combine a market and an instrument field) still holds: the rule combines them,
  not an expression.

| site | used by | levels it may name | read at | acts at | licence |
|---|---|---|---|---|---|
| `screener` | screener criteria and rank | instrument (its own `pause_in` stays the ADR 0049 label) | D | entry at S = D + offset | any; the trial records the strictest |
| `universe` | a universe `Selection` | instrument | D | entry at S | any; the trial records it |
| `gate` | the setup gate (2.2) | market (incl. calendar columns); P2: portfolio | D | entry at S | any; its licence enters the trial's (ADR 0088 decision 7; was "open only", H1) |
| `entry` | `[outcome.entry] when` | instrument, market; P2: portfolio | each close t of the wait | S = t + offset (>= 1) | any; the trial records it |
| `case` | case values (2.4) | instrument, market; P2: portfolio | D (the served session for picks) | the resolved point at S | any; the trial records it |
| `exit` | `[outcome.exit] when` and the compiled settings | instrument, market, position | each close t of the trade | t + 1, or t for position-only rules (2.4a) | any; the trial and the outcome row record it |

The table is not hand-written in code: each row's levels come from `LEVELS[*].scopes` (2.15), so a new
level never edits this check.

**Fail closed at the four new sites (G9-M2, G9-M4).** The screener and universe sites keep today's
semantics. At `gate`, `entry`, `case` and `exit`:
- `is_null` and `not_null` are refused: they are TRUE or FALSE on missing data
  (`predicates.py:70-74`), so a gate `{x is_null}` would open on a gap.
- A string field used with `ne` / `not_in` needs a declared domain (the regime labels, an expression
  feature's categories, a stored column's declared values); a value outside it is read as missing
  before evaluation, so `ne` / `not_in` on an unknown or new label is UNKNOWN, never TRUE; without a
  domain those two ops are refused. `eq` / `in` need no domain: they already fail closed on an unknown
  value (so `instrument.security_type in ["ETF"]` stays allowed, R-1 low). This is `RegimeGate.known` (`gate.py:41`) generalised, so the ADR 0049
  pause read as `not_in` keeps "regime unknown".
- At run start the harness refuses a rule naming a field whose group has no rows over the
  evaluation range (a chain feature before F7, `ibkr_iv` history), with the field and the range.
- An UNKNOWN gate pauses; an UNKNOWN case is UNSELECTABLE; an UNKNOWN entry is not TRUE (on picks and
  base alike); an UNKNOWN exit beyond `exit_unknown_share` (`verdict.toml`, applied by the harness over the stored
  count, R-1) makes the trade UNMEASURED (2.4a).

**Other checks.**
- A field of a level the site does not allow is refused at load (fail closed), as is a
  `position.*` field that does not apply to the template's legs.
- `FieldCatalog` does not import `config/edges/`: the edge loader passes `POSITION_FIELDS` in when it
  builds the catalogue for an edge document, so `config/strategy` keeps its import direction.
- Events are named only through their features, whose `known_from` rule the feature already applies;
  no use site reads an event row.
- The licence of a rule is the strictest of its fields. It may be personal at any site, the gate included (ADR 0088 decision 20); the E1
  licence gate then treats the trial as personal (owner decision 9). Rules may read `no_ml` tables: a
  person wrote the rule (`no-ml-tables`).
- A rule's canonical form (sorted keys, the parsed `Group`) enters the variant's identity through
  `config/edges/identity.py`; absent keys are dropped, so no site edge's fingerprint moves (E2r test).

**Cohorts.** The gate, the screen and every case are read at D; an entry condition only delays S
per name. The harness keeps the decision session D as the cohort: picks and base are compared per D,
with the same entry condition and cases applied to the base names, so a rule in the position never
becomes a hidden filter on one side only.

**Not added:** a rule-level formula language, a second evaluator, a rule table or store (rules live in
the documents that use them), a rule ID registry.

### 2.14 Models (P2 / P3, G13)

**Definition.** A learned scorer whose output is a field rules read. It proposes and ranks; the
harness and the judge decide (ADR 0053).

**What exists (ED7, owner `edge-scorer-fit`).** `fit-edge-scorer` fits a probit of an edge's hit on
the `[scorer] features` read at D, on windows closing before `frozen_from` less one horizon (purged and
embargoed), and writes the coefficients as the TOML expression feature `edge_score_<edge>` with
`fitted_through` in `config/site/features/scores/edge_scores.toml`; nightly scoring is the expression
engine's. `no-ml-tables` refuses any scorer field computed from a table whose terms bar machine
learning. No fit is written on main yet.

**What this design adds (P2, E14):**
- The score is an instrument-level expression feature, so a rule names it like any other
  (`feature.edge_score_<edge>`) at any site that allows instrument fields: a screener's rank, an
  entry condition, a case value, an exit condition. No new seam.
- **Point in time:** a setup whose rule names a fitted score is judged only on decision sessions
  after the score's `fitted_through` plus one horizon; earlier sessions are an `in_sample` slice,
  shown, never judged. A refit is a new feature version, so a new trial.
- **Licence:** the score inherits its inputs' strictest licence; `no_ml` inputs are refused at fit
  (exists).
- **Publishing** a setup whose rules read a score is owner decision 10.

**P3:** other model kinds behind the same contract (an output that is a stored or expression feature
with `fitted_through`): a bucket feature for a case value (position choice), a market-level score (a
market group column, since expression features are per instrument today: to check then).


### 2.15 Feature levels: a declared extension point (G15)

**Definition.** A level is what one row of feature values is about. Each level is declared once, as
one entry of `LEVELS` in `config/strategy/levels.py` (pure, typed, beside the catalogue that reads it;
`config/strategy/` has room), with six parts:

| part | meaning | instrument | market (and calendar) | position | portfolio (P2) |
|---|---|---|---|---|---|
| `key` | what a row is about | (instrument, session) | (market, session) | (trade, close) | (setup, decision session) |
| `provider` | `stored`: feature groups of an entity in `core/model/fields.py::GROUP_TABLE_PREFIXES` (the existing entity extension point of ADR 0047); or `computed`: a named producer with a typed field list | stored `instrument` | stored `market` | computed by `engines/structures/`, `POSITION_FIELDS` | computed by the harness and the picks task, `PORTFOLIO_FIELDS` |
| `pit` | the one read rule the provider applies | the session's partition, ADR 0007 | that session's row only | close t's quotes and the entry facts | trades with S <= D still open after D's close; tonight's ranked list at D |
| `join` | how a row reaches the scope a rule evaluates in: `self`, `broadcast` (one row merged into every candidate's row) or `through <key field>` (the name's membership as known at S) | `self` | `broadcast` per session | `self` (per trade) | `broadcast` per (setup, D) |
| `scopes` | the use sites that may read it (2.13) | screener, universe, entry, case, exit | gate, entry, case, exit | exit | gate, entry, case |
| `licence` | where the licence comes from | `Feature.licence` | `Feature.licence` | the trade's price source | the strictest price source of the trades it reads |

Session / calendar facts are columns of the market row; events are read only through instrument and
market features. Both are rows of the Entities table but not separate providers.

**What adding a level changes, and what it never changes.** A new level adds one `LEVELS` entry, its
field head in `core/model/fields.py`, its provider (a feature-group entity, or a producer with a typed
field list) and, for a new key, its join path. The rule language, `evaluate_group`, the use-site check
(which reads `scopes`), the fail-closed rules and the licence check do not change: they are written
against `LEVELS`, never against a level by name. Test: a fixture level declared only in a test
(stored, `broadcast`, scope `gate`) is readable by a gate rule with no other code change.

**Future example: sector (not built).** Key (sector, session); provider a `rollups/sector/*` entity;
join `through instrument.sector` as known at S's company snapshot (ADR 0007's snapshot rule); scopes
screener, universe, entry, case, exit; licence `Feature.licence`.

**Worked example: portfolio (P2, E15).** ADR 0083 stores no account profile and no positions, so a
portfolio feature describes **the setup's own paper book or tonight's list, never the user's real
holdings**. A rule reading real holdings would need an ADR change.
- Fields (`PORTFOLIO_FIELDS`, `portfolio.<name>`):
  - `open_positions`: the setup's trades open at D;
  - `effective_bets`: `1 / sum w^2` over them after the market factor (2.11);
  - `sector_exposure_max`: the largest share of open trades in one sector (by `instrument.sector` as
    known at each trade's S);
  - `open_premium_at_risk`: the summed collateral of open option trades per slot (one slot per trade;
    no account size);
  - `list_concentration`: the largest share of tonight's ranked list in one sector.
- **Source:** in the harness, the setup's own simulated trades of earlier decision sessions; for
  picks, the forward paper record (`results/edge_paper`) and tonight's ranked list before `top_k`.
  Never `results/screen_picks` of another setup, never a user store.
- **Point in time:** only trades with `entry_session <= D` and `exit_session > D`; tonight's list as
  ranked at D. Because the book at D depends on earlier entries, which a portfolio rule may itself
  have filtered, the harness evaluates the decision sessions of such a setup in order (deterministic,
  property test); a setup that reads no `portfolio.*` field keeps today's independent sessions.
- **Scopes:** gate (stand aside when the book is concentrated), entry, case. Not screener or
  universe (a screener knows nothing of a setup), not exit in P2.
- **No size:** the fields count and share trades; nothing sizes a position (ADR 0083).

**Slice.** The declaration, `LEVELS` with today's four rows and the catalogue reading `scopes`, is part
of E2r (about 40 lines [I]). The portfolio provider is its own P2 slice, E15.


### 2.16 Deferred entity extensions and out of scope (entity fit, G23)

Each extends an existing entity; none needs a new one.

| gap (entity fit) | needed by | smallest generalisation | phase |
|---|---|---|---|
| EF-G6 hedge | B1, B4, B5 | template key `hedge = "none" \| "delta_daily"` (the engine hedges already; `pnl_hedged_mid` exists) | P2 |
| EF-G7 collateral `debit`, `worst_case` | C1, B3, C5, N2, N4 | two more values of the template's `collateral` | P2 |
| EF-G8 positions across names (pairs, baskets) | K7, pairs ideas | a share leg names its instrument (`instrument = "GLD"` or `instrument_from = <feature>`); `pair_spread` becomes the `pair` template | P2 |
| EF-G9 path-aware share exits | breakout, RSI-2, the evaluated ADR 0083 stop | a path-aware share grain; first, exits over `bars/1d` in the time-series harness for named sleeves | P2 |
| EF-G10 sizing (new uses) | A5 (ii), R-H | Book attributes only (G16), never published as a size | P2 |
| EF-G11 cross-instrument references (new) | lead-lag, R-D | a market column (`market_cross_asset@v2`) a gate reads; `canary` stays a Book overlay | P2 |
| EF-G13 chained positions, rolls | the wheel, PMCC | a Book over v2 trades: on `ASSIGNED` enter template B from the delivered shares; rolls stay refused | P2 / P3 |
| EF-G14 selection constraint at entry (minimum credit) | N3 | a template `require` rule at a new use site `select` reading `POSITION_FIELDS` at entry | P3 |
| EF-G15 fill at the next open | overnight ideas | `[outcome] fill = "close" \| "open"` and an open-based column on the share grain | P3 |
| EF-G17 link levels (sector, peers, holdings) | industry and lead-lag ideas | a precomputed instrument feature first; a level by 2.15's recipe only when a rule must compare a name with its group at read time | P2 (sector) / P3 |

**Out of scope.** EF-G16 futures traded as futures: trade through ETFs / ETPs; futures facts enter
only as market features over `rates/futures_curve` and `volatility/vx_futures` (personal). EF-G21
borrow availability: no source; `borrow_bps_annual` stays, and a short pick states that the borrow is
assumed.
---
