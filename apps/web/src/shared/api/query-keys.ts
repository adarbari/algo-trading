/**
 * TanStack Query keys, one factory per API resource, so caching and invalidation stay
 * consistent. Hooks live in entities/features; the keys live here next to the client.
 */
export const queryKeys = {
  health: () => ['health'] as const,
  /** A GraphQL operation: its name and variables (every GraphQL read is keyed this way). */
  gql: (operationName: string, variables: Readonly<Record<string, unknown>>) =>
    ['gql', operationName, variables] as const,
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
  features: {
    catalogue: () => ['features'] as const,
    distribution: (name: string) => ['features', name, 'distribution'] as const,
    check: (expr: string) => ['features', 'check', expr] as const,
  },
} as const;
