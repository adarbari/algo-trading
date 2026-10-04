import { describe, expect, it } from 'vitest';

import { layoutLabels } from './labelLayout';

describe('layoutLabels', () => {
  it('keeps well separated labels on the first row', () => {
    const out = layoutLabels(
      [
        { x: 100, chars: 8 },
        { x: 300, chars: 8 },
      ],
      480,
    );
    expect(out.map((p) => p.row)).toEqual([0, 0]);
  });

  it('stacks a colliding label, then drops one that fits in neither row', () => {
    const out = layoutLabels(
      [
        { x: 200, chars: 8 },
        { x: 210, chars: 8 },
        { x: 215, chars: 8 },
      ],
      480,
    );
    expect(out.map((p) => p.row)).toEqual([0, 1, 'hidden']);
  });

  it('pins labels near the edges instead of overflowing', () => {
    const out = layoutLabels(
      [
        { x: 5, chars: 8 },
        { x: 475, chars: 8 },
      ],
      480,
    );
    expect(out.map((p) => p.edge)).toEqual(['start', 'end']);
  });
});
