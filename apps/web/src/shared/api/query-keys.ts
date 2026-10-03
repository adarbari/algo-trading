/**
 * TanStack Query keys, one factory per API resource, so caching and invalidation stay
 * consistent. Hooks live in entities/features; the keys live here next to the client.
 */
export const queryKeys = {
  health: () => ['health'] as const,
  admin: {
    all: () => ['admin'] as const,
    completeness: (sessions: number) => ['admin', 'ingestion', 'completeness', sessions] as const,
    cell: (dataset: string, session: string) =>
      ['admin', 'ingestion', 'cell', dataset, session] as const,
    nightlyRuns: (limit: number) => ['admin', 'runs', 'nightly', limit] as const,
    run: (runId: string) => ['admin', 'runs', 'run', runId] as const,
    runItems: (runId: string) => ['admin', 'runs', 'run', runId, 'items'] as const,
    quality: () => ['admin', 'quality'] as const,
    verification: () => ['admin', 'verification', 'ibkr'] as const,
    figiReview: () => ['admin', 'review', 'figi'] as const,
    leveragedReview: () => ['admin', 'review', 'leveraged'] as const,
  },
} as const;
