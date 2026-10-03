/**
 * Typography tokens: FINAL (approved mockups 2026-10-03; ADR 0011). IBM Plex Sans for UI and
 * IBM Plex Mono for symbols, ids and code, self-hosted (@fontsource, loaded by UiProvider).
 * Tabular numbers everywhere. A small scale for dense working screens; body is 13 px.
 */

export const fontFamily = {
  sans: "'IBM Plex Sans', system-ui, -apple-system, 'Segoe UI', sans-serif",
  mono: "'IBM Plex Mono', ui-monospace, SFMono-Regular, Menlo, monospace",
} as const;

/** Size and line height per step, in px (line height ~1.45 rounded to whole px). */
export const fontSize = {
  /** Column headers, heatmap axis labels, legends. */
  xs: { size: 11.5, lineHeight: 16 },
  /** Captions, metadata, secondary cells. */
  sm: { size: 12, lineHeight: 17 },
  /** Table cells and dense lists. */
  md: { size: 12.5, lineHeight: 18 },
  /** Body text and panel headings: the default. */
  base: { size: 13, lineHeight: 19 },
  lg: { size: 14, lineHeight: 20 },
  xl: { size: 16, lineHeight: 22 },
  /** Page title (h1). */
  '2xl': { size: 18, lineHeight: 24 },
  '3xl': { size: 22, lineHeight: 28 },
} as const;

export const fontWeight = { regular: 400, medium: 500, semibold: 600 } as const;

/** Tabular figures everywhere: numbers line up in columns. */
export const fontFeatures = "'tnum' 1";

export type FontSize = keyof typeof fontSize;
export type FontWeight = keyof typeof fontWeight;
