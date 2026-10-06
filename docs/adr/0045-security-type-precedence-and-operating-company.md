# ADR 0045: Security-type precedence and the "operating company" applicability

**Status:** accepted (2026-10-06; owner decision). Amends [0042](0042-not-applicable-and-illiquid-values.md)
(`applies_to` `not_etf` becomes `operating_company`; implemented by the companion PR). Clarifies
[0013](0013-universe.md) (no change to the universe's definition). Acceptance check under
[0039](0039-ingestion-workflows-dependencies-and-acceptance.md).

## Context
`apply_identifiers` let the vendor's security type always win over our name rules. Massive types
about 90 preferreds and baby bonds as `CS` (ADAMG "Adamas Trust - 9.125% Senior Notes Due 2030",
ADAML and ACGLN preferred shares), so they became `COMMON_STOCK` (`security_type_source`
`vendor`) and sat in the screen universe, which is stocks and ETFs (ADR 0013). A SPAC is a
shell with a ticker; it stays common stock and in the universe, but it has no earnings.

## Decision
1. **Precedence.** A generic vendor type (Massive `CS`, `OS`, `LT`: all mapped to
   `COMMON_STOCK`) says nothing about being common, so it yields to a more specific result of
   the name rules (`classify.security_type`): `PREFERRED`, `NOTE`, `WARRANT`, `RIGHT`, `UNIT`,
   `ETN`, `ETF`. The row is typed by the name and `security_type_source` is `name_over_vendor`.
   The name rule `ADR` never overrides (it matches "ADS-TEC ENERGY"); a real ADR is typed `ADRC`
   by the vendor. Every specific vendor type (`ADRC`, `FUND` -> `CEF`, `ETF`, `PFD`, ...) still
   wins. FIGI ids are unchanged and old snapshots are not rewritten.
2. **The universe follows without a change to it.** Its `security_types = [COMMON_STOCK, ADR,
   ETF]` filter now drops those rows. ADR 0013 is unchanged: stocks and ETFs.
3. **Acceptance check `reference_classification`** on the `universe-build` step (ADR 0039; it
   SUCCEEDS or FAILS): FAIL when the share of ACTIVE rows typed `name_over_vendor`, or of rows
   where the stored type differs from the name rule's, exceeds `[quality] max_type_disagreement`
   (`sources.toml`). A vendor that retypes its list, or a name rule gone wrong, no longer moves
   the universe silently.
4. **Earnings and SPACs** (companion PR): `applies_to` gains `operating_company` = `COMMON_STOCK`
   or `ADR` and SIC not 6770 (blank-check); a null SIC still applies. It replaces `not_etf`
   for earnings, so earnings of a SPAC are `NOT_APPLICABLE`.

## Consequences
- The first night drops the reclassified rows from the universe (0.8% on the 2026-10-05
  store, under `max_universe_change`); later nights are stable.
- A preferred or note the name rules do not recognise stays common until a rule or the vendor
  catches it; the check measures the disagreement, it does not find these.
- A new vendor type is mapped in `MASSIVE_TYPES`; a new generic one is added to
  `GENERIC_VENDOR_TYPES` (`universe_build.py`).
