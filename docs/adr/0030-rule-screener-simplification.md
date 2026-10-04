# ADR 0030: Rule screens: one list of criteria, no selection, no SKIPPED

**Status:** accepted (2026-10-04; owner decisions). Amends [0029](0029-rule-screener.md)
(missing data, tiers / classify / label, the screen's selection) and
[0015](0015-configs-selections-users.md) (rule screens no longer name a selection;
selections stay for strategies, backtests and Python screeners).

## Context
The Builder funnel showed "Universe 4,203" while the snapshot holds about 11.4k instruments.
The other 7k were dropped by the screen's selection (security type, ACTIVE, optionable)
before any criterion ran, so the funnel hid the step and the rows were never shown or counted
as rejected. The same predicate (`field op value`) existed twice, once as a selection rule and
once as a HARD criterion, with different missing-data behaviour (excluded silently vs
SKIPPED). `tiers` and `classify` only fed a display column, and the Builder could not edit
them. A criterion's stored `label` went stale when its threshold was edited. The `in`
operator on `near_52w` (a three-valued label) hid that "near either extreme" is one number
(`dist_52w`).

## Decision
1. **A rule screen has no `selection`.** It runs over every instrument of the day's universe
   snapshot (the engine passes an implicit match-all selection, so the runner, coverage and
   audit are unchanged). Who is screened is a HARD criterion like any other: the base
   gates `instrument.security_type in [COMMON_STOCK, ADR, ETF]`, `instrument.status = ACTIVE`
   and `instrument.optionable = true` open each screener, and the funnel starts at the
   snapshot. A `selection` key in a screen document is legacy: honoured when present (the immutable
   v1 / v2 presets and copies of them keep their results), never written by the Builder,
   absent from v3. Strategies, backtests and Python screeners keep selections (ADR 0015).
2. **Missing data never passes, and never skips.** Per criterion: HARD missing is a fail
   (`REJECT`, reason `no <field>`, penalty 100); SOFT missing costs the full near-miss
   penalty (10) and leaves the decision to the other criteria; SCORE missing costs 10 (as
   before). The `SKIPPED` decision is no longer produced; stored rows that carry it still
   read. The run summary reports "rejected for missing data" per field instead of skipped.
3. **The spec drops `tiers`, `classify` and `label`.** Flags and columns stay (the preview and
   Ideas show them). The Builder names each criterion from its field, operator and
   threshold, so a name cannot disagree with the rule. The stored `tier` and `class` columns
   are dropped from new rows; readers ignore them in old rows.
4. **The Builder offers `in` / `not_in` for text fields only**, as a multi-select from the
   field's categories. For numbers there is no use that `between` or a comparison does not
   cover. The engine and the spec still accept `in` on any field.
5. **Near the 52-week extremes is `feature.dist_52w <= 0.10`** (the nearer of the distances
   to the high and the low, as a share of price). Which side stays visible in the
   `pct_from_high_52w` / `pct_from_low_52w` columns. `near_52w` stays a catalogue feature.
6. **`vrp_scanner` v3** applies all of this. v1 and v2 are immutable and still parse: their
   `tiers`, `classify` and `label` are accepted and ignored, their `selection` is honoured,
   and an `in` on a number is not rejected for them (the check is on new documents only).

## Consequences
- The funnel shows every step from the snapshot; a rejected row appears with its reason.
- Results per run grow from about 4.2k to about 11.4k rows (`results/rule_screen*`).
- Coverage no longer drops because values are missing; it keeps its other signals (missing
  source tables, run errors, an old universe snapshot).
- The owner decision "any gating criterion missing -> SKIPPED" (2026-10-03) is replaced by
  item 2. Python screeners keep `UNKNOWN`.
- A user screen that sets the removed keys keeps working (`tiers`, `classify`, `label` are
  ignored; `selection` is honoured).
