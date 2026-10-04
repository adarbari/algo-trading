/**
 * Collision avoidance for the labels above a histogram: each label gets the first of two rows
 * where it does not overlap one already placed, else it is hidden (its line stays, and the
 * accessible summary still lists it). Earlier markers have priority. Pure, so it is unit tested.
 */

/** Rough width of one label character (px) at the xs size, and the padding either side. */
export const CHAR_WIDTH = 7;
export const LABEL_PADDING = 8;
/** Space kept between two labels in one row (px). */
const GAP = 4;

export interface LabelInput {
  /** Centre of the marker line, px from the plot's left edge. */
  x: number;
  /** The label's text length in characters. */
  chars: number;
}

export interface LabelPlacement {
  /** 0 = nearest the plot, 1 = stacked above it, `hidden` = dropped. */
  row: 0 | 1 | 'hidden';
  /** `start` / `end` when the label is pinned to an edge instead of centred. */
  edge: 'start' | 'end' | undefined;
}

const ROWS = 2;

export function layoutLabels(labels: readonly LabelInput[], plotWidth: number): LabelPlacement[] {
  const rows: [number, number][][] = Array.from({ length: ROWS }, () => []);
  return labels.map(({ x, chars }): LabelPlacement => {
    const width = chars * CHAR_WIDTH + LABEL_PADDING;
    let left = x - width / 2;
    let edge: LabelPlacement['edge'];
    if (left < 0) {
      left = x;
      edge = 'start';
    } else if (left + width > plotWidth) {
      left = x - width;
      edge = 'end';
    }
    const right = left + width;
    for (let row = 0; row < ROWS; row += 1) {
      const taken = rows[row] as [number, number][];
      if (taken.every(([l, r]) => right + GAP <= l || left >= r + GAP)) {
        taken.push([left, right]);
        return { row: row as 0 | 1, edge };
      }
    }
    return { row: 'hidden', edge };
  });
}
