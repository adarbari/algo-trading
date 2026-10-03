/** Spacing tokens (DRAFT, ADR 0011): a 4 px base scale. Step n = n * 4 px. */

export const spaceUnit = 4;

export const space = {
  0: 0,
  0.5: 2,
  1: 4,
  2: 8,
  3: 12,
  4: 16,
  5: 20,
  6: 24,
  8: 32,
  10: 40,
  12: 48,
} as const;

export type Space = keyof typeof space;

/** CSS variable suffix for a step (`0.5` -> `0-5`). */
export function spaceName(step: Space): string {
  return String(step).replace('.', '-');
}
