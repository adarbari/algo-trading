/** The Guide's Edges section is one splat route: the index, a mechanism and an edge all reach it. */
import { describe, expect, it } from 'vitest';

import { router } from './router';

const splatOf = (path: string): { id: string; splat: unknown } | undefined => {
  const match = router.matchRoutes(path).find((m) => m.routeId.endsWith('/edges/$'));
  return match && { id: match.routeId, splat: (match.params as Record<string, unknown>)['_splat'] };
};

describe('the Guide Edges route', () => {
  it('matches the index, a mechanism page and an edge page', () => {
    expect(splatOf('/guide/edges')?.splat ?? '').toBe('');
    expect(splatOf('/guide/edges/m/slow_to_update')?.splat).toBe('m/slow_to_update');
    expect(splatOf('/guide/edges/momentum_12_1')?.splat).toBe('momentum_12_1');
  });
});
