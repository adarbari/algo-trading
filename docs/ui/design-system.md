# Design system

Decision record: [ADR 0011](../adr/0011-design-system-first-ui.md).

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
  design-system/        package @algotrade/ui. The ONLY place styling decisions live.
    tokens/             color, type, space, radius, border, motion, density, z-index
    components/         one folder per component: Component.tsx, .stories.tsx, .test.tsx
    COMPONENTS.md       GENERATED inventory of every component and its props (do not hand-edit)
  app/                  screens. Imports UI only from @algotrade/ui.
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
3. **Then use it** from `app/`.
4. Screens contain layout and data wiring only: no raw colours, no one-off spacing, no styled
   HTML elements.

## Enforcement (CI)

| Check | Tool |
|---|---|
| `app/` imports UI only from `@algotrade/ui` | ESLint `no-restricted-imports` |
| No hex or rgb colours, inline styles or arbitrary sizes outside `design-system/` | ESLint and Stylelint rules |
| Every design-system component has a catalogue story, a test and a screenshot snapshot | `scripts/check-design-system` |
| `COMPONENTS.md` is up to date | regenerated in CI; fails on diff |
| Screenshot changes are reviewed | Playwright screenshot comparison |
| 1000-line file limit also covers `.ts` / `.tsx` | `scripts/check_file_length.py` |

## Before any screen is built

Tokens and mockups of the two key screens (screener results, contract detail) are
approved by the owner first. Only then is the component catalogue built, and only after
that the app.
