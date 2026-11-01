> Plan part 2 of 4: sections 2.1 to 2.4a (market conditions, gates, position templates, entry and exit rule). Start at [backend-plan.md](backend-plan.md); the decision is [ADR 0088](../adr/0088-setups-as-positions-and-rules.md).

## 2. The concepts

Each: definition; where it lives (owner from `architecture/*_ownership.toml`); schema; point-in-time
rule; writer and reader; what the product shows.

### 2.1 Market conditions (share and option setups)

**Definition.** A per-session, point-in-time description of the market a setup enters: the
dimension states D1-D12 as open verdict columns, one open stand-aside column, and (P2) a composite
label R1-R12, all read at the close of D. The research framed them for option sellers, but nothing
in them is options-specific: share setups gate and slice on the same columns (`rate_shock_on`,
`post_spike_recovery_on`, `vix_high_on`), hence the name `market_conditions@v1` (G7).

**Where: one new leaf market group (N1).** Adding columns to `market_macro`, `market_breadth` or
`regime_indicators` would bump their versions, and because `regime@v3` reads `indicators`, `macro`,
`trend` and `cross_asset` (`regime.py:65-66,189`) and `regime_indicators@v1` reads `macro`, `trend`
and `breadth` (`indicators.py:149`), every bump would cascade into `regime@v4`, supersede
`market.regime@v3.label` (14 files, the ADR 0049 default, every edge fingerprint) and force a 1971
backfill. So the market conditions are **`market_conditions@v1`**, a leaf group that nothing in the headline
regime reads; `market_macro@v3`, `market_breadth@v1`, `regime_indicators@v1` and `regime@v3` stay
untouched.
- **Folder (F0).** `features/rollups/market/` is at its 10-module cap: split it by kind first into a
  subfolder `features/rollups/market/edges/` ("market facts setups read: the triggers of ADR 0075 and
  the market conditions setups gate on"), moving `triggers.py` there (a module move, no group version
  change), declared in `architecture/layout.toml` with its `__init__.py` docstring and mirrored tests.
- **Group (F1)**, `features/rollups/market/edges/conditions.py`, owner `rollup-computation`, skill
  `add-feature`. It reads the macro series directly with the existing helpers
  (`observations.as_series` / `fresh`) and the stored `market_trend@v2` / `market_breadth@v1` rows,
  and builds its verdicts with the `Card` / `compare` helpers of `indicators.py` (written once,
  imported). Thresholds in `rollups.toml`.

| column | licence | meaning |
|---|---|---|
| `vix9d`, `vix6m`, `vvix`, `vix_obs_date` | personal | latest closes known by the session (null before each series starts) and their shared observation date |
| `vix_pct_252`, `vix_median_252`, `vix_high_20`, `vix_chg_5d`, `backwardation_run`, `vvix_pct_252` | personal | rolling statistics over observations known by the session |
| `y10_chg_63d` | open | 10-year par yield change over 63 sessions, bp (`rates/treasury`) |
| `vix_contango_on`, `vix_front_kink_on`, `index_vrp_rich_on`, `index_vrp_cheap_on`, `post_spike_recovery_on`, `rate_shock_on`, `vvix_high_on`, `vix_low_on`, `vix_high_on` | **open** | the D-state verdicts (our own aggregate, the `regime_indicators@v1` precedent: personal value columns beside open `_on` columns) |
| `short_premium_allowed` | **open** | R-A's complement: not backwardation (VIX / VIX3M >= 1), not VRP-cheap outside a post-spike recovery, not (SPX below its 200-day with VIX rising over 5 sessions in the STRESS band) |
| `earnings_season_share` | open | share of the eligible universe with an expected report in the next 10 sessions (`earnings_expected@v1`) |
| `sessions_to_fomc`, `in_opex_week`, `weekday`, `last_before_weekend`, `fomc_cycle_week` (G18) | open | calendar distances (`events/macro_release` FOMC rows by `known_from`; `core/time/windows.py`) |

P2 (F9): `market_conditions@v2.conditions_label` (R1..R12 / UNCLASSIFIED by a fixed precedence; R9, R10 stay
flags), a bump of the leaf only. `market_triggers@v2` (F3, also a leaf; only `on_market:` edges read
it) adds `post_spike_contango_date` and `sessions_since_post_spike_contango`, computed from the series
as v1 does.

**Licence (H1).** Every verdict a trader may see is a stored column declared open; raw VIX-family
values stay personal. The ADR amends ADR 0069 decision 4 / 0047 to name these columns (owner decision
2). Reasons name the condition ("the VIX curve is inverted"), never a value. No gate or state reads an
expression feature over personal inputs.

**Point in time.** Every input is the latest observation known by the session; all VIX-family series
arrive one session late (`release_lag_days = 1`). A ratio of two series is null unless both share the
observation date. No hysteresis (flips are visible in the slices); `regime@v3`'s label keeps its
5-session hold.

**Relation to `regime@v3`.** Unchanged in every respect: the headline regime, the ADR 0049 default
label, the Regime page and the harness's existing slices. The new group is a leaf beside it.

**Versioning.** `market_conditions@v1` is backfilled by `market-rollups --only market_conditions@v1` from
the VIX series' start (1990; columns null until each input starts); a threshold change is
`market_conditions@v2`, which changes only the fingerprints of edges that gate or slice on it.

**Product.** Guide entries for every verdict column; Regime-page cards for them only if the owner
wants them (owner decision 2: `cards.toml` entries reading the leaf group, a later slice).

### 2.2 Conditions on a setup: the edge gate, slices, regime variants

**Definition (G10).** A gate is a rule (2.13) at use site `gate`: a `Group` over open market and
calendar fields, read at D. It is decided by the ADR 0049 `RegimeGate` decision, unchanged: TRUE =
open, FALSE = closed, UNKNOWN = unknown (fail closed, "regime unknown"). One decision serves the
screener's own ADR 0049 gate and the edge gate. The screener's own `pause_in` stays as it is in
`[regime.screeners.<id>]` and is read as the rule `label not_in pause_in` over the label's declared
domain (G9-M2): a label outside the known labels is read as missing first, so it stays "regime
unknown" exactly as `RegimeGate.known` does today (`gate.py:41`), never open; the edge gate is written as
a rule. The first-draft `{field, require}` form is dropped: `require = true` is the rule
`field eq true`.

**Where (owner `run-overlays`, amends ADR 0049).**
- `config/strategy/regime.py` parses `gate` with `parse_group` and checks it with
  `FieldCatalog.check(..., site = "gate")`: market fields only (`market.*`, which holds the calendar
  facts), any licence, which enters the trial's (ADR 0088 decision 7 replaces H1's "open licence only"). The edge document's `gate` key is
  parsed by this module (`document.py` gains the key name only): a gate is not specific to options (X5
  gates on `regime@v3.label`).
- `engines/screening/gate.py`: the open / closed / unknown decision becomes a pure function of a
  `Truth` (`evaluate_group` over the session's market row, `services/screening/regime.py::session_market`
  reading every field the rule names), which the `RegimeGate` uses and other callers use directly. The
  reason names the first FALSE or UNKNOWN rule by its Guide term, never a value.
- Edge document:
  ```toml
  [gate]  # VIX curve upward AND no scheduled FOMC within 2 sessions
  all = [
    { field = "market.market_conditions@v1.vix_contango_on", op = "eq", value = true },
    { field = "market.market_conditions@v1.sessions_to_fomc", op = "gt", value = 2 },
  ]
  # or: gate = { all = [{ field = "market.market_conditions@v1.short_premium_allowed", op = "eq", value = true }] }
  # or: gate = { all = [{ field = "market.regime@v3.label", op = "not_in", value = ["STRESS", "CRISIS"] }] }
  # (always a group: `parse_group` takes exactly one of all / any / not, as a selection's `where`)
  ```
  `[[variants]]` may override `gate` or set `gate = "none"`. A null `sessions_to_fomc` (the schedule
  not known by D) makes the gate UNKNOWN, so the session is skipped and sliced `unknown`, never open.

**How it is applied (N2).** The edge gate never rides `screen_session` or the `[regime].enabled`
switch (off by default), which would turn closed sessions into PAUSED rows with no picks to measure.
- **Harness:** screens with the edge gate off, calls the predicate per decision session and tags it
  open / closed / unknown; the edge's result is the open rows; the rows `slice_kind = "gate"`,
  `slice_value = open | closed | unknown` are stored beside it. The closed slice is the inverse-rule
  decoy (R-A's "sell only in backwardation") at no extra run; open vs closed Welch t is the gate's
  test. The time-series harness (which never calls `screen_session`) does the same.
- **Picks task:** applies the edge gate always, whatever `[regime].enabled` says: closed -> a new
  stored status `gate_closed` with the reason; unknown -> `skipped` with "regime unknown". New storage
  (G-M1, E9): `results/edge_picks` has no `paused` status today (`STATUSES` at
  `edge_picks/night.py:39`; `paused` is only a per-name read code from a screener row's PAUSED
  decision, `pick_edges.py:25,87`). `pick_edges.py` maps `gate_closed` to its `paused` read code
  explicitly, with the gate's reason, kept apart from the screener's own per-name PAUSED.
- **Composition with a screener's own ADR 0049 `pause_in`** (e.g. `vrp_scanner` in STRESS /
  CRISIS, when `[regime]` is enabled): a pick needs both open; the gate and state slices refer to the
  edge gate only, and a row the screener's own gate paused is counted under its existing PAUSED rule,
  not as a closed edge gate.
- Gated and ungated are compared on sessions where the gate is known (VIX3M starts 2007-12), never
  across samples.

**Slices:** `verdict.toml [slices] labels = ["market.regime@v3.label",
"market.market_conditions@v1.vix_contango_on"]` (site-wide, display rows `slice_kind = "state"`,
in-sample / out-of-sample like `regime_part`); P2 adds `conditions_label`. **Regime variants:** a variant
with its own `gate` (`contango_only`, `post_spike`), a trial.

**Per-name conditions** stay in screeners and in the structure: the report skip is the selector's
`skip_report_in_life` (2.4); ex-div and front-kink reuse `ex_div_before_*` and `term_ratio_next_30`.

**Product.** "Paused: the VIX curve is inverted" on the setup; Guide entry "why nothing is on today"
(R-A); per-state rows on the setup page.

### 2.3 Setup state per session (v1)

**Definition.** **ON** (gate open, stored verdict works / promising), **OFF** (verdict not works /
promising), **PAUSED** (gate closed: stand aside), **UNKNOWN** (gate unknown, or no usable stored
verdict), each with a reason. Per-regime rows are shown, not used (M4: a per-slice decision would mine
about 19 slices).

**Stored.** One new stored status: the gate outcome is the pick status `gate_closed` on
`results/edge_picks` (existing writer, ADR 0081; added in E9, G-M1); the verdict is the stored headline in `results/edge_verdict` (unchanged
grain). **Computed** on read by one pure, versioned rule in
`services/read/evaluation/verdict/state.py` (owner `edge-verdict`), bounded by the session (ADR
0083's point-in-time rule).

**Licence (N6).** A setup whose verdict rests on personal evidence is not listed at all for a viewer
without that licence (ADR 0084 decision 1, the E1 gate), so it has no state for them; it is never
shown as UNKNOWN, which would hint at something hidden.

**Product.** A state chip on every setup and idea; Ideas unchanged (owner decision 5). P2: WATCH and
per-regime decisions once slices are counted as trials or held out.

### 2.4 Position templates and contract selection

**Definition.** A position is a list of legs. A leg is either **shares** (a signed quantity) or **an
option** chosen at entry from one session's chain by a rule. A template adds a collateral rule (the
capital its return is measured on) and, for option legs, fixed assignment rules. Templates are site
config. An edge outcome names a template by the new key `position` and overrides its parameters.
The existing `structure` key stays what it is today, the enum of the `expires_otm`,
`option_model_pnl` and v1 `option_pnl` outcomes (`CHAIN_STRUCTURES`, `MODEL_STRUCTURES`), and a
document that sets both keys is refused. A share setup is one share leg. An option setup has at
least one option leg. A covered call is a share leg plus a short call.

**Existing stock edges (G1) need not change now.** No document gains a key, and no version or
fingerprint moves. One pure function, `position_of(outcome)` in `config/edges/positions/templates.py`,
returns the `position` key when set. Otherwise it maps a return outcome's `side`: `long` ->
`long_shares`, `short` -> `short_shares`, `long_short` -> one of each, per leg of the book. The read
model (the example position, the Guide) and the trade contract (2.5a) call it. `pair_spread` and
`portfolio_return` are not one position and keep their own shapes (a `pair` template is P2). The
template is the shared vocabulary. A later share edge version may write `position = "long_shares"`,
which means the same thing.

**Where.**
- Templates: `config/site/positions/templates.toml` (new folder, declared in
  `layout_docs_config.toml`). Now: `long_shares`, `short_shares`, `short_put`, `put_spread`,
  `covered_call`, `short_straddle`, `iron_fly`; the others when an edge names one. Typed
  fail-closed in `config/edges/positions/templates.py`, with `chain.py` moved beside it
  (`config/edges/` is at its cap). Owner `edge-documents`.
- **Selector (one), for option legs:** `features/rollups/options/wing_search.py` is generalised from
  "the put / call of a target delta at a target DTE" to "the option legs of a template" (features
  layer, pure). The tie rule stays: open interest, then the lower strike, then the contract id.
  `put_wing`, `call_wing`, the engine, the Cboe writer and the example position call it. A share leg
  needs no selection.
- **Engine:** `engines/structures/`, a new folder and a new responsibility `option-structures`, added
  to the engines independence contract. It does the marking to each close, the exits of 2.4a,
  assignment, early exercise, the exit fallback and the hedge, for the option legs and any share leg
  held with them (a covered call). It takes over `option_paths.py`'s marking and hedging, which are
  deleted from the task. It imports `features` (the selector), `config` and `quant`, never `data` or
  `storage`. A share-only position never runs the engine: its trades come from the bars grain (2.5a).
- Maths: `quant/edges/chain_pnl.py` (owner `quant-chain-pnl`) gains multi-leg weights and per-leg
  Greeks (our own Black-Scholes at each leg's implied vol from its mid).

**Template sketch:**
```toml
[[template]]
id = "long_shares"
legs = [{ kind = "shares", qty = 100 }]
collateral = "notional"         # entry close x 100
[[template]]
id = "short_shares"
legs = [{ kind = "shares", qty = -100 }]
collateral = "notional"         # entry close x 100; borrow from [edge_costs] borrow_bps_annual
[[template]]
id = "short_put"
legs = [{ kind = "option", right = "P", qty = -1, strike = "delta", delta = 0.30 }]
collateral = "cash_secured"     # strike x 100
[[template]]
id = "put_spread"
legs = [{ kind = "option", right = "P", qty = -1, strike = "delta", delta = 0.30 },
        { kind = "option", right = "P", qty = 1,  strike = "delta", delta = 0.10 }]
collateral = "max_loss"         # width x 100 - credit
[[template]]
id = "covered_call"
legs = [{ kind = "shares", qty = 100 },
        { kind = "option", right = "C", qty = -1, strike = "delta", delta = 0.30 }]
collateral = "notional"         # the share leg: spot x 100
# short_straddle (collateral regt), iron_fly (max_loss); an option leg may carry its own tenor_days
```
Option edge outcome:
```toml
[outcome]
kind = "option_pnl"
position = "short_put"          # the template (new key; `structure` stays the old kinds' enum)
strike_delta = 0.20
tenor_days = 30
expiry_cycle = "monthly"        # monthly | weekly | any
skip_report_in_life = true      # UNSELECTABLE (REPORT_IN_LIFE) if an expected report falls before the selected expiry
start_offset_sessions = 1       # entry (2.4a): S = D + 1; legs selected and filled from S's chain (>= 1, as today)
horizon_sessions = [21]         # exit (2.4a): the hold cap
book = true                     # store the daily mark path (2.5)
[outcome.exit]                  # 2.4a
take_profit = 0.5               # close when the mark has captured half the credit
stop_loss = 2.0                 # close when the loss reaches 2 x the entry credit
exit_dte = 21
when = { any = [{ field = "position.distance_to_strike_pct", op = "gt", value = -0.02 }] }  # optional exit condition (2.4a)
```
Strike rules are `delta`, `atm` and `otm_pct` only. There is no target-yield rule (fitness test) and
no `roll` key.

**Parameters and position choice by rule (G11): case values.** `position`, `strike_delta`,
`tenor_days`, `expiry_cycle`, `take_profit`, `stop_loss` and `exit_dte` take a literal or a case
value. Each `when` is a rule at use site `case` (instrument and market fields, read at D):
```toml
[outcome.tenor_days]            # tenor 30 when IV rank is high, else 45
cases = [{ when = { all = [{ field = "rollup.iv_history@v2.iv_rank_252d", op = "gte", value = 0.8 }] }, value = 30 }]
default = 45
```
- The first case whose rule is TRUE gives the value; `default` only when every case is FALSE. A case
  that is UNKNOWN before a TRUE one makes the name UNSELECTABLE (reason `CASE_UNKNOWN`), never the
  default: missing data never chooses a branch.
- Values are literals of the parameter's type, so the set of concrete points is finite and declared.
  `position` cases choose among templates of one kind (all with an option leg, or all share-only), so a
  setup's trades come from one grain (fitness test).
- Resolution is one pure function, `engines/selection/cases.py::resolve_case` (beside the selection
  evaluator, the same kind: a rule over one session's fields), called by the harness at each D (E13),
  by the picks task and the example position at the served session (E9), never by the engine: the
  engine and the writer receive the resolved concrete point.
- Rows stay keyed by the concrete point: `position_key` holds the resolved template and parameters,
  never the case rule, so two setups (or a case and a grid point) that resolve to the same point share
  rows. The writer writes the union of the points a setup's cases can produce. A case rule is part of
  the variant's identity (a trial); another threshold is another `[[variants]]` entry (grids stay over
  literal parameters, `grid.py` unchanged).

**Selection:** from S's chain alone:
- the expiry by tenor and cycle;
- the strikes by our own delta;
- the quote filters `[option_quotes]`: two-sided, not crossed, spread <= 15% of mid, volume or OI > 0;
- the report skip against the selected expiry, from `earnings_expected@v1` (history-safe). N3: an
  instrument whose `instrument.security_type` does not report (ETF, index, closed-end fund) has no
  report and passes; an unknown date fails only for a reporting type, the `no_earnings` variant's
  rule.

A failure is UNSELECTABLE with a reason and is counted: the name is not entered, which is not a
missing P&L.

**Exits** at closes only (2.4a): one ordered list (take profit, stop loss, DTE, then an optional exit
condition), else expiry or the hold cap. Each rule is a variant, and so a trial.

**Assignment and early exercise** are fixed rules (F1, §7.10):
- An ITM American short at expiry is assigned at the close. For a position without a share leg, the
  shares are sold at the next session's close.
- European cash-settled index roots (a declared table, as in ADR 0084 decision 4) settle at intrinsic
  on the close. This stands in for the AM settlement and is disclosed.
- A short ITM call is assigned at the close before an ex-date when the dividend (`events/dividend`)
  exceeds its extrinsic value.
- A deep ITM short put is flagged (assigned in P2).

**Costs** (harness only). Option legs, `verdict.toml [option_costs]`:
- `levels = ["mid", "effective", "full"]`;
- `effective_share_by_legs = {1 = 0.75, 2 = 0.65, 4 = 0.53}`;
- `commission_usd = 0.65` per contract per side;
- `full` = the whole half-spread per leg at entry and exit (none at expiry).

The option verdict rests on `full`, and single names use `full` everywhere. Share legs keep the
share setups' own costs: `[edge_costs] levels_bps` and the document's `cost_bps` (ADR 0064).

**Point in time.** Selection reads S's chain and our own delta only. The expected report date is the
one known at S. Ex-dates are facts of record read by the outcome, which may look forward.

### 2.4a Entry and exit rule

**Definition.** One entity for both kinds: when a trade enters and what ends it. It is the entry
and exit part of an edge's `[outcome]` and of each variant's override; a variant that changes it is a
trial. The settings below are the defaults; an entry condition and an exit condition are optional
rules (2.13, G11) on top of them.

| part | key | share setup | option setup | status |
|---|---|---|---|---|
| entry offset | `start_offset_sessions` | S = D + offset, entered at S's close; every edge sets it (the parser default 0 is refused), 1 = the next close | the same rule: >= 1, the legs selected and filled from S's chain (as v1 `option_pnl` does); the gate is read at D | exists for both; below 1 refused for every non-event schedule (`config/edges/document.py:738-741`: the screen runs after D's close) |
| horizon | `horizon_sessions` | the exit: the close of the h-th session after S | the hold cap | exists |
| expiry | implied by an option leg | n/a | held to expiry when it falls before the cap; assignment rules (2.4) | new (E3a) |
| take profit | `[outcome.exit] take_profit` | P1 via E3c (a share path walker) | close when the mark captures this share of the credit | new (E3b) |
| stop loss | `[outcome.exit] stop_loss` | P1 via E3c: as take profit | close when the loss reaches this multiple of the credit | new (E3b) |
| DTE | `[outcome.exit] exit_dte` | n/a | close at this many days to expiry | new (E3b) |
| path filter | `max_drawdown` | a hit also needs the window's dip within it (unchanged) | refused: an exit, not a filter | exists |
| entry condition | `[outcome.entry] when` (use site `entry`), `within_sessions` (default 1) | the same rule for both kinds: at each close t from D to D + `within_sessions` - 1, the first t whose instrument and market fields make it TRUE; S = t + `start_offset_sessions`; never TRUE in the wait: not entered (`NOT_TRIGGERED`, counted, not a missing P&L) | as shares; the legs then selected at S. The writers (E4 Cboe, E5 history) write every S in [D + offset, D + `within_sessions` - 1 + offset] for the screened names of an edge with `[outcome.entry]`; until they do, an entry condition on `option_pnl` is refused (G9-M3) | new (E13; shares: a harness mapping over `forward_returns@v2`'s rows; options after the writers cover the wait) |
| exit condition | `[outcome.exit] when` (use site `exit`) | P1 via E3c (a share path walker) | instrument, market and position-level fields at each close; `exit_kind = CONDITION` | new (E3b) |

**No entry at D's close (G-H1).** The screen, the gate (`market_conditions@v1` at D) and the
picks are known only after D's close, so entering at that close is lookahead; the existing refusal
of an offset below 1 applies to option setups too (E2 test).

Evaluated exits act at closes only. The first that fires ends the trade and becomes its `exit_kind`
(`HORIZON`, `EXPIRED`, `ASSIGNED`, `EARLY_ASSIGNED_DIVIDEND`, `TAKE_PROFIT`, `STOP_LOSS`, `EXIT_DTE`,
`CONDITION`, `DELISTED`).

**One ordered list of exit rules (G11).** `take_profit`, `stop_loss` and `exit_dte` stay as settings
and compile, at parse, to rules over position-level fields with their own kind
(`position.profit_share_of_credit gte take_profit` -> `TAKE_PROFIT`;
`position.profit_share_of_credit lte -stop_loss` -> `STOP_LOSS`; `position.dte lte exit_dte` ->
`EXIT_DTE`), followed by `when` (`CONDITION`). The engine evaluates that one list at each close;
several TRUE at one close: the first in the declared order wins (deterministic). Expiry, assignment
and the hold cap stay the engine's fixed rules. So the engine has one exit path, not one per key.

**When a rule may act (the one point-in-time rule, 2.13).** A rule observed at close t from catalogue
fields (instrument, market) acts no earlier than the next close, t + 1: nightly features of t exist
only after t's close, the same reason an entry offset is >= 1 (G-H1). A rule over position-level
fields only (the three settings, or a `when` naming only `position.*`) acts at t's own close, as the
marks it reads are t's closing quotes, the convention the declared exits already use. A rule that
mixes both acts at t + 1. Fail closed for exits (G9-M4): a rule naming a field with no rows over the
evaluation range is refused at run start (2.13); a trade whose exit rule was UNKNOWN on more than
`exit_unknown_share` of its closes is UNMEASURED (counted, kept out of the evidence). The writers store
only the count of UNKNOWN exit evaluations per row (`exit_unknown_closes`, a column, never a status);
the harness applies the share from `verdict.toml [exit_rules] exit_unknown_share`, typed outside
`VerdictSettings` (no fingerprint shift), and run-level coverage is the existing `excluded_coverage`
rule (ADR 0053), with no second no-verdict bound (R-1). Below that share an
UNKNOWN exit rule does not fire at that close (no exit on data we do not have); the trade
goes on to the next close, the existing exit fallback covers a missing last quote, and the count of
UNKNOWN evaluations is a reported measure.

**Position-level features (G12).** Facts that exist only while a trade is open, declared once in
`POSITION_FIELDS` (`config/edges/positions/fields.py`: name, type, unit, which leg kinds it applies
to, Guide entry), named `position.<name>` (a new field head in `core/model/fields.py`), allowed only
at use site `exit`:

| field | meaning | kinds |
|---|---|---|
| `days_held` | exchange sessions since S | both |
| `move_since_entry_pct` | the underlying's close change since S's close | both |
| `profit_share_of_credit` | P&L to date / entry credit (negative = loss) | credit positions |
| `mark_loss_share_of_collateral` | mark loss to date / collateral (the running `max_adverse`) | option |
| `position_delta` | the summed leg deltas x qty, our own Black-Scholes | option |
| `distance_to_strike_pct` | (spot - nearest short strike) / spot, signed toward ITM | option |
| `dte` | calendar days to the nearest expiry | option |

- Computed by `engines/structures/` at each close t from t's chain quotes and bar and the trade's
  entry facts (strikes, credit, entry spot, expiry), never from a later session; not stored as
  catalogue features and not in the outcome row, which keeps only the result (and the mark path when
  `book = true`). A field that does not apply to the position's legs is refused at parse.
- The catalogue fields an exit rule names are read for each close of the window by the caller (the
  option-outcomes task, the history writer), each from its session's partition, and passed to the
  engine as one row per close: the engine stays pure (imports no `data` / `storage`).
- `position_key` includes the canonical form of the exit rule list, so two rules are two rows (as
  G-M6 for `take_profit`), and the row's `licence` is the strictest of its price source and its exit
  rule's fields.
- Share setups: the same fields once the path-aware share grain exists (P2).
 Share setups get no evaluated stop or take profit in P1. `forward_returns@v2` stores the
window's dip (`fwd_max_drawdown`) but not the session it happened, so a stop exit from it would be a
guess; it needs the bars path in a new grain version (P2).

**The historical exit rule (ADR 0083 decision 3), for both kinds.** It is **not built** on `main`:
there is no `[exit_rule]` setting and no code, and ADR 0083 orders it after the Ideas and Test
slices. It is a published reading of the setup's evidence, never an evaluated exit. It is computed
from the evaluation's own winners, so feeding it back into the evaluation would be circular. One rule
over the trade contract (2.5a):
- *Stop* = the 80th percentile of `max_adverse` over the `hit` trades of the verdict's basis (its
  screener and horizon, ADR 0065) in the canonical run. It is read only through
  `services/read/evaluation/runs.py`, with `oos_hidden`, the 45-day retention, and PRUNED distinct
  from NOT_STORED, as ADR 0083 says.
  - Shares: `max_adverse` is today's `edge_trades.max_drawdown` (long picks only: picks are long,
    `edge_picks/night.py:64`, ADR 0083 d3). Ledger rows written before E6a have a null `max_adverse`,
    so the share rule reads the `max_drawdown` alias, never UNKNOWN for every existing run. It is
    shown as a price below the reference close. A short adverse move stays null in P1: the stored
    legs hold only `pick_mdd` (`legs/rows.py:172`), and adding it would bump `LEG_VERSION`
    (`legs/key.py:20`), a full rerun.
  - Options: the worst mark-to-market loss over the trade as a share of collateral. This is a scalar
    the engine stores on every v2 row from its daily marks. It is shown as "close if the position's
    loss reaches $X".
- *Fallback*, with fewer winners than `[exit_rule] min_winners` (value chosen in E12a, as ADR 0083
  leaves it to the implementing PR):
  - shares: 2 x `momentum.atr_14@v1` at the session, labelled as ADR 0083 says;
  - options (owner decision 8, recommended (d), an ADR 0083 amendment in 0087): **the published
    exit of an option setup is its own evaluated rule**: the declared `[outcome.exit] stop_loss`,
    `take_profit` and `exit_dte`, which the backtest used, so the trader sees the rule that was
    tested. The 80th-percentile stop over `max_adverse` is used only when the setup declares no
    `stop_loss`; with fewer winners than `min_winners` it is UNKNOWN, "too few winning trades" (an
    ATR of the underlying does not become a loss on an option position without a model).
- *Hold*:
  - shares: the verdict's stored `basis_horizon`;
  - options: the earlier of the hold cap and the selected expiry (from the example position, 2.8).
- *Unknown, never filled* (ADRs 0036, 0062): no ledger, no `atr_14` row, no basis.
- **Where:** `services/read/evaluation/positions/exit_rule.py`. This is a new subfolder because
  `services/read/evaluation/` is at its 10-module cap. New responsibility `pick-positions` (the
  example position and the historical exit rule, `add-responsibility`).
  - `[exit_rule]` (`min_winners`, `stop_percentile = 0.80`, `atr_multiple = 2.0`) sits in
    `verdict.toml` (`config/site/` is at its file cap). It is typed by its own `ExitRuleSettings` in
    `config/edges/positions/exit_rule.py` (the folder E2 creates; `config/edges/` is at its cap),
    outside `VerdictSettings`. It is not a judge input, so it never enters `settings_hash` or the
    fingerprint (fitness test). `config/edges/verdict.py` only learns to skip the section, a one-line
    change in its known-sections list, which E12a makes before E6b edits the same file (G-M4).
  - **Point in time:** the canonical run's `range_to <= S` and only trades with `exit_session <= S`
    (ADR 0083's bounds); a past-session test.
  - **Two slices (G-M3).** The stop rests on the verdict's basis (`basis_screener`,
    `basis_horizon`), which `results/edge_verdict` does not store yet (`edge_schemas.py:308-321`;
    ADR 0083 decision 2 adds them with a `JUDGE_VERSION` bump, the trader-site track's Ideas slice,
    "T-basis" below). **E12a, shares** reads `edge_trades.max_drawdown` (exists) and needs only
    T-basis and E2's folder: it is the trader-site track's exit-rule slice (one PR, never twice) and
    waits on nothing in the option engine. **E12b, options** reads v2 `max_adverse` and the declared
    exits, after E3b and E6a. T-basis lands before E6b, so each fingerprint shift is re-stored once.
