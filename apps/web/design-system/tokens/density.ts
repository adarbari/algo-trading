/**
 * Density tokens (DRAFT, ADR 0011): `compact` (the default, for data screens) and
 * `comfortable`. Components size controls and rows from these, never from fixed values.
 */

export interface Density {
  readonly controlHeight: number;
  readonly rowHeight: number;
  readonly cellPaddingX: number;
  readonly cellPaddingY: number;
  readonly gap: number;
}

export const density = {
  compact: { controlHeight: 24, rowHeight: 28, cellPaddingX: 8, cellPaddingY: 4, gap: 8 },
  comfortable: { controlHeight: 32, rowHeight: 36, cellPaddingX: 12, cellPaddingY: 8, gap: 12 },
} as const satisfies Record<string, Density>;

export type DensityName = keyof typeof density;

export const defaultDensity: DensityName = 'compact';
