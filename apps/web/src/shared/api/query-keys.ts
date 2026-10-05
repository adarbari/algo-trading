/**
 * TanStack Query keys, one factory per API resource, so caching and invalidation stay
 * consistent. Hooks live in entities/features; the keys live here next to the client.
 */
export const queryKeys = {
  health: () => ['health'] as const,
  /** A GraphQL operation: its name and variables (every GraphQL read is keyed this way). */
  gql: (operationName: string, variables: Readonly<Record<string, unknown>>) =>
    ['gql', operationName, variables] as const,
  /** Every cached response of one GraphQL operation, whatever its variables (invalidation). */
  gqlAll: (operationName: string) => ['gql', operationName] as const,
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
  screeners: {
    all: () => ['screeners'] as const,
    preview: (spec: unknown) => ['screeners', 'preview', spec] as const,
    table: (id: string, query: Readonly<Record<string, unknown>>) =>
      ['screeners', 'table', id, query] as const,
    view: (id: string, name: string | null = null) =>
      ['screeners', 'view', id, name ?? ''] as const,
    views: (id: string) => ['screeners', 'view', id] as const,
    tables: (id: string) => ['screeners', 'table', id] as const,
    run: (id: string, jobId: string) => ['screeners', 'run', id, jobId] as const,
  },
  features: {
    check: (expr: string) => ['features', 'check', expr] as const,
  },
} as const;
