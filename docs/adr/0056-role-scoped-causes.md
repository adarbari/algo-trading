# ADR 0056: Not-available causes are role-scoped

**Status:** accepted (2026-10-08; owner decisions 2026-10-08). Amends
[0036](0036-session-strictness-for-reads.md) (what an UNKNOWN value carries),
[0037](0037-domain-read-model-served-by-graphql.md) (the REST allow-list's error and preview fields) and
[0040](0040-identity-and-roles.md) (a role also decides which words about a gap a caller reads).

## Context
Every page that says a value, a feature or a run is not available says why in the words of the
store: `rollups/instrument/ibkr_iv@v1 has no partition for 2026-10-08`, a table list in
`session.missing` or a run's `missingTables`, an error text on a failed on-request run, the
gateway's reason on a live chain. Those words are for the owner (an admin): they name tables,
steps, vendors and exceptions. A trader needs to know which fields are out and, in a sentence,
why, not how the pipeline is wired. The web already hides the Admin workspace (`guard.ts`), but
a browser-side filter is not enforcement: the response itself carried the words.

## Decision
1. **A gap is public in kind and private in cause.** `Unavailable(kind, features, guide_term)`
   is what every caller reads: the `UnavailableKind` (`SYSTEM` a real failure; `NOT_STORED` no
   row or a stored null with no failure behind it; `NOT_APPLICABLE`, `ILLIQUID`, `LICENCE`,
   `NOT_RUN`), the catalogue features it hides (names are fine) and the Guide glossary term that
   explains the kind. `Unknown` (one value) carries the same: `code`, `reason` (a `NullReason`),
   `kind`, `guide_term`. Public wording per kind is generic ("not available because of a system
   error", "not available for this instrument") and never names a table, vendor, step or error.
2. **The cause is admin-only.** `Cause` is a chain of `CauseLink(level, subject, status,
   message, run_id, session)` ordered root first: SOURCE (IB Gateway unreachable) -> STEP
   (`ibkr-iv` SKIPPED) -> TABLE (`rollups/instrument/ibkr_iv@v1` has no rows for S) -> FEATURE
   (features x, y, z unavailable). `Unknown.detail: str` becomes `Unknown.cause: Cause`: each read
   model construction site builds the leaf it knows (`table_cause`, `feature_cause`,
   `run_cause`); `explain(ctx, leaf)` expands it upstream from stored facts only (feature ->
   group table -> the group's input tables, bounded depth; table -> the nightly step that wrote
   it, from the run record). The kind comes from the code alone, so a trader's read never pays
   for the chain: the chain is built only for an admin, behind one dataloader per request.
3. **The server withholds, the browser never filters.** GraphQL: `AdminCause()` (beside
   `AdminOnly`, `graphql/permissions.py`) resolves to null (never FORBIDDEN) for a caller who is
   not an admin, so a query selecting `cause` succeeds; the legacy table lists and `detail` /
   `audit` are role-aware until the web stops reading them. REST: a field that carries a cause
   declares `ADMIN_CAUSE` (its fallback: null, `[]`, the generic words or an audit without its
   table keys) and a route returns `redact(model, caller.role)`; the not-found handler and the
   GraphQL `NO_DATA` message are generic for a caller who is not an admin. **The role decides,
   not the workspace**: an admin on a trader page is served the cause. Roles come only from
   `config/site/users.toml` (`Query.viewer`, ADR 0040); `guard.ts` stays the only web gate.
4. **Ingestion records what a step writes.** Each nightly step's record carries its registry
   `Task.tables` (`StepResult.as_dict`). An older record has none: its chain stops at the table.
5. **Harness.** `tests/apps/api/graphql/test_causes.py` (every `Cause`-typed field carries
   `AdminCause`; no string field named like a cause is readable by a trader unless role-scoped,
   an Admin type or listed in `architecture/cause_fields.toml`; a trader's response over every
   root that can carry an UNKNOWN holds no table path and a null cause, an admin gets the
   chain); `tests/architecture/api/test_rest_causes.py` (the same over the served REST models and
   the preview and on-request run); a fitness test that every kind maps to a glossary term.
   `architecture/cause_fields.toml` lists facts (kept, each with its reason) and legacy fields
   (emptied when the web converts, PR-3 of this change).
6. **Ownership.** `availability-causes`, owner `services/read/availability/`.

## Consequences
- A trader sees which features are out and one generic sentence plus a Guide term per kind; an
  admin sees the full chain wherever the same gap is shown, on any page.
- `NOT_STORED` versus `SYSTEM` is decided from the code (a missing partition is a system
  failure; a missing row or a stored null is not), not from the chain: an admin may find a failed
  step behind a `NOT_STORED` value. A later change can promote a kind from the chain without
  changing the public vocabulary.
- Old fields stay until the web converts (its surfaces are listed in the plan); for a trader
  they are empty or generic, so those pages show less, never more. The web conversion, the
  `CauseChain` design-system component and the ESLint rule that keeps `.cause` inside
  `entities/availability` follow as separate PRs.
- A new "not available" surface is an `Unavailable` / `Unknown` with a kind and a Guide term (the
  `add-graphql-field`, `add-domain-object`, `add-api-endpoint` and `add-guide-content` skills
  say how); free text about a gap is never a new public field.
