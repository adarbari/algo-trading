import { describe, expect, it } from 'vitest';

import { edgeMatches, filterOptions, type EdgeFacts } from './filter';

const edge = (over: Partial<EdgeFacts> = {}): EdgeFacts => ({
  id: 'e1',
  name: 'Earnings-date advances',
  thesis: 'Stocks reporting early outperform.',
  mechanism: 'slow_to_update',
  assetText: 'Stocks',
  asset: 'stocks',
  side: 'long',
  holdingText: '20 sessions',
  holdingBand: 'medium',
  status: 'candidate',
  ...over,
});

describe('a mechanism page’s edge filters', () => {
  it('lets every edge through with no filter', () => {
    expect(edgeMatches(edge(), {})).toBe(true);
  });

  it('narrows by status, asset, side and holding band, each on the server’s id', () => {
    expect(edgeMatches(edge(), { status: 'rejected' })).toBe(false);
    expect(edgeMatches(edge(), { asset: 'etfs' })).toBe(false);
    expect(edgeMatches(edge(), { side: 'long', holding: 'medium', status: 'candidate' })).toBe(
      true,
    );
    expect(edgeMatches(edge(), { holding: 'short' })).toBe(false);
  });

  it('offers the values the edges carry, once each, with how many', () => {
    const options = filterOptions([
      edge(),
      edge({ id: 'e2' }),
      edge({ id: 'e3', status: 'rejected', assetText: 'ETFs', asset: 'etfs', side: 'long_short' }),
    ]);
    expect(options.status.map((o) => o.label)).toEqual(['Candidate · 2', 'Rejected · 1']);
    expect(options.asset.map((o) => o.value)).toEqual(['stocks', 'etfs']);
    expect(options.side.map((o) => o.label)).toEqual(['Long · 2', 'Long-short · 1']);
    expect(options.holding).toEqual([{ value: 'medium', label: 'Medium · 3' }]);
  });
});
