import { describe, expect, it } from 'vitest';

import { screenerEdges, type ScreenerEdgesResponse } from './screener-edges';

const horizon = (sessions: number | null, hitRate: number | null = 0.6) => ({
  horizonSessions: 20,
  hitRate,
  baseRate: 0.5,
  liftPts: 10,
  sessions,
  picks: 100,
});
const record = (edgeId: string, trades: number | null, notRun: unknown = null) => ({
  screenerId: 's',
  edgeId,
  edgeName: edgeId.toUpperCase(),
  runLabel: null,
  splitFrom: '2026-04-01',
  afterSession: false,
  notRun,
  horizons: trades === null ? [] : [horizon(trades)],
});
const response = (
  records: ReturnType<typeof record>[],
  statuses: Record<string, string>,
): ScreenerEdgesResponse =>
  ({
    edges: Object.entries(statuses).map(([id, status]) => ({ id, status })),
    screener: { id: 's', trackRecords: records },
  }) as unknown as ScreenerEdgesResponse;

describe('screenerEdges', () => {
  it('puts the strongest status first, then the most trades', () => {
    const edges = screenerEdges(
      response([record('a', 30), record('b', 10), record('c', 90)], {
        a: 'candidate',
        b: 'evidenced',
        c: 'candidate',
      }),
    );
    expect(edges.map((e) => e.edgeId)).toEqual(['b', 'c', 'a']);
  });

  it('carries the frozen figures, and none for an edge that has not run', () => {
    const notRun = { code: 'NOT_RUN', kind: 'NOT_RUN', guideTerm: 'not_run', kindText: 'x' };
    const [ran, waiting] = screenerEdges(
      response([record('a', 30), record('b', null, notRun)], { a: 'evidenced', b: 'evidenced' }),
    );
    expect(ran?.figures).toMatchObject({ hitRate: 0.6, baseRate: 0.5, trades: 30, liftPts: 10 });
    expect(ran?.frozenSince).toBe('2026-04-01');
    expect(waiting?.figures).toBeNull();
    expect(waiting?.notRun?.kindText).toBe('x');
  });

  it('never shows a bare win rate: a record missing its trades has no figures', () => {
    const [only] = screenerEdges(response([record('a', 0)], { a: 'candidate' }));
    expect(only?.figures?.trades).toBe(0);
    const partial = response([record('a', 5)], { a: 'candidate' });
    const trackRecords = partial.screener?.trackRecords;
    if (trackRecords?.[0]) trackRecords[0].horizons = [horizon(null)];
    expect(screenerEdges(partial)[0]?.figures).toBeNull();
  });

  it('is empty for a screener no edge lists', () => {
    expect(screenerEdges(response([], {}))).toEqual([]);
  });
});
