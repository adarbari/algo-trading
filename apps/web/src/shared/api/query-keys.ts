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
