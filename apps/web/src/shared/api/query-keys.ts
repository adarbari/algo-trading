/**
 * TanStack Query keys, one factory per API resource, so caching and invalidation stay
 * consistent. Hooks live in entities/features; the keys live here next to the client.
 */
export const queryKeys = {
  health: () => ['health'] as const,
} as const;
