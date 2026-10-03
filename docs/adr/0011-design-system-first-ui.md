# ADR 0011: Design-system-first UI

**Status:** accepted (2026-10-02). Spec: [docs/ui/design-system.md](../ui/design-system.md).
Extended by [0025](0025-frontend-architecture.md) (frontend architecture: layers, component-only
app code, enforcement; [docs/ui/architecture.md](../ui/architecture.md)).

## Context
The owner wants a clean, modern, minimal UI and explicitly does not want generic
generated dashboards. A UI stays consistent only if its styling decisions live in one
place.

## Decision
- The UI is built in this order: **tokens → approved mockups → design-system components →
  screens**.
- Screens may use only components from `@algotrade/ui`. Before adding a widget, check the
  generated `COMPONENTS.md`. If nothing fits, add a **generic** component to the design
  system (with catalogue story, tests and screenshot snapshot), then use it.
- Style: dense but calm. Neutral greys, one accent, IBM Plex Sans + IBM Plex Mono with
  tabular numbers (originally Inter; changed with the approved mockups), borders instead of
  shadows, dark-first with a light mode, compact density for data. No gradients, glows,
  emoji icons or card-wrapped numbers.
- Enforced by ESLint and Stylelint rules, a design-system completeness check and Playwright
  screenshot comparisons.

## Consequences
- The first UI work is slower; every later screen is faster and consistent.

## Notes
- **2026-10-03: tokens final (approved mockups 2026-10-03).** The owner approved the mockups
  (Trader: Ideas, Screener builder, Explore; Admin: Ingestion). The tokens in
  `apps/web/design-system/tokens/` are now final: dark-first Webull-like surfaces with 1 px
  borders, one blue accent, status tints, colour-blind-safe up / down, a six-colour series
  palette, IBM Plex Sans + Mono (self-hosted), a 11.5-22 px scale, compact / comfortable
  density. Tables and the font decision: [design-system.md](../ui/design-system.md#tokens-final).
  Screens lay out and set text only with the primitives (Box, Surface, Stack, Grid, Text,
  Heading, Mono, Divider, VisuallyHidden).
