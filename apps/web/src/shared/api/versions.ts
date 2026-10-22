/**
 * The page cache follows the version the API answered from (ADR 0077 decision 18): `POST
 * /graphql` carries `x-config-generation` (the caller's config generation, on a user-keyed
 * operation only) and `x-release-id` (the serving release). When the generation rises (another
 * tab, a device, the CLI, or our own write) the other user-keyed queries are stale; the active
 * ones refetch, one extra round per write, not a loop (the answered query is spared, only its
 * own variables). When the release moves forward the default session may have moved, so every
 * other query is stale. The web derives nothing: which operations are user-keyed is what the
 * API stamped, and a header absent is left alone (a write in flight, the live path).
 *
 * Order: the generation only rises; a release id `{S}.{X}.f{F}` orders by (S, X, F), so an
 * answer from an older release arriving late is not a change. An answer that was in flight
 * across a write (older generation, arriving late) is refetched once its data has landed, so
 * pre-write data is never left fresh.
 *
 * The entry is at its byte budget: this module is not in it. `installVersions` (called by the
 * page-cache chunk when it starts) puts it behind `active`, which `gql` and the sign-out call.
 */
import { hashKey, type QueryClient, type QueryKey } from '@tanstack/react-query';

import { active } from './active-client';

const seen: {
  generation: number | undefined;
  release: string | undefined;
  userKeyed: Set<string>;
} = { generation: undefined, release: undefined, userKeyed: new Set() };
/** Retired answers wait here, by query hash, for their data to be stored (`refetchOnLanding`). */
const landing = new Set<string>();
let unsubscribe: (() => void) | undefined;

/** Nothing of the last user stays (sign-out, another user signing in). */
function forgetVersions(): void {
  seen.generation = seen.release = undefined;
  seen.userKeyed.clear();
  landing.clear();
  unsubscribe?.();
  unsubscribe = undefined;
}

/** Whether `next` is a release after `last`: `{S}.{X}.f{F}` read as its numbers, in order
 * (session date, sequence, format); an equal or older one, arriving late, is not a change. */
function moved(last: string, next: string): boolean {
  const a = last.split(/\D+/).map(Number);
  const b = next.split(/\D+/).map(Number);
  const i = a.findIndex((n, k) => n !== b[k]);
  return i >= 0 && (b[i] ?? 0) > (a[i] ?? 0);
}

/** Every query of the operations in `only` (all gql queries without it) but the answered one. */
function invalidateOthers(key: QueryKey | null | undefined, only?: ReadonlySet<string>): void {
  const answered = key && hashKey(key);
  void active.client?.invalidateQueries({
    predicate: ({ queryKey, queryHash }) =>
      queryKey[0] === 'gql' && queryHash !== answered && (!only || only.has(String(queryKey[1]))),
  });
}

/** An answer sent before a write is stored only after `gql` returned it: invalidate that query
 * when its fetch succeeds, or the stored data would clear the invalidation. One subscription,
 * dropped by `forgetVersions`. */
function refetchOnLanding(key: QueryKey): void {
  const client = active.client;
  if (!client) return;
  landing.add(hashKey(key));
  unsubscribe ??= client.getQueryCache().subscribe((event) => {
    if (event.type !== 'updated' || event.action.type !== 'success') return;
    if (!landing.delete(event.query.queryHash)) return;
    const stored: QueryKey = event.query.queryKey as QueryKey;
    void Promise.resolve().then(() => client.invalidateQueries({ queryKey: stored, exact: true }));
  });
}

/** Reads the version headers of the answer to the query `key` (`null`: asked outside a query,
 * nothing to spare or refetch) and invalidates what they say is behind. */
export function observeVersions(key: QueryKey | null | undefined, headers: Headers): void {
  const generation = headers.get('x-config-generation');
  if (generation !== null) {
    const n = Number(generation);
    if (key) seen.userKeyed.add(String(key[1]));
    if (seen.generation !== undefined && n > seen.generation) {
      invalidateOthers(key, seen.userKeyed);
    } else if (key && seen.generation !== undefined && n < seen.generation) {
      refetchOnLanding(key); // sent before a write
    }
    seen.generation = Math.max(n, seen.generation ?? n);
  }
  const release = headers.get('x-release-id');
  if (release !== null && (seen.release === undefined || moved(seen.release, release))) {
    if (seen.release !== undefined) invalidateOthers(key);
    seen.release = release;
  }
}

/** Starts following the versions of the answers (`gql` reads `active.observe`) in `client`; the
 * counters are the signed-in user's, so another user (or none) in the viewer query ends them. */
export function installVersions(client: QueryClient): void {
  active.observe = observeVersions;
  let user: unknown;
  client.getQueryCache().subscribe((event) => {
    if (event.type !== 'updated' || event.action.type !== 'success') return;
    if ((event.query.queryKey as QueryKey)[1] !== 'Viewer') return;
    const id = (event.query.state.data as { id?: string } | null)?.id;
    if (user !== undefined && id !== user) forgetVersions();
    user = id;
  });
}

export { forgetVersions };
