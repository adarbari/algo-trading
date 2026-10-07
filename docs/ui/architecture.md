# Web app architecture

Decision record: [ADR 0025](../adr/0025-frontend-architecture.md) (extends
[ADR 0011](../adr/0011-design-system-first-ui.md)). Design-system spec:
[design-system.md](design-system.md). Skills: `.claude/skills/add-ui-component` (a component),
`.claude/skills/add-web-page` (a page / route).

The web app is built from components only. Styling and HTML live in one package, the design
system; everything else composes it in layers that import only downward.

## Where does it go?

| Kind of UI code | Folder |
|---|---|
| Colour, type, space, radius, motion, density value | `apps/web/design-system/tokens/` (typed; `npm run tokens` regenerates `tokens.css`) |
| Layout or typography building block (Stack, Text, Grid, ...) | `apps/web/design-system/primitives/<Name>/` |
| Reusable visual component (Button, DataTable, Banner, TopBar, ...) | `apps/web/design-system/components/<Name>/` (generic name, never a screen's) |
| A URL: route, params, redirects, guard | `apps/web/src/app/routes/<workspace>/` (TRADER: `trader/`, ADMIN: `admin/`) |
| A workspace or section of the top bar | `apps/web/src/app/workspaces/` |
| App-wide provider (query client, UiProvider) | `apps/web/src/app/providers/` |
| What one route shows | `apps/web/src/pages/<page>/` |
| A section of a page combining several features / entities | `apps/web/src/widgets/<widget>/` |
| A user action or flow with its state (filter, builder, form) | `apps/web/src/features/<feature>/` |
| A domain model, its read hooks (TanStack Query) and view components | `apps/web/src/entities/<entity>/` |
| HTTP: client, fetch wrapper, query keys, generated schema | `apps/web/src/shared/api/` |
| Pure helper (formatting, maths) | `apps/web/src/shared/lib/<kind>/<what-it-does>.ts` |
| Build-time configuration (`VITE_*`) | `apps/web/src/shared/config/` |
| Story / unit test | next to the component (`Name.stories.tsx`, `Name.test.tsx`) or module (`x.test.ts`) |
| End-to-end test (mocked API) / real-app smoke / screenshot suite | `apps/web/e2e/` / `apps/web/real/` / `apps/web/visual/` |
| Lint rule, generator, check | `apps/web/lint-rules/`, `apps/web/scripts/` |

Nothing fits? Add a folder for the new kind, declare it as a `[[web_dir]]` in
`architecture/web_layout.toml` with a purpose, and never park code in a neighbour.

## Layers

```
app  ->  pages  ->  widgets  ->  features  ->  entities  ->  shared  ->  @algotrade/ui
shell    routes     sections     actions       models       api/lib/     design system
                                 + state       + hooks      config       (styling, HTML)
```

| Layer | May import | Never |
|---|---|---|
| `app/` | pages, widgets, features, entities, shared (each via `index.ts`), `@algotrade/ui`, router, query | |
| `pages/<p>/` | own files; widgets, features, entities, shared via `index.ts`; `@algotrade/ui` | other pages; router; TanStack Query; HTML; styling |
| `widgets/<w>/` | own files; features, entities, shared; `@algotrade/ui` | other widgets; router; TanStack Query |
| `features/<f>/` | own files; entities, shared; `@algotrade/ui`; TanStack Query | other features; router |
| `entities/<e>/` | own files; another entity's `index.ts`; shared; `@algotrade/ui`; TanStack Query | router |
| `shared/api` | own files; `shared/config`, `shared/lib`; openapi-fetch | UI, upper layers |
| `shared/lib`, `shared/config` | own files; `shared/lib` / `shared/config` | HTTP, UI, upper layers |
| `design-system/` | itself (components via primitives' / components' `index.ts`, tokens) | app code (`src/`), HTTP, router, query |
| `design-system/components/Chart/` | as `design-system/`, plus `lightweight-charts` (the only importer) | |

Third-party UI libraries stay behind one design-system wrapper each: `lightweight-charts` only
in `components/Chart` (ESLint `no-restricted-imports` everywhere else, including the rest of the
design system); `@floating-ui/react` only inside the design system (Tooltip, Popover, Dialog,
Drawer). App code uses the components.

Two features that must work together are composed in a widget (or page); they never import each
other. A page receives route params as props from its route in `app/`.

## Workspaces and navigation

A horizontal top bar switches between two workspaces; each is a route group with a layout route
and a `beforeLoad` guard (`app/workspaces/guard.ts`, the one place role gating goes: it reads
`Query.viewer`, ADR 0040; no session redirects to `/login`, a workspace the viewer's role lacks to the
default workspace; the top bar lists only the workspaces they may enter, shows their name and a
sign-out action). `/login` (`pages/login`, outside both workspaces) is the design-system `LoginForm`
over Supabase password sign-in (`entities/viewer`, `shared/api/auth.ts`, the bearer token on every
request; a 401 ends the session):

| Workspace | Sections (routes) |
|---|---|
| TRADER (default, `/` opens Ideas) | Ideas `/ideas`, Screeners `/screeners` (list), `/screeners/new`, `/screeners/$id/edit` (Builder), Explore `/explore`, Regime `/regime` (the market as weather: `entities/regime`, widgets `regime-header`, `regime-indicators`, `reading-list`; the top-bar chip and the Ideas `regime-strip` read the same query), Backtests `/backtests` |
| ADMIN | Ingestion `/admin/ingestion`, Screener runs & sharing `/admin/screener-runs`, Users & configs `/admin/users` |

Explore is one page (ticker table with feature-catalogue columns, multi-select compare, detail
tabs Overview / Compare / Chart / Options / Features / Events / Screener hits; one ticker opens
on Overview, a compare set of two or more on Compare), not separate universe, instrument, chain
and feature pages. A last tab, Field guide (`tab=guide`, `widgets/field-guide`), takes the whole
page instead of the ticker table: a sidebar to find a catalogue field (search, the guide's themes)
and the field's page (what it means, its spread over the universe with the names passing a
criterion, one name's year, the criterion per intent, caveats, how it is computed); the theme,
field and symbol live in the URL (`theme`, `field`, `symbol`), and the pass counts come from
`FeatureDistribution.passing` (the server counts; the browser derives nothing). The Overview ends with "In rough markets" (`episode_behaviour@v1` features
read by name: beta to SPY, drawdown per reference episode; the episodes' plain names are the
`entities/regime` map until the API serves `episodes.toml`). Unbuilt sections render the placeholder page.

## Rules and how they are enforced

Every message names its rule (`[ADR 0025 rule n]`), this page and the skill with the fix.

| # | Rule | Enforced by |
|---|---|---|
| 1 | Layers import only downward; no imports between slices of one layer (entities: via `index.ts` only) | ESLint `boundaries/dependencies` (`apps/web/lint-rules/layers.js`) |
| 2 | Slices expose a public `index.ts`; no deep imports (also `@algotrade/ui` root only) | `boundaries/dependencies`, `no-restricted-imports`, package `exports`, `test_layout_web.py` |
| 3 | Component-only UI: outside `design-system/` no HTML / SVG elements, no `className` / `style`, no CSS files or CSS-in-JS, no colours or px lengths | ESLint `no-restricted-syntax` / `no-restricted-imports` (`lint-rules/restrictions.js`); Stylelint (tokens only, no gradients / shadows / raw units); `test_layout_web.py` (stylesheets only in the design system) |
| 4 | Only `shared/api` talks HTTP; data through Query hooks in entities / features; router only in `app/` | ESLint `no-restricted-globals` / `-syntax` / `-imports`; `npm run generated:check` (client matches the OpenAPI document) |
| 5 | Files about 300 lines (hard 1000); at most 10 modules per folder | `scripts/check_file_length.py`; `test_layout_web.py`; `make layout` warns at 8 |
| 6 | Every design-system component: stories for Default / Loading / Empty / Error / Dense (or the reason not), unit test with axe, screenshots light + dark | `npm run ds:check`; `test_layout_web.py`; Playwright visual suite (screenshot diff + axe incl. contrast, every story, both themes) |
| 7 | No grab-bag module names (`utils.ts`, `helpers.ts`, ...) | `test_layout_web.py` (`[banned_module_names]`) |
| 8 | Accessible: keyboard and labels for interactive components | `eslint-plugin-jsx-a11y` (strict); axe in unit, visual and e2e tests |

Every folder under `apps/web` is declared in `architecture/web_layout.toml` (`[[web_dir]]`, with
`kind` = layer / slice / segment / component / screenshots); an undeclared folder fails
`tests/architecture/test_layout_web.py`. Owners of web responsibilities (styling, tokens, HTTP,
data access, routing, workspace access, env) are `[[web_responsibility]]` entries in
`architecture/web_ownership.toml`.

## Commands (in `apps/web`, Node 24 + npm)

| Command | Does |
|---|---|
| `npm ci` / `make web-install` | install (lockfile `apps/web/package-lock.json`); `make web-install` also gets the Playwright browser |
| `npm run dev` | dev server on :5173 (proxies `/api/*` to the API on :8000, prefix stripped; `$API_PROXY_TARGET` overrides). `predev` / `prestorybook` run `scripts/check-node-modules.ts`, which stops with "node_modules is out of date with package-lock.json: run `make web-install`" when the installed packages differ from the lockfile (a pull changed the dependencies) |
| `npm run check` / `make web-check` | generated files fresh, `ds:check`, lint (ESLint, Stylelint, Prettier), typecheck, unit tests, build, Storybook build, e2e |
| `make web-real` (`npx playwright test -c playwright.real.config.ts`) | the real-app smoke (below): Vite dev + the real API, empty and golden stores; needs Python (`make install`); part of `make check` and CI's `real-app` job |
| `npm run storybook` | the component catalogue on :6006 |
| `npm run visual:docker` / `make web-visual` | screenshots + axe over every story in the CI Linux image (needs Docker) |
| `npm run visual:update` | accept screenshot changes (commit the PNGs; reviewers see the diffs) |
| `npm run tokens`, `components:md`, `api:generate` | regenerate `tokens.css`, `COMPONENTS.md`, the API types (OpenAPI schema and GraphQL codegen) |

### Real-app smoke (`apps/web/real/`)

The mocked e2e tests cannot see what only the real app shows: a stale `node_modules`, a page
that waits forever on an endpoint that answers 404 or 500, a first-run store with nothing in
it. So `make web-real` starts, for each of two stores, the real API (`uvicorn`, the repo's
`config/`) and the Vite **dev** server (the error overlay exists only there), then opens every
route of both workspaces (the top-bar sections plus `/screeners/new` and
`/screeners/<id>/edit`): the **empty** store (a fresh install, before anything ran) and the
**golden** fixture store (`make golden-store`). A route fails on:

- a console error or uncaught page error;
- the Vite error overlay (e.g. "Failed to resolve import");
- a loading state (`aria-busy`, "Loading…") still showing after 10 s: every query must end in
  data, empty or error (the app's query client never retries a 4xx);
- a failed response other than the API's 404 `{"detail": ...}` ("nothing stored"), which pages
  show as an empty or error panel (each such response and its console line cancel out). `/ideas`
  is stricter: it must show its explained empty state, never a "failed to load" panel.

A new route is covered by adding its path to `workspaces.ts` (or `EXTRA_ROUTES` in
`real/routes.real.spec.ts` for a parameterised one). About 40 s; CI runs it as its own job
(it needs Python and Node), local `make check` runs it after `make web-check`.

The API client's types are generated from `apps/api/openapi.json` (the API's committed contract,
ADR 0024) into `src/shared/api/generated/schema.ts`, and the GraphQL operations' types from
`apps/api/schema.graphql` (ADR 0037; `codegen.ts`) into `src/shared/api/generated/graphql/`;
regenerate in the same PR as an API change. Page reads that moved to the read model go through
`gql()` (`src/shared/api/graphql.ts`) with documents written with the generated `graphql()`
tag in each entity's `api/`; site feature names are typed through `feature('<name>')`
(`generated/catalogue.ts`, `scripts/export_catalogue.py`; docs/api/read-model.md).
The app calls the API under `/api`; `npm run dev` proxies it to `algotrade-api` on :8000.
