# ADR 0042: Not applicable and illiquid values

**Status:** accepted (2026-10-05; owner decision). Amends [0023](0023-feature-store.md) (the
`Feature` / `FeatureGroup` declaration gains two fields) and
[0036](0036-session-strictness-for-reads.md) (the `UnknownCode` vocabulary gains two codes).
Builds on [0038](0038-catalogue-named-values.md) (the browser derives nothing from raw rows).

## Context
A table cell with no value read "Unknown" whatever the cause. An ETF has no earnings and a
non-optionable stock has no option chain: that is not a gap in our data. A thin chain with no
usable quote makes `iv30` null for a reason that is also not a gap (options too illiquid to
price). Showing all three as "Unknown" hides which cells deserve a look.

## Decision
1. **Two new `UnknownCode`s**: `NOT_APPLICABLE` (the feature is not defined for the
   instrument) and `ILLIQUID` (an option feature is null because the chain is too thin).
   Everything else stays as ADR 0036 defines it; a real gap is still `NO_PARTITION`, `NO_ROW`
   or `NULL`.
2. **Declared, not inferred.** `Feature.applies_to` is `any` (default), `optionable` or
   `not_etf`; a `FeatureGroup` may declare it for all its features (a feature's own non-`any`
   value wins). `Feature.null_status` names the status column saying why the value is null: a sibling
   column of the same group (`iv30_status`) or another group's as `<group>.<col>@vN`
   (`iv_history`'s features, derived from `iv30`, name `iv30.iv30_status@v1`; the catalogue
   rejects one that is not a declared column). `Feature.illiquid_statuses` lists the status
   values meaning "too thin to price" (`NO_QUOTES`, `WIDE_SPREADS`, `ILLIQUID`, from
   `iv30.ILLIQUID_STATUSES`); each of the two requires the other, and the generic read loader
   knows no group. `NO_CHAIN`, `NO_SPOT`, `IV_FAILED` and the like stay NULL.
3. **The server decides**, in `services/read/instruments/features.py::_value`. Precedence:
   `NO_PARTITION`, then a present value (always wins), then `NOT_APPLICABLE`, then `ILLIQUID`,
   then `NO_ROW`, then `NULL`. Applicability reads only the session's reference snapshot row
   (`optionable` false, `security_type` ETF); a null `optionable` is not "no".
4. **Expression features inherit**, like their licence: not applicable if any feature it reads
   (directly or through other expressions) is not applicable; else illiquid if any status of
   those inputs is an illiquid one (`FeatureSet.applicability`).
5. **Selections are unchanged.** Screeners, backtests and `core.views` see a null, so a
   not-applicable or illiquid instrument never passes a filter on that feature (ADR 0015's
   three-valued logic: UNKNOWN never passes).
6. **The web** shows "n/a" and "Illiquid" (muted) for the two codes and "Unknown" otherwise,
   from one function (`unknownLabel`), with the server's detail as the tooltip.

## Consequences
- A new option or earnings-like group declares `applies_to`; forgetting it only means its
  cells say "Unknown" (the safe side).
- The decision is point-in-time: it uses the reference snapshot of the session, so an
  instrument that became optionable later is not "n/a" in the past.
- GraphQL `UnknownCode` and the web codegen gain the two values.
