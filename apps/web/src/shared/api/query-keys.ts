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
  explore: {
    tickers: (query: Readonly<Record<string, unknown>>) => ['explore', 'tickers', query] as const,
    compare: (ids: readonly string[], features: readonly string[]) =>
      ['explore', 'compare', ids, features] as const,
    prices: (ids: readonly string[], from: string | null) =>
      ['explore', 'prices', ids, from] as const,
  },
  ideas: {
    all: () => ['ideas'] as const,
    top: (limit: number) => ['ideas', 'top', limit] as const,
  },
  screeners: {
    all: () => ['screeners'] as const,
    list: () => ['screeners', 'list'] as const,
    mine: () => ['screeners', 'mine'] as const,
    detail: (id: string) => ['screeners', 'detail', id] as const,
    versions: (id: string) => ['screeners', 'versions', id] as const,
    preview: (spec: unknown) => ['screeners', 'preview', spec] as const,
    table: (id: string, query: Readonly<Record<string, unknown>>) =>
      ['screeners', 'table', id, query] as const,
    view: (id: string, name: string | null = null) =>
      ['screeners', 'view', id, name ?? ''] as const,
    views: (id: string) => ['screeners', 'view', id] as const,
    tables: (id: string) => ['screeners', 'table', id] as const,
    run: (id: string, jobId: string) => ['screeners', 'run', id, jobId] as const,
  },
  instruments: {
    detail: (id: string) => ['instruments', id] as const,
    bars: (id: string, from: string | null) => ['instruments', id, 'bars', from] as const,
    events: (id: string) => ['instruments', id, 'events'] as const,
    features: (id: string, from: string) => ['instruments', id, 'features', from] as const,
  },
  holdings: {
    etf: (id: string, top: number) => ['holdings', id, top] as const,
  },
  chains: {
    chain: (id: string, expiry: string | null) => ['chains', id, expiry] as const,
  },
  features: {
    catalogue: () => ['features'] as const,
    distribution: (name: string) => ['features', name, 'distribution'] as const,
    check: (expr: string) => ['features', 'check', expr] as const,
  },
} as const;
