# ADR 0037: A domain read model served by GraphQL

**Status:** accepted (2026-10-05; owner decision). Amends [0024](0024-api.md) (thin routes over
`services.explore` become thin GraphQL types over `services.read`; `services.explore` is
deleted at the end) and [0025](0025-frontend-architecture.md) rule 4 (the generated client
has two generators); amended by [0064](0064-edge-evidence-series-and-trade-ledger.md) (one file GET, the edge ledger CSV) and by [0082](0082-shared-filter-bar.md) (filter-bar files, `GET /files/{surface}.csv`). Spec: [docs/api/read-model.md](../api/read-model.md). Implemented over
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
   Amended (2026-10-08): job polling is one route for every on-request job, `GET /jobs/{job_id}`
   (`services/ondemand/status.py` over the `services/jobs` record): the caller reads their own
   jobs, an admin any, a site job (a preset's shared run) everyone; anyone else's job is 404, like
   an unknown id. It replaces the per-kind polls `GET /screens/{id}/run/{job_id}` (0033) and
   `GET /edges/{id}/evaluate/{job_id}` (0059): `max_get_routes` goes from 5 to 4.
   Amended by [0064](0064-edge-evidence-series-and-trade-ledger.md): the edge ledger's CSV file, `GET /files/edges/{edge_id}/trades.csv`
   (same loader as `Query.edgeTrades`): `max_get_routes` goes from 4 to 5.
   Amended by [0082](0082-shared-filter-bar.md): the filter bar's files, `GET /files/{surface}.csv`
   (the surface's own gated loader): `max_get_routes` goes from 5 to 6.
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

## Amendment 2026-10-09: the response cache keys on the runs generation

`POST /graphql` keeps the serialized answer of an error-free query
(`apps/api/algotrade_api/graphql/response_cache.py`). Its key is the published state
(`visible_seq`, read before the answer is computed, ADR 0022), the `WriteEpoch` (the config and
result writes this API served), the document, its variables and the caller's role (ADR 0056).
That covered only operations over published tables and configs; every read of run records
(ideas, status strip, screener runs, track records, edges, ingestion, nightly runs, quality)
ran on each request and, under load, queued for the read threads until the API answered 503.

1. **A runs generation.** `RunStore.generation()` changes on every `save` of a run record (a
   job's too: `services/jobs` saves through the same store) and on nothing else. Local: the
   `(inode, mtime_ns)` of `runs/`, which an atomic rename into it moves (measured on APFS:
   2000 of 2000 saves), `(0, 0)` while it does not exist; memory: a save counter. It is exposed
   as `StoreReader.runs_generation()` and contract-tested (`tests/contract/storage/`).
2. **Four groups, every web operation in exactly one** (a test over the generated `gql.ts`
   fails a new operation until it is classified): shared (role-keyed), user-keyed static,
   run-dependent, never cached. A run-dependent key also holds the runs generation, read
   before the answer like `visible_seq`; an operation whose loader reads the clock
   (`load_completeness`'s last closed session) holds that session too. Role and user id stay in
   the key. An answer with `errors` is never kept.
3. **Exact, not timed.** A save moves the generation, so the next read recomputes; a record
   saved while an answer is computed leaves that answer under a key nobody asks for again. A
   publish and a save are two moves, so a read between them is keyed on one and recomputed on
   the other. The 300 s age bound still covers a config edited outside the process.
   *Amended 2026-10-17 (stale-while-revalidate, replay):* past `TTL_S` an entry is *stale*, not
   gone: it is served once more and recomputed in the background (single flight per key), dropped
   only at `HARD_TTL_S` (24 h), so the first page after an idle spell is a cache answer; a config
   edited outside the process is seen one request later than before, never older than the next
   one. The router remembers each cacheable operation it serves (`OperationLog`: document,
   variables and the caller's `UserRecord`, bounded) and the warmer replays them in process, as
   the caller who asked (role-scoped causes and per-user keys are unchanged: ADR 0056), after the
   home steps at start and after each publish or session flip, before the market frames; at start
   the log is seeded with the web's page-load operations for the configured user
   (`benchmarks/api_latency_pages.json`, `make api-latency-capture`). `LlmUsage` joined the
   cached operations, keyed on `visible_seq` (a logged call publishes a partition) and the
   exchange date.
