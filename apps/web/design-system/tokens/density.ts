/**
 * Density tokens: FINAL (ADR 0011). `compact` (the default: IBKR-like density, from the
 * mockups' 28 px rows and 26 px controls) and `comfortable`. Components size controls, rows
 * and panel padding from these, never from fixed values.
 */

export interface Density {
  readonly controlHeight: number;
  readonly rowHeight: number;
  readonly cellPaddingX: number;
  readonly cellPaddingY: number;
  /** Panel header / body padding. */
  readonly panelPaddingX: number;
  readonly panelPaddingY: number;
  readonly gap: number;
}

export const density = {
  compact: {
    controlHeight: 26,
    rowHeight: 28,
    cellPaddingX: 8,
    cellPaddingY: 5,
    panelPaddingX: 16,
    panelPaddingY: 10,
    gap: 8,
  },
  comfortable: {
    controlHeight: 32,
    rowHeight: 36,
    cellPaddingX: 12,
    cellPaddingY: 9,
    panelPaddingX: 20,
    panelPaddingY: 14,
    gap: 12,
  },
} as const satisfies Record<string, Density>;

export type DensityName = keyof typeof density;

export const defaultDensity: DensityName = 'compact';
