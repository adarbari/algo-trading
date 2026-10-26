/** Shape tokens (ADR 0085, amending 0011): radius 4 / 10 / 16 px and pill; crisp 1 px borders, never shadows. */

/** sm: bars, tracks, swatches; md: controls, nav items; lg: cards and panels; pill: verdict chips. */
export const radius = { none: 0, sm: 4, md: 10, lg: 16, pill: 999 } as const;

export const borderWidth = { thin: 1, thick: 2 } as const;

/** Focus ring: a solid accent outline (never a glow). */
export const focusRing = { width: 2, offset: 1 } as const;

export type Radius = keyof typeof radius;
