---
name: add-api-endpoint
description: Add or change a REST endpoint of the API (apps/api): writes (user configs via services/authoring, on-request runs), job polling, health, live quotes and files only (ADR 0037). A read for a page is NOT a REST endpoint: use add-graphql-field. Covers the service call, schema, thin route, REST allow-list, OpenAPI export and web client regeneration.
---

# Add a REST endpoint (writes, jobs, health, live, files)

**First: is it a read for a page?** (Anything a page shows from stored data: values, lists,
details, counts, a table.) Then **stop: it is a GraphQL field, use
`.claude/skills/add-graphql-field`** (ADR 0037; `docs/api/read-model.md`). A new `GET` serving
stored data fails `tests/architecture/test_structure.py::test_rest_get_routes_are_allowlisted`
(`architecture/rest_allowlist.toml` only shrinks). The one exception is "Legacy page reads"
at the end, and only when the owner explicitly asks.

REST is for (ADR 0037 decision 4):

| Kind | Example | Backend |
|---|---|---|
| A write of user configs | `PUT /screeners/{id}/draft`, `PUT /preferences/...` | one `services/authoring` use case (ADR 0029) |
| A job submission and its polling | `POST /screens/{id}/run`, `GET /screens/{id}/run/{job_id}` | `services/ondemand` (ADR 0033) |
| Health | `GET /health` | |
| Live quotes | `GET /chains/{id}/live` | `services/live` (ADR 0028) |
| Compute over a request body | `POST /screeners/preview`, `POST /features/check` | `services/explore/preview` (moves with read-model PR 8) |
| A file (export, download) | | the use case that owns the data |

Read first: ADR 0024 (`docs/adr/0024-api.md`, as amended by 0029, 0033, 0037), and one write
end to end (`services/authoring/screens.py` -> `schemas/authoring/` -> `routes/authoring/screeners.py`
-> `tests/apps/api/routes/authoring/`). Admin endpoints use the `/admin/` prefix.

**Ownership (ADR 0019):** `http-api` is `apps/api/algotrade_api/*`; config writes go only
through `services/authoring` (import-linter "Config writes go only through
services.authoring"); never import the ingestion or backtest app, storage or `algotrade.data`
from the API.

1. **Use case.** The write / job / live logic is a function in its owner service
   (`services/authoring/`, `services/ondemand/`, `services/live/`). A new kind of write (a new
   table or config the API writes) is a decision: write an ADR first (`write-adr`).
2. **Schema.** A pydantic model in `apps/api/algotrade_api/schemas/<area>/` deriving from
   `Schema` (`from_attributes`), field names as the dataclass. Request bodies are models too.
3. **Route.** In `routes/<area>/`: parameters with `Annotated[..., Query(...)]` / a body model,
   call ONE service function, return `Model.model_validate(result)`. No logic, no pandas. A new
   router goes in `routes/__init__.py` (`ROUTERS`). Folders at the 10-module cap: a new area is
   a subfolder (`make layout`).
4. **A new GET** (job status, a file, live): add a `[[route]]` to
   `architecture/rest_allowlist.toml` with `keep = true` and its `reason`, raise
   `max_get_routes` by one, and amend ADR 0037 (decision 4) in the same PR: raising the count
   without the ADR amendment is gaming the ratchet. A page read is never this case.
5. **Tests** (`tests/apps/api/routes/<area>/test_<x>.py`, the `client` / `user_client`
   fixtures): success, 400 / 404 / 409 paths, the write landing where the use case says.
6. **OpenAPI.** `.venv/bin/python scripts/export_openapi.py`, commit `apps/api/openapi.json`,
   then in `apps/web` run `npm run api:generate`. On a merge conflict in a generated file take
   main's and regenerate.
7. **Docs.** The endpoint table in `docs/architecture.md` section 12.
8. `make check WORKERS=2 WEB_WORKERS=2`.

## Legacy page reads (only until the area moves; only if the owner explicitly asks)

Until read-model PR 4 (`docs/api/read-model.md` "Migration plan") the GraphQL layer does not
exist, and until each area's PR its pages still read `services/explore` over REST. A change to
an existing legacy read (a bug fix, a parameter) follows the old path: the query in
`services/explore/<area>.py` (frozen dataclass of JSON-safe values via `record(s)`, `paginate`,
`NotFoundError` for unknown ids, "no data yet" is a 200 with an empty result), its schema and
thin route, the tests in `tests/apps/api/routes/`, the OpenAPI export. A **new** legacy GET
also needs the owner's explicit request and an allow-list entry with `keep = false` and
`retire_in` naming the read-model PR that moves it; otherwise do the migration PR in order.
Never add `partition_for` / `latest_session` calls outside `services/explore` (ownership
`session-resolution`).
