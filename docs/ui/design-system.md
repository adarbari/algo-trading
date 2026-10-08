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
    foundations/          Storybook pages documenting the tokens (Foundations/Tokens)
    primitives/<Name>/    Box, Surface, Stack, Grid, Text, Heading, Mono, Divider,
                          VisuallyHidden: how screens lay out and set text
    components/<Name>/    Name.tsx, Name.module.css, Name.stories.tsx, Name.test.tsx,
                          index.ts, __screenshots__/ (copy primitives/Text, the template)
    format/               value formatters (number, percent, $13.99B, date, signed delta) used
                          by the data components; exported from @algotrade/ui
    COMPONENTS.md         GENERATED inventory of every component and its props (do not hand-edit)
  src/                    the app in layers (app, pages, widgets, features, entities, shared):
                          imports UI only from @algotrade/ui. See architecture.md.
```

## Tokens (final)

**Final: from the owner-approved mockups, 2026-10-03** (ADR 0011 note). Source of truth:
`apps/web/design-system/tokens/*.ts` (typed; `npm run tokens` writes `tokens.css`). Browse them
in Storybook under **Foundations/Tokens** (swatches in the active theme, both hex values,
contrast ratios, type scale, space, radii, density). Components use only the CSS variables.

Style: dark-first, Webull-like crisp 1 px borders and modular panels; Robinhood-like plain
English and progressive disclosure; IBKR-Desktop density without clutter. **One accent.** No
gradients, glows, shadows, emoji icons or number-in-card tiles.

### Themes and switches

`UiProvider` sets attributes on `<html>`: `data-theme` = `dark` (default) | `light` | `system`
(follows `prefers-color-scheme`); `data-density` = `compact` (default) | `comfortable`;
`data-updown` = `standard` | `cvd`. `prefers-reduced-motion: reduce` sets every duration to 0.

### Colour (`--color-<role>`)

| Role | Dark | Light | Use |
|---|---|---|---|
| `bg` | `#0d0f12` | `#f7f7f5` | canvas |
| `surface` | `#15181d` | `#ffffff` | panels, top bar, popovers |
| `row` | `#1b1f25` | `#f1f1ee` | row hover, wells |
| `border` | `#262a31` | `#e3e3df` | panel and control borders |
| `border-soft` | `#1f2329` | `#ecece8` | dividers inside a panel |
| `control` | `#333842` | `#d4d4cf` | control outlines (segmented, chips, inputs) |
| `track` | `#23272e` | `#f0f0ec` | bar / meter track |
| `empty` | `#1a1d22` | `#f0f0ec` | heatmap cell with no data |
| `text` | `#e8eaee` | `#16181d` | primary text |
| `text-2` | `#c3c7cf` | `#3d424d` | secondary text |
| `muted` | `#8b919c` | `#5b606b` | captions, column headers, units |
| `accent` | `#4f7cff` | `#2446a8` | THE accent: links, primary action, focus ring, selection |
| `on-accent` | `#0d0f12` | `#ffffff` | text on a solid accent fill |
| `accent-soft` | `#1a2440` | `#eef1fa` | selected nav item / row |
| `accent-strong` | `#a9bfff` | `#16306f` | text on `accent-soft`, link hover |
| `accent-border` | `#2f4380` | `#b8c4ea` | selected / focused panel border |
| `positive` (`-bg`, `-border`) | `#5fd3b5` (`#0f2a24`, `#1e5c4e`) | `#0b5d4f` (`#eaf6f2`, `#a9d6c9`) | complete, pass |
| `warning` (`-bg`, `-border`) | `#f0b55c` (`#2e2312`, `#6b4a17`) | `#8a4b00` (`#fdf3e3`, `#e6b26b`) | partial, stale |
| `negative` (`-bg`, `-border`) | `#f08a8a` (`#2f1517`, `#6e2a2e`) | `#8f1d1d` (`#fbecec`, `#e5a3a3`) | failed, error |
| `neutral` (`-bg`, `-border`) | `#c3c7cf` (`#1b1f25`, `#333842`) | `#3d424d` (`#f1f1ee`, `#d4d4cf`) | draft, unknown |
| `info` (`-bg`, `-border`) | `#a9bfff` (`#1a2440`, `#2f4380`) | `#16306f` (`#eef1fa`, `#b8c4ea`) | notes (the accent hue: still one accent) |
| `up` / `down` (standard) | `#5fd3b5` / `#f08a8a` | `#0b5d4f` / `#8f1d1d` | price moves |
| `up` / `down` (`cvd`) | `#56b4e9` / `#e69f00` | `#0b62a8` / `#a14a00` | colour-blind-safe (Okabe-Ito blue / orange) |

Deviation from the mockups: the Ideas / Ingestion boards put white on the dark accent (3.7:1,
below AA); the Screener board's dark-on-accent (5.2:1) is the token. Everything else is the
mockups' `.app` / `.app[data-theme=light]` palette unchanged (`neutral` and `info` are built
from existing mockup colours).

**Contrast (WCAG AA, 4.5:1)**, lowest ratio over bg / surface / row (status colours also over
their own tint), checked by `tokens/tokens.test.ts` and by axe on every story in both themes:

| Text role | Dark | Light |
|---|---|---|
| text / text-2 / muted | 13.7 / 9.8 / 5.2 | 15.7 / 8.9 / 5.6 |
| accent (on bg, surface) / accent-strong (on accent-soft) / on-accent | 4.8 / 8.5 / 5.2 | 7.8 / 11.0 / 8.3 |
| positive / warning / negative / neutral / info | 8.3 / 8.4 / 6.9 / 9.8 / 8.5 | 6.9 / 6.0 / 7.8 / 8.9 / 11.0 |
| up / down standard; cvd | 9.0 / 6.9; 7.2 / 7.4 | 6.9 / 7.9; 5.6 / 5.3 |

`accent` text on `row` in dark is 4.46:1: on a hovered / zebra row use `accent-strong`.

### Data-visualisation series (`--color-s1` ... `--color-s6`)

Assign in this fixed order by entity (never cycled, never re-ranked when a filter changes the
count); a seventh series folds into "Other" or small multiples. Status colours stay reserved
for state and always come with a label. s1-s3 are the mockups' (Explore compare chart).

| Slot | Hue | Dark | Light |
|---|---|---|---|
| s1 | blue (the accent) | `#4f7cff` | `#2446a8` |
| s2 | amber | `#f0b55c` | `#b45309` |
| s3 | teal | `#5fd3b5` | `#0b5d4f` |
| s4 | magenta / wine | `#a04ab3` | `#540d2c` |
| s5 | lavender / violet | `#bcb2fd` | `#8c5bd1` |
| s6 | moss / green | `#586e1c` | `#4e986c` |

Validated with the data-viz palette validator (OKLab, Machado 2009 CVD simulation) over **all
pairs**, not just adjacent ones, so scatter plots and small multiples are safe:

| | Dark (surface `#15181d`) | Light (surface `#ffffff`) |
|---|---|---|
| Worst pair, normal vision (ΔE×100, floor 15) | 18.3 (s2 / s3) | 17.7 (s1 / s3) |
| Worst pair, protan / deutan (ΔE×100, target 8) | 10.3 (s3 / s5) | 9.7 (s2 / s3) |
| Graphic contrast vs surface and bg (3:1) | all >= 3.1 | all >= 3.2 |
| OKLCH lightness | 0.50-0.81 | 0.30-0.62 |

Lightness is spread on purpose (the owner asked for series distinct in lightness as well as
hue), so the series also separate in greyscale and print; the validator's narrow lightness
band check is therefore not applied. Lines and bars still carry a legend and direct labels
(colour is never the only key).

### Type

**IBM Plex Sans** (UI; 400 / 500 / 600) and **IBM Plex Mono** (symbols, ids, code; 400 / 500),
the fonts of the approved mockups, replacing the draft's Inter + JetBrains Mono. Plex is
compact and highly legible at 12-13 px, has true tabular figures, and its Sans / Mono pair
shares metrics. Self-hosted from `@fontsource/ibm-plex-sans` / `@fontsource/ibm-plex-mono`
(Latin subset, imported by `UiProvider`) rather than the Google Fonts CDN: no third-party
request or tracking, works offline and behind strict CSP, versions pinned in the lockfile, and
the CI screenshots render the same glyphs every time. Tabular figures (`tnum`) everywhere.

| Token | xs | sm | md | base | lg | xl | 2xl | 3xl |
|---|---|---|---|---|---|---|---|---|
| size / line height (px) | 11.5 / 16 | 12 / 17 | 12.5 / 18 | **13 / 19** | 14 / 20 | 16 / 22 | 18 / 24 | 22 / 28 |
| use | column headers, legends | captions | table cells | body, panel headings | emphasis | lead | page title (h1), summary figures | hero figure |

Weights: regular 400, medium 500, semibold 600 (headings).

### Space, shape, motion, layers, density

| Group | Tokens |
|---|---|
| Space (`--space-n`, n x 4 px) | 0, 0.5 (2), 1 (4), 1.5 (6), 2 (8), 2.5 (10), 3 (12), 4 (16), 5 (20), 6 (24), 8 (32), 10 (40) |
| Size | `label` 140, `sidebar` 320, `page` 1600 px (max page width); `icon-sm` / `icon-md` / `icon-lg` 12 / 14 / 16; `popover` 280 (min list width); `search` 220 (top-bar search) |
| Breakpoints (Grid `collapse`, container width) | sm 480, md 720, lg 960 px |
| Touch (`@media (pointer: coarse)`, every density) | control 36, row 40, cell padding y 9 px (`density.touch`): controls, rows and every small variant keep at least the control height |
| Radius | none 0, sm 3 (bars, tracks), md 4 (controls, chips), lg 6 (panels) |
| Border | thin 1 px (all surfaces), thick 2 px; focus ring 2 px solid accent, offset 1 px |
| Motion | fast 100 ms, base 150 ms, `cubic-bezier(0.2, 0, 0, 1)`; 0 ms under reduced motion |
| z-index | base 0, raised 1, sticky 10, dropdown 100, overlay 200, modal 300, toast 400, tooltip 500 |
| Density compact (default) | control 26, row 28, cell padding 5 / 8, panel padding 10 / 16, gap 8 px |
| Density comfortable | control 32, row 36, cell padding 9 / 12, panel padding 14 / 20, gap 12 px |

## Primitives: the only way screens lay out and set text

| Primitive | Props (tokens only) |
|---|---|
| `Box` | `as` (div, section, header, main, nav, footer, aside), `padding` / `paddingX` / `paddingY` (space), `width` (`auto`, `page`), `grow` |
| `Surface` | `as`, `tone` (surface, row, bg, accent), `border` (all, none, top, bottom, start, end), `borderTone` (default, soft, control, accent), `radius`, padding as Box, `grow`, `clip` |
| `Stack` | `direction`, `gap` (space), `align`, `justify`, `wrap` (a cluster), `grow`, `as` (+ ul, ol, li) |
| `Grid` | `columns` (1, 2, 3, 4, 6, 12 or `label-value`, `main-aside`, `sidebar-start`, `sidebar-end`), `gap`, `rowGap`, `align`, `collapse` (none, sm, md, lg: one column under that container width), `as` |
| `Text` | `size`, `weight`, `tone` (default, secondary, muted, accent, positive, warning, negative, info, up, down, inherit), `mono`, `numeric`, `truncate`, `as` |
| `Heading` | `level` 1-4 (h1 18 px, h2-h3 13 px, h4 12 px, semibold), `size`, `tone`, `truncate`, `id` |
| `Mono` | `size`, `weight`, `tone`, `code`, `truncate` |
| `Divider` | `orientation`, `tone` (default, soft), `decorative` |
| `VisuallyHidden` | `as` (span, div), `id` |

## Components (design system PR 2: shell, controls, labels, surfaces)

Full props in the generated `apps/web/design-system/COMPONENTS.md`. All follow the mockups'
measures (1 px borders, radius 4 controls / 6 panels, inverted selection in segmented
controls, accent tint for the current nav item and selected chips) and size from the density
tokens.

| Group | Components |
|---|---|
| Shell & navigation | `AppShell` (skip link, top bar, `main`; `page` or `full` layout), `TopBar` (brand, nav, utility and end slots; a two-row grid on phones), `NavTabs` (router-agnostic via `renderLink`, `aria-current`), `AccountMenu` (the viewer's name opens the workspace choice and Sign out), `WorkspaceSwitch` (a SegmentedControl named "Workspace", inside the AccountMenu), `KeyHints` (shortcut hints, hidden under a coarse pointer) |
| Actions & inputs | `Button` (primary, secondary, ghost, dashed; sm / md; icons; loading), `IconButton` (label required), `SegmentedControl` (radio group, arrow keys), `Checkbox` (mixed state, hidden label), `Input` (adornments), `SearchInput` (clear, Escape, loading), `NumberInput` (units, min / max / step, spinbutton), `Select` (native), `Combobox` (descriptions, kind badges, groups, async, ARIA combobox keyboard), `Field` (label, hint, error wired to the control) |
| Labels | `StatusBadge` (positive, warning, negative, neutral, info, accent), `Chip` (static, toggle, removable, dashed add), `TickerTag` (series s1-s6) |
| Surfaces | `Panel` (on Surface: title, description, actions, footer; loading / empty / error states with Retry; `flush` body), `Icon` (stroke set: close, plus, minus, search, chevrons, check, alert, info, external, drag-handle, refresh, filter, columns, spinner) |

Deviation from the mockups: the Explore compare chips colour the symbol text in the series
colour; `TickerTag` keeps the symbol in `text` and shows the series as border and swatch,
because series colours are validated for 3:1 graphic contrast, not 4.5:1 text (s4 / s6 in
dark, s6 in light would fail AA as text). The mockups' dashed-border grey (`#3a3f48`) is the
`control` token.

## Data components (design system PR 3)

Built from the approved Ideas, Screener, Explore and Ingestion mockups; props in `COMPONENTS.md`.

| Component | What it is | Notes |
|---|---|---|
| `DataTable` | Generic data grid on TanStack Table v9 + TanStack Virtual (internal; no TanStack type is public) | Typed `DataTableColumn` (header, description, accessor, `format`, `cell` slot, width step, `grow`); single-column sort with `aria-sort` (numbers high-first on the first click, missing values always last); column picker fed by the caller's columns and descriptions; controlled selection (checkbox column, Shift-click ranges, select all); sticky header; virtual rows of a fixed height per density (`--density-row-height`, plus one `--line-height-xs` for two-line rows); ARIA grid with an active row (arrows, Page Up / Down, Home / End, Enter activates, Space selects); horizontal scroll under the sticky header when narrow; loading / empty / error rows |
| `HeatGrid` | Rows x columns of status cells (complete, partial, failed, not collected) with value text | ARIA grid, roving focus (arrows, Home / End, Ctrl+Home / End), Enter / Space / click selects; accent outline on the selected cell; status legend |
| `StatStrip` | A summary row of stats divided by borders inside one strip (never cards) | label, value (text or formatted), sub-line, tone; two then one column in narrow containers |
| `ShareBar` / `StackedBar` / `BarList` | One share bar (a `meter`); one bar split into toned segments + legend; labelled rows of bars + values (funnel, tiers) | Colour is never the only key: values are text, the stacked bar's name lists every segment |
| `Tabs` | Underline tabs (`tablist`) and the selected panel | Controlled; Left / Right / Home / End with automatic activation; counts; disabled tabs skipped |
| `Disclosure` | Summary row (label + count) that expands to detail | Button with `aria-expanded`; controlled or uncontrolled; boxed or plain |
| `Legend` | Swatches for status tones, `empty`, `accent`, `muted` and series `s1`-`s6` | Shapes: cell (tint + border), solid, line |
| `KeyValue` | Definition list for detail panels (label column + tabular value, optional hint) | Formatted values carry their up / down tone |

The data components use the PR 2 controls: DataTable's selection boxes and column picker are
`Checkbox`es, the picker opens from a `Button` in a `Popover`; Disclosure's chevron is an
`Icon`; decision cells are `StatusBadge`s (cell slot).

### Value formatting

`formatValue(value, format)` (`design-system/format/`, exported from `@algotrade/ui`) is the one
place that decides how a value reads: `number` (`11,427`), `percent` (a fraction: 0.721 ->
`72.1%`), `currency` (`$333.69`), `currency-compact` (`$13.99B`, `$412M`), `compact`
(`11.4K`), `date` (`2 Oct 2026`, `Fri 2 Oct`, ISO) and `delta` (`+1.24%`, `−3.4%`, `+3.2 pts`,
with an up / down tone). Missing values read as an em dash in the muted tone; negatives use the
typographic minus. DataTable, KeyValue, StatStrip, StackedBar and BarList format through it, so
screens never format numbers themselves.

## Charts (design system PR 4)

| Component | What it is | Notes |
|---|---|---|
| `Chart` | THE time-series chart: price history, rebased comparisons, a feature over time | One wrapper around **lightweight-charts** (TradingView, Apache-2.0; canvas, small, built for financial time series). `series` (id, label, points `{time: ISO day, value}`, tone `s1`-`s6` by position), `type` `line` / `area` (one series, flat tint: never a gradient), `range` `3M` / `1Y` / `2Y` / `All` (the caller's `SegmentedControl`, passed as `toolbar`; `CHART_RANGES`), `rebase` (100 x value / first value in the window, dashed 100 line), `events` (dated markers on the first series: ex-dividend circle **D**, split square **S**, earnings up arrow **E**, filing down arrow **F**, macro release circle **M**, each `{ time, kind, detail? }`, plus a key: shape and letter, never colour alone; `detail` is the hover text in the read-out and the table), `volume` (a second pane), `format` (axis, read-out and table through `formatValue`), `height` sm / md / lg, `status` loading / error (+ `onRetry`), `emptyMessage` |
| `Sparkline` | Tiny inline line for a table cell or stat | Plain SVG, no library. Tone `auto` (up / down by first-to-last), `muted` or `s1`-`s6`; dashed `baseline`; `showLast`; gaps break the line; summary as its accessible name |
| `Distribution` | Histogram of one feature across the universe (feature catalogue) | Plain SVG bars on a value axis (unequal bins allowed); `markers` (quantiles dashed, a highlighted value solid accent, each labelled in text); summary as its accessible name; loading / empty / error |

**Chart behaviour.** Crosshair read-out (date, each series' value in tabular figures, volume,
that day's events). Resizes with its container (`autoSize`, ResizeObserver). Colours and font
are read from the tokens of the active theme (the canvas cannot use CSS variables) and the
chart redraws when `data-theme` / `data-updown` or the system scheme changes. No animation:
scroll, zoom and kinetic scrolling are off (the range control sets the window), so reduced
motion needs nothing more. Accessible: the plot is `role="img"` named by a generated summary
("AAPL close, 2 Oct 2025 to 2 Oct 2026; AAPL $… to $333.69 (+…%), low …, high …; events: 4
ex-dividend, 4 earnings"), and **View as table** shows the same numbers in a DataTable.
Screenshot stories use seeded data and wait for the canvas to paint (`data-ready`).

**Boundary.** Only `design-system/components/Chart/` may import `lightweight-charts`, and inside
it only `engine.ts` does (ESLint `no-restricted-imports` everywhere else; ownership entry
`web-charting`). The library's attribution logo stays on (its licence asks for a link to
TradingView; turning it off needs an attribution page instead).

## Event components (EV7a-B)

For the event-sensitivity screens (ADR 0050, `docs/event-sensitivity-plan.md`). The props
mirror the read model's event item in plain TypeScript (`EventItem`: `date`, `time`, `kind`,
`label`, `source`, `knownFrom`), so the design system imports no API types; the label and the
"clear" and "first clear" flags come from the API, nothing is derived in the browser.

| Component | What it is | Notes |
|---|---|---|
| `EventChip` | An event's kind as a colour, a glyph and its short label ("Earnings", "CPI", "2.02 results") | With `event` it is focusable and its tooltip (hover and focus) gives label, time, source and known-from (`EventDetail`); the kind is also a screen-reader prefix |
| `EventTimeline` | Dated events over a window: an axis (month ticks, a mark per event day) above the days with events, each day a group of chips | `dense` collapses a day to a count whose tooltip lists the events; days wrap (phone width); an ordered list named by `label` |
| `ExpiryLadder` | Listed expiries as a table: expiry, DTE, the events it spans (chip + day) or a "Clear" badge | The row with `firstClear` carries the "First clear" badge and an accent rule |
| `CalendarGrid` | Days x names table, chips in the cells; `ruledDays` (expiry Fridays) are ruled and named in the header | Days down; flips to days across under the medium breakpoint (or `orientation`); names paged beyond `pageSize` (30) with Previous / Next names |

**Kind colours: no new tokens.** The existing roles fit, and the glyph and the text carry the
kind where colour cannot: own earnings = `accent` tint with a solid triangle; the reference
name's earnings = `info` tint with a hollow triangle; macro release = `warning` tint with a
circle; market structure = `neutral` tint with a square; filing = `neutral` tint, dashed
border, down triangle. `Chart` markers use the same shapes (earnings up arrow, filing down arrow,
macro circle) and a letter each (E, F, M).

## Feedback (design system PR 4)

| Component | Use | Notes |
|---|---|---|
| `Toast` + `ToastProvider` + `useToast()` | Brief result of an action ("Screener saved", "Export failed") | Mount `ToastProvider` once in `src/app/providers`; `useToast().show({ tone, title, description, action, duration })`. Bottom-end, at most three, 5 s (negative: until dismissed), paused on hover / focus; status (negative: alert) |
| `Banner` | A lasting condition on a page or panel | `info` / `warning` / `negative` tint + border + icon; `asOf` makes it the stale-data notice ("Stale data · as of 1 Oct 2026", warning); actions, dismiss |
| `EmptyState` | Nothing to show yet | Title, one line, an action; `bordered` dashed placeholder, `compact` inside tables |
| `Skeleton` | Loading placeholders shaped like the content | `text` lines, `rect` (chart), `table` rows at the density row height; slow pulse, none under reduced motion; one busy status |
| `ErrorState` | A section failed to load | Alert with message, mono detail, Retry (spinner while `retrying`) |

## Overlays (design system PR 4)

| Component | Use | Notes |
|---|---|---|
| `Tooltip` | A short description of a focusable control | Hover after a delay (600 ms), focus at once, Escape hides; the trigger gets `aria-describedby` through `children(props)` |
| `Popover` | A panel anchored to a trigger, opened by click (column picker, filter editor) | `trigger(props)` wires ref, `aria-expanded` / `aria-controls` / `aria-haspopup`; non-modal dialog; Escape / outside click close and return focus; `trapFocus` optional; flips / shifts / fits the viewport |
| `Dialog` | A short modal task or confirmation | Controlled; title = name, description; focus to the first control in the body, Tab trapped, focus returns to the opener; Escape / close / backdrop (unless `dismissible={false}`); scroll locked |
| `Drawer` | Side sheet for detail in context | Same modal behaviour; `side` end / start; `size` sm / md / lg |
| `MasterDetail` | A list beside its detail (Explore, screener results): the one way a page shows a detail for a chosen row (ADR 0052) | `master`, `detail`, `detailKey` (the chosen item; null none), `detailTitle` / `detailDescription`, `onDetailClose`, `summary` (narrow only, above the list), `columns` 2 / `main-aside`, `collapse` md / lg. Wide: a Grid of the two. Narrow (`useNarrow`): the list; the detail in a Drawer that opens when `detailKey` changes and calls `onDetailClose` on dismiss (the caller clears the choice) |
| `Kbd` | A key or shortcut in text | `keys={['Ctrl', 'K']}` |

**Why Floating UI.** Overlays are built on `@floating-ui/react` (MIT): positioning (flip,
shift, size to the viewport, follows scrolling) plus its focus manager (modal trap, return
focus, focus guards) and dismiss / hover / focus interactions, which are the hard, easily
wrong accessibility parts. It is headless (no styles, no components), so the look stays in our
CSS Modules and tokens; a small hand-written positioner would still need all of the focus
logic. Heavy UI kits (MUI, Chakra, Mantine) were rejected: they bring their own styling
systems. Only the design system imports it (ESLint bans it in `src/`). Overlays are portalled to
`<body>` and layered with the `z-dropdown` / `z-modal` / `z-toast` / `z-tooltip` tokens;
borders, never shadows; the modal backdrop is the canvas colour at partial opacity.

With PR 4 the catalogue covers every v1 screen (Ideas, Screener builder, Explore, Ingestion).

## First component set

| Category | Components |
|---|---|
| Basics | Button, IconButton, Input, NumberInput, Select, Combobox, Checkbox, Toggle, Tabs, Badge, Tooltip, Popover, Dialog, Drawer, Kbd |
| Data | **DataTable** (generic: column definitions, sort, filter, column picker, virtual scrolling, number and percent formatting, row selection, keyboard navigation), Stat, PriceChange, Sparkline, Chart (one wrapper around the chart library), Heatmap |
| Layout | AppShell, Sidebar, Toolbar, Panel, SplitPane (primitives above: Box, Surface, Stack, Grid) |
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
5. **Phones and desktops from the one component** (ADR 0052, `.claude/skills/responsive-ui`):
   layout reacts to the container's width (`@container` at the breakpoint tokens; `useNarrow`
   from `design-system/responsive/` when the tree must change), touch sizing comes from the
   density tokens under a coarse pointer, nothing is hover-only, a list beside its detail is
   `MasterDetail`, and a component with a container or coarse-pointer rule has a `Narrow` story.

## Enforcement (CI)

| Check | Tool |
|---|---|
| App code (`src/`) imports UI only from `@algotrade/ui` (root only) and renders no HTML elements, `className` or `style` | ESLint (`apps/web/lint-rules/`; ADR 0025 rules 2-3) |
| No hex / rgb colours, gradients, shadows, inline styles or one-off sizes; tokens only | ESLint (app code) and Stylelint (design-system CSS) |
| Every design-system component has its stories (all states), a unit test with axe and screenshots | `npm run ds:check`, `tests/architecture/test_layout_web.py` |
| `lightweight-charts` only in `components/Chart`; `@floating-ui/react` only in the design system | ESLint `no-restricted-imports` (`apps/web/lint-rules/restrictions.js`) |
| `COMPONENTS.md` and `tokens.css` are up to date | regenerated in CI (`npm run generated:check`); fails on diff |
| Screenshot changes are reviewed; contrast holds in light and dark | Playwright visual suite over every story (screenshot diff + axe), Linux image |
| 1000-line file limit also covers `.ts` / `.tsx` / `.css` | `scripts/check_file_length.py` |
| Phones: a multi-column `Grid` outside the design system passes `collapse`; a responsive component has a `Narrow` story; every section route and the master-detail / link flows work at iPhone width | ESLint `[ADR 0025 rule 10]`, `npm run ds:check`, the e2e `phone` project (`e2e/phone.spec.ts`) |

## Before any screen is built

Tokens and mockups are approved by the owner first (done 2026-10-03: Ideas, Screener
builder, Explore, Ingestion). A new mockup is needed only for a new screen/page or a visual
pattern in no approved mockup (a new chart type, layout or navigation pattern); a component
in an approved mockup, or built purely from existing tokens and primitives, needs none (its
PR carries stories, light/dark screenshots and axe; the owner reviews it there).
