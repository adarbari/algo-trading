# ADR 0071: Boolean groups in rule screens

**Status:** proposed (2026-10-17; design: the architect's plan from the Describe-it connector
work, PRs #586-#589; awaiting the owner's decision on the questions at the end). Extends
[0029](0029-rule-screener.md) (the finalised spec gains an optional table, its hash
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
- **B. One level of groups by reference (recommended).** The top level stays an AND of items; an
  item is a criterion or a group of kind `any` (OR) or `none` (NOT any) whose members are
  criterion ids. Criteria stay in the flat `[criteria]` table, so layering, `enabled = false`, the
  preview memo, per-criterion result rows and `spec.fields()` keep working. Covers "A or B",
  "except A" and "except A or B"; not `(A and B) or C`.
- **C. A recursive tree `all_of / any_of / not`.** Complete logic, but inline nesting breaks
  per-id layering, the Builder needs a tree editor that fails ADR 0052 on phones, drafting must
  emit trees, and funnel, penalty and "failed" attribution are unclear at depth.

## Decision (if B is accepted)

### Spec
```toml
[groups.oversold]
any = ["rsi_low", "near_low"]

[groups.no_earnings]
none = ["earnings_soon"]
```
`CriterionGroup(id, kind, members)` in `core/model/screen_spec.py`, `ScreenSpec.groups = ()` by
default; `groups` joins the allowed rule keys. A group table holds exactly one of `any` / `none`
plus an optional `enabled`. Validation: group ids pass `validate_id` and share one key space with
criterion ids (and never `score`); members are criterion ids of the same spec (a group id fails:
"groups do not nest; use a formula"); a criterion belongs to at most one group; a member disabled by
a layer drops out before the size rules; `any` needs 2+ members, `none` 1+, at most 12; **every member
is `hard`** (a soft, score or model `score` member fails: a near-miss band has no meaning inside a
group). A group sits in the funnel at its first member's position; members are evaluated and reported
in criteria order, so the result is deterministic.

### Hash and versioning
Additive: with no `[groups]` the canonical JSON (`config/strategy/resolve.py`) is byte for byte
the same, so every finalised `v<N>` (0029) and every harness trial hash (0053) is unchanged; no
format version. Code that predates groups fails closed on the unknown rule key. A test recomputes
every preset hash before and after.

### Evaluation
Members are evaluated as today; the group's truth is `evaluate_group`: `any` is TRUE if a member is
TRUE, else UNKNOWN if one is UNKNOWN, else FALSE; `none` is its negation. An UNKNOWN group is
MISSING and, being hard, rejects, so missing data never passes (0030, 0036); an `any` with one TRUE
member and one missing passes because the known member decides (the formula's behaviour today, shown
in the trace). A `GroupResult(group, outcome, members)` is a gate: `decide()` and `score()` read
ungrouped criteria plus groups, a failed or missing group costs `FAIL_PENALTY` once, members keep
their value and outcome for the trace with no penalty. Reason lines name the members
(`oversold fail: none of rsi_low (41), near_low (0.12)`). Nightly and the Builder dry run share
`evaluate_screen`, so there is one semantics; the preview funnel shows a group as one step.

### Results and reads
`results/rule_screen_values` gains group rows (`mode = "group"`, `field` = the kind) and a nullable
`group_id` on member rows (older partitions read null); `failed` / `missing` in `results/rule_screen`
list gate ids. A shared `is_group_row` sits beside `is_display_column`, and every reader that
filters with one uses both in the same PR. GraphQL gains `ScreenGroup` and `ScreenCriterion.group`.

### Describe it
A new `services/drafting/contract/groups.py` builds groups from parts' joins: a run of parts joined
by `or` becomes an `any` group, a part joined by `and_not` a `none` group (extended over a following
or-run, "except A or B"); OR binds tighter than AND. It applies only when every criterion is hard and
none is a pending formula; otherwise the draft keeps today's formula path and the verifier doubt,
which then fires only when grouping was impossible. The prompt drafts each side of an "or" as its own
criterion. Formulas remain for maths, `(A and B) or C` and or-logic over soft or score intent. Golden
cases gain expected `groups`; the feedback save diff (0066) adds groups added, removed or changed.

### Builder and Guide
Design system first (0011, 0025): a `ConditionGroup` component (a titled surface with the kind label,
the #584 connector token between members, an actions slot; `Narrow` story, axe, light / dark
screenshots). One level is a vertical stack, so phones need no variant (0052). The Builder renders
groups in place with "Either this or the previous", "Exclude (none of)" and "Ungroup"; preview and
pick detail show a group as one expandable row; the plain-English line writes "(A or B)" and "not C".
Guide entries (0051): `criterion_group`, `group_any`, `group_none`; coverage for the `group` mode
value and the `ScreenGroup.kind` enum.

## Consequences
- No migration: no screen has `groups`; existing boolean user formulas keep working unconverted.
- Ownership: the spec, evaluation and drafting entries in `core_ownership.toml` and
  `services_ownership.toml` and the results note in `tables.toml` are extended; no new folder.
- Risk: a reader not updated would show group rows as criteria; the reader rule above and a
  contract test guard it.
- `(A and B) or C` stays a formula; moving to option C later is additive (a member that names a
  group), so this choice does not close it.

### Implementation PRs (each mergeable alone; nothing writes `groups` before PR 5)
1. This ADR.
2. Core: model, parser, validation, `GroupResult`, decide / score / reasons, preview funnel step,
   `docs/screeners/rules.md`; unit, property (group = equivalent formula, Kleene) and preset-hash
   tests. Architect review.
3. Storage and read: group rows, `group_id`, gate ids, `is_group_row` in every reader, GraphQL and
   schema snapshot, Guide entries and coverage. Architect review.
4. Design system: `ConditionGroup`.
5. Web Builder: spec model, actions, rendering, preview, pick detail.
6. Describe it: groups from joins, prompt, verifier, golden cases, feedback diff. Architect review.

### Owner decisions
1. B (one level `any` / `none`) or C (full tree). Recommended: B.
2. Describe it precedence: OR binds tighter than AND, "except" covers the next part or or-run.
   Recommended: yes.
3. Soft or score criteria inside groups: forbidden in v1, or a "soft any" scored by its best member.
   Recommended: forbidden.
4. Existing boolean user formulas: leave them, or offer conversion. Recommended: leave.
