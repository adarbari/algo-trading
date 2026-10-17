# ADR 0071: Boolean groups in rule screens

**Status:** proposed (2026-10-17; design: the architect's plan from the Describe-it connector
work, PRs #586-#589; owner 2026-10-17: a tree in the engine, one level in the Builder; Describe-it
precedence is decided case by case and the owner verifies the cases; every criterion keeps its
`hard` / `soft` / `score` mode inside a group; existing formulas stay as they are).
Extends [0029](0029-rule-screener.md) (the finalised spec gains an optional table, its hash
unchanged when the table is absent) and [0041](0041-natural-language-screener-drafts.md) (a part's
`join` becomes a group, not a formula). Spec: `docs/screeners/rules.md`.

## Context
A rule screen ANDs every criterion: `ScreenSpec.criteria` is a flat tuple in funnel order
(`core/model/screen_spec.py`), `decide()` rejects on any gating FAIL or hard MISSING and `score()`
sums every penalty (`strategies/screeners/rules/decision.py`). A trader's "X or Y" therefore becomes
one boolean expression feature, and "except X" a negated criterion or a formula. Describe it already
records, per part, a `join` of `and | or | and_not` and shows it (#586, #589), but the engine ignores
it and the verifier answers an "or" with the doubt "needs one boolean formula"
(`services/drafting/parts/verify.py`). The owner (2026-10-17): connectors "can define condition
between each of these conditions ... ideally we should support them".

A formula hides the logic: the funnel and "why matched" cannot say which side passed, the Builder
cannot edit it, and every "or" costs the trader a formula-accept step. The pieces needed already
exist: the `all / any / not` grammar (`config/strategy/schema.py`, `parse_group`) serves selections
and flags, and `evaluate_group` is Kleene three-valued (`core/model/predicates.py`), the same logic
as the expression language's `or`.

### Options
- **A. Keep formulas.** No engine change; the problems above stay.
- **B. One level of groups by reference.** The top level stays an AND of items; an item is a
  criterion or a group of kind `any` (OR) or `none` (NOT any) whose members are criterion ids.
  Covers "A or B", "except A or B"; not `(A and B) or C`.
- **C. An inline recursive tree.** Complete logic, but inline nesting breaks per-id layering, and a
  tree editor in the Builder fails ADR 0052 on phones.
- **D. A tree by reference in the engine, one level in the Builder (chosen by the owner).** Groups
  name their members by id, and a member may be another group, so the engine and the spec hold any
  boolean expression while criteria stay in the flat `[criteria]` table (layering,
  `enabled = false`, the preview memo, per-criterion result rows and `spec.fields()` keep working).
  The Builder edits one level now; deeper editing is a later UI decision, not a spec change.

## Decision (option D)

### Spec
```toml
[groups.oversold]            # (rsi_low and volume_up) or near_low
any = ["momentum_dip", "near_low"]

[groups.momentum_dip]
all = ["rsi_low", "volume_up"]

[groups.no_earnings]         # except earnings_soon
none = ["earnings_soon"]
```
`CriterionGroup(id, kind, members)` in `core/model/screen_spec.py`, `ScreenSpec.groups = ()` by
default; `groups` joins the allowed rule keys. A group table holds exactly one of `all` / `any` /
`none` plus an optional `enabled`. Validation: group ids pass `validate_id` and share one key space
with criterion ids (never `score`); members are criterion or group ids of the same spec; every
criterion and group has at most one parent, and the graph is acyclic with depth at most 4; a member
disabled by a layer drops out before the size rules; `all` and `any` need 2+ members, `none` 1+, at
most 12; a top-level `all` is refused (it is the screen itself). A group with no parent is a **gate**
and sits in the funnel at its first criterion's position; members are evaluated and reported in
criteria order, so the result is deterministic. A group has no mode of its own; every criterion
keeps its `hard` / `soft` / `score` mode, `tolerance` and `on_miss` wherever it sits.

### Hash and versioning
Additive: with no `[groups]` the canonical JSON (`config/strategy/resolve.py`) is byte for byte
the same, so every finalised `v<N>` (0029) and every harness trial hash (0053) is unchanged; no
format version. Code that predates groups fails closed on the unknown rule key. A test recomputes
every preset hash before and after.

### Evaluation
Criteria are evaluated as today, each giving a **verdict**: whether it rejects, its penalty (0 to
100) and its `on_miss` (`docs/screeners/rules.md`, Decision and Score). A group combines its
members' verdicts bottom up; the screen itself is the implicit `all` of its gates, so with no groups
nothing changes.
- **`all`**: rejects if any member rejects; penalty is the sum of the members'; `on_miss` the most
  severe. (Exactly today's top-level rule.)
- **`any`**: takes the verdict of its best member: one that does not reject before one that does,
  then the lowest penalty, then criteria order. "A or B" with A a near miss and B a hard fail is
  A's near miss; an `any` with a `score` member never rejects, and the Builder labels it so.
- **`none`**: is `all` over its members negated, pushed down to the criteria (De Morgan: not `all`
  is `any` of the negations, not `any` is `all`). A criterion is negated by its operator (`lt` ↔
  `gte`, `gt` ↔ `lte`, `eq` ↔ `ne`, `in` ↔ `not_in`, `is_null` ↔ `not_null`, `between` ↔ `lt` low
  or `gt` high) and keeps its mode and tolerance, so "except RSI < 30" with tolerance 2 is a near
  miss at RSI 29.
- **Missing data** keeps its mode's rule: a hard criterion with no value rejects, a soft or score
  one costs its full penalty. A hard `any` passes on one known passing member (the Kleene result the
  formula gives today, shown in the trace) and rejects when every member is failing or missing, so
  missing data never passes (0030, 0036).

With every member hard the verdict equals Kleene `evaluate_group` (a property test). A
`GroupResult(group, verdict, decided_by, members)` nests: `decide()` and `score()` read the gates
(ungrouped criteria plus top-level groups); members keep their own value, outcome and penalty in the
trace, and only the gate's verdict counts. Reason lines name the deciding member
(`oversold near miss via rsi_low (31; tolerance 2)`, `oversold fail: neither momentum_dip (rsi_low
41) nor near_low (0.12)`). Nightly and the Builder dry run share `evaluate_screen`, so there is one
semantics; the preview funnel shows a gate as one step.

### Results and reads
`results/rule_screen_values` gains group rows (`mode = "group"`, `field` = the kind, the verdict's outcome and penalty, the deciding member) and a nullable
`group_id` (the parent) on member rows, groups included (older partitions read null); `failed` /
`missing` in `results/rule_screen` list gate ids. A shared `is_group_row` sits beside
`is_display_column`, and every reader that filters with one uses both in the same PR. GraphQL gains
`ScreenGroup` (kind, members, parent) and `ScreenCriterion.group`.

### Describe it
A new `services/drafting/contract/groups.py` builds groups from parts' joins: a run of parts joined
by `or` becomes an `any` group, a part joined by `and_not` a `none` group, and a sentence that needs
`(A and B) or C` an `all` inside an `any`, so that case no longer needs a formula. Precedence is not
one global rule: each phrasing ("A or B and C", "except A or B", "A and B, or C") is a golden case
with its expected tree, and the owner verifies the set in the PR 6 review. The Builder states the
draft's tree in plain English ("(A and B) or C", "not D") before it is saved, so a trader sees the
reading. Each part keeps the mode its words ask for ("ideally", "preferably" → `score`). Grouping
applies whenever no member is a pending formula; otherwise the draft keeps today's formula path and
the verifier doubt. Formulas remain for maths. The feedback
save diff (0066) adds groups added, removed or changed.

### Builder and Guide
Design system first (0011, 0025): a `ConditionGroup` component (a titled surface with the kind label,
the #584 connector token between members, an actions slot; `Narrow` story, axe, light / dark
screenshots). The Builder edits one level, a vertical stack, so phones need no variant (0052): "Either
this or the previous", "Exclude (none of)", "Ungroup". A deeper group (from Describe it or TOML) is
shown as one read-only row with its plain-English expression and its members expandable; "Ungroup"
flattens it one level. Preview and pick detail show a gate as one expandable row. Guide entries
(0051): `criterion_group`, `group_all`, `group_any`, `group_none`; coverage for the `group` mode value
and the `ScreenGroup.kind` enum.

## Consequences
- No migration: no screen has `groups`; existing boolean user formulas keep working unconverted
  (question 4).
- Ownership: the spec, evaluation and drafting entries in `core_ownership.toml` and
  `services_ownership.toml` and the results note in `tables.toml` are extended; no new folder.
- Risk: a reader not updated would show group rows as criteria; the reader rule above and a
  contract test guard it. A deep tree is harder to read than a formula's text; the depth cap and the
  plain-English line bound that.
- A tree editor in the Builder later needs no spec or engine change.

### Implementation PRs (each mergeable alone; nothing writes `groups` before PR 5)
1. This ADR.
2. Core: model, parser, validation (tree, acyclic, depth), nested `GroupResult`, decide / score /
   reasons, preview funnel step, `docs/screeners/rules.md`; unit, property (a tree = the equivalent
   formula, Kleene) and preset-hash tests. Architect review.
3. Storage and read: group rows, `group_id`, gate ids, `is_group_row` in every reader, GraphQL and
   schema snapshot, Guide entries and coverage. Architect review.
4. Design system: `ConditionGroup`.
5. Web Builder: spec model, one-level actions, read-only deeper groups, preview, pick detail.
6. Describe it: groups from joins, prompt, verifier, golden cases for the owner to verify, feedback
   diff. Architect review.

### Owner decisions
1. Decided 2026-10-17: a tree in the engine and spec, one level in the Builder (option D).
2. Decided 2026-10-17: precedence case by case, each a golden case the owner verifies (PR 6).
3. Decided 2026-10-17: every criterion keeps `soft` and `score` inside a group (the verdict rules
   under Evaluation).
4. Decided 2026-10-17: existing boolean formulas are left as they are, never converted.
