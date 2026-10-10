import { describe, expect, it } from 'vitest';

import type { EdgeSettings } from '../api/settings';
import {
  blankDraft,
  draftOf,
  incomplete,
  isDirty,
  isEdgeId,
  QUALITY_KEYS,
  toDocument,
  type EdgeDraft,
} from './draft';

const edge = {
  id: 'mine',
  name: 'My momentum',
  thesis: 'Winners keep winning',
  mechanism: 'Under-reaction',
  persistence: 'Limits to arbitrage',
  sources: [
    { title: 'JT 1993', url: 'https://doi.org/x' },
    { title: 'No link', url: '' },
  ],
  screeners: ['momo'],
  baselines: ['size_small'],
  horizons: [20, 60],
};

const served = (over: Partial<NonNullable<EdgeSettings['settings']>> = {}): EdgeSettings => ({
  schedule: 'on_event:earnings_reaction',
  frozenFrom: '2026-04-01',
  replaces: null,
  settings: {
    topK: 20,
    universe: 'liquid',
    kind: 'excess_return',
    benchmark: 'SPY',
    startOffsetSessions: 1,
    costBps: 15,
    qualityBar: QUALITY_KEYS.map((key) => ({ key, text: `answer ${key}` })),
    own: { extends: 'site_edge' },
    ...over,
  },
});

describe('draftOf', () => {
  it('starts from what the server resolved', () => {
    const d = draftOf(edge, served());
    expect(d).toMatchObject({
      id: 'mine',
      schedule: 'on_event',
      event: 'earnings_reaction',
      take: 'top',
      topK: 20,
      startOffset: 1,
      costBps: 15,
      win: 'beats',
      universe: 'liquid',
      horizons: [20, 60],
      frozenFrom: '2026-04-01',
    });
    expect(d.sources).toEqual([
      { title: 'JT 1993', url: 'https://doi.org/x' },
      { title: 'No link', url: '' },
    ]);
    expect(d.qualityBar.decoys).toBe('answer decoys');
  });

  it('reads "all that qualify", a win without a benchmark and a win test it cannot edit', () => {
    expect(draftOf(edge as never, served({ topK: null })).take).toBe('all');
    expect(draftOf(edge as never, served({ benchmark: 'none' })).win).toBe('rises');
    expect(draftOf(edge as never, served({ kind: 'hit_target' })).win).toBe('other');
  });
});

describe('toDocument', () => {
  const copy = (draft: EdgeDraft, own: Record<string, unknown>) =>
    toDocument(draft, own, 'site_edge');

  it('sends the whole document, extends included, from the draft', () => {
    const doc = copy(draftOf(edge, served()), { extends: 'site_edge' });
    expect(doc).toMatchObject({
      id: 'mine',
      extends: 'site_edge',
      name: 'My momentum',
      schedule: 'on_event:earnings_reaction',
      top_k: 20,
      universe: 'liquid',
      screeners: ['momo'],
      baselines: ['size_small'],
      frozen_from: '2026-04-01',
      outcome: {
        kind: 'excess_return',
        benchmark: 'SPY',
        horizon_sessions: [20, 60],
        start_offset_sessions: 1,
        cost_bps: 15,
      },
    });
    expect(doc.sources).toEqual([
      { title: 'JT 1993', url: 'https://doi.org/x' },
      { title: 'No link' },
    ]);
    expect(Object.keys(doc.quality_bar as object)).toEqual([...QUALITY_KEYS]);
  });

  it('a re-edit keeps an earlier override it did not touch', () => {
    // The file the user saved before: it set keys the builder does not edit.
    const own = {
      extends: 'site_edge',
      notes: 'my own note',
      variants: [{ id: 'plain', base: 'universe' }],
      outcome: { target: 0.05, cost_bps: 10 },
      quality_bar: { outcome: 'mine' },
      follow: { state: 'following' },
    };
    const draft = { ...draftOf(edge, served()), topK: 5 };
    const doc = copy(draft, own);
    expect(doc.notes).toBe('my own note');
    expect(doc.variants).toEqual([{ id: 'plain', base: 'universe' }]);
    expect((doc.outcome as Record<string, unknown>).target).toBe(0.05);
    expect(doc.top_k).toBe(5); // what the user changed
    expect((doc.outcome as Record<string, unknown>).cost_bps).toBe(15); // the draft's value wins
    expect(doc).not.toHaveProperty('follow'); // the state has its own call
  });

  it('keeps the win test of an edge the builder cannot edit, and an inline universe', () => {
    const d = draftOf(edge, served({ kind: 'hit_target', universe: '' }));
    const doc = copy(d, { extends: 'site_edge', outcome: { kind: 'hit_target', target: 2 } });
    expect(doc.outcome).toMatchObject({ kind: 'hit_target', target: 2 });
    expect(doc).not.toHaveProperty('universe');
  });

  it('writes every key of a new edge, "all" for no top N, and drops an empty out-of-sample start', () => {
    const d: EdgeDraft = {
      ...blankDraft(),
      id: 'fresh',
      name: ' Fresh ',
      thesis: 't',
      mechanism: 'm',
      persistence: 'p',
      sources: [
        { title: 'S', url: '' },
        { title: '', url: 'https://ignored' },
      ],
      screeners: ['momo'],
      universe: 'liquid',
      take: 'all',
      win: 'rises',
      schedule: 'month_end',
    };
    const doc = toDocument(d, {}, null);
    expect(doc).not.toHaveProperty('extends');
    expect(doc).not.toHaveProperty('frozen_from');
    expect(doc).toMatchObject({ id: 'fresh', name: 'Fresh', top_k: 'all', schedule: 'month_end' });
    expect(doc.sources).toEqual([{ title: 'S' }]);
    expect(doc.outcome).toMatchObject({ kind: 'excess_return', benchmark: 'none' });
  });
});

describe('incomplete', () => {
  const full = (): EdgeDraft => ({
    ...draftOf(edge, served()),
    id: 'mine',
  });

  it('is empty for a complete draft', () => {
    expect(incomplete(full(), 'clone')).toEqual([]);
  });

  it('names the step of each missing answer', () => {
    const d = full();
    expect(incomplete({ ...d, name: ' ' }, 'clone')).toEqual(['idea']);
    expect(incomplete({ ...d, qualityBar: { ...d.qualityBar, decoys: '' } }, 'clone')).toEqual([
      'idea',
    ]);
    expect(incomplete({ ...d, sources: [{ title: '', url: '' }] }, 'clone')).toEqual(['idea']);
    expect(incomplete({ ...d, screeners: [] }, 'clone')).toEqual(['screens']);
    expect(incomplete({ ...d, topK: null }, 'clone')).toEqual(['picks']);
    expect(incomplete({ ...d, take: 'all', topK: null }, 'clone')).toEqual([]);
    expect(incomplete({ ...d, horizons: [] }, 'clone')).toEqual(['trade']);
    expect(incomplete({ ...d, startOffset: 0 }, 'clone')).toEqual(['trade']);
    expect(incomplete({ ...d, frozenFrom: '2026-02-30' }, 'clone')).toEqual(['test']);
  });

  it('asks a new edge for an id and a universe', () => {
    expect(incomplete({ ...full(), id: 'Bad Id' }, 'new')).toEqual(['idea']);
    expect(incomplete({ ...full(), universe: '' }, 'new')).toEqual(['compare']);
    expect(incomplete({ ...full(), universe: '' }, 'clone')).toEqual([]);
  });
});

describe('isEdgeId and isDirty', () => {
  it('uses the API rule for ids', () => {
    expect(isEdgeId('a-b_9')).toBe(true);
    expect(isEdgeId('A')).toBe(false);
    expect(isEdgeId('')).toBe(false);
  });

  it('compares the draft with where it started', () => {
    const d = blankDraft();
    expect(isDirty(d, blankDraft())).toBe(false);
    expect(isDirty({ ...d, name: 'x' }, d)).toBe(true);
  });
});
