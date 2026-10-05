---
name: add-domain-object
description: Add a domain read object (a frozen dataclass + its load_<object>(ctx, ...) loader) to the read model in src/algotrade/services/read/ (ADRs 0036-0038), for one resolved session, with its UNKNOWN cases, ownership, tests and GraphQL type. Use when a page needs a kind of thing the read model does not have yet; for one more field on an existing object use add-graphql-field.
---

# Add a domain read object

Read first (by section): `docs/api/read-model.md` ("Catalogue feature or typed field", "The
domain objects", "Values and UNKNOWN", "Session resolution"), ADRs 0036, 0037, 0038.

## Step 0: what exists today (check, do not assume)

Run `ls src/algotrade/services/read src/algotrade/services/read/* apps/api/algotrade_api/graphql`.

| You see | Meaning | Do |
|---|---|---|
| only `__init__.py` files | read-model PR 1 state (superseded: PR 2 landed 2026-10) | you are on an old branch: rebase on `origin/main` |
| `session.py`, `values.py`, `context.py`, but no `apps/api/algotrade_api/graphql/schema.py` | an old branch (PR 2 state) | rebase on `origin/main` |
| `graphql/schema.py`, `read/instruments/{identity,features,catalogue}.py`, `read/screens/*` exist | **today**: PRs 4-5 landed (Instrument, FeatureValue, FeatureInfo; Screener, ScreenerRun, ScreenResult, Ideas, TableView on GraphQL); the next object is the one the next RM PR names (RM6: `read/instruments/{events,chains,holdings,prices,series}.py`) | all steps |

Check the object is not already planned: `grep -n "<ObjectName>" docs/api/read-model.md`. If
the spec's object table names it, build exactly that row (identity, fields, tables, module).

## Step 1: identity and fields (the rule, quoted)

> **Typed field**: identity and structure. Who something is (`instrumentId`, `symbol`, `name`,
> `securityType`, `assetClass`, `exchange`), what links to what, and run / session bookkeeping
> (`runId`, `session`, `status`, `knowledgeTs`, decision, score, rank, criterion outcomes).
> These come from snapshot or result tables and never from `rollups/*`.
>
> **Catalogue feature**: anything **per instrument, per session, stored or computed on read**
> that a selection could also use. Read **by catalogue name only**, never as a typed field.

Write down: the identity (the key a client asks by), the typed fields, and which values are
catalogue features (those are NOT fields of your object: the client asks
`instrument { features(names: [...]) }`). A field you want that is a per-instrument value not
in the catalogue (`grep -n "<name>" docs/data/features.md`): **stop, run
`.claude/skills/add-feature` first** in its own PR.

## Step 2: tables and grain (the rule, quoted)

| Grain | Tables | Read for `Session.date` |
|---|---|---|
| session | `rollups/instrument/*`, `chains/*`, `results/*`, `bars/1d`, `verification/*`, `live/*` | exactly the date via `partition(ctx, table)`; absent -> `Unknown(NO_PARTITION)` |
| snapshot | `instruments/reference`, `instruments/company`, `universe`, `instruments/id_map`, `instruments/ibkr_contracts` | `data.reference.snapshot` (ADR 0007), disclosed as `referenceSnapshot` / `preSnapshot` |
| event | `events/*` | by event date (`data.events.read_events`), never by partition |
| issuer-dated | `holdings/etf` | latest `as_of` on or before the date (`data.funds.holdings`), `asOf` disclosed |
| incremental | `instruments/description` | latest stored row |
| range | bars, feature series | explicit `[start, end]` arguments |

Never call `partition_for`, `latest_session`, `rollup_row`, `latest_date` or compute "latest"
yourself (ownership `session-resolution` fails it). A date other than `ctx.session.date` is an
explicit, named argument (`previous_session`), never derived inside the loader.

## Step 3: the module

- Folder by kind: instrument grain -> `src/algotrade/services/read/instruments/`; screen
  results -> `.../read/screens/`; run records -> `.../read/ops/`. Folder at 8+ modules
  (`make layout` prints it): split by kind first (`.claude/skills/add-responsibility` step 3).
- File `<object>.py` (plural noun of the thing: `holdings.py`), docstring saying what it loads.
- A frozen dataclass named for the object (no `View`, `Dto`, `Response` suffixes) and one
  `load_<object>(ctx: ReadContext, <identity>) -> <Object> | None` (None = no such thing).
  Values through `values.to_scalar`; never `to_value`, never a private `_float` / `_text`.
- Data only through `algotrade.data` and `partition(ctx, ...)`; never `algotrade.storage`
  readers, never `services.explore` (it is being deleted).
- No writes, no jobs (import-linter "Read model is read-only").

Verify: `make arch layout ownership`.

## Step 4: UNKNOWN cases

List every way a value can be missing and map it to `UnknownCode`: `NO_PARTITION` (table has
no partition for the session), `NO_ROW` (partition but no row), `NULL` (stored null),
`NOT_IN_CATALOGUE`, `LICENCE`, `NOT_RUN` (no screener run for the session), `PRE_SNAPSHOT`.
"Nothing stored" is never an exception: return the object with `Unknown` / empty lists.
`NotFoundError` only for an identity that does not exist.

## Step 5: tests

`tests/unit/services/read/<area>/test_<object>.py` (mirror; layout tests fail otherwise),
building stores with `tests/helpers/` builders. Cover: the happy path for the session; a missing
partition -> `NO_PARTITION` (the loader must NOT return an older partition: put an older
partition in the store and assert it is ignored); a missing row; the snapshot / as-of disclosure
if the grain has one. Run `.venv/bin/python -m pytest tests/unit/services/read -q -x`.

## Step 6: registries and docs

- `architecture/ownership.toml`: extend the `domain-read-model` description with the object
  if it is a new kind; a new stored table it needs is `.claude/skills/add-dataset`, not here.
- `docs/api/read-model.md` "The domain objects": add or complete the row.
- `make ownership layout`.

## Step 7: GraphQL type (only once PR 4 has landed)

Follow `.claude/skills/add-graphql-field` step 4: `apps/api/algotrade_api/graphql/types/<object>.py`
with `@strawberry.type`, fields copied from the dataclass, one `of()` classmethod, resolvers that
call one loader. Then the snapshot (`.venv/bin/python scripts/export_graphql_schema.py`) and
`make check WORKERS=2 WEB_WORKERS=2`.

## Worked example: Holdings (an ETF's top holdings)

1. Identity `(fund_id, asOf)`; typed fields `asOf, source, total, items[{rank, name, symbol,
   instrument?, weight, assetClass}]` (structure: who the fund holds). No catalogue values.
2. `holdings/etf` is issuer-dated: latest `as_of` on or before `ctx.session.date` with
   `filed <= date` through `data.funds.holdings.etf_holdings`; `asOf` disclosed.
3. `src/algotrade/services/read/instruments/holdings.py`:
   `@dataclass(frozen=True) class Holdings` + `load_holdings(ctx, fund_id, top) -> Holdings | None`
   (None for a non-ETF), symbols linked through `identity.instruments(ctx, ids)`.
4. UNKNOWN: nothing stored for the fund -> `Holdings` with empty `items` and `asOf = None`.
5. `tests/unit/services/read/instruments/test_holdings.py`: latest as-of wins, a later `filed`
   date is invisible, empty for a stock.
6. Spec row already exists ("Holdings"); nothing new in ownership.
7. `types/holdings.py` with `Holdings.of(d)`; `Instrument.holdings(top)` resolves through the
   `holdings` dataloader.

## Stop and do something else instead

- The value is per instrument per session (a number, flag, date, label) -> not an object field:
  `features(names)`; missing from the catalogue -> `add-feature` first.
- You need "the latest" of something -> it is `ctx.session` (session grain) or the grain's one
  rule above; never your own max over dates.
- You are about to import `services.explore` or copy code from it -> move the code (same PR),
  delete the explore copy, and add the deferred ownership rule the plan names for that PR.
- You are about to add a REST GET for it -> no: `architecture/rest_allowlist.toml` only shrinks.
- The same check fails twice -> stop and escalate (CLAUDE.md "Agents, models and tokens").
