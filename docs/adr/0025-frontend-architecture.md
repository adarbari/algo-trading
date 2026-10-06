# ADR 0025: Frontend architecture: a layered, component-only web app

**Status:** accepted (2026-10-03); amended by [0037](0037-domain-read-model-served-by-graphql.md) (rule 4: a second generated client, GraphQL via graphql-codegen, through `shared/api`). Extends [0011](0011-design-system-first-ui.md) (design
system first), [0019](0019-ownership-and-boundaries.md) (one owner per responsibility) and
[0020](0020-directory-layout.md) (one kind of thing per folder) to `apps/web`. Guide:
[docs/ui/architecture.md](../ui/architecture.md).

## Context
`apps/web` is about to be built (phase 5). The owner asked for code that is "extremely modular
with clear ownership boundaries and good directory structure", where "no UI should be built
without components; every part should be a component", on a modern stack, with the rules
in the harness so future work follows them. ADR 0011 fixes the order: tokens, then approved
mockups, then design-system components, then screens. The Python side already enforces
layers (import-linter), owners (`ownership.toml`) and folders (`layout.toml`); the web app
needs the same, with tools that work on TypeScript.

## Decision

### Stack
Vite + React 19 + TypeScript (strict, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`);
TanStack Router (code-based route tree, fully typed), TanStack Query (server state), TanStack
Table (inside the design system's DataTable, later); Storybook (the component catalogue);
Vitest + Testing Library + axe-core (unit and accessibility); Playwright (end-to-end, and
screenshot + axe over every story); ESLint flat config with typescript-eslint,
eslint-plugin-boundaries, jsx-a11y, React, hooks; Stylelint; Prettier. Styling: typed tokens
generate CSS custom properties (light / dark, compact / comfortable, standard / colour-blind
up-down); CSS Modules **only** inside the design system; no Tailwind, no CSS-in-JS. The API
client is generated from the FastAPI OpenAPI document (openapi-typescript + openapi-fetch).
Packages: **npm workspaces** (Node 24 ships npm; corepack/pnpm would need a global shim), one
lockfile `apps/web/package-lock.json`; the design system is the workspace package
`@algotrade/ui` whose `exports` expose only its root.

### Layers and folders
```
apps/web/
  design-system/        @algotrade/ui: the ONLY place styling and raw HTML elements live
    tokens/             typed tokens -> generated tokens.css
    theme/              UiProvider (fonts, tokens, theme, density) + the one global base.css
    primitives/<Name>/  Stack, Text, ...: the only way screens lay out and set text
    components/<Name>/  Name.tsx, .module.css, .stories.tsx, .test.tsx, index.ts, __screenshots__/
    testing/            axe assertion for design-system tests
    COMPONENTS.md       generated inventory (CI fails on drift)
  src/
    app/                shell: entry, providers, router, route groups, layouts, workspaces
    pages/<page>/       one folder per route: composes widgets/features; no logic, no styling
    widgets/<widget>/   page sections composed of features + entities
    features/<feature>/ user actions and flows with their state
    entities/<entity>/  domain models, their read hooks and view components
    shared/{api,lib,config}/  HTTP (only here), pure helpers, build-time config
```
A slice (`pages/*`, `widgets/*`, `features/*`, `entities/*`, `shared/*`) exposes its public API
in `index.ts`; inner folders are segments named for their kind (`ui`, `model`, `api`, `lib`,
`config`). Every folder is declared as a `[[web_dir]]` in `architecture/layout.toml`.

### Workspaces and routes
Two workspaces, switched in a **horizontal top bar** (not a sidebar):
- **TRADER** (default): Ideas (home: screeners in the user's priority order + a combined ranked
  top-ideas list), Screeners (builder: hard / soft criteria, thresholds, weights, live preview,
  save / finalize), Explore (one page replacing separate universe / instrument / chain /
  feature pages: a filterable ticker table whose columns come from the feature catalogue,
  multi-select compare, detail tabs Overview / Chart / Options / Features / Events / Screener
  hits), Backtests.
- **ADMIN** (`/admin/*`): Ingestion (completeness grid dataset x session with drill-down,
  quality checks, issues), Screener runs & sharing (per-user scheduled screens, publishing
  results), Users & configs.

Each workspace is a route group (`src/app/routes/trader/`, `src/app/routes/admin/`) under a
workspace layout route that renders the top bar. `src/app/workspaces/` declares the workspaces
and sections; its `workspaceGuard` runs in every workspace's `beforeLoad` and is the **one seam
for role gating** (today the app is local and single-user, so every workspace is open). Until a
section's page is built, its route renders the generic placeholder page.

### Rule 1: layers import only downward
`app -> pages -> widgets -> features -> entities -> shared -> @algotrade/ui`. Slices of one layer
never import each other (compose them one layer up); the exception is an entity referencing
another entity's public `index.ts`. `shared/` imports only `shared/config` and `shared/lib`. The
design system never imports app code. Enforced by `eslint-plugin-boundaries`
(`apps/web/lint-rules/layers.js`, default disallow).

### Rule 2: slices expose a public index
Across slices only `index.ts` may be imported; deep imports fail (boundaries policies; the
`@algotrade/ui` package `exports`; `no-restricted-imports` for `@algotrade/ui/*` and
`design-system/**` paths). A slice without `index.ts` fails `test_layout_web.py`.

### Rule 3: component-only UI
Outside `design-system/`: no intrinsic HTML / SVG elements in JSX, no `className`, `style` or
`dangerouslySetInnerHTML`, no stylesheets, CSS-in-JS or class utilities, no hex / rgb / hsl
colours and no px / rem lengths. Layout goes through primitives, everything else through
components that expose semantic props and variants. Inside the design system, Stylelint
requires tokens for colours, type, spacing, radius and z-index and bans gradients, shadows,
glows, filters and raw units. Enforced by ESLint (`lint-rules/restrictions.js`), Stylelint
and `test_layout_web.py` (stylesheets only where `styles = true`).

### Rule 4: only shared/api talks HTTP
`fetch`, `XMLHttpRequest`, `WebSocket`, `EventSource` and HTTP libraries are banned outside
`src/shared/api`. Data reaches components through TanStack Query hooks exported by entities
and features; pages and widgets may not import TanStack Query; only `src/app` imports the
router. The client is generated from the OpenAPI document; CI regenerates and fails on drift.

### Rule 5: small files, small folders
Files aim for 300 lines (hard limit 1000: `scripts/check_file_length.py` covers ts / tsx / js /
css). At most 10 modules per folder (`index.ts`, tests and stories excluded); `make layout`
warns at 8.

### Rule 6: complete design-system components
Every primitive and component has a story for each state (Default, Loading, Empty, Error,
Dense, or the reason one does not apply), a unit test with an axe assertion, and committed
screenshots of every story in light and dark. `npm run ds:check` and `test_layout_web.py`
check completeness; the Playwright visual suite compares screenshots and runs axe (including
colour contrast) on every story in both themes. Screenshot baselines are Linux, made in the
official Playwright image locally (`npm run visual:update`) and in CI.

### Rule 7: no grab-bag names
`[banned_module_names]` (`utils`, `helpers`, `common`, `misc`, ...) applies to web modules:
`shared/lib/format/number.ts`, never `utils.ts`.

### Rule 8: accessibility
`eslint-plugin-jsx-a11y` (strict) on all JSX; interactive components need keyboard support and
labels; axe runs in unit tests, on every story (both themes) and in the end-to-end smoke test.

### Ownership
Web responsibilities are `[[web_responsibility]]` entries in `architecture/web_ownership.toml`
(styling, tokens, HTTP, data access, routing, workspace access, env), each naming the lint
rule or check that keeps it in its owner.

## Consequences
- Every lint message names its rule, `docs/ui/architecture.md` and the skill that explains the
  fix (`.claude/skills/add-ui-component`, `.claude/skills/add-web-page`).
- The first screens take longer: each needs its components in the design system first, and
  those wait for the approved mockups (ADR 0011). Tokens ship as **DRAFT**. (Note 2026-10-03:
  tokens final from the approved mockups; layout primitives added. See ADR 0011.)
- `make check` runs the web checks (`make web-check`); CI has a `web` job in the Playwright
  image, so auto-merge waits for it. Screenshot changes are reviewed as image diffs.
- The API client's types come from `apps/api/openapi.json` (ADR 0024, the API's committed
  contract): an API change regenerates `src/shared/api/generated/schema.ts` in the same PR, or
  the web job fails. The app calls the API under `/api` (the dev server strips the prefix and
  proxies to `algotrade-api` on :8000; `VITE_API_BASE_URL` overrides it). Generated files are
  exempt from the line limit (`check_file_length.py` skips a "GENERATED by ... Do not edit"
  header).
