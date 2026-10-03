---
name: add-ui-component
description: Add or change any UI widget, screen or visual element in apps/web. Always use before writing frontend code, so the design system is checked and extended first.
---

# Add a UI component or screen

Read first: `docs/ui/design-system.md` and ADR 0011.

1. **Check the inventory:** read `apps/web/design-system/COMPONENTS.md`. Can an existing
   component, or a composition or configuration of components, do the job? Then use it
   and stop here.
2. **Missing? Design it generically.** Name it for what it is (`DataTable`, `SplitPane`), not
   the screen (`ScreenerTable`). Expose behaviour through props and slots; no
   screen-specific branches inside.
3. **Build it in the design system** (`apps/web/design-system/components/<Name>/`):
   - styling only through tokens (no hex colours, no one-off sizes)
   - light and dark, compact and comfortable density, keyboard and screen-reader accessible
   - `<Name>.stories.tsx` (every state: default, loading, empty, error, dense data)
   - `<Name>.test.tsx` + a Playwright screenshot snapshot
4. **Regenerate** `COMPONENTS.md`.
5. **Use it** from `apps/web/app/`. Screens contain layout and data wiring only.
6. **Style check:** dense but calm. No gradients, glows, decorative shadows, emoji icons,
   or numbers wrapped in big cards. One accent colour.
7. Run the web checks (lint, typecheck, tests, screenshots) and `make check`.
