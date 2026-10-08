---
name: responsive-ui
description: Make or keep a web screen, widget or design-system component usable on phones and desktops from the one component tree (ADR 0052). Use whenever UI is added or changed in apps/web, when a layout has a list beside its detail, a table, a chart, a toolbar or a tooltip, or when a phone-width check (phone e2e project, Narrow story, Grid collapse lint) fails.
---

# Responsive UI: one tree for phones and desktops

Read first: ADR 0052 (`docs/adr/0052-one-ui-for-phones-and-desktops.md`), `docs/ui/architecture.md`
rule 10. Components: `.claude/skills/add-ui-component`; pages: `.claude/skills/add-web-page`.
Never a mobile page, route, widget or component variant: adapt the one component.

## Checklist for every UI change

1. **Width is the container's, not the viewport's.** Layout changes below a width use
   `@container (width < 720px)` (the `breakpoint` tokens `sm` 480 / `md` 720 / `lg` 960 in
   `design-system/tokens/space.ts`; repeat the number in CSS the way `primitives/Grid` does and
   keep its test in sync). A component that must change its *tree* below a width uses
   `useNarrow(breakpoint)` from `design-system/responsive/`. App code never measures or reads
   `matchMedia`: what differs by width is a prop on a design-system component.
2. **Multi-column layout collapses.** Every `Grid` with more than one column outside the design
   system passes `collapse="md"` or `"lg"` (ESLint, ADR 0025 rule 10). Fixed tracks
   (`sidebar-*`, `label-value`, `main-aside`) collapse like the rest.
3. **A list beside its detail is `MasterDetail`** (`master`, `detail`, `detailKey`,
   `detailTitle`, `onDetailClose`, optional `summary` shown above the list on narrow). Choosing
   an item changes `detailKey`; dismissing the sheet calls `onDetailClose`, which clears the
   choice (URL param or state) so the next tap opens it again. Never a page-level Grid for this.
4. **Touch targets.** Controls size from the density tokens; under `@media (pointer: coarse)`
   they take the `touch` values (36 px controls, 40 px rows). A new small variant keeps
   `min-height: var(--density-control-height)` under a coarse pointer. Nothing depends on
   hover alone: a tooltip also opens on focus and tap, a read-out has a tap equivalent, a
   keyboard shortcut is never the only way to an action (a button exists too).
5. **Tables** are `DataTable` with the key column pinned (`pinFirst`, default on) and
   sideways scroll; never a second "cards" table. Put the columns a phone needs first.
6. **Charts** keep touch on (pinch, horizontal drag) and the zoom buttons; mouse wheel and
   drag stay off (the range control sets the window).
7. **Navigation is reachable by touch**: every name that opens something (a screener, a
   ticker, a run) is a Button or link, not text beside a hidden column or a keyboard hint.
8. **Top bar**: sections scroll sideways in one row under `md`; never a hamburger menu.

## Checks (all in `make web-check`)

- `npm run ds:check`: a component whose CSS has `@container` or `pointer: coarse` exports a
  `Narrow` story (the `narrow` decorator in `design-system/testing`: a 375 px container); the
  visual suite screenshots it light and dark and runs axe.
- ESLint `[ADR 0025 rule 10]`: a multi-column `Grid` outside the design system has `collapse`.
- `npx playwright test --project=phone` (`e2e/phone.spec.ts`, iPhone 13 emulation): every
  section route without horizontal overflow, the top bar under 30 % of the viewport, no console
  errors, axe; Explore row tap opens the detail sheet; Ideas screener name opens its results;
  the chart has its zoom buttons. A new route is covered by the workspaces list; a new
  master-detail or link flow adds an assertion there.
- Verify by hand once: the Vite dev server in the browser pane at the `mobile` preset
  (375 x 812), text and accessibility tree first, one reduced-scale screenshot per state.
