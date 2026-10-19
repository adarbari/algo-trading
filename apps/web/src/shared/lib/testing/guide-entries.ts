/**
 * What `Query.guideEntries` answers for a test that thinks in single-entry reads: give the
 * entry as `Query.guideIndicator` / `guideEpisode` / `guideTerm` / `guideStartPage` would
 * (null: no such entry) and get the batch response holding it.
 */
interface SingleEntries {
  guideIndicator?: unknown;
  guideEpisode?: unknown;
  guideTerm?: unknown;
  guideStartPage?: unknown;
}

const listed = (entry: unknown): unknown[] => (entry == null ? [] : [entry]);

export function servedEntries(single: SingleEntries): { guideEntries: Record<string, unknown[]> } {
  return {
    guideEntries: {
      indicators: listed(single.guideIndicator),
      episodes: listed(single.guideEpisode),
      terms: listed(single.guideTerm),
      startPages: listed(single.guideStartPage),
    },
  };
}
