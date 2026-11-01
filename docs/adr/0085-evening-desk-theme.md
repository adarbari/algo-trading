# ADR 0085: The "Evening Desk" look (both themes, Sora / Figtree / DM Mono) and a Light / Dark / System choice

**Status:** accepted (2026-10-25; owner decision after comparing three directions on the mockup
canvas; an architect reviewed this ADR). Amends [0011](0011-design-system-first-ui.md) (the
colour, type, shape and density tokens marked FINAL on 2026-10-03 are replaced; the order
tokens, mockups, components, screens and the "design system first" rule stand) and uses
[0025](0025-frontend-architecture.md) (layers), [0029](0029-rule-screener.md) /
[0032](0032-screener-review-table.md) (user `preferences.toml`, written through
`services/authoring`), [0051](0051-guide-explain-once-show-in-place.md) (every new word has a Guide entry),
[0052](0052-one-ui-for-phones-and-desktops.md) (one UI) and [0083](0083-workflow-first-trader-site.md)
(the product the look serves).

## Context
The site is becoming a paid product ([0083](0083-workflow-first-trader-site.md)). The 2026-10-03
tokens are "dense but calm" for an operator: IBM Plex at 13 px, 28 px table rows, near-black
neutrals, 3-6 px corners, dark only (`UiProvider` defaults to dark and nothing switches it,
although the light palette, its contrast tests and the `system` attribute already exist). A
part-time trader reading a shortlist after the close needs a warmer, more legible page, and some
will not use a dark page. The owner chose direction B, "Evening Desk" (soft dark, warm), and
asked for a light variant the user can choose.

## Decision
1. **The tokens are re-skinned in place.** Same files (`apps/web/design-system/tokens/*.ts`),
   same typed `Palette` (a role cannot exist in one theme only), same generator
   (`tokens/css.ts` -> `tokens.css`), same checks (`textPairs` AA contrast, series 3:1 and
   distinct, axe on every story, screenshots). No second theme system, no new styling
   mechanism; Stylelint still bans raw values, shadows and gradients (crisp 1 px borders stay).
2. **Colour** (owner-approved values; each is a role, components use `--color-<role>` only):

   | Role | Dark | Light |
   |---|---|---|
   | `bg` (ground) | `#121722` | `#F4F6FB` |
   | `bar` (top bar; new role) | `#171E2C` | `#FFFFFF` |
   | `surface` | `#1A2131` | `#FFFFFF` |
   | `row` (raised) | `#202839` | `#EEF1F8` |
   | `border` (line) | `#263048` | `#DEE3EE` |
   | `text` / `text-2` / `muted` | `#EEF1F6` / `#C4CBD9` / `#A3ACC0` | `#1A2033` / `#3F4860` / `#5D667D` |
   | `accent` / `on-accent` | `#AEBDFF` / `#121722` | `#3E55C9` / `#FFFFFF` |
   | `accent-soft` / `accent-strong` | `#252F4F` / `#AEBDFF` | `#E6EAFB` / `#3346B0` |
   | `empty` (no-data dot) | `#2C3650` | `#DCE1EC` |

   The three semantic hues map onto the existing roles, not new ones: **lamp** (the highlight)
   is `warning` (dark `#F5C26B` on `#3A2C14`; light text `#8A5A00` on `#FFF4DE`), **sea-glass**
   (evidence) is `positive` and `up` (dark `#6FD3B8` on `#173A33`; light text `#137560` on
   `#E2F5EF`), **loss** is `negative` and `down` (dark `#F4A38F`; light text **`#AD4631`**).
   Two deviations from the approved light values, forced by contrast and recorded here: the
   owner's loss `#C2563F` is 4.1:1 on the ground and 3.95:1 on a raised row (below AA for text),
   and the light fills (lamp `#D99A2B` 2.2:1, sea-glass `#1E9E80` 3.0:1, loss `#C2563F`) are
   below 3:1 for a graphic. So a role has one value, the AA-safe one, and a dot, a bar end or a
   series in light uses that role (`warning` / `positive` / `negative` fg), not a second lighter
   fill: no `fill` role. The dark series `s6` (`#586e1c`, 2.8:1 on the new surface) is retuned
   with the rest of the series. The colour-blind up / down pair (blue / orange) and the
   six-colour series stay, re-checked on the new surfaces by the same tests; series are still
   assigned by entity, never cycled.
3. **Type**: **Sora** (headings and display figures; `--font-display`, new), **Figtree** (body),
   **DM Mono** (numbers, symbols, ids, code), tabular figures everywhere, self-hosted from
   `@fontsource` as now (no CDN; `UiProvider` imports them; the `route-preload.ts` font
   pattern follows, with a test that it matches at least one bundled file; tabular figures are
   checked in the chosen subsets, since `tnum` is silently ignored by a font without them). Body is **15 px** (decision 5).
4. **Shape**: radius `md` 10 (controls, chips' non-pill kin), `lg` 16 (cards, panels), `sm` 4
   (bars, tracks), new `pill` (verdict chips are pills); borders 1 px, never shadows.
5. **Density is per workspace, and the type scale follows it.** TRADER runs the new
   *comfortable* density at the 15 px scale (rows and controls retuned to fit it, the touch
   floors of 0052 unchanged); ADMIN keeps *compact* with the existing 13 px scale, because its
   28 px-row tables do not fit 15 px. The workspace layout sets `data-density`
   (`UiProvider` already takes it); `src/app` sets it on `:root` once, because popovers render outside the page, and the login page, `/guide` and the ⌘K Explore popover take the density of the workspace they open from (Trader when unsure); a `Density` carries its type scale, so the scale is one
   token set keyed by density, not a second one.
6. **Light / Dark / System.** `Theme = 'light' | 'dark' | 'system'` (exists); the default for a
   user with no stored choice is **System** (the OS decides; Dark is no longer forced). The
   generated CSS makes `system` the behaviour of an *absent* attribute too (light, with its
   `color-scheme`, under `@media (prefers-color-scheme: light)` for `:root:not([data-theme='dark'])`,
   its cvd override after the dark one), so there is one fallback, not two. The choice is stored
   per user as `[appearance] theme` in `config/users/<id>/preferences.toml`, written by
   `services/authoring/preferences.py` and `PUT /preferences/appearance` (a write route, so an
   entry with its test in `architecture/read_your_writes.toml`, ADR 0077; the REST allow-list
   holds GET routes only), validated to one of the three values. It is **read** by a
   `load_appearance` loader in `services/read/users/` through `ConfigStore` and served as
   `Query.appearance { theme }` (`add-graphql-field`): a separate, cached field, not a field of
   `Query.viewer`, which is inline (no I/O) and which `guard.ts` needs to sign in; a missing or
   malformed file reads as `system`, never an error. The browser's storage is a cache, never the
   source of truth. **No flash**: an inline script in `index.html` sets `data-theme` before the
   first paint from a per-device mirror in `localStorage` (rewritten from `Query.appearance` on
   each load and on each change), and sets nothing when there is no mirror. `UiProvider` takes
   `theme` as *optional*: absent, it leaves the attribute as it is (never writes a default on
   mount), and only a value from the stored choice or the control replaces it. A user whose stored
   choice differs from their OS sees the wrong theme only on a device's first visit, until the
   first response; the login page (no user yet) follows the mirror, else the OS. The control (a
   three-option segmented control from the design system) lives in the account menu, and later
   in Settings. A change applies at once and saves in the background; a failed save keeps the
   choice for the session and says so. Role gating is untouched.
7. **Words**: "Theme", "Light", "Dark", "System" and the control's section get Guide entries
   in the same PR that ships the control (0051, `add-guide-content`).

## Consequences
- Every screenshot baseline is regenerated more than once (the `update-screenshots` label);
  each PR explains its visual diff. Contrast and axe stay the gate: a value that fails AA is
  adjusted in the token file and the deviation is recorded here, not waived.
- Dark and light become co-equal: stories, e2e and the screenshot projects keep both.
- The first-visit flash on a new device is the one accepted gap; removing it needs the API to
  render the attribute into `index.html`, which is not worth the coupling now.
- The type scale and density are tied, so a screen cannot mix 13 px and 15 px text outside the
  Admin / Trader split; a future per-user density would reuse the same mechanism.
- The older documents ([0011](0011-design-system-first-ui.md) notes, `docs/ui/design-system.md`,
  `CLAUDE.md`'s "tokens (FINAL ...)") are updated to point here.

- Because System is the default, Playwright (which defaults to a light scheme) turns every
  spec without a theme light: the e2e gets one theme helper and pins the colour scheme, and the
  five specs that set `data-theme` by hand use it. `chartTheme.ts` watches `data-density` as it
  already watches the theme, so chart text follows a density change.

## Delivery (small PRs)
ADR (this) -> tokens + fonts (colour, radius, families, `bar`; the font preload pattern) -> theme switch
(preference write, `Query.appearance`, no-flash script, account-menu control, Guide entries) ->
density and type-scale pass (TRADER comfortable at 15 px, ADMIN compact).
