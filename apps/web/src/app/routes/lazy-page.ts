/**
 * A route's page loaded on demand: `React.lazy` over a dynamic import, with `preload` so the
 * router can fetch the chunk on link intent. Not TanStack's `lazyRouteComponent`: its `Lazy`
 * wrapper calls `use()` on a promise it drops once resolved, which React 19 reports as
 * "called use() to suspend in a previous render but did not call use() when it finished".
 */
import { lazy, type ComponentType } from 'react';

type Module = Record<string, unknown>;

export function lazyPage<M extends Module, K extends keyof M>(
  importer: () => Promise<M>,
  name: K,
): M[K] & { preload: () => Promise<void> } {
  let loading: Promise<M> | undefined;
  const load = () => (loading ??= importer());
  const preload = () => load().then(() => undefined);
  const Page = lazy(() => load().then((m) => ({ default: m[name] as ComponentType })));
  return Object.assign(Page, { preload }) as unknown as M[K] & {
    preload: () => Promise<void>;
  };
}
