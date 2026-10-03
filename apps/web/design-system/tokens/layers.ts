/** Stacking tokens (DRAFT): the only z-index values components may use. */

export const zIndex = {
  base: 0,
  sticky: 10,
  dropdown: 100,
  overlay: 200,
  toast: 300,
  tooltip: 400,
} as const;
