---
name: add-ui-component
description: Add or change any UI widget, visual element or design-system component in apps/web. Always use before writing frontend code, so the design system is checked and extended first and nothing is built outside a component.
---

# Add a UI component

Read first: `docs/ui/architecture.md` (ADR 0025: layers, rules), `docs/ui/design-system.md`
(ADR 0011: tokens, style). A whole page or route: `.claude/skills/add-web-page`.

0. **Where it goes** (`docs/ui/architecture.md`, "Where does it go?"):
   - styling, HTML, a reusable visual piece: the design system,
     `apps/web/design-system/components/<Name>/` (layout / typography building block:
     `primitives/<Name>/`; a token: `tokens/`);
   - app code composing components: `src/{pages,widgets,features,entities}/<slice>/`, by layer.
   Layer rules: `app -> pages -> widgets -> features -> entities -> shared -> @algotrade/ui`;
   no imports between slices of one layer; other slices only through their `index.ts`. If no
   folder fits, declare a new one as a `[[web_dir]]` in `architecture/web_layout.toml`; never park
   code in a neighbour. At most 10 modules per folder (`make layout` warns at 8).
1. **Check the inventory:** read `apps/web/design-system/COMPONENTS.md`. Can an existing
   component, or a composition or configuration of components, do the job? Then use it
   and stop here.
2. **Missing? Design it generically.** Name it for what it is (`DataTable`, `SplitPane`), not
   the screen (`ScreenerTable`). Expose behaviour through props, variants and slots; no
   screen-specific branches; never accept `className` or `style` from callers.
   **Mockup gate (ADR 0011):** an owner-approved mockup is required first for a **new
   screen/page**, or a **visual pattern in no approved mockup** (a new chart type, layout or
   navigation pattern). **No mockup** for a component that appears in an approved screen
   mockup or is built purely from existing tokens and primitives; its PR still carries
   stories for every state, light and dark screenshots and axe, and the owner reviews it there.
3. **Build it in the design system**: copy the template `design-system/primitives/Text/`:
   - `Name.tsx` (file docstring = its catalogue description; `NameProps` with a JSDoc per
     prop), `Name.module.css` (tokens only: `var(--color-*)`, `var(--space-*)`, ...; variants
     as data attributes; no hex, px, gradients, shadows), `index.ts`
   - light and dark, compact and comfortable density, keyboard and screen-reader accessible
   - phones and desktops from the one component (`.claude/skills/responsive-ui`, ADR 0052):
     container queries for layout, touch sizing under a coarse pointer, nothing hover-only;
     a `Narrow` story (the `narrow` decorator in `design-system/testing`) when it has a
     container or coarse-pointer rule
   - `Name.stories.tsx`: `Default`, `Loading`, `Empty`, `Error`, `Dense` (or the reason one
     does not apply in `parameters.states.notApplicable`)
   - `Name.test.tsx` with `expectNoA11yViolations` (from `../../testing`)
   - export it from `components/index.ts` (and so from `@algotrade/ui`)
4. **Regenerate and verify** (in `apps/web`): `npm run components:md`, `npm run ds:check`,
   `npm run storybook` to look at it, `npm run visual:update` (Docker) to write the
   light / dark screenshots into `__screenshots__/`; commit them.
5. **Use it** from the app layer that owns the need, importing only from `@algotrade/ui`. App
   code renders no HTML elements and passes no `className` / `style` (ESLint fails it).
6. **Style check:** dense but calm. No gradients, glows, decorative shadows, emoji icons,
   or numbers wrapped in big cards. One accent colour. Borders, not shadows.
7. Run `make web-check` (or `npm run check`), `make web-visual`, and `make check`.
