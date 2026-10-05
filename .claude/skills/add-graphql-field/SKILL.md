---
name: add-graphql-field
description: Give a web page data it needs from the API: a field on the GraphQL read layer (apps/api/algotrade_api/graphql) backed by a loader in the read model (src/algotrade/services/read), then the web operation through graphql-codegen (ADRs 0036-0038). Use for every page read; REST is only for writes, jobs, health, live quotes and files (add-api-endpoint).
---

# Add a GraphQL field (a page read)

Read first (by section): `docs/api/read-model.md` ("Catalogue feature or typed field",
"GraphQL conventions", "What the browser may not derive"), ADR 0037.

## Step 0: what exists today (check, do not assume)

Run `ls apps/api/algotrade_api/graphql apps/api/algotrade_api/graphql/types/* src/algotrade/services/read`.

| You see | Meaning | Do |
|---|---|---|
| only `__init__.py` files under `graphql/` | an old branch (before PR 4) | rebase on `origin/main` |
| `graphql/schema.py`, `apps/api/schema.graphql`, `apps/web/codegen.ts` exist | **today**: PRs 4-5 landed (`Query.{session,instrument,ideas,screeners,view}`, `Instrument.features(names)`, the `features` and `screener_latest_run` dataloaders, codegen, `useInstrumentFacts`, `useIdeas` on `IdeasPage`) | continue |
| the area's REST GET is still in `architecture/rest_allowlist.toml` | that area has not moved yet | add the field in the area's migration PR (move the area), not beside the REST route |

## Step 1: which object owns it

`grep -n "domain-read-model" -A3 architecture/ownership.toml` and the object table in
`docs/api/read-model.md` ("The domain objects"). Find the object the field belongs to
(`Instrument`, `Screener`, `ScreenerRun`, `ScreenResult`, `Ideas`, ...). No object fits ->
**stop, use `.claude/skills/add-domain-object`**.

## Step 2: is it a feature? (decide before writing any code)

> Anything **per instrument, per session, stored or computed on read** that a selection could
> also use is a catalogue feature, read **by catalogue name only**, never as a typed field.

- It is a per-instrument value (a price stat, IV, earnings date, days to X, a flag, a label):
  **do not add a field.** The page asks
  `instrument { features(names: [feature('rollup.<group>@vN.<col>')]) { name value unknown { code } info { format } } }`.
  Check the name exists: `grep -n "<col>" docs/data/features.md`. Not there -> **stop, run
  `.claude/skills/add-feature`** (its own PR, owner backfill if stored), then come back.
- It is identity, a link to another object, or run / session bookkeeping: a typed field.
  Continue.

## Step 3: the loader (the logic lives here)

Add or extend `load_<thing>(ctx, ...)` in the object's module
`src/algotrade/services/read/<area>/<object>.py`. Rules: read only `ctx.session.date`
(session grain through `partition(ctx, table)`; other grains per the grain table in
`docs/api/read-model.md`); missing data is `Unknown(...)`, not an exception; values through
`values.to_scalar`. Unit test in `tests/unit/services/read/<area>/test_<object>.py`, including
"an older partition exists and is ignored".

Verify: `.venv/bin/python -m pytest tests/unit/services/read -q -x` then `make arch ownership`.

## Step 4: the resolver (no logic)

In `apps/api/algotrade_api/graphql/types/<area>/<object>.py` (`<area>` mirrors the read model: `instruments/`, `screens/`; `types/` itself holds only `query.py` and `session.py`):

```python
@strawberry.field
def holdings(self, info: Info, top: int = 10) -> Holdings | None:
    return Holdings.of(holdings.load_holdings(info.context, self.instrument_id, top))
```

- One loader call (or one dataloader `.load(...)` for a child object), then `.of()`. At most a
  `None` guard. No loops, no `if` on values, no pandas, no `algotrade.data`, no
  `services.explore` (import-linter "GraphQL types are thin" fails it).
- A new type: `@strawberry.type`, fields copied from the read dataclass (same names, camelCase
  is automatic), one `@classmethod of(cls, d)`.
- A child object resolved per parent (an instrument per result row) goes through a dataloader
  in `graphql/loaders.py`, never a loader call per row.
- Never name a field like a catalogue column (`next_earnings_date`, `iv30`, ...): the schema
  test fails it (READ 9).

`@strawberry.field(...)` with arguments is untyped under mypy strict: put
`# type: ignore[untyped-decorator]` on that decorator line only (a fitness test allows it there
and nowhere else). A top-level field goes on `Query` in `types/query.py` and takes the session
as `date: Day = None`; it opens the read context with `info.context.read(date)`.

Verify: `make typecheck arch`.

## Step 5: the schema snapshot

`.venv/bin/python scripts/export_graphql_schema.py`, commit `apps/api/schema.graphql`
(`tests/apps/api/graphql/test_schema.py` fails when stale). On a merge conflict in it: take
main's, regenerate. Add the operation to the 1 s budget in `tests/apps/api/test_main.py` if it
is a page's main query.

## Step 6: the web operation

In `apps/web`, in the entity's `api/` (`src/entities/<entity>/api/`): write the operation with
the generated `graphql()` tag, compose other entities' fragments through their `index.ts`, wrap
it in a hook: `useQuery({ queryKey: queryKeys.gql('<OperationName>', vars), queryFn: () => gql(Doc, vars) })`.
Feature names with `feature('<name>')` from `@/shared/api` (a typo fails `tsc`). Then
`npm run api:generate` (both generators) and commit the generated files; a new site feature
name for `feature()` needs `.venv/bin/python scripts/export_catalogue.py` (CI's Python job checks
`catalogue.ts` is fresh). A string literal naming a feature outside `feature()` fails ESLint
(WEB 5); a `graphql` / `graphql-tag` import fails it too (WEB 2). Render
`unknown.code` where `value` is null; format with `info.format`; never derive a fact the
server can send (`architecture/web_forbidden_derivations.toml`).

Verify: `make web-check` (or `cd apps/web && npm run check`).

## Step 7: finish

`docs/api/read-model.md`: the object row if a field was added to it. If this PR retires a REST
GET: remove its entry from `architecture/rest_allowlist.toml`, run `make rest-allowlist-update`,
and enable any derivation entry the plan names for the PR. Then
`make check WORKERS=2 WEB_WORKERS=2`.

## Worked example: "Overview should show the next earnings date"

1. Object: `Instrument`. 2. Per instrument, per session, stored as
`rollup.earnings@v1.next_earnings_date`: **a feature, no new field.** 3-5: nothing (the
`features` resolver exists). 6. In `entities/instrument/api/`, the overview operation asks
`features(names: [feature('rollup.earnings@v1.next_earnings_date')])`; the widget renders the
value with `info.format = 'date'`, or "not stored for <session.date>" from `unknown.code`. It
never computes the date from `events/earnings` or the browser clock.

A typed example: "the pane should list an ETF's holdings" -> `Instrument.holdings(top)`:
`load_holdings` in `read/instruments/holdings.py` (step 3), the resolver above (step 4).

## Stop and do something else instead

- You are about to add a `GET` route -> no; the allow-list test fails it. REST is
  `add-api-endpoint` for writes, jobs, live, files only.
- You are about to put a loop, a filter or a date comparison in a resolver -> move it into the
  loader (step 3).
- The value is not stored and is a per-instrument fact -> `add-feature` first.
- You need a date other than the request's session -> a named argument (`previous_session`,
  `from` / `to`), never "latest" computed in the loader.
- The web needs a count, a top-N or a "new since" -> ask the server (a typed field computed in
  the loader over the population), never from a page in the browser.
- The same check fails twice -> stop and escalate (CLAUDE.md "Agents, models and tokens").
