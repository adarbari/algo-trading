import { describe, expect, it } from 'vitest';

import { EDGES_FIXTURE } from '@/entities/edge';

import { asksReason, canReveal, isEdgeId, movesFrom, TARGET, warnsFollow } from './moves';

const [momentum, mine, drift] = [
  EDGES_FIXTURE.edges[0],
  EDGES_FIXTURE.edges.find((e) => e.id === 'my_momentum'),
  EDGES_FIXTURE.edges.find((e) => e.id === 'earnings_drift'),
];

describe('the moves a state allows', () => {
  it('follows the API transitions', () => {
    expect(movesFrom('researching')).toEqual(['follow', 'reject']);
    expect(movesFrom('following')).toEqual(['retire', 'reopen']);
    expect(movesFrom('rejected')).toEqual(['reopen']);
    expect(movesFrom('unknown')).toEqual([]);
    expect(TARGET.follow).toBe('following');
    expect(TARGET.reveal).toBeUndefined();
  });

  it('asks a reason for a rejection and a retirement', () => {
    expect([asksReason('reject'), asksReason('retire'), asksReason('follow')]).toEqual([
      true,
      true,
      false,
    ]);
  });

  it('shows a copy its hidden result, never a site edge', () => {
    expect(mine && canReveal(mine)).toBe(true);
    expect(momentum && canReveal(momentum)).toBe(false);
  });

  it('warns a follow only on a verdict that is not good', () => {
    expect(drift && warnsFollow(drift)).toBe(true);
    expect(momentum && warnsFollow(momentum)).toBe(false);
  });

  it('checks an edge id the way the API does', () => {
    expect(isEdgeId('my-edge_2')).toBe(true);
    expect(isEdgeId('My')).toBe(false);
    expect(isEdgeId('')).toBe(false);
  });
});
