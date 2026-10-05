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
1. **Data first: the entity's GraphQL operation** (ADR 0037; `.claude/skills/add-graphql-field`).
   Page reads are GraphQL: the operation in the entity's `api/`, fragments from other entities
   through their `index.ts`, per-instrument values as `features(names: [feature('<name>')])`
   (ADR 0038), then `npm run api:generate`. REST (`add-api-endpoint`) only for a write or a
   job. **Today's state:** the GraphQL layer arrives in read-model PR 4
   (`docs/api/read-model.md` "Migration plan"); until then, and until the page's area has
   moved, a new page read uses the old REST path only if the owner explicitly asks for that
   path ("use the legacy path"; a feature request is not: name the read-model PR that
   delivers it and ask); otherwise do the next migration PR first. On the legacy path too,
   a per-instrument value comes as `features['<catalogue name>']`, never a new typed field
   (`add-api-endpoint` "Legacy page reads"; a test fails it). Only `src/shared/api` talks HTTP.
2. **Entities** (`src/entities/<entity>/`): the domain model types (from the generated
   types), read hooks (`useQuery` over `gql()` with `queryKeys.gql(...)`; legacy REST hooks use
   `api.GET` via `unwrap`), and view components composing `@algotrade/ui`. Export them from
   `index.ts`. Reuse an existing entity before adding one. Render what the server sends: no
   fact derived from raw rows, no browser "today" against stored dates, no counts from a page
   (`architecture/web_forbidden_derivations.toml`, checked by `test_layout_web.py`).
3. **Features** (`src/features/<feature>/`): a user action or flow with its state (filters,
   builder, mutations). Imports entities and shared; never another feature.
4. **Widgets** (`src/widgets/<widget>/`): a page section composing features and entities.
   **Tables use `widgets/feature-table` with the column factories in
   `entities/feature/model/columns.tsx`; never a `DataTableColumn` literal** (ADR 0038; ESLint
   WEB 4, `lint-rules/columns.js`). A widget cannot import another widget, so the page
   composes `FeatureTable` (`sortMode="server"` for the universe, `"client"` for a few keyed
   rows); a missing kind of column is a new factory there, never a literal. Tables whose rows
   are not instruments (chain quotes, events, run records) are listed in `columns.js`
   `STRUCTURE` with the reason.
5. **Page** (`src/pages/<page>/`): composes widgets / features with primitives (`Stack`,
   `Text`); receives route params as props; no logic, no styling, no Query, no router.
   Export it from `index.ts`; add `<Page>.test.tsx`.
6. **Route** (`src/app/routes/<workspace>/routes.tsx`): replace the section's
   `placeholderRoute` with a `createRoute` whose component is the page (params validated
   here). Role gating stays in `workspaceGuard` (`src/app/workspaces/guard.ts`).
7. **Missing component?** Stop and follow `.claude/skills/add-ui-component` (design system
   first; mockup gate: a new page or a visual pattern in no approved mockup needs an
   owner-approved mockup, other components do not; see that skill).
8. **Every query ends in data, empty or error**: render all three states, never an infinite
   loading. Verify with the real-app smoke (`make web-real`).
9. **Test:** unit tests next to each module; extend `e2e/smoke.spec.ts` (or add an e2e spec)
   for the route. Run `make web-check` and `make check`. Every lint message names its rule
   and the fix.
