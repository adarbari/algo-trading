/** Shape tokens (DRAFT, ADR 0011): radius 4-6 px; borders, not shadows, separate surfaces. */

export const radius = { none: 0, sm: 4, md: 6, full: 9999 } as const;

export const borderWidth = { thin: 1, thick: 2 } as const;

/** Focus ring: a solid outline (never a glow). */
export const focusRing = { width: 2, offset: 1 } as const;

export type Radius = keyof typeof radius;
