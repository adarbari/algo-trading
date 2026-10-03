/**
 * Typography tokens (DRAFT, ADR 0011): Inter for UI with tabular numbers everywhere, one
 * monospace for symbols and code, a small scale for dense working screens (11-20 px).
 */

export const fontFamily = {
  sans: "'Inter Variable', Inter, system-ui, -apple-system, 'Segoe UI', sans-serif",
  mono: "'JetBrains Mono Variable', 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace",
} as const;

/** Size and line height per step, in px. */
export const fontSize = {
  xs: { size: 11, lineHeight: 16 },
  sm: { size: 12, lineHeight: 16 },
  md: { size: 13, lineHeight: 20 },
  lg: { size: 14, lineHeight: 20 },
  xl: { size: 16, lineHeight: 24 },
  '2xl': { size: 20, lineHeight: 28 },
} as const;

export const fontWeight = { regular: 400, medium: 500, semibold: 600 } as const;

/** `tnum` everywhere: numbers line up in columns; `cv11`: single-storey a for calmer text. */
export const fontFeatures = "'tnum' 1, 'cv11' 1";

export type FontSize = keyof typeof fontSize;
export type FontWeight = keyof typeof fontWeight;
