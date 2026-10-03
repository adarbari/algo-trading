/**
 * Motion tokens (DRAFT, ADR 0011): 100-150 ms, no bouncing. Durations drop to 0 under
 * `prefers-reduced-motion: reduce` (see css.ts).
 */

export const duration = { fast: 100, base: 150 } as const;

export const easing = { standard: 'cubic-bezier(0.2, 0, 0, 1)' } as const;
