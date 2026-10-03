/**
 * A settled read-hook result for widget and page tests that mock an entity's hooks: the
 * fields the app reads from a TanStack Query result (data, pending / error / fetching flags,
 * error, refetch), without a query client.
 */
import { vi } from 'vitest';

export interface FakeQuery<T> {
  data: T | undefined;
  error: unknown;
  isPending: boolean;
  isError: boolean;
  isFetching: boolean;
  isSuccess: boolean;
  refetch: () => Promise<unknown>;
}

export function fakeQuery<T>(data: T | undefined, state: Partial<FakeQuery<T>> = {}): FakeQuery<T> {
  return {
    data,
    error: null,
    isPending: data === undefined && !state.isError,
    isError: false,
    isFetching: false,
    isSuccess: data !== undefined,
    refetch: vi.fn(() => Promise.resolve()),
    ...state,
  };
}
