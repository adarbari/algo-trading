---
name: add-api-endpoint
description: Add or change an endpoint of the API (apps/api; reads, plus user-config writes via `services/authoring`, ADR 0029): the explore query in services, the response schema, the thin route, the OpenAPI export and the web client regeneration. Use whenever a web page needs data the API does not serve yet.
---

# Add an API endpoint

Read first: ADR 0024 (`docs/adr/0024-api.md`), `docs/architecture.md` section 12 (API) and an
existing area end to end (`services/explore/screens/results.py` → `schemas/screens/results.py` →
`routes/screens/results.py` → `tests/apps/api/routes/screens/test_results.py`). Admin-only endpoints go under
the `/admin/` prefix (`routes/admin.py`) so role-gating can attach to it later.

**Ownership check (ADR 0019):** `http-api` is `apps/api/algotrade_api/*` (routes, schemas,
CORS, errors); `explore-queries` is `src/algotrade/services/explore/*`; market data is read
only through `algotrade.data` (`market-data-reads`), run records through
`StoreReader.runs` / `StoreReader.run`. Never import the ingestion or backtest app, storage or
`algotrade.data` from the API (import-linter: "API: routes reach the library only through
services.explore, config and core"), and never write from explore ("Explore queries are
read-only").

1. **Data (if needed).** No `algotrade.data` function returns what the page needs? Extend the
   data owner (`data/<area>.py`) with a generic read and a unit test in `tests/unit/data/`.
   Do not read storage partitions ad hoc in services when a domain rule is involved (which
   snapshot, adjustments, event dates).
2. **Query.** Add a function to `services/explore/<area>.py` (a new area: a new module there; `services/explore/`, `routes/` and `schemas/` are at
   the 10-module cap, so a new area is a subfolder of its own (`screens/` is the model), or `make layout` fails). It takes the `ReadStore`, resolves `?date=` with
   `partition_for` (latest on or before; none yet = empty result) or
   `data.reference.snapshot`, raises `NotFoundError` for unknown ids, pages large lists with
   `paginate`, and returns a frozen dataclass of JSON-safe values (`record` / `records`).
   All pandas work happens here, never in the route. **"No data yet" is a 200 with an empty
   result (and the session), never a 404**; 404 only for an unknown id / resource.
3. **Schema.** Add a pydantic model to `apps/api/algotrade_api/schemas/<area>.py` deriving
   from `Schema` (`from_attributes`), with the same field names as the dataclass. Typed
   fields wherever the shape is fixed (the TS client is generated from them); `dict[str, Any]`
   only for open-ended rows (stats, feature values).
4. **Route.** In `routes/<area>.py`: parameters with `Annotated[..., Query(...)]` (a date is
   `Query(alias="date")`, defaulting to None = latest; `page` ≥ 1, `size` ≤ 1000), call ONE
   explore function, return `Model.model_validate(result)`. No logic, no pandas. A new area
   router goes in `routes/__init__.py` (`ROUTERS`).
5. **Tests** (`tests/apps/api/routes/test_<area>.py`, the `client` fixture over
   `tests/helpers/api_store.py`; add the rows your endpoint needs there): the happy path,
   404s, pagination, date defaulting and the response shape. Add the path to `ENDPOINTS` in
   `tests/apps/api/test_main.py` (the 1-second budget on golden data).
6. **OpenAPI.** `.venv/bin/python scripts/export_openapi.py`, commit `apps/api/openapi.json`
   (the `test_committed_openapi_is_up_to_date` test fails otherwise), then regenerate the web
   client from it in `apps/web` (`npm run api:generate`). On a merge conflict in either
   generated file never hand-merge: take main's version and regenerate.
7. **Docs.** The endpoint table in `docs/architecture.md` section 12. A new kind of endpoint
   (a write, a job submission, auth) is a decision: write an ADR first.
8. `make check`.
