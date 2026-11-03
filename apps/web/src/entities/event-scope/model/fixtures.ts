/** Test builders for the event-scope entity (exported for widget and page tests). */
import type { EventScope, RemovedName, ScopeName } from './types';

export const scopeName = (over: Partial<ScopeName> = {}): ScopeName => ({
  instrumentId: 'fig-aapl',
  symbol: 'AAPL',
  reasons: ['list'],
  source: 'site',
  addedOn: '2026-10-01',
  note: '',
  by: null,
  at: null,
  lastReview: '2026-10-20',
  stale: false,
  moves: { big: 20, attributed: 15, share: 0.75 },
  ...over,
});

export const removedName = (over: Partial<RemovedName> = {}): RemovedName => ({
  symbol: 'XYZ',
  by: 'ana',
  at: '2026-10-30T12:00:00+00:00',
  note: 'delisted',
  reasons: [],
  ...over,
});

export const eventScope = (over: Partial<EventScope> = {}): EventScope => ({
  session: '2026-11-02',
  staleDays: 90,
  staleCount: 1,
  names: [
    scopeName(),
    scopeName({
      instrumentId: 'fig-msft',
      symbol: 'MSFT',
      reasons: ['list', 'tier'],
      source: 'admin',
      by: 'ana',
      at: '2026-10-25T09:00:00+00:00',
      lastReview: null,
      stale: true,
      moves: null,
    }),
  ],
  removed: [removedName()],
  unresolved: [],
  otherNames: 1200,
  macroDays: 90,
  macroReleases: 14,
  macroUnknown: null,
  ...over,
});
