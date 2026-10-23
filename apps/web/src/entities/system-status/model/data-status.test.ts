import { describe, expect, it } from 'vitest';

import { dataStatusOf, type DatasetView } from './data-status';

const BASE = {
  date: '2026-10-22',
  newer: null,
  dataStatus: {
    state: 'COMPLETE' as const,
    knowledgeTs: '2026-10-22T21:05:00+00:00',
    datasets: [
      { name: 'PRICES' as const, status: 'COMPLETE' as const, share: 0.99, unavailable: [] },
      {
        name: 'FUNDAMENTALS' as const,
        status: 'UNKNOWN' as const,
        share: null,
        unavailable: [
          {
            kindText: 'Not available yet',
          },
        ],
      },
    ],
    affectedScreeners: 2,
    totalScreeners: 7,
  },
};

describe('dataStatusOf', () => {
  it('passes the server figures through without deriving any', () => {
    const view = dataStatusOf(BASE);
    expect(view.state).toBe('COMPLETE');
    expect(view.datasets[0]).toMatchObject({ share: 0.99, gap: null, gaps: [] });
    expect([view.affectedScreeners, view.totalScreeners]).toEqual([2, 7]);
    expect(view.newerDate).toBeNull();
  });

  it('keeps an unknown dataset without a share and its gap as served', () => {
    const unknown = dataStatusOf(BASE).datasets[1] as DatasetView;
    expect(unknown.share).toBeNull();
    expect(unknown.gap).toBe('Not available yet');
    expect(unknown.gaps).toHaveLength(1);
  });

  it('names the newer session', () => {
    expect(dataStatusOf({ ...BASE, newer: { date: '2026-10-23' } }).newerDate).toBe('2026-10-23');
  });
});
