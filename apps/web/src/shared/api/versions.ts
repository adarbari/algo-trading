/**
 * The page cache follows the version the API answered from (ADR 0077 decision 18): `POST
 * /graphql` carries `x-config-generation` (the caller's config generation, on a user-keyed
 * operation only) and `x-release-id` (the serving release). When the generation rises with no
 * write of ours (another tab, a device, the CLI) the user-keyed queries are stale; when the
 * release changes the default session may have moved, so every query is. The web derives
 * nothing: which operations are user-keyed is what the API stamped, and a header absent is left
 * alone (a write in flight, the live path).
 */
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

function invalidateOthers(operation: string, only?: ReadonlySet<string>): void {
  void active.client?.invalidateQueries({
    predicate: ({ queryKey: [kind, name] }) =>
      kind === 'gql' && name !== operation && (!only || only.has(String(name))),
  });
}

/** Reads the version headers of `operation`'s answer and invalidates what they say is behind. */
export function observeVersions(operation: string, headers: Headers): void {
  const generation = headers.get('x-config-generation');
  if (generation !== null) {
    seen.userKeyed.add(operation);
    const n = Number(generation);
    if (seen.generation !== undefined && n > seen.generation) {
      invalidateOthers(operation, seen.userKeyed);
    }
    seen.generation = Math.max(n, seen.generation ?? n);
  }
  const release = headers.get('x-release-id');
  if (release !== null) {
    if (seen.release !== undefined && release !== seen.release) invalidateOthers(operation);
    seen.release = release;
  }
}
