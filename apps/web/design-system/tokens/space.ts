/**
 * Spacing and size tokens: FINAL (ADR 0011). A 4 px scale with the two half steps the mockups
 * use (6 px and 10 px: control and panel-header padding). Step n = n * 4 px.
 */

export const spaceUnit = 4;

export const space = {
  0: 0,
  0.5: 2,
  1: 4,
  1.5: 6,
  2: 8,
  2.5: 10,
  3: 12,
  4: 16,
  5: 20,
  6: 24,
  8: 32,
  10: 40,
} as const;

export type Space = keyof typeof space;

/** CSS variable suffix for a step (`0.5` -> `0-5`). */
export function spaceName(step: Space): string {
  return String(step).replace('.', '-');
}

/**
 * Container widths (px) at which a Grid with `collapse` drops to one column. Container queries
 * cannot read custom properties, so Grid.module.css repeats these numbers; Grid.test.tsx fails
 * if the two disagree.
 */
export const breakpoint = { sm: 480, md: 720, lg: 960 } as const;

export type Breakpoint = keyof typeof breakpoint;

/** Fixed track widths for Grid templates. */
export const size = {
  /** The label column of a label / value grid. */
  label: 140,
  /** A side panel (filters, detail). */
  sidebar: 320,
  /** The widest a working page grows (mockups: 1600). */
  page: 1600,
  /** Icons (stroke set, 16 px grid): small (in badges, chips), default (mockups: 14), large. */
  'icon-sm': 12,
  'icon-md': 14,
  'icon-lg': 16,
  /** A popover list (combobox options) at its narrowest. */
  popover: 280,
  /** A search box in the top bar (mockups: 220). */
  search: 220,
  /** A phone's width (the narrowest iPhone): the frame of the `Narrow` stories. */
  phone: 375,
} as const;
