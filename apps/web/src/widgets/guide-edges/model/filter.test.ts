import { describe, expect, it } from 'vitest';

import { cardMatches, edgeMatches, filtering, ideaMatches, type EdgeRowFacts } from './filter';

const edge = (over: Partial<EdgeRowFacts> = {}): EdgeRowFacts => ({
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

const none = { query: '' };

describe('Edges index filters', () => {
  it('lets every edge through with no filter and no search', () => {
    expect(edgeMatches(edge(), none)).toBe(true);
    expect(filtering(none)).toBe(false);
  });

  it('narrows by asset, side and holding band, each on the server’s id', () => {
    expect(edgeMatches(edge(), { query: '', asset: 'etfs' })).toBe(false);
    expect(edgeMatches(edge(), { query: '', side: 'long', holding: 'medium' })).toBe(true);
    expect(edgeMatches(edge(), { query: '', holding: 'short' })).toBe(false);
    expect(filtering({ query: 'x', side: 'long' })).toBe(true);
  });

  it('searches an edge’s name and thesis, ignoring case', () => {
    expect(edgeMatches(edge(), { query: 'EARLY' })).toBe(true);
    expect(edgeMatches(edge(), { query: 'momentum' })).toBe(false);
  });

  it('keeps a card when one of its edges passes, or the search names the mechanism', () => {
    const card = {
      title: 'Slow to update',
      question: 'Who is slow?',
      short: 'Prices absorb news in steps.',
      examples: 'drift',
      edges: [edge()],
    };
    expect(cardMatches(card, { query: '', asset: 'stocks' })).toBe(true);
    expect(cardMatches(card, { query: '', asset: 'etfs' })).toBe(false);
    expect(cardMatches({ ...card, edges: [] }, { query: 'slow' })).toBe(true);
    // With a structured filter in force the mechanism's own words no longer rescue an empty card.
    expect(cardMatches({ ...card, edges: [] }, { query: 'slow', asset: 'stocks' })).toBe(false);
  });

  it('searches an idea’s title and reason', () => {
    const idea = { title: 'Filing text change', whyNotBuilt: 'Needs filing history.' };
    expect(ideaMatches(idea, 'history')).toBe(true);
    expect(ideaMatches(idea, 'options')).toBe(false);
    expect(ideaMatches(idea, '  ')).toBe(true);
  });
});
