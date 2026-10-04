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
| End-to-end test / screenshot suite | `apps/web/e2e/` / `apps/web/visual/` |
| Lint rule, generator, check | `apps/web/lint-rules/`, `apps/web/scripts/` |

Nothing fits? Add a folder for the new kind, declare it as a `[[web_dir]]` in
`architecture/layout.toml` with a purpose, and never park code in a neighbour.

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
and a `beforeLoad` guard (`app/workspaces/guard.ts`, the one place role gating will go):

| Workspace | Sections (routes) |
|---|---|
| TRADER (default, `/` opens Ideas) | Ideas `/ideas`, Screeners `/screeners` (list), `/screeners/new`, `/screeners/$id/edit` (Builder), Explore `/explore`, Backtests `/backtests` |
| ADMIN | Ingestion `/admin/ingestion`, Screener runs & sharing `/admin/screener-runs`, Users & configs `/admin/users` |

Explore is one page (ticker table with feature-catalogue columns, multi-select compare, detail
tabs Compare / Chart / Options / Features / Events / Screener hits), not separate universe,
instrument, chain and feature pages. Unbuilt sections render the placeholder page.

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

Every folder under `apps/web` is declared in `architecture/layout.toml` (`[[web_dir]]`, with
`kind` = layer / slice / segment / component / screenshots); an undeclared folder fails
`tests/architecture/test_layout_web.py`. Owners of web responsibilities (styling, tokens, HTTP,
data access, routing, workspace access, env) are `[[web_responsibility]]` entries in
`architecture/ownership.toml`.

## Commands (in `apps/web`, Node 24 + npm)

| Command | Does |
|---|---|
| `npm ci` / `make web-install` | install (lockfile `apps/web/package-lock.json`); `make web-install` also gets the Playwright browser |
| `npm run dev` | dev server on :5173 (proxies `/api/*` to the API on :8000, prefix stripped) |
| `npm run check` / `make web-check` | generated files fresh, `ds:check`, lint (ESLint, Stylelint, Prettier), typecheck, unit tests, build, Storybook build, e2e |
| `npm run storybook` | the component catalogue on :6006 |
| `npm run visual:docker` / `make web-visual` | screenshots + axe over every story in the CI Linux image (needs Docker) |
| `npm run visual:update` | accept screenshot changes (commit the PNGs; reviewers see the diffs) |
| `npm run tokens`, `components:md`, `api:generate` | regenerate `tokens.css`, `COMPONENTS.md`, the API schema |

The API client's types are generated from `apps/api/openapi.json` (the API's committed contract,
ADR 0024) into `src/shared/api/generated/schema.ts`; regenerate in the same PR as an API change.
The app calls the API under `/api`; `npm run dev` proxies it to `algotrade-api` on :8000.
