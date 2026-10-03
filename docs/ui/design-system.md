# Design system

Decision record: [ADR 0011](../adr/0011-design-system-first-ui.md). The app's architecture
(layers, component-only rule, enforcement): [architecture.md](architecture.md), ADR 0025.

## Principle: dense but calm

A trading UI shows a lot of numbers. The goal is maximum information with minimum visual
noise.

- **Taken from the best platforms:** Saxo and Robinhood for uncluttered screens; IBKR for
  density and customisable layouts; TradingView for charts as the centrepiece. Simple,
  familiar navigation and watchlists everywhere.
- **Banned** (the generic "AI dashboard" look): gradients, glows, decorative shadows, emoji
  as icons, giant rounded cards around every number, more than one accent colour, centred
  marketing-style headers on working screens.

## Structure

```
apps/web/
  design-system/          package @algotrade/ui. The ONLY place styling and raw HTML live.
    tokens/               typed tokens (color, typography, space, shape, motion, density,
                          layers) -> GENERATED tokens.css (`npm run tokens`)
    theme/                UiProvider: fonts, tokens, theme, density, up/down palette
    primitives/<Name>/    Stack, Text, ...: how screens lay out and set text
    components/<Name>/    Name.tsx, Name.module.css, Name.stories.tsx, Name.test.tsx,
                          index.ts, __screenshots__/ (copy primitives/Text, the template)
    COMPONENTS.md         GENERATED inventory of every component and its props (do not hand-edit)
  src/                    the app in layers (app, pages, widgets, features, entities, shared):
                          imports UI only from @algotrade/ui. See architecture.md.
```

## Tokens

| Group | Decision |
|---|---|
| Color | Neutral grey scale (12 steps), **one** accent, semantic `positive` / `negative` / `warning` / `info`, colour-blind-safe alternative for up/down. Light and dark defined together. |
| Type | Inter (UI) with `tabular-nums` for every number; one monospace for symbols and code. Small scale (11–20 px for working screens). |
| Space | 4 px base scale |
| Shape | Radius 4–6 px; **borders, not shadows**, to separate surfaces |
| Density | `compact` (default for tables) and `comfortable` |
| Motion | 100–150 ms, no bouncing; respects `prefers-reduced-motion` |

The tokens in `apps/web/design-system/tokens/` are a **DRAFT** of this table (12-step neutral
greys, one blue accent, semantic positive / negative / warning / info, green / red up-down with
a blue / orange colour-blind-safe alternative under `data-updown="cvd"`, Inter + JetBrains Mono,
11–20 px type, 4 px space scale, radius 4 / 6 px, 1 px borders, 100 / 150 ms motion,
compact / comfortable density). They change with the mockups and are final when the owner
approves them. Every text colour passes WCAG AA on the canvas in both themes (checked by axe
on every story).

## First component set

| Category | Components |
|---|---|
| Basics | Button, IconButton, Input, NumberInput, Select, Combobox, Checkbox, Toggle, Tabs, Badge, Tooltip, Popover, Dialog, Drawer, Kbd |
| Data | **DataTable** (generic: column definitions, sort, filter, column picker, virtual scrolling, number and percent formatting, row selection, keyboard navigation), Stat, PriceChange, Sparkline, Chart (one wrapper around the chart library), Heatmap |
| Layout | AppShell, Sidebar, Toolbar, Panel, SplitPane, Stack, Grid |
| Feedback | Toast, Banner (including stale-data), EmptyState, Skeleton, ErrorState |

## The workflow every UI change follows

1. **Look first.** Read `COMPONENTS.md`. If a component (or a configuration of one) already
   does the job, use it.
2. **Missing? Add it to the design system, generically.** Name it for *what it is*, not the
   screen that needs it (`DataTable`, not `ScreenerTable`). Behaviour comes in through props
   and composition, not screen-specific branches. Include a catalogue story, tests and a
   screenshot snapshot.
3. **Then use it** from the app (`src/`, through the layer that owns it: architecture.md).
4. Screens contain layout and data wiring only: no raw colours, no one-off spacing, no styled
   HTML elements.

## Enforcement (CI)

| Check | Tool |
|---|---|
| App code (`src/`) imports UI only from `@algotrade/ui` (root only) and renders no HTML elements, `className` or `style` | ESLint (`apps/web/lint-rules/`; ADR 0025 rules 2-3) |
| No hex / rgb colours, gradients, shadows, inline styles or one-off sizes; tokens only | ESLint (app code) and Stylelint (design-system CSS) |
| Every design-system component has its stories (all states), a unit test with axe and screenshots | `npm run ds:check`, `tests/architecture/test_layout_web.py` |
| `COMPONENTS.md` and `tokens.css` are up to date | regenerated in CI (`npm run generated:check`); fails on diff |
| Screenshot changes are reviewed; contrast holds in light and dark | Playwright visual suite over every story (screenshot diff + axe), Linux image |
| 1000-line file limit also covers `.ts` / `.tsx` / `.css` | `scripts/check_file_length.py` |

## Before any screen is built

Tokens and mockups of the two key screens (screener results, contract detail) are
approved by the owner first. Only then is the component catalogue built, and only after
that the app.
