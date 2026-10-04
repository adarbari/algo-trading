---
name: add-web-page
description: Add a page, route or data-backed view to apps/web (route -> page -> widgets -> features -> entities -> shared/api). Use before adding any route, page, data hook or API call in the web app.
---

# Add a web page

Read first: `docs/ui/architecture.md` (ADR 0025). Components: `.claude/skills/add-ui-component`.
No new HTML: pages, widgets, features and entities only compose `@algotrade/ui`.

0. **Where it goes:** find the section in `src/app/workspaces/workspaces.ts` (TRADER: Ideas,
   Screeners, Explore, Backtests; ADMIN: Ingestion, Screener runs, Users & configs). A new
   section is a new entry there plus a route in its workspace group
   (`src/app/routes/trader/` or `src/app/routes/admin/`). Each folder kind is declared in
   `architecture/layout.toml` (`[[web_dir]]`); a new kind of folder is declared first.
1. **API first.** If the page needs data the API lacks, add the endpoint to `apps/api`, commit
   its `apps/api/openapi.json`, then in `apps/web` run `npm run api:generate` (CI fails if the
   generated schema is stale). Add a query key factory in `src/shared/api/query-keys.ts`. Only
   `src/shared/api` talks HTTP.
2. **Entities** (`src/entities/<entity>/`): the domain model types (from the generated
   schema), read hooks (`useQuery` + `api.GET` via `unwrap`), and view components composing
   `@algotrade/ui`. Export them from `index.ts`. Reuse an existing entity before adding one.
3. **Features** (`src/features/<feature>/`): a user action or flow with its state (filters,
   builder, mutations). Imports entities and shared; never another feature.
4. **Widgets** (`src/widgets/<widget>/`): a page section composing features and entities.
5. **Page** (`src/pages/<page>/`): composes widgets / features with primitives (`Stack`,
   `Text`); receives route params as props; no logic, no styling, no Query, no router.
   Export it from `index.ts`; add `<Page>.test.tsx`.
6. **Route** (`src/app/routes/<workspace>/routes.tsx`): replace the section's
   `placeholderRoute` with a `createRoute` whose component is the page (params validated
   here). Role gating stays in `workspaceGuard` (`src/app/workspaces/guard.ts`).
7. **Missing component?** Stop and follow `.claude/skills/add-ui-component` (design system
   first; components wait for approved mockups).
8. **Every query ends in data, empty or error**: render all three states, never an infinite
   loading. Verify with the real-app smoke (`make web-real`).
9. **Test:** unit tests next to each module; extend `e2e/smoke.spec.ts` (or add an e2e spec)
   for the route. Run `make web-check` and `make check`. Every lint message names its rule
   and the fix.
