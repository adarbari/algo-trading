/** Stacking tokens: FINAL (ADR 0011). The only z-index values components may use. */

export const zIndex = {
  base: 0,
  raised: 1,
  sticky: 10,
  dropdown: 100,
  overlay: 200,
  modal: 300,
  toast: 400,
  tooltip: 500,
} as const;
