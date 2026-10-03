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
| Size | `label` 140, `sidebar` 320, `page` 1600 px (max page width) |
| Breakpoints (Grid `collapse`, container width) | sm 480, md 720, lg 960 px |
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

Panel (header, actions, loading / empty / error states) is a component on top of `Surface`
(design system PR 2).

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

Charts come in design system PR 4. Where a data component needs a PR 2 control (Checkbox,
Button, StatusBadge) before PR 2 has merged, it uses a minimal internal placeholder marked
`TODO(design system PR 2)`, replaced when PR 2 lands.

### Value formatting

`formatValue(value, format)` (`design-system/format/`, exported from `@algotrade/ui`) is the one
place that decides how a value reads: `number` (`11,427`), `percent` (a fraction: 0.721 ->
`72.1%`), `currency` (`$333.69`), `currency-compact` (`$13.99B`, `$412M`), `compact`
(`11.4K`), `date` (`2 Oct 2026`, `Fri 2 Oct`, ISO) and `delta` (`+1.24%`, `−3.4%`, `+3.2 pts`,
with an up / down tone). Missing values read as an em dash in the muted tone; negatives use the
typographic minus. DataTable, KeyValue, StatStrip, StackedBar and BarList format through it, so
screens never format numbers themselves.

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

Tokens and mockups are approved by the owner first (done 2026-10-03: Ideas, Screener
builder, Explore, Ingestion). Only then is the component catalogue built, and only after
that the app.
