/** Shape tokens: FINAL (ADR 0011). Radius 3 / 4 / 6 px; crisp 1 px borders, never shadows. */

/** sm: bars, tracks, swatches; md: controls, chips, nav items; lg: panels. */
export const radius = { none: 0, sm: 3, md: 4, lg: 6 } as const;

export const borderWidth = { thin: 1, thick: 2 } as const;

/** Focus ring: a solid accent outline (never a glow). */
export const focusRing = { width: 2, offset: 1 } as const;

export type Radius = keyof typeof radius;
