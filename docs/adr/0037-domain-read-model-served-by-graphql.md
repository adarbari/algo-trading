# ADR 0037: A domain read model served by GraphQL

**Status:** accepted (2026-10-05; owner decision). Amends [0024](0024-api.md) (thin routes over
`services.explore` become thin GraphQL types over `services.read`; `services.explore` is
deleted at the end) and [0025](0025-frontend-architecture.md) rule 4 (the generated client
has two generators). Spec: [docs/api/read-model.md](../api/read-model.md). Implemented over
read-model PRs 2-10; PR 1 records it and builds the harness.

## Context
Each REST area in `services/explore` assembles its own view: its own partition rule, symbol
lookup, scalar coercion and latest-run rule. The web app then joins several responses and
re-derives facts (counts from a page, next earnings from raw events). Four table widgets build
the same columns four ways. A new page meant a new bespoke query, schema and hook, and every
one could pick a different session (ADR 0036).

## Decision
1. **A domain read model**, `src/algotrade/services/read/`: a minimal set of frozen read
   objects (Session, Instrument, FeatureValue / FeatureInfo, Event, OptionChain, Holdings,
   series, FeatureTable, Screener, ScreenerRun, ScreenResult, Ideas, TableView, run records),
   one `load_<object>(ctx, ...)` per object, all reading one `ReadContext` (reader, configs,
   user, the resolved session, the user's catalogue, the result cache, dataloaders). It is the
   only code the GraphQL layer calls (ownership `domain-read-model`); read-only (import-linter).
2. **GraphQL joins them** for the web app: Strawberry in `apps/api/algotrade_api/graphql/`
   (`POST /graphql`), code-first from typed Python. Types are thin: one `.of()` mapping from the
   read dataclass, resolvers that call one loader or dataloader (import-linter "GraphQL types are
   thin"); per-request dataloaders (no N+1); depth, alias, token and list-size limits; errors as
   `extensions.code`; a committed SDL snapshot `apps/api/schema.graphql` checked by a test; no
   mutations, no persisted queries.
3. **Web**: `@graphql-codegen` client preset from the committed SDL over TanStack Query, one
   transport `gql()` in `src/shared/api/graphql.ts`; operations and fragments live in each
   entity's `api/`. No Apollo or urql (a second cache); ESLint bans them.
4. **REST only for** writes, job polling, health, live quotes, the preview POSTs, files and,
   until the last PR, admin. Every GET route is in `architecture/rest_allowlist.toml`, which only
   shrinks (two fitness tests). A new GET that is not a page read needs an amendment here.
   Amended by [0044](0044-hosting-from-the-owners-mac.md): the files include the built web
   app (`GET /{path}`, mounted last, only when `ALGOTRADE_WEB_DIST` is set).
5. **Migration in ten PRs** (the spec's plan), each green and shippable; `services/explore` is
   deleted in the last.

## Consequences
- Two contracts and two generators (OpenAPI and SDL) until PR 10; both are snapshots with
  freshness tests, and the REST side only shrinks.
- Type duplication (dataclass -> `@strawberry.type`) is contained by `.of()`, a fitness test
  that a type's fields mirror its dataclass, and the SDL snapshot. GraphQL types mirror read
  dataclasses by design, so the duplicate-code ratchet (`scripts/check_dupes.py`) skips
  `apps/api/algotrade_api/graphql/types/`; READ 7 (`test_types_mirror_read_model`) keeps them
  in sync.
- Tables are columnar (`FeatureTable.rows: [[JSON]]`), not object lists: per-field resolution
  over 11k rows is too slow.
- One endpoint returning 200 on errors is harder to debug: operation names and
  `extensions.code` carry the signal.
- New skills: `add-domain-object`, `add-graphql-field`; `add-api-endpoint` covers REST writes only.
