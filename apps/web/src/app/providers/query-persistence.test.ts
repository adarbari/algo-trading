import { QueryClient } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { queryKeys } from '@/shared/api';

import {
  CACHE_KEY,
  MAX_AGE_MS,
  startQueryPersistence,
  THROTTLE_MS,
  type PersistStore,
} from './query-persistence';

const NOW = Date.UTC(2026, 9, 9, 12);

function fakeStore(initial?: string) {
  const data = new Map<string, string>();
  if (initial !== undefined) data.set(CACHE_KEY, initial);
  const store: PersistStore & { data: Map<string, string> } = {
    data,
    get: (key) => Promise.resolve(data.get(key)),
    set: (key, value) => {
      data.set(key, value);
      return Promise.resolve();
    },
    del: (key) => {
      data.delete(key);
      return Promise.resolve();
    },
  };
  return store;
}

function record(session: string, user = 'u1', savedAt = NOW - 1000) {
  const key = queryKeys.gql('IdeasPage', {});
  return JSON.stringify({
    v: 1,
    savedAt,
    session,
    user,
    queries: [
      {
        queryHash: JSON.stringify(key),
        queryKey: key,
        state: {
          data: { rows: ['old'] },
          dataUpdatedAt: savedAt,
          dataUpdateCount: 1,
          error: null,
          errorUpdateCount: 0,
          errorUpdatedAt: 0,
          fetchFailureCount: 0,
          fetchFailureReason: null,
          fetchMeta: null,
          isInvalidated: false,
          status: 'success',
          fetchStatus: 'idle',
        },
      },
    ],
  });
}

const flush = () => vi.advanceTimersByTimeAsync(THROTTLE_MS + 10);
const saved = (store: ReturnType<typeof fakeStore>) =>
  JSON.parse(store.data.get(CACHE_KEY) ?? 'null') as {
    session: string;
    queries: { queryKey: unknown[] }[];
  } | null;

function start(store: PersistStore, session: string | null = 's1', cap?: number) {
  const client = new QueryClient();
  client.setQueryData(queryKeys.gql('Viewer', {}), { id: 'u1' });
  const stop = startQueryPersistence(client, {
    store,
    fetchSession: () => Promise.resolve(session),
    now: () => Date.now(),
    cap,
  });
  return { client, stop };
}

beforeEach(() => {
  vi.useFakeTimers({ now: NOW });
});
afterEach(() => {
  vi.useRealTimers();
});

describe('startQueryPersistence', () => {
  it('saves page reads under the session date, throttled into one write', async () => {
    const store = fakeStore();
    const set = vi.spyOn(store, 'set');
    const { client, stop } = start(store);
    await vi.advanceTimersByTimeAsync(0);
    client.setQueryData(queryKeys.gql('IdeasPage', {}), { rows: [1] });
    client.setQueryData(queryKeys.gql('EdgesPage', {}), { rows: [2] });
    await vi.advanceTimersByTimeAsync(THROTTLE_MS - 100);
    expect(set).not.toHaveBeenCalled(); // not before the throttle window is over
    await flush();
    expect(set).toHaveBeenCalledTimes(1);
    expect(saved(store)?.session).toBe('s1');
    expect(saved(store)?.queries).toHaveLength(2);
    stop();
  });

  it('never persists live quotes, previews, job polling, the viewer or a mutation', async () => {
    const store = fakeStore();
    const { client, stop } = start(store);
    await vi.advanceTimersByTimeAsync(0);
    client.setQueryData(queryKeys.gql('IdeasPage', {}), { rows: [1] });
    client.setQueryData(queryKeys.gql('OptionQuotes', { id: 'x' }), { live: 1 });
    client.setQueryData(queryKeys.screeners.preview({ a: 1 }), { rows: [] });
    client.setQueryData(queryKeys.screeners.run('a', 'job'), { status: 'running' });
    client.setQueryData(queryKeys.edges.evaluation('a', 'job'), { status: 'running' });
    await flush();
    const keys = saved(store)?.queries.map((q) => q.queryKey[1]);
    expect(keys).toEqual(['IdeasPage']);
    stop();
  });

  it('keeps the record under the byte cap, dropping the least recently used queries', async () => {
    const store = fakeStore();
    const { client, stop } = start(store, 's1', 1024 + 1700);
    await vi.advanceTimersByTimeAsync(0);
    for (const name of ['A', 'B', 'C']) {
      client.setQueryData(queryKeys.gql(name, {}), { text: 'x'.repeat(400) });
      await vi.advanceTimersByTimeAsync(5);
    }
    await flush();
    const text = store.data.get(CACHE_KEY) ?? '';
    expect(new TextEncoder().encode(text).length).toBeLessThanOrEqual(1024 + 1700);
    expect(saved(store)?.queries.map((q) => q.queryKey[1])).toEqual(['C', 'B']);
    stop();
  });

  it('restores a saved record at once and keeps it while the session date is the same', async () => {
    const store = fakeStore(record('s1'));
    const { client, stop } = start(store, 's1');
    await vi.advanceTimersByTimeAsync(0);
    expect(client.getQueryData(queryKeys.gql('IdeasPage', {}))).toEqual({ rows: ['old'] });
    stop();
  });

  it('renders nothing of a record until the session date answers, and drops another session', async () => {
    const store = fakeStore(record('s1'));
    let answer: (date: string) => void = () => undefined;
    const client = new QueryClient();
    client.setQueryData(queryKeys.gql('Viewer', {}), { id: 'u1' });
    const stop = startQueryPersistence(client, {
      store,
      fetchSession: () => new Promise((resolve) => (answer = resolve)),
      now: () => Date.now(),
    });
    await vi.advanceTimersByTimeAsync(0);
    expect(client.getQueryData(queryKeys.gql('IdeasPage', {}))).toBeUndefined(); // not yet
    answer('s2');
    await vi.advanceTimersByTimeAsync(0);
    expect(client.getQueryData(queryKeys.gql('IdeasPage', {}))).toBeUndefined(); // never shown
    expect(store.data.has(CACHE_KEY)).toBe(false);
    stop();
  });

  it('is busted by a new session: the old record is dropped, the new one is saved', async () => {
    const store = fakeStore(record('s1'));
    const { client, stop } = start(store, 's2');
    await vi.advanceTimersByTimeAsync(0);
    expect(client.getQueryData(queryKeys.gql('IdeasPage', {}))).toBeUndefined();
    await flush();
    expect(saved(store)?.session).toBe('s2');
    stop();
  });

  it('is busted by another user', async () => {
    const store = fakeStore(record('s1', 'someone-else'));
    const { client, stop } = start(store, 's1');
    await vi.advanceTimersByTimeAsync(0);
    expect(client.getQueryData(queryKeys.gql('IdeasPage', {}))).toBeUndefined();
    stop();
  });

  it('drops a record older than 24 hours', async () => {
    const store = fakeStore(record('s1', 'u1', NOW - MAX_AGE_MS - 1));
    const { client, stop } = start(store, 's1');
    await vi.advanceTimersByTimeAsync(0);
    expect(client.getQueryData(queryKeys.gql('IdeasPage', {}))).toBeUndefined();
    expect(store.data.has(CACHE_KEY)).toBe(false);
    stop();
  });

  it('is cleared on sign-out, and a pending write does not bring it back', async () => {
    const store = fakeStore();
    const { client, stop } = start(store);
    await vi.advanceTimersByTimeAsync(0);
    client.setQueryData(queryKeys.gql('IdeasPage', {}), { rows: [1] });
    await flush();
    expect(store.data.has(CACHE_KEY)).toBe(true);
    client.setQueryData(queryKeys.gql('EdgesPage', {}), { rows: [2] }); // a write is pending
    client.setQueryData(queryKeys.gql('Viewer', {}), null); // the sign-out
    await vi.advanceTimersByTimeAsync(0);
    expect(store.data.has(CACHE_KEY)).toBe(false);
    await flush();
    expect(store.data.has(CACHE_KEY)).toBe(false);
    stop();
  });

  it('saves nothing while the session date is unknown', async () => {
    const store = fakeStore();
    const { client, stop } = start(store, null);
    client.setQueryData(queryKeys.gql('IdeasPage', {}), { rows: [1] });
    await flush();
    expect(store.data.has(CACHE_KEY)).toBe(false);
    stop();
  });

  it('survives a failing store: saving stops, nothing throws', async () => {
    const store = fakeStore();
    vi.spyOn(store, 'set').mockRejectedValue(new Error('QuotaExceededError'));
    const { client, stop } = start(store);
    await vi.advanceTimersByTimeAsync(0);
    client.setQueryData(queryKeys.gql('IdeasPage', {}), { rows: [1] });
    await flush();
    client.setQueryData(queryKeys.gql('EdgesPage', {}), { rows: [2] });
    await flush();
    expect(store.set).toHaveBeenCalledTimes(1);
    stop();
  });

  it('does nothing without a store (no IndexedDB)', () => {
    const client = new QueryClient();
    const stop = startQueryPersistence(client, {
      store: null,
      fetchSession: () => Promise.resolve('s1'),
      now: () => Date.now(),
    });
    expect(stop()).toBeUndefined();
  });
});
