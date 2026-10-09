/**
 * The page cache kept between visits (owner decision 2026-10-09): the query cache's GraphQL
 * page reads are saved to IndexedDB, restored after the first paint so a returning visit renders
 * at once, and read again in the background (stale-while-revalidate: the client's short
 * `staleTime`). The record is valid for one user and one published session; a record older than
 * 24 h, of another session or of another user is dropped, a sign-out deletes it, it never
 * exceeds the byte cap (least recently used queries go first) and storage failures only switch
 * saving off: the page cache is an optimisation and must never hurt the browser.
 */
import { dehydrate, hashKey, hydrate, type QueryClient } from '@tanstack/react-query';
import { createStore, del, get, set } from 'idb-keyval';

import { queryKeys } from '@/shared/api';

import { fitToCap, isPersistableKey, type StoredQuery } from '../model/persist-cap';
import { fetchSessionDate } from './session-date';

/** Where the record lives (one key, one value: a JSON text, so its size is measured exactly). */
export const CACHE_KEY = 'page-cache';
/** A record older than this is not shown (the data is nightly). */
export const MAX_AGE_MS = 24 * 60 * 60 * 1000;
/** Writes are at least this far apart: a burst of loading pages is one write. */
export const THROTTLE_MS = 2_000;
const VERSION = 1;

const VIEWER_HASH = hashKey(queryKeys.gql('Viewer', {}));

/** The browser storage the record goes to (IndexedDB; a fake in tests). */
export interface PersistStore {
  get: (key: string) => Promise<string | undefined>;
  set: (key: string, value: string) => Promise<void>;
  del: (key: string) => Promise<void>;
}

export interface PersistDeps {
  /** Null: no storage in this browser (a private window, an old browser): nothing persists. */
  store: PersistStore | null;
  /** The date of the session the API reads now; null: nothing stored. */
  fetchSession: () => Promise<string | null>;
  now: () => number;
  /** The byte cap of the record. */
  cap?: number | undefined;
}

interface PersistedRecord {
  v: number;
  savedAt: number;
  /** The published session the data belongs to (the buster). */
  session: string;
  /** Whose data it is. */
  user: string;
  queries: StoredQuery[];
}

/** IndexedDB through idb-keyval, or null where the browser has none. */
function idbStore(): PersistStore | null {
  if (typeof indexedDB === 'undefined') return null;
  try {
    const store = createStore('algotrade', 'page-cache');
    return {
      get: (key) => get<string>(key, store),
      set: (key, value) => set(key, value, store),
      del: (key) => del(key, store),
    };
  } catch {
    return null;
  }
}

function defaultDeps(): PersistDeps {
  return { store: idbStore(), fetchSession: fetchSessionDate, now: Date.now };
}

function parseRecord(text: string | undefined): PersistedRecord | null {
  if (!text) return null;
  try {
    const record = JSON.parse(text) as Partial<PersistedRecord>;
    if (
      record.v !== VERSION ||
      typeof record.savedAt !== 'number' ||
      typeof record.session !== 'string' ||
      typeof record.user !== 'string' ||
      !Array.isArray(record.queries)
    ) {
      return null;
    }
    return record as PersistedRecord;
  } catch {
    return null;
  }
}

/** The persistence now running, so a second start for the same client does nothing. */
let running: { client: QueryClient; stop: () => void } | undefined;

/**
 * Starts saving and restoring `client`'s page cache; the returned function stops it. Never
 * throws and never blocks: the restore runs after the caller returns.
 */
export function startQueryPersistence(
  client: QueryClient,
  deps: PersistDeps = defaultDeps(),
): () => void {
  const { store, fetchSession, now } = deps;
  if (running?.client === client) return running.stop; // one per client, however many pages ask
  running?.stop();
  running = undefined;
  if (!store) return () => undefined;

  const lastUsed = new Map<string, number>();
  /** The restored queries not yet refetched: hash -> the `dataUpdatedAt` they came with. */
  let restored: { session: string; user: string; stamps: Map<string, number> } | null = null;
  let restoreDone = false;
  let session: string | null = null;
  let user: string | null = null;
  let disabled = false;
  let stopped = false;
  let timer: ReturnType<typeof setTimeout> | undefined;

  const safe = async (action: () => Promise<unknown>): Promise<void> => {
    try {
      await action();
    } catch {
      disabled = true; // a quota error or a blocked database: stop trying, keep the page working
    }
  };

  /** Drops what was restored when it is not this session's or this user's. */
  const reconcile = () => {
    if (!restored) return;
    const stale =
      (session !== null && restored.session !== session) ||
      (user !== null && restored.user !== user);
    if (!stale) return;
    const { stamps } = restored;
    restored = null;
    // Reset only the queries still holding the restored data (not refetched since): mounted
    // ones read again at once, so no page keeps showing another session's rows.
    void client.resetQueries({
      predicate: (query) => stamps.get(query.queryHash) === query.state.dataUpdatedAt,
    });
  };

  const flush = async () => {
    timer = undefined;
    if (disabled || stopped || !restoreDone || session === null || user === null) return;
    const dehydrated = dehydrate(client, {
      shouldDehydrateQuery: (query) =>
        query.state.status === 'success' && isPersistableKey(query.queryKey),
      shouldDehydrateMutation: () => false,
    });
    const queries = dehydrated.queries as unknown as StoredQuery[];
    const fitted = fitToCap(queries, lastUsed, deps.cap);
    const text =
      `{"v":${VERSION},"savedAt":${now()},"session":${JSON.stringify(session)},` +
      `"user":${JSON.stringify(user)},"queries":${fitted.queriesJson}}`;
    await safe(() => store.set(CACHE_KEY, text));
  };

  const schedule = () => {
    if (timer !== undefined || disabled || stopped) return;
    timer = setTimeout(() => void flush(), THROTTLE_MS);
  };

  const forget = () => {
    if (timer !== undefined) clearTimeout(timer);
    timer = undefined;
    user = null;
    restored = null;
    void safe(() => store.del(CACHE_KEY));
  };

  const learnUser = (data: unknown) => {
    if (data === null) {
      forget(); // signed out: nothing of the user stays in the browser
    } else if (typeof data === 'object' && 'id' in data) {
      user = String(data.id);
      reconcile();
      schedule();
    }
  };

  const unsubscribe = client.getQueryCache().subscribe((event) => {
    const { query } = event;
    if (query.queryHash === VIEWER_HASH) {
      if (event.type === 'updated' || event.type === 'added') learnUser(query.state.data);
      return;
    }
    if (event.type === 'observerAdded') lastUsed.set(query.queryHash, now());
    if (event.type === 'removed') schedule();
    if (event.type === 'updated' && event.action.type === 'success') {
      lastUsed.set(query.queryHash, now());
      schedule();
    }
  });

  const onHidden = () => {
    if (document.visibilityState === 'hidden' && timer !== undefined) {
      clearTimeout(timer);
      void flush();
    }
  };
  document.addEventListener('visibilitychange', onHidden);

  const restore = async () => {
    try {
      // Nothing is shown before the API says which session it reads: the record is rendered only
      // when its session is that one, so a page never shows the previous night's data.
      const [text] = await Promise.all([store.get(CACHE_KEY), sessionKnown]);
      if (stopped) return;
      const record = parseRecord(text);
      if (!record || now() - record.savedAt > MAX_AGE_MS) {
        if (text !== undefined) void safe(() => store.del(CACHE_KEY));
        return;
      }
      if (session === null || record.session !== session) {
        void safe(() => store.del(CACHE_KEY));
        return;
      }
      if (user === null && client.getQueryData(queryKeys.gql('Viewer', {})) === null) return;
      hydrate(client, { mutations: [], queries: record.queries as never });
      const stamps = new Map<string, number>();
      for (const q of record.queries) {
        const mine = client.getQueryCache().get(q.queryHash);
        if (mine && mine.state.dataUpdatedAt === q.state.dataUpdatedAt) {
          stamps.set(q.queryHash, q.state.dataUpdatedAt);
          lastUsed.set(q.queryHash, q.state.dataUpdatedAt);
        }
      }
      restored = { session: record.session, user: record.user, stamps };
      reconcile();
    } catch {
      void safe(() => store.del(CACHE_KEY)); // an unreadable record is dropped, never fatal
    } finally {
      restoreDone = true;
      schedule();
    }
  };

  // Without the session date nothing is restored or saved, nothing is trusted.
  const sessionKnown = fetchSession()
    .then((date) => {
      session = date;
      schedule();
    })
    .catch(() => undefined);
  void restore();
  learnUser(client.getQueryData(queryKeys.gql('Viewer', {})) ?? undefined);

  const stop = () => {
    stopped = true;
    if (running?.client === client) running = undefined;
    unsubscribe();
    if (timer !== undefined) clearTimeout(timer);
    document.removeEventListener('visibilitychange', onHidden);
  };
  running = { client, stop };
  return stop;
}
