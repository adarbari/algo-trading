# ADR 0052: One UI for phones and desktops

**Status:** accepted (2026-10-07; owner decision: the UI must serve phones as well as desktops,
without a second code base). Extends [0011](0011-design-system-first-ui.md) and
[0025](0025-frontend-architecture.md) (rule 10 below). Skill: `.claude/skills/responsive-ui`.

## Context
The web app was built against desktop mockups: a top bar that wraps into three rows on a phone,
list-beside-detail pages (Explore, screener results) whose detail drops below a 1 000 px table
when the grid collapses so a tap on a row changes nothing visible, a chart that ignores touch
(pinch, drag), 26 px controls, hover-only read-outs, and no test at any phone width. The only
responsive tools were Grid `collapse` and two container queries. Two ways to serve phones:
(a) a mobile app or mobile pages beside the desktop ones, or (b) the one component tree adapts
to the space and the pointer it has.

## Decision
1. **One component tree** (b). No mobile pages, routes, widgets or "m." variants: a screen is
   the same composition of `@algotrade/ui` at every width. Adapting is the design system's job;
   app code only states what collapses (`collapse`) and what is a list beside its detail
   (`MasterDetail`).
2. **Container queries, not viewport media queries, decide layout.** A component reacts to the
   width it has (`@container (width < <breakpoint>)`, the `breakpoint` tokens `sm` 480, `md` 720,
   `lg` 960; a test keeps the CSS numbers equal to the tokens). A component that must change
   its tree below a width, not only its CSS, measures itself with `useNarrow`
   (`design-system/responsive/`). `@media (pointer: coarse)` is used only for touch sizing.
3. **A list beside its detail is `MasterDetail`.** Wide: a Grid of the two. Narrow: the list,
   and the detail in a `Drawer` that opens when the chosen item (`detailKey`) changes and goes
   back to the list on dismiss, which clears the choice in the URL or state. A page never
   re-implements this with its own Grid.
4. **Touch sizing is a token.** Under a coarse pointer the density variables take the `touch`
   values (`tokens/density.ts`: 36 px controls, 40 px rows) and every small variant (Button `sm`,
   IconButton, Chip, Tabs, NavTabs, SegmentedControl, Checkbox) keeps at least the control height.
   Information shown only on hover (tooltips, the chart read-out) also appears on focus or
   touch; a keyboard-only hint is not the only way to an action.
5. **Tables scroll sideways with their key column pinned** (DataTable `pinFirst`, default on),
   never a second mobile table. **The chart** accepts pinch and horizontal drag on touch and has
   zoom in / out / reset buttons for every pointer; mouse wheel and drag stay off (the range
   control sets the window).
6. **Rule 9 (ADR 0025):** a multi-column `Grid` outside the design system passes `collapse`
   (ESLint); a component with a container or coarse-pointer rule has a `Narrow` story at 375 px
   (`ds:check`, screenshot and axe in the visual suite); the e2e suite runs a `phone` project
   (iPhone 13 emulation: every section route without horizontal overflow, the top bar under 30 %
   of the viewport, the master-detail and link flows above).

## Consequences
- Phones are served from the day a component is written: the skill `.claude/skills/responsive-ui`
  is the checklist, and `add-ui-component` / `add-web-page` point to it.
- Stories gain one state (`Narrow`), the visual suite a few screenshots, the e2e suite one
  project (about 20 s). No new package, route or page.
- A page cannot know whether it is narrow (no hook in app code): what differs by width is a
  prop on a design-system component (`summary` on MasterDetail, `collapse` on Grid). A need no
  component covers is a design-system change first (ADR 0011), never a media query in a page.
- Admin pages are covered by the same rules; the ingestion drilldown is a `MasterDetail` (MU2).

## Amendment 2026-10-07 (MU2, owner's phone test)
- **The workspace switch leaves the top bar** (owner decision: not in the bar's prime space).
  It lives in the `AccountMenu` behind the viewer's name, shown only to a viewer who may enter
  more than one workspace; the bar is brand, sections, the Guide, the status chips and the
  name, a two-row grid under 720 px (about 100 px on a phone; the phone e2e bounds it at 112 px).
  ADR 0025's "switched in a horizontal top bar" reads with this amendment.
- **Narrow tables show their `essential` columns** (else the first three) and the column picker,
  so the user adds the rest; the catalogue columns are hideable there.
- **Tooltips open on a tap** under a coarse pointer; **keyboard hints** are a `KeyHints` row the
  design system hides under a coarse pointer; a table row that opens something takes a tap
  (`onRowActivate`); Explore's compare set has a Compare button that opens the detail sheet.
