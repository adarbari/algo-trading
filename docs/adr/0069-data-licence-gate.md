# ADR 0069: The data-licence gate: every path that serves per-name values

**Amended by [0088](0088-setups-as-positions-and-rules.md)** (proposed, 2026-11-01): decision 4: a gate's fields count toward the setup's licence; no site-wide open verdict column required.

**Status:** accepted, amended by [0083](0083-workflow-first-trader-site.md) (Ideas drops a withheld pick instead of showing its name) (2026-10-16; design: the architect's review of the enforcement PR; the two
owner defaults below are recommended and stand unless the owner changes them). Enforces
[0028](0028-ibkr-enrichment-source.md) (licence tags) and [0064](0064-edge-evidence-series-and-trade-ledger.md)
decision 10 (`users.toml` `licences`); uses [0040](0040-identity-and-roles.md) (roles grant no
licence), [0056](0056-role-scoped-causes.md) (public kind `LICENCE`) and
[0015](0015-configs-selections-users.md) (missing data never passes). Code:
`src/algotrade/services/licences.py`; fitness test `tests/architecture/api/test_licence_gate.py`.

## Context
Free personal-licence analyst features (FMP, Finnhub) are about to join the IBKR-derived ones
(13 per-instrument and 32 market fields are `personal` today: VIX, HY / IG OAS, S&P 500 and
Composite trend, `bear_prob_6m`). Only the edge ledger enforced a licence; every other read
served stored values to any user.

## Decision
1. **One gate.** `held_by` (the registry's licences: `open` for everyone, others only when
   listed; a role grants none), `licence_of` (a field's own licence; an expression's strictest of
   its inputs) and `hidden_fields`. A field the viewer does not hold is never read: UNKNOWN with
   kind `LICENCE` in the read model (`ReadContext.licences`), missing in a screen (a hard criterion
   on it never passes), `unavailable` in a series, no sample in a formula check, no live IBKR quote
   and no `verification/ibkr` row.
2. **Fail closed.** `held` has no default (`HARNESS_ALL` where a caller reads for no user: the
   edge harness, backtests, training, which record the licence of what they read, ADR 0064). A
   catalogue name that does not resolve (a run owner's own expression feature, a retired field)
   counts as `personal` for a viewer without the licence (a live read; a stored run is gated
   by its own record, decision 3).
3. **Nightly runs.** The scheduled `site` run evaluates under every licence, stores every value
   and records its licences in the run's audit; results are filtered per viewer at read. A user's
   own run holds what the registry gives that user. Each run records every field its spec reads with its licence (its audit,
   `field_licences`, from the owner's catalogue at run time). A stored value is gated by the
   stricter of that record and the site catalogue's current licence for the name (so a field
   reclassified since stays hidden); a name the site does not resolve (a user's own expression)
   by the record alone, never by the name in the viewer's catalogue, and with none it is
   withheld. A run evaluated under licences the viewer also holds counts as open, the site's current licence still applying; a run
   with rows and neither values nor a record is withheld whole. A narrow miss of a withheld
   field is dropped from the run's audit, for every role.
   A viewer without the licence sees a screen
   that read a personal field **by names and decisions only**: its criteria values, `score`,
   `tie_break`, `rank` and `reasons` (which quote the value) are withheld, a sort by rank or score is
   by symbol, and its Ideas ordering ignores score. (Owner default, as the ledger: names and
   decisions stay visible.)
4. **Market fields.** The gate covers the market entity too: a trader without the licence loses
   the Regime page's personal inputs (most indicators); the regime label, our own aggregate,
   stays open. (Owner default: accepted; the owner may grant the licence, or declare a series
   open, per user or per field.)
5. **Shared caches carry the licence set**: the GraphQL response key (every operation), the
   episode-signals cache and the regime-explanation cache.

## Consequences
- A new feature with a personal source is protected by declaring `licence = "personal"`; no
  per-path work. A new reader of values fails the fitness test until it is listed as gated.
- Not recomputed: the verdict (decision) of a stored run recorded under a licence later withdrawn.
  A run's `rank` is withheld with its score (null in GraphQL); the decision stays.
- The site's own run keeps every licence on purpose (decision 3); the leak it would be to give
  `site` no licence-filtering at read is what the per-viewer filter prevents.
