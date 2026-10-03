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
- Style: dense but calm. Neutral greys, one accent, Inter with tabular numbers, borders
  instead of shadows, light and dark modes, compact density for data. No gradients, glows,
  emoji icons or card-wrapped numbers.
- Enforced by ESLint and Stylelint rules, a design-system completeness check and Playwright
  screenshot comparisons.

## Consequences
- The first UI work is slower; every later screen is faster and consistent.
