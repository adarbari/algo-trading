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
 * across a write (older generation, arriving late) is refetched once it has settled, so
 * pre-write data is never left fresh.
 */
import { hashKey, type QueryKey } from '@tanstack/react-query';

import { active } from './active-client';

const seen: {
  generation: number | undefined;
  release: string | undefined;
  userKeyed: Set<string>;
} = {
  generation: undefined,
  release: undefined,
  userKeyed: new Set(),
};

/** Nothing of the last user stays (sign-out, another user signing in). */
export function forgetVersions(): void {
  seen.generation = undefined;
  seen.release = undefined;
  seen.userKeyed.clear();
}

/** `{S}.{X}.f{F}` as a comparable triple (session, sequence, format); null when it is not. */
function order(release: string): [string, number, number] | null {
  const m = /^([^.]+)\.(\d+)\.f(\d+)$/.exec(release);
  return m ? [m[1] ?? '', Number(m[2]), Number(m[3])] : null;
}

/** Whether `next` is a release other than `last`, and not an older one. */
function moved(last: string, next: string): boolean {
  const a = order(last);
  const b = order(next);
  if (a === null || b === null) return last !== next;
  if (a[0] !== b[0]) return b[0] > a[0];
  return b[1] !== a[1] ? b[1] > a[1] : b[2] > a[2];
}

function invalidateOthers(key: QueryKey, only?: ReadonlySet<string>): void {
  const answered = hashKey(key);
  void active.client?.invalidateQueries({
    predicate: ({ queryKey, queryHash }) =>
      queryKey[0] === 'gql' && queryHash !== answered && (!only || only.has(String(queryKey[1]))),
  });
}

/** Reads the version headers of the answer to the query `key` and invalidates what they say is
 * behind. */
export function observeVersions(key: QueryKey, headers: Headers): void {
  const operation = String(key[1]);
  const generation = headers.get('x-config-generation');
  if (generation !== null) {
    seen.userKeyed.add(operation);
    const n = Number(generation);
    if (seen.generation !== undefined && n > seen.generation) {
      invalidateOthers(key, seen.userKeyed);
    } else if (seen.generation !== undefined && n < seen.generation) {
      // sent before a write: refetch it once its data has landed
      setTimeout(() => void active.client?.invalidateQueries({ queryKey: key, exact: true }), 0);
    }
    seen.generation = Math.max(n, seen.generation ?? n);
  }
  const release = headers.get('x-release-id');
  if (release !== null) {
    if (seen.release === undefined || moved(seen.release, release)) {
      if (seen.release !== undefined) invalidateOthers(key);
      seen.release = release;
    }
  }
}
